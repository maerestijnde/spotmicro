#!/usr/bin/env python3
"""
MicroSpot PlayStation Controller Interface

Reads PS4 (DualShock 4) or PS5 (DualSense) input via Bluetooth
and controls the robot through the FastAPI backend.

Usage:
    python3 ps4_controller.py [--api URL] [--interface /dev/input/js0]

Requirements:
    pip install pyPS4Controller requests
"""

import requests
import time
import argparse
import sys
import threading

try:
    from pyPS4Controller.controller import Controller
except ImportError:
    print("Error: pyPS4Controller not installed")
    print("Install with: sudo pip3 install pyPS4Controller")
    sys.exit(1)

from controller_config import ControllerConfig


class MicroSpotController(Controller):
    """
    PS4 Controller handler for MicroSpot robot

    Inherits from pyPS4Controller and overrides event methods
    to send commands to the FastAPI backend.
    """

    def __init__(self, api_url="http://localhost:8000", **kwargs):
        Controller.__init__(self, **kwargs)
        self.api_url = api_url
        self.config = ControllerConfig()

        # State tracking
        self.is_walking = False
        self.current_direction = None
        self.body_height = 40  # Default knee bend (degrees), synced at connect
        self.balance_enabled = False

        # Rate limiting for body updates
        self._last_body_update = 0

        # Analog stick state for body control
        self._right_stick = {"x": 0, "y": 0}
        self._triggers = {"l2": 0, "r2": 0}

        print(f"[MicroSpot] API URL: {self.api_url}")

    def _api_post(self, endpoint, data=None, silent=False):
        """Send POST request to API with error handling"""
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
        except requests.exceptions.ConnectionError:
            if not silent:
                print(f"[API] Connection failed")
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
        """Fire-and-forget POST request (non-blocking)"""
        def _do_post():
            try:
                requests.post(f"{self.api_url}{endpoint}", json=data or {}, timeout=0.3)
            except Exception:
                pass
        threading.Thread(target=_do_post, daemon=True).start()

    # ============== WALKING CONTROL (Left Stick) ==============

    def on_L3_up(self, value):
        """Left stick pushed up - walk forward"""
        if abs(value) < self.config.STICK_DEADZONE:
            return
        if not self.is_walking or self.current_direction != "forward":
            result = self._api_post("/api/gait/start", {"direction": "forward"})
            if result:
                self.is_walking = True
                self.current_direction = "forward"
                print("[Walk] FORWARD")

    def on_L3_down(self, value):
        """Left stick pushed down - walk backward"""
        print(f"[L3_down] value={value}, deadzone={self.config.STICK_DEADZONE}")
        if abs(value) < self.config.STICK_DEADZONE:
            print("[L3_down] Below deadzone, ignoring")
            return
        if not self.is_walking or self.current_direction != "backward":
            print("[L3_down] Starting backward walk...")
            result = self._api_post("/api/gait/start", {"direction": "backward"})
            print(f"[L3_down] API result: {result}")
            if result:
                self.is_walking = True
                self.current_direction = "backward"
                print("[Walk] BACKWARD")

    def on_L3_y_at_rest(self):
        """Left stick Y returned to center - stop walking"""
        if self.is_walking:
            self._api_post("/api/gait/stop")
            self.is_walking = False
            self.current_direction = None
            print("[Walk] STOPPED")

    def on_L3_left(self, value):
        """Left stick pushed left - lateral step left."""
        if abs(value) < self.config.STICK_DEADZONE:
            return
        self._update_lateral_rate(-value / 32767.0)

    def on_L3_right(self, value):
        """Left stick pushed right - lateral step right."""
        if abs(value) < self.config.STICK_DEADZONE:
            return
        self._update_lateral_rate(value / 32767.0)

    def on_L3_x_at_rest(self):
        """Left stick X-axis returned to center."""
        self._update_lateral_rate(0.0)

    def _update_lateral_rate(self, rate: float):
        """Update the gait controller lateral rate via API (async)."""
        rate = max(-1.0, min(1.0, rate))
        self._api_post_async("/api/gait/lateral", {"rate": rate})

    def _update_turn_rate(self, rate: float):
        """Update the gait controller turn rate via API (async)."""
        rate = max(-1.0, min(1.0, rate))
        self._api_post_async("/api/gait/turn", {"rate": rate})

    # ============== BODY ORIENTATION (Right Stick) ==============

    def on_R3_up(self, value):
        """Right stick Y up - body pitch forward"""
        self._right_stick["y"] = -value  # Invert for natural feel
        self._update_body_pose()

    def on_R3_down(self, value):
        """Right stick Y down - body pitch backward"""
        self._right_stick["y"] = -value
        self._update_body_pose()

    def on_R3_left(self, value):
        """Right stick X left - body roll left"""
        self._right_stick["x"] = value
        self._update_body_pose()

    def on_R3_right(self, value):
        """Right stick X right - body roll right"""
        self._right_stick["x"] = value
        self._update_body_pose()

    def on_R3_x_at_rest(self):
        """Right stick X centered"""
        self._right_stick["x"] = 0
        self._update_body_pose()

    def on_R3_y_at_rest(self):
        """Right stick Y centered"""
        self._right_stick["y"] = 0
        self._update_body_pose()

    def _update_body_pose(self):
        """Update body pose based on stick/trigger positions (rate limited)"""
        now = time.time()
        if now - self._last_body_update < self.config.BODY_UPDATE_INTERVAL:
            return
        self._last_body_update = now

        # Apply deadzone
        x = self._right_stick["x"] if abs(self._right_stick["x"]) > self.config.STICK_DEADZONE else 0
        y = self._right_stick["y"] if abs(self._right_stick["y"]) > self.config.STICK_DEADZONE else 0

        # Convert stick values to radians
        # Stick range: -32767 to 32767
        # Target range: -MAX to MAX radians
        phi = (x / 32767) * self.config.MAX_ROLL     # Roll
        theta = (y / 32767) * self.config.MAX_PITCH  # Pitch

        # Yaw from triggers
        l2 = self._triggers["l2"]
        r2 = self._triggers["r2"]
        psi = ((r2 - l2) / 32767) * self.config.MAX_YAW  # Yaw

        # Only send if there's actual movement (async for low latency)
        if phi != 0 or theta != 0 or psi != 0:
            self._api_post_async("/api/body", {"phi": phi, "theta": theta, "psi": psi})

    # ============== HEIGHT CONTROL (L1/L2) ==============

    def _sync_body_height(self):
        """Sync body_height with backend on connect"""
        try:
            result = self._api_get("/api/tuning")
            if result and "knee_bend" in result:
                self.body_height = result["knee_bend"]
                print(f"[Sync] knee_bend={self.body_height}")
        except Exception:
            pass

    def on_L1_press(self):
        """L1 - raise body (decrease knee bend)"""
        print(">>> L1 EVENT <<<")
        print(f"[L1] height was {self.body_height}")
        self.body_height = max(self.config.MIN_HEIGHT,
                               self.body_height - self.config.HEIGHT_STEP)
        print(f"[L1] now {self.body_height}")
        self._api_post("/api/gait/stand_height", {"knee_bend": self.body_height})
        self._api_post("/api/gait/preview_stand")

    def on_L1_release(self):
        pass

    def on_L2_press(self, value):
        """L2 trigger - lower body (increase knee bend)"""
        print(f">>> L2 EVENT <<< value={value}")
        # Only trigger on initial press (value crosses threshold)
        if not hasattr(self, '_l2_pressed') or not self._l2_pressed:
            self._l2_pressed = True
            print(f"[L2] height was {self.body_height}")
            self.body_height = min(self.config.MAX_HEIGHT,
                                   self.body_height + self.config.HEIGHT_STEP)
            print(f"[L2] now {self.body_height}")
            self._api_post("/api/gait/stand_height", {"knee_bend": self.body_height})
            self._api_post("/api/gait/preview_stand")

    def on_L2_release(self):
        """L2 released"""
        self._l2_pressed = False

    # ============== TRIGGERS (Turn/Yaw Control) ==============

    def on_R1_press(self):
        """R1 - turn left (while walking)"""
        print(">>> R1 EVENT <<<")
        self._update_turn_rate(-0.5)  # Turn left at 50%

    def on_R1_release(self):
        """R1 released - stop turning"""
        self._update_turn_rate(0.0)

    def on_R2_press(self, value):
        """R2 trigger - turn right (while walking) / yaw right (body)"""
        print(f">>> R2 EVENT <<< value={value}")
        self._triggers["r2"] = value
        self._update_body_pose()
        # Also update turn rate for walking
        turn = value / 32767.0
        self._update_turn_rate(turn)

    def on_R2_release(self):
        """R2 released"""
        self._triggers["r2"] = 0
        self._update_body_pose()
        self._update_turn_rate(0.0)

    # ============== D-PAD (Poses) ==============

    def on_up_arrow_press(self):
        """D-pad up - stand pose"""
        self._api_post("/api/pose/stand")
        print("[Pose] STAND")

    def on_down_arrow_press(self):
        """D-pad down - sit pose"""
        self._api_post("/api/pose/sit")
        print("[Pose] SIT")

    def on_left_arrow_press(self):
        """D-pad left - rest pose"""
        self._api_post("/api/pose/rest")
        print("[Pose] REST")

    def on_right_arrow_press(self):
        """D-pad right - neutral pose"""
        self._api_post("/api/pose/neutral")
        print("[Pose] NEUTRAL")

    def on_up_down_arrow_release(self):
        pass  # Poses are one-shot commands, no release action needed

    def on_left_right_arrow_release(self):
        pass  # Poses are one-shot commands, no release action needed

    # ============== FACE BUTTONS ==============

    def on_x_press(self):
        """X button - single step forward"""
        if not self.is_walking:
            self._api_post("/api/gait/step", {"direction": "forward"})
            print("[Step] FORWARD")

    def on_x_release(self):
        pass  # Single step is one-shot, no release action needed

    def on_circle_press(self):
        """Circle - stop walking"""
        self._api_post("/api/gait/stop")
        self.is_walking = False
        self.current_direction = None
        print("[STOP]")

    def on_circle_release(self):
        pass  # Stop is one-shot, no release action needed

    def on_triangle_press(self):
        """Triangle - toggle balance mode"""
        self.balance_enabled = not self.balance_enabled
        self._api_post("/api/balance/enable", {"enable": self.balance_enabled})
        status = "ON" if self.balance_enabled else "OFF"
        print(f"[Balance] {status}")

    def on_triangle_release(self):
        pass  # Toggle is one-shot, no release action needed

    def on_square_press(self):
        """Square - return to calibrated neutral positions"""
        self._api_post("/api/goto_neutrals")
        print("[GOTO NEUTRALS]")

    def on_square_release(self):
        pass  # Neutrals is one-shot, no release action needed

    # ============== MENU BUTTONS ==============

    def on_options_press(self):
        """Options - emergency stop"""
        self._api_post("/api/gait/stop")
        self._api_post("/api/pose/neutral")
        self.is_walking = False
        self.current_direction = None
        self._right_stick = {"x": 0, "y": 0}
        self._triggers = {"l2": 0, "r2": 0}
        print("[EMERGENCY STOP]")

    def on_options_release(self):
        pass  # Emergency stop is one-shot, no release action needed

    def on_share_press(self):
        """Share - calibrate IMU"""
        self._api_post("/api/balance/calibrate")
        print("[IMU] Calibrating...")

    def on_share_release(self):
        pass  # IMU calibration is one-shot, no release action needed

    def on_playstation_button_press(self):
        """PS button - show status"""
        status = self._api_get("/api/gait/status")
        if status:
            running = status.get('running', False)
            direction = status.get('direction', 'none')
            print(f"[Status] running={running}, direction={direction}")
        else:
            print("[Status] Could not get status")

    def on_playstation_button_release(self):
        pass  # Status display is one-shot, no release action needed

    # ============== ANALOG STICK PRESS (L3/R3) ==============

    def on_L3_press(self):
        """L3 (left stick click) - single step backward"""
        if not self.is_walking:
            self._api_post("/api/gait/step", {"direction": "backward"})
            print("[Step] BACKWARD")

    def on_L3_release(self):
        pass  # Single step is one-shot, no release action needed

    def on_R3_press(self):
        """R3 (right stick click) - reset body orientation"""
        self._right_stick = {"x": 0, "y": 0}
        self._triggers = {"l2": 0, "r2": 0}
        self._api_post("/api/body", {"phi": 0, "theta": 0, "psi": 0})
        print("[Body] Reset orientation")

    def on_R3_release(self):
        pass  # Body reset is one-shot, no release action needed

    # ============== DUALSENSE (PS5) BUTTON REMAPPING ==============
    # DualSense uses different button codes than DualShock 4
    # DS4: L1=4, R1=5, L2=axis2, R2=axis5
    # DS5: L1=6, R1=7, L2=4, R2=5

    def on_unknown_event(self, event):
        """Handle unmapped events - includes DualSense button remapping"""
        # Button events (type 1)
        if event.type == 1:
            # DualSense R1 button (code 7)
            if event.code == 7:
                if event.value == 1:
                    print("[DualSense] R1 pressed (remapped)")
                    self.on_R1_press()
                else:
                    self.on_R1_release()
                return
            # DualSense L1 button (code 6) - might also need remapping
            elif event.code == 6:
                if event.value == 1:
                    print("[DualSense] L1 pressed (remapped)")
                    self.on_L1_press()
                else:
                    self.on_L1_release()
                return
            # DualSense R2 as button (code 5)
            elif event.code == 5:
                if event.value == 1:
                    print("[DualSense] R2 pressed (button mode)")
                    self.on_R2_press(32767)  # Max value
                else:
                    self.on_R2_release()
                return
            # DualSense L2 as button (code 4)
            elif event.code == 4:
                if event.value == 1:
                    print("[DualSense] L2 pressed (button mode)")
                    self.on_L2_press(32767)  # Max value
                else:
                    self.on_L2_release()
                return

        # Axis events (type 2) - DualSense triggers as analog axes
        elif event.type == 2:
            # DualSense L2 trigger (axis 3)
            if event.code == 3:
                if event.value > 1000:  # Threshold for "pressed"
                    self.on_L2_press(event.value)
                elif event.value < 100:
                    self.on_L2_release()
                return
            # DualSense R2 trigger (axis 4)
            elif event.code == 4:
                if event.value > 1000:
                    self.on_R2_press(event.value)
                elif event.value < 100:
                    self.on_R2_release()
                return

        # Log truly unknown events for debugging
        print(f"[UNKNOWN EVENT] type={event.type} code={event.code} value={event.value}")


