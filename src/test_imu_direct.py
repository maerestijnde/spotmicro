#!/usr/bin/env python3
"""Direct IMU test - same as imu_test.py"""
print("=== Direct IMU Test ===")

# Step 1: Check if mpu6050 package exists
print("\n1. Checking mpu6050 package...")
try:
    from mpu6050 import mpu6050
    print("   OK: mpu6050 package found")
except ImportError as e:
    print(f"   FAIL: {e}")
    print("   Install with: pip install mpu6050-raspberrypi")
    exit(1)

# Step 2: Try to initialize IMU
print("\n2. Initializing MPU6050 at 0x68...")
try:
    imu = mpu6050(0x68)
    print("   OK: MPU6050 initialized")
except Exception as e:
    print(f"   FAIL: {e}")
    exit(1)

# Step 3: Read accelerometer data
print("\n3. Reading accelerometer...")
try:
    accel = imu.get_accel_data()
    print(f"   OK: x={accel['x']:.2f}, y={accel['y']:.2f}, z={accel['z']:.2f}")
except Exception as e:
    print(f"   FAIL: {e}")
    exit(1)

# Step 4: Calculate pitch/roll
print("\n4. Calculating angles...")
import math
pitch = math.atan2(accel['y'], math.sqrt(accel['x']**2 + accel['z']**2)) * 57.3
roll = math.atan2(-accel['x'], accel['z']) * 57.3
print(f"   Pitch: {pitch:.1f} degrees")
print(f"   Roll: {roll:.1f} degrees")

print("\n=== IMU Test PASSED ===")
