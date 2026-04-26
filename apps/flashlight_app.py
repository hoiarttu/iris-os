"""
apps/flashlight_app.py — IRIS Torch
─────────────────────────────────────────────────────────────────────────────
Themed spatial torch anchored to world space.
pin_mode='pinned' — auto-off when looking away via bounds logic.
Beta tap  — toggle on/off
Alpha tap — cycle intensity down (25/50/75/100%)
"""

import pygame
import core.display as _cd
from apps.base_app import BaseApp

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

INTENSITIES       = [0.5, 1.0]
INTENSITY_LABELS  = ['50%', '100%']
LERP_SPEED        = 4.0   # brightness transition speed
PADDING           = 48    # px inset from screen edge
CORNER_RADIUS     = 32


class FlashlightApp(BaseApp):
    name             = 'Torch'
    description      = 'Spatial torch'
    pin_mode         = 'pinned'
    show_cursor      = False
    dlp_auto_off     = True   # bounds logic handles DLP sleep
    cap_hold_secs    = 0.0

    def __init__(self):
        super().__init__()
        self._on            = True
        self._intensity_idx = 3      # start at 100%
        self._current_frac  = 1.0   # smoothed brightness
        self._target_frac   = 1.0

        self._font    = pygame.font.Font(_MONO_BOLD, 16)
        self._font_nm = pygame.font.Font(_MONO_BOLD, 20)
        self._name_surf = self._font_nm.render('TORCH', True, (255, 255, 255))
        self._icon_surf = self._font.render('TR', True, (255, 255, 255))

    def update(self, dt):
        # Smooth brightness transition
        target = INTENSITIES[self._intensity_idx] if self._on else 0.0
        self._target_frac = target
        diff = self._target_frac - self._current_frac
        if abs(diff) > 0.001:
            self._current_frac += diff * min(1.0, LERP_SPEED * dt)
        else:
            self._current_frac = self._target_frac

    def _get_color(self):
        r, g, b = _cd.ACCENT
        f = self._current_frac
        return (int(r * f), int(g * f), int(b * f))

    def _handle_beta(self):
        self._on = not self._on

    def _handle_alpha(self):
        self._intensity_idx = (self._intensity_idx - 1) % len(INTENSITIES)

    def draw_fullscreen(self, surface):
        w, h = surface.get_size()
        surface.fill((0, 0, 0))

        if self._current_frac > 0.01:
            color = self._get_color()
            # Black rect slightly larger underneath to mask edge antialiasing glitch
            pygame.draw.rect(surface, (0, 0, 0),
                             pygame.Rect(PADDING - 2, PADDING - 2,
                                         w - (PADDING - 2) * 2,
                                         h - (PADDING - 2) * 2),
                             border_radius=CORNER_RADIUS + 2)
            pygame.draw.rect(surface, color,
                             pygame.Rect(PADDING, PADDING,
                                         w - PADDING * 2, h - PADDING * 2),
                             border_radius=CORNER_RADIUS)

        # Intensity label
        label = INTENSITY_LABELS[self._intensity_idx] if self._on else 'OFF'
        lbl = self._font.render(label, True, _cd.SECONDARY)
        surface.blit(lbl, (w - lbl.get_width() - 20, h - 28))

    def draw_icon(self, surface, center, radius):
        cache_key = int(radius * 1.4)
        if getattr(self, '_icon_cache_size', None) != cache_key:
            try:
                img = pygame.image.load('assets/iris-mirageOS-icon.png').convert_alpha()
                self._icon_cache = pygame.transform.smoothscale(
                    img, (cache_key, cache_key))
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
        color = tuple(int(c * INTENSITIES[self._intensity_idx])
                      for c in _cd.ACCENT)
        pygame.draw.rect(surface,
                         color,
                         pygame.Rect(rect.centerx - 20, rect.centery + 8,
                                     40, 16),
                         border_radius=6)
        pygame.draw.rect(surface,
                         _cd.SECONDARY,
                         pygame.Rect(rect.centerx - 20, rect.centery + 8,
                                     40, 16),
                         1, border_radius=6)