def print_controls():
    """Print control reference"""
    print("=" * 60)
    print("   MicroSpot PlayStation Controller (PS4/PS5)")
    print("=" * 60)
    print()
    print("  MOVEMENT")
    print("    Left Stick Up/Down : Walk forward/backward")
    print("    Left Stick L/R     : Lateral step left/right")
    print("    L2/R2 Triggers     : Turn left/right (while walking)")
    print("    X Button           : Single step forward")
    print("    L3 Click           : Single step backward")
    print("    Circle             : Stop walking")
    print()
    print("  BODY CONTROL")
    print("    Right Stick        : Pitch/Roll")
    print("    L2/R2 Triggers     : Yaw left/right (body)")
    print("    L1/R1              : Lower/Raise body")
    print("    R3 Click           : Reset body orientation")
    print()
    print("  POSES")
    print("    D-pad Up           : Stand")
    print("    D-pad Down         : Sit")
    print("    D-pad Left         : Rest")
    print("    D-pad Right        : Neutral")
    print()
    print("  OTHER")
    print("    Triangle           : Toggle balance mode")
    print("    Square             : Go to calibrated neutrals")
    print("    Share              : Calibrate IMU")
    print("    Options            : EMERGENCY STOP")
    print("    PS Button          : Show status")
    print()
    print("=" * 60)


