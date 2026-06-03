#!/usr/bin/env python3
"""
Controller Watchdog - Keeps PlayStation controller connected
Automatically reconnects when controller disconnects
"""

import subprocess
import time
import os

# Known controller MAC (will be detected automatically)
CONTROLLER_MAC = None

# Backoff config: start at 2s, double up to 60s on repeated failures
_reconnect_delay = 2
_MAX_RECONNECT_DELAY = 60
_FAILURE_THRESHOLD = 3
_consecutive_failures = 0

def get_paired_controller():
    """Find paired PlayStation controller"""
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'Wireless Controller' in line or 'DualSense' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]  # MAC address
    except:
        pass
    return None

def is_controller_connected():
    """Check if controller is connected"""
    return os.path.exists('/dev/input/js0')

def connect_controller(mac):
    """Try to connect to controller"""
    try:
        subprocess.run(
            ["bluetoothctl", "connect", mac],
            capture_output=True, timeout=10
        )
        return True
    except:
        return False

def ensure_bluetooth_on():
    """Make sure Bluetooth is enabled"""
    try:
        subprocess.run(["sudo", "rfkill", "unblock", "bluetooth"],
                      capture_output=True, timeout=5)
        subprocess.run(["sudo", "hciconfig", "hci0", "up"],
                      capture_output=True, timeout=5)
        subprocess.run(["bluetoothctl", "power", "on"],
                      capture_output=True, timeout=5)
    except:
        pass

def main():
    global CONTROLLER_MAC, _reconnect_delay, _consecutive_failures

    print("[Watchdog] Controller watchdog started")
    print("[Watchdog] Looking for paired PlayStation controller...")

    ensure_bluetooth_on()

    while True:
        # Try to find controller MAC if not known
        if not CONTROLLER_MAC:
            CONTROLLER_MAC = get_paired_controller()
            if CONTROLLER_MAC:
                print(f"[Watchdog] Found controller: {CONTROLLER_MAC}")
                _consecutive_failures = 0
                _reconnect_delay = 2
            else:
                time.sleep(10)
                continue

        # Check if connected
        if is_controller_connected():
            if _consecutive_failures > 0:
                print("[Watchdog] Controller back online.")
                _consecutive_failures = 0
                _reconnect_delay = 2
            time.sleep(5)  # All good, check every 5 sec (was 2)
        else:
            _consecutive_failures += 1
            if _consecutive_failures <= _FAILURE_THRESHOLD:
                print(f"[Watchdog] Controller disconnected (attempt {_consecutive_failures}), reconnecting...")
                connect_controller(CONTROLLER_MAC)
                time.sleep(2)
                if is_controller_connected():
                    print("[Watchdog] Reconnected!")
                    _consecutive_failures = 0
                    _reconnect_delay = 2
                else:
                    time.sleep(_reconnect_delay)
            else:
                # Exponential backoff to avoid DDoS-ing Bluetooth stack
                print(f"[Watchdog] Controller unavailable, retry in {_reconnect_delay}s...")
                time.sleep(_reconnect_delay)
                _reconnect_delay = min(_reconnect_delay * 2, _MAX_RECONNECT_DELAY)
                connect_controller(CONTROLLER_MAC)
                if is_controller_connected():
                    print("[Watchdog] Reconnected after backoff!")
                    _consecutive_failures = 0
                    _reconnect_delay = 2

if __name__ == "__main__":
    main()
