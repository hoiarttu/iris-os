"""
apps/base_app.py — BaseApp contract
─────────────────────────────────────────────────────────────────────────────
All methods are no-ops by default.
Apps only override what they need.
"""

import pygame


class BaseApp:
    name        = 'App'
    description = ''
    icon_path   = None   # path to PNG asset, or None to use draw_icon()

    # State
    focused = False
    active  = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def update(self, dt: float):
        pass

    def on_focus(self):
        self.focused = True

    def on_blur(self):
        self.focused = False
        self.active  = False

    def on_select(self):
        self.active = True

    def launch(self):
        """App takes the full screen. Called by kernel."""
        pass

    def suspend(self):
        """Menu returned via home gesture. App freezes."""
        pass

    def resume(self):
        """App returns to foreground."""
        pass

    def close(self):
        """App exits. Kernel returns to menu."""
        self.active  = False
        self.focused = False

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_icon(self, surface: pygame.Surface, center: tuple, radius: float):
        """
        Draw app icon inside hex.
        Default: two-letter abbreviation.
        Override with PNG blit when assets are ready.
        """
        pass   # subclasses implement

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        """
        Draw centre widget when this app is focused or default.
        Override in each app.
        """
        pass

    def draw_fullscreen(self, surface: pygame.Surface):
        """
        Draw full screen when app is in STATE_APP.
        Override in each app.
        """
        surface.fill((0, 0, 0))
