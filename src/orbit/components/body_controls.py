"""
Orbit body controls - Height/Pitch/Roll/Yaw sliders with Apply/Reset.
"""
from math import radians

from nicegui import ui

from orbit.state import api_post


def create_body_controls():
    """Create body orientation sliders with Apply/Reset. Returns None."""
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
