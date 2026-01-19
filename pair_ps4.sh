#!/bin/bash
#
# MicroSpot PlayStation Controller Bluetooth Pairing Helper
# Works with PS4 (DualShock 4) and PS5 (DualSense)
#
# Usage: ./pair_ps4.sh
#

echo "============================================"
echo "   MicroSpot PlayStation Controller Pairing"
echo "   (PS4 / PS5)"
echo "============================================"
echo ""
echo "Instructions:"
echo "  PS4: Hold SHARE + PS button"
echo "  PS5: Hold CREATE + PS button"
echo "  until the light bar blinks rapidly"
echo ""
echo "Press Enter when controller is in pairing mode..."
read

echo ""
echo "Enabling Bluetooth..."

# Unblock and enable Bluetooth
sudo rfkill unblock bluetooth
sleep 1
sudo hciconfig hci0 up
sleep 1

# Power on via bluetoothctl
bluetoothctl power on
bluetoothctl agent on
bluetoothctl default-agent

echo ""
echo "Scanning for 15 seconds..."
echo "(Keep controller in pairing mode!)"
echo ""

# Scan for devices
bluetoothctl --timeout 15 scan on

echo ""
echo "Looking for PlayStation controller..."

# Find controller - check for both PS4 and PS5 names
MAC=$(bluetoothctl devices | grep -iE "(wireless controller|dualsense)" | head -1 | awk '{print $2}')

if [ -z "$MAC" ]; then
    echo ""
    echo "No controller found!"
    echo ""
    echo "Troubleshooting:"
    echo "1. Make sure controller is in pairing mode"
    echo "   (light bar should blink rapidly)"
    echo "2. PS4: Hold SHARE + PS for 3 seconds"
    echo "   PS5: Hold CREATE + PS for 3 seconds"
    echo "3. Try again: ./pair_ps4.sh"
    exit 1
fi

DEVICE_NAME=$(bluetoothctl devices | grep -iE "(wireless controller|dualsense)" | head -1 | cut -d' ' -f3-)
echo ""
echo "Found: $DEVICE_NAME"
echo "MAC:   $MAC"
echo ""
echo "Pairing..."

# Pair, trust, and connect
bluetoothctl pair "$MAC"
sleep 2
bluetoothctl trust "$MAC"
sleep 1
bluetoothctl connect "$MAC"

echo ""
echo "============================================"
echo "   Pairing Complete!"
echo "============================================"
echo ""
echo "Controller should now be paired and trusted."
echo "It will connect automatically on future boots."
echo ""
echo "Test with:"
echo "  ls -la /dev/input/js*"
echo ""
echo "Start MicroSpot with:"
echo "  ./start.sh"
echo ""
