#!/usr/bin/env python3
"""
MicroSpot Control v2.0 - With Spot Micro Kinematics Integration
Complete quadruped robot control with proper IK/FK
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import signal
import sys
import atexit
import json
import time
import numpy as np
from pathlib import Path
from math import degrees, radians, cos, pi
import datetime
import logging
import os

# ============== LOGGING SETUP ==============
# Configurable via environment variables:
#   LOG_LEVEL=INFO (default) - main application
#   LOG_LEVEL_GAIT=WARNING   - gait controller
#   LOG_LEVEL_SERVO=WARNING  - servo operations
#   LOG_LEVEL_IMU=WARNING    - IMU/balance
#   LOG_LEVEL_API=INFO       - API requests

def setup_logging():
    """Configure structured logging with named loggers per module"""
    # Default log level from environment
    default_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Custom formatter with module name
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Allow all, filter per handler
    root.addHandler(console)

    # Named loggers with configurable levels
    loggers = {
        "microspot": os.environ.get("LOG_LEVEL", default_level),
        "microspot.gait": os.environ.get("LOG_LEVEL_GAIT", "WARNING"),
        "microspot.servo": os.environ.get("LOG_LEVEL_SERVO", "WARNING"),
        "microspot.imu": os.environ.get("LOG_LEVEL_IMU", "WARNING"),
        "microspot.api": os.environ.get("LOG_LEVEL_API", "INFO"),
        "microspot.init": os.environ.get("LOG_LEVEL", default_level),
    }

    for name, level in loggers.items():
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Suppress noisy uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logging.getLogger("microspot")

# Initialize logging
log = setup_logging()
log_init = logging.getLogger("microspot.init")
log_servo = logging.getLogger("microspot.servo")
log_gait = logging.getLogger("microspot.gait")
log_imu = logging.getLogger("microspot.imu")
log_api = logging.getLogger("microspot.api")

# Import gait controller
try:
    from gait import GaitController, DEFAULT_GAIT_PARAMS
    GAIT_AVAILABLE = True
    log_init.info("Gait module loaded")
except Exception as e:
    GAIT_AVAILABLE = False
    log_init.warning(f"Gait module not available: {e}")

# Import stability monitor
try:
    from stability_monitor import StabilityMonitor, StabilityState, StabilityThresholds
    STABILITY_AVAILABLE = True
    log_init.info("Stability monitor loaded")
except Exception as e:
    STABILITY_AVAILABLE = False
    log_init.warning(f"Stability monitor not available: {e}")

# Import Spot Micro Kinematics
try:
    from kinematics.spot_micro_stick_figure import SpotMicroStickFigure
    KINEMATICS_AVAILABLE = True
    log_init.info("Spot Micro Kinematics loaded")
except Exception as e:
    KINEMATICS_AVAILABLE = False
    log_init.warning(f"Kinematics not available: {e}")

# Hardware initialization
try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo

    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 50
    HW = True
    log_init.info("Hardware initialized (PCA9685)")
except Exception as e:
    HW = False
    pca = None
    log_init.warning("No hardware - simulation mode")

# Configuration
BASE_DIR = Path(__file__).parent

SERVO_PARAMS = {
    "min_pulse": 500,
    "max_pulse": 2500,
    "actuation_range": 180,  # MG996R 180° servo's - CORRECT
    "frequency": 50
}

# Spot Micro dimensions (in meters) - KDY0523/mike4192 measurements
# Source: https://github.com/mike4192/spot_micro_kinematics_python
SPOT_CONFIG = {
    "body_length": 0.186,      # 186mm (front-to-back hip distance)
    "body_width": 0.078,       # 78mm (side-to-side hip distance)
    "hip_length": 0.055,       # 55mm (hip/shoulder segment)
    "upper_leg_length": 0.1075, # 107.5mm (upper leg)
    "lower_leg_length": 0.130  # 130mm (lower leg)
}

# Quadruped configuration
QUAD_CONFIG = {
    "FL": {"name": "Front Left", "channels": [0, 1, 2], "color": "#ff4444", "position": [-60, 10, 60]},
    "FR": {"name": "Front Right", "channels": [3, 4, 5], "color": "#44ff44", "position": [60, 10, 60]},
    "RL": {"name": "Rear Left", "channels": [6, 7, 8], "color": "#4444ff", "position": [-60, 10, -60]},
    "RR": {"name": "Rear Right", "channels": [9, 10, 11], "color": "#ffaa44", "position": [60, 10, -60]}
}

# Servo state
servos = {}
servo_angles = {i: 90 for i in range(16)}

# Calibration system
class CalibrationProfile:
    """Manages servo calibration data with offsets, directions, and limits"""

    def __init__(self):
        self.version = "1.1"  # Updated for KDY0523 dimensions
        self.calibrated = False
        self.calibration_date = None
        self.robot_dimensions = SPOT_CONFIG.copy()
        self.neutral_pose = {
            "description": "Legs straight down, body level",
            "leg_height": 0.14
        }
        self.servos = {}

        # Initialize with defaults for all servos
        for leg_id, config in QUAD_CONFIG.items():
            for joint_idx, channel in enumerate(config["channels"]):
                joint_name = ["hip", "knee", "ankle"][joint_idx]
                self.servos[channel] = {
                    "channel": channel,
                    "leg": leg_id,
                    "joint": joint_name,
                    "label": f"{config['name']} {joint_name.title()}",
                    "offset": 0,
                    "direction": 1,
                    "neutral_angle": 90,
                    "min_angle": 0,
                    "max_angle": 180,  # MG996R 180° servo's
                    "safe_angle": 90,
                    "calibrated": False,
                    "notes": ""
                }

    def apply_to_angle(self, channel, angle):
        """Apply calibration to convert commanded angle to actual servo angle"""
        if channel not in self.servos:
            return angle

        servo = self.servos[channel]
        # Apply direction and neutral offset
        # neutral_angle already contains the calibrated center point
        # We calculate the delta from logical 90° and apply direction
        delta = angle - 90  # How far from logical center
        calibrated = servo["neutral_angle"] + (servo["direction"] * delta)

        # Clamp to safe limits
        calibrated = max(servo["min_angle"], min(servo["max_angle"], calibrated))
        return calibrated

    def is_fully_calibrated(self):
        """Check if all servos are calibrated"""
        return all(s["calibrated"] for s in self.servos.values() if s["channel"] < 12)

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            "version": self.version,
            "calibrated": self.is_fully_calibrated(),
            "calibration_date": self.calibration_date,
            "robot_dimensions": self.robot_dimensions,
            "neutral_pose": self.neutral_pose,
            "servos": self.servos
        }

    @classmethod
    def from_dict(cls, data):
        """Create from dictionary (JSON deserialization)"""
        profile = cls()
        profile.version = data.get("version", "1.0")
        profile.calibrated = data.get("calibrated", False)
        profile.calibration_date = data.get("calibration_date")
        profile.robot_dimensions = data.get("robot_dimensions", profile.robot_dimensions)
        profile.neutral_pose = data.get("neutral_pose", profile.neutral_pose)
        servos_data = data.get("servos", {})
        # Convert string keys to integers
        profile.servos = {int(k): v for k, v in servos_data.items()}
        return profile

calibration = None

# Kinematics model
spot_model = None
body_state = {"x": 0, "y": 0.14, "z": 0, "phi": 0, "theta": 0, "psi": 0}

# Gait controller
gait_controller = None

# Stability monitor
stability_monitor = None

# Custom poses storage
custom_poses = {}

def load_custom_poses():
    """Load custom poses from file"""
    global custom_poses
    poses_file = BASE_DIR / "custom_poses.json"

    if poses_file.exists():
        try:
            with open(poses_file) as f:
                custom_poses = json.load(f)
            print(f"✓ Loaded {len(custom_poses)} custom poses")
        except Exception as e:
            print(f"✗ Error loading custom poses: {e}")
            custom_poses = {}
    else:
        custom_poses = {}
        print("⚠ No custom poses file found")

def save_custom_poses():
    """Save custom poses to file"""
    poses_file = BASE_DIR / "custom_poses.json"
    with open(poses_file, 'w') as f:
        json.dump(custom_poses, f, indent=2)
    print(f"✓ Custom poses saved ({len(custom_poses)} poses)")

# Preset poses (kinematics-based with fallback angles)
# Fallback angles: [FL_hip, FL_knee, FL_ankle, FR_hip, FR_knee, FR_ankle, RL_hip, RL_knee, RL_ankle, RR_hip, RR_knee, RR_ankle]
# Based on working gait stand: knee=50 (90-40), ankle=142 (90+52)
# All legs now symmetric (removed rear ankle compensation)
POSES = {
    "neutral": {
        "type": "calibrated_neutral",
        "description": "Table pose - legs straight down (140mm height)"
    },
    "stand": {
        "type": "body_state",
        "body_height": 0.10,
        "body_angles": {"phi": 0, "theta": 0, "psi": 0},
        "description": "Standing - body lowered, legs bent",
        # All legs symmetric
        "fallback_angles": [90, 50, 142, 90, 50, 142, 90, 50, 142, 90, 50, 142]
    },
    "sit": {
        "type": "body_state",
        "body_height": 0.06,
        "body_angles": {"phi": 0, "theta": -0.2, "psi": 0},
        "description": "Sitting - front high, rear flat on ground",
        # Front: knee=80, ankle=105. Rear: knee=5, ankle=178 (maximum possible, butt flat)
        "fallback_angles": [90, 80, 105, 90, 80, 105, 90, 5, 178, 90, 5, 178]
    },
    "rest": {
        "type": "body_state",
        "body_height": 0.02,
        "body_angles": {"phi": 0, "theta": 0, "psi": 0},
        "description": "Resting - body flat on ground, maximally folded",
        # All legs symmetric
        "fallback_angles": [90, 10, 175, 90, 10, 175, 90, 10, 175, 90, 10, 175]
    }
}

def init_kinematics():
    """Initialize Spot Micro kinematics model with actual robot dimensions"""
    global spot_model
    if not KINEMATICS_AVAILABLE:
        return False

    try:
        # Create with position only - dimensions are class defaults
        spot_model = SpotMicroStickFigure(
            x=body_state["x"],
            y=body_state["y"],
            z=body_state["z"]
        )
        # Set initial body angles (table pose)
        spot_model.set_body_angles(phi=0, theta=0, psi=0)

        print(f"✓ Kinematics model initialized")
        print(f"  Default dimensions: body={spot_model.body_length*1000:.0f}x{spot_model.body_width*1000:.0f}mm")
        print(f"  Legs: hip={spot_model.hip_length*1000:.0f}mm, upper={spot_model.upper_leg_length*1000:.0f}mm, lower={spot_model.lower_leg_length*1000:.0f}mm")
        return True
    except Exception as e:
        print(f"✗ Kinematics init failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def load_calibration():
    """Load calibration profile from file"""
    global calibration
    calib_file = BASE_DIR / "calibration.json"

    if calib_file.exists():
        try:
            with open(calib_file) as f:
                data = json.load(f)
            calibration = CalibrationProfile.from_dict(data)
            log_init.info(f"Loaded calibration ({len(calibration.servos)} servos)")
            if calibration.is_fully_calibrated():
                print(f"  Fully calibrated on {calibration.calibration_date}")
            else:
                uncalibrated = sum(1 for s in calibration.servos.values() if s["channel"] < 12 and not s["calibrated"])
                if uncalibrated > 0:
                    print(f"  ⚠ {uncalibrated} servos need calibration")
        except Exception as e:
            print(f"✗ Error loading calibration: {e}")
            calibration = CalibrationProfile()
    else:
        calibration = CalibrationProfile()
        print("⚠ No calibration file found - using defaults")

def save_calibration():
    """Save calibration profile to file"""
    calib_file = BASE_DIR / "calibration.json"
    calibration.calibration_date = datetime.datetime.now().isoformat()
    with open(calib_file, 'w') as f:
        json.dump(calibration.to_dict(), f, indent=2)
    print(f"✓ Calibration saved")

# ============== TUNING PERSISTENCE ==============
# Global tuning configuration (loaded at startup, persisted to tuning.json)
tuning_config = {
    "gait": {"cycle_time": 1.0, "step_height": 36, "step_length": 15, "speed": 1.0},
    "balance": {"kp": 0.5, "pitch_gain": 1.0, "roll_gain": 1.0},
    "stand": {"knee_bend": 40, "ankle_compensation": 1.3}
}

def load_tuning():
    """Load tuning parameters from file"""
    global tuning_config
    tuning_file = BASE_DIR / "tuning.json"

    if tuning_file.exists():
        try:
            with open(tuning_file) as f:
                data = json.load(f)
            # Merge with defaults (in case new keys were added)
            if "gait" in data:
                tuning_config["gait"].update(data["gait"])
            if "balance" in data:
                tuning_config["balance"].update(data["balance"])
            if "stand" in data:
                tuning_config["stand"].update(data["stand"])
            log_init.info(f"Loaded tuning config (Kp={tuning_config['balance']['kp']})")
        except Exception as e:
            print(f"✗ Error loading tuning: {e}")
    else:
        print("⚠ No tuning.json found - using defaults")
        save_tuning_to_file()  # Create default file

def save_tuning_to_file():
    """Save tuning parameters to file"""
    tuning_file = BASE_DIR / "tuning.json"
    tuning_config["last_updated"] = datetime.datetime.now().isoformat()
    tuning_config["version"] = "1.0"
    with open(tuning_file, 'w') as f:
        json.dump(tuning_config, f, indent=2)
    print(f"✓ Tuning saved")

def apply_tuning_to_gait():
    """Apply loaded tuning config to gait controller"""
    if GAIT_AVAILABLE and gait_controller:
        # Apply gait params
        gait_controller.set_params(**tuning_config["gait"])
        # Apply balance Kp
        gait_controller.set_balance_kp(tuning_config["balance"]["kp"])
        # Apply balance gains (pitch/roll)
        if gait_controller.balance:
            try:
                gait_controller.balance.pitch_gain = tuning_config["balance"].get("pitch_gain", 1.0)
                gait_controller.balance.roll_gain = tuning_config["balance"].get("roll_gain", 1.0)
            except AttributeError:
                pass  # Balance controller may not have these attributes
        log_init.info(f"Applied tuning to gait controller")

def init_servos():
    if not HW:
        print("Simulation mode - no servos")
        return

    try:
        for leg_id, config in QUAD_CONFIG.items():
            for i, channel in enumerate(config["channels"]):
                key = f"{leg_id}_{i}"
                servos[key] = servo.Servo(
                    pca.channels[channel],
                    min_pulse=SERVO_PARAMS["min_pulse"],
                    max_pulse=SERVO_PARAMS["max_pulse"],
                    actuation_range=SERVO_PARAMS["actuation_range"]
                )
                # Don't set angle yet - wait for goto_calibrated_neutrals
                servo_angles[channel] = 90
        print(f"✓ Initialized {len(servos)} servos")
    except Exception as e:
        print(f"✗ Servo init error: {e}")

def goto_calibrated_neutrals():
    """Send all servos to their calibrated neutral positions"""
    if not calibration:
        print("⚠ No calibration loaded, using 90° for all")
        for channel in range(12):
            set_servo(channel, 90, apply_offset=False)
        return

    print(f"\n{'='*60}")
    print(f"SENDING SERVOS TO CALIBRATED NEUTRAL POSITIONS")
    print(f"{'='*60}")
    for channel in range(12):
        if channel in calibration.servos:
            s = calibration.servos[channel]
            neutral = s["neutral_angle"]
            # Send RAW neutral angle (no offset calculation needed)
            set_servo(channel, neutral, apply_offset=False)
            print(f"  Ch{channel:2d} ({s['label']:<20}): → {neutral:3d}°")
        else:
            set_servo(channel, 90, apply_offset=False)
            print(f"  Ch{channel:2d} (unconfigured): → 90°")
    print(f"{'='*60}\n")

def set_servo(channel, angle, apply_offset=True):
    """Set servo angle with optional calibration"""
    servo_angles[channel] = angle

    if apply_offset and calibration:
        actual_angle = calibration.apply_to_angle(channel, angle)
        # Logging: show calibration being applied
        if channel in calibration.servos and calibration.servos[channel]["calibrated"]:
            servo_info = calibration.servos[channel]
            delta = angle - 90
            print(f"  Ch{channel} ({servo_info['label']:<20}): "
                  f"Cmd={angle:>3}° → Actual={int(actual_angle):>3}° "
                  f"(neutral={servo_info['neutral_angle']:>3}°, delta={delta:+3}°)")
    else:
        actual_angle = angle

    actual_angle = max(0, min(180, actual_angle))  # 180° servo range

    if not HW:
        return True

    try:
        for key, srv in servos.items():
            leg_id, joint_idx = key.split('_')
            leg_channels = QUAD_CONFIG[leg_id]["channels"]
            if leg_channels[int(joint_idx)] == channel:
                srv.angle = actual_angle
                return True
        return False
    except Exception as e:
        print(f"✗ Error ch{channel}: {e}")
        return False

def move_servo_smooth(channel, target_angle, duration_ms=500, apply_offset=True):
    """
    Move servo smoothly to target angle over specified duration.

    Args:
        channel: Servo channel (0-11)
        target_angle: Target angle in degrees
        duration_ms: Duration of movement in milliseconds (default 500ms)
        apply_offset: Whether to apply calibration offset
    """
    current = servo_angles.get(channel, 90)

    if duration_ms <= 0:
        # Instant move
        set_servo(channel, target_angle, apply_offset)
        return True

    # Calculate steps (20ms per step = 50Hz update rate)
    step_time = 0.02  # 20ms
    steps = max(1, int(duration_ms / 1000 / step_time))

    for i in range(steps + 1):
        progress = i / steps
        # Smooth easing (ease-in-out)
        smooth_progress = (1 - cos(progress * pi)) / 2
        intermediate = current + (target_angle - current) * smooth_progress
        set_servo(channel, int(intermediate), apply_offset)
        time.sleep(step_time)

    return True


def move_all_servos_smooth(target_angles, duration_ms=500, apply_offset=True):
    """
    Move all servos smoothly to target angles simultaneously.

    Args:
        target_angles: List of 12 target angles [ch0, ch1, ..., ch11]
        duration_ms: Duration of movement in milliseconds
        apply_offset: Whether to apply calibration offset
    """
    if len(target_angles) != 12:
        print(f"Error: expected 12 angles, got {len(target_angles)}")
        return False

    # Get current angles
    current_angles = [servo_angles.get(ch, 90) for ch in range(12)]

    if duration_ms <= 0:
        # Instant move
        for ch, angle in enumerate(target_angles):
            set_servo(ch, angle, apply_offset)
        return True

    # Calculate steps (20ms per step = 50Hz update rate)
    step_time = 0.02  # 20ms
    steps = max(1, int(duration_ms / 1000 / step_time))

    for i in range(steps + 1):
        progress = i / steps
        # Smooth easing (ease-in-out)
        smooth_progress = (1 - cos(progress * pi)) / 2

        for ch in range(12):
            intermediate = current_angles[ch] + (target_angles[ch] - current_angles[ch]) * smooth_progress
            set_servo(ch, int(intermediate), apply_offset)

        time.sleep(step_time)

    return True


def disable_servo(channel):
    """Disable servo PWM so it can be moved freely by hand"""
    if not HW:
        print(f"Simulation: would disable servo {channel}")
        return True

    try:
        # PCA9685 register addresses:
        # LED0_ON_L = 0x06, LED0_ON_H = 0x07, LED0_OFF_L = 0x08, LED0_OFF_H = 0x09
        # Each channel is 4 bytes apart
        # Setting bit 4 (0x10) in OFF_H register enables "full off" mode
        off_h_reg = 0x09 + 4 * channel  # OFF_H register for this channel

        # Use the i2c_device context manager to write directly
        with pca.i2c_device as i2c:
            i2c.write(bytes([off_h_reg, 0x10]))  # Set bit 4 (full off)

        print(f"✓ Servo {channel} disabled (full off bit set)")
        return True
    except Exception as e:
        print(f"✗ Error disabling ch{channel} via register: {e}")
        # Fallback: try alternative method via pwm_out
        try:
            # Set all ON/OFF registers to disable output completely
            # ON_L=0, ON_H=0, OFF_L=0, OFF_H=0x10 (full off)
            base_reg = 0x06 + 4 * channel
            with pca.i2c_device as i2c:
                i2c.write(bytes([base_reg, 0x00, 0x00, 0x00, 0x10]))
            print(f"✓ Servo {channel} disabled via full register write")
            return True
        except Exception as e2:
            print(f"✗ Fallback also failed: {e2}")
            # Last resort: duty_cycle = 0 (still sends tiny pulse but minimal)
            try:
                pca.channels[channel].duty_cycle = 0
                print(f"  Last resort: duty_cycle = 0")
                return True
            except:
                pass
        return False

def set_leg(leg_id, angles):
    if leg_id not in QUAD_CONFIG:
        return False
    config = QUAD_CONFIG[leg_id]
    success = True
    for i, (channel, angle) in enumerate(zip(config["channels"], angles)):
        if not set_servo(channel, angle):
            success = False
    if success:
        print(f"→ {leg_id}: {angles}")
    return success

def set_all_legs_from_ik():
    """Use kinematics model to set all leg angles"""
    if not spot_model:
        return False

    try:
        # Get joint angles from kinematics (in radians)
        angles_rad = spot_model.get_leg_angles()

        # Kinematics leg order: [FR, RR, FL, RL]
        # Our leg order: [FL, FR, RL, RR]
        leg_mapping = {
            0: "FR",  # Kinematics index 0 = Front Right
            1: "RR",  # Kinematics index 1 = Rear Right
            2: "FL",  # Kinematics index 2 = Front Left
            3: "RL"   # Kinematics index 3 = Rear Left
        }

        for kin_idx, leg_id in leg_mapping.items():
            leg_angles_rad = angles_rad[kin_idx]

            # Convert radians to degrees
            # Kinematics returns angles in robot frame, need to map to servo frame
            # 0 radians in kinematics = 90° logical servo angle
            #
            # Left legs (FL, RL): IK angles are already mirrored by kinematics library,
            # but our calibration also applies direction=-1, causing double inversion.
            # We need to invert the IK delta to compensate.
            if leg_id in ["FL", "RL"]:
                leg_angles_deg = [
                    90 - degrees(leg_angles_rad[0]),  # Hip: invert for left
                    90 - degrees(leg_angles_rad[1]),  # Knee: invert for left
                    90 - degrees(leg_angles_rad[2])   # Ankle: invert for left
                ]
            else:
                leg_angles_deg = [
                    90 + degrees(leg_angles_rad[0]),  # Hip
                    90 + degrees(leg_angles_rad[1]),  # Knee
                    90 + degrees(leg_angles_rad[2])   # Ankle
                ]

            # Apply to servos (calibration will be applied in set_servo)
            set_leg(leg_id, leg_angles_deg)

            print(f"  {leg_id}: hip={leg_angles_deg[0]:.1f}°, knee={leg_angles_deg[1]:.1f}°, ankle={leg_angles_deg[2]:.1f}°")

        return True
    except Exception as e:
        print(f"✗ IK error: {e}")
        return False

def set_body_pose(x=None, y=None, z=None, phi=None, theta=None, psi=None):
    """Set body pose and update leg angles via IK"""
    if not spot_model:
        return False

    try:
        # Update body state
        if x is not None: body_state["x"] = x
        if y is not None: body_state["y"] = y
        if z is not None: body_state["z"] = z
        if phi is not None: body_state["phi"] = phi
        if theta is not None: body_state["theta"] = theta
        if psi is not None: body_state["psi"] = psi

        # Update kinematics model
        spot_model.set_body_angles(
            phi=body_state["phi"],
            theta=body_state["theta"],
            psi=body_state["psi"]
        )

        # Apply to servos
        return set_all_legs_from_ik()
    except Exception as e:
        print(f"✗ Body pose error: {e}")
        return False

def set_foot_position(leg_id, x, y, z):
    """
    Set individual foot position relative to body origin.

    This is a placeholder for future IK-based foot positioning. When implemented,
    this function will allow precise control of each foot's position in 3D space,
    which is essential for:
    - Terrain adaptation (stepping over obstacles)
    - Body shifting during gait (moving CoG over support legs)
    - Custom foot trajectories for different gaits

    Args:
        leg_id: Leg identifier ("FL", "FR", "RL", "RR")
        x: Forward/backward position in meters (+X = forward)
        y: Height position in meters (+Y = up)
        z: Left/right position in meters (+Z = left)

    Returns:
        bool: True if position was set successfully, False otherwise

    Note:
        The current kinematics library (SpotMicroStickFigure) operates on all
        four legs simultaneously. Per-leg IK would require either:
        1. Implementing 3-DOF inverse kinematics for a single leg
        2. Using the existing library but only applying results for one leg

    See Also:
        - ik_interface.py for the IK wrapper module
        - CLAUDE.md for architecture documentation
    """
    # TODO: Implement per-leg IK using one of these approaches:
    # 1. Extract single-leg IK math from kinematics library
    # 2. Create IKInterface.set_single_foot() method
    # 3. Use geometric IK: given (x, y, z), solve for hip, knee, ankle angles
    #
    # For geometric IK approach:
    #   - Calculate distance from hip to foot
    #   - Use law of cosines to find knee angle
    #   - Use atan2 for hip and ankle angles
    pass

def set_pose(pose_name, duration_ms=0):
    """
    Execute preset pose using kinematics (instant by default).

    Args:
        pose_name: Name of the pose to execute
        duration_ms: Duration of smooth transition in ms (default 500ms, 0 for instant)
    """
    if pose_name not in POSES:
        print(f"✗ Unknown pose: {pose_name}")
        return False

    pose = POSES[pose_name]
    pose_type = pose.get("type", "body_state")

    if pose_type == "calibrated_neutral":
        # Special case: send to calibrated neutral positions (table pose)
        print(f"✓ Pose: {pose_name} - {pose.get('description', '')}")
        # Build target angles for smooth transition
        target_angles = [90] * 12  # Logical 90° = calibrated neutral
        if duration_ms > 0:
            move_all_servos_smooth(target_angles, duration_ms)
        else:
            for channel in range(12):
                set_servo(channel, 90)
        return True

    elif pose_type == "body_state":
        # Set body state
        body_height = pose.get("body_height", 0.14)
        angles = pose.get("body_angles", {})
        phi = angles.get("phi", 0)
        theta = angles.get("theta", 0)
        psi = angles.get("psi", 0)

        # Update global body state
        body_state["y"] = body_height
        body_state["phi"] = phi
        body_state["theta"] = theta
        body_state["psi"] = psi

        print(f"✓ Pose: {pose_name} - {pose.get('description', '')}")
        print(f"  Body: h={body_height*1000:.0f}mm")
        if duration_ms > 0:
            print(f"  Smooth transition: {duration_ms}ms")

        # Use fallback angles (kinematics library interface is complex)
        fallback = pose.get("fallback_angles")
        if fallback:
            print(f"  Using predefined angles")
            if duration_ms > 0:
                move_all_servos_smooth(fallback, duration_ms)
            else:
                for channel, angle in enumerate(fallback):
                    set_servo(channel, angle)
            return True
        else:
            print("✗ No fallback angles defined")
            return False

    else:
        print(f"✗ Unknown pose type: {pose_type}")
        return False

def reset_all():
    for channel in range(16):
        set_servo(channel, 90)
    print("✓ Reset to 90°")

def cleanup():
    if HW and pca:
        print("Shutting down...")
        try:
            pca.deinit()
        except:
            pass
    print("Shutdown complete")

signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(0)))
atexit.register(cleanup)

def _load_tuning():
    """Load tuning from tuning.json and apply to gait controller"""
    load_tuning()
    apply_tuning_to_gait()

def init_gait():
    """Initialize gait controller"""
    global gait_controller
    if not GAIT_AVAILABLE:
        return False

    try:
        gait_controller = GaitController(set_servo)
        _load_tuning()
        print("✓ Gait controller initialized")
        return True
    except Exception as e:
        print(f"✗ Gait init failed: {e}")
        return False

def init_stability_monitor():
    """Initialize stability monitor for tracking robot orientation"""
    global stability_monitor
    if not STABILITY_AVAILABLE:
        return False

    try:
        # Use default thresholds
        stability_monitor = StabilityMonitor()
        print("✓ Stability monitor initialized")
        return True
    except Exception as e:
        print(f"✗ Stability monitor init failed: {e}")
        return False

# Initialize
load_calibration()
init_servos()
init_kinematics()
init_gait()
init_stability_monitor()
load_custom_poses()

# Startup: go directly to stand position
if HW:
    print("\n🚀 Starting up - going to stand position...")
    set_pose("stand", duration_ms=0)  # Direct to stand, no smooth transition
    print("✓ Startup complete - robot in stand position")

# FastAPI app
app = FastAPI(title="MicroSpot Control", version="2.0.0")

@app.get("/")
def index():
    return {"message": "MicroSpot API v2.0", "docs": "/docs", "status": "/api/status"}

@app.get("/api/config")
def get_config():
    return {
        "hardware": HW,
        "kinematics": KINEMATICS_AVAILABLE,
        "legs": QUAD_CONFIG,
        "servo_params": SERVO_PARAMS,
        "spot_config": SPOT_CONFIG,
        "poses": list(POSES.keys()),
        "current_angles": servo_angles,
        "calibration": calibration.to_dict() if calibration else {},
        "body_state": body_state
    }

@app.get("/api/status")
def get_status():
    return {
        "hardware": HW,
        "kinematics": KINEMATICS_AVAILABLE,
        "servos": len(servos),
        "angles": servo_angles,
        "calibration": calibration.to_dict() if calibration else {},
        "body": body_state
    }

@app.get("/api/calibration")
def get_calibration():
    """Get current calibration profile"""
    return calibration.to_dict() if calibration else {}

@app.post("/api/calibration/servo/{channel}")
async def update_servo_calibration(channel: int, data: dict):
    """Update calibration for a specific servo"""
    if calibration and channel in calibration.servos:
        calibration.servos[channel].update(data)
        save_calibration()
        return {"status": "ok", "channel": channel}
    return {"status": "error", "message": "Invalid channel"}

@app.post("/api/calibration/save")
async def save_calibration_endpoint():
    """Save current calibration"""
    save_calibration()
    return {"status": "ok"}

@app.post("/api/calibration/reset")
async def reset_calibration():
    """Reset calibration to defaults"""
    global calibration
    calibration = CalibrationProfile()
    save_calibration()
    return {"status": "ok"}

@app.get("/api/calibration/export")
def export_calibration():
    """Export calibration as downloadable JSON"""
    return calibration.to_dict() if calibration else {}

@app.get("/api/calibration/summary")
def calibration_summary():
    """Print calibration summary to console"""
    if not calibration:
        return {"status": "error", "message": "No calibration"}

    print(f"\n{'='*70}")
    print(f"CALIBRATION SUMMARY - All Values")
    print(f"{'='*70}")
    print(f"{'Ch':<4} {'Label':<22} {'Neutral':<9} {'Offset':<9} {'Calibrated'}")
    print(f"{'-'*70}")

    for channel in range(12):
        if channel in calibration.servos:
            s = calibration.servos[channel]
            status = "✓" if s["calibrated"] else "✗"
            print(f"{channel:<4} {s['label']:<22} {s['neutral_angle']:>3}°      "
                  f"{s['offset']:>+4}°      {status}")

    print(f"{'='*70}")
    print(f"File: {BASE_DIR / 'calibration.json'}")
    print(f"Date: {calibration.calibration_date}")
    print(f"{'='*70}\n")

    return {"status": "ok", "calibration": calibration.to_dict()}

# REST API endpoints for control (used by Streamlit)
@app.post("/api/servo/{channel}")
async def set_servo_endpoint(channel: int, data: dict):
    """Set servo angle via REST API"""
    angle = data.get("angle", 90)
    raw = data.get("raw", False)  # If true, don't apply calibration
    success = set_servo(channel, angle, apply_offset=not raw)
    return {"status": "ok" if success else "error", "channel": channel, "angle": angle}

@app.post("/api/servo/{channel}/disable")
async def disable_servo_endpoint(channel: int):
    """Disable servo PWM so it can be moved freely"""
    success = disable_servo(channel)
    return {"status": "ok" if success else "error", "channel": channel, "disabled": success}

@app.post("/api/leg/{leg_id}")
async def set_leg_endpoint(leg_id: str, data: dict):
    """Set leg angles via REST API"""
    angles = data.get("angles", [90, 90, 90])
    if leg_id not in QUAD_CONFIG:
        return {"status": "error", "message": f"Unknown leg: {leg_id}"}
    success = set_leg(leg_id, angles)
    return {"status": "ok" if success else "error", "leg_id": leg_id, "angles": angles}

@app.post("/api/pose/{pose_name}")
async def set_pose_endpoint(pose_name: str, data: dict = {}):
    """Execute preset pose via REST API with optional smooth transition.

    Args:
        pose_name: Name of the pose (neutral, stand, sit, rest)
        data: Optional dict with duration_ms (default 500ms, 0 for instant)
    """
    if pose_name not in POSES:
        return {"status": "error", "message": f"Unknown pose: {pose_name}", "available": list(POSES.keys())}
    duration_ms = data.get("duration_ms", 500)
    success = set_pose(pose_name, duration_ms)
    return {"status": "ok" if success else "error", "pose": pose_name, "body_state": body_state, "duration_ms": duration_ms}

@app.post("/api/body")
async def set_body_pose_endpoint(data: dict):
    """Set body pose via REST API"""
    success = set_body_pose(
        x=data.get("x"),
        y=data.get("y"),
        z=data.get("z"),
        phi=data.get("phi"),
        theta=data.get("theta"),
        psi=data.get("psi")
    )
    return {"status": "ok" if success else "error", "body_state": body_state}

@app.post("/api/reset")
async def reset_endpoint():
    """Reset all servos to 90° via REST API"""
    reset_all()
    return {"status": "ok", "angles": servo_angles}

@app.post("/api/goto_neutrals")
async def goto_neutrals_endpoint():
    """Send all servos to their calibrated neutral positions"""
    goto_calibrated_neutrals()
    return {"status": "ok"}

# ============== GAIT API ENDPOINTS ==============

@app.get("/api/gait/status")
def get_gait_status():
    """Get gait controller status"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"available": False, "running": False}

    return {
        "available": True,
        "running": gait_controller.is_running(),
        "direction": gait_controller.direction,
        "params": gait_controller.get_params()
    }

