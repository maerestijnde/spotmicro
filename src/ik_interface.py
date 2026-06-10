#!/usr/bin/env python3
"""IK Interface for MicroSpot - Correct coordinate mapping"""
import math
import numpy as np
from math import degrees
import json
from pathlib import Path
from kinematics.spot_micro_stick_figure import SpotMicroStickFigure, SpotMicroLeg
from kinematics.utilities import transformations

# Default calibration path
_CALIBRATION_FILE = Path(__file__).parent / "calibration.json"


class IKInterface:
    LEG_TO_IK_INDEX = {'RR': 0, 'FR': 1, 'FL': 2, 'RL': 3}
    LEG_CHANNELS = {
        'FL': [0, 1, 2], 'FR': [3, 4, 5],
        'RL': [6, 7, 8], 'RR': [9, 10, 11],
    }
    LEFT_LEGS = ['FL', 'RL']
    LEG_NAME_MAP = {
        'RR': 'leg_rightback',
        'FR': 'leg_rightfront',
        'FL': 'leg_leftfront',
        'RL': 'leg_leftback'
    }

    def __init__(self, calibration_path=None, body_height=0.10):
        self.body_height = body_height
        self.model = SpotMicroStickFigure(x=0, y=body_height, z=0)
        self.calibration = {}
        if calibration_path:
            self._load_calibration(calibration_path)

        # Foot positions: include hip_length in Z offset
        hl = self.model.body_length / 2
        hw = self.model.body_width / 2 + self.model.hip_length
        self.neutral_feet = {
            'FL': np.array([hl, 0, -hw]),
            'FR': np.array([hl, 0, hw]),
            'RL': np.array([-hl, 0, -hw]),
            'RR': np.array([-hl, 0, hw]),
        }

        # Workspace limits derived from leg geometry
        l1 = self.model.hip_length
        l2 = self.model.upper_leg_length
        l3 = self.model.lower_leg_length
        self._max_reach = math.sqrt(l1**2 + (l2 + l3)**2)
        self._min_reach = math.sqrt(l1**2 + abs(l2 - l3)**2)

        # Cache last known good solution for each leg (logical angles)
        self._last_good_angles = {
            'FL': [90.0, 90.0, 90.0],
            'FR': [90.0, 90.0, 90.0],
            'RL': [90.0, 90.0, 90.0],
            'RR': [90.0, 90.0, 90.0],
        }

        # Observability counters
        self.failure_count: int = 0
        self.clamp_count: int = 0
        self.last_failure: str = ""
        self.on_failure = None  # Optional[Callable[[str, str], None]] — called as on_failure(leg_id, reason)

    def _load_calibration(self, path):
        try:
            with open(path) as f:
                data = json.load(f)
            self.calibration = {int(k): v for k, v in data.get('servos', {}).items()}
        except Exception:
            pass

    def get_neutral_foot_positions(self):
        return {k: v.copy() for k, v in self.neutral_feet.items()}

    def set_body_height(self, height):
        self.body_height = height
        self.model = SpotMicroStickFigure(x=0, y=height, z=0)

    def _is_workspace_valid(self, leg_id, x, y, z):
        """Check if a foot position is reachable by the leg."""
        try:
            leg_name = self.LEG_NAME_MAP[leg_id]
            leg = self.model.legs[leg_name]

            # Transform to leg-local coordinates
            ht_inv = transformations.ht_inverse(leg.get_homog_transf())
            p_global = np.array([x, y, z, 1.0])
            p_local = ht_inv.dot(p_global)
            x4, y4, z4 = float(p_local[0]), float(p_local[1]), float(p_local[2])

            l1, l2, l3 = leg._l1, leg._l2, leg._l3
            r2 = x4**2 + y4**2 + z4**2
            r_min2 = l1**2 + (l2 - l3)**2
            r_max2 = l1**2 + (l2 + l3)**2

            if r2 < r_min2 - 1e-9 or r2 > r_max2 + 1e-9:
                return False

            if x4**2 + y4**2 < l1**2 - 1e-9:
                return False

            return True
        except Exception:
            return False

    def _clamp_to_workspace(self, leg_id, x, y, z):
        """Clamp a foot position to the nearest valid workspace point."""
        try:
            leg_name = self.LEG_NAME_MAP[leg_id]
            leg = self.model.legs[leg_name]

            ht_inv = transformations.ht_inverse(leg.get_homog_transf())
            p_global = np.array([x, y, z, 1.0])
            p_local = ht_inv.dot(p_global)
            x4, y4, z4 = float(p_local[0]), float(p_local[1]), float(p_local[2])

            l1, l2, l3 = leg._l1, leg._l2, leg._l3
            r2 = x4**2 + y4**2 + z4**2
            r_min2 = l1**2 + (l2 - l3)**2
            r_max2 = l1**2 + (l2 + l3)**2

            # Clamp radial distance
            if r2 > r_max2:
                scale = math.sqrt(r_max2 / r2)
                x4 *= scale
                y4 *= scale
                z4 *= scale
            elif r2 < r_min2 and r2 > 1e-12:
                scale = math.sqrt(r_min2 / r2)
                x4 *= scale
                y4 *= scale
                z4 *= scale

            # Ensure x4^2 + y4^2 >= l1^2
            xy2 = x4**2 + y4**2
            if xy2 < l1**2 and xy2 > 1e-12:
                scale = l1 / math.sqrt(xy2)
                x4 *= scale
                y4 *= scale

            # Convert back to global coordinates
            p_local_clamped = np.array([x4, y4, z4, 1.0])
            p_global_clamped = leg.get_homog_transf().dot(p_local_clamped)
            return float(p_global_clamped[0]), float(p_global_clamped[1]), float(p_global_clamped[2])
        except Exception:
            # If clamping fails, return original position
            return x, y, z

    def set_foot_position(self, leg_id, x, y, z):
        """
        Compute IK for a single leg to reach (x, y, z) in global coordinates.

        Args:
            leg_id: "FL", "FR", "RL", or "RR"
            x, y, z: Target foot position in meters (global frame)

        Returns:
            list: [hip, knee, ankle] logical angles in degrees.
            On IK failure, returns the cached last-known-good solution.
        """
        if leg_id not in self.LEG_CHANNELS:
            raise ValueError(f"Invalid leg_id: {leg_id}")

        # Validate workspace and clamp if needed
        if not self._is_workspace_valid(leg_id, x, y, z):
            x, y, z = self._clamp_to_workspace(leg_id, x, y, z)
            self.clamp_count += 1

        try:
            leg_name = self.LEG_NAME_MAP[leg_id]
            # Get the leg's base transform and geometry from the model
            ht_leg_start = self.model.legs[leg_name].get_homog_transf()
            l1 = self.model.hip_length
            l2 = self.model.upper_leg_length
            l3 = self.model.lower_leg_length
            leg12 = leg_name in ('leg_rightback', 'leg_rightfront')

            # Create a temporary leg for isolated IK (doesn't mutate model state)
            temp_leg = SpotMicroLeg(0.0, 0.0, 0.0, l1, l2, l3, ht_leg_start, leg12)
            temp_leg.set_foot_position_in_global_coords(x, y, z)
            q1, q2, q3 = temp_leg.get_leg_angles()

            # Check for NaN/invalid angles
            if any(math.isnan(a) or math.isinf(a) for a in (q1, q2, q3)):
                raise ValueError("IK produced invalid angles")

            # Convert to logical angles (0-180, 90 = neutral)
            if leg_id in self.LEFT_LEGS:
                angles = [90.0 - degrees(q1), 90.0 + degrees(q2), 90.0 + degrees(q3)]
            else:
                angles = [90.0 + degrees(q1), 90.0 - degrees(q2), 90.0 + degrees(q3)]

            # Clamp to valid servo range
            angles = [max(0.0, min(180.0, a)) for a in angles]

            # Cache good solution
            self._last_good_angles[leg_id] = angles.copy()
            return angles

        except Exception as e:
            import logging
            reason = f"{type(e).__name__}: {e}"
            self.failure_count += 1
            self.last_failure = reason
            logging.getLogger("microspot.ik").warning(
                f"IK failed for {leg_id} at ({x:.3f}, {y:.3f}, {z:.3f}): {reason}. "
                f"Using cached solution: {self._last_good_angles[leg_id]}"
            )
            if self.on_failure is not None:
                try:
                    self.on_failure(leg_id, reason)
                except Exception:
                    pass
            return self._last_good_angles[leg_id].copy()

    def get_ik_stats(self) -> dict:
        """Return observability counters."""
        return {
            "failure_count": self.failure_count,
            "clamp_count": self.clamp_count,
            "last_failure": self.last_failure,
        }

    def feet_to_angles(self, foot_positions):
        coords = np.array([foot_positions['RR'], foot_positions['FR'],
                          foot_positions['FL'], foot_positions['RL']])
        self.model.set_absolute_foot_coordinates(coords)
        ik = self.model.get_leg_angles()
        result = {}
        for leg, idx in self.LEG_TO_IK_INDEX.items():
            q1, q2, q3 = ik[idx]
            if leg in self.LEFT_LEGS:
                result[leg] = [90-degrees(q1), 90+degrees(q2), 90+degrees(q3)]
            else:
                result[leg] = [90+degrees(q1), 90-degrees(q2), 90+degrees(q3)]
        return result

    def angles_to_servo_commands(self, angles):
        cmds = {}
        for leg, angs in angles.items():
            for i, ch in enumerate(self.LEG_CHANNELS[leg]):
                ang = angs[i]
                if ch in self.calibration:
                    c = self.calibration[ch]
                    delta = ang - 90
                    val = c['neutral_angle'] + c['direction'] * delta
                    val = max(0, min(180, val))
                else:
                    val = ang
                cmds[ch] = val
        return cmds

    def feet_to_servo_commands(self, fp):
        return self.angles_to_servo_commands(self.feet_to_angles(fp))


if __name__ == "__main__":
    ik = IKInterface(str(_CALIBRATION_FILE), body_height=0.10)
    feet = ik.get_neutral_foot_positions()
    print("Feet (mm):", {k: [round(v*1000) for v in pos] for k, pos in feet.items()})
    angles = ik.feet_to_angles(feet)
    print("Logical angles:", {k: [round(a) for a in v] for k, v in angles.items()})
    cmds = ik.feet_to_servo_commands(feet)
    print("Servo cmds:", {k: round(v) for k, v in sorted(cmds.items())})

    # Test per-leg IK via set_foot_position
    print("\nPer-leg IK test (neutral positions):")
    for leg_id in ['FL', 'FR', 'RL', 'RR']:
        neutral = feet[leg_id]
        leg_angles = ik.set_foot_position(leg_id, neutral[0], neutral[1], neutral[2])
        print(f"  {leg_id}: {[round(a) for a in leg_angles]}")

    # Test workspace validation / clamping
    print("\nWorkspace clamping test (unreachable position):")
    far_angles = ik.set_foot_position('FL', 0.5, 0.5, 0.5)
    print(f"  FL (0.5,0.5,0.5) clamped: {[round(a) for a in far_angles]}")
