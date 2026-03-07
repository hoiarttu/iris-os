"""
components/mirage_manager.py

Scene graph — now wired to the App system.
───────────────────────────────────────────
Changes from previous version:
  • Each hex slot holds a BaseApp instance instead of a raw action dict
  • Centre widget renders focused app or ClockApp by default
  • on_focus / on_blur called on app instances
  • on_select called after dwell completes
  • cos/sin computed once per frame
  • No Surface allocations in hot path
"""

import os
import math
import json

import pygame

from core.display   import canvas, CENTER, WIDTH, HEIGHT, ACCENT, DIM, BLACK
from core.geometry  import (angle_diff, animated_color_offset,
                             ease_out, lerp_angle)
from components.hexmenu import HexMenu
from components.draw    import (draw_hex, draw_light_cone,
                                draw_icon_glow, draw_tooltip,
                                draw_pointer, draw_center_glow)
from apps.base_app      import BaseApp
from apps.clock_app     import ClockApp
from apps.placeholder_app import PlaceholderApp
from apps.system_app    import SystemApp

# ── Tuning ────────────────────────────────────────────────────────────────────

FOV_YAW    = 45.0
FOV_PITCH  = 30.0
SMOOTH_T   = 0.12
DWELL_SECS = 0.6

# ── Default app layout ────────────────────────────────────────────────────────

def default_apps() -> list:
    return [
        PlaceholderApp('Menu'),
        PlaceholderApp('Navigation'),
        SystemApp(),
        PlaceholderApp('Media'),
        PlaceholderApp('Settings'),
        PlaceholderApp('Comms'),
        PlaceholderApp('Vision'),
    ]


# ── Hex border drawing ────────────────────────────────────────────────────────

def draw_hex_neon(surface, points, focused: bool, pulse: float):
    pygame.draw.polygon(surface, (8, 8, 18), points)
    t   = pulse * 0.5
    r   = int(120 + 60 * math.sin(t))
    g   = int(40  + 20 * math.sin(t + 1))
    b   = int(220 + 35 * math.cos(t + 0.5))
    col = (min(255,r), min(255,g), min(255,b))
    width = 3 if focused else 2
    pygame.draw.polygon(surface, col, points, width + 2)
    pygame.draw.polygon(surface, (min(255, col[0]+60),
                                   min(255, col[1]+40),
                                   min(255, col[2]+40)), points, width)


# ── Centre widget area ────────────────────────────────────────────────────────