@app.post("/api/gait/start")
async def start_gait(data: dict = {}):
    """Start walking gait"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    direction = data.get("direction", "forward")

    # Update params if provided
    if "params" in data:
        gait_controller.set_params(**data["params"])

    success = gait_controller.start(direction)
    return {
        "status": "ok" if success else "error",
        "running": gait_controller.is_running(),
        "direction": direction
    }

@app.post("/api/gait/stop")
async def stop_gait():
    """Stop walking gait"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    success = gait_controller.stop()
    return {
        "status": "ok" if success else "error",
        "running": gait_controller.is_running()
    }

@app.post("/api/gait/step")
async def single_step(data: dict = {}):
    """Execute a single step"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    if gait_controller.is_running():
        return {"status": "error", "message": "Gait already running - stop first"}

    direction = data.get("direction", "forward")

    # Update params if provided
    if "params" in data:
        gait_controller.set_params(**data["params"])

    gait_controller.single_step(direction)
    return {"status": "ok", "direction": direction}

@app.post("/api/gait/params")
async def set_gait_params(data: dict):
    """Update gait parameters"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    gait_controller.set_params(**data)
    return {"status": "ok", "params": gait_controller.get_params()}

@app.post("/api/gait/stand_height")
async def set_stand_height(data: dict):
    """Set stand height (knee bend amount)"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    knee_bend = data.get("knee_bend", 45)
    angles = gait_controller.set_stand_height(knee_bend)
    return {"status": "ok", "knee_bend": knee_bend, "stand_angles": angles}

@app.post("/api/gait/preview_stand")
async def preview_stand():
    """Move robot to current stand position for preview"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    gait_controller.preview_stand()
    return {"status": "ok", "stand_angles": gait_controller.get_stand_angles()}

