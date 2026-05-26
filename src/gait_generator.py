#!/usr/bin/env python3
"""
Generic gait generator using CPG (Central Pattern Generator) oscillators
combined with Bezier foot trajectories.

Supports multiple gait types (walk, trot, pace, bound) with smooth online
transitions between them.
"""
import math
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass, field


# =============================================================================
# Gait phase definitions (desired phase offsets per leg, normalized [0,1))
# =============================================================================
GAIT_PHASE_OFFSETS = {
    "walk": {"FL": 0.00, "FR": 0.50, "RL": 0.75, "RR": 0.25},   # 4-beat
    "trot": {"FL": 0.00, "FR": 0.50, "RL": 0.50, "RR": 0.00},   # diagonal pairs
    "pace": {"FL": 0.00, "FR": 0.50, "RL": 0.00, "RR": 0.50},   # lateral pairs
    "bound": {"FL": 0.00, "FR": 0.00, "RL": 0.50, "RR": 0.50},  # front/hind pairs
}

LEG_ORDER = ["FL", "FR", "RL", "RR"]
LEFT_LEGS = {"FL", "RL"}
RIGHT_LEGS = {"FR", "RR"}
FRONT_LEGS = {"FL", "FR"}
REAR_LEGS = {"RL", "RR"}


# =============================================================================
# Data classes
# =============================================================================
@dataclass
class CPGConfig:
    """Configuration for the CPG oscillator network."""
    base_frequency: float = 1.0          # Hz — base oscillation frequency
    coupling_strength: float = 5.0       # Strength of phase coupling
    transition_duration: float = 1.0     # Seconds to smoothly transition gait
    max_frequency: float = 3.0           # Hz — max allowed frequency
    min_frequency: float = 0.2           # Hz — min allowed frequency


@dataclass
class BezierConfig:
    """Configuration for Bezier foot trajectories."""
    stride_length: float = 0.04          # meters
    stride_height: float = 0.03          # meters
    lateral_fraction: float = 0.0        # -1.0 to 1.0 (sideways bias)
    duty_factor: float = 0.5             # Fraction of cycle in stance (0.5 = walk/trot)
    ground_penetration: float = 0.0      # meters — how far foot sinks into ground


# =============================================================================
# CPG Oscillator Network
# =============================================================================
class CPGNetwork:
    """
    4 coupled Kuramoto-style oscillators, one per leg.

    Each oscillator i has phase φ_i evolving as:
        dφ_i/dt = ω + Σ_j K_ij * sin(φ_j - φ_i - Δφ_ij)

    where Δφ_ij is the desired phase difference for the current gait.
    During gait transitions, target Δφ values are interpolated smoothly.
    """

    def __init__(self, config: CPGConfig = None):
        self.config = config or CPGConfig()
        self._phases: Dict[str, float] = {leg: 0.0 for leg in LEG_ORDER}
        self._freq: float = self.config.base_frequency
        self._target_freq: float = self.config.base_frequency
        self._coupling: float = self.config.coupling_strength

        # Current and target phase offsets (relative to FL)
        self._current_offsets: Dict[str, float] = {leg: 0.0 for leg in LEG_ORDER}
        self._target_offsets: Dict[str, float] = {leg: 0.0 for leg in LEG_ORDER}

        # Transition state
        self._in_transition: bool = False
        self._transition_timer: float = 0.0
        self._transition_total: float = 0.0
        self._pre_transition_offsets: Dict[str, float] = {leg: 0.0 for leg in LEG_ORDER}

    @property
    def frequency(self) -> float:
        return self._freq

    def set_frequency(self, freq: float):
        """Set target intrinsic frequency (clamped to valid range)."""
        self._target_freq = max(self.config.min_frequency,
                                min(self.config.max_frequency, freq))

    def set_gait_offsets(self, offsets: Dict[str, float]):
        """
        Start a smooth transition to new phase offsets.
        offsets: dict mapping leg_id -> phase offset [0,1)
        """
        # Normalize offsets so FL is always 0 reference
        normalized = {}
        fl_offset = offsets.get("FL", 0.0)
        for leg in LEG_ORDER:
            normalized[leg] = (offsets.get(leg, 0.0) - fl_offset) % 1.0

        self._pre_transition_offsets = dict(self._current_offsets)
        self._target_offsets = normalized
        self._in_transition = True
        self._transition_timer = 0.0
        self._transition_total = self.config.transition_duration

    def get_phase(self, leg_id: str) -> float:
        """Return current phase of leg_id in [0,1)."""
        return self._phases.get(leg_id, 0.0) % 1.0

    def get_phases(self) -> Dict[str, float]:
        """Return all leg phases in [0,1)."""
        return {leg: self._phases[leg] % 1.0 for leg in LEG_ORDER}

    def _shortest_phase_diff(self, a: float, b: float) -> float:
        """
        Compute shortest directed phase difference from a to b,
        accounting for wrap-around on the unit circle.
        """
        diff = (b - a) % 1.0
        if diff > 0.5:
            diff -= 1.0
        return diff

    def _update_offsets(self, dt: float):
        """Interpolate phase offsets during a gait transition."""
        if not self._in_transition:
            self._current_offsets = dict(self._target_offsets)
            return

        self._transition_timer += dt
        alpha = min(1.0, self._transition_timer / self._transition_total)
        # Smoothstep for jerk-free interpolation
        alpha = alpha * alpha * (3.0 - 2.0 * alpha)

        for leg in LEG_ORDER:
            pre = self._pre_transition_offsets[leg]
            tgt = self._target_offsets[leg]
            # Use shortest-path interpolation for circular phases
            diff = self._shortest_phase_diff(pre, tgt)
            self._current_offsets[leg] = (pre + diff * alpha) % 1.0

        if self._transition_timer >= self._transition_total:
            self._in_transition = False
            self._current_offsets = dict(self._target_offsets)

    def update(self, dt: float) -> Dict[str, float]:
        """
        Advance CPG dynamics by dt seconds.

        Returns:
            Dict of {leg_id: phase} with phases in [0,1).
        """
        # Smooth frequency change
        freq_err = self._target_freq - self._freq
        self._freq += freq_err * min(1.0, dt * 5.0)  # ~0.2s time constant

        # Interpolate offsets if transitioning
        self._update_offsets(dt)

        # Compute phase derivatives
        dphase = {}
        for leg_i in LEG_ORDER:
            phi_i = self._phases[leg_i]
            coupling_sum = 0.0
            for leg_j in LEG_ORDER:
                if leg_i == leg_j:
                    continue
                phi_j = self._phases[leg_j]
                desired_diff = self._current_offsets[leg_j] - self._current_offsets[leg_i]
                actual_diff = (phi_j - phi_i) % 1.0
                if actual_diff > 0.5:
                    actual_diff -= 1.0
                diff_err = self._shortest_phase_diff(actual_diff, desired_diff)
                coupling_sum += math.sin(diff_err * 2.0 * math.pi)

            dphase[leg_i] = 2.0 * math.pi * self._freq + self._coupling * coupling_sum

        # Integrate
        for leg in LEG_ORDER:
            self._phases[leg] = (self._phases[leg] + dphase[leg] * dt / (2.0 * math.pi)) % 1.0

        return self.get_phases()


