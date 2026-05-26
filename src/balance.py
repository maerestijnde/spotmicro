#!/usr/bin/env python3
"""
Balance Controller for MicroSpot
Uses MPU6050 IMU for pitch/roll measurement and balance correction.
Implements complementary filter (accel + gyro fusion) and PID-style control.
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

    Uses MPU6050 accelerometer and gyroscope with a complementary filter
    to measure pitch and roll, then calculates leg angle corrections
    via PID-style control to maintain balance.
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
        self.balance_gain = 0.5  # Proportional gain for balance correction
        self.ki = 0.0            # Integral gain (disabled by default)
        self.kd = 0.0            # Derivative gain (disabled by default)
        self._integral_limit = 10.0  # Anti-windup clamp (degrees·s)

        # Pitch/roll sensitivity
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
        self._last_raw_pitch = 0.0  # Last valid raw accel reading
        self._last_raw_roll = 0.0
        self._alpha = 0.25  # Low-pass filter coefficient (0-1, higher = more responsive)

        # Complementary filter state
        self._fused_pitch = 0.0
        self._fused_roll = 0.0
        self._last_fused_time = time.time()
        self._complementary_alpha = 0.98  # Gyro trust factor

        # Gyro fallback state
        self._last_gyro_x = 0.0
        self._last_gyro_y = 0.0

        # PID state
        self._pitch_integral = 0.0
        self._roll_integral = 0.0
        self._last_pitch_error = 0.0
        self._last_roll_error = 0.0
        self._last_correction_time = time.time()

    # ------------------------------------------------------------------
    # Backward-compatible alias: kp -> balance_gain
    # ------------------------------------------------------------------
    @property
    def kp(self) -> float:
        """Backward-compatible alias for balance_gain."""
        return self.balance_gain

    @kp.setter
    def kp(self, value: float):
        self.balance_gain = value

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
            self._fused_pitch = raw_p
            self._fused_roll = raw_r
            self._last_pitch = (raw_p - self.pitch_offset) * self.pitch_gain
            self._last_roll = (raw_r - self.roll_offset) * self.roll_gain

            # Reset PID state after calibration
            self._pitch_integral = 0.0
            self._roll_integral = 0.0
            self._last_pitch_error = 0.0
            self._last_roll_error = 0.0
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

    def _read_gyro_rates(self):
        """
        Read gyroscope rates from MPU6050.

        Returns:
            Tuple of (gx, gy) in degrees/second
        """
        if self.simulation_mode or self.imu is None:
            return 0.0, 0.0

        with self._lock:
            try:
                # Try library method first
                gyro = self.imu.get_gyro_data()
                gx, gy = gyro['x'], gyro['y']
            except Exception:
                # Fallback: read raw registers 0x43-0x48
                try:
                    import smbus2
                    bus_num = self._i2c_bus or 1
                    with smbus2.SMBus(bus_num) as bus:
                        data = bus.read_i2c_block_data(self._i2c_address, 0x43, 6)

                    def _combine(high, low):
                        val = (high << 8) | low
                        if val > 32767:
                            val -= 65536
                        return val

                    raw_x = _combine(data[0], data[1])
                    raw_y = _combine(data[2], data[3])
                    raw_z = _combine(data[4], data[5])

                    # Default scale: ±250°/s = 131 LSB/(°/s)
                    gx = raw_x / 131.0
                    gy = raw_y / 131.0
                    # gz = raw_z / 131.0  # not used for pitch/roll
                except Exception:
                    return self._last_gyro_x, self._last_gyro_y

            # Guard against all-zeros bad reading
            if abs(gx) < 0.01 and abs(gy) < 0.01:
                return self._last_gyro_x, self._last_gyro_y

            self._last_gyro_x = gx
            self._last_gyro_y = gy
            return gx, gy

    def get_angles(self):
        """
        Get current pitch and roll angles (calibrated and filtered).
        Uses complementary filter to fuse accelerometer and gyroscope.

        Returns:
            Tuple of (pitch, roll) in degrees
        """
        # During calibration, return cached values to avoid I2C lock contention
        if self._calibrating:
            return self._last_pitch, self._last_roll

        # Read sensors
        accel_pitch, accel_roll = self._read_raw_angles()
        gyro_x, gyro_y = self._read_gyro_rates()

        # Compute dt for complementary filter
        now = time.time()
        dt = now - self._last_fused_time
        self._last_fused_time = now
        # Clamp dt to prevent huge jumps after pause
        dt = max(0.001, min(0.1, dt))

        # Complementary filter:
        #   angle = alpha * (angle + gyro_rate * dt) + (1 - alpha) * accel_angle
        self._fused_pitch = (
            self._complementary_alpha * (self._fused_pitch + gyro_y * dt)
            + (1.0 - self._complementary_alpha) * accel_pitch
        )
        self._fused_roll = (
            self._complementary_alpha * (self._fused_roll + gyro_x * dt)
            + (1.0 - self._complementary_alpha) * accel_roll
        )

        # Apply calibration offset and per-axis sensitivity
        pitch = (self._fused_pitch - self.pitch_offset) * self.pitch_gain
        roll = (self._fused_roll - self.roll_offset) * self.roll_gain

        # Light low-pass filter for additional smoothing
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
            "filter": "complementary",
            "balance_gain": round(self.balance_gain, 3),
            "ki": round(self.ki, 4),
            "kd": round(self.kd, 4),
        }

    def get_correction(self):
        """
        Calculate balance correction for each leg using PID-style control.

        Returns:
            Dict mapping leg_id to correction angle in degrees
            Positive = bend knee more, Negative = straighten knee
        """
        pitch, roll = self.get_angles()

        now = time.time()
        dt = now - self._last_correction_time
        self._last_correction_time = now
        dt = max(0.001, min(0.1, dt))

        # Errors relative to level (0°)
        pitch_error = pitch
        roll_error = roll

        # Proportional term
        pitch_p = pitch_error * self.balance_gain
        roll_p = roll_error * self.balance_gain

        # Integral term with anti-windup
        self._pitch_integral += pitch_error * dt
        self._roll_integral += roll_error * dt
        self._pitch_integral = max(-self._integral_limit, min(self._integral_limit, self._pitch_integral))
        self._roll_integral = max(-self._integral_limit, min(self._integral_limit, self._roll_integral))

        pitch_i = self._pitch_integral * self.ki
        roll_i = self._roll_integral * self.ki

        # Derivative term
        pitch_d = (pitch_error - self._last_pitch_error) / dt * self.kd
        roll_d = (roll_error - self._last_roll_error) / dt * self.kd

        self._last_pitch_error = pitch_error
        self._last_roll_error = roll_error

        pitch_total = pitch_p + pitch_i + pitch_d
        roll_total = roll_p + roll_i + roll_d

        corrections = {}

        # Front legs
        corrections['FL'] = -pitch_total - roll_total * 0.5
        corrections['FR'] = -pitch_total + roll_total * 0.5

        # Rear legs - NEGATIVE pitch correction (lift rear when tilting forward)
        # 0.5 factor makes rear legs less aggressive than front
        corrections['RL'] = -pitch_total * 0.5 - roll_total * 0.5
        corrections['RR'] = -pitch_total * 0.5 + roll_total * 0.5

        return corrections

    def set_balance_gain(self, gain: float):
        """
        Set proportional gain for balance correction.

        Args:
            gain: Proportional gain (0.0 to 2.0 typical)
        """
        self.balance_gain = max(0.0, min(2.0, gain))
        print(f"Balance gain set to {self.balance_gain}")

    def set_kp(self, kp):
        """
        Backward-compatible alias for set_balance_gain().

        Args:
            kp: Proportional gain (0.0 to 2.0 typical)
        """
        self.set_balance_gain(kp)

    def set_ki(self, ki: float):
        """
        Set integral gain for balance correction.

        Args:
            ki: Integral gain (0.0 to 1.0 typical)
        """
        self.ki = max(0.0, min(1.0, ki))
        print(f"Balance Ki set to {self.ki}")

    def set_kd(self, kd: float):
        """
        Set derivative gain for balance correction.

        Args:
            kd: Derivative gain (0.0 to 1.0 typical)
        """
        self.kd = max(0.0, min(1.0, kd))
        print(f"Balance Kd set to {self.kd}")

    def reset_pid(self):
        """Reset PID integral and derivative state."""
        self._pitch_integral = 0.0
        self._roll_integral = 0.0
        self._last_pitch_error = 0.0
        self._last_roll_error = 0.0
        print("Balance PID state reset")

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
