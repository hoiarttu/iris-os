"""
apps/system_app.py — IRIS System
─────────────────────────────────────────────────────────────────────────────
Telemetry display. Reads system stats async — never blocks render loop.
pin_mode = 'pinned' — lives in world space like a real mirage.

Stats updated every 2s via lightweight /proc reads.
No subprocess calls in hot path.
"""

import os, time, threading
import pygame
from apps.base_app import BaseApp
from core.display import WIDTH, HEIGHT, BLACK, WHITE, ACCENT, SECONDARY

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

# ── Async stat reader ─────────────────────────────────────────────────────────

class StatReader(threading.Thread):
    """Reads system stats in background. Main thread reads cached values."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cpu    = 0.0
        self.temp   = 0.0
        self.mem    = 0.0
        self.wifi   = 'none'
        self.bt     = False
        self._lock  = threading.Lock()
        self._stopping = False
        self._prev_idle  = 0
        self._prev_total = 0

    def run(self):
        while not self._stopping:
            cpu   = self._read_cpu()
            temp  = self._read_temp()
            mem   = self._read_mem()
            wifi  = self._read_wifi()
            bt    = self._read_bt()
            with self._lock:
                self.cpu  = cpu
                self.temp = temp
                self.mem  = mem
                self.wifi = wifi
                self.bt   = bt
            time.sleep(2.0)

    def get(self):
        with self._lock:
            return self.cpu, self.temp, self.mem, self.wifi, self.bt

    def stop(self):
        self._stopping = True

    def _read_cpu(self):
        try:
            with open('/proc/stat') as f:
                vals = list(map(int, f.readline().split()[1:]))
            idle  = vals[3]
            total = sum(vals)
            di    = idle  - self._prev_idle
            dt    = total - self._prev_total
            self._prev_idle  = idle
            self._prev_total = total
            return round(100.0 * (1 - di / dt), 1) if dt else 0.0
        except:
            return 0.0

    def _read_temp(self):
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                return int(f.read().strip()) / 1000.0
        except:
            return 0.0

    def _read_mem(self):
        try:
            info = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    k, v = line.split(':')
                    info[k.strip()] = int(v.split()[0])
            total = info.get('MemTotal', 1)
            avail = info.get('MemAvailable', 0)
            return round(100.0 * (1 - avail / total), 1)
        except:
            return 0.0

    def _read_wifi(self):
        try:
            with open('/proc/net/wireless') as f:
                lines = f.readlines()
            if len(lines) < 3:
                return 'none'
            parts = lines[2].split()
            iface = parts[0].rstrip(':')
            level = int(float(parts[3].rstrip('.')))
            return f'{iface} {level}dB'
        except:
            return 'none'

    def _read_bt(self):
        try:
            return os.path.exists('/sys/class/bluetooth') and \
                   bool(os.listdir('/sys/class/bluetooth'))
        except:
            return False


# ── App ───────────────────────────────────────────────────────────────────────

class SystemApp(BaseApp):
    name          = 'System'
    description   = 'System status'
    pin_mode      = 'pinned'
    show_cursor   = True
    cap_hold_secs = 0.0

    # Colors
    COL_WARN = (255, 220,  50)   # yellow
    COL_CRIT = (255,  80,  80)   # red
    COL_DIM  = (60,   60,  70)

    def __init__(self):
        super().__init__()

        self._reader = StatReader()
        self._reader.start()

        self._fps    = 0
        self._frames = 0
        self._fps_t  = time.time()

        # Pre-load fonts
        self._f_big  = pygame.font.Font(_MONO_BOLD, 36)
        self._f_med  = pygame.font.Font(_MONO_BOLD, 22)
        self._f_sm   = pygame.font.Font(_MONO_BOLD, 16)
        self._f_tiny = pygame.font.Font(_MONO_BOLD, 18)

        # Icon/widget
        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)
        self._name_surf = fn.render('SYSTEM', True, WHITE)
        self._icon_surf = fi.render('SY',     True, WHITE)

        # Cached stat values
        self._cpu  = 0.0
        self._temp = 0.0
        self._mem  = 0.0
        self._wifi = 'none'
        self._bt   = False

    def close(self):
        self._reader.stop()
        super().close()

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt):
        import core.display as _cd
        self._fps = _cd.FPS
        if not self._reader.is_alive():
            print('[System] StatReader died — restarting')
            self._reader = StatReader()
            self._reader.start()
    # ── Helpers ───────────────────────────────────────────────────────────────

    def _val_color(self, val, warn, crit):
        if val >= crit:  return self.COL_CRIT
        if val >= warn:  return self.COL_WARN
        return ACCENT

    def _bar(self, surface, x, y, w, h, frac, color):
        pygame.draw.rect(surface, self.COL_DIM,  (x, y, w, h), border_radius=3)
        filled = max(2, int(w * frac))
        pygame.draw.rect(surface, color, (x, y, filled, h), border_radius=3)

    def _row(self, surface, x, y, label, val_str, frac, color):
        lbl  = self._f_sm.render(label,   True, (160, 160, 180))
        val  = self._f_sm.render(val_str, True, color)
        surface.blit(lbl, (x, y))
        surface.blit(val, (x + 120, y))
        self._bar(surface, x, y + 18, 200, 6, frac, color)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_fullscreen(self, surface):
        surface.fill(BLACK)
        W, H = surface.get_size()
        cx   = W // 2
        y    = 20

        # Title
        t = self._f_big.render('SYSTEM', True, ACCENT)
        surface.blit(t, (cx - t.get_width() // 2, y))
        y += t.get_height() + 16

        # Divider
        pygame.draw.line(surface, self.COL_DIM, (40, y), (W - 40, y), 1)
        y += 12

        # Stats rows
        margin = 60
        self._row(surface, margin, y,
                  'CPU', f'{self._cpu:.0f}%',
                  self._cpu / 100,
                  self._val_color(self._cpu, 60, 85))
        y += 36

        self._row(surface, margin, y,
                  'TEMP', f'{self._temp:.0f}°C',
                  min(1.0, self._temp / 85.0),
                  self._val_color(self._temp, 65, 80))
        y += 36

        self._row(surface, margin, y,
                  'MEM', f'{self._mem:.0f}%',
                  self._mem / 100,
                  self._val_color(self._mem, 70, 90))
        y += 36

        self._row(surface, margin, y,
                  'FPS', f'{self._fps}',
                  min(1.0, self._fps / 30),
                  self._val_color(30 - self._fps, 10, 20))
        y += 48

        # Divider
        pygame.draw.line(surface, self.COL_DIM, (40, y), (W - 40, y), 1)
        y += 12

        # Connectivity
        wifi_col = ACCENT if self._wifi != 'none' else self.COL_CRIT
        wifi_txt = self._f_sm.render(
            f'WIFI  {self._wifi}', True, wifi_col)
        surface.blit(wifi_txt, (margin, y))
        y += 24

        bt_col = ACCENT if self._bt else self.COL_DIM
        bt_txt = self._f_sm.render(
            'BT    on' if self._bt else 'BT    off', True, bt_col)
        surface.blit(bt_txt, (margin, y))

    def draw_icon(self, surface, center, radius):
        # Cache scaled icon surface — load once, reuse every frame
        cache_key = int(radius * 1.4)
        if getattr(self, '_icon_cache_size', None) != cache_key:
            try:
                img = pygame.image.load('assets/iris-app-system.png').convert_alpha()
                size = cache_key
                self._icon_cache = pygame.transform.smoothscale(img, (size, size))
                self._icon_cache_size = cache_key
            except Exception:
                self._icon_cache = self._icon_surf
                self._icon_cache_size = cache_key
        r = self._icon_cache.get_rect(center=center)
        surface.blit(self._icon_cache, r)

    def draw_widget(self, surface, rect):
        import core.display as _cd
        self._fps = _cd.FPS
        self._cpu, self._temp, self._mem, self._wifi, self._bt = self._reader.get()
        nr = self._name_surf.get_rect(
            centerx=rect.centerx, top=rect.top + 6)
        surface.blit(self._name_surf, nr)
        y = nr.bottom + 6

        for label, val, warn, crit in [
            ('CPU',  self._cpu,  60, 85),
            ('TMP',  self._temp, 65, 80),
            ('MEM',  self._mem,  70, 90),
        ]:
            col  = self._val_color(val, warn, crit)
            surf = self._f_sm.render(f'{label} {val:.0f}', True, col)
            sr   = surf.get_rect(centerx=rect.centerx, top=y)
            surface.blit(surf, sr)
            y += surf.get_height() + 2
