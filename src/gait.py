#!/usr/bin/env python3
"""
MicroSpot Walking Gait Module
Implements trot gait pattern for quadruped locomotion

Supports two modes:
- Angle-based (default): Direct angle offsets for hip/knee/ankle
- IK-based (optional): Foot position trajectories with inverse kinematics
"""
import time
import math
import threading
from collections import deque
from typing import Callable, Optional
from pathlib import Path

# Get directory where this script is located
_SCRIPT_DIR = Path(__file__).parent

# Balance control
try:
    from balance import BalanceController
    BALANCE_AVAILABLE = True
except ImportError:
    BALANCE_AVAILABLE = False
    print("Warning: BalanceController not available")

# Default calibration path
_DEFAULT_CALIBRATION = _SCRIPT_DIR / "calibration.json"

# Try to import IK interface, fall back to angle-based if unavailable
try:
    from ik_interface import IKInterface
    from trajectory import FootTrajectory, TrajectoryConfig
    IK_AVAILABLE = True
except ImportError:
    IK_AVAILABLE = False
    print("Warning: IK interface not available, using angle-based gait")

# Try to import CPG gait generator
try:
    from gait_generator import GaitGenerator, CPGConfig, BezierConfig
    GENERATOR_AVAILABLE = True
except ImportError:
    GENERATOR_AVAILABLE = False
    print("Warning: GaitGenerator not available")

# Try to import crawl gait
try:
    from crawl_gait import CrawlGaitController
    CRAWL_AVAILABLE = True
except ImportError:
    CRAWL_AVAILABLE = False
    print("Warning: CrawlGait not available")

# =============================================================================
# Gait Constants
# =============================================================================
# These constants define the default gait behavior. They can be overridden
# via the GaitController.set_params() method or via the API.

DEFAULT_STEP_HEIGHT = 36      # degrees - ankle lift during swing phase
DEFAULT_STRIDE_LENGTH = 15    # degrees - forward/back hip movement per step
DEFAULT_CYCLE_TIME = 1.0      # seconds per complete gait cycle
TROT_PHASE_OFFSET = 0.5       # diagonal legs offset by half cycle (trot gait)

DEFAULT_KNEE_BEND = 40        # degrees - default standing knee bend
DEFAULT_ANKLE_COMPENSATION = 1.3  # factor - ankle compensates knee bend (verhoogd voor meer voorwaartse enkel)

GAIT_UPDATE_RATE = 0.02       # seconds - 50Hz servo update rate
SINGLE_STEP_UPDATE_RATE = 0.03  # seconds - slightly slower for testing

# Knee/ankle movement ratios during swing/stance
KNEE_FORWARD_RATIO = 0.7      # how much knee contributes to forward motion
ANKLE_FORWARD_RATIO = 0.3     # how much ankle compensates forward motion
ANKLE_LIFT_RATIO = 0.8        # ankle compensation during leg lift
HIP_SWING_ANGLE = 0           # degrees hip swings forward/back during gait (0 = stable forward walk)
LATERAL_STEP_ANGLE = 15       # degrees hip moves for lateral stepping

# IK mode defaults (in meters)
DEFAULT_IK_STEP_HEIGHT = 0.03   # How high to lift foot
DEFAULT_IK_STRIDE_LENGTH = 0.04 # Forward/back distance

# =============================================================================

# Gait parameters
DEFAULT_GAIT_PARAMS = {
    "cycle_time": DEFAULT_CYCLE_TIME,  # Full cycle duration in seconds
    "step_height": None,               # Auto from knee_bend if None
    "step_length": None,               # Auto from knee_bend if None
    "speed": 1.0,                      # Speed multiplier
    "rear_lift_boost": 6,              # Extra lift degrees for rear legs
    # IK mode parameters (in meters)
    "ik_step_height": DEFAULT_IK_STEP_HEIGHT,
    "ik_stride_length": DEFAULT_IK_STRIDE_LENGTH,
}

DEBUG = True  # Print debug info


