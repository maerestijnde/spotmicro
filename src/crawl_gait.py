#!/usr/bin/env python3
"""
MicroSpot Crawl Gait Module
Implements an 8-phase statically-stable crawl gait with active body shifting.

Sequence:
    0. Shift body over FR+RL+RR triangle (prep for FL lift)
    1. FL swing (lift, move forward, place)
    2. Shift body over FL+FR+RL triangle (prep for RR lift)
    3. RR swing
    4. Shift body over FL+RL+RR triangle (prep for FR lift)
    5. FR swing
    6. Shift body over FL+FR+RR triangle (prep for RL lift)
    7. RL swing

Body shifting is done via SpotMicroStickFigure inverse kinematics when available.
If IK is unavailable, a simplified angle-based fallback is used (no CoG shifting,
but still only one leg moves at a time).
"""
import time
import math
from typing import Callable, Optional, Dict, Tuple
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent

# Try to import IK / kinematics
try:
    from ik_interface import IKInterface
    from kinematics.spot_micro_stick_figure import SpotMicroStickFigure
    import numpy as np
    IK_AVAILABLE = True
except ImportError:
    IK_AVAILABLE = False

# Balance control
try:
    from balance import BalanceController
    BALANCE_AVAILABLE = True
except ImportError:
    BALANCE_AVAILABLE = False

# Default calibration
_DEFAULT_CALIBRATION = _SCRIPT_DIR / "calibration.json"

GAIT_UPDATE_RATE = 0.02  # 50 Hz

LEG_CHANNELS = {
    "FL": {"hip": 0, "knee": 1, "ankle": 2, "side": "left"},
    "FR": {"hip": 3, "knee": 4, "ankle": 5, "side": "right"},
    "RL": {"hip": 6, "knee": 7, "ankle": 8, "side": "left"},
    "RR": {"hip": 9, "knee": 10, "ankle": 11, "side": "right"},
}

# Knee/ankle movement ratios (same as trot gait)
KNEE_FORWARD_RATIO = 0.7
ANKLE_FORWARD_RATIO = 0.3
ANKLE_LIFT_RATIO = 0.8

# Phase definitions
SHIFT_PHASE = 0
SWING_PHASE = 1

# Default crawl parameters
DEFAULT_KNEE_BEND = 40
DEFAULT_ANKLE_COMP = 1.3


