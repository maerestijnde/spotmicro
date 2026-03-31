"""Orbit UI - Settings page with Controller/Poses/Recordings/System tabs."""

from nicegui import ui

from orbit.layout import create_shell
from orbit.state import state, api_get, api_post, ensure_client, API_URL
from orbit.theme import ACCENT_CYAN, TEXT_MUTED, TEXT_PRIMARY


@ui.page("/settings")
async def settings_page():
    refs = create_shell("Settings")

    ui.label("Settings").classes("text-2xl font-bold text-white mb-4")

    with ui.tabs().classes("w-full").props("dense active-color=cyan indicator-color=cyan") as tabs:
        tab_controller = ui.tab("Controller")
        tab_poses = ui.tab("Custom Poses")
        tab_recordings = ui.tab("Recordings")
        tab_system = ui.tab("System")

    with ui.tab_panels(tabs, value=tab_controller).classes("w-full"):
        # ---- Controller tab ----
        with ui.tab_panel(tab_controller):
            with ui.card().classes("w-full mb-4"):
                ui.label("PlayStation Controller").classes("text-lg font-bold text-white mb-2")
                ui.label("Works with PS4 (DualShock 4) and PS5 (DualSense)").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

            with ui.card().classes("w-full"):
                ui.label("Controller Mapping").classes("text-lg font-bold text-white mb-3")

                with ui.row().classes("w-full gap-6"):
                    with ui.column().classes("flex-grow"):
                        ui.label("Movement").classes("text-gray-300 font-bold mb-1")
                        _mapping_table([
                            ["Left Stick Up/Down", "Walk forward/backward"],
                            ["Left Stick Left/Right", "Lateral step"],
                            ["L2 / R2", "Turn left/right"],
                            ["X", "Single step forward"],
                            ["L3 Click", "Single step backward"],
                            ["Circle", "Stop"],
                        ])

                        ui.separator().classes("my-3")
                        ui.label("Poses").classes("text-gray-300 font-bold mb-1")
                        _mapping_table([
                            ["D-pad Up", "Stand"],
                            ["D-pad Down", "Sit"],
                            ["D-pad Left", "Rest"],
                            ["D-pad Right", "Neutral"],
                        ])

                    with ui.column().classes("flex-grow"):
                        ui.label("Body Control").classes("text-gray-300 font-bold mb-1")
                        _mapping_table([
                            ["Right Stick", "Pitch / Roll"],
                            ["L2 / R2", "Yaw (+ turn)"],
                            ["L1", "Body LOWER"],
                            ["R1", "Body HIGHER"],
                            ["R3 Click", "Reset orientation"],
                        ])

                        ui.separator().classes("my-3")
                        ui.label("Other").classes("text-gray-300 font-bold mb-1")
                        _mapping_table([
                            ["Triangle", "Toggle balance"],
                            ["Square", "Go to neutrals"],
                            ["Share", "Calibrate IMU"],
                            ["Options", "EMERGENCY STOP"],
                        ])

        # ---- Custom Poses tab ----
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
                                        ui.label(desc).classes("text-sm").style(f"color: {TEXT_MUTED}")
                                    with ui.row().classes("gap-2 mt-2"):
                                        async def load_pose(name=pose_name):
                                            await api_post(f"/api/custom_poses/{name}/execute")
                                            ui.notify(f"Loaded {name}", type="positive")

                                        async def delete_pose(name=pose_name):
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
                        ui.label("No custom poses saved yet").style(f"color: {TEXT_MUTED}")

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

        # ---- Recordings tab ----
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
                        ).classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                        with ui.row().classes("items-center gap-3"):
                            ui.badge(
                                "Recording" if is_recording else "Idle",
                                color="red" if is_recording else "gray"
                            ).props("rounded")

                            if is_recording:
                                ui.label(f"File: {rec_status.get('filename', '?')}").classes("text-sm").style(f"color: {TEXT_MUTED}")

                    if recordings:
                        with ui.card().classes("w-full"):
                            ui.label(f"Saved Recordings ({len(recordings)})").classes("text-lg font-bold text-white mb-3")
                            for rec in recordings:
                                with ui.row().classes("w-full items-center gap-3 py-2").style(
                                    "border-bottom: 1px solid #21262d"
                                ):
                                    ui.label(rec["filename"]).classes("font-mono text-sm flex-grow").style(f"color: {ACCENT_CYAN}")
                                    ui.label(f"{rec['size_kb']} KB").classes("text-sm").style(f"color: {TEXT_MUTED}")

                                    async def download(fn=rec["filename"]):
                                        ui.download(f"{API_URL}/api/recordings/{fn}")

                                    ui.button("Download", on_click=download).props("dense flat size=sm color=cyan")
                    else:
                        ui.label("No recordings yet. Press REC in the header to start.").style(f"color: {TEXT_MUTED}")

            await refresh_recordings()

            ui.button("Refresh", on_click=refresh_recordings).props("dense unelevated outline").classes("mt-3")

        # ---- System tab ----
        with ui.tab_panel(tab_system):
            with ui.card().classes("w-full mb-4"):
                ui.label("System Info").classes("text-lg font-bold text-white mb-3")

                status = await api_get("/api/status") or {}

                with ui.row().classes("gap-6"):
                    with ui.column():
                        hw = "Active" if status.get("hardware") else "Simulation"
                        hw_color = "green" if status.get("hardware") else "orange"
                        ui.label("Hardware").classes("text-sm").style(f"color: {TEXT_MUTED}")
                        ui.badge(hw, color=hw_color).props("rounded")

                    with ui.column():
                        kin = "Available" if status.get("kinematics") else "Disabled"
                        kin_color = "green" if status.get("kinematics") else "gray"
                        ui.label("Kinematics").classes("text-sm").style(f"color: {TEXT_MUTED}")
                        ui.badge(kin, color=kin_color).props("rounded")

                    with ui.column():
                        calib = status.get("calibration", {})
                        calibrated = sum(
                            1 for s in calib.get("servos", {}).values()
                            if isinstance(s, dict) and s.get("calibrated", False)
                        )
                        ui.label("Calibration").classes("text-sm").style(f"color: {TEXT_MUTED}")
                        ui.linear_progress(value=calibrated / 12, show_value=False).props(
                            "color=cyan rounded size=20px"
                        ).classes("w-32")
                        ui.label(f"{calibrated}/12 servos").classes("text-xs").style(f"color: {TEXT_MUTED}")

                ui.separator().classes("my-3")
                ui.label(f"Backend: {API_URL}").classes("text-sm").style(f"color: {TEXT_MUTED}")

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
        refs["connection_badge"].text = "Connected" if connected else "Disconnected"
        refs["connection_badge"]._props["color"] = "green" if connected else "red"
        refs["connection_badge"].update()
        refs["uptime_label"].text = state.uptime

    ui.timer(2.0, update_conn)


def _mapping_table(rows: list):
    """Render a controller mapping table."""
    with ui.element("table").classes("text-sm").style(f"color: {TEXT_PRIMARY}"):
        for inp, action in rows:
            with ui.element("tr"):
                with ui.element("td").classes("pr-4 py-1 font-bold").style(f"color: {ACCENT_CYAN}"):
                    ui.label(inp)
                with ui.element("td").classes("py-1"):
                    ui.label(action)
