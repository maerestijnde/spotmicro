#!/usr/bin/env python3
import sys
from pathlib import Path

# Add parent directory (src/) to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from microspot_app import set_servo
import time

print("Hip direction test")
print("Zet robot veilig op")
input("Enter...")

ch = 0  # FL hip
print(f"Testing channel {ch}")

# Neutral
set_servo(ch, 90, True)
time.sleep(1)
input("Nu neutraal. Enter...")

# Low actual
set_servo(ch, 70, True)
time.sleep(0.5)
print("Logical 70 - kijk of poot naar voor of achter ging")
input("Enter...")

# High actual  
set_servo(ch, 110, True)
time.sleep(0.5)
print("Logical 110 - kijk of poot naar voor of achter ging")

set_servo(ch, 90, True)