class CrawlGaitController:
    """
    8-phase crawl gait controller with body shifting.

    When IK is available, the controller actively shifts the robot's body
    toward the support triangle of the three grounded legs before lifting
    a leg. This keeps the CoG inside the support polygon.

    When IK is unavailable, it falls back to a simplified angle-based crawl
    gait without explicit body shifting (still only one leg moves at a time).
    """

    def __init__(
        self,
        set_servo_func: Callable[[int, float, bool], bool],
        use_ik: bool = True,
    ):
        self.set_servo = set_servo_func
        self.running = False
        self.direction = "forward"
        self.cycle_time = 4.0  # seconds per full 8-phase cycle
        self.speed = 1.0

        # Step parameters (angle-based fallback)
        self.step_height = 30      # degrees
        self.step_length = 12      # degrees
        self.knee_bend = DEFAULT_KNEE_BEND
        self.ankle_comp = int(self.knee_bend * DEFAULT_ANKLE_COMP)

        # Body shift parameters (IK mode)
        self.body_shift_ratio = 0.35   # fraction of support triangle center to shift toward
        self.shift_smooth = 0.5        # cosine smoothing for body shifts

        # IK mode
        self.use_ik = use_ik and IK_AVAILABLE
        self.ik_interface = None
        self._stick_figure = None
        self._neutral_feet = None

        if self.use_ik:
            try:
                self.ik_interface = IKInterface(
                    calibration_path=str(_DEFAULT_CALIBRATION),
                    body_height=0.10,
                )
                self._stick_figure = SpotMicroStickFigure(x=0, y=0.10, z=0)
                self._neutral_feet = self.ik_interface.get_neutral_foot_positions()
                print("CrawlGait: IK body-shifting enabled")
            except Exception as e:
                print(f"CrawlGait: IK init failed ({e}), using angle-based fallback")
                self.use_ik = False

        # Interpolation cache
        self._current_angles: Dict[int, float] = {}
        self._interp_speed = 1.0

        # Balance
        self.balance = None
        self.use_balance = False
        if BALANCE_AVAILABLE:
            try:
                self.balance = BalanceController()
            except Exception:
                pass

        # Stand angles
        self._rear_knee_comp = {"RL": -4, "RR": +5}
        self._rear_ankle_comp = {"RL": 0, "RR": 0}
        self._update_stand_angles()

        # 8-phase sequence: (phase_type, leg_id)
        # leg_id=None for shift phases
        self.phase_sequence = [
            (SHIFT_PHASE, "FL"),   # 0: shift body for FL
            (SWING_PHASE, "FL"),   # 1: FL swing
            (SHIFT_PHASE, "RR"),   # 2: shift body for RR
            (SWING_PHASE, "RR"),   # 3: RR swing
            (SHIFT_PHASE, "FR"),   # 4: shift body for FR
            (SWING_PHASE, "FR"),   # 5: FR swing
            (SHIFT_PHASE, "RL"),   # 6: shift body for RL
            (SWING_PHASE, "RL"),   # 7: RL swing
        ]

        # Body shift targets (fraction of body dimensions toward support center)
        # These are approximate shifts in meters (x=forward, z=left/right)
        # Positive x = forward, positive z = right
        hl = 0.093   # half body length (0.186/2)
        hw = 0.078   # half body width  (0.078/2) + hip offset
        self._shift_targets = {
            "FL": ( hl * 0.25,  hw * 0.25),   # shift back-right for FL lift
            "RR": (-hl * 0.25, -hw * 0.25),   # shift front-left for RR lift
            "FR": ( hl * 0.25, -hw * 0.25),   # shift back-left for FR lift
            "RL": (-hl * 0.25,  hw * 0.25),   # shift front-right for RL lift
        }

        # Cached balance
        self._balance_corrections: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Stand / params
    # ------------------------------------------------------------------
    def _update_stand_angles(self):
        k = 90 - self.knee_bend
        a = 90 + self.ankle_comp
        self.stand_angles = {
            "FL": {"hip": 90, "knee": k, "ankle": a},
            "FR": {"hip": 90, "knee": k, "ankle": a},
            "RL": {"hip": 90, "knee": k + self._rear_knee_comp["RL"],
                   "ankle": a + self._rear_ankle_comp["RL"]},
            "RR": {"hip": 90, "knee": k + self._rear_knee_comp["RR"],
                   "ankle": a + self._rear_ankle_comp["RR"]},
        }

    def set_params(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ("running", "thread", "set_servo"):
                setattr(self, key, value)
                print(f"  Crawl param {key} = {value}")
        if "knee_bend" in kwargs:
            self.ankle_comp = int(self.knee_bend * DEFAULT_ANKLE_COMP)
            self._update_stand_angles()

    def set_stand_height(self, knee_bend: int):
        knee_bend = max(0, min(80, knee_bend))
        self.knee_bend = knee_bend
        self.ankle_comp = int(knee_bend * DEFAULT_ANKLE_COMP)
        self._update_stand_angles()
        return self.stand_angles

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------
    def enable_balance(self, enable=True, calibrate=True):
        if not BALANCE_AVAILABLE or not self.balance:
            return False
        self.use_balance = enable
        if enable and calibrate:
            self.balance.calibrate(30)
        print(f"Crawl balance: {'ON' if enable else 'OFF'}")
        return True

    def _update_balance_corrections(self):
        if self.use_balance and self.balance:
            try:
                self._balance_corrections = self.balance.get_correction()
            except Exception:
                self._balance_corrections = {}
        else:
            self._balance_corrections = {}

    # ------------------------------------------------------------------
    # Interpolation / servo helpers
    # ------------------------------------------------------------------
    def _interpolate(self, ch: int, target: float) -> float:
        if ch not in self._current_angles:
            self._current_angles[ch] = target
            return target
        cur = self._current_angles[ch]
        new = cur + (target - cur) * self._interp_speed
        self._current_angles[ch] = new
        return new

    def _apply_leg_angles(self, leg_id: str, angles: Dict[str, float]):
        leg = LEG_CHANNELS[leg_id]
        bal = self._balance_corrections.get(leg_id, 0)
        hip = int(self._interpolate(leg["hip"], angles["hip"]))
        knee = int(self._interpolate(leg["knee"], angles["knee"] + bal))
        ankle = int(self._interpolate(leg["ankle"], angles["ankle"] - bal * 0.5))
        self.set_servo(leg["hip"], hip, True)
        self.set_servo(leg["knee"], knee, True)
        self.set_servo(leg["ankle"], ankle, True)

    # ------------------------------------------------------------------
    # Body shifting (IK mode)
    # ------------------------------------------------------------------
    def _compute_body_shift_angles(
        self, target_leg: str, phase: float
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute servo angles for all legs while shifting the body toward
        the support triangle of the three grounded legs.

        Args:
            target_leg: the leg that will be lifted next
            phase: 0.0 to 1.0 through the shift motion

        Returns:
            dict of {leg_id: {hip, knee, ankle}} logical angles
        """
        if not self.use_ik or self._stick_figure is None:
            return {}

        # Get shift target for this leg
        dx, dz = self._shift_targets.get(target_leg, (0.0, 0.0))

        # Smooth the shift with cosine interpolation
        smooth = (1.0 - math.cos(phase * math.pi)) / 2.0
        sx = dx * smooth
        sz = dz * smooth

        # Build a temporary stick figure with shifted body position
        sf = SpotMicroStickFigure(x=sx, y=0.10, z=sz)

        # Keep all feet at their neutral absolute positions
        nf = self._neutral_feet
        coords = np.array([
            nf["RR"],  # rightback  (index 0)
            nf["FR"],  # rightfront (index 1)
            nf["FL"],  # leftfront  (index 2)
            nf["RL"],  # leftback   (index 3)
        ])
        sf.set_absolute_foot_coordinates(coords)
        ik = sf.get_leg_angles()

        # Convert to logical angles (same convention as ik_interface)
        result = {}
        leg_map = {
            "RR": (0, False), "FR": (1, False),
            "FL": (2, True),  "RL": (3, True),
        }
        for leg_id, (idx, is_left) in leg_map.items():
            q1, q2, q3 = ik[idx]
            if is_left:
                result[leg_id] = {
                    "hip": 90.0 - math.degrees(q1),
                    "knee": 90.0 + math.degrees(q2),
                    "ankle": 90.0 + math.degrees(q3),
                }
            else:
                result[leg_id] = {
                    "hip": 90.0 + math.degrees(q1),
                    "knee": 90.0 - math.degrees(q2),
                    "ankle": 90.0 + math.degrees(q3),
                }
        return result

    # ------------------------------------------------------------------
    # Swing (angle-based fallback)
    # ------------------------------------------------------------------
    def _leg_angles_swing(self, phase: float, leg_id: str) -> Dict[str, float]:
        stand = self.stand_angles[leg_id]
        dir_mult = -1.0 if self.direction == "backward" else 1.0

        lift = self.step_height * math.sin(phase * math.pi)
        fwd = self.step_length * dir_mult * (phase * 2 - 1)

        knee_offset = -lift + fwd * KNEE_FORWARD_RATIO
        ankle_offset = lift * ANKLE_LIFT_RATIO + fwd * ANKLE_FORWARD_RATIO
        hip_offset = 0  # crawl uses less hip swing

        return {
            "hip": stand["hip"] + hip_offset,
            "knee": stand["knee"] + knee_offset,
            "ankle": stand["ankle"] + ankle_offset,
        }

    def _leg_angles_stance(self, leg_id: str) -> Dict[str, float]:
        """During crawl, stance legs hold their stand position (possibly with small push)."""
        return self.stand_angles[leg_id].copy()

    # ------------------------------------------------------------------
    # Main gait loop
    # ------------------------------------------------------------------
    def _gait_loop(self):
        print(f"\n{'=' * 60}")
        print(f"CRAWL GAIT STARTED - Direction: {self.direction}")
        print(f"Mode: {'IK+BodyShift' if self.use_ik else 'Angle-based'}")
        print(f"Cycle time: {self.cycle_time}s")
        print(f"{'=' * 60}\n")

        cycle_time = self.cycle_time / self.speed
        phase_duration = cycle_time / 8.0
        start_time = time.time()
        last_phase_idx = -1

        while self.running:
            self._update_balance_corrections()

            elapsed = time.time() - start_time
            cycle_phase = (elapsed % cycle_time) / cycle_time
            phase_idx = min(int(cycle_phase * 8), 7)
            phase_local = (cycle_phase * 8) - phase_idx  # 0..1 within current phase

            if phase_idx != last_phase_idx:
                ptype, leg = self.phase_sequence[phase_idx]
                desc = "SHIFT" if ptype == SHIFT_PHASE else f"SWING {leg}"
                print(f"  Phase {phase_idx}: {desc}")
                last_phase_idx = phase_idx

            ptype, target_leg = self.phase_sequence[phase_idx]

            if ptype == SHIFT_PHASE:
                # Body shift phase
                if self.use_ik:
                    angles = self._compute_body_shift_angles(target_leg, phase_local)
                    for leg_id in LEG_CHANNELS:
                        if leg_id in angles:
                            self._apply_leg_angles(leg_id, angles[leg_id])
                else:
                    # Angle-based fallback: all legs hold stand position
                    for leg_id in LEG_CHANNELS:
                        self._apply_leg_angles(leg_id, self.stand_angles[leg_id])
            else:
                # Swing phase: one leg swings, others hold (or follow body shift)
                swing_angles = self._leg_angles_swing(phase_local, target_leg)

                if self.use_ik:
                    # During swing, body is already shifted; compute shifted stance for others
                    shift_angles = self._compute_body_shift_angles(target_leg, 1.0)
                else:
                    shift_angles = {}

                for leg_id in LEG_CHANNELS:
                    if leg_id == target_leg:
                        self._apply_leg_angles(leg_id, swing_angles)
                    elif leg_id in shift_angles:
                        self._apply_leg_angles(leg_id, shift_angles[leg_id])
                    else:
                        self._apply_leg_angles(leg_id, self.stand_angles[leg_id])

            time.sleep(GAIT_UPDATE_RATE)

        print(f"\n{'=' * 60}")
        print("CRAWL GAIT STOPPED")
        print(f"{'=' * 60}\n")
        self._return_to_stand()

    def _return_to_stand(self):
        print("Returning to stand...")
        self._update_balance_corrections()
        for leg_id in LEG_CHANNELS:
            self._apply_leg_angles(leg_id, self.stand_angles[leg_id])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def goto_stand(self):
        print(f"\n{'=' * 60}")
        print("CRAWL: GOING TO STAND")
        print(f"{'=' * 60}")
        self._update_balance_corrections()
        for leg_id, angles in self.stand_angles.items():
            self._apply_leg_angles(leg_id, angles)

    def start(self, direction: str = "forward"):
        if self.running:
            print("Crawl gait already running")
            return False
        self.goto_stand()
        time.sleep(0.3)
        self.direction = direction
        self.running = True
        import threading
        self.thread = threading.Thread(target=self._gait_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if not self.running:
            return False
        self.running = False
        if hasattr(self, "thread") and self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        return True

    def is_running(self) -> bool:
        return self.running

    def single_step(self, direction: str = "forward"):
        """Execute one full 8-phase crawl cycle for testing."""
        print(f"\n{'=' * 60}")
        print(f"CRAWL SINGLE STEP - {direction}")
        print(f"{'=' * 60}")
        self.goto_stand()
        time.sleep(0.3)
        self.direction = direction

        cycle_time = self.cycle_time / self.speed
        steps = int(cycle_time / GAIT_UPDATE_RATE)
        last_phase = -1

        for i in range(steps):
            self._update_balance_corrections()
            cycle_phase = i / steps
            phase_idx = min(int(cycle_phase * 8), 7)
            phase_local = (cycle_phase * 8) - phase_idx

            if phase_idx != last_phase:
                ptype, leg = self.phase_sequence[phase_idx]
                desc = "SHIFT" if ptype == SHIFT_PHASE else f"SWING {leg}"
                print(f"  Phase {phase_idx}: {desc}")
                last_phase = phase_idx

            ptype, target_leg = self.phase_sequence[phase_idx]

            if ptype == SHIFT_PHASE:
                if self.use_ik:
                    angles = self._compute_body_shift_angles(target_leg, phase_local)
                    for leg_id in LEG_CHANNELS:
                        if leg_id in angles:
                            self._apply_leg_angles(leg_id, angles[leg_id])
                else:
                    for leg_id in LEG_CHANNELS:
                        self._apply_leg_angles(leg_id, self.stand_angles[leg_id])
            else:
                swing_angles = self._leg_angles_swing(phase_local, target_leg)
                if self.use_ik:
                    shift_angles = self._compute_body_shift_angles(target_leg, 1.0)
                else:
                    shift_angles = {}

                for leg_id in LEG_CHANNELS:
                    if leg_id == target_leg:
                        self._apply_leg_angles(leg_id, swing_angles)
                    elif leg_id in shift_angles:
                        self._apply_leg_angles(leg_id, shift_angles[leg_id])
                    else:
                        self._apply_leg_angles(leg_id, self.stand_angles[leg_id])

            time.sleep(GAIT_UPDATE_RATE)

        self._return_to_stand()
        print("Crawl single step complete")
