#!/usr/bin/env python3
"""
MicroSpot Xbox 360 Controller Interface

Reads Xbox 360 controller input via USB and controls the robot
through the FastAPI backend.

Usage:
    python3 xbox_controller.py [--api URL] [--interface /dev/input/js0]

Requirements:
    pip install inputs requests

    OR use without inputs library (raw joystick reading)
"""

import requests
import time
import argparse
import sys
import struct
import threading
from pathlib import Path

from controller_config import ControllerConfig


class Xbox360Controller:
    """
    Xbox 360 Controller handler for MicroSpot robot

    Reads raw joystick events from /dev/input/js0 and sends
    commands to the FastAPI backend.

    Xbox 360 Button Mapping (Linux xpad driver):
        Buttons:
            A=0, B=1, X=2, Y=3
            LB=4, RB=5
            Back=6, Start=7
            Xbox=8
            Left Stick Click=9, Right Stick Click=10

        Axes:
            Left Stick X=0, Y=1
            LT=2 (trigger, 0 to 32767)
            Right Stick X=3, Y=4
            RT=5 (trigger, 0 to 32767)
            D-pad X=6, Y=7
    """

    # Button mappings
    BTN_A = 0
    BTN_B = 1
    BTN_X = 2
    BTN_Y = 3
    BTN_LB = 4
    BTN_RB = 5
    BTN_BACK = 6
    BTN_START = 7
    BTN_XBOX = 8
    BTN_LSTICK = 9
    BTN_RSTICK = 10

    # Axis mappings
    AXIS_LX = 0  # Left stick X
    AXIS_LY = 1  # Left stick Y
    AXIS_LT = 2  # Left trigger
    AXIS_RX = 3  # Right stick X
    AXIS_RY = 4  # Right stick Y
    AXIS_RT = 5  # Right trigger
    AXIS_DX = 6  # D-pad X
    AXIS_DY = 7  # D-pad Y

    def __init__(self, api_url="http://localhost:8000", interface="/dev/input/js0"):
        self.api_url = api_url
        self.interface = interface
        self.config = ControllerConfig()
        self.running = False

        # State tracking
        self.is_walking = False
        self.current_direction = None
        self.body_height = 40  # Default knee bend
        self.balance_enabled = False

        # Rate limiting for body updates
        self._last_body_update = 0

        # Analog state
        self._left_stick = {"x": 0, "y": 0}
        self._right_stick = {"x": 0, "y": 0}
        self._triggers = {"lt": 0, "rt": 0}

        print(f"[Xbox360] API URL: {self.api_url}")
        print(f"[Xbox360] Interface: {self.interface}")

    def _api_post(self, endpoint, data=None, silent=False):
        """Send POST request to API"""
        try:
            url = f"{self.api_url}{endpoint}"
            resp = requests.post(url, json=data or {}, timeout=0.3)
            if resp.status_code == 200:
                return resp.json()
            elif not silent:
                print(f"[API] Error {resp.status_code}: {endpoint}")
            return None
        except requests.exceptions.Timeout:
            if not silent:
                print(f"[API] Timeout: {endpoint}")
            return None
        except Exception:
            return None

    def _api_get(self, endpoint):
        """Send GET request to API"""
        try:
            url = f"{self.api_url}{endpoint}"
            resp = requests.get(url, timeout=0.3)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def _api_post_async(self, endpoint, data=None):
        """Fire-and-forget POST request"""
        def _do_post():
            try:
                requests.post(f"{self.api_url}{endpoint}", json=data or {}, timeout=0.3)
            except Exception:
                pass
        threading.Thread(target=_do_post, daemon=True).start()

    def _sync_body_height(self):
        """Sync body_height with backend"""
        try:
            result = self._api_get("/api/tuning")
            if result and "knee_bend" in result:
                self.body_height = result["knee_bend"]
                print(f"[Sync] knee_bend={self.body_height}")
        except Exception:
            pass

    # ============== BUTTON HANDLERS ==============

    def on_button(self, button, pressed):
        """Handle button press/release"""
        if pressed:
            if button == self.BTN_A:
                # A = Single step forward (like X on PS)
                if not self.is_walking:
                    self._api_post("/api/gait/step", {"direction": "forward"})
                    print("[Step] FORWARD")

            elif button == self.BTN_B:
                # B = Stop (like Circle on PS)
                self._api_post("/api/gait/stop")
                self.is_walking = False
                self.current_direction = None
                print("[STOP]")

            elif button == self.BTN_X:
                # X = Go to neutrals (like Square on PS)
                self._api_post("/api/goto_neutrals")
                print("[GOTO NEUTRALS]")

            elif button == self.BTN_Y:
                # Y = Toggle balance (like Triangle on PS)
                self.balance_enabled = not self.balance_enabled
                self._api_post("/api/balance/enable", {"enable": self.balance_enabled})
                status = "ON" if self.balance_enabled else "OFF"
                print(f"[Balance] {status}")

            elif button == self.BTN_LB:
                # LB = Lower body (like L1 on PS)
                print(">>> LB EVENT <<<")
                self.body_height = min(self.config.MAX_HEIGHT,
                                       self.body_height + self.config.HEIGHT_STEP)
                print(f"[LB] Body height now {self.body_height}")
                self._api_post("/api/gait/stand_height", {"knee_bend": self.body_height})
                self._api_post("/api/gait/preview_stand")

            elif button == self.BTN_RB:
                # RB = Raise body (like R1 on PS)
                print(">>> RB EVENT <<<")
                self.body_height = max(self.config.MIN_HEIGHT,
                                       self.body_height - self.config.HEIGHT_STEP)
                print(f"[RB] Body height now {self.body_height}")
                self._api_post("/api/gait/stand_height", {"knee_bend": self.body_height})
                self._api_post("/api/gait/preview_stand")

            elif button == self.BTN_BACK:
                # Back = Calibrate IMU (like Share on PS)
                self._api_post("/api/balance/calibrate")
                print("[IMU] Calibrating...")

            elif button == self.BTN_START:
                # Start = Emergency stop (like Options on PS)
                self._api_post("/api/gait/stop")
                self._api_post("/api/pose/neutral")
                self.is_walking = False
                self.current_direction = None
                print("[EMERGENCY STOP]")

            elif button == self.BTN_XBOX:
                # Xbox button = Show status
                status = self._api_get("/api/gait/status")
                if status:
                    print(f"[Status] running={status.get('running')}, direction={status.get('direction')}")

            elif button == self.BTN_LSTICK:
                # Left stick click = Single step backward
                if not self.is_walking:
                    self._api_post("/api/gait/step", {"direction": "backward"})
                    print("[Step] BACKWARD")

            elif button == self.BTN_RSTICK:
                # Right stick click = Reset body orientation
                self._right_stick = {"x": 0, "y": 0}
                self._triggers = {"lt": 0, "rt": 0}
                self._api_post("/api/body", {"phi": 0, "theta": 0, "psi": 0})
                print("[Body] Reset orientation")

    # ============== AXIS HANDLERS ==============

    def on_axis(self, axis, value):
        """Handle axis movement"""

        # Left stick Y - Walk forward/backward
        if axis == self.AXIS_LY:
            self._left_stick["y"] = value
            if value < -self.config.STICK_DEADZONE:
                # Up = forward
                if not self.is_walking or self.current_direction != "forward":
                    result = self._api_post("/api/gait/start", {"direction": "forward"})
                    if result:
                        self.is_walking = True
                        self.current_direction = "forward"
                        print("[Walk] FORWARD")
            elif value > self.config.STICK_DEADZONE:
                # Down = backward
                if not self.is_walking or self.current_direction != "backward":
                    result = self._api_post("/api/gait/start", {"direction": "backward"})
                    if result:
                        self.is_walking = True
                        self.current_direction = "backward"
                        print("[Walk] BACKWARD")
            else:
                # Centered - stop
                if self.is_walking and self._left_stick["x"] == 0:
                    self._api_post("/api/gait/stop")
                    self.is_walking = False
                    self.current_direction = None
                    print("[Walk] STOPPED")

        # Left stick X - Lateral movement
        elif axis == self.AXIS_LX:
            self._left_stick["x"] = value
            if abs(value) > self.config.STICK_DEADZONE:
                rate = value / 32767.0
                self._api_post_async("/api/gait/lateral", {"rate": rate})
            else:
                self._api_post_async("/api/gait/lateral", {"rate": 0})

        # Right stick - Body pitch/roll
        elif axis == self.AXIS_RX:
            self._right_stick["x"] = value
            self._update_body_pose()

        elif axis == self.AXIS_RY:
            self._right_stick["y"] = value
            self._update_body_pose()

        # Left trigger - Turn left + Yaw
        elif axis == self.AXIS_LT:
            self._triggers["lt"] = value
            self._update_body_pose()
            turn = -(value / 32767.0)
            self._api_post_async("/api/gait/turn", {"rate": turn})

        # Right trigger - Turn right + Yaw
        elif axis == self.AXIS_RT:
            self._triggers["rt"] = value
            self._update_body_pose()
            turn = value / 32767.0
            self._api_post_async("/api/gait/turn", {"rate": turn})

        # D-pad Y - Poses
        elif axis == self.AXIS_DY:
            if value < -16000:
                # Up
                self._api_post("/api/pose/stand")
                print("[Pose] STAND")
            elif value > 16000:
                # Down
                self._api_post("/api/pose/sit")
                print("[Pose] SIT")

        # D-pad X - Poses
        elif axis == self.AXIS_DX:
            if value < -16000:
                # Left
                self._api_post("/api/pose/rest")
                print("[Pose] REST")
            elif value > 16000:
                # Right
                self._api_post("/api/pose/neutral")
                print("[Pose] NEUTRAL")

    def _update_body_pose(self):
        """Update body pose based on stick/trigger positions"""
        now = time.time()
        if now - self._last_body_update < self.config.BODY_UPDATE_INTERVAL:
            return
        self._last_body_update = now

        # Apply deadzone
        x = self._right_stick["x"] if abs(self._right_stick["x"]) > self.config.STICK_DEADZONE else 0
        y = self._right_stick["y"] if abs(self._right_stick["y"]) > self.config.STICK_DEADZONE else 0

        # Convert to radians
        phi = (x / 32767) * self.config.MAX_ROLL
        theta = (-y / 32767) * self.config.MAX_PITCH  # Invert Y

        # Yaw from triggers
        lt = self._triggers["lt"]
        rt = self._triggers["rt"]
        psi = ((rt - lt) / 32767) * self.config.MAX_YAW

        if phi != 0 or theta != 0 or psi != 0:
            self._api_post_async("/api/body", {"phi": phi, "theta": theta, "psi": psi})

    # ============== MAIN LOOP ==============

    def listen(self):
        """Main event loop - reads from joystick device"""
        print(f"\n[Xbox360] Opening {self.interface}...")

        # Wait for device
        while not Path(self.interface).exists():
            print(f"[Xbox360] Waiting for controller at {self.interface}...")
            time.sleep(2)

        print("[Xbox360] Controller connected!")
        self._sync_body_height()

        # Event format: timestamp (4 bytes), value (2 bytes), type (1 byte), number (1 byte)
        EVENT_FORMAT = "IhBB"
        EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

        self.running = True

        try:
            with open(self.interface, "rb") as js:
                while self.running:
                    event = js.read(EVENT_SIZE)
                    if len(event) < EVENT_SIZE:
                        break

                    timestamp, value, event_type, number = struct.unpack(EVENT_FORMAT, event)

                    # Type 1 = button, Type 2 = axis
                    # Bit 0x80 = init event (ignore)
                    if event_type & 0x80:
                        continue

                    if event_type == 1:
                        self.on_button(number, value == 1)
                    elif event_type == 2:
                        self.on_axis(number, value)

        except FileNotFoundError:
            print(f"[Xbox360] Device {self.interface} not found")
        except PermissionError:
            print(f"[Xbox360] Permission denied for {self.interface}")
            print("Try: sudo chmod 666 /dev/input/js0")
        except KeyboardInterrupt:
            print("\n[Xbox360] Stopping...")
        finally:
            self.running = False
            # Stop robot on exit
            try:
                requests.post(f"{self.api_url}/api/gait/stop", timeout=1)
            except:
                pass


