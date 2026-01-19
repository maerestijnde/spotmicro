#!/usr/bin/env python3
"""
Autotune All Servos - Calibreert alle 12 servo's (hip, knee, ankle) per poot
Gebaseerd op autotune_knee.py maar uitgebreid voor volledige robot calibratie
"""

import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import time
import select
import sys
import json
from pathlib import Path

# Hardware init
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

# Calibration file path (one level up from tools/)
CALIBRATION_FILE = Path(__file__).parent.parent / "calibration.json"

# Leg configuration
LEGS = {
    "1": ("FL", {"hip": 0,  "knee": 1,  "ankle": 2,  "side": "left"},  "Front Left"),
    "2": ("FR", {"hip": 3,  "knee": 4,  "ankle": 5,  "side": "right"}, "Front Right"),
    "3": ("RL", {"hip": 6,  "knee": 7,  "ankle": 8,  "side": "left"},  "Rear Left"),
    "4": ("RR", {"hip": 9,  "knee": 10, "ankle": 11, "side": "right"}, "Rear Right"),
}

# Side-specific settings
SIDE_CONFIG = {
    "left": {
        "ankle_forward": 0,      # Left ankle forward position
        "direction_hip": 1,      # Hip direction
        "direction_knee": -1,    # Knee direction (inverted for left)
        "direction_ankle": -1,   # Ankle direction (inverted for left)
    },
    "right": {
        "ankle_forward": 180,    # Right ankle forward position (180° servos)
        "direction_hip": 1,      # Hip direction
        "direction_knee": 1,     # Knee direction (normal for right)
        "direction_ankle": 1,    # Ankle direction (normal for right)
    }
}

# Servo objects cache
servos_cache = {}

def get_servo(channel):
    """Get or create servo object for channel"""
    if channel not in servos_cache:
        servos_cache[channel] = servo.Servo(
            pca.channels[channel],
            min_pulse=500,
            max_pulse=2500,
            actuation_range=180  # MG996R 180° servos
        )
    return servos_cache[channel]

def set_servo_angle(channel, angle):
    """Set servo to specific angle"""
    srv = get_servo(channel)
    srv.angle = max(0, min(180, angle))

def load_calibration():
    """Load existing calibration data"""
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE) as f:
            return json.load(f)
    return None

