"""
apps/system_app.py

System stats app — CPU, temperature, memory.
──────────────────────────────────────────────
Reads Pi system stats and displays them in the centre widget when focused.
Uses only stdlib — no psutil dependency to keep RAM low.
"""

import os
import time
import pygame
from apps.base_app import BaseApp


def _read_cpu_temp() -> float:
    """Read CPU temperature from the Pi thermal zone."""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def _read_cpu_percent() -> float:
    """
    Estimate CPU usage by reading /proc/stat twice with a short gap.
    Returns a 0-100 float.
    """
    try:
        def read_stat():
            with open('/proc/stat') as f:
                line = f.readline()
            vals = list(map(int, line.split()[1:]))
            idle    = vals[3]
            total   = sum(vals)
            return idle, total

        idle1, total1 = read_stat()
        time.sleep(0.1)
        idle2, total2 = read_stat()
        diff_idle  = idle2  - idle1
        diff_total = total2 - total1
        if diff_total == 0:
            return 0.0
        return round(100.0 * (1 - diff_idle / diff_total), 1)
    except Exception:
        return 0.0


def _read_mem_percent() -> float:
    """Read memory usage from /proc/meminfo."""
    try:
        info = {}
        with open('/proc/meminfo') as f:
            for line in f:
                key, val = line.split(':')
                info[key.strip()] = int(val.split()[0])
        total = info.get('MemTotal', 1)
        avail = info.get('MemAvailable', 0)
        return round(100.0 * (1 - avail / total), 1)
    except Exception:
        return 0.0


class SystemApp(BaseApp):
    name        = 'System'
    description = 'CPU · Temp · Memory'

    _UPDATE_INTERVAL = 2.0   # seconds between stat reads

    def __init__(self):
        self._cpu   = 0.0
        self._temp  = 0.0
        self._mem   = 0.0
        self._timer = 0.0

    def update(self, dt: float):
        self._timer += dt
        if self._timer >= self._UPDATE_INTERVAL:
            self._timer = 0.0
            self._temp  = _read_cpu_temp()
            self._cpu   = _read_cpu_percent()
            self._mem   = _read_mem_percent()

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        name_font  = pygame.font.SysFont('monospace', 22, bold=True)
        value_font = pygame.font.SysFont('monospace', 14)

        # Header
        name_surf = name_font.render('SYSTEM', True, (80, 220, 255))
        name_rect = name_surf.get_rect(centerx=rect.centerx,
                                        top=rect.top + 10)
        surface.blit(name_surf, name_rect)

        # Stats
        stats = [
            f'CPU   {self._cpu:5.1f} %',
            f'TEMP  {self._temp:5.1f} C',
            f'MEM   {self._mem:5.1f} %',
        ]
        y = name_rect.bottom + 10
        for line in stats:
            # Colour code: green < 60, yellow < 80, red >= 80
            val = float(line.split()[-2])
            if val >= 80:
                col = (255, 80, 80)
            elif val >= 60:
                col = (255, 220, 80)
            else:
                col = (80, 255, 160)
            surf = value_font.render(line, True, col)
            rect2 = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, rect2)
            y += surf.get_height() + 4
