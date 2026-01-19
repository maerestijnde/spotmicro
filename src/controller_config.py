#!/usr/bin/env python3
"""
Controller configuration and constants for PS4 controller
"""

class ControllerConfig:
    """Configuration for PS4 controller mapping"""

    # Deadzone for analog sticks (15% of full range)
    # Stick values range from -32767 to 32767
    STICK_DEADZONE = 4900

    # Maximum body orientation angles (radians)
    MAX_PITCH = 0.3
    MAX_ROLL = 0.3
    MAX_YAW = 0.3

    # Body height range (knee bend degrees)
    MIN_HEIGHT = 0    # Legs straight (table pose)
    MAX_HEIGHT = 80   # Very low crouch (knee=10)
    HEIGHT_STEP = 5   # Step size for L1/R1

    # Rate limiting (seconds)
    BODY_UPDATE_INTERVAL = 0.05  # 50ms between body updates

    # API base URL
    DEFAULT_API_URL = "http://localhost:8000"

    # API endpoints
    ENDPOINTS = {
        # Gait control
        "gait_start": "/api/gait/start",
        "gait_stop": "/api/gait/stop",
        "gait_step": "/api/gait/step",
        "gait_status": "/api/gait/status",
        "gait_params": "/api/gait/params",
        "stand_height": "/api/gait/stand_height",
        "preview_stand": "/api/gait/preview_stand",

        # Poses
        "pose": "/api/pose/{name}",
        "custom_poses": "/api/custom_poses",
        "execute_custom": "/api/custom_poses/{name}/execute",

        # Body control
        "body": "/api/body",
        "goto_neutrals": "/api/goto_neutrals",
        "reset": "/api/reset",

        # Servo control
        "servo": "/api/servo/{channel}",
        "leg": "/api/leg/{leg_id}",

        # Balance
        "balance_status": "/api/balance/status",
        "balance_enable": "/api/balance/enable",
        "balance_calibrate": "/api/balance/calibrate",
        "balance_angles": "/api/balance/angles",

        # Status
        "status": "/api/status",
        "config": "/api/config",
    }