def print_controls():
    """Print control reference"""
    print("=" * 60)
    print("   MicroSpot Xbox 360 Controller")
    print("=" * 60)
    print()
    print("  MOVEMENT")
    print("    Left Stick Up/Down : Walk forward/backward")
    print("    Left Stick L/R     : Lateral step left/right")
    print("    LT/RT Triggers     : Turn left/right")
    print("    A Button           : Single step forward")
    print("    Left Stick Click   : Single step backward")
    print("    B Button           : Stop walking")
    print()
    print("  BODY CONTROL")
    print("    Right Stick        : Pitch/Roll")
    print("    LT/RT Triggers     : Yaw left/right")
    print("    LB/RB              : Lower/Raise body")
    print("    Right Stick Click  : Reset orientation")
    print()
    print("  POSES (D-pad)")
    print("    Up                 : Stand")
    print("    Down               : Sit")
    print("    Left               : Rest")
    print("    Right              : Neutral")
    print()
    print("  OTHER")
    print("    Y Button           : Toggle balance")
    print("    X Button           : Go to neutrals")
    print("    Back               : Calibrate IMU")
    print("    Start              : EMERGENCY STOP")
    print("    Xbox Button        : Show status")
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="MicroSpot Xbox 360 Controller")
    parser.add_argument("--api", "-a", default="http://localhost:8000",
                        help="Backend API URL")
    parser.add_argument("--interface", "-i", default="/dev/input/js0",
                        help="Controller interface")
    args = parser.parse_args()

    print_controls()

    controller = Xbox360Controller(
        api_url=args.api,
        interface=args.interface
    )

    # Listen with reconnection
    while True:
        try:
            controller.listen()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Error] {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    main()
