#!/usr/bin/env python3
"""
MicroSpot Auto-Calibration System
Collision-aware automated servo calibration with IMU feedback

Usage:
    python3 auto_calibrate.py [--leg FL|FR|RL|RR] [--joint hip|knee|ankle] [--all]

Features:
    - Collision-aware servo ranges (hip limited, knee/ankle sequential)
    - IMU-based collision detection
    - Walking quality metrics
    - Per-leg calibration workflow
"""

import argparse
import time
import json
import sys
import math
import requests
from pathlib import Path

# ============== CONFIGURATION ==============

API_URL = "http://localhost:8000"
CALIBRATION_FILE = Path(__file__).parent / "calibration.json"

# Servo range constraints for collision avoidance
SERVO_CONSTRAINTS = {
    "hip": {
        "safe_min": 45,     # Never go below this (collision risk)
        "safe_max": 135,    # Never go above this (collision risk)
        "sweep_step": 5,    # Degrees per step during sweep
        "sweep_delay": 0.1, # Seconds between steps
    },
    "knee": {
        "safe_min": 0,      # Full range OK
        "safe_max": 180,    # Full range OK
        "sweep_step": 5,
        "sweep_delay": 0.1,
        "requires": "ankle_forward",  # Must set ankle forward first
    },
    "ankle": {
        "safe_min": 0,      # Full range OK
        "safe_max": 180,    # Full range OK
        "sweep_step": 5,
        "sweep_delay": 0.1,
        "requires": "knee_neutral",   # Must set knee to neutral first
    },
}

# Leg configuration
LEG_CONFIG = {
    "FL": {"hip": 0, "knee": 1, "ankle": 2, "direction": -1, "ankle_forward": 0},
    "FR": {"hip": 3, "knee": 4, "ankle": 5, "direction": 1, "ankle_forward": 180},
    "RL": {"hip": 6, "knee": 7, "ankle": 8, "direction": -1, "ankle_forward": 0},
    "RR": {"hip": 9, "knee": 10, "ankle": 11, "direction": 1, "ankle_forward": 180},
}

# IMU collision detection thresholds
COLLISION_THRESHOLD = 15.0  # Degrees - sudden pitch/roll change indicates collision
IMU_SAMPLE_RATE = 0.05      # Seconds between IMU samples

# ============== API HELPERS ==============

def api_get(endpoint):
    """GET request to API"""
    try:
        resp = requests.get(f"{API_URL}{endpoint}", timeout=2)
        return resp.json() if resp.ok else None
    except:
        return None

def api_post(endpoint, data=None):
    """POST request to API"""
    try:
        resp = requests.post(f"{API_URL}{endpoint}", json=data or {}, timeout=2)
        return resp.json() if resp.ok else None
    except:
        return None

def set_servo(channel, angle):
    """Set a single servo to a specific angle"""
    return api_post(f"/api/servo/{channel}", {"angle": angle})

def get_imu_angles():
    """Get current IMU pitch/roll"""
    data = api_get("/api/balance/angles")
    if data:
        return data.get("pitch", 0), data.get("roll", 0)
    return 0, 0

def load_calibration():
    """Load current calibration from file"""
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE) as f:
            return json.load(f)
    return {"servos": {}}

def save_calibration(calibration):
    """Save calibration to file"""
    with open(CALIBRATION_FILE, 'w') as f:
        json.dump(calibration, f, indent=2)

# ============== COLLISION DETECTION ==============

class CollisionDetector:
    """Monitors IMU for sudden changes indicating collision"""

    def __init__(self, threshold=COLLISION_THRESHOLD):
        self.threshold = threshold
        self.last_pitch = 0
        self.last_roll = 0
        self.collision_detected = False

    def update(self):
        """Check for collision based on IMU change"""
        pitch, roll = get_imu_angles()

        pitch_delta = abs(pitch - self.last_pitch)
        roll_delta = abs(roll - self.last_roll)

        self.last_pitch = pitch
        self.last_roll = roll

        if pitch_delta > self.threshold or roll_delta > self.threshold:
            self.collision_detected = True
            return True, pitch, roll

        return False, pitch, roll

    def reset(self):
        """Reset collision state"""
        self.collision_detected = False
        self.last_pitch, self.last_roll = get_imu_angles()

# ============== CALIBRATION FUNCTIONS ==============

def set_safe_position(leg_id):
    """Move leg to safe starting position"""
    config = LEG_CONFIG[leg_id]
    print(f"  Setting {leg_id} to safe position...")

    # Hip to center
    set_servo(config["hip"], 90)
    time.sleep(0.2)

    # Knee to 90 (bent)
    set_servo(config["knee"], 90)
    time.sleep(0.2)

    # Ankle forward (collision-free position)
    set_servo(config["ankle"], config["ankle_forward"])
    time.sleep(0.3)

    print(f"  {leg_id} in safe position")