@app.get("/api/gait/stand_angles")
def get_stand_angles():
    """Get current stand angles"""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    return {"status": "ok", "stand_angles": gait_controller.get_stand_angles()}

@app.post("/api/gait/turn")
async def set_turn_rate(data: dict):
    """Set turning rate (-1.0 = full left, 1.0 = full right)."""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    rate = data.get("rate", 0.0)
    rate = max(-1.0, min(1.0, rate))  # Clamp to valid range
    gait_controller.set_turn_rate(rate)
    return {"status": "ok", "turn_rate": rate}

@app.post("/api/gait/lateral")
async def set_lateral_rate(data: dict):
    """Set lateral stepping rate (-1.0 = full left, 1.0 = full right)."""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"status": "error", "message": "Gait not available"}

    rate = data.get("rate", 0.0)
    rate = max(-1.0, min(1.0, rate))  # Clamp to valid range
    gait_controller.set_lateral_rate(rate)
    return {"status": "ok", "lateral_rate": rate}

@app.post("/api/gait/mode")
async def set_gait_mode(data: dict = {}):
    """Switch between IK and angle-based gait modes.

    Args:
        data: {"use_ik": bool} - True for IK mode, False for angle-based

    Returns:
        {"success": bool, "mode": str, "ik_available": bool}
    """
    if not GAIT_AVAILABLE or not gait_controller:
        return {"success": False, "error": "Gait controller not initialized"}

    use_ik = data.get("use_ik", False)

    # Try to set the mode
    success = gait_controller.set_mode(use_ik)

    return {
        "success": success,
        "mode": "ik" if gait_controller.use_ik else "angle",
        "ik_available": hasattr(gait_controller, 'ik_interface') and gait_controller.ik_interface is not None
    }