class GaitController:
    """
    Trot gait controller for quadruped robot

    Trot gait: Diagonal leg pairs move together
    - Phase 0: FL + RR swing (lift and forward), FR + RL stance (push back)
    - Phase 1: FR + RL swing, FL + RR stance

    IMPORTANT: All movements are relative to STAND position, not table/calibration position!
    - Table/calibration: logical 90 deg = raw ~135 deg for knees (tafelpoot stand)
    - Stand: legs bent (knee ~45 deg logical), body lowered, ready to walk

    Calibration handles left/right mirroring:
    - Left side (ch 1,2,7,8): direction=-1 (270 deg links = 0 deg rechts)
    - Right side (ch 4,5,10,11): direction=1

    Supports two modes:
    - Angle-based (use_ik=False): Direct angle offsets - default, proven to work
    - IK-based (use_ik=True): Foot trajectories with inverse kinematics
    """

    def __init__(self, set_servo_func: Callable[[int, float, bool], bool], use_ik: bool = False, generator_mode: bool = False, crawl_mode: bool = False):
        """
        Initialize gait controller

        Args:
            set_servo_func: Function to set servo angle - set_servo(channel, angle, apply_offset=True)
            use_ik: If True, use IK-based foot trajectories. Falls back to angle-based if IK unavailable.
            generator_mode: If True, use CPG-based GaitGenerator for phase/trajectory engine.
                            Requires IK. Falls back to angle-based if unavailable.
            crawl_mode: If True, use 8-phase crawl gait with body shifting.
                        Falls back to angle-based if unavailable.
        """
        self.set_servo = set_servo_func
        self.params = DEFAULT_GAIT_PARAMS.copy()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.direction = "forward"  # forward, backward, left, right

        # Crawl mode delegation
        self.crawl_mode = crawl_mode and CRAWL_AVAILABLE
        self.crawl_controller: Optional[CrawlGaitController] = None
        if crawl_mode:
            if CRAWL_AVAILABLE:
                try:
                    self.crawl_controller = CrawlGaitController(set_servo_func, use_ik=use_ik)
                    print("Crawl mode enabled")
                except Exception as e:
                    print(f"Crawl init failed: {e}, using trot gait")
                    self.crawl_mode = False
            else:
                print("Warning: CrawlGait not available, using trot gait")

        # Generator mode setting (CPG-based gait generator)
        self.generator_mode = generator_mode and GENERATOR_AVAILABLE and IK_AVAILABLE
        self.gait_generator = None
        if generator_mode and not GENERATOR_AVAILABLE:
            print("Warning: GaitGenerator requested but not available")
        if generator_mode and not IK_AVAILABLE:
            print("Warning: GaitGenerator requires IK, falling back to angle-based")

        # IK mode setting
        self.use_ik = (use_ik or self.generator_mode) and IK_AVAILABLE
        if use_ik and not IK_AVAILABLE:
            print("Warning: IK requested but not available, falling back to angle-based")

        # Initialize IK interface if available and requested
        self.ik_interface = None
        self.trajectory = None
        if self.use_ik:
            try:
                self.ik_interface = IKInterface(
                    calibration_path=str(_DEFAULT_CALIBRATION),
                    body_height=0.10  # 10cm standing height
                )
                self.trajectory = FootTrajectory(TrajectoryConfig(
                    step_height=self.params["ik_step_height"],
                    stride_length=self.params["ik_stride_length"]
                ))
                if self.generator_mode:
                    self.gait_generator = GaitGenerator(
                        cpg_config=CPGConfig(base_frequency=1.0 / DEFAULT_CYCLE_TIME),
                        bezier_config=BezierConfig(
                            stride_length=self.params["ik_stride_length"],
                            stride_height=self.params["ik_step_height"],
                        )
                    )
                    print("Generator mode enabled (CPG + Bezier)")
                else:
                    print("IK mode enabled")
            except Exception as e:
                print(f"IK init failed: {e}, falling back to angle-based")
                self.use_ik = False
                self.generator_mode = False

        # Interpolation: track current angles for smooth movement
        self._current_angles = {}  # {channel: current_angle}
        self._interp_speed = 1.0   # 1.0 = direct to target (0.5 caused constant servo hunting and high current draw!)

        # Cached balance corrections (read IMU once per gait cycle, not per leg)
        self._balance_corrections = {}

        # Servo channel mapping
        # FL: hip=0, knee=1, ankle=2
        # FR: hip=3, knee=4, ankle=5
        # RL: hip=6, knee=7, ankle=8
        # RR: hip=9, knee=10, ankle=11
        self.legs = {
            "FL": {"hip": 0, "knee": 1, "ankle": 2, "side": "left"},
            "FR": {"hip": 3, "knee": 4, "ankle": 5, "side": "right"},
            "RL": {"hip": 6, "knee": 7, "ankle": 8, "side": "left"},
            "RR": {"hip": 9, "knee": 10, "ankle": 11, "side": "right"},
        }

        # Diagonal pairs for trot
        self.pair_a = ["FL", "RR"]  # Move together
        self.pair_b = ["FR", "RL"]  # Move together

        # Turn rate for steering (-1.0 = full left, 1.0 = full right)
        self.turn_rate = 0.0
        # Lateral rate for side stepping (-1.0 = full left, 1.0 = full right)
        self.lateral_rate = 0.0

        # Heartbeat watchdog: auto-stop if no command received for WATCHDOG_TIMEOUT seconds
        self.WATCHDOG_TIMEOUT = 3.0
        self.last_command_time: float = time.monotonic()

        # Shadow comparison: compute IK angles alongside angle-mode (no servo writes)
        self.shadow_compare: bool = False
        self._shadow_tick: int = 0
        self._shadow_buffer = {
            leg: {joint: deque(maxlen=50) for joint in ["hip", "knee", "ankle"]}
            for leg in ["FL", "FR", "RL", "RR"]
        }
        self._shadow_divergence: dict = {}  # latest per-leg, per-joint divergence (degrees)

        # Balance controller (IMU)
        self.balance = None
        self.use_balance = False
        if BALANCE_AVAILABLE:
            try:
                self.balance = BalanceController()
                print("IMU balance controller initialized")
            except Exception as e:
                print(f"IMU init failed: {e}")

        # Stand positie: lichte knie buiging voor stabiliteit
        # Alle hoeken zijn LOGISCH (90 = calibrated neutral = tafelpoot)
        self._default_knee_bend = DEFAULT_KNEE_BEND
        self._default_ankle_comp = int(DEFAULT_KNEE_BEND * DEFAULT_ANKLE_COMPENSATION)

        # Rear leg compensation: counter calibration asymmetry
        # RL neutral=86° (-4° from 90°), RR neutral=95° (+5° from 90°)
        # Compensation inverts the offset to achieve effective 90° neutral
        self._rear_knee_comp = {"RL": -4, "RR": +5}
        self._rear_ankle_comp = {"RL": 0, "RR": 0}

        self.stand_angles = {
            "FL": {"hip": 90, "knee": 90 - self._default_knee_bend, "ankle": 90 + self._default_ankle_comp},
            "FR": {"hip": 90, "knee": 90 - self._default_knee_bend, "ankle": 90 + self._default_ankle_comp},
            "RL": {"hip": 90, "knee": 90 - self._default_knee_bend, "ankle": 90 + self._default_ankle_comp + self._rear_ankle_comp["RL"]},
            "RR": {"hip": 90, "knee": 90 - self._default_knee_bend, "ankle": 90 + self._default_ankle_comp + self._rear_ankle_comp["RR"]},
        }

        # Auto-calculate step params based on knee_bend (for angle-based mode)
        if self.params["step_height"] is None:
            self.params["step_height"] = int(self._default_knee_bend * 0.9)
        if self.params["step_length"] is None:
            self.params["step_length"] = int(self._default_knee_bend * 0.5)
        print(f"  Auto: height={self.params['step_height']} deg, length={self.params['step_length']} deg")
        print(f"  Mode: {'IK' if self.use_ik else 'Angle-based'}")

    def set_gait_type(self, gait: str) -> bool:
        """
        Set the gait type when in generator mode.

        Args:
            gait: One of "walk", "trot", "pace", "bound"

        Returns:
            True if gait type was set successfully
        """
        if not self.generator_mode or self.gait_generator is None:
            print("Gait type switching only available in generator mode")
            return False
        try:
            self.gait_generator.set_gait_type(gait)
            print(f"Gait type set to: {gait}")
            return True
        except Exception as e:
            print(f"Failed to set gait type: {e}")
            return False

    def set_mode(self, use_ik: bool, generator_mode: bool = False, crawl_mode: bool = False) -> bool:
        """
        Switch between IK, generator, and angle-based gait modes.

        Args:
            use_ik: True for IK mode, False for angle-based
            generator_mode: True for CPG-based gait generator (requires IK)
            crawl_mode: True for 8-phase crawl gait with body shifting

        Returns:
            True if mode was set successfully
        """
        # Handle crawl mode
        if crawl_mode:
            if not CRAWL_AVAILABLE:
                print("CrawlGait not available")
                return False
            try:
                if self.crawl_controller is None:
                    self.crawl_controller = CrawlGaitController(self.set_servo, use_ik=use_ik)
                self.crawl_mode = True
                self.generator_mode = False
                self.use_ik = False
                print("Switched to crawl mode")
                return True
            except Exception as e:
                print(f"Failed to switch to crawl mode: {e}")
                return False

        # If disabling crawl mode, ensure crawl thread is stopped before switching
        if self.crawl_mode and not crawl_mode:
            if self.crawl_controller and self.crawl_controller.is_running():
                self.crawl_controller.stop()
            self.crawl_mode = False
            print("Crawl mode disabled")

        if generator_mode and not GENERATOR_AVAILABLE:
            print("GaitGenerator not available, staying in current mode")
            return False
        if (use_ik or generator_mode) and not IK_AVAILABLE:
            print("IK not available, staying in angle-based mode")
            return False

        if generator_mode:
            try:
                if self.ik_interface is None:
                    self.ik_interface = IKInterface(
                        calibration_path=str(_DEFAULT_CALIBRATION),
                        body_height=0.10
                    )
                if self.gait_generator is None:
                    self.gait_generator = GaitGenerator(
                        cpg_config=CPGConfig(base_frequency=1.0 / DEFAULT_CYCLE_TIME),
                        bezier_config=BezierConfig(
                            stride_length=self.params["ik_stride_length"],
                            stride_height=self.params["ik_step_height"],
                        )
                    )
                self.generator_mode = True
                self.use_ik = True
                print("Switched to generator mode")
                return True
            except Exception as e:
                print(f"Failed to switch to generator mode: {e}")
                return False

        if use_ik and not self.use_ik:
            # Switching to IK mode - initialize if needed
            try:
                if self.ik_interface is None:
                    self.ik_interface = IKInterface(
                        calibration_path=str(_DEFAULT_CALIBRATION),
                        body_height=0.10
                    )
                if self.trajectory is None:
                    self.trajectory = FootTrajectory(TrajectoryConfig(
                        step_height=self.params["ik_step_height"],
                        stride_length=self.params["ik_stride_length"]
                    ))
                self.use_ik = True
                self.generator_mode = False
                print("Switched to IK mode")
                return True
            except Exception as e:
                print(f"Failed to switch to IK mode: {e}")
                return False
        elif not use_ik:
            self.use_ik = False
            self.generator_mode = False
            print("Switched to angle-based mode")
            return True

        return True

    def set_crawl_params(self, **kwargs) -> bool:
        """Update crawl gait parameters (delegates to crawl controller)."""
        if self.crawl_controller:
            self.crawl_controller.set_params(**kwargs)
            return True
        return False

    def set_params(self, **kwargs):
        """Update gait parameters"""
        # Delegate crawl-specific params if in crawl mode
        if self.crawl_mode and self.crawl_controller:
            crawl_params = {k: v for k, v in kwargs.items()
                            if k in ("cycle_time", "speed", "step_height", "step_length", "knee_bend")}
            if crawl_params:
                self.crawl_controller.set_params(**crawl_params)
        for key, value in kwargs.items():
            if key in self.params:
                self.params[key] = value
                print(f"  Gait param {key} = {value}")

        # Update trajectory config if IK params changed
        if self.trajectory and ("ik_step_height" in kwargs or "ik_stride_length" in kwargs):
            self.trajectory.config.step_height = self.params["ik_step_height"]
            self.trajectory.config.stride_length = self.params["ik_stride_length"]

        # Update gait generator if in generator mode
        if self.generator_mode and self.gait_generator:
            if "ik_step_height" in kwargs:
                self.gait_generator.set_stride_params(height=self.params["ik_step_height"])
            if "ik_stride_length" in kwargs:
                self.gait_generator.set_stride_params(length=self.params["ik_stride_length"])
            if "speed" in kwargs:
                self.gait_generator.set_speed(self.params["speed"])
            if "cycle_time" in kwargs:
                self.gait_generator.cpg.config.base_frequency = 1.0 / self.params["cycle_time"]
                self.gait_generator.set_speed(self.params["speed"])

    def heartbeat(self):
        """Refresh the watchdog timer. Call this from any active controller or UI to signal liveness."""
        self.last_command_time = time.monotonic()

    def set_turn_rate(self, rate: float):
        """
        Set the turn rate for steering while walking.

        Args:
            rate: Turn rate from -1.0 (full left) to 1.0 (full right)
                  0.0 = straight ahead
                  Negative = turn left (left legs take shorter steps)
                  Positive = turn right (right legs take shorter steps)
        """
        self.turn_rate = max(-1.0, min(1.0, rate))
        self.last_command_time = time.monotonic()
        if DEBUG and abs(rate) > 0.1:
            print(f"  Turn rate: {self.turn_rate:.2f}")

    def set_lateral_rate(self, rate: float):
        """
        Set the lateral rate for side stepping.

        Args:
            rate: Lateral rate from -1.0 (full left) to 1.0 (full right)
                  0.0 = no lateral movement

                  Negative = step left
                  Positive = step right
        """
        self.lateral_rate = max(-1.0, min(1.0, rate))
        self.last_command_time = time.monotonic()
        if DEBUG and abs(rate) > 0.1:
            print(f"  Lateral rate: {self.lateral_rate:.2f}")

        # Sync to gait generator if in generator mode
        if self.generator_mode and self.gait_generator:
            self.gait_generator.set_lateral_fraction(self.lateral_rate)

    def set_stand_height(self, knee_bend: int):
        """
        Set stand height by adjusting knee bend.

        Args:
            knee_bend: Degrees of knee bend from vertical (0-60)
                       0 = tafelpoot (legs straight down)
                       30 = comfortable standing (default)
                       60 = very low crouch

        Returns:
            dict: Updated stand_angles

        Note:
            All angles are LOGICAL angles where 90 deg = calibrated neutral.
            The calibration system handles left/right mirroring via direction.
            Ankle compensates ~1.0x knee bend for foot under knee.
        """
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.set_stand_height(knee_bend)
        # Clamp to safe range (0=straight, 80=very low like rest pose)
        knee_bend = max(0, min(80, knee_bend))

        # Ankle compensation factor
        ankle_comp = int(knee_bend * DEFAULT_ANKLE_COMPENSATION)

        # Calculate logical angles
        knee_angle = 90 - knee_bend
        ankle_angle = 90 + ankle_comp

        # Update all legs (rear ankle compensation: + om naar voren te brengen)
        self.stand_angles = {
            "FL": {"hip": 90, "knee": knee_angle, "ankle": ankle_angle},
            "FR": {"hip": 90, "knee": knee_angle, "ankle": ankle_angle},
            "RL": {"hip": 90, "knee": knee_angle, "ankle": ankle_angle + self._rear_ankle_comp["RL"]},
            "RR": {"hip": 90, "knee": knee_angle, "ankle": ankle_angle + self._rear_ankle_comp["RR"]},
        }

        print(f"Stand height set: knee_bend={knee_bend} deg")
        print(f"  Logical angles: knee={knee_angle} deg, ankle={ankle_angle} deg")
        print(f"  (90 deg = tafelpoot neutral)")

        return self.stand_angles

    def get_stand_angles(self):
        """Get current stand angles"""
        return self.stand_angles

    def preview_stand(self):
        """Move to current stand position WITHOUT balance corrections"""
        print("Previewing stand position...")
        for leg_id, angles in self.stand_angles.items():
            leg = self.legs[leg_id]
            # Direct servo control - NO balance!
            self.set_servo(leg["hip"], int(angles["hip"]), True)
            self.set_servo(leg["knee"], int(angles["knee"]), True)
            self.set_servo(leg["ankle"], int(angles["ankle"]), True)

    def enable_balance(self, enable=True, calibrate=True):
        """Enable/disable IMU balance correction"""
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.enable_balance(enable, calibrate)
        if not BALANCE_AVAILABLE or not self.balance:
            print("Balance not available")
            return False
        self.use_balance = enable
        if enable and calibrate:
            print("Calibrating IMU... hold still")
            self.balance.calibrate(30)
        print(f"Balance: {'ON' if enable else 'OFF'}")
        return True

    def set_balance_kp(self, kp):
        """Set balance Kp gain"""
        if self.balance:
            self.balance.set_kp(kp)
            return True
        return False

    def get_params(self):
        """Get current gait parameters"""
        result = self.params.copy()
        result["use_ik"] = self.use_ik
        result["ik_available"] = IK_AVAILABLE
        result["crawl_mode"] = self.crawl_mode
        result["generator_mode"] = self.generator_mode
        result["shadow_compare"] = self.shadow_compare
        return result

    def get_shadow_divergence(self) -> dict:
        """Return latest per-leg, per-joint angle divergence (angle-mode vs IK)."""
        return self._shadow_divergence.copy()

    def _smooth_phase(self, t: float) -> float:
        """
        Convert linear time to smooth phase using cosine interpolation
        t: 0 to 1 linear
        returns: 0 to 1 smooth (slow at start/end, fast in middle)
        """
        return (1 - math.cos(t * math.pi)) / 2

    # ==================== ANGLE-BASED METHODS ====================

    def _leg_angles_swing(self, phase: float, leg_id: str) -> dict:
        """
        Calculate leg angles during swing phase (leg in air, moving forward)
        ANGLE-BASED MODE

        All angles are LOGICAL (90 deg = calibrated neutral).
        The calibration system handles direction inversion for left/right.

        Args:
            phase: 0.0 = start (leg back), 0.5 = mid (lifted), 1.0 = end (leg forward)
            leg_id: "FL", "FR", "RL", or "RR"

        Returns:
            dict with hip, knee, ankle logical angles
        """
        step_h = self.params["step_height"]
        step_l = self.params["step_length"]

        # Get this leg's stand position as base
        stand = self.stand_angles[leg_id]

        # Direction multiplier: forward=1, backward=-1
        dir_mult = -1.0 if self.direction == "backward" else 1.0

        # Apply turn differential to step length
        if leg_id in ['FL', 'RL']:  # Left legs
            stride_mult = 1.0 - self.turn_rate * 0.5
        else:  # Right legs (FR, RR)
            stride_mult = 1.0 + self.turn_rate * 0.5

        # Leg lift: sine curve peaks at phase 0.5
        lift_amount = step_h * math.sin(phase * math.pi)

        # No special rear leg compensation - let calibration handle differences
        rear_lift_boost = 0

        # Forward position: swing starts at back (-), ends at front (+)
        # dir_mult reverses this for backward walking
        fwd = step_l * stride_mult * dir_mult * (phase * 2 - 1)

        # Knee: lift + forward reach (with rear boost)
        knee_offset = -(lift_amount + rear_lift_boost) + fwd * KNEE_FORWARD_RATIO

        # Ankle: compensate for lift and forward motion
        ankle_offset = lift_amount * ANKLE_LIFT_RATIO + fwd * ANKLE_FORWARD_RATIO

        # Geen extra swing compensatie - stand_angles hebben al de rear ankle comp

        # Hip swings forward during swing phase
        hip_offset = HIP_SWING_ANGLE * (phase * 2 - 1)

        # Lateral movement: hip moves sideways during swing
        # Left legs: positive lateral = hip increases (foot moves right)
        # Right legs: positive lateral = hip decreases (foot moves right)
        if self.lateral_rate != 0:
            lateral_amount = LATERAL_STEP_ANGLE * self.lateral_rate * math.sin(phase * math.pi)
            if leg_id in ['FL', 'RL']:  # Left legs
                hip_offset += lateral_amount
            else:  # Right legs
                hip_offset -= lateral_amount

        return {
            "hip": stand["hip"] + hip_offset,
            "knee": stand["knee"] + knee_offset,
            "ankle": stand["ankle"] + ankle_offset
        }

    def _leg_angles_stance(self, phase: float, leg_id: str) -> dict:
        """
        Calculate leg angles during stance phase (leg on ground, pushing back)
        ANGLE-BASED MODE

        All angles are LOGICAL (90 deg = calibrated neutral).

        Args:
            phase: 0.0 = start (leg forward), 1.0 = end (leg back)
            leg_id: "FL", "FR", "RL", or "RR"

        Returns:
            dict with hip, knee, ankle logical angles
        """
        step_l = self.params["step_length"]

        # Get this leg's stand position as base
        stand = self.stand_angles[leg_id]

        # Direction multiplier: forward=1, backward=-1
        dir_mult = -1.0 if self.direction == "backward" else 1.0

        # Apply turn differential
        if leg_id in ['FL', 'RL']:  # Left legs
            stride_mult = 1.0 - self.turn_rate * 0.5
        else:  # Right legs (FR, RR)
            stride_mult = 1.0 + self.turn_rate * 0.5

        # Forward position: stance starts at front (+), ends at back (-)
        # dir_mult reverses this for backward walking
        fwd = step_l * stride_mult * dir_mult * (1 - phase * 2)

        # Knee and ankle move to push body forward
        knee_offset = fwd * KNEE_FORWARD_RATIO
        ankle_offset = fwd * ANKLE_FORWARD_RATIO

        # Hip swings backward during stance phase
        hip_offset = HIP_SWING_ANGLE * (1 - phase * 2)

        # Lateral movement: hip pushes back during stance
        # Opposite direction from swing to push body sideways
        if self.lateral_rate != 0:
            lateral_amount = LATERAL_STEP_ANGLE * self.lateral_rate * (1 - phase)
            if leg_id in ['FL', 'RL']:  # Left legs
                hip_offset -= lateral_amount
            else:  # Right legs
                hip_offset += lateral_amount

        return {
            "hip": stand["hip"] + hip_offset,
            "knee": stand["knee"] + knee_offset,
            "ankle": stand["ankle"] + ankle_offset
        }

    # ==================== IK-BASED METHODS ====================

    def _leg_angles_swing_ik(self, phase: float, leg_id: str) -> dict:
        """
        Calculate leg angles during swing phase using IK.
        IK-BASED MODE

        Args:
            phase: 0.0 to 1.0 through swing
            leg_id: "FL", "FR", "RL", or "RR"

        Returns:
            dict with hip, knee, ankle logical angles
        """
        if not self.ik_interface or not self.trajectory:
            return self._leg_angles_swing(phase, leg_id)

        try:
            # Get neutral foot position from IK interface
            neutral_feet = self.ik_interface.get_neutral_foot_positions()
            neutral = neutral_feet[leg_id]

            # Calculate foot position during swing
            foot_pos = self.trajectory.swing_position(
                phase,
                neutral[0],  # x
                neutral[1],  # y (height from body)
                neutral[2]   # z (lateral)
            )

            # Get all foot positions (other legs stay at neutral)
            all_feet = neutral_feet.copy()
            all_feet[leg_id] = list(foot_pos)

            # Convert to angles using IK
            angles = self.ik_interface.feet_to_angles(all_feet)
            leg_angles = angles[leg_id]

            return {
                "hip": leg_angles[0],
                "knee": leg_angles[1],
                "ankle": leg_angles[2]
            }
        except Exception as e:
            if DEBUG:
                print(f"IK swing error for {leg_id}: {e}")
            return self._leg_angles_swing(phase, leg_id)

    def _leg_angles_stance_ik(self, phase: float, leg_id: str) -> dict:
        """
        Calculate leg angles during stance phase using IK.
        IK-BASED MODE

        Args:
            phase: 0.0 to 1.0 through stance
            leg_id: "FL", "FR", "RL", or "RR"

        Returns:
            dict with hip, knee, ankle logical angles
        """
        if not self.ik_interface or not self.trajectory:
            return self._leg_angles_stance(phase, leg_id)

        try:
            # Get neutral foot position from IK interface
            neutral_feet = self.ik_interface.get_neutral_foot_positions()
            neutral = neutral_feet[leg_id]

            # Calculate foot position during stance
            foot_pos = self.trajectory.stance_position(
                phase,
                neutral[0],  # x
                neutral[1],  # y (height from body)
                neutral[2]   # z (lateral)
            )

            # Get all foot positions (other legs stay at neutral)
            all_feet = neutral_feet.copy()
            all_feet[leg_id] = list(foot_pos)

            # Convert to angles using IK
            angles = self.ik_interface.feet_to_angles(all_feet)
            leg_angles = angles[leg_id]

            return {
                "hip": leg_angles[0],
                "knee": leg_angles[1],
                "ankle": leg_angles[2]
            }
        except Exception as e:
            if DEBUG:
                print(f"IK stance error for {leg_id}: {e}")
            return self._leg_angles_stance(phase, leg_id)

    # ==================== COMMON METHODS ====================

    def _get_swing_angles(self, phase: float, leg_id: str) -> dict:
        """Get swing angles using current mode (IK or angle-based)"""
        if self.use_ik:
            return self._leg_angles_swing_ik(phase, leg_id)
        else:
            return self._leg_angles_swing(phase, leg_id)

    def _get_stance_angles(self, phase: float, leg_id: str) -> dict:
        """Get stance angles using current mode (IK or angle-based)"""
        if self.use_ik:
            return self._leg_angles_stance_ik(phase, leg_id)
        else:
            return self._leg_angles_stance(phase, leg_id)

    def _interpolate(self, ch: int, target: float) -> float:
        if ch not in self._current_angles:
            self._current_angles[ch] = target
            return target
        cur = self._current_angles[ch]
        new = cur + (target - cur) * self._interp_speed
        self._current_angles[ch] = new
        return new

    def _update_balance_corrections(self):
        """Read IMU once per gait cycle and cache corrections for all legs.
        Uses cached correction to avoid I2C bus contention with background reader."""
        if self.use_balance and self.balance:
            try:
                self._balance_corrections = self.balance.get_cached_correction()
            except Exception:
                pass
        else:
            self._balance_corrections = {}

    def _apply_leg_angles(self, leg_id: str, angles: dict):
        """Apply calculated angles to a leg's servos (with balance)"""
        leg = self.legs[leg_id]
        bal = self._balance_corrections.get(leg_id, 0)
        hip = int(self._interpolate(leg["hip"], angles["hip"]))
        knee = int(self._interpolate(leg["knee"], angles["knee"] + bal))
        ankle = int(self._interpolate(leg["ankle"], angles["ankle"] - bal * 0.5))
        self.set_servo(leg["hip"], hip, True)
        self.set_servo(leg["knee"], knee, True)
        self.set_servo(leg["ankle"], ankle, True)

    def _update_generator_angles(self) -> dict:
        """
        Update leg angles using the CPG gait generator.
        Returns dict of {leg_id: {hip, knee, ankle}} angles.
        """
        if not self.generator_mode or not self.gait_generator or not self.ik_interface:
            return {}

        dt = GAIT_UPDATE_RATE
        feet_rel = self.gait_generator.update(dt)
        neutral = self.ik_interface.get_neutral_foot_positions()

        # Convert relative to absolute foot positions
        abs_feet = {}
        for leg_id, rel in feet_rel.items():
            n = neutral[leg_id]
            abs_feet[leg_id] = [n[0] + rel[0], n[1] + rel[1], n[2] + rel[2]]

        # Compute angles via IK
        angles = self.ik_interface.feet_to_angles(abs_feet)

        # Format as {leg_id: {hip, knee, ankle}}
        result = {}
        for leg_id in self.legs:
            result[leg_id] = {
                "hip": angles[leg_id][0],
                "knee": angles[leg_id][1],
                "ankle": angles[leg_id][2],
            }
        return result

    def _compute_shadow_tick(self, cycle_phase: float):
        """Compute IK angles for current phase without moving servos (shadow compare).
        Only called every 5th tick in angle-mode when shadow_compare is enabled."""
        if not (IK_AVAILABLE and self.ik_interface):
            return
        try:
            divergence = {}
            for leg_id in self.legs:
                in_pair_a = leg_id in self.pair_a
                if cycle_phase < 0.5:
                    if in_pair_a:
                        p = self._smooth_phase(cycle_phase * 2)
                        ang = self._leg_angles_swing(p, leg_id)
                        ik = self._leg_angles_swing_ik(p, leg_id)
                    else:
                        p = cycle_phase * 2
                        ang = self._leg_angles_stance(p, leg_id)
                        ik = self._leg_angles_stance_ik(p, leg_id)
                else:
                    if in_pair_a:
                        p = (cycle_phase - 0.5) * 2
                        ang = self._leg_angles_stance(p, leg_id)
                        ik = self._leg_angles_stance_ik(p, leg_id)
                    else:
                        p = self._smooth_phase((cycle_phase - 0.5) * 2)
                        ang = self._leg_angles_swing(p, leg_id)
                        ik = self._leg_angles_swing_ik(p, leg_id)

                divergence[leg_id] = {
                    joint: round(abs(ik[joint] - ang[joint]), 1)
                    for joint in ["hip", "knee", "ankle"]
                }
                for joint in ["hip", "knee", "ankle"]:
                    self._shadow_buffer[leg_id][joint].append(divergence[leg_id][joint])

            self._shadow_divergence = divergence
        except Exception as e:
            if DEBUG:
                print(f"Shadow compare error: {e}")

    def _gait_loop(self):
        """Main gait loop - runs in separate thread"""
        print(f"\n{'=' * 60}")
        print(f"GAIT STARTED - Direction: {self.direction}")
        if self.generator_mode:
            print(f"Mode: Generator (CPG + Bezier)")
            print(f"Gait type: {self.gait_generator.get_gait_type()}")
        else:
            print(f"Mode: {'IK' if self.use_ik else 'Angle-based'}")
        print(f"Params: cycle={self.params['cycle_time']}s, height={self.params['step_height']} deg, length={self.params['step_length']} deg")
        print(f"Pair A (swing first): {self.pair_a}")
        print(f"Pair B (stance first): {self.pair_b}")
        print(f"{'=' * 60}\n")

        cycle_time = self.params["cycle_time"] / self.params["speed"]
        step_time = GAIT_UPDATE_RATE

        start_time = time.time()
        last_phase_half = -1

        while self.running:
            # Watchdog: auto-stop if no command received within timeout
            if time.monotonic() - self.last_command_time > self.WATCHDOG_TIMEOUT:
                print(f"GAIT WATCHDOG: no command for {self.WATCHDOG_TIMEOUT}s, stopping")
                self.running = False
                break

            # Read IMU once per iteration (not per leg)
            self._update_balance_corrections()

            if self.generator_mode:
                angles = self._update_generator_angles()
                for leg_id in self.legs:
                    if leg_id in angles:
                        self._apply_leg_angles(leg_id, angles[leg_id])
                if DEBUG:
                    current_half = 0 if self.gait_generator.get_leg_phase("FL") < 0.5 else 1
                    if current_half != last_phase_half:
                        if current_half == 0:
                            print(f">> FL swing, FR stance")
                        else:
                            print(f">> FL stance, FR swing")
                        last_phase_half = current_half
            else:
                elapsed = time.time() - start_time
                cycle_phase = (elapsed % cycle_time) / cycle_time
                current_half = 0 if cycle_phase < 0.5 else 1

                if DEBUG and current_half != last_phase_half:
                    if current_half == 0:
                        print(f">> FL+RR lift, FR+RL ground")
                    else:
                        print(f">> FR+RL lift, FL+RR ground")
                    last_phase_half = current_half

                # Shadow compare: every 5th tick compute IK angles without applying them
                if self.shadow_compare and not self.use_ik:
                    self._shadow_tick += 1
                    if self._shadow_tick % 5 == 0:
                        self._compute_shadow_tick(cycle_phase)

                if cycle_phase < 0.5:
                    swing_phase = self._smooth_phase(cycle_phase * 2)
                    for leg_id in self.pair_a:
                        angles = self._get_swing_angles(swing_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

                    stance_phase = cycle_phase * 2
                    for leg_id in self.pair_b:
                        angles = self._get_stance_angles(stance_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)
                else:
                    stance_phase = (cycle_phase - 0.5) * 2
                    for leg_id in self.pair_a:
                        angles = self._get_stance_angles(stance_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

                    swing_phase = self._smooth_phase((cycle_phase - 0.5) * 2)
                    for leg_id in self.pair_b:
                        angles = self._get_swing_angles(swing_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

            time.sleep(step_time)

        print(f"\n{'=' * 60}")
        print(f"GAIT STOPPED")
        print(f"{'=' * 60}\n")

        self._return_to_stand()

    def _return_to_stand(self):
        """Smoothly return all legs to STAND position"""
        print("Returning to stand position...")
        self._update_balance_corrections()
        for leg_id in self.legs:
            self._apply_leg_angles(leg_id, self.stand_angles[leg_id])

    def goto_stand(self):
        """Move robot to STAND position (ready to walk)"""
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.goto_stand()
        print(f"\n{'=' * 60}")
        print("GOING TO STAND POSITION")
        print(f"{'=' * 60}")
        self._update_balance_corrections()
        for leg_id, angles in self.stand_angles.items():
            print(f"  {leg_id}: hip={angles['hip']}, knee={angles['knee']}, ankle={angles['ankle']}")
            self._apply_leg_angles(leg_id, angles)
        print(f"{'=' * 60}\n")

    def _compute_ik_stand_angles(self) -> dict:
        """Compute stand angles for neutral foot positions via IK.

        Returns {leg_id: {hip, knee, ankle}} on success, {} on failure.
        Uses IKInterface.feet_to_angles which solves all 4 legs simultaneously.
        """
        if not self.ik_interface:
            return {}
        try:
            neutral_feet = self.ik_interface.get_neutral_foot_positions()
            raw = self.ik_interface.feet_to_angles(neutral_feet)
            return {
                leg: {"hip": round(a[0], 1), "knee": round(a[1], 1), "ankle": round(a[2], 1)}
                for leg, a in raw.items()
            }
        except Exception as e:
            print(f"IK stand computation failed: {e}")
            return {}

    def validate_ik_stand(self, tolerance_deg: float = 20.0) -> dict:
        """Compare IK stand angles with angle-based stand angles.

        Returns a report dict:
          {"ok": bool, "max_deviation": float, "tolerance": float,
           "legs": {leg: {ik, angle, deviation, max_dev}},
           "ik_angles": {...}, "error": str (only on failure)}
        """
        ik_angles = self._compute_ik_stand_angles()
        if not ik_angles:
            return {"ok": False, "error": "IK stand computation failed", "ik_available": IK_AVAILABLE}

        report: dict = {"ok": True, "legs": {}, "max_deviation": 0.0, "tolerance": tolerance_deg,
                        "ik_available": IK_AVAILABLE, "ik_angles": ik_angles}
        for leg_id in self.legs:
            ik = ik_angles.get(leg_id)
            if not ik:
                continue
            ang = self.stand_angles[leg_id]
            dev = {j: round(abs(ik[j] - ang[j]), 1) for j in ["hip", "knee", "ankle"]}
            max_dev = max(dev.values())
            report["legs"][leg_id] = {"ik": ik, "angle_based": ang, "deviation": dev, "max_dev": max_dev}
            report["max_deviation"] = max(report["max_deviation"], max_dev)
            if max_dev > tolerance_deg:
                report["ok"] = False

        return report

    def goto_stand_ik(self, tolerance_deg: float = 20.0) -> bool:
        """Move to stand position using IK-computed angles.

        Falls back to angle-based stand when IK is unavailable or deviation is too large.
        Returns True if IK stand was applied, False if fell back to angle-based.
        """
        report = self.validate_ik_stand(tolerance_deg)
        if not report.get("ok"):
            max_dev = report.get("max_deviation", 0.0)
            err = report.get("error", "")
            print(f"IK stand validation failed "
                  f"({'max deviation ' + str(max_dev) + '° > ' + str(tolerance_deg) + '°' if not err else err})"
                  f" — falling back to angle-based stand")
            self.goto_stand()
            return False

        ik_angles = report["ik_angles"]
        print(f"\n{'=' * 60}")
        print(f"GOING TO IK STAND  (max deviation {report['max_deviation']:.1f}°)")
        print(f"{'=' * 60}")
        self._update_balance_corrections()
        for leg_id, angles in ik_angles.items():
            print(f"  {leg_id}: hip={angles['hip']:.0f}, knee={angles['knee']:.0f}, ankle={angles['ankle']:.0f}")
            self._apply_leg_angles(leg_id, angles)
        print(f"{'=' * 60}\n")
        return True

    def start(self, direction: str = "forward"):
        """Start the gait - first goes to STAND position, then starts walking"""
        if self.running:
            print("Gait already running")
            return False

        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.start(direction)

        # IK mode uses IK-computed stand angles; generator mode keeps angle stand (uses CPG)
        if self.use_ik and not self.generator_mode:
            self.goto_stand_ik()
        else:
            self.goto_stand()
        time.sleep(0.3)

        self.direction = direction
        self.last_command_time = time.monotonic()  # Reset watchdog on start
        if self.generator_mode and self.gait_generator:
            self.gait_generator.set_direction(direction)
            self.gait_generator.reset_phases()
        self.running = True
        self.thread = threading.Thread(target=self._gait_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop the gait"""
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.stop()
        if not self.running:
            print("Gait not running")
            return False

        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        return True

    def is_running(self) -> bool:
        """Check if gait is running"""
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.is_running()
        return self.running

    def single_step(self, direction: str = "forward"):
        """Execute a single step cycle (for testing) - starts from STAND position"""
        if self.crawl_mode and self.crawl_controller:
            return self.crawl_controller.single_step(direction)
        print(f"\n{'=' * 60}")
        print(f"SINGLE STEP - Direction: {direction}")
        if self.generator_mode:
            print(f"Mode: Generator (CPG + Bezier)")
        else:
            print(f"Mode: {'IK' if self.use_ik else 'Angle-based'}")
        print(f"Params: height={self.params['step_height']} deg, length={self.params['step_length']} deg")
        print(f"{'=' * 60}")

        self.goto_stand()
        time.sleep(0.3)

        self.direction = direction
        if self.generator_mode and self.gait_generator:
            self.gait_generator.set_direction(direction)
            self.gait_generator.reset_phases()

        cycle_time = self.params["cycle_time"] / self.params["speed"]
        step_time = SINGLE_STEP_UPDATE_RATE
        steps = int(cycle_time / step_time)

        last_half = -1

        for i in range(steps):
            # Read IMU once per iteration
            self._update_balance_corrections()

            if self.generator_mode:
                angles = self._update_generator_angles()
                for leg_id in self.legs:
                    if leg_id in angles:
                        self._apply_leg_angles(leg_id, angles[leg_id])
                current_half = 0 if self.gait_generator.get_leg_phase("FL") < 0.5 else 1
                if current_half != last_half:
                    if current_half == 0:
                        print(f"\n>> Phase 1: FL swing, FR stance")
                    else:
                        print(f"\n>> Phase 2: FL stance, FR swing")
                    last_half = current_half
            else:
                cycle_phase = i / steps
                current_half = 0 if cycle_phase < 0.5 else 1

                if current_half != last_half:
                    if current_half == 0:
                        print(f"\n>> Phase 1: FL+RR LIFT, FR+RL on ground")
                    else:
                        print(f"\n>> Phase 2: FR+RL LIFT, FL+RR on ground")
                    last_half = current_half

                if cycle_phase < 0.5:
                    swing_phase = self._smooth_phase(cycle_phase * 2)
                    for leg_id in self.pair_a:
                        angles = self._get_swing_angles(swing_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

                    stance_phase = cycle_phase * 2
                    for leg_id in self.pair_b:
                        angles = self._get_stance_angles(stance_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)
                else:
                    stance_phase = (cycle_phase - 0.5) * 2
                    for leg_id in self.pair_a:
                        angles = self._get_stance_angles(stance_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

                    swing_phase = self._smooth_phase((cycle_phase - 0.5) * 2)
                    for leg_id in self.pair_b:
                        angles = self._get_swing_angles(swing_phase, leg_id)
                        self._apply_leg_angles(leg_id, angles)

            time.sleep(step_time)

        self._return_to_stand()
        print(f"\n{'=' * 60}")
        print("Single step complete")
        print(f"{'=' * 60}\n")


# Demo function for testing
def demo_gait(set_servo_func, use_ik=False, generator_mode=False):
    """Demo the gait - single step forward"""
    controller = GaitController(set_servo_func, use_ik=use_ik, generator_mode=generator_mode)
    controller.single_step("forward")
    return controller
