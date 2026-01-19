#!/usr/bin/env python3
"""Test walk met IMU balance correctie"""
import sys, time
sys.path.insert(0, '.')
from microspot_app import set_servo
from gait import GaitController

gait = GaitController(set_servo)
gait.set_params(cycle_time=0.8, step_height=25, step_length=15)

print("\n=== BALANCE WALK TEST ===")
print("1) Eerst ZONDER balance")
print("2) Dan MET balance\n")

input("Enter voor walk ZONDER balance...")
gait.start('forward')
time.sleep(5)
gait.stop()
time.sleep(1)

input("\nEnter voor walk MET balance...")
gait.enable_balance(True)
gait.start('forward')
time.sleep(5)
gait.stop()

print("\nDone!")