def sweep_find_neutral(leg_id, joint, min_angle, max_angle, collision_detector):
    """
    Sweep a joint through its range to find neutral position.
    Stops immediately if collision detected.

    Returns: (neutral_angle, success)
    """
    config = LEG_CONFIG[leg_id]
    channel = config[joint]
    constraints = SERVO_CONSTRAINTS[joint]

    step = constraints["sweep_step"]
    delay = constraints["sweep_delay"]

    print(f"\n  Sweeping {leg_id} {joint} ({min_angle}° to {max_angle}°)...")
    print(f"  Press Ctrl+C to stop and set neutral at current position")

    collision_detector.reset()
    current_angle = min_angle

    try:
        # Sweep from min to max
        while current_angle <= max_angle:
            set_servo(channel, current_angle)
            time.sleep(delay)

            # Check for collision
            collision, pitch, roll = collision_detector.update()
            if collision:
                print(f"\n  COLLISION DETECTED at {current_angle}°! (pitch={pitch:.1f}°, roll={roll:.1f}°)")
                print(f"  Returning to safe position...")
                set_safe_position(leg_id)
                return current_angle - step, False

            # Progress indicator
            sys.stdout.write(f"\r  Angle: {current_angle}° | IMU: pitch={pitch:.1f}°, roll={roll:.1f}°    ")
            sys.stdout.flush()

            current_angle += step

        print(f"\n  Sweep complete!")

    except KeyboardInterrupt:
        print(f"\n  Stopped at {current_angle}°")

    # Ask user for neutral position
    print(f"\n  Current servo at {current_angle}°")
    while True:
        try:
            user_input = input(f"  Enter neutral angle (or 'current' for {current_angle}): ").strip()
            if user_input.lower() == 'current' or user_input == '':
                neutral = current_angle
            else:
                neutral = int(user_input)

            if min_angle <= neutral <= max_angle:
                set_servo(channel, neutral)
                confirm = input(f"  Set {leg_id} {joint} neutral to {neutral}°? (y/n): ").strip().lower()
                if confirm == 'y':
                    return neutral, True
            else:
                print(f"  Invalid angle. Must be between {min_angle} and {max_angle}")
        except ValueError:
            print(f"  Invalid input. Enter a number or 'current'")
        except KeyboardInterrupt:
            print("\n  Cancelled")
            return 90, False

def calibrate_leg(leg_id, collision_detector):
    """
    Calibrate all joints of a single leg in collision-safe order:
    1. Hip (limited range 45-135°)
    2. Knee (full range, ankle must be forward)
    3. Ankle (full range, knee at neutral)
    """
    config = LEG_CONFIG[leg_id]
    calibration = load_calibration()

    print(f"\n{'='*50}")
    print(f"  CALIBRATING {leg_id} LEG")
    print(f"{'='*50}")

    # 1. Safe starting position
    set_safe_position(leg_id)
    time.sleep(0.5)

    results = {}

    # 2. Calibrate HIP (limited range - never go to extremes!)
    print(f"\n--- HIP (channel {config['hip']}) ---")
    print(f"  IMPORTANT: Hip range limited to 45-135° to prevent collision!")
    hip_neutral, success = sweep_find_neutral(
        leg_id, "hip",
        SERVO_CONSTRAINTS["hip"]["safe_min"],
        SERVO_CONSTRAINTS["hip"]["safe_max"],
        collision_detector
    )
    if success:
        results["hip"] = hip_neutral
        # Update calibration
        ch_str = str(config["hip"])
        if ch_str in calibration["servos"]:
            calibration["servos"][ch_str]["neutral_angle"] = hip_neutral
            calibration["servos"][ch_str]["calibrated"] = True

    # 3. Calibrate KNEE (full range, ankle stays forward)
    print(f"\n--- KNEE (channel {config['knee']}) ---")
    print(f"  Setting ankle to forward position for collision-free knee sweep...")
    set_servo(config["ankle"], config["ankle_forward"])
    time.sleep(0.3)

    knee_neutral, success = sweep_find_neutral(
        leg_id, "knee",
        SERVO_CONSTRAINTS["knee"]["safe_min"],
        SERVO_CONSTRAINTS["knee"]["safe_max"],
        collision_detector
    )
    if success:
        results["knee"] = knee_neutral
        ch_str = str(config["knee"])
        if ch_str in calibration["servos"]:
            calibration["servos"][ch_str]["neutral_angle"] = knee_neutral
            calibration["servos"][ch_str]["calibrated"] = True

    # 4. Calibrate ANKLE (full range, knee at neutral)
    print(f"\n--- ANKLE (channel {config['ankle']}) ---")
    print(f"  Setting knee to neutral position for collision-free ankle sweep...")
    set_servo(config["knee"], results.get("knee", 90))
    time.sleep(0.3)

    ankle_neutral, success = sweep_find_neutral(
        leg_id, "ankle",
        SERVO_CONSTRAINTS["ankle"]["safe_min"],
        SERVO_CONSTRAINTS["ankle"]["safe_max"],
        collision_detector
    )
    if success:
        results["ankle"] = ankle_neutral
        ch_str = str(config["ankle"])
        if ch_str in calibration["servos"]:
            calibration["servos"][ch_str]["neutral_angle"] = ankle_neutral
            calibration["servos"][ch_str]["calibrated"] = True

    # Save calibration
    save_calibration(calibration)
    print(f"\n  Calibration saved for {leg_id}: {results}")

    return results

