"""
Orbit UI - Reusable metric card component.

Usage:
    from orbit.components.metric_card import metric_card
    val_label = metric_card("thermostat", "Pitch", "0.0", unit="deg")
    # later: val_label.text = "12.3"
"""
from nicegui import ui

from orbit.theme import BG_SECONDARY, BORDER_COLOR, ACCENT_CYAN, TEXT_PRIMARY, TEXT_MUTED


def metric_card(icon: str, label: str, value: str = "--", unit: str = "",
                color: str = ACCENT_CYAN) -> ui.label:
    """Render a compact metric display card.

    Args:
        icon:  Material icon name.
        label: Metric label text.
        value: Initial display value.
        unit:  Optional unit suffix (e.g. "deg", "mm").
        color: Accent color for the icon and value.

    Returns:
        The value label element (for live updates via `.text = ...`).
    """
    with ui.card().classes("w-full").style(
        f"background: {BG_SECONDARY}; border: 1px solid {BORDER_COLOR}; border-radius: 12px; padding: 12px;"
    ):
        with ui.row().classes("items-center gap-3 w-full"):
            ui.icon(icon).classes("text-2xl").style(f"color: {color}; opacity: 0.8;")

            with ui.column().classes("flex-grow gap-0"):
                ui.label(label).classes("text-xs").style(f"color: {TEXT_MUTED}; line-height: 1;")

                with ui.row().classes("items-baseline gap-1"):
                    value_label = ui.label(str(value)).classes("text-xl font-bold font-mono").style(
                        f"color: {color}; line-height: 1.2;"
                    )
                    if unit:
                        ui.label(unit).classes("text-xs").style(f"color: {TEXT_MUTED};")

    return value_label
