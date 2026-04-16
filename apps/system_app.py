"""
apps/system_control_app.py
Unified system diagnostics + runtime status (IRIS core dashboard)
"""

import pygame
import time
from apps.base_app import BaseApp


_MONO      = 'assets/fonts/Rajdhani-Bold.ttf'
_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'


# -------------------------
# Hardware metrics
# -------------------------

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

        if not hasattr(_read_cpu_percent, "_last"):
            _read_cpu_percent._last = (idle, total)
            return 0.0

        last_idle, last_total = _read_cpu_percent._last
        _read_cpu_percent._last = (idle, total)

        diff_total = total - last_total
        diff_idle  = idle - last_idle

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


class SystemControlApp(BaseApp):
    """
    Unified IRIS diagnostics + runtime status dashboard.
    Replaces both SystemApp and ControlCenterApp.
    """

    name        = "System"
    description = "Diagnostics + runtime status"

    _UPDATE_INTERVAL = 1.5

    def __init__(self):
        super().__init__()

        self._timer = 0.0

        # -------------------------
        # System metrics
        # -------------------------
        self.cpu  = 0.0
        self.temp = 0.0
        self.mem  = 0.0

        # -------------------------
        # Runtime metrics (IRIS layer)
        # -------------------------
        self.fps    = 0
        self.imu_ok = True
        self.esp_ok = False
        self.wifi_ok = True

        self.last_t = time.time()

        # -------------------------
        # Fonts
        # -------------------------
        self.font_title = pygame.font.Font(_MONO_BOLD, 28)
        self.font_small = pygame.font.Font(_MONO_BOLD, 18)
        self.font_icon  = pygame.font.Font(_MONO_BOLD, 16)

        # -------------------------
        # Pre-rendered surfaces
        # -------------------------
        self._name_surf = self.font_title.render("SYSTEM CONTROL", True, (255, 255, 255))
        self._icon_surf = self.font_icon.render("SYS", True, (255, 255, 255))

        self._stat_surfs = []
        self._rebuild()

    # -------------------------
    # Metrics update
    # -------------------------
    def update(self, dt: float):
        self._timer += dt

        # FPS estimate (engine-side dt)
        now = time.time()
        if dt > 0:
            self.fps = int(1.0 / dt)

        if self._timer >= self._UPDATE_INTERVAL:
            self._timer = 0.0

            # hardware
            self.cpu  = _read_cpu_percent()
            self.temp = _read_cpu_temp()
            self.mem  = _read_mem_percent()

            self._rebuild()

    # -------------------------
    # Pre-render text block
    # -------------------------
    def _rebuild(self):
        def color(val):
            return (
                (255, 90, 90) if val >= 80 else
                (255, 220, 90) if val >= 60 else
                (255, 255, 255)
            )

        lines = [
            (f"CPU   {self.cpu:5.1f}%",  self.cpu),
            (f"TEMP  {self.temp:5.1f}C", self.temp),
            (f"MEM   {self.mem:5.1f}%",  self.mem),
            (f"FPS   {self.fps}",       self.fps),

            (f"IMU   {'OK' if self.imu_ok else 'FAIL'}", 0),
            (f"ESP32 {'OK' if self.esp_ok else 'OFF'}", 0),
            (f"WiFi  {'OK' if self.wifi_ok else 'OFF'}", 0),
        ]

        self._stat_surfs = []
        for text, val in lines:
            col = color(val) if isinstance(val, (int, float)) else (255, 255, 255)
            self._stat_surfs.append(self.font_small.render(text, True, col))

    # -------------------------
    # Menu icon
    # -------------------------
    def draw_icon(self, surface, center, radius):
        rect = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, rect)

    # -------------------------
    # Hex widget preview
    # -------------------------
    def draw_widget(self, surface, rect):
        title_rect = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, title_rect)

        y = title_rect.bottom + 10

        for surf in self._stat_surfs:
            r = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, r)
            y += surf.get_height() + 3

    # -------------------------
    # Fullscreen mode
    # -------------------------
    def draw_fullscreen(self, surface):
        surface.fill((0, 0, 0))

        cx = surface.get_width() // 2

        title = self._name_surf.get_rect(centerx=cx, top=40)
        surface.blit(self._name_surf, title)

        y = title.bottom + 20

        for surf in self._stat_surfs:
            r = surf.get_rect(centerx=cx, top=y)
            surface.blit(surf, r)
            y += surf.get_height() + 8
