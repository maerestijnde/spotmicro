#!/bin/bash
# MicroSpot - Start backend + Orbit UI + PS4 Controller
# Usage: ./start.sh
# Press Ctrl+C to stop all services

cd "$(dirname "$0")/src"

echo "========================================"
echo "   MicroSpot Control System v2.0"
echo "   Orbit UI (NiceGUI)"
echo "========================================"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $BACKEND_PID 2>/dev/null
    kill $PS4_PID 2>/dev/null
    kill $WATCHDOG_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# Start backend in background
echo "Starting backend API (port 8000)..."
python3 microspot_app.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Check if backend started
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "ERROR: Backend failed to start!"
    exit 1
fi

echo "Backend running (PID: $BACKEND_PID)"
echo ""

# Start controller watchdog (auto-reconnect)
echo "Starting controller watchdog..."
python3 controller_watchdog.py &
WATCHDOG_PID=$!

# Start PS4 controller in background
echo "Starting PS4 controller listener..."
python3 ps4_controller.py &
PS4_PID=$!
sleep 1

if kill -0 $PS4_PID 2>/dev/null; then
    echo "PS4 controller running (PID: $PS4_PID)"
else
    echo "PS4 controller not started (install: pip3 install pyPS4Controller)"
fi
echo ""

echo "Starting Orbit UI (port 8502)..."
echo ""
echo "========================================"
echo "  Open: http://microspot:8502"
echo "  API:  http://microspot:8000/docs"
echo "  PS4:  Connect controller via Bluetooth"
echo "========================================"
echo ""
python3 orbit_app.py

# Wait for processes
wait
