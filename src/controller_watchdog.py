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
    global CONTROLLER_MAC

    print("[Watchdog] Controller watchdog started")
    print("[Watchdog] Looking for paired PlayStation controller...")

    ensure_bluetooth_on()

    while True:
        # Try to find controller MAC if not known
        if not CONTROLLER_MAC:
            CONTROLLER_MAC = get_paired_controller()
            if CONTROLLER_MAC:
                print(f"[Watchdog] Found controller: {CONTROLLER_MAC}")
            else:
                time.sleep(5)
                continue

        # Check if connected
        if is_controller_connected():
            time.sleep(2)  # All good, check again in 2 sec
        else:
            print("[Watchdog] Controller disconnected, reconnecting...")
            if connect_controller(CONTROLLER_MAC):
                time.sleep(2)
                if is_controller_connected():
                    print("[Watchdog] Reconnected!")
                else:
                    print("[Watchdog] Reconnect failed, waiting...")
                    time.sleep(3)
            else:
                # Maybe controller was unpaired
                CONTROLLER_MAC = get_paired_controller()
                time.sleep(5)

if __name__ == "__main__":
    main()
