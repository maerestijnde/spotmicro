#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from microspot_app import set_servo
from gait import GaitController

gait = GaitController(set_servo)
gait.set_params(cycle_time=2.0, step_height=25, step_length=12, speed=0.5)

print('Single step test')
input('Enter...')

gait.single_step('forward')
print('Done!')
