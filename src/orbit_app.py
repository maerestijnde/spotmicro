#!/usr/bin/env python3
"""
MicroSpot Orbit UI - Modern dashboard for SpotMicro quadruped robot.

NiceGUI-based UI with dark Orbit theme, 3D robot visualization,
and real-time servo/IMU monitoring.

Usage:
    cd src && python3 orbit_app.py
    Open http://localhost:8502
"""

from nicegui import ui, app

# Import all pages to register @ui.page routes
import orbit.pages  # noqa: F401

from orbit.state import http_client


async def _shutdown():
    if http_client and not http_client.is_closed:
        await http_client.aclose()


app.on_shutdown(_shutdown)

if __name__ in {"__main__", "__mp_main__"}:
    print()
    print("========================================")
    print("   MicroSpot Orbit UI v1.0")
    print("========================================")
    print()
    print("  Dashboard: http://localhost:8502")
    print("  Backend:   http://localhost:8000")
    print()
    ui.run(
        title="MicroSpot Orbit",
        port=8502,
        host="0.0.0.0",
        reload=False,
        show=False,
        favicon="🐕",
        storage_secret="microspot-secret-key",
    )
