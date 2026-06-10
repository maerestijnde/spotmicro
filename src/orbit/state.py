"""
Orbit state management - RobotState dataclass and async API client.

Ported from nicegui_app.py with enhancements for the Orbit UI.
WebSocket telemetry subscription replaces fast polling for real-time data.
"""
import os
import time
import socket
import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, List

import httpx

log = logging.getLogger("orbit.state")

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
WS_URL = API_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/telemetry"

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

    # E-stop state (from telemetry)
    estop: bool = False

    # Gait mode from telemetry
    gait_mode: str = "angle"

    # Shadow comparison
    shadow_compare: bool = False
    shadow_max: dict = field(default_factory=dict)  # {"hip": X, "knee": X, "ankle": X}

    # WS connection state
    ws_connected: bool = False

    # Subscriber callbacks: list of async callables called on each telemetry frame
    _telemetry_subscribers: List[Callable] = field(default_factory=list)
    # Subscriber callbacks for discrete events
    _event_subscribers: List[Callable] = field(default_factory=list)

    def subscribe(self, callback: Callable):
        """Register a coroutine called on every telemetry frame: async def cb(frame: dict)."""
        if callback not in self._telemetry_subscribers:
            self._telemetry_subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        if callback in self._telemetry_subscribers:
            self._telemetry_subscribers.remove(callback)

    def subscribe_scoped(self, callback: Callable, client) -> None:
        """Subscribe + auto-unsubscribe when the NiceGUI client disconnects.

        Prevents subscriber accumulation when users navigate between pages.
        Usage:
            state.subscribe_scoped(my_callback, client)
        """
        self.subscribe(callback)
        async def _cleanup():
            self.unsubscribe(callback)
        client.on_disconnect(_cleanup)

    def subscribe_events(self, callback: Callable):
        """Register a coroutine called on discrete events: async def cb(event: dict)."""
        if callback not in self._event_subscribers:
            self._event_subscribers.append(callback)

    async def _apply_telemetry(self, frame: dict):
        """Update state fields from a telemetry frame received via WebSocket."""
        self.connected = True
        self.ws_connected = True
        self.servo_angles = {int(k): v for k, v in frame.get("servos", {}).items()}
        imu = frame.get("imu", {})
        self.pitch = imu.get("pitch", self.pitch)
        self.roll = imu.get("roll", self.roll)
        now = time.time()
        self.pitch_history.append(self.pitch)
        self.roll_history.append(self.roll)
        self.time_history.append(now)

        gait = frame.get("gait", {})
        self.walking = gait.get("running", self.walking)
        self.gait_mode = gait.get("mode", self.gait_mode)
        self.shadow_compare = gait.get("shadow_compare", self.shadow_compare)
        if "shadow_max" in gait:
            self.shadow_max = gait["shadow_max"]

        stab = frame.get("stability", {})
        self.stability_state = stab.get("state", self.stability_state)

        self.estop = frame.get("estop", self.estop)

        # Notify subscribers
        for cb in list(self._telemetry_subscribers):
            try:
                await cb(frame)
            except Exception as e:
                log.debug(f"Telemetry subscriber error: {e}")

    async def _apply_event(self, event: dict):
        """Handle a discrete event message from the telemetry WebSocket."""
        name = event.get("name", "")
        data = event.get("data", {})
        self.activity_log.append({
            "timestamp": time.time(),
            "tag": name,
            "message": name.replace("_", " ").title(),
        })
        self.event_history.append({"t": time.time(), "tag": name})
        if name.startswith("estop"):
            self.estop = (name == "estop")
        for cb in list(self._event_subscribers):
            try:
                await cb(event)
            except Exception as e:
                log.debug(f"Event subscriber error: {e}")

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


async def start_telemetry_ws():
    """
    Background asyncio task: connect to /ws/telemetry with auto-reconnect.
    Updates `state` fields directly; subscribers are notified on each frame.
    Falls back gracefully if the websockets library is not installed.
    """
    try:
        import websockets
    except ImportError:
        log.warning("websockets library not installed — telemetry WS disabled, using polling fallback")
        return

    retry_delay = 2.0
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
                log.info(f"Telemetry WS connected: {WS_URL}")
                state.ws_connected = True
                retry_delay = 2.0  # reset on success
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") == "telemetry":
                        await state._apply_telemetry(msg)
                    elif msg.get("type") == "event":
                        await state._apply_event(msg)
        except Exception as e:
            log.debug(f"Telemetry WS disconnected: {e} — retrying in {retry_delay}s")
            state.ws_connected = False
            state.connected = False
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 1.5, 30.0)  # exponential backoff, max 30s


# Module-level singleton
state = RobotState()
