"""
Orbit UI - Calibration page.

Ported from Streamlit components/calibration.py + servo_page.py.
Blocking time.sleep() calls replaced with async move_servo_smooth endpoint.
"""
from nicegui import ui

from orbit.layout import create_shell
from orbit.state import api_get, api_post, state
from orbit.theme import (
    ACCENT_CYAN, STATUS_GREEN, STATUS_RED, TEXT_MUTED, BG_SECONDARY, BORDER_COLOR, TEXT_PRIMARY,
)
try:
    from orbit.viz import (
        create_robot_topdown_view,
        create_leg_diagram,
        create_calibration_workflow_diagram,
        create_offset_explanation_diagram,
    )
    VIZ_AVAILABLE = True
except Exception:
    VIZ_AVAILABLE = False


JOINT_NAMES = ["Hip", "Knee", "Ankle"]
LEGS = [
    ("FL", "Front Left",  [0, 1, 2]),
    ("FR", "Front Right", [3, 4, 5]),
    ("RL", "Rear Left",   [6, 7, 8]),
    ("RR", "Rear Right",  [9, 10, 11]),
]


@ui.page("/calibration")
async def calibration_page():
    refs = create_shell(page_title="Calibration")

    # ---- Load calibration data ----
    calib_data = await api_get("/api/calibration") or {}
    servos_raw = calib_data.get("servos", {})
    # Normalise keys to int
    servos = {int(k): v for k, v in servos_raw.items() if int(k) < 12}

    calibrated_count = sum(1 for s in servos.values() if s.get("calibrated", False))
    total = len(servos)

    # ---- Header row: summary ----
    with ui.row().classes("w-full items-center justify-between mb-3"):
        ui.label("Servo Calibration").classes("text-xl font-bold").style(f"color: {TEXT_PRIMARY}")
        color = STATUS_GREEN if calibrated_count == total else STATUS_RED
        ui.badge(f"{calibrated_count}/{total} calibrated").props("rounded").style(f"color: {color}; border: 1px solid {color}")

    # ---- SVG robot overview (if available) ----
    if VIZ_AVAILABLE and servos:
        try:
            svg = create_robot_topdown_view(
                highlighted_legs=[
                    leg for leg, _, chs in LEGS
                    if any(servos.get(ch, {}).get("calibrated", False) for ch in chs)
                ],
                show_channels=True,
            )
            with ui.card().classes("w-full mb-3"):
                ui.label("Robot Overview").classes("text-sm mb-2").style(f"color: {TEXT_MUTED}")
                ui.html(svg).classes("w-full")
        except Exception:
            pass

    # ---- Tabs: Per-servo | All servos ----
    with ui.tabs().classes("w-full") as tabs:
        tab_single = ui.tab("Single Servo", icon="tune")
        tab_all = ui.tab("All Servos", icon="grid_view")
        tab_help = ui.tab("How To", icon="help_outline")

    with ui.tab_panels(tabs, value=tab_single).classes("w-full"):

        # ================== SINGLE SERVO ==================
        with ui.tab_panel(tab_single):
            if not servos:
                ui.label("No calibration data available.").classes("text-red-400")
            else:
                # Servo selector
                options = [f"Ch{ch}: {s['label']}" for ch, s in sorted(servos.items())]
                selected_label = ui.select(
                    options,
                    value=options[0],
                    label="Select Servo",
                ).classes("w-full mb-3")

                def get_selected_channel() -> int:
                    return int(selected_label.value.split(":")[0].replace("Ch", ""))

                # Dynamic area — rebuilt when selection changes
                servo_panel = ui.column().classes("w-full")

                async def rebuild_servo_panel():
                    servo_panel.clear()
                    ch = get_selected_channel()
                    s = servos.get(ch, {})
                    if not s:
                        return

                    with servo_panel:
                        # Info row
                        status_color = STATUS_GREEN if s.get("calibrated") else STATUS_RED
                        with ui.row().classes("items-center gap-3 mb-2"):
                            ui.badge(
                                "calibrated" if s.get("calibrated") else "not calibrated"
                            ).props("rounded").style(f"color: {status_color}")
                            ui.label(
                                f"{s.get('leg')} {s.get('joint')} | Saved neutral: {s.get('neutral_angle', 90)}°"
                            ).classes("text-sm").style(f"color: {TEXT_MUTED}")

                        # SVG leg diagram
                        if VIZ_AVAILABLE:
                            try:
                                svg_leg = create_leg_diagram(
                                    leg_id=s.get("leg", "FL"),
                                    highlight_joint=s.get("joint", "hip"),
                                )
                                with ui.card().classes("w-full mb-2"):
                                    ui.html(svg_leg)
                            except Exception:
                                pass

                        # Angle slider
                        current_angle = s.get("neutral_angle", 90)
                        angle_label = ui.label(f"{current_angle}° (offset {current_angle-90:+d})").classes("text-sm font-bold mb-1")
                        slider = ui.slider(min=0, max=180, value=current_angle, step=1).classes("w-full mb-2")

                        async def send_raw(new_angle: int, _ch: int = ch):
                            await api_post(f"/api/servo/{_ch}", {"angle": new_angle, "raw": True})
                            angle_label.text = f"{new_angle}° (offset {new_angle-90:+d})"

                        slider.on("change", lambda e: send_raw(int(e.args)))

                        # Fine-tune buttons
                        with ui.row().classes("gap-2 mb-3"):
                            for delta in [-5, -1, +1, +5]:
                                sign = "+" if delta > 0 else ""
                                async def nudge(d: int = delta, s_ref=slider, lbl=angle_label, _ch: int = ch):
                                    new_val = max(0, min(180, int(s_ref.value) + d))
                                    s_ref.value = new_val
                                    await api_post(f"/api/servo/{_ch}", {"angle": new_val, "raw": True})
                                    lbl.text = f"{new_val}° (offset {new_val-90:+d})"
                                ui.button(f"{sign}{delta}", on_click=nudge).props("dense unelevated outline size=sm")

                        ui.separator().classes("my-2")

                        # Free-move calibration
                        ui.label("Free Move Calibration").classes("text-sm font-bold mb-1")
                        ui.label(
                            "1. Press 'Release' to go limp  "
                            "2. Move leg by hand to neutral  "
                            "3. Use slider to re-engage  "
                            "4. Press 'Save'"
                        ).classes("text-xs mb-2").style(f"color: {TEXT_MUTED}")

                        with ui.row().classes("gap-2 mb-3"):
                            async def release(_ch: int = ch):
                                await api_post(f"/api/servo/{_ch}/disable")
                                ui.notify(f"Servo {_ch} released", type="info")

                            async def to_90(s_ref=slider, lbl=angle_label, _ch: int = ch):
                                s_ref.value = 90
                                await api_post(f"/api/servo/{_ch}", {"angle": 90, "raw": True})
                                lbl.text = "90° (offset +0)"

                            ui.button("🔓 Release", on_click=release, color="orange").props("dense unelevated")
                            ui.button("🔒 To 90°", on_click=to_90).props("dense unelevated outline")

                        ui.separator().classes("my-2")

                        # Save / Goto
                        with ui.row().classes("gap-2"):
                            async def goto_saved(s_data=s, s_ref=slider, lbl=angle_label, _ch: int = ch):
                                saved = s_data.get("neutral_angle", 90)
                                s_ref.value = saved
                                # Use smooth move endpoint (no blocking sleep)
                                await api_post(f"/api/servo/{_ch}", {"angle": saved, "raw": True})
                                lbl.text = f"{saved}° (offset {saved-90:+d})"

                            async def save_neutral(s_ref=slider, s_data=s, _ch: int = ch):
                                new_neutral = int(s_ref.value)
                                updated = dict(s_data)
                                updated["neutral_angle"] = new_neutral
                                updated["offset"] = new_neutral - 90
                                updated["calibrated"] = True
                                await api_post(f"/api/calibration/servo/{_ch}", updated)
                                await api_post("/api/calibration/save")
                                s_data["neutral_angle"] = new_neutral
                                s_data["calibrated"] = True
                                ui.notify(f"Saved {new_neutral}° for servo {_ch}", type="positive")
                                await rebuild_servo_panel()

                            ui.button(
                                f"Go to saved ({s.get('neutral_angle', 90)}°)",
                                on_click=goto_saved,
                            ).props("dense unelevated outline")
                            ui.button("💾 Save", on_click=save_neutral, color="green").props("dense unelevated")

                await rebuild_servo_panel()

                selected_label.on("update:model-value", lambda _: rebuild_servo_panel())

        # ================== ALL SERVOS ==================
        with ui.tab_panel(tab_all):
            if not servos:
                ui.label("No calibration data available.").classes("text-red-400")
            else:
                with ui.row().classes("gap-2 mb-3"):
                    async def all_to_90():
                        for ch in range(12):
                            await api_post(f"/api/servo/{ch}", {"angle": 90, "raw": True})
                        ui.notify("All servos → 90°", type="info")
                        await rebuild_all_grid()

                    async def all_to_neutrals():
                        await api_post("/api/goto_neutrals")
                        ui.notify("All servos → saved neutrals", type="positive")
                        await rebuild_all_grid()

                    ui.button("All to 90°", on_click=all_to_90).props("dense unelevated outline")
                    ui.button("All to Neutrals", on_click=all_to_neutrals, color="green").props("dense unelevated")

                all_grid = ui.column().classes("w-full")
                all_sliders: dict = {}

                async def rebuild_all_grid():
                    all_grid.clear()
                    all_sliders.clear()
                    with all_grid:
                        for leg_id, leg_name, channels in LEGS:
                            with ui.card().classes("w-full mb-2"):
                                ui.label(leg_name).classes("text-sm font-bold mb-2")
                                with ui.row().classes("gap-4 w-full"):
                                    for joint_idx, ch in enumerate(channels):
                                        s = servos.get(ch, {})
                                        with ui.column().classes("flex-grow"):
                                            ui.label(f"{JOINT_NAMES[joint_idx]} (ch{ch})").classes("text-xs").style(f"color: {TEXT_MUTED}")
                                            cur = s.get("neutral_angle", 90)
                                            val_lbl = ui.label(f"{cur}°").classes("text-xs font-bold")
                                            sl = ui.slider(min=0, max=180, value=cur, step=1)

                                            async def on_change(e, _ch=ch, lbl=val_lbl):
                                                new_val = int(e.args)
                                                lbl.text = f"{new_val}°"
                                                await api_post(f"/api/servo/{_ch}", {"angle": new_val, "raw": True})

                                            sl.on("change", on_change)
                                            all_sliders[ch] = sl

                async def save_all_neutrals():
                    for ch, sl in all_sliders.items():
                        s = servos.get(ch, {})
                        new_neutral = int(sl.value)
                        updated = dict(s)
                        updated["neutral_angle"] = new_neutral
                        updated["offset"] = new_neutral - 90
                        updated["calibrated"] = True
                        await api_post(f"/api/calibration/servo/{ch}", updated)
                    await api_post("/api/calibration/save")
                    ui.notify("All neutrals saved!", type="positive")

                await rebuild_all_grid()
                ui.button("💾 Save All Neutrals", on_click=save_all_neutrals, color="green").props("unelevated").classes("w-full mt-2")

        # ================== HOW TO ==================
        with ui.tab_panel(tab_help):
            if VIZ_AVAILABLE:
                try:
                    svg_steps = create_calibration_workflow_diagram()
                    ui.html(svg_steps).classes("w-full")
                except Exception:
                    pass
                try:
                    svg_offset = create_offset_explanation_diagram()
                    ui.html(svg_offset).classes("w-full mt-3")
                except Exception:
                    pass
            else:
                ui.label("Calibration flow:").classes("font-bold mb-2")
                for step in [
                    "1. Select a servo in the 'Single Servo' tab",
                    "2. Press 'Release' — the servo goes limp",
                    "3. Move the leg by hand to the true neutral position",
                    "4. Use the slider to slowly re-engage until it just grabs",
                    "5. Press 'Save' — this becomes the new neutral_angle in calibration.json",
                    "6. Repeat for all 12 servos",
                ]:
                    ui.label(step).classes("text-sm mb-1").style(f"color: {TEXT_MUTED}")

    # ---- Footer update via telemetry ----
    async def on_cal_telemetry(frame: dict):
        refs["pitch_footer"].text = f"P: {state.pitch:.1f}"
        refs["roll_footer"].text = f"R: {state.roll:.1f}"
        refs["uptime_label"].text = state.uptime

    state.subscribe(on_cal_telemetry)
