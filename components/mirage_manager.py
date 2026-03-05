"""
components/mirage_manager.py
"""

import os
import math
import json
import subprocess

import pygame

from core.display   import canvas, CENTER, ACCENT
from core.geometry  import (angle_diff, animated_color_offset,
                             ease_out, lerp_angle)
from components.hexmenu import HexMenu
from components.draw    import (draw_hex, draw_light_cone,
                                draw_icon, draw_icon_glow,
                                draw_tooltip)

FOV_YAW    = 45.0
FOV_PITCH  = 30.0
SMOOTH_T   = 0.12
DWELL_SECS = 0.6


class Action:
    __slots__ = ('type', 'payload')
    TYPES = ('app', 'setting', 'mirage', 'none')

    def __init__(self, atype='none', payload=None):
        if atype not in self.TYPES:
            raise ValueError(f'Unknown action type: {atype!r}')
        self.type    = atype
        self.payload = payload or {}

    def to_dict(self):
        return {'type': self.type, 'payload': self.payload}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get('type', 'none'), d.get('payload', {}))


def execute_
