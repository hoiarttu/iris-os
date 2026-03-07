"""
apps/placeholder_app.py

Placeholder app for hex slots not yet implemented.
────────────────────────────────────────────────────
Shows a name and "Coming soon" in the centre widget when focused.
Each slot gets its own instance with a custom name.
"""

import pygame
from apps.base_app import BaseApp


class PlaceholderApp(BaseApp):

    def __init__(self, name: str, description: str = 'Coming soon'):
        self.name        = name
        self.description = description

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        # App name
        name_font = pygame.font.SysFont('monospace', 22, bold=True)
        name_surf = name_font.render(self.name.upper(), True, (80, 220, 255))
        name_rect = name_surf.get_rect(centerx=rect.centerx,
                                        top=rect.top + 12)
        surface.blit(name_surf, name_rect)

        # Coming soon
        desc_font = pygame.font.SysFont('monospace', 13)
        desc_surf = desc_font.render(self.description, True, (120, 120, 120))
        desc_rect = desc_surf.get_rect(centerx=rect.centerx,
                                        top=name_rect.bottom + 6)
        surface.blit(desc_surf, desc_rect)
