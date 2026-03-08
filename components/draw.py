"""
components/draw.py

Minimal draw primitives — no animations, no allocs in hot path.
─────────────────────────────────────────────────────────────────────────────
Only what is strictly needed:
  draw_hex_border   filled hex + border
  draw_pointer      gaze crosshair dot
"""

import pygame
from core.display import BLACK, WHITE, ACCENT

# ── Hex colours ───────────────────────────────────────────────────────────────

HEX_FILL           = (  8,   8,  18)
HEX_BORDER_IDLE    = ( 80,  40, 180)
HEX_BORDER_FOCUSED = ( 80, 220, 255)
HEX_BORDER_WIDTH   = 2


def draw_hex_border(surface, points, focused: bool = False):
    """
    Dark-filled hex with single-colour border.
    No alpha. No glow. Asset-ready — app.draw_icon() draws on top.
    """
    pygame.draw.polygon(surface, HEX_FILL, points)
    colour = HEX_BORDER_FOCUSED if focused else HEX_BORDER_IDLE
    pygame.draw.polygon(surface, colour, points, HEX_BORDER_WIDTH)


def draw_pointer(surface, pos, color=WHITE, size: int = 3):
    """Gaze crosshair — simple dot."""
    pygame.draw.circle(surface, color, pos, size)
    pygame.draw.circle(surface, BLACK,  pos, size, 1)
