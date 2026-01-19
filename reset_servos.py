#!/usr/bin/env python3
"""Standalone script to reset/disable all servos"""
import sys

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685

    print("Resetting PCA9685...")
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)

    # Optie 1: Alle PWM outputs naar 0
    for channel in range(16):
        pca.channels[channel].duty_cycle = 0

    # Optie 2: Deinit (reset de chip)
    pca.deinit()

    print("✓ Servos gereset - alle outputs uit")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
