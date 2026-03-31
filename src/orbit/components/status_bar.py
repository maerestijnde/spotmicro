"""
Orbit UI - Horizontal status badge strip.

Usage:
    from orbit.components.status_bar import create_status_bar
    badges = create_status_bar()
    # badges["stability"].text = "STABLE"
"""
from nicegui import ui

from orbit.theme import STATUS_GREEN, STATUS_YELLOW, STATUS_RED, TEXT_MUTED


def _badge_color(status: str) -> str:
    """Map a status keyword to a color."""
    mapping = {
        "green": STATUS_GREEN,
        "yellow": STATUS_YELLOW,
        "red": STATUS_RED,
        "muted": TEXT_MUTED,
    }
    return mapping.get(status, TEXT_MUTED)


def _status_badge(label: str, color: str = TEXT_MUTED) -> ui.html:
    """Render a single dot + text status badge. Returns the html element for updates."""
    badge = ui.html(
        f'<span class="status-badge" style="color: {color};">{label}</span>'
    )
    return badge


def create_status_bar() -> dict:
    """Render a horizontal row of status badges.

    Returns dict with keys: stability, walking, balance, imu
    Each value is the ui.html element. Update via:
        update_badge(badges["stability"], "STABLE", STATUS_GREEN)
    """
    badges = {}

    with ui.row().classes("w-full items-center gap-3 px-1 py-1"):
        badges["stability"] = _status_badge("Stability: --")
        badges["walking"] = _status_badge("Walking: --")
        badges["balance"] = _status_badge("Balance: --")
        badges["imu"] = _status_badge("IMU: --")

    return badges


def update_badge(badge: ui.html, label: str, color: str = TEXT_MUTED):
    """Update a status badge's label and color.

    Args:
        badge: The ui.html element returned by create_status_bar().
        label: New text to display.
        color: Hex color string.
    """
    badge.content = f'<span class="status-badge" style="color: {color};">{label}</span>'
