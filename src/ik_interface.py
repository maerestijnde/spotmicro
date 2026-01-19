#!/usr/bin/env python3
"""IK Interface for MicroSpot - Correct coordinate mapping"""
import numpy as np
from math import degrees
import json
from pathlib import Path
from kinematics.spot_micro_stick_figure import SpotMicroStickFigure

# Default calibration path
_CALIBRATION_FILE = Path(__file__).parent / "calibration.json"

class IKInterface:
    LEG_TO_IK_INDEX = {'RR': 0, 'FR': 1, 'FL': 2, 'RL': 3}
    LEG_CHANNELS = {
        'FL': [0, 1, 2], 'FR': [3, 4, 5],
        'RL': [6, 7, 8], 'RR': [9, 10, 11],
    }
    LEFT_LEGS = ['FL', 'RL']

    def __init__(self, calibration_path=None, body_height=0.10):
        self.body_height = body_height
        self.model = SpotMicroStickFigure(x=0, y=body_height, z=0)
        self.calibration = {}
        if calibration_path:
            self._load_calibration(calibration_path)
        
        # Foot positions: include hip_length in Z offset
        hl = self.model.body_length / 2
        hw = self.model.body_width / 2 + self.model.hip_length
        self.neutral_feet = {
            'FL': np.array([hl, 0, -hw]),
            'FR': np.array([hl, 0, hw]),
            'RL': np.array([-hl, 0, -hw]),
            'RR': np.array([-hl, 0, hw]),
        }

    def _load_calibration(self, path):
        try:
            with open(path) as f:
                data = json.load(f)
            self.calibration = {int(k): v for k, v in data.get('servos', {}).items()}
        except: pass

    def get_neutral_foot_positions(self):
        return {k: v.copy() for k, v in self.neutral_feet.items()}

    def set_body_height(self, height):
        self.body_height = height
        self.model = SpotMicroStickFigure(x=0, y=height, z=0)

    def feet_to_angles(self, foot_positions):
        coords = np.array([foot_positions['RR'], foot_positions['FR'],
                          foot_positions['FL'], foot_positions['RL']])
        self.model.set_absolute_foot_coordinates(coords)
        ik = self.model.get_leg_angles()
        result = {}
        for leg, idx in self.LEG_TO_IK_INDEX.items():
            q1, q2, q3 = ik[idx]
            if leg in self.LEFT_LEGS:
                result[leg] = [90-degrees(q1), 90+degrees(q2), 90+degrees(q3)]
            else:
                result[leg] = [90+degrees(q1), 90-degrees(q2), 90+degrees(q3)]
        return result

    def angles_to_servo_commands(self, angles):
        cmds = {}
        for leg, angs in angles.items():
            for i, ch in enumerate(self.LEG_CHANNELS[leg]):
                ang = angs[i]
                if ch in self.calibration:
                    c = self.calibration[ch]
                    delta = ang - 90
                    val = c['neutral_angle'] + c['direction'] * delta
                    val = max(0, min(180, val))
                else:
                    val = ang
                cmds[ch] = val
        return cmds

    def feet_to_servo_commands(self, fp):
        return self.angles_to_servo_commands(self.feet_to_angles(fp))

if __name__ == "__main__":
    ik = IKInterface(str(_CALIBRATION_FILE), body_height=0.10)
    feet = ik.get_neutral_foot_positions()
    print("Feet (mm):", {k: [round(v*1000) for v in pos] for k,pos in feet.items()})
    angles = ik.feet_to_angles(feet)
    print("Logical angles:", {k: [round(a) for a in v] for k,v in angles.items()})
    cmds = ik.feet_to_servo_commands(feet)
    print("Servo cmds:", {k: round(v) for k,v in sorted(cmds.items())})
