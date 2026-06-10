"""
Orbit gait control buttons - Walk/Stop/Step + mode selector.
"""
from nicegui import ui

from orbit.state import api_get, api_post, state
from orbit.theme import TEXT_MUTED, STATUS_GREEN


def create_gait_controls():
    """Create Walk/Stop/Step buttons + mode selector. Returns None."""
    # ---- Walk / Stop / Step ----
    with ui.row().classes("gap-2 w-full mb-2"):
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

    # ---- Gait mode selector ----
    mode_options = {"angle": "Angle-based", "ik": "IK", "crawl": "Crawl"}
    mode_select = ui.select(
        mode_options,
        value="angle",
        label="Gait mode",
    ).props("dense outlined").classes("w-full").style(f"color: {TEXT_MUTED}")

    async def _load_mode():
        data = await api_get("/api/gait/mode")
        if data:
            m = data.get("mode", "angle")
            if m in mode_options:
                mode_select.value = m

    async def _change_mode(e):
        if state.walking:
            ui.notify("Stop the gait before switching mode", type="warning")
            await _load_mode()  # revert the select
            return
        result = await api_post("/api/gait/mode", {"mode": mode_select.value})
        if result and result.get("success"):
            ui.notify(f"Mode → {mode_options.get(mode_select.value, mode_select.value)}", type="positive")
        else:
            ik_ok = (result or {}).get("ik_available", True)
            err = (result or {}).get("error", "")
            if not ik_ok and mode_select.value == "ik":
                ui.notify(
                    "IK not available — kinematics submodule missing or matplotlib not installed",
                    type="negative",
                )
            else:
                ui.notify(f"Mode switch failed: {err or 'unknown error'}", type="negative")
            await _load_mode()

    mode_select.on("update:model-value", _change_mode)

    # Update select whenever mode changes via telemetry
    async def _on_mode_telemetry(frame: dict):
        gait = frame.get("gait", {})
        new_mode = gait.get("mode", "angle")
        if new_mode in mode_options and mode_select.value != new_mode:
            mode_select.value = new_mode

    state.subscribe(_on_mode_telemetry)

    # Load initial mode
    ui.timer(0, _load_mode, once=True)
