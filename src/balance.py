#!/usr/bin/env python3
"""
Balance Controller for MicroSpot
Uses MPU6050 IMU for pitch/roll measurement and balance correction
"""
import math
import time
import threading

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

    def __init__(self, address=0x68, bus=None):
        """
        Initialize balance controller.

        Args:
            address: I2C address of MPU6050 (default 0x68)
            bus: I2C bus number (default None = auto-detect: try bus 3 first, then 1)
        """
        self.imu = None
        self.simulation_mode = not MPU_AVAILABLE
        self._i2c_bus = bus
        self._i2c_address = address

        if MPU_AVAILABLE:
            # Auto-detect bus: prefer bus 3 (isolated software I2C) over bus 1 (shared with servos)
            buses_to_try = [bus] if bus is not None else [3, 1]
            for try_bus in buses_to_try:
                try:
                    self.imu = mpu6050(address, bus=try_bus)
                    for _ in range(3):
                        self.imu.get_accel_data()
                        time.sleep(0.01)
                    self._i2c_bus = try_bus
                    print(f"MPU6050 initialized at 0x{address:02x} on bus {try_bus}")
                    break
                except Exception as e:
                    print(f"MPU6050 bus {try_bus} failed: {e}")
                    self.imu = None
            if self.imu is None:
                print("MPU6050 not found on any bus, using simulation mode")
                self.simulation_mode = True

        # Calibration offsets (set by calibrate())
        self.pitch_offset = 0.0
        self.roll_offset = 0.0

        # Control gains
        self.kp = 0.5  # Proportional gain for balance correction
        self.pitch_gain = 1.0  # Pitch sensitivity
        self.roll_gain = 1.0   # Roll sensitivity

        # I2C thread safety lock
        self._lock = threading.Lock()

        # Calibration state
        self._calibrating = False

        # Background IMU reader
        self._bg_running = False
        self._bg_thread = None

        # Stale data detection & recovery
        self._stale_count = 0
        self._stale_threshold = 20  # 2 seconds at 10Hz
        self._recovery_count = 0

        # Filtering
        self._last_pitch = 0.0
        self._last_roll = 0.0
        self._last_raw_pitch = 0.0  # Last valid raw reading (before filter)
        self._last_raw_roll = 0.0
        self._alpha = 0.25  # Low-pass filter coefficient (0-1, higher = more responsive)

    @property
    def is_calibrating(self):
        """Check if calibration is currently in progress."""
        return self._calibrating

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

        self._calibrating = True
        try:
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

            # Refresh cached values with new offsets so UI doesn't show stale data
            raw_p, raw_r = self._read_raw_angles()
            self._last_pitch = (raw_p - self.pitch_offset) * self.pitch_gain
            self._last_roll = (raw_r - self.roll_offset) * self.roll_gain
        finally:
            self._calibrating = False

    def _read_raw_angles(self):
        """
        Read raw pitch and roll from accelerometer.

        Returns:
            Tuple of (pitch, roll) in degrees
        """
        if self.simulation_mode or self.imu is None:
            return 0.0, 0.0

        with self._lock:
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
        # During calibration, return cached values to avoid I2C lock contention
        if self._calibrating:
            return self._last_pitch, self._last_roll

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

    def get_cached_angles(self):
        """
        Return last known pitch/roll without triggering an I2C read.
        Use this for UI polling to avoid bus contention with the gait loop.
        """
        return self._last_pitch, self._last_roll

    def start_background_reader(self, rate_hz=10):
        """Start background IMU reading thread at fixed rate."""
        if self._bg_running:
            return
        self._bg_running = True
        self._bg_thread = threading.Thread(
            target=self._bg_read_loop, args=(rate_hz,), daemon=True
        )
        self._bg_thread.start()
        print(f"IMU background reader started at {rate_hz}Hz")

    def stop_background_reader(self):
        """Stop background IMU reading thread."""
        self._bg_running = False
        if self._bg_thread:
            self._bg_thread.join(timeout=1.0)
            self._bg_thread = None
            print("IMU background reader stopped")

    def _bg_read_loop(self, rate_hz):
        """Background loop: read IMU at fixed rate, update cache.
        Detects stale/frozen data and triggers multi-stage recovery."""
        interval = 1.0 / rate_hz
        prev_pitch, prev_roll = None, None
        while self._bg_running:
            if not self._calibrating:
                try:
                    self.get_angles()
                    p, r = self._last_pitch, self._last_roll
                    # Detect frozen values (identical to 2 decimal places)
                    if prev_pitch is not None:
                        if round(p, 2) == round(prev_pitch, 2) and round(r, 2) == round(prev_roll, 2):
                            self._stale_count += 1
                        else:
                            self._stale_count = 0
                    prev_pitch, prev_roll = p, r
                except Exception:
                    self._stale_count += 1
                # Trigger recovery if stale too long
                if self._stale_count >= self._stale_threshold:
                    self._attempt_recovery()
                    self._stale_count = 0
                    prev_pitch, prev_roll = None, None
            time.sleep(interval)

    def _gpio_recover_bus(self):
        """Toggle SCL 9 times to free a stuck SDA line on software I2C bus.
        Standard I2C bus recovery: clocking SCL forces the slave to release SDA."""
        try:
            import RPi.GPIO as GPIO
            scl_pin, sda_pin = 27, 17  # Software I2C bus 3 pins

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(scl_pin, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.setup(sda_pin, GPIO.IN)

            # Clock SCL 9 times - slave releases SDA after completing its byte
            recovered = False
            for i in range(9):
                GPIO.output(scl_pin, GPIO.LOW)
                time.sleep(0.001)
                GPIO.output(scl_pin, GPIO.HIGH)
                time.sleep(0.001)
                if GPIO.input(sda_pin):  # SDA released
                    recovered = True
                    break

            # Send STOP condition: SDA low→high while SCL high
            GPIO.setup(sda_pin, GPIO.OUT)
            GPIO.output(sda_pin, GPIO.LOW)
            time.sleep(0.0005)
            GPIO.output(scl_pin, GPIO.HIGH)
            time.sleep(0.0005)
            GPIO.output(sda_pin, GPIO.HIGH)
            time.sleep(0.0005)

            GPIO.cleanup([scl_pin, sda_pin])
            time.sleep(0.1)  # Let i2c-gpio driver resync
            return recovered
        except Exception as e:
            print(f"GPIO bus recovery failed: {e}")
            return False

    def _attempt_recovery(self):
        """Multi-stage MPU6050 recovery after stale data detected."""
        self._recovery_count += 1
        print(f"IMU recovery attempt #{self._recovery_count}")

        bus_num = self._i2c_bus or 1

        # Stage 0: GPIO-level bus recovery for software I2C (bus 3)
        # Toggles SCL 9 times to free stuck SDA - must run BEFORE smbus2 attempts
        if bus_num == 3:
            if self._gpio_recover_bus():
                print(f"IMU recovery stage 0 (GPIO clock recovery): SDA released")
            else:
                print(f"IMU recovery stage 0 (GPIO clock recovery): SDA still stuck")

        # Stage 1: Device reset via register write (~200ms)
        try:
            import smbus2
            with smbus2.SMBus(bus_num) as bus:
                bus.write_byte_data(self._i2c_address, 0x6B, 0x80)  # DEVICE_RESET
                time.sleep(0.1)
                bus.write_byte_data(self._i2c_address, 0x6B, 0x00)  # Wake from sleep
                time.sleep(0.1)
                who = bus.read_byte_data(self._i2c_address, 0x75)    # WHO_AM_I
                if who == 0x68:
                    print(f"IMU recovery stage 1 (register reset on bus {bus_num}): OK")
                    return
        except Exception as e:
            print(f"IMU recovery stage 1 failed: {e}")

        # Stage 2: Reinitialize mpu6050 object (~500ms)
        try:
            from mpu6050 import mpu6050 as mpu6050_cls
            self.imu = mpu6050_cls(self._i2c_address, bus=bus_num)
            for _ in range(3):
                self.imu.get_accel_data()
                time.sleep(0.01)
            print(f"IMU recovery stage 2 (reinit on bus {bus_num}): OK")
            return
        except Exception as e:
            print(f"IMU recovery stage 2 failed: {e}")

        # Stage 3: All recovery failed
        print("IMU CRITICAL: all recovery stages failed, sensor may need power cycle")
        self.simulation_mode = True

    def get_health(self):
        """Get IMU health status for monitoring."""
        return {
            "available": self.is_available(),
            "simulation": self.simulation_mode,
            "stale_count": self._stale_count,
            "recovery_count": self._recovery_count,
            "bg_running": self._bg_running,
        }

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
