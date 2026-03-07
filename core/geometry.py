"""
core/geometry.py

Pure-math utilities shared across IRIS OS.
───────────────────────────────────────────
RULES
  • No pygame.  No hardware.  No side-effects.
  • animated_color uses a 256-entry pre-computed LUT — no sin/cos at runtime.
"""

import math


# ── Colour LUT ────────────────────────────────────────────────────────────────
# animated_color(t) used to call math.sin/cos every frame per hex.
# Pre-compute 256 steps (≈ 8.5° resolution at 30fps → imperceptible stepping).
# Lookup with index = int(t * _LUT_SCALE) % 256.

_LUT_SIZE  = 256
_LUT_SCALE = 30.0   # tune: higher = faster colour cycle

_COLOR_LUT: list = []
for _i in range(_LUT_SIZE):
    _t = _i / _LUT_SCALE
    _r = max(0, min(255, int(100 + 50  * math.sin(_t))))
    _g = max(0, min(255, int(180 + 60  * math.sin(_t + 2))))
    _b = max(0, min(255, int(255 + 30  * math.cos(_t + 1))))
    _COLOR_LUT.append((_r, _g, _b))
_COLOR_LUT = tuple(_COLOR_LUT)   # tuple: faster index than list on CPython


def animated_color(t: float) -> tuple:
    """O(1) colour from pre-computed LUT.  t is the pulse timer (seconds)."""
    return _COLOR_LUT[int(t * _LUT_SCALE) % _LUT_SIZE]


def animated_color_offset(t: float, offset: int) -> tuple:
    """Same LUT, with a per-hex index offset so each hex has a different phase."""
    return _COLOR_LUT[(int(t * _LUT_SCALE) + offset * (_LUT_SIZE // 7)) % _LUT_SIZE]


# ── Hex geometry ──────────────────────────────────────────────────────────────

def hex_points(center: tuple, radius: float) -> list:
    cx, cy = center
    return [
        (cx + radius * math.cos(math.radians(60 * i - 30)),
         cy + radius * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]


# ── Spatial ───────────────────────────────────────────────────────────────────

def distance(p1: tuple, p2: tuple) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def angle_diff(a: float, b: float) -> float:
    """Shortest angular distance (degrees). Always ≥ 0."""
    return abs((a - b + 180) % 360 - 180)


def rotate_points(points: list, cos_a: float, sin_a: float,
                  ox: float, oy: float) -> list:
    """
    Rotate a list of (x,y) points around (ox,oy).
    Caller pre-computes cos_a / sin_a so this stays multiply-only.
    Returns a new list of int tuples (ready for pygame.draw).
    """
    out = []
    for x, y in points:
        dx, dy = x - ox, y - oy
        out.append((int(ox + cos_a * dx - sin_a * dy),
                    int(oy + sin_a * dx + cos_a * dy)))
    return out


# ── Easing ────────────────────────────────────────────────────────────────────

def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


# ── Interpolation ─────────────────────────────────────────────────────────────

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_angle(a: float, b: float, t: float) -> float:
    """Lerp between two angles (degrees) via the short arc."""
    diff = (b - a + 180.0) % 360.0 - 180.0
    return (a + diff * t) % 360.0
