"""
Orbit gait control buttons - Walk/Stop/Step.
"""
from nicegui import ui

from orbit.state import api_post


def create_gait_controls():
    """Create Walk/Stop/Step button row. Returns None."""
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
