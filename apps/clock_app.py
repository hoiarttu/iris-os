"""
apps/clock_app.py — default centre widget
Shows time and date. Pre-rendered surfaces, no hot-path allocs.
"""

import time
import pygame
from apps.base_app import BaseApp

_MONO      = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
_MONO_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


class ClockApp(BaseApp):
    name        = 'Clock'
    description = ''

    def __init__(self):
        self._time_str  = ''
        self._date_str  = ''
        self._tick      = 999.0

        self._font_time = pygame.font.Font(_MONO_BOLD, 38)
        self._font_date = pygame.font.Font(_MONO,      16)
        self._color     = (80, 220, 255)
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

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        if self._time_surf:
            tr = self._time_surf.get_rect(centerx=rect.centerx,
                                           centery=rect.centery - 12)
            surface.blit(self._time_surf, tr)
        if self._date_surf:
            top = tr.bottom + 4 if self._time_surf else rect.top
            dr  = self._date_surf.get_rect(centerx=rect.centerx, top=top)
            surface.blit(self._date_surf, dr)
