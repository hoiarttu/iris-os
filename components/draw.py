"""
components/draw.py

All pygame drawing — zero Surface allocations in the hot path.
──────────────────────────────────────────────────────────────
RULES
  • Every function takes `surface` as first arg — no global canvas.
  • Alpha effects use POOL surfaces from core.display — never allocate.
  • Tooltip text surfaces are cached by string — rendered once, reused every frame.
  • Font objects come from core.display — never constructed here.
"""

import math
import pygame

from core.display import (POOL, ACCENT, HIGHLIGHT, HEX_NORMAL,
                           WHITE, BLACK, FONT_ICON, FONT_TOOLTIP)


# ── Tooltip cache ─────────────────────────────────────────────────────────────
# Maps label string → pre-rendered (text_surf, shadow_surf) tuple.
# Zero render calls after first encounter of each unique label.
_TIP_CACHE: dict = {}


def _get_tip_surfs(text: str) -> tuple:
    if text not in _TIP_CACHE:
        _TIP_CACHE[text] = (
            FONT_TOOLTIP.render(text, True, WHITE),
            FONT_TOOLTIP.render(text, True, BLACK),
        )
    return _TIP_CACHE[text]


# ── Icon cache ─────────────────────────────────────────────────────────────────
_ICON_CACHE: dict = {}


def _get_icon_surf(label: str, color: tuple, scale: float) -> pygame.Surface:
    key = (label[:2], color, round(scale, 1))
    if key not in _ICON_CACHE:
        size   = max(8, int(13 * scale))
        font   = FONT_ICON if scale == 1.0 else pygame.font.SysFont('monospace', size, bold=True)
        _ICON_CACHE[key] = font.render(label[:2], True, color)
    return _ICON_CACHE[key]


# ── Hex ───────────────────────────────────────────────────────────────────────

def draw_hex(surface, points, fill_color, alpha: int = 255,
             border_color=BLACK, border_width: int = 2):
    """
    Draw a filled hexagon.
    alpha < 255: uses POOL['glow_sm'] as scratch — no alloc.
    """
    if alpha < 255:
        s = POOL['glow_sm']
        # We can't use a tiny surface for an arbitrary polygon —
        # use the cone surface (full-size) for alpha-blended hexes.
        s = POOL['cone']
        s.fill((0, 0, 0, 0))
        r, g, b = fill_color[:3]
        pygame.draw.polygon(s, (r, g, b, alpha), points)
        surface.blit(s, (0, 0))
    else:
        pygame.draw.polygon(surface, fill_color, points)
    if border_width > 0:
        pygame.draw.polygon(surface, border_color, points, border_width)


def draw_hex_menu(surface, polygons, highlight_idx=None):
    for idx, poly in enumerate(polygons):
        draw_hex(surface, poly,
                 fill_color=HIGHLIGHT if idx == highlight_idx else HEX_NORMAL)


# ── Centre glow / reticle ─────────────────────────────────────────────────────

def draw_center_glow(surface, center, radius: int = 18):
    """
    Radial glow using POOL['glow_lg'].
    Draws a single gradient circle — not 18 separate surfaces.
    """
    s  = POOL['glow_lg']
    s.fill((0, 0, 0, 0))
    hw = s.get_width()  // 2
    hh = s.get_height() // 2
    # Two-pass: outer soft ring + inner bright ring
    pygame.draw.circle(s, (*ACCENT, 40),  (hw, hh), radius)
    pygame.draw.circle(s, (*ACCENT, 90),  (hw, hh), radius // 2)
    surface.blit(s, (center[0] - hw, center[1] - hh))
    pygame.draw.circle(surface, WHITE, center, 3)


# ── Light cone ────────────────────────────────────────────────────────────────

def draw_light_cone(surface, origin, target, color=None):
    """
    Faint triangle spotlight from origin toward the selected hex.
    Single POOL['cone'] blit — not 12 separate surfaces.
    """
    color = color or ACCENT
    ox, oy = origin
    tx, ty = target
    dx, dy = tx - ox, ty - oy
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * 16, dx / length * 16

    tip   = (int(tx), int(ty))
    left  = (int(ox + nx), int(oy + ny))
    right = (int(ox - nx), int(oy - ny))

    s = POOL['cone']
    s.fill((0, 0, 0, 0))
    pygame.draw.polygon(s, (*color, 35), [left, right, tip])
    surface.blit(s, (0, 0))


# ── Icon / glow ───────────────────────────────────────────────────────────────

def draw_icon(surface, center, color, label: str = '?', scale: float = 1.0):
    surf = _get_icon_surf(label, color, scale)
    rect = surf.get_rect(center=center)
    surface.blit(surf, rect)


def draw_icon_glow(surface, center, intensity: float = 0.5):
    """Pulsing halo around selected icon using POOL['glow_sm']."""
    radius = int(14 + intensity * 6)
    alpha  = int(80 * intensity)
    s  = POOL['glow_sm']
    s.fill((0, 0, 0, 0))
    hw = s.get_width()  // 2
    hh = s.get_height() // 2
    pygame.draw.circle(s, (*ACCENT, alpha), (hw, hh), radius)
    surface.blit(s, (center[0] - hw, center[1] - hh))


def draw_tooltip(surface, anchor, text: str):
    if not text:
        return
    txt_surf, shd_surf = _get_tip_surfs(text)
    x = anchor[0] - txt_surf.get_width() // 2
    y = anchor[1] + 28
    surface.blit(shd_surf, (x + 1, y + 1))
    surface.blit(txt_surf, (x, y))


# ── Pointer ───────────────────────────────────────────────────────────────────

def draw_pointer(surface, pos, color=WHITE, size: int = 3):
    pygame.draw.circle(surface, color, pos, size)
    pygame.draw.circle(surface, BLACK, pos, size, 1)
