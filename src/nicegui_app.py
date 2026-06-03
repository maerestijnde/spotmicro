#!/usr/bin/env python3
"""
MicroSpot NiceGUI UI - Real-time robot control dashboard

WebSocket-driven UI built on NiceGUI (FastAPI + Vue/Quasar + Three.js).
Connects to the existing FastAPI backend at port 8000 via httpx async REST.

Usage:
    cd src && python3 nicegui_app.py
    Open http://localhost:8502
"""
import os
import sys
import time
import socket
import asyncio
from math import radians, cos, sin, degrees
from collections import deque
from dataclasses import dataclass, field

import httpx
from nicegui import ui, app

# ============================================================================
# CONFIGURATION
# ============================================================================

def get_backend_url():
    """Get backend API URL from environment or auto-detect."""
    if "MICROSPOT_BACKEND" in os.environ:
        return os.environ["MICROSPOT_BACKEND"]
    try:
        hostname = socket.gethostname()
        return f"http://{hostname}:8000"
    except Exception:
        return "http://localhost:8000"

API_URL = get_backend_url()

# Colors
COLOR_BG = "#0a0a1a"
COLOR_CARD = "#111125"
COLOR_ACCENT = "#00d4ff"
COLOR_SUCCESS = "#00ff88"
COLOR_WARNING = "#ff8800"
COLOR_DANGER = "#ff2244"
COLOR_TEXT = "#e0e0e0"
COLOR_MUTED = "#888899"

# Leg colors (matching robot_3d.py)
LEG_COLORS = {"FL": "#ff4444", "FR": "#44ff44", "RL": "#4444ff", "RR": "#ffaa44"}

# ============================================================================
# ROBOT DIMENSIONS (meters) - from robot_3d.py
# ============================================================================

BODY_LENGTH = 0.186
BODY_WIDTH = 0.078
HIP_LENGTH = 0.055
UPPER_LEG_LENGTH = 0.1075
LOWER_LEG_LENGTH = 0.130

LEG_CONFIG = {
    "FL": {"channels": [0, 1, 2], "color": "#ff4444", "side": "left", "end": "front"},
    "FR": {"channels": [3, 4, 5], "color": "#44ff44", "side": "right", "end": "front"},
    "RL": {"channels": [6, 7, 8], "color": "#4444ff", "side": "left", "end": "rear"},
    "RR": {"channels": [9, 10, 11], "color": "#ffaa44", "side": "right", "end": "rear"},
}

SERVO_NAMES = {
    0: "FL Hip", 1: "FL Knee", 2: "FL Ankle",
    3: "FR Hip", 4: "FR Knee", 5: "FR Ankle",
    6: "RL Hip", 7: "RL Knee", 8: "RL Ankle",
    9: "RR Hip", 10: "RR Knee", 11: "RR Ankle",
}

# ============================================================================
# FORWARD KINEMATICS - ported from robot_3d.py
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

# ============================================================================
# ASYNC HTTP HELPERS
# ============================================================================

http_client: httpx.AsyncClient = None


async def ensure_client():
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(base_url=API_URL, timeout=5.0)
    return http_client


async def api_get(path: str) -> dict | None:
    try:
        client = await ensure_client()
        resp = await client.get(path)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[API] GET {path} -> {resp.status_code}")
    except Exception as e:
        print(f"[API] GET {path} failed: {e}")
    return None


async def api_post(path: str, json: dict = None) -> dict | None:
    try:
        client = await ensure_client()
        resp = await client.post(path, json=json or {})
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[API] POST {path} -> {resp.status_code}")
    except Exception as e:
        print(f"[API] POST {path} failed: {e}")
    return None

# ============================================================================
# ROBOT STATE - centralized state updated by timers
# ============================================================================

@dataclass
class RobotState:
    connected: bool = False
    servo_angles: dict = field(default_factory=dict)
    pitch: float = 0.0
    roll: float = 0.0
    walking: bool = False
    balance_enabled: bool = False
    balance_available: bool = False
    stability_state: str = "unknown"
    body: dict = field(default_factory=dict)
    gait_params: dict = field(default_factory=dict)
    tuning: dict = field(default_factory=dict)

    # IMU history for charting
    pitch_history: deque = field(default_factory=lambda: deque(maxlen=200))
    roll_history: deque = field(default_factory=lambda: deque(maxlen=200))
    time_history: deque = field(default_factory=lambda: deque(maxlen=200))

    # Event markers for chart overlay
    event_history: deque = field(default_factory=lambda: deque(maxlen=50))
    _last_event_ts: float = 0.0

    # Slider fight prevention: {channel: last_user_touch_time}
    slider_touch_times: dict = field(default_factory=dict)

    # Busy guards to prevent overlapping timer ticks
    _fast_updating: bool = False
    _slow_updating: bool = False

    async def update_fast(self):
        """Called at 5Hz - status + IMU angles + events (parallel)."""
        if self._fast_updating:
            return
        self._fast_updating = True
        try:
            since = self._last_event_ts
            status, angles, events = await asyncio.gather(
                api_get("/api/status"),
                api_get("/api/balance/angles"),
                api_get(f"/api/events/recent?since={since}"),
            )
            if status:
                self.connected = True
                self.servo_angles = status.get("angles", {})
            else:
                self.connected = False

            if angles:
                self.pitch = angles.get("pitch", 0)
                self.roll = angles.get("roll", 0)
                now = time.time()
                self.pitch_history.append(self.pitch)
                self.roll_history.append(self.roll)
                self.time_history.append(now)

            if events:
                for ev in events:
                    self.event_history.append(ev)
                    if ev["t"] > self._last_event_ts:
                        self._last_event_ts = ev["t"]
        finally:
            self._fast_updating = False

    async def update_slow(self):
        """Called at 0.5Hz - gait/balance/stability (parallel)."""
        if self._slow_updating:
            return
        self._slow_updating = True
        try:
            gait, bal, stab = await asyncio.gather(
                api_get("/api/gait/status"),
                api_get("/api/balance/status"),
                api_get("/api/stability"),
            )
            if gait:
                self.walking = gait.get("running", False) or gait.get("walking", False)
                self.gait_params = gait
            if bal:
                self.balance_enabled = bal.get("enabled", False)
                self.balance_available = bal.get("available", False)
            if stab:
                self.stability_state = stab.get("state", "unknown")
        finally:
            self._slow_updating = False

    def get_stability_display(self) -> tuple:
        """Returns (label, color) for stability state."""
        max_tilt = max(abs(self.pitch), abs(self.roll))
        if max_tilt < 10:
            return "STABLE", COLOR_SUCCESS
        elif max_tilt < 25:
            return "WARNING", COLOR_WARNING
        elif max_tilt < 35:
            return "CRITICAL", COLOR_DANGER
        else:
            return "EMERGENCY", "#dc2626"

    def can_update_slider(self, channel: int) -> bool:
        """Check if timer can update slider (>1s since last user touch)."""
        last_touch = self.slider_touch_times.get(channel, 0)
        return (time.time() - last_touch) > 1.0

    def mark_slider_touched(self, channel: int):
        self.slider_touch_times[channel] = time.time()