@app.get("/api/gait/mode")
def get_gait_mode():
    """Get current gait mode (IK or angle-based)."""
    if not GAIT_AVAILABLE or not gait_controller:
        return {"error": "Gait controller not initialized"}

    params = gait_controller.get_params()
    return {
        "mode": "ik" if params.get("use_ik", False) else "angle",
        "ik_available": params.get("ik_available", False),
        "ik_step_height": params.get("ik_step_height", 0.03),
        "ik_stride_length": params.get("ik_stride_length", 0.04)
    }

# ============== CUSTOM POSES API ENDPOINTS ==============

@app.get("/api/custom_poses")
def get_custom_poses():
    """Get all custom poses"""
    return {"status": "ok", "poses": custom_poses}

@app.post("/api/custom_poses/{pose_name}")
async def save_custom_pose(pose_name: str, data: dict):
    """Save a custom pose

    Expected data format:
    {
        "description": "My custom pose",
        "angles": {
            "FL": {"hip": 90, "knee": 45, "ankle": 135},
            "FR": {"hip": 90, "knee": 45, "ankle": 135},
            "RL": {"hip": 90, "knee": 45, "ankle": 135},
            "RR": {"hip": 90, "knee": 45, "ankle": 135}
        }
    }
    """
    if not pose_name or pose_name in POSES:
        return {"status": "error", "message": "Invalid pose name or conflicts with preset"}

    custom_poses[pose_name] = {
        "description": data.get("description", "Custom pose"),
        "angles": data.get("angles", {}),
        "created": datetime.datetime.now().isoformat()
    }

    save_custom_poses()
    return {"status": "ok", "pose_name": pose_name}

