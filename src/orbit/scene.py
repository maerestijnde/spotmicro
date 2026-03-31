"""
Orbit 3D robot scene - Three.js visualization via NiceGUI.

Ported from nicegui_app.py lines 427-551 with Orbit styling.
Uses object pooling: body, head, joint spheres and ground are created once
and moved each frame. Only leg-segment lines are recreated (NiceGUI lines
don't support endpoint updates). Change detection skips frames where
nothing moved.
"""
from nicegui import ui

from orbit.state import LEG_CONFIG
from orbit.kinematics import (
    BODY_LENGTH, BODY_WIDTH,
    apply_body_rotation, compute_all_leg_points,
)


class RobotScene:
    """Manages the Three.js 3D scene for the robot visualization."""

    def __init__(self):
        self.scene: ui.scene = None
        self._last_hash = None
        # Pooled objects (created once)
        self._body_box = None
        self._head_sphere = None
        self._ground = None
        self._joint_spheres: dict = {}   # (leg_id, joint_key) -> sphere
        # Lines must be recreated each frame
        self._lines: list = []
        self._initialized = False

    def create(self, height: int = 400) -> ui.scene:
        self.scene = ui.scene(width=-1, height=height, grid=True).classes("w-full rounded-lg")
        with self.scene:
            self.scene.move_camera(x=0.3, y=0.25, z=0.3, look_at_x=0, look_at_y=0.1, look_at_z=0)
        return self.scene

    def _init_objects(self, all_legs: dict, body_y: float, pitch: float, roll: float, yaw: float):
        """Create all pooled scene objects once."""
        with self.scene:
            # Static ground plane (Orbit dark navy)
            self._ground = self.scene.box(0.5, 0.001, 0.5).move(0, -0.001, 0).material("#0d1117", opacity=0.3)

            # Body box
            body_center = [0, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                body_center = apply_body_rotation([body_center], pitch, roll, yaw, [0, body_y, 0])[0]
            self._body_box = self.scene.box(BODY_LENGTH, 0.05, BODY_WIDTH).move(
                body_center[0], body_center[1], body_center[2]
            ).material("#1a3a5c", opacity=0.85)

            # Head sphere
            hx = BODY_LENGTH / 2
            head_pos = [hx + 0.02, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                head_pos = apply_body_rotation([head_pos], pitch, roll, yaw, [0, body_y, 0])[0]
            self._head_sphere = self.scene.sphere(0.012).move(
                head_pos[0], head_pos[1], head_pos[2]
            ).material("#ffcc00")

            # 16 joint spheres (4 legs x 4 joints)
            for leg_id, pts in all_legs.items():
                color = LEG_CONFIG[leg_id]["color"]
                for joint_key in ["hip_origin", "hip_end", "knee_end", "foot_end"]:
                    p = pts[joint_key]
                    size = 0.008 if joint_key != "foot_end" else 0.01
                    sphere = self.scene.sphere(size).move(p[0], p[1], p[2]).material(color)
                    self._joint_spheres[(leg_id, joint_key)] = sphere

            # Initial lines
            self._create_lines(all_legs)

        self._initialized = True

    def _create_lines(self, all_legs: dict):
        """(Re)create leg segment lines."""
        for line in self._lines:
            try:
                line.delete()
            except Exception:
                pass
        self._lines.clear()

        for leg_id, pts in all_legs.items():
            color = LEG_CONFIG[leg_id]["color"]
            for s, e in [("hip_origin", "hip_end"), ("hip_end", "knee_end"), ("knee_end", "foot_end")]:
                line = self.scene.line(pts[s], pts[e]).material(color)
                self._lines.append(line)

    def update(self, servo_angles: dict, pitch: float = 0, roll: float = 0, yaw: float = 0):
        """Update the robot geometry. Moves pooled objects instead of recreating."""
        if self.scene is None:
            return

        # Change detection - skip if nothing moved
        try:
            angle_vals = tuple(servo_angles.get(str(i), servo_angles.get(i, 90)) for i in range(12))
        except Exception:
            angle_vals = ()
        current_hash = hash((angle_vals, round(pitch, 1), round(roll, 1), round(yaw, 1)))
        if current_hash == self._last_hash:
            return
        self._last_hash = current_hash

        # Compute leg positions
        all_legs, body_y = compute_all_leg_points(servo_angles, body_pitch=pitch, body_roll=roll, body_yaw=yaw)

        # First call: create all objects
        if not self._initialized:
            self._init_objects(all_legs, body_y, pitch, roll, yaw)
            return

        with self.scene:
            # Move body box
            body_center = [0, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                body_center = apply_body_rotation([body_center], pitch, roll, yaw, [0, body_y, 0])[0]
            self._body_box.move(body_center[0], body_center[1], body_center[2])

            # Move head sphere
            hx = BODY_LENGTH / 2
            head_pos = [hx + 0.02, body_y, 0]
            if pitch != 0 or roll != 0 or yaw != 0:
                head_pos = apply_body_rotation([head_pos], pitch, roll, yaw, [0, body_y, 0])[0]
            self._head_sphere.move(head_pos[0], head_pos[1], head_pos[2])

            # Move joint spheres (16 moves instead of 16 delete+create)
            for leg_id, pts in all_legs.items():
                for joint_key in ["hip_origin", "hip_end", "knee_end", "foot_end"]:
                    p = pts[joint_key]
                    self._joint_spheres[(leg_id, joint_key)].move(p[0], p[1], p[2])

            # Recreate lines (NiceGUI lines can't update endpoints)
            self._create_lines(all_legs)