def _centre_rect() -> pygame.Rect:
    w, h = 160, 100
    return pygame.Rect(CENTER[0] - w//2, CENTER[1] - 180, w, h)

# ── Mirage ────────────────────────────────────────────────────────────────────

class Mirage:
    __slots__ = ('azimuth', 'elevation', 'type', 'apps', 'visible')
    TYPES = ('hexmenu',)

    def __init__(self, azimuth: float, elevation: float,
                 mtype: str, apps: list = None):
        if mtype not in self.TYPES:
            raise ValueError(f'Unknown Mirage type: {mtype!r}')
        self.azimuth   = float(azimuth)
        self.elevation = float(elevation)
        self.type      = mtype
        self.apps      = apps or default_apps()
        self.visible   = False

    def to_dict(self):
        return {'azimuth': self.azimuth, 'elevation': self.elevation,
                'type': self.type}

    def __repr__(self):
        return f'Mirage({self.type} az={self.azimuth:.0f} el={self.elevation:.0f})'


# ── Scene manager ─────────────────────────────────────────────────────────────

class MirageManager:

    def __init__(self, path: str, os_ref=None):
        self.path        = path
        self.os_ref      = os_ref
        self.mirages     = []
        self.hex_menu    = HexMenu(radius=70)
        self._smooth_yaw = 0.0
        self._dwell      = {}
        self._dwell_key  = None
        self._clock_app  = ClockApp()
        self._focused_app = self._clock_app
        self._last_focused_app = None
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                raw = json.load(f)
            self.mirages = []
            for entry in raw:
                try:
                    self.mirages.append(Mirage(
                        entry['azimuth'], entry['elevation'], entry['type']))
                except (ValueError, TypeError, KeyError) as e:
                    print(f'[Scene] Skipped: {e}')
        else:
            self.mirages = [Mirage(0.0, 0.0, 'hexmenu')]
        print(f'[Scene] {len(self.mirages)} mirage(s) loaded')

    def save(self):
        arr = [m.to_dict() for m in self.mirages]
        with open(self.path, 'w') as f:
            json.dump(arr, f, indent=2)
        print(f'[Scene] Saved {len(arr)} mirage(s)')

    def add(self, azimuth, elevation, mtype='hexmenu'):
        m = Mirage(azimuth, elevation, mtype)
        self.mirages.append(m)
        return m

    def remove(self, idx: int):
        if 0 <= idx < len(self.mirages):
            print(f'[Scene] Removed {self.mirages.pop(idx)}')

    def update(self, yaw: float, pitch: float, pulse: float, dt: float):
        self._clock_app.update(dt)
        self._smooth_yaw = lerp_angle(self._smooth_yaw, yaw, SMOOTH_T)
        cos_a = 1.0
        sin_a = 0.0
        active_key = None
        active_app = None

        for m in self.mirages:
            m.visible = (angle_diff(yaw,   m.azimuth)  <= FOV_YAW and
                         angle_diff(pitch, m.elevation) <= FOV_PITCH)
            if not m.visible:
                continue

            for app in m.apps:
                app.update(dt)

            if m.type == 'hexmenu':
                key, app, widget_pos = self._render_hexmenu(
                    m, yaw, pulse, cos_a, sin_a, dt)
                if key is not None:
                    active_key = key
                    active_app = app

        if active_app != self._last_focused_app:
            if self._last_focused_app and self._last_focused_app != self._clock_app:
                self._last_focused_app.on_blur()
            if active_app:
                active_app.on_focus()
            self._last_focused_app = active_app

        self._focused_app = active_app if active_app else self._clock_app
        self._draw_centre_widget(*widget_pos)

        if active_key:
            self._dwell[active_key] = self._dwell.get(active_key, 0.0) + dt
            if self._dwell[active_key] >= DWELL_SECS:
                mirage_id, hex_idx = active_key
                mirage = next((m for m in self.mirages
                               if id(m) == mirage_id), None)
                if mirage and hex_idx < len(mirage.apps):
                    mirage.apps[hex_idx].on_select()
                del self._dwell[active_key]
        else:
            if self._dwell_key and self._dwell_key != active_key:
                self._dwell.pop(self._dwell_key, None)
        self._dwell_key = active_key

    def _draw_centre_widget(self, cx, cy):
        w, h = 160, 100
        rect = pygame.Rect(cx - w//2, cy - h//2, w, h)
        self._focused_app.draw_widget(canvas, rect)

    def _render_hexmenu(self, mirage, yaw, pulse, cos_a, sin_a, dt):
        # Translate menu position based on yaw offset from mirage azimuth
        yaw_diff  = angle_diff(yaw, mirage.azimuth)
        yaw_sign  = 1 if ((yaw - mirage.azimuth + 360) % 360) < 180 else -1
        cx = int(CENTER[0] - yaw_sign * yaw_diff * 32)
        cy = CENTER[1]
        polys   = self.hex_menu.get_rotated_polygons(cos_a, sin_a, cx, cy)
        centers = self.hex_menu.get_center_points(cos_a, sin_a, cx, cy)
        sel = self.hex_menu.get_highlight(polys[1:], centers[1:], CENTER)
        if sel is not None:
            sel += 1

        apps      = mirage.apps
        dwell_key = (id(mirage), sel) if sel is not None else None
        dwell_elapsed = self._dwell.get(dwell_key, 0.0) if dwell_key else 0.0
        dwell_frac    = min(1.0, dwell_elapsed / DWELL_SECS)
        active_app    = apps[sel] if sel is not None and sel < len(apps) else None

        for i, (poly, cpt) in enumerate(zip(polys, centers)):
            if i == 0:
                continue
            focused = (i == sel)
            draw_hex_neon(canvas, poly, focused, pulse)
            if focused:
                draw_light_cone(canvas, CENTER, cpt)
                glow_t = (math.sin(pulse * 2) + 1) * 0.5
                draw_icon_glow(canvas, cpt, glow_t)
            if i < len(apps):
                apps[i].draw_icon(canvas, cpt, self.hex_menu.radius * 0.5)
            if focused and dwell_frac > 0.0:
                self._draw_dwell_ring(canvas, cpt, dwell_frac)

        return dwell_key, active_app, centers[0]

    @staticmethod
    def _draw_dwell_ring(surface, center, frac: float):
        r    = 22
        rect = pygame.Rect(center[0] - r, center[1] - r, r * 2, r * 2)
        end_angle = math.pi * 2 * frac
        pygame.draw.arc(surface, ACCENT, rect,
                        math.pi / 2, math.pi / 2 + end_angle, 2)
