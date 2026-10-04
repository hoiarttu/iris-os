"""
apps/dash_app.py — Dash
─────────────────────────────────────────────────────────────────────────────
Launched from the centre hex. Always-visible top row while open: temperature
(left), time (centre), date (right, no year). Map/Scan land in later passes.

Weather reads a cached {"lat":.., "lon":..} from LOCATION_CACHE_PATH, written
by the (not-yet-built) phone companion page. Until that exists, temperature
correctly shows the empty placeholder — this is expected, not a bug.
"""

import time, threading, json
import urllib.request
import pygame
from apps.base_app import BaseApp
from core.display   import WIDTH, HEIGHT, BLACK, WHITE

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

LOCATION_CACHE_PATH = 'last_location.json'
WEATHER_POLL_SECS   = 1200   # 20 min between live fetches once a location exists
LOCATION_CHECK_SECS = 60     # how often we check whether a location has appeared

# Bottom info row. Its top edge IS the future map's bottom edge — not a
# margin near it. Map viewport must use this exact constant as its bottom,
# so the two are structurally attached, never independently positioned.
BOTTOM_BAR_MARGIN      = 24
BOTTOM_BAR_RESERVED_PX = 64


class WeatherReader(threading.Thread):
    """Background poller — Open-Meteo, free/no-key. Reads the last cached
    phone location rather than tracking it live; see module docstring."""

    def __init__(self):
        super().__init__(daemon=True)
        self.temp_c      = None   # None = no reading yet (placeholder state)
        self.last_update = 0.0
        self._lock        = threading.Lock()
        self._stopping     = False

    def run(self):
        while not self._stopping:
            loc = self._read_cached_location()
            if loc is not None:
                with self._lock:
                    last = self.last_update
                if last == 0.0 or time.time() - last >= WEATHER_POLL_SECS:
                    self._fetch(loc)
            time.sleep(LOCATION_CHECK_SECS)

    def _read_cached_location(self):
        try:
            with open(LOCATION_CACHE_PATH) as f:
                data = json.load(f)
            return float(data['lat']), float(data['lon'])
        except Exception:
            return None

    def _fetch(self, loc):
        lat, lon = loc
        url = (f'https://api.open-meteo.com/v1/forecast'
               f'?latitude={lat}&longitude={lon}&current=temperature_2m')
        try:
            req = urllib.request.Request(
                url, headers={'User-Agent': 'iris-os-dash/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                temp = data.get('current', {}).get('temperature_2m')
                if temp is not None:
                    with self._lock:
                        self.temp_c      = float(temp)
                        self.last_update = time.time()
        except Exception:
            pass   # fail quietly — corner just keeps showing last known/placeholder

    def get(self):
        with self._lock:
            return self.temp_c

    def stop(self):
        self._stopping = True


class DashApp(BaseApp):
    roll_locked = True       # status row ignores head roll
    name        = 'Dash'
    description = 'Glanceable HUD'
    pin_mode    = 'free'   # always centred, ignores head yaw/pitch offset
    show_cursor = False    # no reticle yet — hide cursor while Dash is open

    def __init__(self):
        super().__init__()
        self._time_str = ''
        self._date_str = ''
        self._temp_val = None
        self._tick     = 999.0

        self._font      = pygame.font.Font(_MONO_BOLD, 28)
        self._color     = WHITE
        self._time_surf = None
        self._date_surf = None
        self._temp_surf = None

        self._weather = WeatherReader()
        self._weather.start()

    def close(self):
        self._weather.stop()
        super().close()

    def update(self, dt: float):
        if not self._weather.is_alive():
            print('[Dash] WeatherReader died — restarting')
            self._weather = WeatherReader()
            self._weather.start()

        self._tick += dt
        if self._tick >= 1.0:
            self._tick = 0.0
            now = time.localtime()
            t = f'{now.tm_hour:02d}.{now.tm_min:02d}'
            d = f'{now.tm_mday}.{now.tm_mon}'
            if t != self._time_str:
                self._time_str  = t
                self._time_surf = self._font.render(t, True, self._color)
            if d != self._date_str:
                self._date_str  = d
                self._date_surf = self._font.render(d, True, self._color)

            temp = self._weather.get()
            temp_text = f'{temp:.0f}°C' if temp is not None else '—'
            if temp_text != self._temp_val:
                self._temp_val  = temp_text
                self._temp_surf = self._font.render(temp_text, True, self._color)

    def draw_fullscreen(self, surface: pygame.Surface):
        surface.fill(BLACK)
        y = HEIGHT - BOTTOM_BAR_MARGIN   # row's baseline — anchored to screen bottom
        if self._temp_surf:
            r = self._temp_surf.get_rect(left=BOTTOM_BAR_MARGIN, bottom=y)
            surface.blit(self._temp_surf, r)
        if self._time_surf:
            r = self._time_surf.get_rect(centerx=WIDTH // 2, bottom=y)
            surface.blit(self._time_surf, r)
        if self._date_surf:
            r = self._date_surf.get_rect(right=WIDTH - BOTTOM_BAR_MARGIN, bottom=y)
            surface.blit(self._date_surf, r)
