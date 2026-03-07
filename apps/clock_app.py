"""
apps/clock_app.py

Default centre widget — clock and date.
─────────────────────────────────────────
Shown when no hex is being gazed at.
Overrides draw_widget() only — no icon needed since it lives in the centre.
"""

import time
import pygame
from apps.base_app import BaseApp


class ClockApp(BaseApp):
    name        = 'Clock'
    description = ''

    def __init__(self):
        self._time_str = ''
        self._date_str = ''
        self._tick      = 0.0

    def update(self, dt: float):
        self._tick += dt
        # Only update time string once per second
        if self._tick >= 1.0:
            self._tick = 0.0
            now = time.localtime()
            self._time_str = f'{now.tm_hour:02d}.{now.tm_min:02d}'
            self._date_str = f'{now.tm_mday}.{now.tm_mon}.{now.tm_year}'

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        """
        Large time in the upper half of the rect.
        Smaller date below it.
        """
        # Time
        time_font = pygame.font.SysFont('monospace', 42, bold=True)
        time_surf = time_font.render(self._time_str, True, (80, 220, 255))
        time_rect = time_surf.get_rect(centerx=rect.centerx,
                                        centery=rect.centery - 16)
        surface.blit(time_surf, time_rect)

        # Date
        date_font = pygame.font.SysFont('monospace', 18)
        date_surf = date_font.render(self._date_str, True, (80, 220, 255))
        date_rect = date_surf.get_rect(centerx=rect.centerx,
                                        top=time_rect.bottom + 4)
        surface.blit(date_surf, date_rect)
