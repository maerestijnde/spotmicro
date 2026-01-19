#!/usr/bin/env python3
"""
Stability monitoring for quadruped robot.

This module provides real-time stability monitoring based on IMU pitch/roll readings.
It categorizes the robot's stability state and can trigger appropriate responses
when instability is detected.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time


class StabilityState(Enum):
    """Enumeration of stability states from most stable to emergency."""
    STABLE = "stable"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class StabilityThresholds:
    """Thresholds for stability state transitions.

    All values are in degrees. When pitch or roll exceeds a threshold,
    the stability state changes accordingly.

    Attributes:
        warning_pitch: Pitch angle (degrees) that triggers WARNING state
        warning_roll: Roll angle (degrees) that triggers WARNING state
        critical_pitch: Pitch angle (degrees) that triggers CRITICAL state
        critical_roll: Roll angle (degrees) that triggers CRITICAL state
        emergency_pitch: Pitch angle (degrees) that triggers EMERGENCY state
        emergency_roll: Roll angle (degrees) that triggers EMERGENCY state
    """
    warning_pitch: float = 10.0   # degrees
    warning_roll: float = 10.0    # degrees
    critical_pitch: float = 20.0  # degrees
    critical_roll: float = 20.0   # degrees
    emergency_pitch: float = 30.0 # degrees
    emergency_roll: float = 30.0  # degrees


class StabilityMonitor:
    """Monitors robot stability and triggers appropriate responses.

    The monitor tracks pitch and roll angles from the IMU and categorizes
    the robot's stability into four states:

    - STABLE: Normal operation, angles within acceptable range
    - WARNING: Slightly tilted, may need attention
    - CRITICAL: Significantly tilted, corrective action recommended
    - EMERGENCY: Severely tilted, immediate action required (e.g., stop walking)

    Example usage:
        monitor = StabilityMonitor()

        # In your control loop:
        state = monitor.update(pitch, roll)
        if state == StabilityState.EMERGENCY:
            gait_controller.stop()

        # Get detailed status:
        status = monitor.get_status()
    """

    def __init__(self, thresholds: Optional[StabilityThresholds] = None):
        """Initialize the stability monitor.

        Args:
            thresholds: Custom thresholds for stability states. If None, uses defaults.
        """
        self.thresholds = thresholds or StabilityThresholds()
        self.current_state = StabilityState.STABLE
        self.previous_state = StabilityState.STABLE
        self.last_check_time = time.time()
        self.pitch = 0.0
        self.roll = 0.0

        # Track time in each state for analysis
        self.state_start_time = time.time()
        self.state_history: list[tuple[StabilityState, float]] = []
        self.max_history_length = 100

        # Callbacks for state changes
        self._on_state_change_callbacks: list = []

    def update(self, pitch: float, roll: float) -> StabilityState:
        """Update with current IMU readings and return stability state.

        Args:
            pitch: Current pitch angle in degrees (positive = nose up)
            roll: Current roll angle in degrees (positive = right side down)

        Returns:
            Current stability state after evaluation
        """
        self.pitch = pitch
        self.roll = roll
        self.last_check_time = time.time()

        abs_pitch = abs(pitch)
        abs_roll = abs(roll)

        # Determine new state based on thresholds (check worst case first)
        if abs_pitch > self.thresholds.emergency_pitch or abs_roll > self.thresholds.emergency_roll:
            new_state = StabilityState.EMERGENCY
        elif abs_pitch > self.thresholds.critical_pitch or abs_roll > self.thresholds.critical_roll:
            new_state = StabilityState.CRITICAL
        elif abs_pitch > self.thresholds.warning_pitch or abs_roll > self.thresholds.warning_roll:
            new_state = StabilityState.WARNING
        else:
            new_state = StabilityState.STABLE

        # Handle state transition
        if new_state != self.current_state:
            self._handle_state_change(new_state)

        return self.current_state

    def _handle_state_change(self, new_state: StabilityState):
        """Handle a state transition.

        Args:
            new_state: The new stability state
        """
        self.previous_state = self.current_state

        # Record time spent in previous state
        time_in_state = time.time() - self.state_start_time
        self.state_history.append((self.previous_state, time_in_state))

        # Trim history if needed
        if len(self.state_history) > self.max_history_length:
            self.state_history = self.state_history[-self.max_history_length:]

        # Update to new state
        self.current_state = new_state
        self.state_start_time = time.time()

        # Notify callbacks
        for callback in self._on_state_change_callbacks:
            try:
                callback(self.previous_state, new_state, self.pitch, self.roll)
            except Exception as e:
                print(f"Stability callback error: {e}")

    def on_state_change(self, callback):
        """Register a callback for state changes.

        Args:
            callback: Function with signature (old_state, new_state, pitch, roll)
        """
        self._on_state_change_callbacks.append(callback)

    def get_status(self) -> dict:
        """Get current stability status.

        Returns:
            Dictionary containing current state, angles, and timing info
        """
        return {
            "state": self.current_state.value,
            "pitch": round(self.pitch, 2),
            "roll": round(self.roll, 2),
            "last_check": self.last_check_time,
            "time_in_state": round(time.time() - self.state_start_time, 2),
            "thresholds": {
                "warning": {"pitch": self.thresholds.warning_pitch, "roll": self.thresholds.warning_roll},
                "critical": {"pitch": self.thresholds.critical_pitch, "roll": self.thresholds.critical_roll},
                "emergency": {"pitch": self.thresholds.emergency_pitch, "roll": self.thresholds.emergency_roll}
            }
        }

    def get_state_statistics(self) -> dict:
        """Get statistics about time spent in each state.

        Returns:
            Dictionary with total time and percentage for each state
        """
        total_time = sum(duration for _, duration in self.state_history)
        if total_time == 0:
            return {state.value: {"time": 0, "percentage": 0} for state in StabilityState}

        stats = {}
        for state in StabilityState:
            state_time = sum(duration for s, duration in self.state_history if s == state)
            stats[state.value] = {
                "time": round(state_time, 2),
                "percentage": round(100 * state_time / total_time, 1)
            }

        return stats

    def is_stable(self) -> bool:
        """Check if robot is currently stable.

        Returns:
            True if in STABLE state
        """
        return self.current_state == StabilityState.STABLE

    def needs_attention(self) -> bool:
        """Check if robot needs attention (WARNING or worse).

        Returns:
            True if in WARNING, CRITICAL, or EMERGENCY state
        """
        return self.current_state != StabilityState.STABLE

    def is_emergency(self) -> bool:
        """Check if robot is in emergency state.

        Returns:
            True if in EMERGENCY state
        """
        return self.current_state == StabilityState.EMERGENCY

    def reset(self):
        """Reset the monitor to initial state."""
        self.current_state = StabilityState.STABLE
        self.previous_state = StabilityState.STABLE
        self.pitch = 0.0
        self.roll = 0.0
        self.state_start_time = time.time()
        self.state_history.clear()
