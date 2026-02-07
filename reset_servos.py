#!/usr/bin/env python3
"""Standalone script to reset/disable all servos on dual PCA9685 setup"""
import sys

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685

    print("Resetting dual PCA9685 boards...")
    i2c = busio.I2C(board.SCL, board.SDA)

    # Initialize both PCA boards
    pca_front = PCA9685(i2c, address=0x41)  # Front legs (FL, FR)
    pca_rear = PCA9685(i2c, address=0x40)   # Rear legs (RL, RR)

    # Reset all PWM outputs on both boards (only channels 0-5 are used per board)
    print("  PCA @ 0x41 (front legs)...")
    for channel in range(6):
        pca_front.channels[channel].duty_cycle = 0

    print("  PCA @ 0x40 (rear legs)...")
    for channel in range(6):
        pca_rear.channels[channel].duty_cycle = 0

    # Deinit both boards
    pca_front.deinit()
    pca_rear.deinit()

    print("✓ Servos gereset - alle outputs uit (beide PCA boards)")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
