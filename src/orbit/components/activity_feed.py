"""
Orbit UI - Scrollable activity feed panel.

Usage:
    from orbit.components.activity_feed import create_activity_feed, refresh_feed
    feed = create_activity_feed()
    # In a timer: refresh_feed(feed, state.activity_log)
"""
import time

from nicegui import ui

from orbit.theme import (
    BG_SECONDARY, BORDER_COLOR, TEXT_MUTED, TEXT_PRIMARY,
    STATUS_GREEN, STATUS_RED, ACCENT_CYAN, STATUS_PURPLE,
)

# Color mapping by event tag prefix
EVENT_COLORS = {
    "gait_start": STATUS_GREEN,
    "gait_stop": STATUS_RED,
    "pose_": ACCENT_CYAN,
    "balance_": "#ff8800",
    "imu_": STATUS_PURPLE,
}


def _event_color(tag: str) -> str:
    """Pick a color for an event based on its tag prefix."""
    for prefix, color in EVENT_COLORS.items():
        if tag.startswith(prefix):
            return color
    return TEXT_MUTED


def _format_time(ts: float) -> str:
    """Format a unix timestamp as HH:MM:SS."""
    return time.strftime("%H:%M:%S", time.localtime(ts))


def create_activity_feed() -> ui.column:
    """Create the activity feed container.

    Returns the ui.column container. Call refresh_feed() to populate it.
    """
    with ui.card().classes("w-full").style(
        f"background: {BG_SECONDARY}; border: 1px solid {BORDER_COLOR}; border-radius: 12px;"
    ):
        ui.label("Activity").classes("text-xs font-bold px-3 pt-2").style(f"color: {TEXT_MUTED};")
        container = ui.column().classes("activity-feed w-full gap-0 px-1 pb-2")

    return container


def refresh_feed(container: ui.column, events, max_items: int = 30):
    """Re-render the activity feed from an events iterable.

    Args:
        container: The ui.column returned by create_activity_feed().
        events: Iterable of dicts with keys: timestamp, tag, message.
        max_items: Maximum items to display.
    """
    container.clear()

    items = list(events)[-max_items:]

    with container:
        if not items:
            ui.label("No events yet").classes("text-xs px-2 py-1").style(f"color: {TEXT_MUTED};")
            return

        for ev in items:
            tag = ev.get("tag", "")
            color = _event_color(tag)
            ts = _format_time(ev.get("timestamp", time.time()))
            msg = ev.get("message", tag)

            with ui.element("div").classes("activity-item").style(f"border-left-color: {color};"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(ts).classes("font-mono").style(
                        f"color: {TEXT_MUTED}; font-size: 0.7rem; min-width: 55px;"
                    )
                    ui.label(msg).style(f"color: {TEXT_PRIMARY}; font-size: 0.8rem;")

    # Auto-scroll to bottom
    container.run_method("scrollTo", 0, 99999)
