#!/usr/bin/env python3
"""Foot trajectory generation for gait control using Bezier curves."""
import math
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class TrajectoryConfig:
    """Configuration for foot trajectories."""
    step_height: float = 0.03  # meters - how high to lift foot
    stride_length: float = 0.04  # meters - forward/back distance


class FootTrajectory:
    """Generates foot positions for gait phases using Bezier curves."""

    def __init__(self, config: TrajectoryConfig = None):
        self.config = config or TrajectoryConfig()

    def _bezier4(self, t: float, p0: float, p1: float, p2: float, p3: float) -> float:
        """Cubic Bezier interpolation for a single coordinate."""
        u = 1.0 - t
        return (u * u * u * p0 +
                3.0 * u * u * t * p1 +
                3.0 * u * t * t * p2 +
                t * t * t * p3)

    def _move_along_arc(self, x: float, z: float, dist: float,
                        turn_radius: Optional[float]) -> Tuple[float, float]:
        """
        Move a point (x, z) by distance dist along an arc of given radius.

        Args:
            x, z: Starting position in the ground plane
            dist: Distance to move along the arc (positive = forward)
            turn_radius: Radius of turn in meters. Positive = left turn.
                         None or 0 means straight line.

        Returns:
            (new_x, new_z) after moving along the arc
        """
        if turn_radius is None or abs(turn_radius) < 0.01:
            return x + dist, z

        # Turn center is at (0, -turn_radius) in body x-z plane
        cx, cz = 0.0, -turn_radius
        dx, dz = x - cx, z - cz
        r = math.sqrt(dx * dx + dz * dz)
        if r < 0.001:
            return x + dist, z

        # Current angle from turn center
        theta = math.atan2(dx, dz)
        # For left turn (R > 0), forward motion increases theta
        dtheta = dist / r
        new_theta = theta + dtheta
        new_x = cx + r * math.sin(new_theta)
        new_z = cz + r * math.cos(new_theta)
        return new_x, new_z

    def evaluate(self, phase: float, neutral: Tuple[float, float, float],
                 is_swing: bool = True,
                 turn_radius: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Evaluate foot trajectory at any phase [0,1].

        Args:
            phase: 0.0 to 1.0 through the phase
            neutral: (x, y, z) neutral foot position in meters
            is_swing: True for swing phase (lift → swing → place),
                      False for stance phase (push back along ground)
            turn_radius: Optional turn radius in meters. Positive = left turn.

        Returns:
            (x, y, z) foot position in meters
        """
        nx, ny, nz = neutral
        half_stride = self.config.stride_length * 0.5

        if is_swing:
            # Swing: start at back, arc up and forward, touch down at front
            start_x, start_z = self._move_along_arc(nx, nz, -half_stride, turn_radius)
            end_x, end_z = self._move_along_arc(nx, nz, half_stride, turn_radius)

            # 4 control points for smooth lift → forward arc → placement
            p0 = (start_x, ny, start_z)
            p1 = (start_x + (end_x - start_x) * 0.25,
                  ny + self.config.step_height,
                  start_z + (end_z - start_z) * 0.25)
            p2 = (start_x + (end_x - start_x) * 0.75,
                  ny + self.config.step_height,
                  start_z + (end_z - start_z) * 0.75)
            p3 = (end_x, ny, end_z)

            x = self._bezier4(phase, p0[0], p1[0], p2[0], p3[0])
            y = self._bezier4(phase, p0[1], p1[1], p2[1], p3[1])
            z = self._bezier4(phase, p0[2], p1[2], p2[2], p3[2])
            return (x, y, z)
        else:
            # Stance: push back from front to back along ground
            start_x, start_z = self._move_along_arc(nx, nz, half_stride, turn_radius)
            end_x, end_z = self._move_along_arc(nx, nz, -half_stride, turn_radius)

            # Slight Bezier smoothing for velocity continuity
            p0 = (start_x, ny, start_z)
            p1 = (start_x + (end_x - start_x) * 0.3, ny,
                  start_z + (end_z - start_z) * 0.3)
            p2 = (start_x + (end_x - start_x) * 0.7, ny,
                  start_z + (end_z - start_z) * 0.7)
            p3 = (end_x, ny, end_z)

            x = self._bezier4(phase, p0[0], p1[0], p2[0], p3[0])
            y = self._bezier4(phase, p0[1], p1[1], p2[1], p3[1])
            z = self._bezier4(phase, p0[2], p1[2], p2[2], p3[2])
            return (x, y, z)

    def swing_position(self, phase: float, neutral_x: float, neutral_y: float,
                       neutral_z: float,
                       turn_radius: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Calculate foot position during swing phase.
        (Legacy wrapper — delegates to evaluate.)
        """
        return self.evaluate(
            phase, (neutral_x, neutral_y, neutral_z),
            is_swing=True, turn_radius=turn_radius
        )

    def stance_position(self, phase: float, neutral_x: float, neutral_y: float,
                        neutral_z: float,
                        turn_radius: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Calculate foot position during stance phase.
        (Legacy wrapper — delegates to evaluate.)
        """
        return self.evaluate(
            phase, (neutral_x, neutral_y, neutral_z),
            is_swing=False, turn_radius=turn_radius
        )


if __name__ == "__main__":
    # Test the trajectory generator
    config = TrajectoryConfig(step_height=0.03, stride_length=0.04)
    traj = FootTrajectory(config)

    # Neutral foot position (typical for standing)
    neutral = (0.0, 0.0, 0.133)  # x, y (height from body), z (lateral)

    print("Swing phase positions (straight):")
    for i in range(11):
        phase = i / 10.0
        pos = traj.swing_position(phase, *neutral)
        print(f"  phase={phase:.1f}: x={pos[0]*1000:.1f}mm, y={pos[1]*1000:.1f}mm, z={pos[2]*1000:.1f}mm")

    print("\nStance phase positions (straight):")
    for i in range(11):
        phase = i / 10.0
        pos = traj.stance_position(phase, *neutral)
        print(f"  phase={phase:.1f}: x={pos[0]*1000:.1f}mm, y={pos[1]*1000:.1f}mm, z={pos[2]*1000:.1f}mm")

    print("\nSwing phase positions (left turn, R=0.5m):")
    for i in range(11):
        phase = i / 10.0
        pos = traj.swing_position(phase, *neutral, turn_radius=0.5)
        print(f"  phase={phase:.1f}: x={pos[0]*1000:.1f}mm, y={pos[1]*1000:.1f}mm, z={pos[2]*1000:.1f}mm")

    print("\nEvaluate at phase 0.5 (swing vs stance):")
    print("  swing:", traj.evaluate(0.5, neutral, is_swing=True))
    print("  stance:", traj.evaluate(0.5, neutral, is_swing=False))