# Per-client state stored in app.storage.user
state = RobotState()

# ============================================================================
# CUSTOM CSS
# ============================================================================

CUSTOM_CSS = """
<style>
:root {
    --bg-dark: #0a0a1a;
    --card-bg: #111125;
    --accent: #00d4ff;
    --success: #00ff88;
    --warning: #ff8800;
    --danger: #ff2244;
}
body, .q-page, .nicegui-content {
    background-color: var(--bg-dark) !important;
}
.q-card {
    background-color: var(--card-bg) !important;
    border: 1px solid #222244 !important;
    border-radius: 12px !important;
}
.q-drawer {
    background-color: #0d0d22 !important;
}
.q-toolbar {
    background-color: #0d0d22 !important;
}
.q-btn--flat.text-white:hover {
    background: rgba(0, 212, 255, 0.1) !important;
}
.glow-slider .q-slider__thumb {
    box-shadow: 0 0 8px var(--accent) !important;
}
.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 0.8rem;
    text-transform: uppercase;
}
.leg-card-fl { border-left: 4px solid #ff4444 !important; }
.leg-card-fr { border-left: 4px solid #44ff44 !important; }
.leg-card-rl { border-left: 4px solid #4444ff !important; }
.leg-card-rr { border-left: 4px solid #ffaa44 !important; }
.emergency-btn {
    animation: pulse-red 2s infinite;
}
@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 5px rgba(255, 34, 68, 0.5); }
    50% { box-shadow: 0 0 20px rgba(255, 34, 68, 0.8); }
}
</style>
"""

# ============================================================================
# 3D SCENE BUILDER
# ============================================================================

