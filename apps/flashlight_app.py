"""
apps/flashlight_app.py — IRIS Flashlight
─────────────────────────────────────────────────────────────────────────────
Projects a themed color surface anchored to world space.
pin_mode='pinned' — DLP auto-cuts when looking away via existing bounds logic.
dlp_auto_off=False — we manage DLP state ourselves.

Beta tap — toggle on/off
Alpha tap — cycle intensity (25/50/75/100%)
"""

import pygame
import core.display as _cd
from apps.base_app import BaseApp

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

INTENSITIES = [0.25, 0.5, 0.75, 1.0]
INTENSITY_LABELS = ['25%', '50%', '75%', '100%']


class FlashlightApp(BaseApp):
    name             = 'Torch'
    description      = 'Spatial torch'
    pin_mode         = 'pinned'
    show_cursor      = False
    dlp_auto_off     = False
    cap_hold_secs    = 0.0

    def __init__(self):
        super().__init__()
        self._on           = True
        self._intensity_idx = 3   # start at 100%
        self._surface      = None
        self._last_accent  = None
        self._last_size    = None

        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)
        self._name_surf = fn.render('LIGHT', True, (255, 255, 255))
        self._icon_surf = fi.render('LT',   True, (255, 255, 255))

    def _get_color(self):
        r, g, b = _cd.ACCENT
        frac = INTENSITIES[self._intensity_idx]
        return (int(r * frac), int(g * frac), int(b * frac))

    def _rebuild_surface(self, w, h):
        color = self._get_color()
        s = pygame.Surface((w, h))
        s.fill(color)
        self._surface      = s
        self._last_accent  = _cd.ACCENT
        self._last_size    = (w, h)

    def _handle_beta(self):
        self._on = not self._on

    def _handle_alpha(self):
        self._intensity_idx = (self._intensity_idx - 1) % len(INTENSITIES)
        self._surface = None   # force rebuild

    def draw_fullscreen(self, surface):
        w, h = surface.get_size()
        if self._on:
            if (self._surface is None or
                    self._last_accent != _cd.ACCENT or
                    self._last_size != (w, h)):
                self._rebuild_surface(w, h)
            surface.blit(self._surface, (0, 0))
            # Intensity indicator — bottom right
            f = pygame.font.Font(_MONO_BOLD, 16)
            lbl = f.render(INTENSITY_LABELS[self._intensity_idx], True, _cd.SECONDARY)
            surface.blit(lbl, (w - lbl.get_width() - 16, h - 28))
        else:
            surface.fill((0, 0, 0))
            f = pygame.font.Font(_MONO_BOLD, 20)
            off = f.render('OFF', True, _cd.SECONDARY)
            surface.blit(off, (w // 2 - off.get_width() // 2,
                               h // 2 - off.get_height() // 2))

    def draw_icon(self, surface, center, radius):
        cache_key = int(radius * 1.4)
        if getattr(self, '_icon_cache_size', None) != cache_key:
            try:
                img = pygame.image.load('assets/iris-mirageOS-icon.png').convert_alpha()
                self._icon_cache = pygame.transform.smoothscale(img, (cache_key, cache_key))
                self._icon_cache_size = cache_key
            except Exception:
                self._icon_cache = self._icon_surf
                self._icon_cache_size = cache_key
        r = self._icon_cache.get_rect(center=center)
        surface.blit(self._icon_cache, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx,
                                       centery=rect.centery - 8)
        surface.blit(self._name_surf, nr)
        # Show current color swatch
        color = self._get_color()
        pygame.draw.circle(surface, color,
                           (rect.centerx, rect.centery + 14), 8)
        pygame.draw.circle(surface, _cd.SECONDARY,
                           (rect.centerx, rect.centery + 14), 8, 1)
