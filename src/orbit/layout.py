"""
Orbit UI Layout - Shell with header, mini-sidebar, and footer.

Usage:
    from orbit.layout import create_shell
    refs = create_shell(page_title="Dashboard")
    # refs["connection_badge"], refs["pitch_footer"], etc.
"""
from nicegui import ui, Client

from orbit.theme import (
    apply_theme, BG_SIDEBAR, BORDER_COLOR, ACCENT_BLUE, ACCENT_CYAN,
    TEXT_PRIMARY, TEXT_MUTED, STATUS_GREEN, STATUS_RED,
)
from orbit.state import api_get, api_post, state

ESTOP_RED = "#dc2626"


# Navigation items: (path, icon, label)
NAV_ITEMS = [
    ("/", "dashboard", "Dashboard"),
    ("/servos", "precision_manufacturing", "Servos"),
    ("/calibration", "manage_accounts", "Calibration"),
    ("/tuning", "tune", "Tuning"),
    ("/imu", "sensors", "IMU"),
    ("/settings", "settings", "Settings"),
]


def create_shell(page_title: str = "Dashboard", client: Client = None) -> dict:
    """Build the full page shell and return updatable UI refs.

    Returns dict with keys:
        connection_badge, rec_btn, header_row,
        stability_footer_badge, pitch_footer, roll_footer, uptime_label
    """
    apply_theme()

    refs = {}

    # ------------------------------------------------------------------ Header
    header = ui.header().classes("items-center justify-between px-4").style(
        f"height: 48px; background: {BG_SIDEBAR}; border-bottom: 1px solid {BORDER_COLOR};"
    )
    refs["header"] = header

    with header:
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

            # ---- E-STOP (hardware emergency stop — no confirm dialog, must be instant) ----
            refs["estop_btn"] = ui.button(
                "⚡ E-STOP",
                color="red",
            ).props("dense unelevated size=sm").classes("font-bold px-3").style(
                f"background: {ESTOP_RED} !important; color: white; letter-spacing: 0.05em;"
            )

            async def do_estop():
                result = await api_post("/api/estop")
                ui.notify(
                    "⚡ E-STOP ACTIVATED — All servos disabled!",
                    type="negative",
                    position="top",
                    timeout=0,  # persistent until dismissed
                )

            refs["estop_btn"].on_click(do_estop)

            # ---- Reset e-stop (confirm dialog) ----
            refs["estop_reset_btn"] = ui.button(
                "Reset", color="orange"
            ).props("dense unelevated size=sm").classes("font-bold").style(
                "display: none;"
            )

            async def do_estop_reset():
                with ui.dialog() as confirm_dialog, ui.card():
                    ui.label("Reset E-Stop?").classes("text-base font-bold")
                    ui.label("Robot will move to stand position. Make sure it is safe to power servos.").classes("text-sm mt-1")
                    with ui.row().classes("gap-2 mt-3"):
                        async def confirmed():
                            confirm_dialog.close()
                            await api_post("/api/estop/reset")
                            ui.notify("E-stop reset — robot returning to stand", type="positive")
                        ui.button("Confirm Reset", on_click=confirmed, color="orange").props("dense unelevated")
                        ui.button("Cancel", on_click=confirm_dialog.close).props("dense unelevated outline")
                confirm_dialog.open()

            refs["estop_reset_btn"].on_click(do_estop_reset)

            # Subscribe to telemetry for estop state changes
            async def on_estop_telemetry(frame: dict):
                is_estop = frame.get("estop", False)
                if is_estop:
                    refs["header"].style(
                        f"height: 48px; background: {ESTOP_RED}; border-bottom: 2px solid #ff6666;"
                    )
                    refs["estop_reset_btn"].style("display: inline-block;")
                else:
                    refs["header"].style(
                        f"height: 48px; background: {BG_SIDEBAR}; border-bottom: 1px solid {BORDER_COLOR};"
                    )
                    refs["estop_reset_btn"].style("display: none;")
                refs["header"].update()
                refs["estop_reset_btn"].update()

            if client:
                state.subscribe_scoped(on_estop_telemetry, client)
            else:
                state.subscribe(on_estop_telemetry)

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