class RobotScene:
    """Manages the Three.js 3D scene for the robot visualization.

    Uses object pooling: body, head, joint spheres and ground are created once
    and moved each frame.  Only leg-segment lines are recreated (NiceGUI lines
    don't support endpoint updates).  Change detection skips frames where
    nothing moved.
    """

    def __init__(self):
        self.scene: ui.scene = None
        self._last_hash = None
        # Pooled objects (created once)
        self._body_box = None
        self._head_sphere = None
        self._ground = None
        self._joint_spheres: dict = {}   # (leg_id, joint_key) -> sphere
        # Lines must be recreated each frame
        self._lines: list = []
        self._initialized = False

    def create(self, height: int = 400) -> ui.scene:
        self.scene = ui.scene(width=-1, height=height, grid=True).classes("w-full rounded-lg")
        with self.scene:
            self.scene.move_camera(x=0.3, y=0.25, z=0.3, look_at_x=0, look_at_y=0.1, look_at_z=0)
        return self.scene

    def _init_objects(self, all_legs: dict, body_y: float, pitch: float, roll: float, yaw: float):
        """Create all pooled scene objects once."""
        with self.scene:
            # Static ground plane (never touched again)
            self._ground = self.scene.box(0.5, 0.001, 0.5).move(0, -0.001, 0).material("#1a1a2e", opacity=0.3)

            # Body box
            body_center = [0, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                body_center = apply_body_rotation([body_center], pitch, roll, yaw, [0, body_y, 0])[0]
            self._body_box = self.scene.box(BODY_LENGTH, 0.05, BODY_WIDTH).move(
                body_center[0], body_center[1], body_center[2]
            ).material("#1a3a5c", opacity=0.85)

            # Head sphere
            hx = BODY_LENGTH / 2
            head_pos = [hx + 0.02, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                head_pos = apply_body_rotation([head_pos], pitch, roll, yaw, [0, body_y, 0])[0]
            self._head_sphere = self.scene.sphere(0.012).move(
                head_pos[0], head_pos[1], head_pos[2]
            ).material("#ffcc00")

            # 16 joint spheres (4 legs x 4 joints)
            for leg_id, pts in all_legs.items():
                color = LEG_CONFIG[leg_id]["color"]
                for joint_key in ["hip_origin", "hip_end", "knee_end", "foot_end"]:
                    p = pts[joint_key]
                    size = 0.008 if joint_key != "foot_end" else 0.01
                    sphere = self.scene.sphere(size).move(p[0], p[1], p[2]).material(color)
                    self._joint_spheres[(leg_id, joint_key)] = sphere

            # Initial lines
            self._create_lines(all_legs)

        self._initialized = True

    def _create_lines(self, all_legs: dict):
        """(Re)create leg segment lines."""
        for line in self._lines:
            try:
                line.delete()
            except Exception:
                pass
        self._lines.clear()

        for leg_id, pts in all_legs.items():
            color = LEG_CONFIG[leg_id]["color"]
            for s, e in [("hip_origin", "hip_end"), ("hip_end", "knee_end"), ("knee_end", "foot_end")]:
                line = self.scene.line(pts[s], pts[e]).material(color)
                self._lines.append(line)

    def update(self, servo_angles: dict, pitch: float = 0, roll: float = 0, yaw: float = 0):
        """Update the robot geometry. Moves pooled objects instead of recreating."""
        if self.scene is None:
            return

        # Change detection - skip if nothing moved
        try:
            angle_vals = tuple(servo_angles.get(str(i), servo_angles.get(i, 90)) for i in range(12))
        except Exception:
            angle_vals = ()
        current_hash = hash((angle_vals, round(pitch, 1), round(roll, 1), round(yaw, 1)))
        if current_hash == self._last_hash:
            return
        self._last_hash = current_hash

        # Compute leg positions
        all_legs, body_y = compute_all_leg_points(servo_angles, body_pitch=pitch, body_roll=roll, body_yaw=yaw)

        # First call: create all objects
        if not self._initialized:
            self._init_objects(all_legs, body_y, pitch, roll, yaw)
            return

        with self.scene:
            # Move body box
            body_center = [0, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                body_center = apply_body_rotation([body_center], pitch, roll, yaw, [0, body_y, 0])[0]
            self._body_box.move(body_center[0], body_center[1], body_center[2])

            # Move head sphere
            hx = BODY_LENGTH / 2
            head_pos = [hx + 0.02, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                head_pos = apply_body_rotation([head_pos], pitch, roll, yaw, [0, body_y, 0])[0]
            self._head_sphere.move(head_pos[0], head_pos[1], head_pos[2])

            # Move joint spheres (16 moves instead of 16 delete+create)
            for leg_id, pts in all_legs.items():
                for joint_key in ["hip_origin", "hip_end", "knee_end", "foot_end"]:
                    p = pts[joint_key]
                    self._joint_spheres[(leg_id, joint_key)].move(p[0], p[1], p[2])

            # Recreate lines (NiceGUI lines can't update endpoints)
            self._create_lines(all_legs)


# ============================================================================
# SHARED LAYOUT
# ============================================================================

def create_header():
    """Create the app header with emergency stop."""
    with ui.header().classes("items-center justify-between px-4 py-2"):
        with ui.row().classes("items-center gap-4"):
            ui.label("MicroSpot").classes("text-xl font-bold text-white")
            ui.label("NiceGUI Dashboard").classes("text-sm text-gray-400")

        with ui.row().classes("items-center gap-3"):
            # Connection indicator
            connection_badge = ui.badge("--", color="gray").props("rounded")

            # Recording toggle
            rec_btn = ui.button("REC", color="gray").props("dense unelevated").classes("text-white font-bold")

            async def toggle_rec():
                status = await api_get("/api/recording/status")
                if status and status.get("recording"):
                    result = await api_post("/api/recording/stop")
                    if result and result.get("ok"):
                        rec_btn._props["color"] = "gray"
                        rec_btn.update()
                        ui.notify(f"Recording saved: {result.get('filename')}", type="positive")
                    else:
                        ui.notify("Stop recording failed", type="negative")
                else:
                    result = await api_post("/api/recording/start")
                    if result and result.get("ok"):
                        rec_btn._props["color"] = "red"
                        rec_btn.update()
                        ui.notify("Recording started", type="info")
                    else:
                        ui.notify("Start recording failed", type="negative")

            rec_btn.on_click(toggle_rec)

            # Emergency stop
            async def emergency_stop():
                await api_post("/api/gait/stop")
                for ch in range(12):
                    await api_post(f"/api/servo/{ch}/disable")
                ui.notify("EMERGENCY STOP - All servos disabled!", type="negative", position="top")

            ui.button("EMERGENCY STOP", on_click=emergency_stop, color="red").props(
                "dense unelevated"
            ).classes("emergency-btn text-white font-bold")

    return connection_badge, rec_btn


def create_sidebar():
    """Create the left navigation drawer."""
    with ui.left_drawer(value=True).classes("p-4").style("background-color: #0d0d22; width: 200px"):
        ui.label("Navigation").classes("text-gray-400 text-xs uppercase tracking-wider mb-3")

        nav_items = [
            ("/", "dashboard", "Control"),
            ("/servos", "settings_input_component", "Servos"),
            ("/tuning", "tune", "Tuning"),
            ("/imu", "speed", "IMU"),
            ("/settings", "settings", "Settings"),
        ]

        for href, icon, label in nav_items:
            ui.link(label, href).classes(
                "text-white no-underline block py-2 px-3 rounded-lg hover:bg-blue-900/30 "
                "transition-colors duration-200"
            ).style("font-size: 0.95rem")

        ui.separator().classes("my-4")
        ui.label(f"Backend").classes("text-gray-500 text-xs")
        ui.label(API_URL).classes("text-gray-400 text-xs break-all")


# ============================================================================
# PAGE: CONTROL DASHBOARD
# ============================================================================

@ui.page("/")
async def control_page():
    ui.dark_mode(True)
    ui.add_head_html(CUSTOM_CSS)
    connection_badge, rec_btn = create_header()
    create_sidebar()

    robot_scene = RobotScene()

    # Status bar
    with ui.row().classes("w-full gap-3 mb-3"):
        stability_badge = ui.badge("--", color="gray").props("rounded outline")
        walking_badge = ui.badge("Stopped", color="gray").props("rounded outline")
        balance_badge = ui.badge("Balance OFF", color="gray").props("rounded outline")
        pitch_label = ui.label("Pitch: 0.0").classes("text-cyan-400 ml-auto")
        roll_label = ui.label("Roll: 0.0").classes("text-orange-400")

    with ui.row().classes("w-full gap-4").style("flex-wrap: nowrap"):
        # Left: 3D Scene
        with ui.column().classes("flex-grow"):
            with ui.card().classes("w-full"):
                ui.label("3D Robot View").classes("text-gray-400 text-sm mb-1")
                scene = robot_scene.create(height=420)

        # Right: Controls
        with ui.column().style("min-width: 320px; max-width: 380px"):
            # Walking
            with ui.card().classes("w-full mb-3"):
                ui.label("Walking").classes("text-gray-300 font-bold mb-2")
                with ui.row().classes("gap-2 w-full"):
                    async def walk_start():
                        result = await api_post("/api/gait/start", {"direction": "forward"})
                        if result is not None:
                            ui.notify("Walking started", type="positive")
                        else:
                            ui.notify("Walk command failed", type="negative")

                    async def walk_stop():
                        result = await api_post("/api/gait/stop")
                        if result is not None:
                            ui.notify("Walking stopped", type="info")
                        else:
                            ui.notify("Stop command failed", type="negative")

                    async def walk_step():
                        result = await api_post("/api/gait/step")
                        if result is not None:
                            ui.notify("Step executed", type="info")
                        else:
                            ui.notify("Step command failed", type="negative")

                    ui.button("Walk", on_click=walk_start, color="green").props("dense unelevated").classes("flex-grow")
                    ui.button("Stop", on_click=walk_stop, color="red").props("dense unelevated").classes("flex-grow")
                    ui.button("Step", on_click=walk_step, color="blue").props("dense unelevated").classes("flex-grow")

            # Poses
            with ui.card().classes("w-full mb-3"):
                ui.label("Poses").classes("text-gray-300 font-bold mb-2")
                with ui.grid(columns=2).classes("w-full gap-2"):
                    for pose in ["neutral", "stand", "sit", "rest"]:
                        async def apply_pose(p=pose):
                            result = await api_post(f"/api/pose/{p}")
                            if result is not None:
                                ui.notify(f"Pose: {p}", type="positive")
                            else:
                                ui.notify(f"Pose '{p}' failed", type="negative")
                        ui.button(pose.title(), on_click=apply_pose).props("dense unelevated outline").classes("w-full")

            # Body control
            with ui.card().classes("w-full mb-3"):
                ui.label("Body Control").classes("text-gray-300 font-bold mb-2")

                body_height = ui.slider(min=20, max=160, value=100, step=5).props("label label-always color=cyan dense")
                ui.label("Height (mm)").classes("text-xs text-gray-500 -mt-1")

                body_pitch = ui.slider(min=-30, max=30, value=0, step=1).props("label label-always color=cyan dense")
                ui.label("Pitch").classes("text-xs text-gray-500 -mt-1")

                body_roll = ui.slider(min=-30, max=30, value=0, step=1).props("label label-always color=cyan dense")
                ui.label("Roll").classes("text-xs text-gray-500 -mt-1")

                body_yaw = ui.slider(min=-30, max=30, value=0, step=1).props("label label-always color=cyan dense")
                ui.label("Yaw").classes("text-xs text-gray-500 -mt-1")

                with ui.row().classes("gap-2 w-full mt-2"):
                    async def apply_body():
                        data = {
                            "y": body_height.value / 1000.0,
                            "phi": radians(body_roll.value),
                            "theta": radians(body_pitch.value),
                            "psi": radians(body_yaw.value),
                        }
                        await api_post("/api/body", data)
                        ui.notify("Body updated", type="positive")

                    async def reset_body():
                        await api_post("/api/body", {"y": 0.14, "phi": 0, "theta": 0, "psi": 0})
                        body_height.value = 140
                        body_pitch.value = 0
                        body_roll.value = 0
                        body_yaw.value = 0
                        ui.notify("Body reset", type="info")

                    ui.button("Apply", on_click=apply_body, color="blue").props("dense unelevated").classes("flex-grow")
                    ui.button("Reset", on_click=reset_body).props("dense unelevated outline").classes("flex-grow")

            # Balance
            with ui.card().classes("w-full"):
                ui.label("Balance").classes("text-gray-300 font-bold mb-2")
                balance_switch = ui.switch("Enable Balance", value=False)

                async def toggle_balance():
                    await api_post("/api/balance/enable", {"enable": balance_switch.value})
                    ui.notify(f"Balance {'enabled' if balance_switch.value else 'disabled'}", type="info")

                balance_switch.on_value_change(toggle_balance)

                async def calibrate_imu():
                    ui.notify("Hold robot still...", type="info", position="top", timeout=2000)
                    try:
                        client = await ensure_client()
                        resp = await asyncio.wait_for(
                            client.post("/api/balance/calibrate", json={}), timeout=5.0
                        )
                        if resp.status_code == 200:
                            ui.notify("IMU calibrated", type="positive")
                        else:
                            ui.notify("Calibration failed", type="negative")
                    except asyncio.TimeoutError:
                        ui.notify("Calibration timeout", type="warning")
                    except Exception as e:
                        ui.notify(f"Calibration error: {e}", type="negative")

                ui.button("Calibrate IMU", on_click=calibrate_imu).props("dense unelevated outline").classes("mt-2")

    # Timer: fast badges (5Hz) - API + badge updates only
    async def fast_badges():
        await state.update_fast()

        stab_label, stab_color = state.get_stability_display()
        stability_badge.text = stab_label
        stability_badge._props["color"] = "green" if stab_label == "STABLE" else "orange" if stab_label == "WARNING" else "red"
        stability_badge.update()

        walking_badge.text = "Walking" if state.walking else "Stopped"
        walking_badge._props["color"] = "green" if state.walking else "gray"
        walking_badge.update()

        balance_badge.text = f"Balance {'ON' if state.balance_enabled else 'OFF'}"
        balance_badge._props["color"] = "green" if state.balance_enabled else "gray"
        balance_badge.update()

        connection_badge.text = "Connected" if state.connected else "Disconnected"
        connection_badge._props["color"] = "green" if state.connected else "red"
        connection_badge.update()

        pitch_label.text = f"Pitch: {state.pitch:.1f}"
        roll_label.text = f"Roll: {state.roll:.1f}"

    # Timer: 3D scene (3Hz) - separate from badges to reduce contention
    async def scene_update():
        robot_scene.update(state.servo_angles, state.pitch, state.roll)

    async def slow_update():
        await state.update_slow()
        balance_switch.value = state.balance_enabled

    ui.timer(0.5, fast_badges)      # was 0.2 (5Hz) → 0.5 (2Hz) reduce Pi load
    ui.timer(0.5, scene_update)     # was 0.333 (3Hz) → 0.5 (2Hz)
    ui.timer(2.0, slow_update)


# ============================================================================
# PAGE: SERVO CONTROL
# ============================================================================

@ui.page("/servos")
async def servos_page():
    ui.dark_mode(True)
    ui.add_head_html(CUSTOM_CSS)
    connection_badge, rec_btn = create_header()
    create_sidebar()

    ui.label("Servo Control").classes("text-2xl font-bold text-white mb-4")

    # Quick actions
    with ui.row().classes("gap-2 mb-4"):
        async def reset_all():
            await api_post("/api/reset")
            ui.notify("All servos reset to 90", type="info")

        async def goto_neutrals():
            await api_post("/api/goto_neutrals")
            ui.notify("Moved to calibrated neutrals", type="positive")

        ui.button("Reset All 90", on_click=reset_all, color="orange").props("dense unelevated")
        ui.button("Go to Neutrals", on_click=goto_neutrals, color="blue").props("dense unelevated")

    # Servo sliders storage
    servo_sliders = {}
    servo_labels = {}

    # Create leg cards
    with ui.grid(columns=2).classes("w-full gap-4"):
        for leg_id, config in LEG_CONFIG.items():
            css_class = f"leg-card-{leg_id.lower()}"
            with ui.card().classes(f"w-full {css_class}"):
                ui.label(f"{leg_id} Leg").classes("text-lg font-bold mb-2").style(f"color: {config['color']}")

                joints = ["Hip", "Knee", "Ankle"]
                for j_idx, joint in enumerate(joints):
                    channel = config["channels"][j_idx]

                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(joint).classes("text-gray-400 w-16")
                        lbl = ui.label("90").classes("text-cyan-400 w-10 text-right font-mono")
                        servo_labels[channel] = lbl

                        slider = ui.slider(min=0, max=180, value=90, step=1).props(
                            "dense color=cyan label-always"
                        ).classes("flex-grow glow-slider")
                        servo_sliders[channel] = slider

                        # Slider change handler with throttle
                        async def on_servo_change(e, ch=channel, sl=slider, lb=lbl):
                            state.mark_slider_touched(ch)
                            lb.text = str(int(sl.value))
                            await api_post(f"/api/servo/{ch}", {"angle": sl.value})

                        slider.on("update:model-value", on_servo_change, throttle=0.05)

                    # Quick buttons
                    with ui.row().classes("gap-1 ml-20 -mt-1 mb-2"):
                        for angle in [0, 45, 90, 135, 180]:
                            async def set_angle(a=angle, ch=channel, sl=slider, lb=lbl):
                                state.mark_slider_touched(ch)
                                sl.value = a
                                lb.text = str(a)
                                await api_post(f"/api/servo/{ch}", {"angle": a})

                            ui.button(str(angle), on_click=set_angle).props("dense flat size=xs").classes("text-gray-400")

    # Calibration section
    ui.separator().classes("my-4")
    with ui.expansion("Calibration Tools", icon="build").classes("w-full"):
        with ui.card().classes("w-full"):
            ui.label("Fine-tune servo positions").classes("text-gray-400 mb-2")

            cal_channel = ui.select(
                {ch: name for ch, name in SERVO_NAMES.items()},
                value=0, label="Select Servo"
            ).classes("w-64")

            with ui.row().classes("gap-2 mt-2"):
                for delta in [-5, -1, 1, 5]:
                    sign = "+" if delta > 0 else ""

                    async def nudge(d=delta):
                        ch = cal_channel.value
                        if ch in servo_sliders:
                            new_val = max(0, min(180, servo_sliders[ch].value + d))
                            servo_sliders[ch].value = new_val
                            servo_labels[ch].text = str(int(new_val))
                            state.mark_slider_touched(ch)
                            await api_post(f"/api/servo/{ch}", {"angle": new_val})

                    ui.button(f"{sign}{delta}", on_click=nudge).props("dense unelevated outline")

            with ui.row().classes("gap-2 mt-3"):
                async def release_servo():
                    ch = cal_channel.value
                    await api_post(f"/api/servo/{ch}/disable")
                    ui.notify(f"Servo {ch} released", type="info")

                async def save_neutral():
                    ch = cal_channel.value
                    angle = servo_sliders[ch].value if ch in servo_sliders else 90
                    await api_post(f"/api/calibration/servo/{ch}", {"neutral_angle": angle})
                    await api_post("/api/calibration/save")
                    ui.notify(f"Neutral saved for servo {ch}: {angle}", type="positive")

                ui.button("Release Servo", on_click=release_servo, color="orange").props("dense unelevated")
                ui.button("Save as Neutral", on_click=save_neutral, color="green").props("dense unelevated")

    # Timer to update slider values from backend
    async def update_servos():
        await state.update_fast()
        connection_badge.text = "Connected" if state.connected else "Disconnected"
        connection_badge._props["color"] = "green" if state.connected else "red"
        connection_badge.update()

        for ch, slider in servo_sliders.items():
            if state.can_update_slider(ch):
                angle = get_servo_angle(state.servo_angles, ch)
                slider.value = angle
                if ch in servo_labels:
                    servo_labels[ch].text = str(int(angle))

    ui.timer(0.5, update_servos)    # was 0.2 (5Hz) → 0.5 (2Hz)


# ============================================================================
# PAGE: TUNING
# ============================================================================

@ui.page("/tuning")
async def tuning_page():
    ui.dark_mode(True)
    ui.add_head_html(CUSTOM_CSS)
    connection_badge, rec_btn = create_header()
    create_sidebar()

    ui.label("Tuning").classes("text-2xl font-bold text-white mb-4")

    # Fetch current tuning
    tuning = await api_get("/api/tuning") or {}

    with ui.tabs().classes("w-full").props("dense active-color=cyan indicator-color=cyan") as tabs:
        tab_stand = ui.tab("Stand")
        tab_balance = ui.tab("Balance")
        tab_gait = ui.tab("Gait")

    with ui.tab_panels(tabs, value=tab_stand).classes("w-full"):
        # Stand tab
        with ui.tab_panel(tab_stand):
            with ui.card().classes("w-full"):
                ui.label("Stand Position").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust how low the robot bends its knees when standing").classes("text-gray-400 text-sm mb-3")

                knee_bend = ui.slider(
                    min=0, max=60, value=int(tuning.get("knee_bend", 40)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Knee Bend (degrees)").classes("text-xs text-gray-500")

                with ui.row().classes("gap-2 mt-4"):
                    async def preview_stand():
                        await api_post("/api/gait/stand_height", {"knee_bend": knee_bend.value})
                        await api_post("/api/gait/preview_stand")
                        ui.notify("Preview applied", type="positive")

                    async def save_stand():
                        await api_post("/api/tuning/knee_bend", {"value": knee_bend.value})
                        ui.notify(f"Knee bend saved: {knee_bend.value}", type="positive")

                    ui.button("Preview", on_click=preview_stand).props("dense unelevated outline").classes("flex-grow")
                    ui.button("Save", on_click=save_stand, color="green").props("dense unelevated").classes("flex-grow")

        # Balance tab
        with ui.tab_panel(tab_balance):
            with ui.card().classes("w-full"):
                ui.label("Balance Settings").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust how aggressively the robot compensates for tilt").classes("text-gray-400 text-sm mb-3")

                kp_slider = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("balance_kp", 0.5)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Kp (Proportional Gain)").classes("text-xs text-gray-500")

                pitch_gain = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("pitch_gain", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Pitch Gain").classes("text-xs text-gray-500")

                roll_gain = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("roll_gain", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Roll Gain").classes("text-xs text-gray-500")

                with ui.row().classes("gap-2 mt-4"):
                    async def apply_balance():
                        await api_post("/api/balance/kp", {"kp": kp_slider.value})
                        ui.notify(f"Kp applied: {kp_slider.value}", type="info")

                    async def save_balance():
                        await api_post("/api/tuning/balance_kp", {"value": kp_slider.value})
                        await api_post("/api/tuning/pitch_gain", {"value": pitch_gain.value})
                        await api_post("/api/tuning/roll_gain", {"value": roll_gain.value})
                        ui.notify("Balance settings saved", type="positive")

                    ui.button("Apply", on_click=apply_balance).props("dense unelevated outline").classes("flex-grow")
                    ui.button("Save", on_click=save_balance, color="green").props("dense unelevated").classes("flex-grow")

        # Gait tab
        with ui.tab_panel(tab_gait):
            with ui.card().classes("w-full"):
                ui.label("Gait Parameters").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust walking cycle timing and step geometry").classes("text-gray-400 text-sm mb-3")

                cycle_time = ui.slider(
                    min=0.4, max=1.5, value=float(tuning.get("cycle_time", 0.8)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Cycle Time (seconds)").classes("text-xs text-gray-500")

                step_height = ui.slider(
                    min=10, max=40, value=int(tuning.get("step_height", 25)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Step Height (degrees)").classes("text-xs text-gray-500")

                step_length = ui.slider(
                    min=5, max=30, value=int(tuning.get("step_length", 15)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Step Length (degrees)").classes("text-xs text-gray-500")

                speed_slider = ui.slider(
                    min=0.5, max=2.0, value=float(tuning.get("speed", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Speed Multiplier").classes("text-xs text-gray-500")

                with ui.row().classes("gap-2 mt-4"):
                    async def apply_gait():
                        await api_post("/api/gait/params", {
                            "cycle_time": cycle_time.value,
                            "step_height": step_height.value,
                            "step_length": step_length.value,
                            "speed": speed_slider.value,
                        })
                        ui.notify("Gait parameters applied", type="info")

                    async def save_gait():
                        await api_post("/api/tuning/cycle_time", {"value": cycle_time.value})
                        await api_post("/api/tuning/step_height", {"value": step_height.value})
                        await api_post("/api/tuning/step_length", {"value": step_length.value})
                        await api_post("/api/tuning/speed", {"value": speed_slider.value})
                        ui.notify("Gait parameters saved", type="positive")

                    ui.button("Apply", on_click=apply_gait).props("dense unelevated outline").classes("flex-grow")
                    ui.button("Save", on_click=save_gait, color="green").props("dense unelevated").classes("flex-grow")

                # Presets
                ui.separator().classes("my-3")
                ui.label("Presets").classes("text-gray-300 font-bold mb-2")
                with ui.row().classes("gap-2"):
                    presets = {
                        "Slow": {"cycle_time": 1.2, "step_height": 20},
                        "Normal": {"cycle_time": 0.8, "step_height": 25},
                        "Fast": {"cycle_time": 0.5, "step_height": 30},
                    }
                    for name, params in presets.items():
                        async def apply_preset(p=params, n=name):
                            await api_post("/api/gait/params", p)
                            cycle_time.value = p["cycle_time"]
                            step_height.value = p["step_height"]
                            ui.notify(f"{n} preset applied", type="info")

                        ui.button(name, on_click=apply_preset).props("dense unelevated outline")

    # Connection update timer
    async def update_connection():
        await state.update_fast()
        connection_badge.text = "Connected" if state.connected else "Disconnected"
        connection_badge._props["color"] = "green" if state.connected else "red"
        connection_badge.update()

    ui.timer(2.0, update_connection)


# ============================================================================
# PAGE: IMU MONITOR
# ============================================================================

@ui.page("/imu")
async def imu_page():
    ui.dark_mode(True)
    ui.add_head_html(CUSTOM_CSS)
    connection_badge, rec_btn = create_header()
    create_sidebar()

    ui.label("IMU Monitor").classes("text-2xl font-bold text-white mb-4")

    with ui.row().classes("w-full gap-4").style("flex-wrap: nowrap"):
        # Left: Chart
        with ui.column().classes("flex-grow"):
            with ui.card().classes("w-full"):
                ui.label("Orientation (Real-time)").classes("text-gray-400 text-sm mb-2")

                chart = ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "legend": {
                        "data": ["Pitch", "Roll"],
                        "textStyle": {"color": "#999"},
                        "top": 0,
                    },
                    "grid": {"top": 30, "right": 20, "bottom": 30, "left": 50},
                    "xAxis": {
                        "type": "category",
                        "data": [],
                        "axisLabel": {"color": "#666"},
                        "axisLine": {"lineStyle": {"color": "#333"}},
                    },
                    "yAxis": {
                        "type": "value",
                        "min": -45,
                        "max": 45,
                        "axisLabel": {"color": "#666", "formatter": "{value}"},
                        "axisLine": {"lineStyle": {"color": "#333"}},
                        "splitLine": {"lineStyle": {"color": "#222"}},
                    },
                    "series": [
                        {
                            "name": "Pitch",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "lineStyle": {"color": "#00d4ff", "width": 2},
                            "itemStyle": {"color": "#00d4ff"},
                            "showSymbol": False,
                            "animation": True,
                            "animationDuration": 180,
                        },
                        {
                            "name": "Roll",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "lineStyle": {"color": "#ff8800", "width": 2},
                            "itemStyle": {"color": "#ff8800"},
                            "showSymbol": False,
                            "animation": True,
                            "animationDuration": 180,
                        },
                    ],
                    "backgroundColor": "transparent",
                }).classes("w-full").style("height: 350px")

        # Right: Current values
        with ui.column().style("min-width: 280px; max-width: 320px"):
            # Knobs for pitch/roll
            with ui.card().classes("w-full mb-3"):
                ui.label("Current Angles").classes("text-gray-400 text-sm mb-3")

                with ui.row().classes("justify-around w-full"):
                    with ui.column().classes("items-center"):
                        pitch_knob = ui.knob(0, min=-45, max=45, show_value=True, color="cyan", track_color="grey-8").props("size=90px thickness=0.2")
                        ui.label("Pitch").classes("text-cyan-400 text-sm mt-1")

                    with ui.column().classes("items-center"):
                        roll_knob = ui.knob(0, min=-45, max=45, show_value=True, color="orange", track_color="grey-8").props("size=90px thickness=0.2")
                        ui.label("Roll").classes("text-orange-400 text-sm mt-1")

            # Stability
            with ui.card().classes("w-full mb-3"):
                ui.label("Stability").classes("text-gray-400 text-sm mb-2")
                stab_badge = ui.badge("--", color="gray").props("rounded").classes("text-lg px-4 py-1")

            # Balance controls
            with ui.card().classes("w-full mb-3"):
                ui.label("Balance").classes("text-gray-400 text-sm mb-2")
                imu_balance_switch = ui.switch("Enable Balance", value=False)

                async def toggle_imu_balance():
                    try:
                        client = await ensure_client()
                        await asyncio.wait_for(
                            client.post("/api/balance/enable", json={"enable": imu_balance_switch.value}),
                            timeout=3.0
                        )
                    except Exception:
                        ui.notify("Balance toggle timeout", type="warning")

                imu_balance_switch.on_value_change(toggle_imu_balance)

                async def cal_imu():
                    ui.notify("Hold robot still...", type="info", position="top", timeout=2000)
                    try:
                        client = await ensure_client()
                        resp = await asyncio.wait_for(client.post("/api/balance/calibrate", json={}), timeout=5.0)
                        if resp.status_code == 200:
                            ui.notify("IMU calibrated", type="positive")
                        else:
                            ui.notify("Calibration failed", type="negative")
                    except asyncio.TimeoutError:
                        ui.notify("Calibration timeout", type="warning")
                    except Exception as e:
                        ui.notify(f"Calibration error: {e}", type="negative")

                ui.button("Calibrate IMU", on_click=cal_imu).props("dense unelevated outline").classes("w-full mt-2")

            # Kp control
            with ui.card().classes("w-full"):
                ui.label("Quick Kp Adjust").classes("text-gray-400 text-sm mb-2")
                kp_imu = ui.slider(min=0.1, max=2.0, value=0.5, step=0.1).props("label label-always color=cyan dense")

                async def save_kp_imu():
                    await api_post("/api/balance/kp", {"kp": kp_imu.value})
                    await api_post("/api/tuning/balance_kp", {"value": kp_imu.value})
                    ui.notify(f"Kp saved: {kp_imu.value}", type="positive")

                ui.button("Save Kp", on_click=save_kp_imu, color="green").props("dense unelevated").classes("w-full mt-2")

    # Timer: fast IMU data + chart (5Hz)
    async def update_imu_fast():
        await state.update_fast()

        connection_badge.text = "Connected" if state.connected else "Disconnected"
        connection_badge._props["color"] = "green" if state.connected else "red"
        connection_badge.update()

        pitch_knob.value = round(state.pitch, 1)
        roll_knob.value = round(state.roll, 1)

        if state.time_history:
            t0 = state.time_history[0]
            t_end = state.time_history[-1]
            x_data = [f"{(t - t0):.0f}" for t in state.time_history]
            pitch_data = [round(p, 1) for p in state.pitch_history]
            roll_data = [round(r, 1) for r in state.roll_history]

            # Build event markLines (vertical lines at event timestamps)
            mark_lines = []
            event_colors = {
                "gait_start": "#00ff88", "gait_stop": "#ff2244",
                "pose_": "#00d4ff", "balance_": "#ff8800", "imu_": "#aa44ff",
            }
            for ev in state.event_history:
                evt = ev["t"]
                if evt < t0 or evt > t_end:
                    continue
                x_val = f"{(evt - t0):.0f}"
                tag = ev["tag"]
                # Pick color by prefix
                color = "#888899"
                for prefix, c in event_colors.items():
                    if tag.startswith(prefix):
                        color = c
                        break
                # Short label (remove common prefixes)
                label = tag.replace("gait_", "").replace("pose_", "P:").replace("balance_", "B:")
                mark_lines.append({
                    "xAxis": x_val,
                    "label": {"formatter": label, "color": color, "fontSize": 10},
                    "lineStyle": {"color": color, "type": "dashed", "width": 1},
                })

            chart.options["xAxis"]["data"] = x_data
            chart.options["series"][0]["data"] = pitch_data
            chart.options["series"][1]["data"] = roll_data
            # Attach markLine to first series
            if mark_lines:
                chart.options["series"][0]["markLine"] = {
                    "symbol": "none",
                    "data": mark_lines,
                    "animation": False,
                }
            else:
                chart.options["series"][0].pop("markLine", None)
            chart.update()

    # Timer: slow stability/balance (2s)
    async def update_imu_slow():
        await state.update_slow()

        stab_label, stab_color = state.get_stability_display()
        stab_badge.text = stab_label
        color_map = {COLOR_SUCCESS: "green", COLOR_WARNING: "orange", COLOR_DANGER: "red"}
        stab_badge._props["color"] = color_map.get(stab_color, "red")
        stab_badge.update()

        imu_balance_switch.value = state.balance_enabled

    ui.timer(0.2, update_imu_fast)
    ui.timer(2.0, update_imu_slow)


# ============================================================================
# PAGE: SETTINGS
# ============================================================================

@ui.page("/settings")
async def settings_page():
    ui.dark_mode(True)
    ui.add_head_html(CUSTOM_CSS)
    connection_badge, rec_btn = create_header()
    create_sidebar()

    ui.label("Settings").classes("text-2xl font-bold text-white mb-4")

    with ui.tabs().classes("w-full").props("dense active-color=cyan indicator-color=cyan") as tabs:
        tab_controller = ui.tab("Controller")
        tab_poses = ui.tab("Custom Poses")
        tab_recordings = ui.tab("Recordings")
        tab_system = ui.tab("System")

    with ui.tab_panels(tabs, value=tab_controller).classes("w-full"):
        # Controller tab
        with ui.tab_panel(tab_controller):
            with ui.card().classes("w-full mb-4"):
                ui.label("PlayStation Controller").classes("text-lg font-bold text-white mb-2")
                ui.label("Works with PS4 (DualShock 4) and PS5 (DualSense)").classes("text-gray-400 text-sm mb-3")

                with ui.row().classes("gap-4"):
                    controller_badge = ui.badge("Checking...", color="gray").props("rounded")
                    listener_badge = ui.badge("Checking...", color="gray").props("rounded")

            with ui.card().classes("w-full"):
                ui.label("Controller Mapping").classes("text-lg font-bold text-white mb-3")

                with ui.row().classes("w-full gap-6"):
                    with ui.column().classes("flex-grow"):
                        ui.label("Movement").classes("text-gray-300 font-bold mb-1")
                        mapping_data_movement = [
                            ["Left Stick Up/Down", "Walk forward/backward"],
                            ["Left Stick Left/Right", "Lateral step"],
                            ["L2 / R2", "Turn left/right"],
                            ["X", "Single step forward"],
                            ["L3 Click", "Single step backward"],
                            ["Circle", "Stop"],
                        ]
                        with ui.element("table").classes("text-sm text-gray-300"):
                            for inp, action in mapping_data_movement:
                                with ui.element("tr"):
                                    with ui.element("td").classes("pr-4 py-1 font-bold text-cyan-400"):
                                        ui.label(inp)
                                    with ui.element("td").classes("py-1"):
                                        ui.label(action)

                        ui.separator().classes("my-3")
                        ui.label("Poses").classes("text-gray-300 font-bold mb-1")
                        mapping_data_poses = [
                            ["D-pad Up", "Stand"],
                            ["D-pad Down", "Sit"],
                            ["D-pad Left", "Rest"],
                            ["D-pad Right", "Neutral"],
                        ]
                        with ui.element("table").classes("text-sm text-gray-300"):
                            for inp, action in mapping_data_poses:
                                with ui.element("tr"):
                                    with ui.element("td").classes("pr-4 py-1 font-bold text-cyan-400"):
                                        ui.label(inp)
                                    with ui.element("td").classes("py-1"):
                                        ui.label(action)

                    with ui.column().classes("flex-grow"):
                        ui.label("Body Control").classes("text-gray-300 font-bold mb-1")
                        mapping_data_body = [
                            ["Right Stick", "Pitch / Roll"],
                            ["L2 / R2", "Yaw (+ turn)"],
                            ["L1", "Body LOWER"],
                            ["R1", "Body HIGHER"],
                            ["R3 Click", "Reset orientation"],
                        ]
                        with ui.element("table").classes("text-sm text-gray-300"):
                            for inp, action in mapping_data_body:
                                with ui.element("tr"):
                                    with ui.element("td").classes("pr-4 py-1 font-bold text-cyan-400"):
                                        ui.label(inp)
                                    with ui.element("td").classes("py-1"):
                                        ui.label(action)

                        ui.separator().classes("my-3")
                        ui.label("Other").classes("text-gray-300 font-bold mb-1")
                        mapping_data_other = [
                            ["Triangle", "Toggle balance"],
                            ["Square", "Go to neutrals"],
                            ["Share", "Calibrate IMU"],
                            ["Options", "EMERGENCY STOP"],
                        ]
                        with ui.element("table").classes("text-sm text-gray-300"):
                            for inp, action in mapping_data_other:
                                with ui.element("tr"):
                                    with ui.element("td").classes("pr-4 py-1 font-bold text-cyan-400"):
                                        ui.label(inp)
                                    with ui.element("td").classes("py-1"):
                                        ui.label(action)

        # Custom Poses tab
        with ui.tab_panel(tab_poses):
            poses_container = ui.column().classes("w-full")

            async def refresh_poses():
                poses_container.clear()
                with poses_container:
                    data = await api_get("/api/custom_poses")
                    custom_poses = data.get("poses", {}) if data else {}

                    if custom_poses:
                        ui.label("Saved Poses").classes("text-lg font-bold text-white mb-3")
                        with ui.grid(columns=3).classes("w-full gap-3"):
                            for pose_name, pose_data in custom_poses.items():
                                with ui.card().classes("w-full"):
                                    ui.label(pose_name).classes("font-bold text-white")
                                    desc = pose_data.get("description", "") if isinstance(pose_data, dict) else ""
                                    if desc:
                                        ui.label(desc).classes("text-gray-400 text-sm")
                                    with ui.row().classes("gap-2 mt-2"):
                                        async def load_pose(name=pose_name):
                                            await api_post(f"/api/custom_poses/{name}/execute")
                                            ui.notify(f"Loaded {name}", type="positive")

                                        async def delete_pose(name=pose_name):
                                            resp = await api_post(f"/api/custom_poses/{name}")  # DELETE not supported via helper
                                            try:
                                                client = await ensure_client()
                                                await client.delete(f"/api/custom_poses/{name}")
                                            except Exception:
                                                pass
                                            ui.notify(f"Deleted {name}", type="warning")
                                            await refresh_poses()

                                        ui.button("Load", on_click=load_pose, color="blue").props("dense unelevated size=sm")
                                        ui.button("Delete", on_click=delete_pose, color="red").props("dense unelevated outline size=sm")
                    else:
                        ui.label("No custom poses saved yet").classes("text-gray-400")

                    ui.separator().classes("my-4")
                    ui.label("Save Current Position").classes("text-lg font-bold text-white mb-3")

                    with ui.row().classes("gap-3 items-end"):
                        pose_name_input = ui.input("Pose Name", placeholder="e.g. my_stand").classes("w-48")
                        pose_desc_input = ui.input("Description", placeholder="e.g. Low stance").classes("w-64")

                        async def save_pose():
                            name = pose_name_input.value
                            if not name:
                                ui.notify("Enter a pose name", type="warning")
                                return
                            current = await api_get("/api/current_pose")
                            angles = current.get("angles", {}) if current else {}
                            await api_post(f"/api/custom_poses/{name}", {
                                "description": pose_desc_input.value or "Custom pose",
                                "angles": angles,
                            })
                            ui.notify(f"Saved '{name}'", type="positive")
                            pose_name_input.value = ""
                            pose_desc_input.value = ""
                            await refresh_poses()

                        ui.button("Save Current", on_click=save_pose, color="green").props("dense unelevated")

            await refresh_poses()

        # Recordings tab
        with ui.tab_panel(tab_recordings):
            recordings_container = ui.column().classes("w-full")

            async def refresh_recordings():
                recordings_container.clear()
                with recordings_container:
                    data = await api_get("/api/recordings")
                    recordings = data.get("recordings", []) if data else []

                    rec_status = await api_get("/api/recording/status")
                    is_recording = rec_status.get("recording", False) if rec_status else False

                    with ui.card().classes("w-full mb-4"):
                        ui.label("Data Recording").classes("text-lg font-bold text-white mb-2")
                        ui.label(
                            "Record servo angles and IMU data to CSV for analysis"
                        ).classes("text-gray-400 text-sm mb-3")

                        with ui.row().classes("items-center gap-3"):
                            rec_status_badge = ui.badge(
                                "Recording" if is_recording else "Idle",
                                color="red" if is_recording else "gray"
                            ).props("rounded")

                            if is_recording:
                                ui.label(f"File: {rec_status.get('filename', '?')}").classes("text-gray-400 text-sm")

                    if recordings:
                        with ui.card().classes("w-full"):
                            ui.label(f"Saved Recordings ({len(recordings)})").classes("text-lg font-bold text-white mb-3")
                            for rec in recordings:
                                with ui.row().classes("w-full items-center gap-3 py-2").style(
                                    "border-bottom: 1px solid #222244"
                                ):
                                    ui.label(rec["filename"]).classes("text-cyan-400 font-mono text-sm flex-grow")
                                    ui.label(f"{rec['size_kb']} KB").classes("text-gray-500 text-sm")

                                    async def download(fn=rec["filename"]):
                                        ui.download(f"{API_URL}/api/recordings/{fn}")

                                    ui.button("Download", on_click=download).props("dense flat size=sm color=cyan")
                    else:
                        ui.label("No recordings yet. Press REC in the header to start.").classes("text-gray-400")

            await refresh_recordings()

            ui.button("Refresh", on_click=refresh_recordings).props("dense unelevated outline").classes("mt-3")

        # System tab
        with ui.tab_panel(tab_system):
            with ui.card().classes("w-full mb-4"):
                ui.label("System Info").classes("text-lg font-bold text-white mb-3")

                status = await api_get("/api/status") or {}

                with ui.row().classes("gap-6"):
                    with ui.column():
                        hw = "Active" if status.get("hardware") else "Simulation"
                        hw_color = "green" if status.get("hardware") else "orange"
                        ui.label("Hardware").classes("text-gray-400 text-sm")
                        ui.badge(hw, color=hw_color).props("rounded")

                    with ui.column():
                        kin = "Available" if status.get("kinematics") else "Disabled"
                        kin_color = "green" if status.get("kinematics") else "gray"
                        ui.label("Kinematics").classes("text-gray-400 text-sm")
                        ui.badge(kin, color=kin_color).props("rounded")

                    with ui.column():
                        calib = status.get("calibration", {})
                        calibrated = sum(
                            1 for s in calib.get("servos", {}).values()
                            if isinstance(s, dict) and s.get("calibrated", False)
                        )
                        ui.label("Calibration").classes("text-gray-400 text-sm")
                        ui.linear_progress(value=calibrated / 12, show_value=False).props(
                            "color=cyan rounded size=20px"
                        ).classes("w-32")
                        ui.label(f"{calibrated}/12 servos").classes("text-xs text-gray-400")

                ui.separator().classes("my-3")
                ui.label(f"Backend: {API_URL}").classes("text-gray-400 text-sm")

            with ui.card().classes("w-full"):
                ui.label("Quick Actions").classes("text-lg font-bold text-white mb-3")

                with ui.row().classes("gap-3"):
                    async def test_api():
                        result = await api_get("/api/status")
                        if result:
                            ui.notify("API working!", type="positive")
                        else:
                            ui.notify("API connection failed", type="negative")

                    async def reset_servos():
                        await api_post("/api/reset")
                        ui.notify("Servos reset to 90", type="info")

                    async def export_cal():
                        data = await api_get("/api/calibration/export")
                        if data:
                            ui.notify("Calibration data exported (check backend logs)", type="positive")
                        else:
                            ui.notify("Export failed", type="negative")

                    ui.button("Test API", on_click=test_api).props("dense unelevated outline")
                    ui.button("Reset Servos 90", on_click=reset_servos, color="orange").props("dense unelevated")
                    ui.button("Export Calibration", on_click=export_cal).props("dense unelevated outline")

    # Connection update timer
    async def update_conn():
        s = await api_get("/api/status")
        connected = s is not None
        connection_badge.text = "Connected" if connected else "Disconnected"
        connection_badge._props["color"] = "green" if connected else "red"
        connection_badge.update()

    ui.timer(2.0, update_conn)


# ============================================================================
# APP STARTUP
# ============================================================================

app.on_shutdown(lambda: http_client.aclose() if http_client and not http_client.is_closed else None)

if __name__ in {"__main__", "__mp_main__"}:
    print(f"Starting MicroSpot NiceGUI UI on port 8502")
    print(f"Backend API: {API_URL}")
    ui.run(
        title="MicroSpot",
        port=8502,
        host="0.0.0.0",
        reload=False,
        show=False,
        favicon="🐕",
    )
