"""
Orbit pose selector - Preset pose grid and custom pose cards.
"""
from nicegui import ui

from orbit.state import api_get, api_post


def create_pose_selector():
    """Create preset pose grid and custom pose list. Returns None."""
    # Preset poses
    ui.label("Presets").classes("text-gray-300 font-bold mb-2")
    with ui.grid(columns=2).classes("w-full gap-2"):
        for pose in ["neutral", "stand", "sit", "rest"]:
            async def apply_pose(p=pose):
                result = await api_post(f"/api/pose/{p}")
                if result is not None:
                    ui.notify(f"Pose: {p}", type="positive")
                else:
                    ui.notify(f"Pose '{p}' failed", type="negative")
            ui.button(pose.title(), on_click=apply_pose).props("dense unelevated outline").classes("w-full")

    ui.separator().classes("my-3")

    # Custom poses
    ui.label("Custom Poses").classes("text-gray-300 font-bold mb-2")
    custom_container = ui.column().classes("w-full")

    async def refresh_custom():
        custom_container.clear()
        with custom_container:
            data = await api_get("/api/custom_poses")
            custom_poses = data.get("poses", {}) if data else {}

            if custom_poses:
                with ui.grid(columns=2).classes("w-full gap-2"):
                    for pose_name in custom_poses:
                        async def load_pose(name=pose_name):
                            await api_post(f"/api/custom_poses/{name}/execute")
                            ui.notify(f"Loaded {name}", type="positive")
                        ui.button(pose_name, on_click=load_pose).props("dense unelevated outline").classes("w-full")
            else:
                ui.label("No custom poses saved").classes("text-gray-500 text-sm")

    # Load on creation
    ui.timer(0.1, refresh_custom, once=True)