@app.delete("/api/custom_poses/{pose_name}")
async def delete_custom_pose(pose_name: str):
    """Delete a custom pose"""
    if pose_name in custom_poses:
        del custom_poses[pose_name]
        save_custom_poses()
        return {"status": "ok", "deleted": pose_name}
    return {"status": "error", "message": "Pose not found"}

@app.post("/api/custom_poses/{pose_name}/execute")
async def execute_custom_pose(pose_name: str):
    """Execute a custom pose"""
    if pose_name not in custom_poses:
        return {"status": "error", "message": "Pose not found"}

    pose = custom_poses[pose_name]
    angles = pose.get("angles", {})

    # Apply angles to each leg
    for leg_id in ["FL", "FR", "RL", "RR"]:
        if leg_id in angles:
            leg_angles = angles[leg_id]
            set_leg(leg_id, [
                leg_angles.get("hip", 90),
                leg_angles.get("knee", 90),
                leg_angles.get("ankle", 90)
            ])

    return {"status": "ok", "pose": pose_name}

@app.get("/api/current_pose")
def get_current_pose():
    """Get current servo angles formatted as a pose"""
    angles = {}
    for leg_id, config in QUAD_CONFIG.items():
        channels = config["channels"]
        angles[leg_id] = {
            "hip": servo_angles.get(channels[0], 90),
            "knee": servo_angles.get(channels[1], 90),
            "ankle": servo_angles.get(channels[2], 90)
        }
    return {"status": "ok", "angles": angles}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    print("WebSocket connected")

    try:
        while True:
            data = await ws.receive_json()
            cmd = data.get("cmd")

            if cmd == "servo":
                channel = data.get("channel")
                angle = data.get("angle")
                success = set_servo(channel, angle)
                await ws.send_json({"status": "ok" if success else "error", "channel": channel})

            elif cmd == "leg":
                leg_id = data.get("leg_id")
                angles = data.get("angles")
                success = set_leg(leg_id, angles)
                await ws.send_json({"status": "ok" if success else "error", "leg_id": leg_id})

            elif cmd == "body_pose":
                # Set body orientation
                success = set_body_pose(
                    x=data.get("x"),
                    y=data.get("y"),
                    z=data.get("z"),
                    phi=data.get("phi"),
                    theta=data.get("theta"),
                    psi=data.get("psi")
                )
                await ws.send_json({"status": "ok" if success else "error", "body": body_state})

            elif cmd == "pose":
                pose_name = data.get("pose")
                success = set_pose(pose_name)
                await ws.send_json({"status": "ok" if success else "error", "pose": pose_name})

            elif cmd == "reset":
                reset_all()
                await ws.send_json({"status": "ok"})

            elif cmd == "calibrate_servo":
                # Live calibration adjustment - sends raw angle without applying calibration
                channel = data.get("channel")
                angle = data.get("angle")
                success = set_servo(channel, angle, apply_offset=False)
                await ws.send_json({"status": "ok" if success else "error", "channel": channel, "angle": angle})

            elif cmd == "save_servo_calibration":
                # Save calibration data for a specific servo
                channel = data.get("channel")
                servo_data = data.get("servo_data")
                if calibration and channel in calibration.servos:
                    calibration.servos[channel].update(servo_data)
                    save_calibration()
                    await ws.send_json({"status": "ok", "channel": channel})
                else:
                    await ws.send_json({"status": "error", "message": "Invalid channel"})

            elif cmd == "test_calibration":
                # Test calibrated neutral position for all servos
                if calibration:
                    for channel, servo_data in calibration.servos.items():
                        if channel < 12:  # Only the 12 robot servos
                            set_servo(channel, 90)  # 90 = logical neutral, calibration will apply
                    await ws.send_json({"status": "ok"})
                else:
                    await ws.send_json({"status": "error", "message": "No calibration loaded"})

            elif cmd == "goto_calibrated_neutrals":
                # Send servos directly to their calibrated neutral angles (raw)
                if calibration:
                    print(f"\n{'='*60}")
                    print(f"GOING TO CALIBRATED NEUTRAL POSITIONS (RAW)")
                    print(f"{'='*60}")
                    for channel in range(12):
                        if channel in calibration.servos:
                            s = calibration.servos[channel]
                            neutral = s["neutral_angle"]
                            # Send RAW angle (no calibration applied)
                            set_servo(channel, neutral, apply_offset=False)
                            print(f"  Ch{channel} ({s['label']:<20}): → {neutral}°")
                    print(f"{'='*60}\n")
                    await ws.send_json({"status": "ok"})
                else:
                    await ws.send_json({"status": "error", "message": "No calibration loaded"})

            elif cmd == "autotune_start":
                # Start autotune for a specific servo
                channel = data.get("channel")
                if calibration and channel in calibration.servos:
                    servo_info = calibration.servos[channel]
                    print(f"\n{'='*60}")
                    print(f"AUTOTUNE START - Channel {channel}")
                    print(f"Servo: {servo_info['label']}")
                    print(f"Leg: {servo_info['leg']} - Joint: {servo_info['joint']}")
                    print(f"{'='*60}")
                    await ws.send_json({"status": "ok", "channel": channel, "servo": servo_info})
                else:
                    await ws.send_json({"status": "error", "message": "Invalid channel"})

            elif cmd == "autotune_set_neutral":
                # User pressed STOP - save current angle as neutral
                channel = data.get("channel")
                angle = data.get("angle")
                if calibration and channel in calibration.servos:
                    servo_info = calibration.servos[channel]
                    old_neutral = servo_info["neutral_angle"]

                    # Calculate offset
                    servo_info["neutral_angle"] = angle
                    servo_info["offset"] = angle - 90
                    servo_info["calibrated"] = True

                    # Logging
                    print(f"\n{'='*60}")
                    print(f"AUTOTUNE SAVED - Channel {channel}")
                    print(f"Servo: {servo_info['label']}")
                    print(f"  Old neutral: {old_neutral}°")
                    print(f"  New neutral: {angle}°")
                    print(f"  Offset: {servo_info['offset']:+.1f}°")
                    print(f"  Rotation: {angle - old_neutral:+.1f}° from previous")
                    print(f"{'='*60}\n")

                    save_calibration()
                    await ws.send_json({
                        "status": "ok",
                        "channel": channel,
                        "neutral_angle": angle,
                        "offset": servo_info["offset"],
                        "rotation": angle - old_neutral
                    })
                else:
                    await ws.send_json({"status": "error", "message": "Invalid channel"})

            elif cmd == "autotune_complete":
                # All servos calibrated - show summary
                if calibration:
                    print(f"\n{'='*60}")
                    print(f"AUTOTUNE COMPLETE - CALIBRATION SUMMARY")
                    print(f"{'='*60}")
                    print(f"{'Channel':<8} {'Label':<20} {'Neutral':<10} {'Offset':<10}")
                    print(f"{'-'*60}")

                    for channel in range(12):
                        if channel in calibration.servos:
                            s = calibration.servos[channel]
                            if s["calibrated"]:
                                print(f"{channel:<8} {s['label']:<20} {s['neutral_angle']:<10}° {s['offset']:+.1f}°")

                    print(f"{'='*60}")
                    print(f"Calibration saved to: {BASE_DIR / 'calibration.json'}")
                    print(f"{'='*60}\n")

                    await ws.send_json({"status": "ok", "calibration": calibration.to_dict()})
                else:
                    await ws.send_json({"status": "error", "message": "No calibration loaded"})

            else:
                await ws.send_json({"status": "error", "message": f"Unknown: {cmd}"})

    except WebSocketDisconnect:
        pass