def on_connect(controller):
    """Called when controller connects"""
    print()
    print("[Controller] CONNECTED!")
    print(f"[Debug] body_height before sync: {controller.body_height}")
    controller._sync_body_height()
    print(f"[Debug] body_height after sync: {controller.body_height}")
    print(f"[Debug] MIN_HEIGHT={controller.config.MIN_HEIGHT}, MAX_HEIGHT={controller.config.MAX_HEIGHT}")
    print(f"[Debug] R1 method exists: {hasattr(controller, 'on_R1_press')}")
    print(f"[Debug] R2 method exists: {hasattr(controller, 'on_R2_press')}")
    print()


def on_disconnect(controller):
    """Called when controller disconnects - stop robot for safety"""
    print()
    print("[Controller] DISCONNECTED - stopping robot for safety")
    try:
        requests.post(f"{controller.api_url}/api/gait/stop", timeout=1)
    except:
        pass
    controller.is_walking = False
    controller.current_direction = None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="MicroSpot PS4 Controller Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 ps4_controller.py
  python3 ps4_controller.py --api http://192.168.1.100:8000
  python3 ps4_controller.py --interface /dev/input/js1
        """
    )
    parser.add_argument(
        "--api", "-a",
        default="http://localhost:8000",
        help="Backend API URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--interface", "-i",
        default="/dev/input/js0",
        help="Controller interface (default: /dev/input/js0)"
    )
    args = parser.parse_args()

    print_controls()
    print(f"API: {args.api}")
    print(f"Interface: {args.interface}")
    print()
    print("Waiting for controller...")
    print("(Hold SHARE + PS button to put controller in pairing mode)")
    print()

    controller = MicroSpotController(
        api_url=args.api,
        interface=args.interface,
        connecting_using_ds4drv=False
    )

    # Listen forever with reconnection
    while True:
        try:
            print("[Listen] Starting controller listener...")
            controller.listen(
                timeout=120,  # 2 minute timeout before reconnect attempt
                on_connect=lambda: on_connect(controller),
                on_disconnect=lambda: on_disconnect(controller)
            )
            print("[Listen] Listener returned, will restart...")
        except KeyboardInterrupt:
            print("\n[Exit] Stopping...")
            # Stop robot on exit
            try:
                requests.post(f"{args.api}/api/gait/stop", timeout=1)
            except:
                pass
            break
        except Exception as e:
            print(f"[Error] {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    main()