# =============================================================================
# Bezier Foot Trajectory Generator
# =============================================================================
class BezierTrajectory:
    """
    Generates physically plausible foot trajectories using 4-point Bezier
    curves for the swing phase and linear ground movement for stance.
    """

    def __init__(self, config: BezierConfig = None):
        self.config = config or BezierConfig()

    def _bezier_point(self, t: float, p0: Tuple[float, float, float],
                      p1: Tuple[float, float, float],
                      p2: Tuple[float, float, float],
                      p3: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Evaluate a cubic Bezier curve at parameter t ∈ [0,1]."""
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        z = uuu * p0[2] + 3 * uu * t * p1[2] + 3 * u * tt * p2[2] + ttt * p3[2]
        return (x, y, z)

    def _build_swing_control_points(self, stride_length: float, stride_height: float,
                                    lateral_offset: float, leg_id: str) -> List[Tuple[float, float, float]]:
        """
        Build 4 Bezier control points for swing phase.
        Coordinate frame: x = forward, y = up, z = lateral (positive = right)
        """
        half_len = stride_length / 2.0

        # Lift-off (back, ground)
        p0 = (-half_len, 0.0, lateral_offset)
        # Start of lift (still back, lifting up)
        p1 = (-half_len * 0.5, stride_height, lateral_offset)
        # Coming down (forward, still up)
        p2 = (half_len * 0.5, stride_height * 0.7, lateral_offset)
        # Touch-down (forward, ground)
        p3 = (half_len, 0.0, lateral_offset)

        return [p0, p1, p2, p3]

    def get_foot_position(self, phase: float, leg_id: str,
                          stride_length: float = None,
                          stride_height: float = None,
                          lateral_fraction: float = None,
                          turn_rate: float = 0.0,
                          direction_mult: float = 1.0) -> Tuple[float, float, float]:
        """
        Compute foot position for a leg at a given gait phase.

        Args:
            phase: Gait phase [0,1). 0=start of swing, duty_factor=end of swing/start of stance.
            leg_id: "FL", "FR", "RL", or "RR"
            stride_length: Override config stride_length
            stride_height: Override config stride_height
            lateral_fraction: Override config lateral_fraction (-1 to 1)
            turn_rate: -1.0 to 1.0, positive = turn right
            direction_mult: 1.0 for forward, -1.0 for backward

        Returns:
            (x, y, z) foot position relative to neutral stance position
        """
        sl = stride_length if stride_length is not None else self.config.stride_length
        sh = stride_height if stride_height is not None else self.config.stride_height
        lat = lateral_fraction if lateral_fraction is not None else self.config.lateral_fraction
        duty = self.config.duty_factor

        # Determine if in swing or stance
        if phase < duty:
            # Swing phase — Bezier curve
            swing_phase = phase / duty if duty > 0 else 0.0
            swing_phase = max(0.0, min(1.0, swing_phase))

            # Apply turn differential: inner legs shorter stride, outer longer
            if leg_id in LEFT_LEGS:
                turn_mult = 1.0 - turn_rate * 0.3
            else:
                turn_mult = 1.0 + turn_rate * 0.3
            adj_stride = sl * turn_mult * direction_mult

            # Lateral offset from config
            if leg_id in LEFT_LEGS:
                lat_offset = -lat * sl * 0.5
            else:
                lat_offset = lat * sl * 0.5

            pts = self._build_swing_control_points(adj_stride, sh, lat_offset, leg_id)
            return self._bezier_point(swing_phase, *pts)
        else:
            # Stance phase — linear push back along ground
            stance_phase = (phase - duty) / (1.0 - duty) if duty < 1.0 else 0.0
            stance_phase = max(0.0, min(1.0, stance_phase))

            # Apply turn differential
            if leg_id in LEFT_LEGS:
                turn_mult = 1.0 - turn_rate * 0.3
            else:
                turn_mult = 1.0 + turn_rate * 0.3
            adj_stride = sl * turn_mult * direction_mult

            half_len = adj_stride / 2.0
            # Move from front to back linearly
            x = half_len - adj_stride * stance_phase
            y = -self.config.ground_penetration  # slight ground contact

            if leg_id in LEFT_LEGS:
                z = -lat * sl * 0.5
            else:
                z = lat * sl * 0.5

            return (x, y, z)


# =============================================================================
# Main GaitGenerator
# =============================================================================
class GaitGenerator:
    """
    High-level gait generator combining CPG oscillators with Bezier foot trajectories.

    Supports walk, trot, pace, and bound gaits with smooth online transitions.
    """

    def __init__(self, cpg_config: CPGConfig = None, bezier_config: BezierConfig = None):
        self.cpg = CPGNetwork(cpg_config or CPGConfig())
        self.traj = BezierTrajectory(bezier_config or BezierConfig())
        self._gait_type: str = "trot"
        self._speed: float = 1.0
        self._direction: str = "forward"
        self._turn_rate: float = 0.0
        self._lateral_fraction: float = 0.0
        self._stride_length: float = self.traj.config.stride_length
        self._stride_height: float = self.traj.config.stride_height

        # Initialize with trot
        self.set_gait_type("trot")

    def set_gait_type(self, gait: str):
        """
        Set the gait type. Triggers a smooth transition if already running.

        Args:
            gait: One of "walk", "trot", "pace", "bound"

        Raises:
            ValueError: If gait type is unknown.
        """
        gait = gait.lower()
        if gait not in GAIT_PHASE_OFFSETS:
            raise ValueError(f"Unknown gait '{gait}'. Supported: {list(GAIT_PHASE_OFFSETS.keys())}")

        self._gait_type = gait
        self.cpg.set_gait_offsets(GAIT_PHASE_OFFSETS[gait])

    def set_speed(self, speed: float):
        """
        Set locomotion speed. Affects oscillator frequency.

        Args:
            speed: Speed multiplier (0.0 = stopped, 1.0 = normal, >1.0 = faster)
        """
        self._speed = max(0.0, speed)
        self.cpg.set_frequency(self.cpg.config.base_frequency * self._speed)

    def set_direction(self, direction: str):
        """
        Set walking direction.

        Args:
            direction: "forward" or "backward"
        """
        direction = direction.lower()
        if direction not in ("forward", "backward"):
            raise ValueError("Direction must be 'forward' or 'backward'")
        self._direction = direction

    def set_turn_rate(self, rate: float):
        """
        Set turn rate for steering.

        Args:
            rate: -1.0 (full left) to 1.0 (full right), 0.0 = straight
        """
        self._turn_rate = max(-1.0, min(1.0, rate))

    def set_stride_params(self, length: float = None, height: float = None):
        """
        Update stride parameters.

        Args:
            length: Stride length in meters (None = keep current)
            height: Stride height in meters (None = keep current)
        """
        if length is not None:
            self._stride_length = max(0.0, length)
            self.traj.config.stride_length = self._stride_length
        if height is not None:
            self._stride_height = max(0.0, height)
            self.traj.config.stride_height = self._stride_height

    def set_lateral_fraction(self, fraction: float):
        """
        Set lateral bias for side-stepping.

        Args:
            fraction: -1.0 to 1.0
        """
        self._lateral_fraction = max(-1.0, min(1.0, fraction))

    def update(self, dt: float) -> Dict[str, Tuple[float, float, float]]:
        """
        Advance the gait generator by dt seconds.

        Args:
            dt: Time step in seconds

        Returns:
            Dict mapping leg_id -> (x, y, z) foot position relative to neutral stance.
        """
        phases = self.cpg.update(dt)
        direction_mult = -1.0 if self._direction == "backward" else 1.0

        result = {}
        for leg in LEG_ORDER:
            result[leg] = self.traj.get_foot_position(
                phase=phases[leg],
                leg_id=leg,
                stride_length=self._stride_length,
                stride_height=self._stride_height,
                lateral_fraction=self._lateral_fraction,
                turn_rate=self._turn_rate,
                direction_mult=direction_mult,
            )
        return result

    def get_leg_phase(self, leg_id: str) -> float:
        """
        Get the current phase of a specific leg.

        Args:
            leg_id: "FL", "FR", "RL", or "RR"

        Returns:
            Phase in [0, 1).
        """
        return self.cpg.get_phase(leg_id)

    def get_gait_type(self) -> str:
        """Return current gait type."""
        return self._gait_type

    def is_transitioning(self) -> bool:
        """Return True if the generator is currently transitioning between gaits."""
        return self.cpg._in_transition

    def reset_phases(self):
        """Reset all oscillator phases to their gait-defined offsets."""
        offsets = GAIT_PHASE_OFFSETS.get(self._gait_type, GAIT_PHASE_OFFSETS["trot"])
        for leg in LEG_ORDER:
            self.cpg._phases[leg] = offsets[leg]
        self.cpg._current_offsets = {leg: offsets[leg] for leg in LEG_ORDER}
        self.cpg._target_offsets = {leg: offsets[leg] for leg in LEG_ORDER}
        self.cpg._in_transition = False


# =============================================================================
# Utility: convert generator output to servo commands via IKInterface
# =============================================================================
def feet_positions_to_servo_angles(feet_positions: Dict[str, Tuple[float, float, float]],
                                   ik_interface,
                                   neutral_feet: Dict[str, object]) -> Dict[str, Tuple[float, float, float]]:
    """
    Convert relative foot positions from GaitGenerator to absolute foot positions,
    then compute servo angles via IKInterface.

    Args:
        feet_positions: {leg_id: (dx, dy, dz)} relative to neutral
        ik_interface: Instance of IKInterface
        neutral_feet: {leg_id: np.array([x, y, z])} neutral positions

    Returns:
        {leg_id: (hip, knee, ankle)} logical angles in degrees
    """
    # Build absolute foot positions
    abs_feet = {}
    for leg, rel in feet_positions.items():
        n = neutral_feet[leg]
        abs_feet[leg] = [n[0] + rel[0], n[1] + rel[1], n[2] + rel[2]]

    angles = ik_interface.feet_to_angles(abs_feet)
    return angles


# =============================================================================
# Simple test
# =============================================================================
if __name__ == "__main__":
    import time

    gen = GaitGenerator()
    gen.set_speed(1.0)

    print("Testing gait generator...")
    print(f"Initial gait: {gen.get_gait_type()}")

    # Simulate 2 seconds of trot
    dt = 0.02
    for _ in range(100):
        positions = gen.update(dt)
        if _ % 25 == 0:
            phases = {leg: gen.get_leg_phase(leg) for leg in LEG_ORDER}
            print(f"  t={_*dt:.2f} phases={phases}")

    print("\nTransitioning to walk...")
    gen.set_gait_type("walk")

    for _ in range(100):
        positions = gen.update(dt)
        if _ % 25 == 0:
            phases = {leg: gen.get_leg_phase(leg) for leg in LEG_ORDER}
            print(f"  t={_*dt:.2f} phases={phases} transitioning={gen.is_transitioning()}")

    print("\nTransitioning to bound...")
    gen.set_gait_type("bound")

    for _ in range(100):
        positions = gen.update(dt)
        if _ % 25 == 0:
            phases = {leg: gen.get_leg_phase(leg) for leg in LEG_ORDER}
            print(f"  t={_*dt:.2f} phases={phases} transitioning={gen.is_transitioning()}")

    print("\nSample foot positions (trot at phase 0.25):")
    gen2 = GaitGenerator()
    gen2.set_gait_type("trot")
    gen2.cpg._phases = {"FL": 0.25, "FR": 0.75, "RL": 0.75, "RR": 0.25}
    pos = gen2.update(0.0)
    for leg, p in pos.items():
        print(f"  {leg}: x={p[0]*1000:.1f}mm y={p[1]*1000:.1f}mm z={p[2]*1000:.1f}mm")
