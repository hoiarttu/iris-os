"""
apps/system_app.py
IRIS System App — Minimal widget + full Mirage GUI dashboard
"""

import pygame
import time
from apps.base_app import BaseApp


_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'


# -------------------------
# System reads
# -------------------------

def _read_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except:
        return 0.0


def _read_cpu_percent():
    try:
        with open('/proc/stat') as f:
            vals = list(map(int, f.readline().split()[1:]))

        idle = vals[3]
        total = sum(vals)

        if not hasattr(_read_cpu_percent, "_last"):
            _read_cpu_percent._last = (idle, total)
            return 0.0

        last_idle, last_total = _read_cpu_percent._last
        _read_cpu_percent._last = (idle, total)

        dt = total - last_total
        di = idle - last_idle

        if dt == 0:
            return 0.0

        return 100.0 * (1 - di / dt)

    except:
        return 0.0


def _read_mem_percent():
    try:
        info = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':')
                info[k.strip()] = int(v.split()[0])

        total = info.get("MemTotal", 1)
        avail = info.get("MemAvailable", 0)

        return 100.0 * (1 - avail / total)

    except:
        return 0.0


# -------------------------
# Interpretation
# -------------------------

def _state(label, v):
    if label == "CPU":
        if v < 30:
            return "steady", False
        if v < 70:
            return "loaded", False
        return "heavy load", True

    if label == "TEMP":
        if v < 60:
            return "cool", False
        if v < 80:
            return "warm", True
        return "hot", True

    if label == "MEM":
        if v < 60:
            return "stable", False
        if v < 80:
            return "tight", True
        return "critical", True

    if label == "FPS":
        if v > 50:
            return "fluid", False
        if v > 30:
            return "stable", False
        return "lagging", True

    return "unknown", False


# -------------------------
# App
# -------------------------

