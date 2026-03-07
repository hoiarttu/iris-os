"""
apps/base_app.py

Abstract base class for all IRIS apps.
────────────────────────────────────────
Every app inherits from BaseApp and overrides only what it needs.
All methods have safe no-op defaults so placeholder apps need zero code.

Lifecycle
---------
  update(dt)        called every frame regardless of focus
  on_focus()        gaze entered this hex
  on_blur()         gaze left this hex
  on_select()       dwell timer completed — app confirmed

Rendering
---------
  draw_icon(surface, center, radius)
      Draw the app's icon inside its hex.
      center: (x, y) pixel centre of the hex
      radius: hex radius in pixels

  draw_widget(surface, rect)
      Draw the centre widget when this app is focused (or default).
      rect: pygame.Rect defining the available centre area
"""

import pygame


class BaseApp:
    # ── Identity ─────────────────────────────────────────────────────────────
    name        = 'App'
    description = ''       # one line shown in centre widget when focused
    icon_path   = None     # path to PNG icon, or None to use draw_icon()

    # ── State ─────────────────────────────────────────────────────────────────
    focused  = False
    active   = False       # True after on_select() fires, until on_blur()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def update(self, dt: float):
        """Called every frame. Override for live data, animations, etc."""
        pass

    def on_focus(self):
        """Gaze entered this hex."""
        self.focused = True

    def on_blur(self):
        """Gaze left this hex."""
        self.focused = False
        self.active  = False

    def on_select(self):
        """Dwell timer completed — user confirmed this app."""
        self.active = True

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_icon(self, surface: pygame.Surface, center: tuple, radius: float):
        """
        Draw the app icon inside its hex.
        Default: draws the first two letters of the app name.
        Override for custom icons or PNG rendering.
        """
        font = pygame.font.SysFont('monospace', int(radius * 0.5), bold=True)
        col  = (80, 220, 255) if not self.focused else (255, 255, 100)
        text = font.render(self.name[:2].upper(), True, col)
        rect = text.get_rect(center=center)
        surface.blit(text, rect)

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        """
        Draw the centre widget when this app is focused.
        Default: shows app name and description.
        Override in each app for custom content.
        """
        # App name
        name_font = pygame.font.SysFont('monospace', 22, bold=True)
        name_surf = name_font.render(self.name.upper(), True, (80, 220, 255))
        name_rect = name_surf.get_rect(centerx=rect.centerx,
                                        top=rect.top + 12)
        surface.blit(name_surf, name_rect)

        # Description
        if self.description:
            desc_font = pygame.font.SysFont('monospace', 13)
            desc_surf = desc_font.render(self.description, True, (180, 180, 180))
            desc_rect = desc_surf.get_rect(centerx=rect.centerx,
                                            top=name_rect.bottom + 6)
            surface.blit(desc_surf, desc_rect)
