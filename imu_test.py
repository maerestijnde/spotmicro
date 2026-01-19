#!/usr/bin/env python3
from mpu6050 import mpu6050
import math, time

imu = mpu6050(0x68)
print("MPU6050 Test - Ctrl+C stop")
try:
    while True:
        a = imu.get_accel_data()
        g = imu.get_gyro_data()
        pitch = math.atan2(a['y'], math.sqrt(a['x']**2 + a['z']**2)) * 57.3
        roll = math.atan2(-a['x'], a['z']) * 57.3
        print(f"\rPitch:{pitch:+5.1f} Roll:{roll:+5.1f} Gx:{g['x']:+5.1f}", end="")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nDone")