# ============== WALKING QUALITY METRICS ==============

def measure_walking_quality(duration=5.0):
    """
    Measure walking quality using IMU variance.
    Lower variance = more stable walking.

    Returns: dict with quality metrics
    """
    print(f"\n  Measuring walking quality for {duration}s...")

    # Start walking
    api_post("/api/gait/start")
    time.sleep(0.5)

    # Collect IMU samples
    samples = []
    start_time = time.time()

    while time.time() - start_time < duration:
        pitch, roll = get_imu_angles()
        samples.append({"pitch": pitch, "roll": roll, "time": time.time() - start_time})
        time.sleep(IMU_SAMPLE_RATE)

    # Stop walking
    api_post("/api/gait/stop")
    time.sleep(0.5)

    # Calculate metrics
    if not samples:
        return {"error": "No samples collected"}

    pitches = [s["pitch"] for s in samples]
    rolls = [s["roll"] for s in samples]

    def variance(values):
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)

    def max_deviation(values):
        mean = sum(values) / len(values)
        return max(abs(x - mean) for x in values)

    metrics = {
        "samples": len(samples),
        "duration": duration,
        "pitch_variance": variance(pitches),
        "roll_variance": variance(rolls),
        "pitch_max_dev": max_deviation(pitches),
        "roll_max_dev": max_deviation(rolls),
        "pitch_mean": sum(pitches) / len(pitches),
        "roll_mean": sum(rolls) / len(rolls),
        "quality_score": 100 - (variance(pitches) + variance(rolls)) * 5,  # Higher = better
    }

    print(f"\n  Walking Quality Metrics:")
    print(f"    Pitch variance: {metrics['pitch_variance']:.2f}°")
    print(f"    Roll variance:  {metrics['roll_variance']:.2f}°")
    print(f"    Max pitch dev:  {metrics['pitch_max_dev']:.1f}°")
    print(f"    Max roll dev:   {metrics['roll_max_dev']:.1f}°")
    print(f"    Quality score:  {metrics['quality_score']:.1f}/100")

    return metrics

# ============== MAIN ==============

def main():
    parser = argparse.ArgumentParser(description="MicroSpot Auto-Calibration")
    parser.add_argument("--leg", choices=["FL", "FR", "RL", "RR"],
                        help="Calibrate specific leg")
    parser.add_argument("--all", action="store_true",
                        help="Calibrate all legs")
    parser.add_argument("--test-walk", action="store_true",
                        help="Test walking quality metrics")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="Backend API URL")
    args = parser.parse_args()

    global API_URL
    API_URL = args.api

    print("="*60)
    print("  MicroSpot Auto-Calibration System")
    print("  Collision-aware servo calibration with IMU feedback")
    print("="*60)

    # Check API connection
    status = api_get("/api/status")
    if not status:
        print("\nERROR: Cannot connect to backend API!")
        print(f"  Make sure microspot_app.py is running on {API_URL}")
        sys.exit(1)
    print(f"\nConnected to backend: {API_URL}")

    # Initialize collision detector
    collision_detector = CollisionDetector()

    if args.test_walk:
        # Test walking quality
        metrics = measure_walking_quality(duration=5.0)
        return

    if args.leg:
        # Calibrate single leg
        calibrate_leg(args.leg, collision_detector)

    elif args.all:
        # Calibrate all legs in order
        for leg in ["FL", "FR", "RL", "RR"]:
            calibrate_leg(leg, collision_detector)
            print(f"\n  {leg} complete. Press Enter to continue to next leg...")
            input()

    else:
        # Interactive menu
        print("\nOptions:")
        print("  1. Calibrate FL leg")
        print("  2. Calibrate FR leg")
        print("  3. Calibrate RL leg")
        print("  4. Calibrate RR leg")
        print("  5. Calibrate ALL legs")
        print("  6. Test walking quality")
        print("  q. Quit")

        while True:
            choice = input("\nSelect option: ").strip().lower()

            if choice == '1':
                calibrate_leg("FL", collision_detector)
            elif choice == '2':
                calibrate_leg("FR", collision_detector)
            elif choice == '3':
                calibrate_leg("RL", collision_detector)
            elif choice == '4':
                calibrate_leg("RR", collision_detector)
            elif choice == '5':
                for leg in ["FL", "FR", "RL", "RR"]:
                    calibrate_leg(leg, collision_detector)
            elif choice == '6':
                measure_walking_quality(duration=5.0)
            elif choice == 'q':
                break
            else:
                print("Invalid option")

    print("\nCalibration complete!")

if __name__ == "__main__":
    main()
