#!/usr/bin/env python3
import sys
from pathlib import Path

# Add parent directory (src/) to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from microspot_app import set_servo
from gait import GaitController
import time

print("Single Step Test")
print("Zorg dat robot veilig staat!")
input("Enter om te starten...")

gait = GaitController(set_servo)
gait.set_params(
    cycle_time=2.0,
    step_height=25,
    step_length=12,
    speed=0.5
)

print("Executing single step forward...")
gait.single_step("forward")
print("Done!")
