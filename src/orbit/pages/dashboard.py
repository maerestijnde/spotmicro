"""
Orbit UI - Dashboard page: Hero 3D view + status bar + controls + activity feed.
"""
from nicegui import ui

from orbit.layout import create_shell
from orbit.theme import ACCENT_CYAN, STATUS_GREEN, STATUS_YELLOW, STATUS_RED, TEXT_MUTED
from orbit.state import state
from orbit.scene import RobotScene
from orbit.components.status_bar import create_status_bar, update_badge
from orbit.components.activity_feed import create_activity_feed, refresh_feed
from orbit.components.gait_controls import create_gait_controls
from orbit.components.pose_selector import create_pose_selector
from orbit.components.balance_panel import create_balance_panel
from orbit.components.body_controls import create_body_controls
from orbit.components.shadow_panel import create_shadow_panel


@ui.page("/")
async def dashboard_page():
    refs = create_shell(page_title="Dashboard")

    robot_scene = RobotScene()

    # ---- Status bar ----
    badges = create_status_bar()

    # ---- Main layout: 3D hero (left) + controls (right) ----
    with ui.row().classes("w-full gap-4").style("flex-wrap: nowrap"):
        # Left column: 3D scene (~65%)
        with ui.column().classes("flex-grow"):
            with ui.card().classes("w-full"):
                ui.label("3D Robot View").classes("text-gray-400 text-sm mb-1")
                robot_scene.create(height=450)

        # Right column: controls (~35%)
        with ui.column().style("min-width: 320px; max-width: 380px"):
            # Walking controls
            with ui.card().classes("w-full mb-3"):
                ui.label("Walking").classes("text-gray-300 font-bold mb-2")
                create_gait_controls()

            # Poses
            with ui.card().classes("w-full mb-3"):
                create_pose_selector()

            # Balance
            with ui.card().classes("w-full mb-3"):
                ui.label("Balance").classes("text-gray-300 font-bold mb-2")
                balance_switch = create_balance_panel()

            # IK Shadow compare
            with ui.card().classes("w-full mb-3"):
                create_shadow_panel()

            # Body control
            with ui.card().classes("w-full"):
                ui.label("Body Control").classes("text-gray-300 font-bold mb-2")
                create_body_controls()

    # ---- Activity feed (bottom) ----
    feed_container = create_activity_feed()

    # ---- WS subscriber + fallback timer ----
    _last_feed_len = [0]

    def _refresh_ui():
        """Update all UI elements from current state. Called by WS subscriber or fallback timer."""
        # Connection badge
        ws_ok = state.ws_connected
        refs["connection_badge"].text = "Connected" if state.connected else "Disconnected"
        refs["connection_badge"]._props["color"] = "green" if ws_ok else ("orange" if state.connected else "red")
        refs["connection_badge"].update()

        # Footer pitch/roll
        refs["pitch_footer"].text = f"P: {state.pitch:.1f}"
        refs["roll_footer"].text = f"R: {state.roll:.1f}"

        # Footer uptime
        refs["uptime_label"].text = state.uptime

        # Status badges
        stab_label, stab_color = state.get_stability_display()
        update_badge(badges["stability"], f"Stability: {stab_label}", stab_color)
        update_badge(
            badges["walking"],
            "Walking" if state.walking else "Stopped",
            STATUS_GREEN if state.walking else TEXT_MUTED,
        )
        update_badge(
            badges["imu"],
            f"IMU: {state.pitch:.0f}/{state.roll:.0f}",
            ACCENT_CYAN,
        )

        # Activity feed (only refresh when new events arrive)
        current_len = len(state.activity_log)
        if current_len != _last_feed_len[0]:
            _last_feed_len[0] = current_len
            refresh_feed(feed_container, state.activity_log)

    async def on_telemetry(frame: dict):
        """Called by WS subscriber on every telemetry frame (~10Hz from backend)."""
        robot_scene.update(state.servo_angles, state.pitch, state.roll)
        _refresh_ui()

    # Register subscriber — unregister on page leave (NiceGUI handles cleanup via weak refs)
    state.subscribe(on_telemetry)

    async def slow_update():
        """2s polling: fetch slow data that isn't in telemetry (gait/balance/stability details)."""
        await state.update_slow()

        balance_switch.value = state.balance_enabled

        # Footer stability badge
        stab_label, stab_color = state.get_stability_display()
        color_map = {
            "#00ff88": "green", "#ff8800": "orange", "#ff2244": "red",
        }
        refs["stability_footer_badge"].text = stab_label
        refs["stability_footer_badge"]._props["color"] = color_map.get(stab_color, "red")
        refs["stability_footer_badge"].update()

        update_badge(
            badges["balance"],
            f"Balance {'ON' if state.balance_enabled else 'OFF'}",
            STATUS_GREEN if state.balance_enabled else TEXT_MUTED,
        )

    async def fallback_fast():
        """Fallback 0.5s polling: only active when WS is not connected."""
        if not state.ws_connected:
            await state.update_fast()
            _refresh_ui()

    ui.timer(0.5, fallback_fast)   # Only does work when WS is down
    ui.timer(2.0, slow_update)
