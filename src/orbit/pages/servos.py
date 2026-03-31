"""Orbit UI - Servo control page with 2x2 leg cards."""

from nicegui import ui

from orbit.layout import create_shell
from orbit.state import state, api_post, SERVO_NAMES, LEG_CONFIG
from orbit.theme import ACCENT_CYAN, TEXT_MUTED
from orbit.kinematics import get_servo_angle


@ui.page("/servos")
async def servos_page():
    refs = create_shell("Servos")

    ui.label("Servo Control").classes("text-2xl font-bold text-white mb-4")

    # Quick actions bar
    with ui.row().classes("gap-2 mb-4"):
        async def reset_all():
            await api_post("/api/reset")
            ui.notify("All servos reset to 90", type="info")

        async def goto_neutrals():
            await api_post("/api/goto_neutrals")
            ui.notify("Moved to calibrated neutrals", type="positive")

        async def release_all():
            for ch in range(12):
                await api_post(f"/api/servo/{ch}/disable")
            ui.notify("All servos released", type="warning")

        ui.button("Reset All 90", on_click=reset_all, color="orange").props("dense unelevated")
        ui.button("Go to Neutrals", on_click=goto_neutrals, color="blue").props("dense unelevated")
        ui.button("Release All", on_click=release_all, color="grey-8").props("dense unelevated")

    # Servo sliders storage
    servo_sliders = {}
    servo_labels = {}

    # 2x2 leg cards grid
    with ui.grid(columns=2).classes("w-full gap-4"):
        for leg_id, config in LEG_CONFIG.items():
            css_class = f"leg-card-{leg_id.lower()}"
            with ui.card().classes(f"w-full {css_class}"):
                ui.label(f"{leg_id} Leg").classes("text-lg font-bold mb-2").style(f"color: {config['color']}")

                joints = ["Hip", "Knee", "Ankle"]
                for j_idx, joint in enumerate(joints):
                    channel = config["channels"][j_idx]

                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(joint).classes("w-16").style(f"color: {TEXT_MUTED}")
                        lbl = ui.label("90").classes("w-10 text-right font-mono").style(f"color: {ACCENT_CYAN}")
                        servo_labels[channel] = lbl

                        slider = ui.slider(min=0, max=180, value=90, step=1).props(
                            "dense color=cyan label-always"
                        ).classes("flex-grow glow-slider")
                        servo_sliders[channel] = slider

                        async def on_servo_change(e, ch=channel, sl=slider, lb=lbl):
                            state.mark_slider_touched(ch)
                            lb.text = str(int(sl.value))
                            await api_post(f"/api/servo/{ch}", {"angle": sl.value})

                        slider.on("update:model-value", on_servo_change, throttle=0.05)

                    # Quick-set buttons
                    with ui.row().classes("gap-1 ml-20 -mt-1 mb-2"):
                        for angle in [0, 45, 90, 135, 180]:
                            async def set_angle(a=angle, ch=channel, sl=slider, lb=lbl):
                                state.mark_slider_touched(ch)
                                sl.value = a
                                lb.text = str(a)
                                await api_post(f"/api/servo/{ch}", {"angle": a})

                            ui.button(str(angle), on_click=set_angle).props("dense flat size=xs").style(f"color: {TEXT_MUTED}")

    # Calibration tools (expandable)
    ui.separator().classes("my-4")
    with ui.expansion("Calibration Tools", icon="build").classes("w-full"):
        with ui.card().classes("w-full"):
            ui.label("Fine-tune servo positions").classes("mb-2").style(f"color: {TEXT_MUTED}")

            cal_channel = ui.select(
                {ch: name for ch, name in SERVO_NAMES.items()},
                value=0, label="Select Servo"
            ).classes("w-64")

            with ui.row().classes("gap-2 mt-2"):
                for delta in [-5, -1, 1, 5]:
                    sign = "+" if delta > 0 else ""

                    async def nudge(d=delta):
                        ch = cal_channel.value
                        if ch in servo_sliders:
                            new_val = max(0, min(180, servo_sliders[ch].value + d))
                            servo_sliders[ch].value = new_val
                            servo_labels[ch].text = str(int(new_val))
                            state.mark_slider_touched(ch)
                            await api_post(f"/api/servo/{ch}", {"angle": new_val})

                    ui.button(f"{sign}{delta}", on_click=nudge).props("dense unelevated outline")

            with ui.row().classes("gap-2 mt-3"):
                async def release_servo():
                    ch = cal_channel.value
                    await api_post(f"/api/servo/{ch}/disable")
                    ui.notify(f"Servo {ch} released", type="info")

                async def save_neutral():
                    ch = cal_channel.value
                    angle = servo_sliders[ch].value if ch in servo_sliders else 90
                    await api_post(f"/api/calibration/servo/{ch}", {"neutral_angle": angle})
                    await api_post("/api/calibration/save")
                    ui.notify(f"Neutral saved for servo {ch}: {angle}", type="positive")

                ui.button("Release Servo", on_click=release_servo, color="orange").props("dense unelevated")
                ui.button("Save as Neutral", on_click=save_neutral, color="green").props("dense unelevated")

    # Timer: 5Hz update servo sliders from state
    async def update_servos():
        await state.update_fast()

        refs["connection_badge"].text = "Connected" if state.connected else "Disconnected"
        refs["connection_badge"]._props["color"] = "green" if state.connected else "red"
        refs["connection_badge"].update()

        refs["pitch_footer"].text = f"P: {state.pitch:.1f}"
        refs["roll_footer"].text = f"R: {state.roll:.1f}"
        refs["uptime_label"].text = state.uptime

        for ch, slider in servo_sliders.items():
            if state.can_update_slider(ch):
                angle = get_servo_angle(state.servo_angles, ch)
                slider.value = angle
                if ch in servo_labels:
                    servo_labels[ch].text = str(int(angle))

    ui.timer(0.2, update_servos)
