"""
components/hexmenu.py
"""

import math


class HexMenu:
    N_HEXES = 7

    def __init__(self, radius=42):
        self.radius = radius
        R = radius

        self._rel_centers = (
            ( 0,                    0        ),
            ( math.sqrt(3) * R,     0        ),
            ( math.sqrt(3)/2 * R,   1.5 * R  ),
            (-math.sqrt(3)/2 * R,   1.5 * R  ),
            (-math.sqrt(3) * R,     0        ),
            (-math.sqrt(3)/2 * R,  -1.5 * R  ),
            ( math.sqrt(3)/2 * R,  -1.5 * R  ),
        )

        self._v_offsets = tuple(
            (R * math.cos(math.radians(a)),
             R * math.sin(math.radians(a)))
            for a in (30, 90, 150, 210, 270, 330)
        )

        self._base_polys = tuple(
            tuple((dx + ox, dy + oy)
                  for ox, oy in self._v_offsets)
            for dx, dy in self._rel_centers
        )

        self._hit_radius_sq = R * R

    def get_rotated_polygons(self, cos_a, sin_a, cx, cy):
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

    def get_center_points(self, cos_a, sin_a, cx, cy):
        out = []
        for dx, dy in self._rel_centers:
            out.append((
                int(cx + cos_a * dx - sin_a * dy),
                int(cy + sin_a * dx + cos_a * dy),
            ))
        return out

    def get_highlight(self, polygons, centers, pointer):
        px, py = pointer
        r2 = self._hit_radius_sq
        for idx, (poly, (hx, hy)) in enumerate(zip(polygons, centers)):
            dx, dy = px - hx, py - hy
            if dx*dx + dy*dy > r2:
                continue
            if self._point_in_poly(px, py, poly):
                return idx
        return None

    @staticmethod
    def _point_in_poly(x, y, poly):
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
