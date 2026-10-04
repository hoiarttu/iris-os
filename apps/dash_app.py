"""
apps/dash_app.py — Dash
─────────────────────────────────────────────────────────────────────────────
Launched from the centre hex. Starting point: the same clock readout the
centre widget has always shown, now as a real, selectable, fullscreen app.
Infobar / minimap / Scan land here in later passes.
"""

import time
import pygame
from apps.base_app import BaseApp
from core.display   import WIDTH, HEIGHT, BLACK

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'


class DashApp(BaseApp):
    name        = 'Dash'
    description = 'Glanceable HUD'
    pin_mode    = 'free'   # always centred, ignores head yaw/pitch offset
    show_cursor = False    # no reticle yet — hide cursor while Dash is open

    def __init__(self):
        super().__init__()
        self._time_str  = ''
        self._date_str  = ''
        self._tick      = 999.0

        self._font_time = pygame.font.Font(_MONO_BOLD, 64)
        self._font_date = pygame.font.Font(_MONO_BOLD, 24)
        self._color     = (255, 255, 255)
        self._time_surf = None
        self._date_surf = None

    def update(self, dt: float):
        self._tick += dt
        if self._tick >= 1.0:
            self._tick = 0.0
            now = time.localtime()
            t = f'{now.tm_hour:02d}.{now.tm_min:02d}'
            d = f'{now.tm_mday}.{now.tm_mon}.{now.tm_year}'
            if t != self._time_str:
                self._time_str  = t
                self._time_surf = self._font_time.render(t, True, self._color)
            if d != self._date_str:
                self._date_str  = d
                self._date_surf = self._font_date.render(d, True, self._color)

    def draw_fullscreen(self, surface: pygame.Surface):
        surface.fill(BLACK)
        if self._time_surf:
            tr = self._time_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 16))
            surface.blit(self._time_surf, tr)
        if self._date_surf:
            top = tr.bottom + 6 if self._time_surf else HEIGHT // 2
            dr  = self._date_surf.get_rect(centerx=WIDTH // 2, top=top)
            surface.blit(self._date_surf, dr)
