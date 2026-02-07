#!/usr/bin/env python3
"""Autotune voor knie servo - vindt fysieke limieten"""

import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import time
import select
import sys

# Hardware init - Dual PCA9685 setup
i2c = busio.I2C(board.SCL, board.SDA)
pca_front = PCA9685(i2c, address=0x41)  # Front legs (FL, FR) - channels 0-5
pca_front.frequency = 50
pca_rear = PCA9685(i2c, address=0x40)   # Rear legs (RL, RR) - channels 0-5
pca_rear.frequency = 50


def get_pca_and_channel(logical_channel: int):
    """
    Map logical channel (0-11) to PCA board and physical channel.

    Logical channels 0-5 (FL, FR) -> PCA @ 0x41, physical channels 0-5
    Logical channels 6-11 (RL, RR) -> PCA @ 0x40, physical channels 0-5
    """
    if logical_channel < 6:
        return pca_front, logical_channel
    else:
        return pca_rear, logical_channel - 6


def create_servo(channel):
    """Create servo object for logical channel (0-11)"""
    pca_board, physical_channel = get_pca_and_channel(channel)
    return servo.Servo(pca_board.channels[physical_channel], min_pulse=500, max_pulse=2500, actuation_range=180)


# Knie servo channels met bijbehorende enkel en enkel forward positie
# (knie_ch, enkel_ch, enkel_forward_angle, naam)
KNEES = {
    "1": (1, 2, 0, "FL Knee - Front Left"),       # FL enkel: 0 = forward
    "2": (4, 5, 180, "FR Knee - Front Right"),    # FR enkel: 180 = forward (180° servos)
    "3": (7, 8, 0, "RL Knee - Rear Left"),        # RL enkel: 0 = forward
    "4": (10, 11, 180, "RR Knee - Rear Right"),   # RR enkel: 180 = forward (180° servos)
}

print("=== AUTOTUNE KNIE SERVO ===")
print()
print("Selecteer welke knie:")
for key, (knee_ch, ankle_ch, ankle_fwd, name) in KNEES.items():
    print(f"  {key}) Channel {knee_ch}: {name}")
print()

choice = input("Keuze [1-4]: ").strip()
if choice not in KNEES:
    print("Ongeldige keuze!")
    pca.deinit()
    sys.exit(1)

SERVO_CHANNEL, ANKLE_CHANNEL, ANKLE_FORWARD, KNEE_NAME = KNEES[choice]

# Create servo objects using dual PCA mapping
srv = create_servo(SERVO_CHANNEL)
ankle_srv = create_servo(ANKLE_CHANNEL)

print()
print(f"=== AUTOTUNE SERVO {SERVO_CHANNEL} ({KNEE_NAME}) ===")
print()
print("Dit script vindt de fysieke limieten van de servo.")
print("Druk ENTER om te stoppen bij elke limiet.")
print()

# Zet enkel volledig naar voor
print(f"Enkel (channel {ANKLE_CHANNEL}) naar {ANKLE_FORWARD}° (volledig forward)...")
ankle_srv.angle = ANKLE_FORWARD
time.sleep(0.3)

# Start knie op 90° raw (midden van 180° range)
START_ANGLE = 90
srv.angle = START_ANGLE
time.sleep(0.5)

input(f"Knie staat op {START_ANGLE}° raw, enkel op {ANKLE_FORWARD}°. Druk ENTER om te beginnen...")

# === VIND MINIMUM (naar 0°) ===
print("\n--- ZOEKEN NAAR MINIMUM ---")
print("Servo gaat langzaam naar 0°...")
print("Druk ENTER zodra de servo fysiek stopt of je weerstand voelt!")

current = START_ANGLE
min_angle = 0

try:
    while current > 0:
        srv.angle = current
        time.sleep(0.05)
        print(f"\r  Huidige hoek: {current}°   ", end="", flush=True)

        if select.select([sys.stdin], [], [], 0.0)[0]:
            sys.stdin.readline()
            min_angle = current
            print(f"\n  ✓ MINIMUM gevonden: {min_angle}°")
            break

        current -= 1
    else:
        min_angle = 0
        print(f"\n  Bereikt 0° zonder stop - minimum = 0°")

except KeyboardInterrupt:
    min_angle = current
    print(f"\n  Gestopt op {min_angle}°")

# Terug naar start
srv.angle = START_ANGLE
time.sleep(0.5)

# === VIND MAXIMUM (naar 180°) ===
print("\n--- ZOEKEN NAAR MAXIMUM ---")
print("Servo gaat langzaam naar 180°...")
print("Druk ENTER zodra de servo fysiek stopt of je weerstand voelt!")

current = START_ANGLE
max_angle = 180

try:
    while current < 180:
        srv.angle = current
        time.sleep(0.05)
        print(f"\r  Huidige hoek: {current}°   ", end="", flush=True)

        if select.select([sys.stdin], [], [], 0.0)[0]:
            sys.stdin.readline()
            max_angle = current
            print(f"\n  ✓ MAXIMUM gevonden: {max_angle}°")
            break

        current += 1
    else:
        max_angle = 180
        print(f"\n  Bereikt 180° zonder stop - maximum = 180°")

except KeyboardInterrupt:
    max_angle = current
    print(f"\n  Gestopt op {max_angle}°")

# === VIND NEUTRAAL ===
print("\n--- INSTELLEN NEUTRALE POSITIE ---")
print("Gebruik +/- om de servo te bewegen, ENTER als been recht naar beneden hangt")

current = (min_angle + max_angle) // 2
srv.angle = current

while True:
    cmd = input(f"  Hoek: {current}° [+/-/++/--/getal/ENTER]: ").strip()

    if cmd == "":
        neutral = current
        break
    elif cmd == "+":
        current = min(max_angle, current + 1)
    elif cmd == "-":
        current = max(min_angle, current - 1)
    elif cmd == "++":
        current = min(max_angle, current + 10)
    elif cmd == "--":
        current = max(min_angle, current - 10)
    elif cmd.lstrip('-').isdigit():
        current = max(min_angle, min(max_angle, int(cmd)))

    srv.angle = current

# === RESULTAAT ===
print("\n" + "=" * 50)
print(f"AUTOTUNE RESULTAAT SERVO {SERVO_CHANNEL} ({KNEE_NAME})")
print("=" * 50)
print(f"  Fysiek minimum:  {min_angle}°")
print(f"  Fysiek maximum:  {max_angle}°")
print(f"  Neutrale positie: {neutral}°")
print(f"  Totale range:    {max_angle - min_angle}°")
print()
print("Aanbevolen calibration.json waarden:")
print(f'''
    "{SERVO_CHANNEL}": {{
      "neutral_angle": {neutral},
      "min_angle": {min_angle},
      "max_angle": {max_angle},
      "direction": 1,
      "offset": {neutral - 90}
    }}
''')

pca_front.deinit()
pca_rear.deinit()
print("Done!")
