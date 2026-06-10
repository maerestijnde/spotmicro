"""Orbit UI - IMU monitor page with ECharts, gauges, and stability display."""

import asyncio

from nicegui import ui, Client

from orbit.layout import create_shell
from orbit.state import (
    state, api_get, api_post, ensure_client,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER,
)
from orbit.theme import ACCENT_CYAN, TEXT_MUTED, STATUS_GREEN, STATUS_RED


@ui.page("/imu")
async def imu_page(client: Client):
    refs = create_shell("IMU", client=client)

    ui.label("IMU Monitor").classes("text-2xl font-bold text-white mb-4")

    with ui.row().classes("w-full gap-4").style("flex-wrap: nowrap"):
        # Left: ECharts line graph
        with ui.column().classes("flex-grow"):
            with ui.card().classes("w-full"):
                ui.label("Orientation (Real-time)").classes("text-sm mb-2").style(f"color: {TEXT_MUTED}")

                chart = ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "legend": {
                        "data": ["Pitch", "Roll"],
                        "textStyle": {"color": "#999"},
                        "top": 0,
                    },
                    "grid": {"top": 30, "right": 20, "bottom": 30, "left": 50},
                    "xAxis": {
                        "type": "category",
                        "data": [],
                        "axisLabel": {"color": "#666"},
                        "axisLine": {"lineStyle": {"color": "#333"}},
                    },
                    "yAxis": {
                        "type": "value",
                        "min": -45,
                        "max": 45,
                        "axisLabel": {"color": "#666", "formatter": "{value}"},
                        "axisLine": {"lineStyle": {"color": "#333"}},
                        "splitLine": {"lineStyle": {"color": "#222"}},
                    },
                    "series": [
                        {
                            "name": "Pitch",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "lineStyle": {"color": ACCENT_CYAN, "width": 2},
                            "itemStyle": {"color": ACCENT_CYAN},
                            "showSymbol": False,
                            "animation": True,
                            "animationDuration": 180,
                        },
                        {
                            "name": "Roll",
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "lineStyle": {"color": "#ff8800", "width": 2},
                            "itemStyle": {"color": "#ff8800"},
                            "showSymbol": False,
                            "animation": True,
                            "animationDuration": 180,
                        },
                    ],
                    "backgroundColor": "transparent",
                }).classes("w-full").style("height: 350px")

        # Right: Gauges and controls
        with ui.column().style("min-width: 280px; max-width: 320px"):
            # Pitch/Roll knobs
            with ui.card().classes("w-full mb-3"):
                ui.label("Current Angles").classes("text-sm mb-3").style(f"color: {TEXT_MUTED}")

                with ui.row().classes("justify-around w-full"):
                    with ui.column().classes("items-center"):
                        pitch_knob = ui.knob(0, min=-45, max=45, show_value=True, color="cyan", track_color="grey-8").props("size=110px thickness=0.2")
                        ui.label("Pitch").classes("text-sm mt-1").style(f"color: {ACCENT_CYAN}")

                    with ui.column().classes("items-center"):
                        roll_knob = ui.knob(0, min=-45, max=45, show_value=True, color="orange", track_color="grey-8").props("size=110px thickness=0.2")
                        ui.label("Roll").classes("text-sm mt-1").style("color: #ff8800")

            # Stability badge
            with ui.card().classes("w-full mb-3"):
                ui.label("Stability").classes("text-sm mb-2").style(f"color: {TEXT_MUTED}")
                stab_badge = ui.badge("--", color="gray").props("rounded").classes("text-lg px-4 py-1")

            # Balance controls
            with ui.card().classes("w-full mb-3"):
                ui.label("Balance").classes("text-sm mb-2").style(f"color: {TEXT_MUTED}")
                imu_balance_switch = ui.switch("Enable Balance", value=False)

                async def toggle_imu_balance():
                    try:
                        client = await ensure_client()
                        await asyncio.wait_for(
                            client.post("/api/balance/enable", json={"enable": imu_balance_switch.value}),
                            timeout=3.0
                        )
                    except Exception:
                        ui.notify("Balance toggle timeout", type="warning")

                imu_balance_switch.on_value_change(toggle_imu_balance)

                async def cal_imu():
                    ui.notify("Hold robot still...", type="info", position="top", timeout=2000)
                    try:
                        client = await ensure_client()
                        resp = await asyncio.wait_for(client.post("/api/balance/calibrate", json={}), timeout=5.0)
                        if resp.status_code == 200:
                            ui.notify("IMU calibrated", type="positive")
                        else:
                            ui.notify("Calibration failed", type="negative")
                    except asyncio.TimeoutError:
                        ui.notify("Calibration timeout", type="warning")
                    except Exception as e:
                        ui.notify(f"Calibration error: {e}", type="negative")

                ui.button("Calibrate IMU", on_click=cal_imu).props("dense unelevated outline").classes("w-full mt-2")

            # Quick Kp slider
            with ui.card().classes("w-full"):
                ui.label("Quick Kp Adjust").classes("text-sm mb-2").style(f"color: {TEXT_MUTED}")
                kp_imu = ui.slider(min=0.1, max=2.0, value=0.5, step=0.1).props("label label-always color=cyan dense")

                async def save_kp_imu():
                    await api_post("/api/balance/kp", {"kp": kp_imu.value})
                    await api_post("/api/tuning/balance_kp", {"value": kp_imu.value})
                    ui.notify(f"Kp saved: {kp_imu.value}", type="positive")

                ui.button("Save Kp", on_click=save_kp_imu, color="green").props("dense unelevated").classes("w-full mt-2")

    # Event color mapping for chart markLines
    event_colors = {
        "gait_start": STATUS_GREEN, "gait_stop": STATUS_RED,
        "pose_": ACCENT_CYAN, "balance_": "#ff8800", "imu_": "#a371f7",
    }

    def _refresh_imu_ui():
        """Update knobs + badges from current state."""
        refs["connection_badge"].text = "Connected" if state.connected else "Disconnected"
        refs["connection_badge"]._props["color"] = "green" if state.ws_connected else ("orange" if state.connected else "red")
        refs["connection_badge"].update()
        refs["pitch_footer"].text = f"P: {state.pitch:.1f}"
        refs["roll_footer"].text = f"R: {state.roll:.1f}"
        refs["uptime_label"].text = state.uptime

        pitch_knob.value = round(state.pitch, 1)
        roll_knob.value = round(state.roll, 1)

    def _update_chart():
        """Redraw the IMU history chart from current state."""
        if state.time_history:
            t0 = state.time_history[0]
            t_end = state.time_history[-1]
            x_data = [f"{(t - t0):.0f}" for t in state.time_history]
            pitch_data = [round(p, 1) for p in state.pitch_history]
            roll_data = [round(r, 1) for r in state.roll_history]

            # Build event markLines
            mark_lines = []
            for ev in state.event_history:
                evt = ev["t"]
                if evt < t0 or evt > t_end:
                    continue
                x_val = f"{(evt - t0):.0f}"
                tag = ev["tag"]
                color = TEXT_MUTED
                for prefix, c in event_colors.items():
                    if tag.startswith(prefix):
                        color = c
                        break
                label = tag.replace("gait_", "").replace("pose_", "P:").replace("balance_", "B:")
                mark_lines.append({
                    "xAxis": x_val,
                    "label": {"formatter": label, "color": color, "fontSize": 10},
                    "lineStyle": {"color": color, "type": "dashed", "width": 1},
                })

            chart.options["xAxis"]["data"] = x_data
            chart.options["series"][0]["data"] = pitch_data
            chart.options["series"][1]["data"] = roll_data
            if mark_lines:
                chart.options["series"][0]["markLine"] = {
                    "symbol": "none",
                    "data": mark_lines,
                    "animation": False,
                }
            else:
                chart.options["series"][0].pop("markLine", None)
            chart.update()

    async def on_imu_telemetry(frame: dict):
        """Called on each WS telemetry frame — update chart + UI."""
        _refresh_imu_ui()
        _update_chart()

    state.subscribe_scoped(on_imu_telemetry, client)

    # Timer: 2s slow stability/balance (polling OK — not time-critical)
    async def update_imu_slow():
        await state.update_slow()

        stab_label, stab_color = state.get_stability_display()
        stab_badge.text = stab_label
        color_map = {COLOR_SUCCESS: "green", COLOR_WARNING: "orange", COLOR_DANGER: "red"}
        stab_badge._props["color"] = color_map.get(stab_color, "red")
        stab_badge.update()

        imu_balance_switch.value = state.balance_enabled

        # Update footer stability badge
        refs["stability_footer_badge"].text = stab_label
        refs["stability_footer_badge"]._props["color"] = color_map.get(stab_color, "red")
        refs["stability_footer_badge"].update()

    async def fallback_imu_fast():
        """Fallback polling when WS is down."""
        if not state.ws_connected:
            await state.update_fast()
            _refresh_imu_ui()
            _update_chart()

    ui.timer(0.5, fallback_imu_fast)
    ui.timer(2.0, update_imu_slow)
