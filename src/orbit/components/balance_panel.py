"""
Orbit balance panel - Toggle, Kp slider, IMU calibrate button.
"""
import asyncio

from nicegui import ui

from orbit.state import api_post, ensure_client


def create_balance_panel():
    """Create balance controls. Returns balance_switch for timer updates."""
    balance_switch = ui.switch("Enable Balance", value=False)

    async def toggle_balance():
        await api_post("/api/balance/enable", {"enable": balance_switch.value})
        ui.notify(f"Balance {'enabled' if balance_switch.value else 'disabled'}", type="info")

    balance_switch.on_value_change(toggle_balance)

    ui.separator().classes("my-2")

    kp_slider = ui.slider(min=0.1, max=2.0, value=0.5, step=0.1).props("label label-always color=cyan dense")
    ui.label("Kp (Proportional Gain)").classes("text-xs text-gray-500 -mt-1")

    async def save_kp():
        await api_post("/api/balance/kp", {"kp": kp_slider.value})
        ui.notify(f"Kp set: {kp_slider.value}", type="positive")

    ui.button("Apply Kp", on_click=save_kp).props("dense unelevated outline").classes("w-full mt-1")

    ui.separator().classes("my-2")

    async def calibrate_imu():
        ui.notify("Hold robot still...", type="info", position="top", timeout=2000)
        try:
            client = await ensure_client()
            resp = await asyncio.wait_for(
                client.post("/api/balance/calibrate", json={}), timeout=5.0
            )
            if resp.status_code == 200:
                ui.notify("IMU calibrated", type="positive")
            else:
                ui.notify("Calibration failed", type="negative")
        except asyncio.TimeoutError:
            ui.notify("Calibration timeout", type="warning")
        except Exception as e:
            ui.notify(f"Calibration error: {e}", type="negative")

    ui.button("Calibrate IMU", on_click=calibrate_imu).props("dense unelevated outline").classes("w-full")

    return balance_switch
