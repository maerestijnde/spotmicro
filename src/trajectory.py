#!/usr/bin/env python3
"""Foot trajectory generation for gait control."""
import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class TrajectoryConfig:
    """Configuration for foot trajectories."""
    step_height: float = 0.03  # meters - how high to lift foot
    stride_length: float = 0.04  # meters - forward/back distance


class FootTrajectory:
    """Generates foot positions for gait phases."""

    def __init__(self, config: TrajectoryConfig = None):
        self.config = config or TrajectoryConfig()

    def swing_position(self, phase: float, neutral_x: float, neutral_y: float, neutral_z: float) -> Tuple[float, float, float]:
        """
        Calculate foot position during swing phase.

        Args:
            phase: 0.0 to 1.0 through swing
            neutral_x, neutral_y, neutral_z: Neutral foot position in meters

        Returns:
            (x, y, z) foot position in meters
        """
        # Sinusoidal lift profile
        lift = self.config.step_height * math.sin(phase * math.pi)

        # Linear forward movement
        forward_offset = self.config.stride_length * (phase - 0.5)

        return (
            neutral_x + forward_offset,
            neutral_y + lift,  # Y is up
            neutral_z
        )

    def stance_position(self, phase: float, neutral_x: float, neutral_y: float, neutral_z: float) -> Tuple[float, float, float]:
        """
        Calculate foot position during stance phase (pushing back).

        Args:
            phase: 0.0 to 1.0 through stance
            neutral_x, neutral_y, neutral_z: Neutral foot position

        Returns:
            (x, y, z) foot position in meters
        """
        # Foot moves backward relative to body (pushes body forward)
        backward_offset = self.config.stride_length * (0.5 - phase)

        return (
            neutral_x + backward_offset,
            neutral_y,  # No lift during stance
            neutral_z
        )


if __name__ == "__main__":
    # Test the trajectory generator
    config = TrajectoryConfig(step_height=0.03, stride_length=0.04)
    traj = FootTrajectory(config)

    # Neutral foot position (typical for standing)
    neutral = (0.0, 0.0, 0.133)  # x, y (height from body), z (lateral)

    print("Swing phase positions:")
    for i in range(11):
        phase = i / 10.0
        pos = traj.swing_position(phase, *neutral)
        print(f"  phase={phase:.1f}: x={pos[0]*1000:.1f}mm, y={pos[1]*1000:.1f}mm, z={pos[2]*1000:.1f}mm")

    print("\nStance phase positions:")
    for i in range(11):
        phase = i / 10.0
        pos = traj.stance_position(phase, *neutral)
        print(f"  phase={phase:.1f}: x={pos[0]*1000:.1f}mm, y={pos[1]*1000:.1f}mm, z={pos[2]*1000:.1f}mm")
