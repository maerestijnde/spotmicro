#!/usr/bin/env python3
"""
Balance Controller for MicroSpot
Uses MPU6050 IMU for pitch/roll measurement and balance correction
"""
import math
import time

# Try to import MPU6050, allow simulation mode if not available
try:
    from mpu6050 import mpu6050
    MPU_AVAILABLE = True
except ImportError:
    MPU_AVAILABLE = False
    print("Warning: mpu6050 package not available, balance will use simulated values")


class BalanceController:
    """
    IMU-based balance controller for quadruped robot.

    Uses MPU6050 accelerometer to measure pitch and roll,
    then calculates leg angle corrections to maintain balance.
    """

    def __init__(self, address=0x68):
        """
        Initialize balance controller.

        Args:
            address: I2C address of MPU6050 (default 0x68)
        """
        self.imu = None
        self.simulation_mode = not MPU_AVAILABLE

        if MPU_AVAILABLE:
            try:
                self.imu = mpu6050(address)
                # Warmup reads - first read often returns zeros
                for _ in range(3):
                    self.imu.get_accel_data()
                    time.sleep(0.01)
                print(f"MPU6050 initialized at 0x{address:02x}")
            except Exception as e:
                print(f"MPU6050 init failed: {e}, using simulation mode")
                self.simulation_mode = True

        # Calibration offsets (set by calibrate())
        self.pitch_offset = 0.0
        self.roll_offset = 0.0

        # Control gains
        self.kp = 0.5  # Proportional gain for balance correction
        self.pitch_gain = 1.0  # Pitch sensitivity
        self.roll_gain = 1.0   # Roll sensitivity

        # Filtering
        self._last_pitch = 0.0
        self._last_roll = 0.0
        self._last_raw_pitch = 0.0  # Last valid raw reading (before filter)
        self._last_raw_roll = 0.0
        self._alpha = 0.25  # Low-pass filter coefficient (0-1, higher = more responsive)

    def calibrate(self, samples=30):
        """
        Calibrate IMU zero point by averaging samples.
        Robot should be on flat surface and stationary.

        Args:
            samples: Number of samples to average
        """
        if self.simulation_mode:
            self.pitch_offset = 0.0
            self.roll_offset = 0.0
            print("Calibration skipped (simulation mode)")
            return

        print(f"Calibrating IMU with {samples} samples...")
        pitch_sum = 0.0
        roll_sum = 0.0

        for i in range(samples):
            try:
                p, r = self._read_raw_angles()
                pitch_sum += p
                roll_sum += r
                time.sleep(0.02)
            except Exception as e:
                print(f"Calibration sample {i} failed: {e}")

        self.pitch_offset = pitch_sum / samples
        self.roll_offset = roll_sum / samples

        print(f"Calibrated: pitch_offset={self.pitch_offset:.2f}, roll_offset={self.roll_offset:.2f}")

    def _read_raw_angles(self):
        """
        Read raw pitch and roll from accelerometer.

        Returns:
            Tuple of (pitch, roll) in degrees
        """
        if self.simulation_mode or self.imu is None:
            return 0.0, 0.0

        try:
            accel = self.imu.get_accel_data()

            # MPU6050 sometimes returns all zeros - ignore these bad readings
            # A valid reading should have z ~= 9.8 (gravity) when level
            if abs(accel['x']) < 0.01 and abs(accel['y']) < 0.01 and abs(accel['z']) < 0.01:
                # Bad reading - return last known good values
                return self._last_raw_pitch, self._last_raw_roll

            # Calculate pitch and roll from accelerometer
            # Pitch: rotation around X axis (front/back tilt)
            # Roll: rotation around Z axis (left/right tilt)
            pitch = math.atan2(accel['y'],
                              math.sqrt(accel['x']**2 + accel['z']**2)) * 57.2958
            roll = math.atan2(-accel['x'], accel['z']) * 57.2958

            # Store as last known good values
            self._last_raw_pitch = pitch
            self._last_raw_roll = roll

            return pitch, roll
        except Exception as e:
            print(f"IMU read error: {e}")
            return self._last_raw_pitch, self._last_raw_roll

    def get_angles(self):
        """
        Get current pitch and roll angles (calibrated and filtered).

        Returns:
            Tuple of (pitch, roll) in degrees
        """
        raw_pitch, raw_roll = self._read_raw_angles()

        # Apply calibration offset
        pitch = (raw_pitch - self.pitch_offset) * self.pitch_gain
        roll = (raw_roll - self.roll_offset) * self.roll_gain

        # Low-pass filter for smoothing
        pitch = self._alpha * pitch + (1 - self._alpha) * self._last_pitch
        roll = self._alpha * roll + (1 - self._alpha) * self._last_roll

        self._last_pitch = pitch
        self._last_roll = roll

        return pitch, roll

    def get_correction(self):
        """
        Calculate balance correction for each leg.

        Returns:
            Dict mapping leg_id to correction angle in degrees
            Positive = bend knee more, Negative = straighten knee
        """
        pitch, roll = self.get_angles()

        # Calculate corrections based on body orientation
        # If body tilts forward (positive pitch), front legs should extend, rear legs bend
        # If body tilts right (positive roll), left legs should extend, right legs bend

        corrections = {}

        # Front legs
        corrections['FL'] = -pitch * self.kp - roll * self.kp * 0.5
        corrections['FR'] = -pitch * self.kp + roll * self.kp * 0.5

        # Rear legs - NEGATIVE pitch correction (lift rear when tilting forward)
        # 0.5 factor makes rear legs less aggressive than front
        corrections['RL'] = -pitch * self.kp * 0.5 - roll * self.kp * 0.5
        corrections['RR'] = -pitch * self.kp * 0.5 + roll * self.kp * 0.5

        return corrections

    def set_kp(self, kp):
        """
        Set proportional gain for balance correction.

        Args:
            kp: Proportional gain (0.0 to 2.0 typical)
        """
        self.kp = max(0.0, min(2.0, kp))
        print(f"Balance Kp set to {self.kp}")

    def is_available(self):
        """Check if IMU is available and working."""
        return not self.simulation_mode and self.imu is not None


# Test function
if __name__ == "__main__":
    print("Balance Controller Test")
    print("=" * 40)

    balance = BalanceController()

    if balance.is_available():
        print("\nCalibrating... hold robot still on flat surface")
        balance.calibrate(30)

        print("\nReading angles (Ctrl+C to stop):")
        try:
            while True:
                pitch, roll = balance.get_angles()
                corrections = balance.get_correction()
                print(f"\rPitch: {pitch:+5.1f}  Roll: {roll:+5.1f}  "
                      f"FL: {corrections['FL']:+4.1f}  FR: {corrections['FR']:+4.1f}  "
                      f"RL: {corrections['RL']:+4.1f}  RR: {corrections['RR']:+4.1f}", end="")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nDone")
    else:
        print("IMU not available - simulation mode")
        pitch, roll = balance.get_angles()
        print(f"Simulated: pitch={pitch}, roll={roll}")
