"""
Orbit forward kinematics - ported verbatim from nicegui_app.py lines 56-212.

Computes 3D joint positions for the robot visualization.
"""
from math import radians, cos, sin

from orbit.state import LEG_CONFIG

# ============================================================================
# ROBOT DIMENSIONS (meters)
# ============================================================================

BODY_LENGTH = 0.186
BODY_WIDTH = 0.078
HIP_LENGTH = 0.055
UPPER_LEG_LENGTH = 0.1075
LOWER_LEG_LENGTH = 0.130

# ============================================================================
# FORWARD KINEMATICS
# ============================================================================


def get_servo_angle(servo_angles: dict, channel: int) -> float:
    return servo_angles.get(channel, servo_angles.get(str(channel), 90))


def calculate_leg_points(hip_origin: list, hip_angle: float, knee_angle: float,
                         ankle_angle: float, is_left_side: bool) -> dict:
    """Calculate leg joint positions using forward kinematics. Returns dict of [x, y, z] lists."""
    z_dir = 1.0 if is_left_side else -1.0
    hip_end = [hip_origin[0], hip_origin[1], hip_origin[2] + z_dir * HIP_LENGTH]

    hip_rad = radians(hip_angle - 90)
    knee_rad = radians(knee_angle - 90)
    ankle_rad = radians(ankle_angle - 90)

    knee_x = hip_end[0] + UPPER_LEG_LENGTH * sin(hip_rad + knee_rad)
    knee_y = hip_end[1] - UPPER_LEG_LENGTH * cos(hip_rad + knee_rad)
    knee_z = hip_end[2]
    knee_end = [knee_x, knee_y, knee_z]

    total_angle = hip_rad + knee_rad + ankle_rad
    foot_x = knee_end[0] + LOWER_LEG_LENGTH * sin(total_angle)
    foot_y = knee_end[1] - LOWER_LEG_LENGTH * cos(total_angle)
    foot_z = knee_end[2]
    foot_end = [foot_x, foot_y, foot_z]

    return {"hip_origin": hip_origin, "hip_end": hip_end, "knee_end": knee_end, "foot_end": foot_end}


# Rotation matrix cache - avoids recomputing for same pitch/roll/yaw
_rot_cache = {"key": None, "matrix": None}


def _get_rotation_matrix(pitch: float, roll: float, yaw: float) -> list:
    """Get rotation matrix R = Rx(roll) @ Rz(pitch) @ Ry(yaw), cached."""
    global _rot_cache
    key = (pitch, roll, yaw)
    if _rot_cache["key"] == key:
        return _rot_cache["matrix"]

    pitch_rad = radians(pitch)
    roll_rad = radians(roll)
    yaw_rad = radians(yaw)

    cr, sr = cos(roll_rad), sin(roll_rad)
    cp, sp = cos(pitch_rad), sin(pitch_rad)
    cy, sy = cos(yaw_rad), sin(yaw_rad)

    Rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]
    Rz = [[cp, -sp, 0], [sp, cp, 0], [0, 0, 1]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]

    def mat_mul(A, B):
        result = [[0]*3 for _ in range(3)]
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    result[i][j] += A[i][k] * B[k][j]
        return result

    R = mat_mul(mat_mul(Rx, Rz), Ry)
    _rot_cache = {"key": key, "matrix": R}
    return R


def apply_body_rotation(points: list, pitch: float, roll: float, yaw: float, center: list) -> list:
    """Apply body rotation to points. points is list of [x,y,z] lists."""
    if pitch == 0 and roll == 0 and yaw == 0:
        return points

    R = _get_rotation_matrix(pitch, roll, yaw)
    rotated = []
    for p in points:
        d = [p[i] - center[i] for i in range(3)]
        r = [sum(R[i][j] * d[j] for j in range(3)) + center[i] for i in range(3)]
        rotated.append(r)
    return rotated


def compute_all_leg_points(servo_angles: dict, body_y: float = None,
                           body_pitch: float = 0, body_roll: float = 0,
                           body_yaw: float = 0) -> dict:
    """Compute all leg joint positions. Returns dict keyed by leg_id."""
    if body_y is None:
        body_y = UPPER_LEG_LENGTH + LOWER_LEG_LENGTH

    hx = BODY_LENGTH / 2
    hz = BODY_WIDTH / 2

    hip_origins = {
        "FL": [hx, body_y, hz],
        "FR": [hx, body_y, -hz],
        "RL": [-hx, body_y, hz],
        "RR": [-hx, body_y, -hz],
    }

    center = [0, body_y, 0]
    has_rotation = body_pitch != 0 or body_roll != 0 or body_yaw != 0

    # Batch rotate all 4 hip origins at once (1 call instead of 4)
    if has_rotation:
        leg_order = ["FL", "FR", "RL", "RR"]
        origins_list = [hip_origins[lid] for lid in leg_order]
        rotated_origins = apply_body_rotation(origins_list, body_pitch, body_roll, body_yaw, center)
        for i, lid in enumerate(leg_order):
            hip_origins[lid] = rotated_origins[i]

    result = {}
    all_points_to_rotate = []

    for leg_id, config in LEG_CONFIG.items():
        channels = config["channels"]
        is_left = config["side"] == "left"

        hip_angle = get_servo_angle(servo_angles, channels[0])
        knee_angle = get_servo_angle(servo_angles, channels[1])
        ankle_angle = get_servo_angle(servo_angles, channels[2])

        leg_pts = calculate_leg_points(hip_origins[leg_id], hip_angle, knee_angle, ankle_angle, is_left)
        result[leg_id] = leg_pts

        if has_rotation:
            for key in ["hip_end", "knee_end", "foot_end"]:
                all_points_to_rotate.append((leg_id, key, leg_pts[key]))

    # Batch rotate all 12 leg points at once (1 call instead of 12)
    if has_rotation and all_points_to_rotate:
        points = [p for _, _, p in all_points_to_rotate]
        rotated = apply_body_rotation(points, body_pitch, body_roll, body_yaw, center)
        for i, (leg_id, key, _) in enumerate(all_points_to_rotate):
            result[leg_id][key] = rotated[i]

    return result, body_y
