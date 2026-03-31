"""
Orbit UI Layout - Shell with header, mini-sidebar, and footer.

Usage:
    from orbit.layout import create_shell
    refs = create_shell(page_title="Dashboard")
    # refs["connection_badge"], refs["pitch_footer"], etc.
"""
from nicegui import ui

from orbit.theme import (
    apply_theme, BG_SIDEBAR, BORDER_COLOR, ACCENT_BLUE, ACCENT_CYAN,
    TEXT_PRIMARY, TEXT_MUTED, STATUS_GREEN, STATUS_RED,
)
from orbit.state import api_get, api_post, state


# Navigation items: (path, icon, label)
NAV_ITEMS = [
    ("/", "dashboard", "Dashboard"),
    ("/servos", "precision_manufacturing", "Servos"),
    ("/tuning", "tune", "Tuning"),
    ("/imu", "sensors", "IMU"),
    ("/settings", "settings", "Settings"),
]


def create_shell(page_title: str = "Dashboard") -> dict:
    """Build the full page shell and return updatable UI refs.

    Returns dict with keys:
        connection_badge, rec_btn,
        stability_footer_badge, pitch_footer, roll_footer, uptime_label
    """
    apply_theme()

    refs = {}

    # ------------------------------------------------------------------ Header
    with ui.header().classes("items-center justify-between px-4").style(
        f"height: 48px; background: {BG_SIDEBAR}; border-bottom: 1px solid {BORDER_COLOR};"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("pets").classes("text-lg").style(f"color: {ACCENT_CYAN}")
            ui.label("MicroSpot").classes("text-base font-bold").style(f"color: {TEXT_PRIMARY}")
            ui.label(page_title).classes("text-sm").style(f"color: {TEXT_MUTED}")

        with ui.row().classes("items-center gap-2"):
            # Connection badge
            refs["connection_badge"] = (
                ui.badge("--", color="gray").props("rounded dense")
            )

            # REC button
            refs["rec_btn"] = (
                ui.button("REC", color="grey-8")
                .props("dense unelevated size=sm")
                .classes("text-white font-bold")
            )

            async def toggle_rec():
                rec_status = await api_get("/api/recording/status")
                if rec_status and rec_status.get("recording"):
                    result = await api_post("/api/recording/stop")
                    if result and result.get("ok"):
                        refs["rec_btn"]._props["color"] = "grey-8"
                        refs["rec_btn"].update()
                        ui.notify(f"Recording saved: {result.get('filename')}", type="positive")
                else:
                    result = await api_post("/api/recording/start")
                    if result and result.get("ok"):
                        refs["rec_btn"]._props["color"] = "red"
                        refs["rec_btn"].update()
                        ui.notify("Recording started", type="info")

            refs["rec_btn"].on_click(toggle_rec)

            # Emergency stop
            async def emergency_stop():
                await api_post("/api/gait/stop")
                for ch in range(12):
                    await api_post(f"/api/servo/{ch}/disable")
                ui.notify("EMERGENCY STOP - All servos disabled!", type="negative", position="top")

            ui.button("STOP", on_click=emergency_stop, color="red").props(
                "dense unelevated size=sm"
            ).classes("emergency-btn text-white font-bold")

    # ------------------------------------------------------------- Mini-sidebar
    with ui.left_drawer(value=True).props("mini mini-to-overlay bordered").classes("p-0").style(
        f"background: {BG_SIDEBAR}; width: 200px;"
    ) as drawer:
        # Add hover expand behavior
        drawer.on("mouseover", lambda: drawer.props(remove="mini"))
        drawer.on("mouseout", lambda: drawer.props(add="mini"))

        ui.element("div").classes("py-2")  # top spacer

        for path, icon, label in NAV_ITEMS:
            active = page_title.lower() == label.lower()
            active_style = (
                f"border-left: 3px solid {ACCENT_BLUE}; background: rgba(31,111,235,0.12); color: {ACCENT_BLUE};"
                if active
                else f"border-left: 3px solid transparent; color: {TEXT_MUTED};"
            )
            with ui.link(target=path).classes("no-underline block"):
                with ui.row().classes("items-center gap-3 py-2 px-3").style(
                    f"{active_style} transition: all 0.2s ease;"
                ):
                    ui.icon(icon).classes("text-lg")
                    ui.label(label).classes("text-sm")

    # ------------------------------------------------------------------ Footer
    with ui.footer().classes("items-center justify-between px-4").style(
        f"height: 32px; background: {BG_SIDEBAR}; border-top: 1px solid {BORDER_COLOR};"
    ):
        with ui.row().classes("items-center gap-4"):
            refs["stability_footer_badge"] = (
                ui.badge("--", color="gray").props("rounded dense")
            )
            refs["pitch_footer"] = ui.label("P: 0.0").classes("text-xs").style(f"color: {ACCENT_CYAN}")
            refs["roll_footer"] = ui.label("R: 0.0").classes("text-xs").style("color: #ff8800")

        refs["uptime_label"] = ui.label("0m 0s").classes("text-xs").style(f"color: {TEXT_MUTED}")

    return refs
