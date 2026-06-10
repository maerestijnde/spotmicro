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
        tab_ik = ui.tab("IK")

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

        # ---- IK tab ----
        with ui.tab_panel(tab_ik):
            with ui.card().classes("w-full mb-3"):
                ui.label("IK Parameters").classes("text-lg font-bold text-white mb-2")
                ui.label("Foot trajectory geometry for IK-based gait mode").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                ik_mode_data = await api_get("/api/gait/mode") or {}

                ik_step_height = ui.slider(
                    min=0.01, max=0.08,
                    value=float(ik_mode_data.get("ik_step_height", 0.03)),
                    step=0.005,
                ).props("label label-always color=cyan dense")
                ui.label("Step Height (meters)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                ik_stride_length = ui.slider(
                    min=0.01, max=0.08,
                    value=float(ik_mode_data.get("ik_stride_length", 0.04)),
                    step=0.005,
                ).props("label label-always color=cyan dense")
                ui.label("Stride Length (meters)").classes("text-xs").style(f"color: {TEXT_MUTED}")

                with ui.row().classes("gap-2 mt-4"):
                    async def apply_ik_params():
                        await api_post("/api/gait/params", {
                            "ik_step_height": ik_step_height.value,
                            "ik_stride_length": ik_stride_length.value,
                        })
                        ui.notify("IK params applied", type="info")

                    async def save_ik_params():
                        await api_post("/api/gait/params", {
                            "ik_step_height": ik_step_height.value,
                            "ik_stride_length": ik_stride_length.value,
                        })
                        await api_post("/api/tuning/ik_step_height", {"value": ik_step_height.value})
                        await api_post("/api/tuning/ik_stride_length", {"value": ik_stride_length.value})
                        ui.notify("IK params saved", type="positive")

                    ui.button("Apply", on_click=apply_ik_params).props("dense unelevated outline").classes("flex-grow")
                    ui.button("Save", on_click=save_ik_params, color="green").props("dense unelevated").classes("flex-grow")

                # IK presets for incremental testing
                ui.separator().classes("my-3")
                ui.label("IK Test Presets").classes("text-gray-300 font-bold mb-1")
                ui.label("Use in order — validate each step before moving to the next").classes("text-xs mb-2").style(f"color: {TEXT_MUTED}")
                ik_presets = {
                    "Minimal": {"ik_step_height": 0.015, "ik_stride_length": 0.02},
                    "Slow":    {"ik_step_height": 0.025, "ik_stride_length": 0.03},
                    "Normal":  {"ik_step_height": 0.03,  "ik_stride_length": 0.04},
                }
                with ui.row().classes("gap-2"):
                    for name, params in ik_presets.items():
                        async def apply_ik_preset(p=params, n=name):
                            await api_post("/api/gait/params", p)
                            ik_step_height.value = p["ik_step_height"]
                            ik_stride_length.value = p["ik_stride_length"]
                            ui.notify(f"IK preset '{n}' applied", type="info")
                        ui.button(name, on_click=apply_ik_preset).props("dense unelevated outline")

            # IK Stand Validation card
            with ui.card().classes("w-full"):
                ui.label("IK Stand Validation").classes("text-lg font-bold text-white mb-1")
                ui.label(
                    "Compares IK-computed neutral stand angles with the angle-based stand. "
                    "Deviation >20° = investigate before switching to IK mode."
                ).classes("text-xs mb-3").style(f"color: {TEXT_MUTED}")

                validate_col = ui.column().classes("w-full")

                async def run_ik_validate():
                    validate_col.clear()
                    with validate_col:
                        ui.spinner(size="sm")
                    data = await api_get("/api/gait/ik_stand")
                    validate_col.clear()
                    if not data or data.get("error"):
                        with validate_col:
                            ui.label(f"Error: {(data or {}).get('error', 'unreachable')}").classes("text-sm text-red-400")
                        return
                    ok = data.get("ok", False)
                    max_dev = data.get("max_deviation", 0.0)
                    ok_color = "#00ff88" if ok else "#ff2244"
                    with validate_col:
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("check_circle" if ok else "cancel").style(f"color: {ok_color}; font-size:20px;")
                            ui.label(
                                f"{'PASS — safe to use IK mode' if ok else 'FAIL — do not switch to IK yet'}"
                            ).classes("text-base font-bold").style(f"color: {ok_color}")
                        ui.label(f"Max deviation: {max_dev:.1f}° (tolerance: {data.get('tolerance', 20)}°)").classes("text-sm").style(f"color: {TEXT_MUTED}")
                        legs = data.get("legs", {})
                        if legs:
                            with ui.row().classes("gap-3 mt-2 flex-wrap"):
                                for leg_id, leg_data in sorted(legs.items()):
                                    with ui.card().classes("p-2"):
                                        ui.label(leg_id).classes("text-sm font-bold text-white")
                                        for joint in ["hip", "knee", "ankle"]:
                                            d = leg_data.get("deviation", {}).get(joint, 0.0)
                                            ik_v = leg_data.get("ik", {}).get(joint, 0.0)
                                            ang_v = leg_data.get("angle_based", {}).get(joint, 0.0)
                                            jc = "#00ff88" if d < 10 else ("#ff8800" if d < 25 else "#ff2244")
                                            ui.label(
                                                f"{joint}: IK {ik_v:.0f}° vs {ang_v:.0f}° (Δ{d:.0f}°)"
                                            ).classes("text-xs").style(f"color: {jc}")

                ui.button("Run Validation", on_click=run_ik_validate, color="blue").props("dense unelevated").classes("w-full")

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
