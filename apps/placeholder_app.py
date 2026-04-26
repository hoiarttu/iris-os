"""
apps/placeholder_app.py — empty hex slot
"""

import pygame
from apps.base_app import BaseApp

_MONO      = 'assets/fonts/Rajdhani-Bold.ttf'
_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'


class PlaceholderApp(BaseApp):

    def __init__(self, name: str, description: str = 'Coming soon'):
        self.name        = name
        self.description = description

        self._name_surf = pygame.font.Font(_MONO_BOLD, 24).render(
            name.upper(), True, (255, 255, 255))
        self._desc_surf = pygame.font.Font(_MONO_BOLD, 16).render(
            description, True, (120, 120, 120))
        self._icon_surf = pygame.font.Font(_MONO_BOLD, 18).render(
            name[:2].upper(), True, (255, 255, 255))

    def draw_icon(self, surface, center, radius):
        # Use named icon if available, fall back to text
        icon_map = {
            'Comms': 'assets/iris-app-comms.png',
        }
        iconpath = icon_map.get(self.name)
        cache_key = int(radius * 1.4)
        if iconpath and getattr(self, '_icon_cache_size', None) != cache_key:
            try:
                img = pygame.image.load(iconpath).convert_alpha()
                self._icon_cache = pygame.transform.smoothscale(img, (cache_key, cache_key))
                self._icon_cache_size = cache_key
            except Exception:
                self._icon_cache = None
                self._icon_cache_size = cache_key
        if iconpath and getattr(self, '_icon_cache', None):
            r = self._icon_cache.get_rect(center=center)
            surface.blit(self._icon_cache, r)
        else:
            r = self._icon_surf.get_rect(center=center)
            surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx, centery=rect.centery - 10)
        surface.blit(self._name_surf, nr)
        dr = self._desc_surf.get_rect(centerx=rect.centerx, top=nr.bottom + 4)
        surface.blit(self._desc_surf, dr)
