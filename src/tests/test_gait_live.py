#!/usr/bin/env python3
import sys, time
sys.path.insert(0, '.')
from microspot_app import set_servo
from gait import GaitController

cmds = []
def log_servo(ch, angle, flag):
    if ch in [7,8,10,11]:  # alleen achterpoten
        cmds.append((time.time(), ch, angle))
    set_servo(ch, angle, flag)

gait = GaitController(log_servo)
gait.set_params(cycle_time=2.0)

print('1 cycle lopen, kijk naar RL vs RR')
input('Enter...')

cmds = []
gait.start('forward')
time.sleep(2.1)
gait.stop()

print('\n=== COMMANDO LOG ===')
t0 = cmds[0][0] if cmds else 0
for t, ch, ang in cmds[-20:]:
    name = {7:'RL_knee',8:'RL_ankle',10:'RR_knee',11:'RR_ankle'}[ch]
    print(f'{t-t0:.2f}s {name:10} -> {ang}')