class SystemApp(BaseApp):
    name = "System"
    description = "Mirage system dashboard"

    _UPDATE_INTERVAL = 1.5

    def __init__(self):
        super().__init__()

        self.timer = 0.0

        # raw values
        self.cpu = 0.0
        self.temp = 0.0
        self.mem = 0.0
        self.fps = 60

        # subsystem flags
        self.imu_ok = True
        self.esp_ok = False
        self.wifi_ok = True

        # fonts
        self.title_font = pygame.font.Font(_MONO_BOLD, 26)
        self.body_font = pygame.font.Font(_MONO_BOLD, 18)
        self.small_font = pygame.font.Font(_MONO_BOLD, 14)

        self.icon = self.small_font.render("SYS", True, (255, 255, 255))

        # UI cache
        self.full_lines = []
        self.warnings = []

    # -------------------------
    # Update
    # -------------------------
    def update(self, dt):
        self.timer += dt

        if dt > 0:
            self.fps = int(1.0 / dt)

        if self.timer >= self._UPDATE_INTERVAL:
            self.timer = 0.0

            self.cpu = _read_cpu_percent()
            self.temp = _read_cpu_temp()
            self.mem = _read_mem_percent()

            self._build_full_ui()

    # -------------------------
    # Build UI data
    # -------------------------
    def _build_full_ui(self):
        self.full_lines = []
        self.warnings = []

        metrics = [
            ("CPU", self.cpu),
            ("TEMP", self.temp),
            ("MEM", self.mem),
            ("FPS", self.fps),
        ]

        for name, val in metrics:
            state, warn = _state(name, val)
            self.full_lines.append((name, val, state))

            if warn:
                self.warnings.append(f"{name}: {state}")

        if not self.imu_ok:
            self.warnings.append("IMU failure")
        if not self.esp_ok:
            self.warnings.append("ESP32 offline")
        if not self.wifi_ok:
            self.warnings.append("WiFi disconnected")

    # -------------------------
    # Icon
    # -------------------------
    def draw_icon(self, surface, center, radius):
        r = self.icon.get_rect(center=center)
        surface.blit(self.icon, r)

    # -------------------------
    # Widget (minimal)
    # -------------------------
    def draw_widget(self, surface, rect):
        cpu_txt = self.small_font.render(f"CPU {self.cpu:.0f}%", True, (255, 255, 255))
        temp_txt = self.small_font.render(f"T {self.temp:.0f}C", True, (255, 255, 255))
        mem_txt = self.small_font.render(f"M {self.mem:.0f}%", True, (255, 255, 255))

        surface.blit(cpu_txt, (rect.centerx - cpu_txt.get_width() // 2, rect.top + 10))
        surface.blit(temp_txt, (rect.centerx - temp_txt.get_width() // 2, rect.top + 30))
        surface.blit(mem_txt, (rect.centerx - mem_txt.get_width() // 2, rect.top + 50))

    # -------------------------
    # Fullscreen GUI
    # -------------------------
    def draw_fullscreen(self, surface):
        surface.fill((10, 10, 12))

        # TITLE
        title = self.title_font.render("SYSTEM MIRAGE", True, (255, 255, 255))
        surface.blit(title, (40, 30))

        # PANEL HELPER
        def panel(rect, title_text):
            pygame.draw.rect(surface, (20, 20, 25), rect, border_radius=12)
            pygame.draw.rect(surface, (60, 60, 70), rect, 2, border_radius=12)

            t = self.small_font.render(title_text, True, (180, 180, 220))
            surface.blit(t, (rect.x + 12, rect.y + 8))

        # METRICS PANEL
        metrics_rect = pygame.Rect(40, 80, 400, 220)
        panel(metrics_rect, "METRICS")

        def metric_card(x, y, label, value, state):
            w, h = 170, 60
            r = pygame.Rect(x, y, w, h)

            pygame.draw.rect(surface, (30, 30, 35), r, border_radius=10)

            color = (100, 200, 255)
            if "heavy" in state or "hot" in state or "critical" in state:
                color = (255, 100, 100)
            elif "warm" in state or "tight" in state:
                color = (255, 200, 100)

            pygame.draw.rect(surface, color, (r.x, r.y, 6, h), border_radius=6)

            lbl = self.small_font.render(label, True, (180, 180, 180))
            val = self.body_font.render(f"{value:.1f}", True, (255, 255, 255))
            st = self.small_font.render(state, True, color)

            surface.blit(lbl, (r.x + 12, r.y + 6))
            surface.blit(val, (r.x + 12, r.y + 22))
            surface.blit(st, (r.x + 12, r.y + 42))

        base_x = metrics_rect.x + 15
        base_y = metrics_rect.y + 30

        for i, (name, val, state) in enumerate(self.full_lines):
            x = base_x + (i % 2) * 190
            y = base_y + (i // 2) * 80
            metric_card(x, y, name, val, state)

        # STATUS PANEL
        status_rect = pygame.Rect(460, 80, 300, 220)
        panel(status_rect, "LINK STATUS")

        status_items = [
            ("IMU", self.imu_ok),
            ("ESP32", self.esp_ok),
            ("WiFi", self.wifi_ok),
        ]

        y = status_rect.y + 40
        for name, ok in status_items:
            col = (120, 255, 120) if ok else (255, 100, 100)
            txt = f"{name}: {'OK' if ok else 'OFF'}"

            surf = self.body_font.render(txt, True, col)
            surface.blit(surf, (status_rect.x + 20, y))
            y += 40

        # WARNINGS PANEL
        warn_rect = pygame.Rect(40, 320, 720, 140)
        panel(warn_rect, "WARNINGS")

        if not self.warnings:
            ok = self.body_font.render("No anomalies detected", True, (120, 255, 120))
            surface.blit(ok, (warn_rect.x + 20, warn_rect.y + 50))
        else:
            y = warn_rect.y + 40
            for w in self.warnings[:4]:
                surf = self.small_font.render("⚠ " + w, True, (255, 120, 120))
                surface.blit(surf, (warn_rect.x + 20, y))
                y += 22
