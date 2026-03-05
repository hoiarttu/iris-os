"""
components/mirage_manager.py

Scene graph for world-anchored Mirage windows.
────────────────────────────────────────────────
RULES
  • cos/sin for rotation computed ONCE per frame, shared across all mirages.
  • Polygon list built ONCE per mirage per frame.
  • Actions fire after DWELL_SECONDS of sustained gaze — not on first hover.
  • No Surface allocations.

Action types
  'app'     → subprocess.Popen(cmd)
  'setting' → os_ref.settings[key] = value
  'mirage'  → spawn a new Mirage at current gaze
  'none'    → placeholder
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
from components.draw    import (draw_hex, draw_center_glow, draw_light_cone,
                                draw_icon, draw_icon_glow, draw_tooltip,
                                draw_pointer)

# ── Tuning ────────────────────────────────────────────────────────────────────

FOV_YAW      = 45.0   # horizontal half-FOV (degrees)
FOV_PITCH    = 30.0   # vertical   half-FOV (degrees)
SMOOTH_T     = 0.12   # lerp weight for cosmetic yaw smoothing
DWELL_SECS   = 0.6    # seconds of gaze required before an action fires


# ── Action system ──────────────────────────────────────────────────────────────

class Action:
    __slots__ = ('type', 'payload')
    TYPES = ('app', 'setting', 'mirage', 'none')

    def __init__(self, atype: str = 'none', payload: dict = None):
        if atype not in self.TYPES:
            raise ValueError(f'Unknown action type: {atype!r}')
        self.type    = atype
        self.payload = payload or {}

    def to_dict(self):
        return {'type': self.type, 'payload': self.payload}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(d.get('type', 'none'), d.get('payload', {}))


def execute_action(action: Action, os_ref):
    if action.type == 'none':
        return
    if action.type == 'app':
        cmd = action.payload.get('cmd')
        if cmd:
            print(f'[Action] Launch: {cmd}')
            subprocess.Popen(cmd, shell=True)
    elif action.type == 'setting':
        key = action.payload.get('key')
        if key is not None:
            os_ref.settings[key] = action.payload.get('value')
            print(f'[Action] {key} = {action.payload.get("value")}')
    elif action.type == 'mirage':
        state  = os_ref.imu.state   # use cached state — no extra sensor read
        offset = action.payload.get('azimuth_offset', 90.0)
        os_ref.scene.add(
            (state.yaw + offset) % 360.0,
            state.pitch,
            action.payload.get('mtype', 'hexmenu'),
            action.payload.get('data', {}),
        )
        print('[Action] Mirage spawned')


# ── Mirage ────────────────────────────────────────────────────────────────────

class Mirage:
    __slots__ = ('azimuth', 'elevation', 'type', 'data', 'visible')
    TYPES = ('hexmenu',)

    def __init__(self, azimuth: float, elevation: float,
                 mtype: str, data: dict = None):
        if mtype not in self.TYPES:
            raise ValueError(f'Unknown Mirage type: {mtype!r}')
        self.azimuth   = float(azimuth)
        self.elevation = float(elevation)
        self.type      = mtype
        self.data      = data or {}
        self.visible   = False

    def to_dict(self):
        return {'azimuth': self.azimuth, 'elevation': self.elevation,
                'type': self.type, 'data': self.data}

    def __repr__(self):
        return f'Mirage({self.type} az={self.azimuth:.0f} el={self.elevation:.0f})'


# ── Scene manager ──────────────────────────────────────────────────────────────

class MirageManager:

    def __init__(self, path: str, os_ref=None):
        self.path        = path
        self.os_ref      = os_ref
        self.mirages: list[Mirage] = []
        self.hex_menu    = HexMenu(radius=42)

        # Cosmetic smoothed yaw (visual only — never used for FOV math)
        self._smooth_yaw = 0.0

        # Dwell tracking: (mirage_id, hex_idx) → elapsed seconds
        self._dwell: dict = {}
        self._dwell_key   = None   # currently gazed (id, idx) tuple

        self.load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                raw = json.load(f)
            self.mirages = []
            for entry in raw:
                try:
                    self.mirages.append(Mirage(**entry))
                except (ValueError, TypeError) as e:
                    print(f'[Scene] Skipped: {e}')
        else:
            self.mirages = [Mirage(0.0, 0.0, 'hexmenu', data={
                'labels': ['App', 'Settings', 'New', '–', '–', '–', '–'],
                'actions': [
                    {'type': 'app',     'payload': {'cmd': 'echo hello'}},
                    {'type': 'setting', 'payload': {'key': 'debug', 'value': True}},
                    {'type': 'mirage',  'payload': {'mtype': 'hexmenu'}},
                    {'type': 'none'}, {'type': 'none'},
                    {'type': 'none'}, {'type': 'none'},
                ],
            })]
        print(f'[Scene] {len(self.mirages)} mirage(s) loaded')

    def save(self):
        arr = [m.to_dict() for m in self.mirages]
        with open(self.path, 'w') as f:
            json.dump(arr, f, indent=2)
        print(f'[Scene] Saved {len(arr)} mirage(s)')

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add(self, azimuth, elevation, mtype='hexmenu', data=None) -> Mirage:
        m = Mirage(azimuth, elevation, mtype, data)
        self.mirages.append(m)
        return m

    def remove(self, idx: int):
        if 0 <= idx < len(self.mirages):
            print(f'[Scene] Removed {self.mirages.pop(idx)}')

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, yaw: float, pitch: float, pulse: float, dt: float):
        """
        dt: seconds since last frame (passed from the kernel — no time.time() here).
        cos_a / sin_a computed ONCE and reused for every visible mirage.
        """
        self._smooth_yaw = lerp_angle(self._smooth_yaw, yaw, SMOOTH_T)
        angle_rad = math.radians(-self._smooth_yaw)
        cos_a     = math.cos(angle_rad)
        sin_a     = math.sin(angle_rad)

        active_key = None

        for m in self.mirages:
            m.visible = (angle_diff(yaw,   m.azimuth)   <= FOV_YAW and
                         angle_diff(pitch, m.elevation)  <= FOV_PITCH)
            if not m.visible:
                continue
            if m.type == 'hexmenu':
                active_key = self._render_hexmenu(
                    m, yaw, pulse, cos_a, sin_a, dt)

        # Dwell accumulation — only for currently gazed hex
        if active_key:
            self._dwell[active_key] = self._dwell.get(active_key, 0.0) + dt
            if self._dwell[active_key] >= DWELL_SECS:
                mirage_id, hex_idx = active_key
                mirage = next((m for m in self.mirages
                                if id(m) == mirage_id), None)
                if mirage:
                    self._fire_action(mirage, hex_idx)
                del self._dwell[active_key]
        else:
            # Reset dwell for any key that's no longer active
            if self._dwell_key and self._dwell_key != active_key:
                self._dwell.pop(self._dwell_key, None)

        self._dwell_key = active_key

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render_hexmenu(self, mirage: Mirage, yaw: float, pulse: float,
                        cos_a: float, sin_a: float, dt: float):
        """
        Returns the active dwell key (id(mirage), hex_idx) or None.
        """
        cx, cy  = CENTER
        polys   = self.hex_menu.get_rotated_polygons(cos_a, sin_a, cx, cy)
        centers = self.hex_menu.get_center_points(cos_a, sin_a, cx, cy)
        sel     = self.hex_menu.get_highlight(polys, centers, (cx, cy))

        n      = self.hex_menu.N_HEXES
        labels = mirage.data.get('labels', [])

        # Dwell progress for current selection
        dwell_key     = (id(mirage), sel) if sel is not None else None
        dwell_elapsed = self._dwell.get(dwell_key, 0.0) if dwell_key else 0.0
        dwell_frac    = min(1.0, dwell_elapsed / DWELL_SECS)

        for i, (poly, cpt) in enumerate(zip(polys, centers)):
            base_angle = (90 + i * (360.0 / n)) % 360.0
            rel_yaw    = (yaw - mirage.azimuth + 360.0) % 360.0
            fade       = max(0.15, 1.0 - angle_diff(rel_yaw, base_angle) / FOV_YAW)
            col        = animated_color_offset(pulse, i)
            label      = labels[i] if i < len(labels) else '·'

            if i == sel:
                draw_light_cone(canvas, (cx, cy), cpt)
                glow_t = (math.sin(pulse * 2) + 1) * 0.5
                draw_hex(canvas, poly, col, alpha=int(ease_out(glow_t) * 100 + 60))
                draw_icon_glow(canvas, cpt, glow_t)
                draw_icon(canvas, cpt, col, label=label, scale=1.2)
                draw_tooltip(canvas, cpt, label)
                # Dwell progress ring
                if dwell_frac > 0.0:
                    self._draw_dwell_ring(canvas, cpt, dwell_frac)
            else:
                alpha = int(255 * fade)
                faded_col = (int(col[0]*fade), int(col[1]*fade), int(col[2]*fade))
                draw_hex(canvas, poly, faded_col, alpha=alpha)
                draw_icon(canvas, cpt, faded_col, label=label)

        return dwell_key

    @staticmethod
    def _draw_dwell_ring(surface, center, frac: float):
        """
        Partial arc showing dwell progress.
        Uses pygame.draw.arc — no surface allocation.
        """
        r    = 20
        rect = pygame.Rect(center[0] - r, center[1] - r, r * 2, r * 2)
        end_angle = math.pi * 2 * frac
        pygame.draw.arc(surface, ACCENT, rect,
                        math.pi / 2, math.pi / 2 + end_angle, 2)

    # ── Action dispatch ───────────────────────────────────────────────────────

    def _fire_action(self, mirage: Mirage, hex_idx: int):
        actions_raw = mirage.data.get('actions', [])
        if hex_idx < len(actions_raw):
            execute_action(Action.from_dict(actions_raw[hex_idx]), self.os_ref)
