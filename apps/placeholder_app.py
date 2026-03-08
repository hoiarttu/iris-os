"""
apps/placeholder_app.py — empty hex slot
"""

import pygame
from apps.base_app import BaseApp

_MONO      = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
_MONO_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


class PlaceholderApp(BaseApp):

    def __init__(self, name: str, description: str = 'Coming soon'):
        self.name        = name
        self.description = description

        self._name_surf = pygame.font.Font(_MONO_BOLD, 20).render(
            name.upper(), True, (80, 220, 255))
        self._desc_surf = pygame.font.Font(_MONO, 13).render(
            description, True, (120, 120, 120))
        self._icon_surf = pygame.font.Font(_MONO_BOLD, 16).render(
            name[:2].upper(), True, (80, 220, 255))

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx, top=rect.top + 10)
        surface.blit(self._name_surf, nr)
        dr = self._desc_surf.get_rect(centerx=rect.centerx, top=nr.bottom + 6)
        surface.blit(self._desc_surf, dr)
