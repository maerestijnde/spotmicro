#!/usr/bin/env python3
"""
MicroSpot 180 Servo Kalibratie Script
Voor MG996R servo's met 180 graden range
"""
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import json
import time
from pathlib import Path

# Calibration file path (one level up from tools/)
CALIBRATION_FILE = Path(__file__).parent.parent / "calibration.json"

# Hardware init
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 50

# Servo config voor MG996R
SERVO_CONFIG = {
    "min_pulse": 500,
    "max_pulse": 2500,
    "actuation_range": 180  # CORRECT voor MG996R
}

# Channel mapping
CHANNELS = {
    "FL_hip": 0,  "FL_knee": 1,  "FL_ankle": 2,
    "FR_hip": 3,  "FR_knee": 4,  "FR_ankle": 5,
    "RL_hip": 6,  "RL_knee": 7,  "RL_ankle": 8,
    "RR_hip": 9,  "RR_knee": 10, "RR_ankle": 11
}

def create_servo(channel):
    return servo.Servo(
        pca.channels[channel],
        min_pulse=SERVO_CONFIG["min_pulse"],
        max_pulse=SERVO_CONFIG["max_pulse"],
        actuation_range=SERVO_CONFIG["actuation_range"]
    )

def set_angle(channel, angle):
    """Zet servo op specifieke hoek (0-180)"""
    angle = max(0, min(180, angle))
    srv = create_servo(channel)
    srv.angle = angle
    print(f"  Ch{channel}: {angle}")
    return angle

def all_to_center():
    """Zet alle servo's naar 90 (midden)"""
    print("\n=== ALLE SERVO'S NAAR 90 (MIDDEN) ===")
    for name, ch in CHANNELS.items():
        set_angle(ch, 90)
    print("\nAlle servo's staan nu op 90 (fysiek midden)")
    print("Controleer: staan de poten RECHT naar beneden?")

def calibrate_single(channel):
    """Interactieve kalibratie voor een servo"""
    print(f"\n=== KALIBRATIE CH{channel} ===")
    print("Commands: +/- (1), ++/-- (5), +++/--- (10), 90 (center), q (quit)")

    current = 90
    set_angle(channel, current)

    while True:
        cmd = input(f"  [{current}] > ").strip().lower()

        if cmd == 'q':
            return current
        elif cmd == '90':
            current = 90
        elif cmd == '+++':
            current = min(180, current + 10)
        elif cmd == '++':
            current = min(180, current + 5)
        elif cmd == '+':
            current = min(180, current + 1)
        elif cmd == '---':
            current = max(0, current - 10)
        elif cmd == '--':
            current = max(0, current - 5)
        elif cmd == '-':
            current = max(0, current - 1)
        elif cmd.isdigit():
            current = max(0, min(180, int(cmd)))

        set_angle(channel, current)

def full_calibration():
    """Complete kalibratie procedure"""
    print("\n" + "="*60)
    print("MICROSPOT 180 SERVO KALIBRATIE")
    print("="*60)

    # Stap 1: Alle naar midden
    all_to_center()
    input("\nDruk ENTER als je klaar bent om te beginnen...")

    calibrated = {}

    # Stap 2: Per servo kalibreren
    for name, ch in CHANNELS.items():
        print(f"\n--- {name.upper()} (Channel {ch}) ---")
        print("Beweeg de servo tot de poot in TAFELPOOT positie staat")
        print("(Been recht naar beneden, in lijn met body)")

        neutral = calibrate_single(ch)
        calibrated[ch] = neutral
        print(f"  -> {name} neutral = {neutral}")

    # Stap 3: Opslaan
    print("\n=== RESULTATEN ===")
    for name, ch in CHANNELS.items():
        print(f"  {name}: {calibrated[ch]}")

    save = input("\nOpslaan naar calibration.json? (y/n): ")
    if save.lower() == 'y':
        save_calibration(calibrated)

    return calibrated

def save_calibration(neutrals):
    """Sla kalibratie op naar calibration.json"""
    try:
        with open(CALIBRATION_FILE, 'r') as f:
            calib = json.load(f)
    except FileNotFoundError:
        calib = {
            "version": "1.1",
            "calibrated": False,
            "calibration_date": None,
            "robot_dimensions": {
                "body_length": 0.186,
                "body_width": 0.078,
                "hip_length": 0.055,
                "upper_leg_length": 0.1075,
                "lower_leg_length": 0.130
            },
            "neutral_pose": {
                "description": "Legs straight down, body level",
                "leg_height": 0.14
            },
            "servos": {}
        }

    # Update neutral angles
    for ch, neutral in neutrals.items():
        ch_str = str(ch)
        if ch_str not in calib['servos']:
            calib['servos'][ch_str] = {
                "channel": ch,
                "calibrated": False
            }
        calib['servos'][ch_str]['neutral_angle'] = neutral
        # Reset offset (wordt berekend als neutral - 90)
        calib['servos'][ch_str]['offset'] = neutral - 90
        calib['servos'][ch_str]['calibrated'] = True

    # Update directions (standaard SpotMicro convention)
    # Links = -1, Rechts = +1
    directions = {
        0: -1, 1: -1, 2: -1,   # FL
        3: +1, 4: +1, 5: +1,   # FR
        6: -1, 7: -1, 8: -1,   # RL
        9: +1, 10: +1, 11: +1  # RR
    }
    for ch, d in directions.items():
        ch_str = str(ch)
        if ch_str in calib['servos']:
            calib['servos'][ch_str]['direction'] = d

    calib['calibration_date'] = time.strftime("%Y-%m-%dT%H:%M:%S")

    with open(CALIBRATION_FILE, 'w') as f:
        json.dump(calib, f, indent=2)

    print(f"Calibration opgeslagen naar {CALIBRATION_FILE}!")

def verify_calibration():
    """Verificeer de huidige kalibratie"""
    try:
        with open(CALIBRATION_FILE) as f:
            c = json.load(f)
        print('\n=== HUIDIGE KALIBRATIE ===')
        for ch in range(12):
            ch_str = str(ch)
            if ch_str in c.get('servos', {}):
                s = c['servos'][ch_str]
                neutral = s.get('neutral_angle', 90)
                direction = s.get('direction', 1)
                valid = '(OK)' if 0 <= neutral <= 180 else '(ONGELDIG!)'
                calibrated = 'cal' if s.get('calibrated', False) else 'niet'
                label = s.get('label', f'Ch{ch}')
                print(f'Ch{ch:2d} {label:20} n={neutral:3} d={direction:+d} {valid} [{calibrated}]')
            else:
                print(f'Ch{ch:2d} (niet in file)')
    except FileNotFoundError:
        print("Geen calibration.json gevonden!")

if __name__ == "__main__":
    import sys

    print("="*60)
    print("  MICROSPOT 180 KALIBRATIE TOOL")
    print("  Voor MG996R servo's (180 graden range)")
    print("="*60)

    if len(sys.argv) > 1:
        if sys.argv[1] == "center":
            all_to_center()
        elif sys.argv[1] == "full":
            full_calibration()
        elif sys.argv[1] == "verify":
            verify_calibration()
        elif sys.argv[1].isdigit():
            calibrate_single(int(sys.argv[1]))
        else:
            print(f"Onbekend argument: {sys.argv[1]}")
    else:
        print("\nGebruik:")
        print("  python3 calibrate_180.py center  - Alle servo's naar 90")
        print("  python3 calibrate_180.py full    - Complete kalibratie")
        print("  python3 calibrate_180.py verify  - Controleer calibration.json")
        print("  python3 calibrate_180.py <ch>    - Kalibreer een channel (0-11)")

    pca.deinit()