# ============== BALANCE/IMU ENDPOINTS ==============

@app.get("/api/balance/status")
def get_balance_status():
    """Get IMU balance status"""
    if not gait_controller:
        return {"error": "No gait"}
    return {
        "available": gait_controller.balance is not None,
        "enabled": gait_controller.use_balance,
    }

@app.post("/api/balance/enable")
async def enable_balance(data: dict = {}):
    """Enable/disable IMU balance"""
    if not gait_controller:
        return {"error": "No gait"}
    enable = data.get("enable", True)
    success = gait_controller.enable_balance(enable, True)
    return {"ok": success, "enabled": gait_controller.use_balance}

@app.post("/api/balance/calibrate")
async def calibrate_balance():
    """Calibrate IMU zero point"""
    if not gait_controller or not gait_controller.balance:
        return {"error": "No IMU"}
    gait_controller.balance.calibrate(30)
    return {"ok": True}

@app.get("/api/balance/angles")
def get_balance_angles():
    """Get current pitch/roll"""
    if not gait_controller or not gait_controller.balance:
        return {"pitch": 0, "roll": 0, "error": "no_balance_controller"}
    try:
        # Check if IMU is actually available (not in simulation mode)
        bal = gait_controller.balance
        is_real = getattr(bal, 'is_available', lambda: False)()
        p, r = bal.get_angles()
        return {
            "pitch": round(p, 1),
            "roll": round(r, 1),
            "imu_available": is_real,
            "simulation": getattr(bal, 'simulation_mode', True)
        }
    except Exception as e:
        return {"pitch": 0, "roll": 0, "error": str(e)}

