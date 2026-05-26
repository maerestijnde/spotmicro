#!/bin/bash
#
# MicroSpot PlayStation Controller Bluetooth Pairing Helper
# Works with PS4 (DualShock 4) and PS5 (DualSense)
#
# Usage: ./pair_ps4.sh
#

set -e

CONTROLLER_MAC=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}$1${NC}"; }
print_error()   { echo -e "${RED}$1${NC}"; }
print_warn()    { echo -e "${YELLOW}$1${NC}"; }

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
read -p "Press Enter when controller is in pairing mode..."

echo ""
echo "Step 1/5: Enabling Bluetooth..."

# Unblock and enable Bluetooth
sudo rfkill unblock bluetooth 2>/dev/null || true
sleep 1
sudo hciconfig hci0 up 2>/dev/null || true
sleep 1

bluetoothctl power on >/dev/null 2>&1
bluetoothctl agent on >/dev/null 2>&1
bluetoothctl default-agent >/dev/null 2>&1

echo "Step 2/5: Cleaning up old pairings..."

# Remove existing PlayStation controllers from BlueZ
# This is CRITICAL - dualsense often fails re-pairing if old keys exist
for mac in $(bluetoothctl devices Paired 2>/dev/null | grep -iE "(wireless controller|dualsense|dualshock)" | awk '{print $2}'); do
    print_warn "  Removing old pairing: $mac"
    bluetoothctl remove "$mac" >/dev/null 2>&1 || true
    # Also clear any cached device info
    sudo rm -f "/var/lib/bluetooth/$(hciconfig hci0 | grep 'BD Address' | awk '{print $3}')/${mac}/info" 2>/dev/null || true
done

# Forget any cached controller MAC
CONTROLLER_MAC=""

# Give BlueZ a moment to process
sleep 2

echo "Step 3/5: Resetting Bluetooth adapter..."
bluetoothctl discoverable on >/dev/null 2>&1 || true
sleep 1

echo "Step 4/5: Scanning for controller..."
echo "(Keep controller in pairing mode!)"
echo ""

# Do a fresh scan - look for the controller
FOUND=0
SCAN_SECONDS=20

# Start scan in background and capture output
SCAN_OUTPUT=$(mktemp)
timeout $SCAN_SECONDS bluetoothctl --timeout $SCAN_SECONDS scan on > "$SCAN_OUTPUT" 2>&1 &
SCAN_PID=$!

# Wait for scan to complete
wait $SCAN_PID 2>/dev/null || true

# Check for controller in scan results and in device list
sleep 2

# Try to find the controller
MAC=$(bluetoothctl devices | grep -iE "(wireless controller|dualsense|dualshock)" | head -1 | awk '{print $2}')
DEVICE_NAME=$(bluetoothctl devices | grep -iE "(wireless controller|dualsense|dualshock)" | head -1 | cut -d' ' -f3-)

rm -f "$SCAN_OUTPUT"

if [ -z "$MAC" ]; then
    echo ""
    print_error "No controller found during scan!"
    echo ""
    echo "Troubleshooting:"
    echo "1. Make sure controller is in pairing mode"
    echo "   (light bar should blink rapidly WHITE/BLUE)"
    echo "2. PS4: Hold SHARE + PS for 3+ seconds"
    echo "   PS5: Hold CREATE + PS for 3+ seconds"
    echo "3. If controller was previously paired to another device,"
    echo "   unpair it there first"
    echo "4. Try turning the controller fully OFF, then retry pairing"
    echo ""
    echo "You can also try a full Bluetooth reset:"
    echo "  sudo systemctl restart bluetooth"
    echo "  sudo rm -rf /var/lib/bluetooth/*"
    echo "  sudo reboot"
    exit 1
fi

echo ""
print_success "Found: $DEVICE_NAME"
print_success "MAC:   $MAC"
echo ""

echo "Step 5/5: Pairing, trusting & connecting..."

# Pair
if ! bluetoothctl pair "$MAC" >/dev/null 2>&1; then
    print_warn "Standard pair failed, trying alternative method..."
    bluetoothctl pairable on >/dev/null 2>&1 || true
    if ! bluetoothctl pair "$MAC" >/dev/null 2>&1; then
        print_error "Pairing failed!"
        echo "Try: sudo systemctl restart bluetooth && sudo rm -rf /var/lib/bluetooth/* && sudo reboot"
        exit 1
    fi
fi
print_success "  Paired OK"

sleep 2

# Trust
bluetoothctl trust "$MAC" >/dev/null 2>&1 || true
print_success "  Trusted OK"

sleep 1

# Connect
if bluetoothctl connect "$MAC" >/dev/null 2>&1; then
    print_success "  Connected OK"
else
    print_warn "  Immediate connect failed, this is normal for DualSense"
    print_warn "  The controller should auto-connect when you press the PS button"
fi

# Wait for HID device to appear
echo ""
echo "Waiting for controller HID interface (/dev/input/js0)..."
for i in {1..10}; do
    if [ -e /dev/input/js0 ]; then
        print_success "Controller HID ready!"
        break
    fi
    sleep 1
done

echo ""
echo "============================================"
if [ -e /dev/input/js0 ]; then
    print_success "   Pairing Complete! Controller ready."
else
    print_warn "   Pairing stored. Press PS button to connect."
fi
echo "============================================"
echo ""

# Show device info
bluetoothctl info "$MAC" 2>/dev/null | grep -E "Name:|Connected:|Paired:|Trusted:" || true
echo ""

# Check js device
if ls -la /dev/input/js* 2>/dev/null; then
    echo ""
    echo "Controller input devices detected."
fi

echo ""
echo "Start MicroSpot with:"
echo "  ./start.sh"
echo ""
