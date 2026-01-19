#!/bin/bash
# MicroSpot - Start backend + UI + PS4 Controller
# Usage: ./start.sh [--dash]
#   --dash    Use Dash UI instead of Streamlit (better real-time)
# Press Ctrl+C to stop all services

USE_DASH=false
if [ "$1" == "--dash" ]; then
    USE_DASH=true
fi

cd "$(dirname "$0")/src"

echo "========================================"
echo "   MicroSpot Control System v2.0"
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

# Start UI (foreground)
if [ "$USE_DASH" == "true" ]; then
    echo "Starting Dash UI (port 8050)..."
    echo ""
    echo "========================================"
    echo "  Open: http://microspot:8050"
    echo "  API:  http://microspot:8000/docs"
    echo "  PS4:  Connect controller via Bluetooth"
    echo "========================================"
    echo ""
    python3 dash_app.py
else
    echo "Starting Streamlit UI (port 8501)..."
    echo ""
    echo "========================================"
    echo "  Open: http://microspot:8501"
    echo "  API:  http://microspot:8000/docs"
    echo "  PS4:  Connect controller via Bluetooth"
    echo "  TIP:  Use --dash for better real-time"
    echo "========================================"
    echo ""
    streamlit run app.py --server.port 8501 --server.headless true
fi

# Wait for processes
wait