def save_calibration(data):
    """Save calibration data"""
    data["calibration_date"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(CALIBRATION_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\n  Calibration saved to {CALIBRATION_FILE}")

def wait_for_enter_or_sweep(start, end, servo_obj, step_delay=0.05):
    """
    Sweep servo from start to end, return angle when user presses ENTER
    Returns the angle where user stopped, or end angle if no stop
    """
    step = 1 if end > start else -1
    current = start

    while (step > 0 and current <= end) or (step < 0 and current >= end):
        servo_obj.angle = current
        time.sleep(step_delay)
        print(f"\r  Huidige hoek: {current}°   ", end="", flush=True)

        # Check for ENTER without blocking
        if select.select([sys.stdin], [], [], 0.0)[0]:
            sys.stdin.readline()
            print(f"\n  Gestopt op {current}°")
            return current

        current += step

    print(f"\n  Bereikt limiet {end}° zonder stop")
    return end

def tune_servo_interactive(channel, joint_type, leg_name, side):
    """
    Interactive tuning for a single servo
    Returns: (min_angle, max_angle, neutral_angle)
    """
    srv = get_servo(channel)
    config = SIDE_CONFIG[side]

    print(f"\n{'='*60}")
    print(f"CALIBRATIE: Channel {channel} - {leg_name} {joint_type.upper()}")
    print(f"{'='*60}")

    # Different start positions and instructions per joint type
    if joint_type == "hip":
        START_ANGLE = 90  # Midden van 180° range
        neutral_instruction = "heup RECHT naar buiten/binnen (loodrecht op body)"
    elif joint_type == "knee":
        START_ANGLE = 90  # Midden van 180° range
        neutral_instruction = "bovenbeen RECHT naar beneden (verticaal)"
    else:  # ankle
        START_ANGLE = 90  # Midden van 180° range
        neutral_instruction = "voet PARALLEL aan de grond"

    # Go to start position
    srv.angle = START_ANGLE
    time.sleep(0.5)

    input(f"\nServo staat op {START_ANGLE}°. Druk ENTER om te beginnen met sweep...")

    # === FIND MINIMUM (sweep naar 0°) ===
    print(f"\n--- ZOEKEN NAAR MINIMUM (richting 0°) ---")
    print("Druk ENTER zodra je fysieke weerstand voelt of de servo stopt!")

    srv.angle = START_ANGLE
    time.sleep(0.3)
    min_angle = wait_for_enter_or_sweep(START_ANGLE, 0, srv)

    # Return to start
    srv.angle = START_ANGLE
    time.sleep(0.5)

    # === FIND MAXIMUM (sweep naar 180°) ===
    print(f"\n--- ZOEKEN NAAR MAXIMUM (richting 180°) ---")
    print("Druk ENTER zodra je fysieke weerstand voelt of de servo stopt!")

    min_angle_found = min_angle
    max_angle = wait_for_enter_or_sweep(START_ANGLE, 180, srv)

    # === FIND NEUTRAL ===
    print(f"\n--- INSTELLEN NEUTRALE POSITIE ---")
    print(f"Doel: {neutral_instruction}")
    print("Gebruik: +/- (1°), ++/-- (10°), getal, of ENTER om te bevestigen")

    # Start at middle of range
    current = (min_angle + max_angle) // 2
    srv.angle = current

    while True:
        cmd = input(f"  Hoek: {current}° [+/-/++/--/getal/ENTER]: ").strip()

        if cmd == "":
            neutral_angle = current
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
            val = int(cmd)
            current = max(min_angle, min(max_angle, val))

        srv.angle = current

    print(f"\n  RESULTAAT {joint_type.upper()}:")
    print(f"    Min: {min_angle}°, Max: {max_angle}°, Neutraal: {neutral_angle}°")

    return min_angle, max_angle, neutral_angle

def calibrate_leg(leg_id, channels, leg_name, side):
    """
    Calibrate all 3 servos of a leg: HIP -> KNEE -> ANKLE

    Collision-free workflow:
    1. START: Hip=135°, Knee=135°, Ankle=forward (been gestrekt naar buiten)
    2. Calibrate HIP (andere servo's blijven)
    3. Calibrate KNEE (ankle blijft forward)
    4. Naar tafelpoot: hip+knee naar neutrale positie
    5. Calibrate ANKLE
    6. Terug naar startpositie
    """
    config = SIDE_CONFIG[side]
    results = {}

    print(f"\n{'#'*60}")
    print(f"# CALIBRATIE POOT: {leg_name} ({leg_id})")
    print(f"# Side: {side} | Channels: hip={channels['hip']}, knee={channels['knee']}, ankle={channels['ankle']}")
    print(f"{'#'*60}")

    # === START POSITIE (collision-free) ===
    print("\n[START] Veilige startpositie...")
    print(f"  Hip -> 90°, Knee -> 90°, Ankle -> {config['ankle_forward']}° (forward)")
    set_servo_angle(channels['hip'], 90)
    set_servo_angle(channels['knee'], 90)
    set_servo_angle(channels['ankle'], config['ankle_forward'])
    time.sleep(0.5)
    input("Druk ENTER als de poot veilig gepositioneerd is...")

    # === 1. HIP CALIBRATION ===
    print("\n[1/3] HIP CALIBRATIE")
    print("  (Knee=90°, Ankle=forward blijven staan)")

    hip_min, hip_max, hip_neutral = tune_servo_interactive(
        channels['hip'], "hip", leg_name, side
    )
    results['hip'] = {
        'min': hip_min, 'max': hip_max, 'neutral': hip_neutral,
        'direction': config['direction_hip']
    }

    # === 2. KNEE CALIBRATION ===
    print("\n[2/3] KNEE CALIBRATIE")
    print(f"  Hip -> {hip_neutral}° (net gecalibreerd neutraal)")
    print(f"  Ankle blijft op {config['ankle_forward']}° (forward)")
    set_servo_angle(channels['hip'], hip_neutral)
    time.sleep(0.3)

    knee_min, knee_max, knee_neutral = tune_servo_interactive(
        channels['knee'], "knee", leg_name, side
    )
    results['knee'] = {
        'min': knee_min, 'max': knee_max, 'neutral': knee_neutral,
        'direction': config['direction_knee']
    }

    # === NAAR TAFELPOOT STAND ===
    print("\n[TAFELPOOT] Voorbereiden voor ankle calibratie...")
    print(f"  Hip -> {hip_neutral}°, Knee -> {knee_neutral}° (beide neutraal)")
    set_servo_angle(channels['hip'], hip_neutral)
    set_servo_angle(channels['knee'], knee_neutral)
    time.sleep(0.5)
    input("Druk ENTER als de poot in tafelpoot-stand staat...")

    # === 3. ANKLE CALIBRATION ===
    print("\n[3/3] ANKLE CALIBRATIE")
    print(f"  Hip en Knee staan neutraal - nu ankle afstemmen")

    ankle_min, ankle_max, ankle_neutral = tune_servo_interactive(
        channels['ankle'], "ankle", leg_name, side
    )
    results['ankle'] = {
        'min': ankle_min, 'max': ankle_max, 'neutral': ankle_neutral,
        'direction': config['direction_ankle']
    }

    # === TERUG NAAR START VOOR VOLGENDE POOT ===
    print("\n[EINDE] Terug naar startpositie...")
    print(f"  Hip -> 90°, Knee -> 90°, Ankle -> {config['ankle_forward']}°")
    set_servo_angle(channels['hip'], 90)
    set_servo_angle(channels['knee'], 90)
    set_servo_angle(channels['ankle'], config['ankle_forward'])
    time.sleep(0.3)

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"POOT {leg_name} COMPLEET")
    print(f"{'='*60}")
    for joint, data in results.items():
        ch = channels[joint]
        print(f"  {joint.upper():6} (ch{ch:2d}): neutral={data['neutral']:3d}°, "
              f"range=[{data['min']:3d}°-{data['max']:3d}°], dir={data['direction']:+d}")

    return results

def update_calibration_file(leg_id, channels, results, side):
    """Update calibration.json with new values"""
    # Load existing or create new
    calib = load_calibration()
    if calib is None:
        calib = {
            "version": "1.0",
            "calibrated": False,
            "robot_dimensions": {
                "body_length": 0.186,
                "body_width": 0.078,
                "hip_length": 0.055,
                "upper_leg_length": 0.1075,
                "lower_leg_length": 0.130
            },
            "neutral_pose": {
                "description": "Legs straight down, body level - tafelpoot stand",
                "leg_height": 0.14
            },
            "servos": {}
        }

    # Joint labels
    joint_labels = {
        "hip": f"{leg_id} Hip",
        "knee": f"{leg_id} Knee",
        "ankle": f"{leg_id} Ankle"
    }

    # Leg names for labels
    leg_names = {"FL": "Front Left", "FR": "Front Right", "RL": "Rear Left", "RR": "Rear Right"}

    # Update each servo
    for joint, data in results.items():
        channel = channels[joint]
        calib["servos"][str(channel)] = {
            "channel": channel,
            "leg": leg_id,
            "joint": joint,
            "label": f"{leg_names[leg_id]} {joint.title()}",
            "offset": data['neutral'] - 90,
            "direction": data['direction'],
            "neutral_angle": data['neutral'],
            "min_angle": data['min'],
            "max_angle": data['max'],
            "safe_angle": data['neutral'],
            "calibrated": True,
            "notes": f"autotune_all.py - {time.strftime('%Y-%m-%d %H:%M')}"
        }

    # Check if all 12 servos are calibrated
    calibrated_count = sum(1 for ch in range(12) if str(ch) in calib["servos"]
                          and calib["servos"][str(ch)].get("calibrated", False))
    calib["calibrated"] = (calibrated_count == 12)

    save_calibration(calib)
    return calib

def test_neutrals(calib):
    """Test: set all servos to their neutral positions"""
    print(f"\n{'='*60}")
    print("TEST: Alle servo's naar neutrale positie")
    print(f"{'='*60}")

    for ch in range(12):
        ch_str = str(ch)
        if ch_str in calib["servos"]:
            neutral = calib["servos"][ch_str]["neutral_angle"]
            label = calib["servos"][ch_str]["label"]
            set_servo_angle(ch, neutral)
            print(f"  Ch{ch:2d} ({label:<20}): {neutral}°")
        else:
            set_servo_angle(ch, 90)
            print(f"  Ch{ch:2d} (niet gecalibreerd): 90° (default)")

    print(f"{'='*60}")

def calibrate_single_servo(channel):
    """Calibrate a single servo by channel number (collision-free)"""
    # Find which leg and joint this channel belongs to
    leg_id = None
    joint_type = None
    side = None

    for key, (lid, channels, name) in LEGS.items():
        if channel == channels['hip']:
            leg_id, joint_type, side = lid, 'hip', channels['side']
            leg_name = name
            break
        elif channel == channels['knee']:
            leg_id, joint_type, side = lid, 'knee', channels['side']
            leg_name = name
            break
        elif channel == channels['ankle']:
            leg_id, joint_type, side = lid, 'ankle', channels['side']
            leg_name = name
            break

    if leg_id is None:
        print(f"Channel {channel} niet gevonden in leg configuratie!")
        return None

    config = SIDE_CONFIG[side]

    # Get channels for this leg
    for key, (lid, channels, name) in LEGS.items():
        if lid == leg_id:
            leg_channels = channels
            break

    # Prepare other servos for this calibration (collision-free)
    print(f"\nVoorbereiding voor {leg_name} {joint_type.upper()} (ch{channel})...")

    if joint_type == 'hip':
        # Hip: zet knee=90, ankle=forward (been gestrekt naar buiten)
        print(f"  Knee -> 90°, Ankle -> {config['ankle_forward']}° (forward)")
        set_servo_angle(leg_channels['knee'], 90)
        set_servo_angle(leg_channels['ankle'], config['ankle_forward'])
    elif joint_type == 'knee':
        # Knee: zet ankle=forward (been gestrekt)
        print(f"  Ankle -> {config['ankle_forward']}° (forward)")
        set_servo_angle(leg_channels['ankle'], config['ankle_forward'])
    elif joint_type == 'ankle':
        # Ankle: zet knee naar neutral (tafelpoot stand)
        calib = load_calibration()
        knee_ch = str(leg_channels['knee'])
        hip_ch = str(leg_channels['hip'])

        # Haal hip en knee neutrals op
        if calib and hip_ch in calib.get('servos', {}):
            hip_neutral = calib['servos'][hip_ch].get('neutral_angle', 90)
        else:
            hip_neutral = 90
        if calib and knee_ch in calib.get('servos', {}):
            knee_neutral = calib['servos'][knee_ch].get('neutral_angle', 90)
        else:
            knee_neutral = 90

        print(f"  Hip -> {hip_neutral}°, Knee -> {knee_neutral}° (tafelpoot stand)")
        set_servo_angle(leg_channels['hip'], hip_neutral)
        set_servo_angle(leg_channels['knee'], knee_neutral)

    time.sleep(0.5)
    input("Druk ENTER als de poot veilig gepositioneerd is...")

    # Run the tuning
    min_angle, max_angle, neutral_angle = tune_servo_interactive(
        channel, joint_type, leg_name, side
    )

    # Save to calibration file
    results = {
        joint_type: {
            'min': min_angle,
            'max': max_angle,
            'neutral': neutral_angle,
            'direction': config[f'direction_{joint_type}'] if joint_type != 'hip' else config['direction_hip']
        }
    }

    # Update just this servo in calibration
    calib = load_calibration()
    if calib is None:
        calib = {
            "version": "1.0",
            "calibrated": False,
            "robot_dimensions": {
                "body_length": 0.186,
                "body_width": 0.078,
                "hip_length": 0.055,
                "upper_leg_length": 0.1075,
                "lower_leg_length": 0.130
            },
            "neutral_pose": {
                "description": "Legs straight down, body level - tafelpoot stand",
                "leg_height": 0.185
            },
            "servos": {}
        }

    leg_names = {"FL": "Front Left", "FR": "Front Right", "RL": "Rear Left", "RR": "Rear Right"}
    direction = config[f'direction_{joint_type}'] if joint_type != 'hip' else config['direction_hip']

    calib["servos"][str(channel)] = {
        "channel": channel,
        "leg": leg_id,
        "joint": joint_type,
        "label": f"{leg_names[leg_id]} {joint_type.title()}",
        "offset": neutral_angle - 90,
        "direction": direction,
        "neutral_angle": neutral_angle,
        "min_angle": min_angle,
        "max_angle": max_angle,
        "safe_angle": neutral_angle,
        "calibrated": True,
        "notes": f"autotune_all.py - {time.strftime('%Y-%m-%d %H:%M')}"
    }

    save_calibration(calib)
    return calib

def print_servo_menu():
    """Print servo selection menu"""
    print("\n" + "="*60)
    print("SERVO OVERZICHT")
    print("="*60)
    print(f"{'Ch':<4} {'Poot':<6} {'Joint':<8} {'Label':<22}")
    print("-"*60)

    for key, (leg_id, channels, name) in LEGS.items():
        print(f"{channels['hip']:<4} {leg_id:<6} {'hip':<8} {name} Hip")
        print(f"{channels['knee']:<4} {leg_id:<6} {'knee':<8} {name} Knee")
        print(f"{channels['ankle']:<4} {leg_id:<6} {'ankle':<8} {name} Ankle")
    print("="*60)

def main():
    print("="*60)
    print("  AUTOTUNE ALL SERVOS - MicroSpot Calibratie Tool")
    print("="*60)
    print()
    print("Kies modus:")
    print("  s) SERVO - calibreer 1 servo (channel 0-11)")
    print("  l) LEG   - calibreer hele poot (hip->knee->ankle)")
    print("  a) ALL   - calibreer alle 12 servo's")
    print("  t) TEST  - zet alle servo's naar neutrale positie")
    print("  r) RAW   - zet alle servo's naar 135° (raw test)")
    print("  q) Quit")
    print()

    mode = input("Modus [s/l/a/t/r/q]: ").strip().lower()

    if mode == 'q':
        print("Bye!")
        pca.deinit()
        sys.exit(0)

    if mode == 'r':
        print("\nAlle servo's naar 90° (raw/midden)...")
        for ch in range(12):
            set_servo_angle(ch, 90)
            print(f"  Ch{ch}: 90°")
        input("\nDruk ENTER om af te sluiten...")
        pca.deinit()
        sys.exit(0)

    if mode == 't':
        calib = load_calibration()
        if calib:
            test_neutrals(calib)
        else:
            print("Geen calibration.json gevonden!")
        pca.deinit()
        sys.exit(0)

    if mode == 's':
        # Single servo mode
        print_servo_menu()
        try:
            channel = int(input("\nChannel nummer [0-11]: ").strip())
            if channel < 0 or channel > 11:
                print("Ongeldig channel!")
                pca.deinit()
                sys.exit(1)
        except ValueError:
            print("Ongeldig nummer!")
            pca.deinit()
            sys.exit(1)

        calibrate_single_servo(channel)

        # Show result
        calib = load_calibration()
        if calib and str(channel) in calib.get("servos", {}):
            s = calib["servos"][str(channel)]
            print(f"\n{'='*60}")
            print(f"RESULTAAT Channel {channel}:")
            print(f"  Neutral: {s['neutral_angle']}°")
            print(f"  Range: [{s['min_angle']}° - {s['max_angle']}°]")
            print(f"  Direction: {s['direction']}")
            print(f"  Offset: {s['offset']}")
            print(f"{'='*60}")

        pca.deinit()
        sys.exit(0)

    if mode == 'l':
        # Leg mode
        print("\nSelecteer poot:")
        for key, (leg_id, channels, name) in LEGS.items():
            print(f"  {key}) {name} ({leg_id})")

        choice = input("\nKeuze [1-4]: ").strip()
        if choice not in LEGS:
            print("Ongeldige keuze!")
            pca.deinit()
            sys.exit(1)

        legs_to_calibrate = [choice]

    elif mode == 'a':
        # All legs mode
        legs_to_calibrate = ["1", "2", "3", "4"]

    else:
        print("Ongeldige modus!")
        pca.deinit()
        sys.exit(1)

    # Calibrate selected legs
    final_calib = None
    for leg_key in legs_to_calibrate:
        leg_id, channels, leg_name = LEGS[leg_key]
        side = channels['side']

        results = calibrate_leg(leg_id, channels, leg_name, side)
        final_calib = update_calibration_file(leg_id, channels, results, side)

        if len(legs_to_calibrate) > 1 and leg_key != legs_to_calibrate[-1]:
            cont = input(f"\nDoorgaan naar volgende poot? [Y/n]: ").strip().lower()
            if cont == 'n':
                break

    # Final test
    if final_calib:
        print(f"\n{'#'*60}")
        print("# CALIBRATIE COMPLEET")
        print(f"{'#'*60}")

        test_choice = input("\nWil je alle servo's naar hun neutrale positie zetten? [Y/n]: ").strip().lower()
        if test_choice != 'n':
            test_neutrals(final_calib)

    # Summary
    print(f"\n{'='*60}")
    print("SAMENVATTING CALIBRATION.JSON")
    print(f"{'='*60}")

    calib = load_calibration()
    if calib:
        calibrated = sum(1 for ch in range(12) if str(ch) in calib.get("servos", {})
                        and calib["servos"][str(ch)].get("calibrated", False))
        print(f"Gecalibreerde servo's: {calibrated}/12")
        print(f"Volledig gecalibreerd: {'Ja' if calibrated == 12 else 'Nee'}")

        print(f"\n{'Ch':<4} {'Label':<22} {'Neutral':<9} {'Range':<15} {'Dir':<5}")
        print("-" * 60)
        for ch in range(12):
            ch_str = str(ch)
            if ch_str in calib.get("servos", {}):
                s = calib["servos"][ch_str]
                if s.get("calibrated"):
                    print(f"{ch:<4} {s['label']:<22} {s['neutral_angle']:>3}°     "
                          f"[{s['min_angle']:>3}°-{s['max_angle']:>3}°]    {s['direction']:+d}")
                else:
                    print(f"{ch:<4} {s.get('label', 'Unknown'):<22} -- niet gecalibreerd --")
            else:
                print(f"{ch:<4} {'<niet in file>':<22}")

    print(f"\n{'='*60}")
    print("Done!")
    pca.deinit()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAfgebroken door gebruiker")
        pca.deinit()
        sys.exit(0)