@app.get("/api/balance/config")
def get_balance_config():
    """Get current balance controller configuration."""
    if gait_controller and gait_controller.balance:
        return {
            "enabled": gait_controller.use_balance,
            "pitch_gain": getattr(gait_controller.balance, 'pitch_gain', 1.0),
            "roll_gain": getattr(gait_controller.balance, 'roll_gain', 1.0),
            "kp": getattr(gait_controller.balance, 'kp', 1.0)
        }
    return {"enabled": False, "error": "Balance controller not available"}

@app.post("/api/balance/config")
async def set_balance_config(data: dict):
    """Update balance controller gains.

    Args (in data dict):
        pitch_gain: Gain for pitch correction (optional)
        roll_gain: Gain for roll correction (optional)
        kp: Proportional gain for balance (optional)
    """
    if not gait_controller or not gait_controller.balance:
        return {"success": False, "error": "Balance controller not available"}

    updated = {}
    if "pitch_gain" in data:
        gait_controller.balance.pitch_gain = data["pitch_gain"]
        updated["pitch_gain"] = data["pitch_gain"]
    if "roll_gain" in data:
        gait_controller.balance.roll_gain = data["roll_gain"]
        updated["roll_gain"] = data["roll_gain"]
    if "kp" in data:
        gait_controller.set_balance_kp(data["kp"])
        updated["kp"] = data["kp"]

    return {"success": True, "updated": updated}

