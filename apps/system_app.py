"""
apps/system_app.py
IRIS System App — Integrated telemetry (ESP + WiFi + BT)
"""

import pygame
import math
import subprocess
from apps.base_app import BaseApp


_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'


# -------------------------
# IMU (placeholder)
# -------------------------
def _get_imu_angles():
    return 0.0, 0.0


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

        return round(100.0 * (1 - di / dt), 1)

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

        return round(100.0 * (1 - avail / total), 1)

    except:
        return 0.0


# -------------------------
# Connectivity
# -------------------------
def _read_wifi():
    try:
        ssid = subprocess.check_output(["iwgetid", "-r"], text=True).strip()
        link = subprocess.check_output(["iwconfig"], text=True)

        strength = 0
        for line in link.splitlines():
            if "Signal level" in line:
                part = line.split("Signal level=")[1]
                strength = int(part.split(" ")[0])
                break

        return ssid, strength
    except:
        return None, 0


def _read_bt():
    try:
        out = subprocess.check_output(["hciconfig"], text=True)
        return "UP RUNNING" in out
    except:
        return False


# -------------------------
# Interpretation
# -------------------------
def _state(label, v):

    if label == "CPU":
        if v < 30: return "steady", False
        if v < 70: return "loaded", False
        return "heavy", True

    if label == "TEMP":
        if v < 60: return "cool", False
        if v < 80: return "warm", True
        return "hot", True

    if label == "MEM":
        if v < 60: return "stable", False
        if v < 80: return "tight", True
        return "critical", True

    if label == "FPS":
        if v > 35: return "good", False
        if v > 20: return "ok", False
        return "low", True

    if label == "WIFI":
        if v > -60: return "strong", False
        if v > -75: return "ok", False
        return "weak", True

    if label == "BT":
        return ("on", False) if v > 0 else ("off", True)

    return "unknown", False


# -------------------------
# App
# -------------------------
class SystemApp(BaseApp):

    name = "System"
    description = "System status"
    pin_mode = 'free'   # always centred, telemetry should always be visible

    _UPDATE_INTERVAL = 1.5

    def __init__(self, input_handler=None):
        super().__init__()

        self.input = input_handler

        self.timer = 0.0

        self.cpu = 0.0
        self.temp = 0.0
        self.mem = 0.0
        self.fps = 60

        self.wifi_ssid = None
        self.wifi_strength = 0
        self.bt_ok = False
        self.esp_ok = False

        # Fonts
        self.title_font = pygame.font.Font(_MONO_BOLD, 32)
        self.body_font  = pygame.font.Font(_MONO_BOLD, 20)
        self.small_font = pygame.font.Font(_MONO_BOLD, 16)

        # Mirage surfaces
        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)

        self._name_surf = fn.render("SYSTEM", True, (255,255,255))
        self._icon_surf = fi.render("SY", True, (255,255,255))

        # IMU offset
        self.offset_x = 0
        self.offset_y = 0
        self.smooth = 0.1

        self.full_lines = []
        self.warnings = []

    # -------------------------
    def update(self, dt):

        self.timer += dt

        if dt > 0:
            self.fps = int(1.0 / dt)

        yaw, pitch = _get_imu_angles()

        tx = yaw * 200
        ty = pitch * 200

        self.offset_x += (tx - self.offset_x) * self.smooth
        self.offset_y += (ty - self.offset_y) * self.smooth

        if self.timer >= self._UPDATE_INTERVAL:
            self.timer = 0.0

            self.cpu  = _read_cpu_percent()
            self.temp = _read_cpu_temp()
            self.mem  = _read_mem_percent()

            self.wifi_ssid, self.wifi_strength = _read_wifi()
            self.bt_ok = _read_bt()

            if self.input:
                self.esp_ok = self.input._connected
            else:
                self.esp_ok = False

            self._build_ui()

    # -------------------------
    def _build_ui(self):

        self.full_lines = []
        self.warnings = []

        metrics = [
            ("CPU", self.cpu),
            ("TEMP", self.temp),
            ("MEM", self.mem),
            ("FPS", self.fps),
            ("WIFI", self.wifi_strength),
            ("BT", 100 if self.bt_ok else 0),
        ]

        for name, val in metrics:
            state, warn = _state(name, val)
            self.full_lines.append((name, val, state))

            if warn:
                self.warnings.append(f"{name} {state}")

        if not self.esp_ok:
            self.warnings.append("esp offline")

        if not self.wifi_ssid:
            self.warnings.append("wifi disconnected")

        if not self.bt_ok:
            self.warnings.append("bluetooth off")

    # -------------------------
    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    # -------------------------
    def draw_widget(self, surface, rect):

        nr = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)

        y = nr.bottom + 6

        lines = [
            f"CPU  {self.cpu:.0f}%",
            f"TMP  {self.temp:.0f}C",
            f"MEM  {self.mem:.0f}%"
        ]

        if self.wifi_ssid:
            lines.append(f"WIFI {self.wifi_strength}")

        if self.fps < 25:
            lines.append(f"FPS  {self.fps}")

        for line in lines[:4]:
            surf = self.small_font.render(line, True, (220,220,220))
            sr = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, sr)
            y += surf.get_height() + 2

    # -------------------------
    def draw_fullscreen(self, surface):

        W, H = surface.get_size()

        world = pygame.Surface((W, H), pygame.SRCALPHA)
        world.fill((0, 0, 0))

        margin = 16
        y = 10

        title = self.title_font.render("SYSTEM", True, (255,255,255))
        world.blit(title, (W//2 - title.get_width()//2, y))
        y += title.get_height() + 10

        def panel(x, y, w, h, label):
            r = pygame.Rect(x, y, w, h)
            pygame.draw.rect(world, (20,20,25), r, border_radius=10)
            pygame.draw.rect(world, (60,60,70), r, 2, border_radius=10)

            t = self.small_font.render(label, True, (180,180,220))
            world.blit(t, (x+10, y+5))
            return r

        panel_w = W - margin*2

        rows = math.ceil(len(self.full_lines)/2)
        card_h = 60
        m_h = 30 + rows*(card_h+8)

        mrect = panel(margin, y, panel_w, m_h, "metrics")

        card_w = (panel_w - 30)//2

        for i, (name, val, state) in enumerate(self.full_lines):

            cx = mrect.x + 10 + (i % 2)*(card_w+10)
            cy = mrect.y + 25 + (i // 2)*(card_h+8)

            r = pygame.Rect(cx, cy, card_w, card_h)
            pygame.draw.rect(world, (30,30,35), r, border_radius=8)

            col = (100,200,255)
            if "hot" in state or "critical" in state or "low" in state:
                col = (255,100,100)

            pygame.draw.rect(world, col, (r.x, r.y, 4, card_h))

            world.blit(self.small_font.render(name, True, (180,180,180)), (r.x+8, r.y+5))
            world.blit(self.body_font.render(f"{val:.0f}", True, (255,255,255)), (r.x+8, r.y+25))

        y = mrect.bottom + 10

        max_warn = max(1, (H - y - 20)//20)
        warn_list = self.warnings[:max_warn]

        w_h = 30 + len(warn_list)*20
        wrect = panel(margin, y, panel_w, w_h, "warnings")

        wy = wrect.y + 25
        for w in warn_list:
            txt = self.small_font.render(w, True, (255,120,120))
            world.blit(txt, (wrect.x+10, wy))
            wy += 20

        surface.blit(world, (int(self.offset_x), int(self.offset_y)))
