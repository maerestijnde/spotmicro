#!/usr/bin/env python3
import sys, time
sys.path.insert(0, '.')
from microspot_app import set_servo

print('=== ALLE POTEN STAND TEST ===')
print('Kijk welke poot zwakker lijkt')
input('Enter...')

legs = {
    'FL': (0, 1, 2),
    'FR': (3, 4, 5),
    'RL': (6, 7, 8),
    'RR': (9, 10, 11)
}

print('Alle poten naar stand...')
for name, (hip, knee, ankle) in legs.items():
    set_servo(hip, 90, True)
    set_servo(knee, 45, True)
    set_servo(ankle, 135, True)

time.sleep(3)
print('Houden alle poten het gewicht?')
input('Enter om te stoppen...')
print('Done!')
