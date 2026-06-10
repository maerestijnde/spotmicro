"""
Orbit - Shadow Comparison Panel.

Shows angle-mode vs IK angle divergence per joint in real-time.
Only meaningful when gait is running with shadow_compare enabled.
"""
from nicegui import ui

from orbit.state import api_get, api_post, state
from orbit.theme import ACCENT_CYAN, TEXT_MUTED, STATUS_GREEN, STATUS_YELLOW, STATUS_RED

_JOINTS = ["hip", "knee", "ankle"]
_LEGS = ["FL", "FR", "RL", "RR"]

# Color thresholds for divergence (degrees)
_WARN_DEG = 10.0
_CRIT_DEG = 25.0


def _divergence_color(deg: float) -> str:
    if deg >= _CRIT_DEG:
        return STATUS_RED
    if deg >= _WARN_DEG:
        return STATUS_YELLOW
    return STATUS_GREEN


def create_shadow_panel(client=None) -> dict:
    """Create shadow comparison panel. Returns dict of updatable refs."""
    refs = {}

    with ui.column().classes("w-full gap-1"):
        # Header row: title + toggle switch
        with ui.row().classes("w-full items-center justify-between mb-1"):
            ui.label("IK Shadow Compare").classes("text-sm font-bold").style(f"color: {TEXT_MUTED}")
            shadow_switch = ui.switch(
                value=False,
                on_change=lambda e: _toggle_shadow(e.value),
            ).props("dense color=cyan")
            refs["shadow_switch"] = shadow_switch

        # Status label
        refs["status_label"] = ui.label("Shadow compare OFF").classes("text-xs").style(f"color: {TEXT_MUTED}")

        # Per-joint max-divergence bar (shown when active)
        bars_col = ui.column().classes("w-full gap-1")
        refs["bars_col"] = bars_col

        # IK stats row
        refs["ik_stats_label"] = ui.label("").classes("text-xs").style(f"color: {TEXT_MUTED}")

    async def _toggle_shadow(enabled: bool):
        result = await api_post("/api/gait/shadow", {"enabled": enabled})
        if result and not result.get("error"):
            if enabled and not result.get("ik_available"):
                ui.notify("IK not available on this system", type="warning")
                shadow_switch.value = False
            else:
                ui.notify(
                    f"Shadow compare {'enabled' if enabled else 'disabled'}",
                    type="positive" if enabled else "info",
                )
        else:
            err = (result or {}).get("error", "failed")
            ui.notify(f"Shadow toggle failed: {err}", type="negative")
            shadow_switch.value = not enabled

    def _rebuild_bars(shadow_max: dict, ik_stats: dict):
        bars_col.clear()
        if not shadow_max:
            return
        with bars_col:
            for joint in _JOINTS:
                deg = shadow_max.get(joint, 0.0)
                color = _divergence_color(deg)
                pct = min(100, int(deg / 45.0 * 100))  # 45° = full bar
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label(joint.capitalize()).classes("text-xs w-10").style(f"color: {TEXT_MUTED}")
                    with ui.element("div").classes("flex-grow").style("height:6px; background:#1a2035; border-radius:3px;"):
                        ui.element("div").style(
                            f"width:{pct}%; height:100%; background:{color}; border-radius:3px; "
                            "transition: width 0.3s ease;"
                        )
                    ui.label(f"{deg:.0f}°").classes("text-xs w-8 text-right").style(f"color:{color};")

        if ik_stats:
            fails = ik_stats.get("failure_count", 0)
            clamps = ik_stats.get("clamp_count", 0)
            refs["ik_stats_label"].text = f"IK failures: {fails} | clamped: {clamps}"
        else:
            refs["ik_stats_label"].text = ""

    async def on_shadow_telemetry(frame: dict):
        gait = frame.get("gait", {})
        active = gait.get("shadow_compare", False)

        # Sync switch without re-triggering the change handler
        if refs["shadow_switch"].value != active:
            refs["shadow_switch"].value = active

        if active:
            refs["status_label"].text = "Shadow compare ACTIVE"
            refs["status_label"].style(f"color: {ACCENT_CYAN}")
            shadow_max = gait.get("shadow_max", {})
            ik_stats = gait.get("ik_stats", {})
            _rebuild_bars(shadow_max, ik_stats)
        else:
            refs["status_label"].text = "Shadow compare OFF"
            refs["status_label"].style(f"color: {TEXT_MUTED}")
            bars_col.clear()
            refs["ik_stats_label"].text = ""

    if client:
        state.subscribe_scoped(on_shadow_telemetry, client)
    else:
        state.subscribe(on_shadow_telemetry)

    # ---- IK Stand Validation ----
    ui.separator().classes("my-2")
    validate_result = ui.column().classes("w-full")
    refs["validate_result"] = validate_result

    async def _run_validate():
        validate_result.clear()
        with validate_result:
            ui.spinner(size="sm")
        data = await api_get("/api/gait/ik_stand")
        validate_result.clear()
        if not data:
            with validate_result:
                ui.label("Validation failed — backend unreachable").classes("text-xs").style(f"color: {STATUS_RED}")
            return
        if not data.get("ik_available", True) or data.get("error"):
            with validate_result:
                ui.label(f"IK not available: {data.get('error', '')}").classes("text-xs").style(f"color: {STATUS_RED}")
            return
        ok = data.get("ok", False)
        max_dev = data.get("max_deviation", 0.0)
        color = STATUS_GREEN if ok else STATUS_RED
        with validate_result:
            with ui.row().classes("items-center gap-2"):
                ui.icon("check_circle" if ok else "cancel").style(f"color: {color}; font-size:16px;")
                ui.label(
                    f"{'IK stand OK' if ok else 'Large deviation!'} — max {max_dev:.1f}°"
                ).classes("text-xs font-bold").style(f"color: {color}")
            legs = data.get("legs", {})
            for leg_id, leg_data in sorted(legs.items()):
                max_leg = leg_data.get("max_dev", 0.0)
                c = _divergence_color(max_leg)
                with ui.row().classes("w-full items-center gap-1"):
                    ui.label(leg_id).classes("text-xs w-8").style(f"color: {TEXT_MUTED}")
                    dev = leg_data.get("deviation", {})
                    for joint in ["hip", "knee", "ankle"]:
                        d = dev.get(joint, 0.0)
                        jc = _divergence_color(d)
                        ui.label(f"{joint[0].upper()}:{d:.0f}°").classes("text-xs").style(f"color: {jc}")

    ui.button("Validate IK Stand", on_click=_run_validate).props(
        "dense unelevated outline size=sm"
    ).classes("w-full mt-1")

    # Load initial state
    async def _load_initial():
        data = await api_get("/api/gait/mode")
        if data:
            refs["shadow_switch"].value = data.get("shadow_compare", False)

    ui.timer(0, _load_initial, once=True)

    return refs