# ============== STABILITY ENDPOINTS ==============

@app.get("/api/stability")
def get_stability_status():
    """Get current stability status from IMU readings."""
    if not stability_monitor:
        return {"state": "unknown", "error": "Stability monitor not available"}

    # Update stability monitor with current IMU readings if available
    if gait_controller and gait_controller.balance:
        try:
            pitch, roll = gait_controller.balance.get_angles()
            stability_monitor.update(pitch, roll)
        except:
            pass

    return stability_monitor.get_status()

@app.get("/api/stability/thresholds")
def get_stability_thresholds():
    """Get current stability thresholds."""
    if not stability_monitor:
        return {"error": "Stability monitor not available"}

    return {
        "warning": {
            "pitch": stability_monitor.thresholds.warning_pitch,
            "roll": stability_monitor.thresholds.warning_roll
        },
        "critical": {
            "pitch": stability_monitor.thresholds.critical_pitch,
            "roll": stability_monitor.thresholds.critical_roll
        },
        "emergency": {
            "pitch": stability_monitor.thresholds.emergency_pitch,
            "roll": stability_monitor.thresholds.emergency_roll
        }
    }

@app.post("/api/stability/thresholds")
async def set_stability_thresholds(data: dict):
    """Update stability thresholds.

    Args (in data dict):
        warning_pitch, warning_roll: Warning thresholds (degrees)
        critical_pitch, critical_roll: Critical thresholds (degrees)
        emergency_pitch, emergency_roll: Emergency thresholds (degrees)
    """
    if not stability_monitor:
        return {"success": False, "error": "Stability monitor not available"}

    updated = {}
    for key in ["warning_pitch", "warning_roll", "critical_pitch", "critical_roll",
                "emergency_pitch", "emergency_roll"]:
        if key in data:
            setattr(stability_monitor.thresholds, key, data[key])
            updated[key] = data[key]

    return {"success": True, "updated": updated}

@app.get("/api/stability/statistics")
def get_stability_statistics():
    """Get statistics about time spent in each stability state."""
    if not stability_monitor:
        return {"error": "Stability monitor not available"}

    return stability_monitor.get_state_statistics()

@app.post("/api/stability/reset")
async def reset_stability():
    """Reset stability monitor to initial state."""
    if not stability_monitor:
        return {"success": False, "error": "Stability monitor not available"}

    stability_monitor.reset()
    return {"success": True}

# ============== TUNING ENDPOINTS ==============

@app.get("/api/tuning")
def get_tuning():
    """Get all tuning parameters from tuning_config (persistent) and gait controller"""
    # Combine persistent config with live gait params
    result = {
        # Gait params (from tuning_config, updated by gait controller)
        "cycle_time": tuning_config["gait"].get("cycle_time", 1.0),
        "step_height": tuning_config["gait"].get("step_height", 36),
        "step_length": tuning_config["gait"].get("step_length", 15),
        "speed": tuning_config["gait"].get("speed", 1.0),
        # Balance params (persistent)
        "balance_kp": tuning_config["balance"].get("kp", 0.5),
        "pitch_gain": tuning_config["balance"].get("pitch_gain", 1.0),
        "roll_gain": tuning_config["balance"].get("roll_gain", 1.0),
        # Stand params (persistent)
        "knee_bend": tuning_config["stand"].get("knee_bend", 40),
        "ankle_compensation": tuning_config["stand"].get("ankle_compensation", 1.3),
    }

    # If gait controller available, get live values
    if GAIT_AVAILABLE and gait_controller:
        params = gait_controller.get_params()
        result["cycle_time"] = params.get("cycle_time", result["cycle_time"])
        result["step_height"] = params.get("step_height", result["step_height"])
        result["step_length"] = params.get("step_length", result["step_length"])
        result["speed"] = params.get("speed", result["speed"])

    return result

@app.post("/api/tuning/{key}")
async def save_tuning_param(key: str, data: dict):
    """Save a tuning parameter to gait controller AND persist to file"""
    value = data.get("value")

    # Gait parameters
    if key in ["cycle_time", "step_height", "step_length", "speed"]:
        tuning_config["gait"][key] = value
        if GAIT_AVAILABLE and gait_controller:
            gait_controller.set_params(**{key: value})
        save_tuning_to_file()
        return {"ok": True, "key": key, "value": value, "persisted": True}

    # Balance parameters
    elif key in ["balance_kp", "kp"]:
        tuning_config["balance"]["kp"] = value
        if gait_controller:
            gait_controller.set_balance_kp(value)
        save_tuning_to_file()
        return {"ok": True, "key": "balance_kp", "value": value, "persisted": True}

    elif key in ["pitch_gain", "roll_gain"]:
        tuning_config["balance"][key] = value
        # Apply to gait controller's balance object
        if GAIT_AVAILABLE and gait_controller and gait_controller.balance:
            try:
                if key == "pitch_gain":
                    gait_controller.balance.pitch_gain = value
                elif key == "roll_gain":
                    gait_controller.balance.roll_gain = value
                log_tuning.info(f"Applied {key}={value} to balance controller")
            except AttributeError:
                log_tuning.warning(f"Balance controller doesn't support {key}")
        save_tuning_to_file()
        return {"ok": True, "key": key, "value": value, "persisted": True}

    # Stand parameters
    elif key in ["knee_bend", "ankle_compensation"]:
        tuning_config["stand"][key] = value
        save_tuning_to_file()
        return {"ok": True, "key": key, "value": value, "persisted": True}

    else:
        return {"error": f"Unknown tuning parameter: {key}"}

@app.post("/api/balance/kp")
async def set_balance_kp_endpoint(data: dict):
    """Set balance Kp and persist to file"""
    if not gait_controller:
        return {"error": "No gait"}
    kp = data.get("kp", 1.0)
    gait_controller.set_balance_kp(kp)
    # Also persist to tuning config
    tuning_config["balance"]["kp"] = kp
    save_tuning_to_file()
    return {"ok": True, "kp": kp, "persisted": True}

# ============== MAIN ==============

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🤖  MicroSpot Control v2.0 (with Spot Micro Kinematics)")
    print("="*70)
    print(f"Mode: {'Hardware' if HW else 'Simulation'}")
    print(f"Kinematics: {'✓ Available' if KINEMATICS_AVAILABLE else '✗ Not available'}")
    print(f"URL:  http://microspot:8000")
    print("\nLeg Configuration:")
    for leg_id, config in QUAD_CONFIG.items():
        print(f"  {leg_id} - {config['name']:15s} Channels: {config['channels']}")
    print(f"\nPreset Poses: {', '.join(POSES.keys())}")
    if calibration:
        calibrated_count = sum(1 for s in calibration.servos.values() if s.get('channel', 99) < 12 and s.get('calibrated', False))
        print(f"Calibration: {calibrated_count}/12 servos calibrated")
    print("="*70 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
