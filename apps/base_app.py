"""
apps/base_app.py — BaseApp contract
─────────────────────────────────────────────────────────────────────────────
All methods are no-ops by default.
Apps only override what they need.

pin_mode:
  'pinned'  fullscreen canvas offset by IMU delta from mirage origin
            looking away = black. Default.
  'free'    always centered, ignores IMU (SystemApp etc.)
  'world'   app handles IMU itself via on_imu() (TestgameApp)

exit:
  No per-app exit mode. Exit is always:
    Both caps hold 1.5s  → home (system, unkillable)
    Fist + pull          → home
  Single cap alpha = back/navigate (in-app only, never exits)
  Single cap beta  = confirm/select

cap_hold_secs:
  Minimum hold duration before alpha/beta register. Per-app.
  0.0 = instant (default). Raise for immersive apps (e.g. 1.5 for games).
"""

import pygame


class BaseApp:
    name          = 'App'
    description   = ''
    icon_path     = None

    # Spatial
    pin_mode      = 'pinned'   # 'pinned' | 'free' | 'world'

    # Cursor
    show_cursor   = True

    # Input
    cap_hold_secs = 0.0        # min hold before alpha/beta register

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

    # ── Input hooks (called by kernel) ────────────────────────────────────────

    def on_event(self, event):
        """Raw pygame event forwarded by kernel each frame."""
        pass

    def on_imu(self, imu_state, hand=None):
        """IMU + hand state, called every frame in STATE_APP."""
        pass

    def on_gesture(self, gesture: str):
        """
        Named gesture string forwarded by kernel.
        Kernel handles: 'grab_pull' (home), 'pinch' (select) at system level.
        Apps receive all gestures and can act on swipe_up/down for scroll etc.
        """
        pass

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_icon(self, surface: pygame.Surface, center: tuple, radius: float):
        """Draw app icon inside hex."""
        pass

    def draw_widget(self, surface: pygame.Surface, rect: pygame.Rect):
        """Draw centre widget when focused."""
        pass

    def draw_fullscreen(self, surface: pygame.Surface):
        """Draw full screen when app is in STATE_APP."""
        surface.fill((0, 0, 0))
