"""
components/hexmenu.py

HexMenu — layout geometry and pointer hit-detection.
──────────────────────────────────────────────────────
RULES
  • No pygame.  No hardware.  Stateless geometry after __init__.
  • Base hex vertex positions are computed ONCE in __init__ and cached.
  • get_rotated_polygons() only applies a rotation delta — no trig per vertex.
  • Point-in-polygon uses early-exit on bounding-radius check first.
"""

import math
from core.geometry import rotate_points


class HexMenu:
    """
    7-hex layout (1 centre + 6 surrounding), pointy-top orientation.

    Hot-path contract
    -----------------
    get_rotated_polygons(cos_a, sin_a, cx, cy) → list of 7 polygon point-lists
      • Only called with pre-computed cos/sin from mirage_manager.
      • No math.cos / math.sin inside the loop.
    """

    N_HEXES = 7

    def __init__(self, radius: float = 42):
        self.radius = radius
        R = radius

        # Centre of each hex relative to anchor (0,0)
        self._rel_centers: tuple = (
            ( 0,                    0          ),   # 0 centre
            ( math.sqrt(3) * R,     0          ),   # 1 right
            ( math.sqrt(3)/2 * R,   1.5 * R    ),   # 2 bottom-right
            (-math.sqrt(3)/2 * R,   1.5 * R    ),   # 3 bottom-left
            (-math.sqrt(3) * R,     0          ),   # 4 left
            (-math.sqrt(3)/2 * R,  -1.5 * R    ),   # 5 top-left
            ( math.sqrt(3)/2 * R,  -1.5 * R    ),   # 6 top-right
        )

        # Vertex offsets around a hex centre (pointy-top)
        self._v_offsets: tuple = tuple(
            (R * math.cos(math.radians(a)),
             R * math.sin(math.radians(a)))
            for a in (30, 90, 150, 210, 270, 330)
        )

        # Pre-built polygons centred at (0,0) — translated + rotated each frame
        # Shape: tuple of 7 × tuple of 6 × (float, float)
        self._base_polys: tuple = tuple(
            tuple((dx + ox, dy + oy)
                  for ox, oy in self._v_offsets)
            for dx, dy in self._rel_centers
        )

        # Pre-compute bounding radius for quick rejection in hit-test
        # (point must be within this radius of a hex centre to be inside it)
        self._hit_radius_sq: float = R * R

    # ── Polygon construction (hot path) ──────────────────────────────────────

    def get_rotated_polygons(self, cos_a: float, sin_a: float,
                              cx: float, cy: float) -> list:
        """
        Return 7 screen-space polygons rotated by (cos_a, sin_a) around (cx, cy).
        cos_a, sin_a must be pre-computed by the caller (done once per frame).
        """
        out = []
        for base in self._base_polys:
            rotated = []
            for x, y in base:
                rotated.append((
                    int(cx + cos_a * x - sin_a * y),
                    int(cy + sin_a * x + cos_a * y),
                ))
            out.append(rotated)
        return out

    def get_center_points(self, cos_a: float, sin_a: float,
                           cx: float, cy: float) -> list:
        """Return just the centre point of each hex (for icon placement)."""
        out = []
        for dx, dy in self._rel_centers:
            out.append((
                int(cx + cos_a * dx - sin_a * dy),
                int(cy + sin_a * dx + cos_a * dy),
            ))
        return out

    # ── Hit detection ─────────────────────────────────────────────────────────

    def get_highlight(self, polygons: list, centers: list,
                     	 pointer: tuple):
        """
        Return the index of the hex under `pointer`, or None.
        Uses a two-stage test:
          1. Cheap radius² rejection against each hex centre.
          2. Ray-casting only if the point passes stage 1.
        """
        px, py = pointer
        r2 = self._hit_radius_sq
        for idx, (poly, (hx, hy)) in enumerate(zip(polygons, centers)):
            dx, dy = px - hx, py - hy
            if dx*dx + dy*dy > r2:
                continue                    # fast reject
            if self._point_in_poly(px, py, poly):
                return idx
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _point_in_poly(x: float, y: float, poly) -> bool:
        inside = False
        n = len(poly)
        for i in range(n):
            j = (i - 1) % n
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y):
                if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
        return inside
