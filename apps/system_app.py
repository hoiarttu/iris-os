"""
apps/system_app.py — CPU, temperature, memory
Pre-renders all text surfaces. No sleep() in hot path.
"""

import pygame
from apps.base_app import BaseApp

_MONO      = '/home/iris/mirage_gui/assets/fonts/Rajdhani-Bold.ttf'
_MONO_BOLD = '/home/iris/mirage_gui/assets/fonts/Rajdhani-Bold.ttf'


def _read_cpu_temp() -> float:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def _read_cpu_percent() -> float:
    try:
        with open('/proc/stat') as f:
            vals = list(map(int, f.readline().split()[1:]))
        idle  = vals[3]
        total = sum(vals)
        if not hasattr(_read_cpu_percent, '_last'):
            _read_cpu_percent._last = (idle, total)
            return 0.0
        last_idle, last_total = _read_cpu_percent._last
        _read_cpu_percent._last = (idle, total)
        diff_total = total - last_total
        diff_idle  = idle  - last_idle
        if diff_total == 0:
            return 0.0
        return round(100.0 * (1 - diff_idle / diff_total), 1)
    except Exception:
        return 0.0


def _read_mem_percent() -> float:
    try:
        info = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':')
                info[k.strip()] = int(v.split()[0])
        total = info.get('MemTotal', 1)
        avail = info.get('MemAvailable', 0)
        return round(100.0 * (1 - avail / total), 1)
    except Exception:
        return 0.0


class SystemApp(BaseApp):
    name        = 'System'
    description = 'CPU · Temp · Memory'
    _UPDATE_INTERVAL = 2.0

    def __init__(self):
        self._cpu   = 0.0
        self._temp  = 0.0
        self._mem   = 0.0
        self._timer = 0.0

        fn = pygame.font.Font(_MONO_BOLD, 20)
        fv = pygame.font.Font(_MONO_BOLD, 14)
        fi = pygame.font.Font(_MONO_BOLD, 16)

        self._name_surf = fn.render('SYSTEM', True, (255, 255, 255))
        self._icon_surf = fi.render('SY',     True, (255, 255, 255))
        self._stat_surfs = []
        self._fn_big = fn
        self._fv     = fv
        self._rebuild_stats()

    def _rebuild_stats(self):
        lines = [
            (f'CPU   {self._cpu:5.1f}%',  self._cpu),
            (f'TEMP  {self._temp:5.1f}C', self._temp),
            (f'MEM   {self._mem:5.1f}%',  self._mem),
        ]
        self._stat_surfs = []
        for text, val in lines:
            col = (255,100,100) if val>=80 else (255,230,100) if val>=60 else (255,255,255)
            self._stat_surfs.append(self._fv.render(text, True, col))

    def update(self, dt: float):
        self._timer += dt
        if self._timer >= self._UPDATE_INTERVAL:
            self._timer = 0.0
            self._temp  = _read_cpu_temp()
            self._cpu   = _read_cpu_percent()
            self._mem   = _read_mem_percent()
            self._rebuild_stats()

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)
        y = nr.bottom + 8
        for surf in self._stat_surfs:
            sr = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, sr)
            y += surf.get_height() + 3

    def draw_fullscreen(self, surface):
        surface.fill((0, 0, 0))
        y  = 40
        cx = surface.get_width() // 2
        nr = self._name_surf.get_rect(centerx=cx, top=y)
        surface.blit(self._name_surf, nr)
        y  = nr.bottom + 20
        for surf in self._stat_surfs:
            sr = surf.get_rect(centerx=cx, top=y)
            surface.blit(surf, sr)
            y += surf.get_height() + 8
