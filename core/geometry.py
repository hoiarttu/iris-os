"""
core/geometry.py
"""

import math

_LUT_SIZE  = 256
_LUT_SCALE = 30.0

_COLOR_LUT = []
for _i in range(_LUT_SIZE):
    _t = _i / _LUT_SCALE
    _r = max(0, min(255, int(100 + 50  * math.sin(_t))))
    _g = max(0, min(255, int(180 + 60  * math.sin(_t + 2))))
    _b = max(0, min(255, int(255 + 30  * math.cos(_t + 1))))
    _COLOR_LUT.append((_r, _g, _b))
_COLOR_LUT = tuple(_COLOR_LUT)

def animated_color(t):
    return _COLOR_LUT[int(t * _LUT_SCALE) % _LUT_SIZE]

def animated_color_offset(t, offset):
    return _COLOR_LUT[(int(t * _LUT_SCALE) + offset * (_LUT_SIZE // 7)) % _LUT_SIZE]

def hex_points(center, radius):
    cx, cy = center
    return [
        (cx + radius * math.cos(math.radians(60 * i - 30)),
         cy + radius * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]

def distance(p1, p2):
    return math.h
