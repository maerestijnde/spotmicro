"""Orbit UI - Tuning page with Stand/Balance/Gait tabs."""

from nicegui import ui

from orbit.layout import create_shell
from orbit.state import state, api_get, api_post
from orbit.theme import TEXT_MUTED


@ui.page("/tuning")
async def tuning_page():
    refs = create_shell("Tuning")

    ui.label("Tuning").classes("text-2xl font-bold text-white mb-4")

    # Fetch current tuning values
    tuning = await api_get("/api/tuning") or {}

    with ui.tabs().classes("w-full").props("dense active-color=cyan indicator-color=cyan") as tabs:
        tab_stand = ui.tab("Stand")
        tab_balance = ui.tab("Balance")
        tab_gait = ui.tab("Gait")

    with ui.tab_panels(tabs, value=tab_stand).classes("w-full"):
        # ---- Stand tab ----
        with ui.tab_panel(tab_stand):
            with ui.card().classes("w-full"):
                ui.label("Stand Position").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust how low the robot bends its knees when standing").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                knee_bend = ui.slider(
                    min=0, max=60, value=int(tuning.get("knee_bend", 40)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Knee Bend (degrees)").classes("text-xs").style(f"color: {TEXT_MUTED}")

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

        # ---- Balance tab ----
        with ui.tab_panel(tab_balance):
            with ui.card().classes("w-full"):
                ui.label("Balance Settings").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust how aggressively the robot compensates for tilt").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                kp_slider = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("balance_kp", 0.5)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Kp (Proportional Gain)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                pitch_gain = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("pitch_gain", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Pitch Gain").classes("text-xs").style(f"color: {TEXT_MUTED}")

                roll_gain = ui.slider(
                    min=0.1, max=2.0, value=float(tuning.get("roll_gain", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Roll Gain").classes("text-xs").style(f"color: {TEXT_MUTED}")

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

        # ---- Gait tab ----
        with ui.tab_panel(tab_gait):
            with ui.card().classes("w-full"):
                ui.label("Gait Parameters").classes("text-lg font-bold text-white mb-2")
                ui.label("Adjust walking cycle timing and step geometry").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                cycle_time = ui.slider(
                    min=0.4, max=1.5, value=float(tuning.get("cycle_time", 0.8)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Cycle Time (seconds)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                step_height = ui.slider(
                    min=10, max=40, value=int(tuning.get("step_height", 25)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Step Height (degrees)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                step_length = ui.slider(
                    min=5, max=30, value=int(tuning.get("step_length", 15)), step=5
                ).props("label label-always color=cyan dense")
                ui.label("Step Length (degrees)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                speed_slider = ui.slider(
                    min=0.5, max=2.0, value=float(tuning.get("speed", 1.0)), step=0.1
                ).props("label label-always color=cyan dense")
                ui.label("Speed Multiplier").classes("text-xs").style(f"color: {TEXT_MUTED}")

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

                # Preset chips
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
        refs["connection_badge"].text = "Connected" if state.connected else "Disconnected"
        refs["connection_badge"]._props["color"] = "green" if state.connected else "red"
        refs["connection_badge"].update()
        refs["pitch_footer"].text = f"P: {state.pitch:.1f}"
        refs["roll_footer"].text = f"R: {state.roll:.1f}"
        refs["uptime_label"].text = state.uptime

    ui.timer(2.0, update_connection)
