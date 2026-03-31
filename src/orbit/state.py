"""
Orbit state management - RobotState dataclass and async API client.

Ported from nicegui_app.py with enhancements for the Orbit UI.
"""
import os
import time
import socket
import asyncio
from collections import deque
from dataclasses import dataclass, field

import httpx

# ============================================================================
# CONFIGURATION
# ============================================================================

SERVO_NAMES = {
    0: "FL Hip", 1: "FL Knee", 2: "FL Ankle",
    3: "FR Hip", 4: "FR Knee", 5: "FR Ankle",
    6: "RL Hip", 7: "RL Knee", 8: "RL Ankle",
    9: "RR Hip", 10: "RR Knee", 11: "RR Ankle",
}

LEG_CONFIG = {
    "FL": {"channels": [0, 1, 2], "color": "#ff4444", "side": "left", "end": "front"},
    "FR": {"channels": [3, 4, 5], "color": "#44ff44", "side": "right", "end": "front"},
    "RL": {"channels": [6, 7, 8], "color": "#4444ff", "side": "left", "end": "rear"},
    "RR": {"channels": [9, 10, 11], "color": "#ffaa44", "side": "right", "end": "rear"},
}

# Stability display colors
COLOR_SUCCESS = "#00ff88"
COLOR_WARNING = "#ff8800"
COLOR_DANGER = "#ff2244"


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
# ROBOT STATE
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

    # Activity log for the activity feed panel
    activity_log: deque = field(default_factory=lambda: deque(maxlen=100))

    # Controller status
    controller_connected: bool = False

    # Uptime tracking
    uptime_start: float = field(default_factory=time.time)

    # Slider fight prevention: {channel: last_user_touch_time}
    slider_touch_times: dict = field(default_factory=dict)

    # Busy guards to prevent overlapping timer ticks
    _fast_updating: bool = False
    _slow_updating: bool = False

    @property
    def uptime(self) -> str:
        """Formatted uptime string."""
        elapsed = int(time.time() - self.uptime_start)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"

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
                    # Also add to activity log
                    self.activity_log.append({
                        "timestamp": ev["t"],
                        "tag": ev["tag"],
                        "message": ev.get("msg", ev["tag"]),
                    })
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


# Module-level singleton
state = RobotState()
