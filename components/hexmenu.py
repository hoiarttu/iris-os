# components/hexmenu.py
import math

class HexMenu:
    """
    Computes the layout of 7 hexagons (one center + 6 around) and checks pointer hits.
    """
    def __init__(self, radius):
        self.radius = radius
        R = radius
        # Precompute relative centers (axial layout, pointy-topped hex coordinates)
        self.rel_centers = [
            (0,           0),            # center hex
            (math.sqrt(3)*R, 0),         # right
            (math.sqrt(3)/2*R,  1.5*R),  # bottom-right
            (-math.sqrt(3)/2*R, 1.5*R),  # bottom-left
            (-math.sqrt(3)*R,   0),      # left
            (-math.sqrt(3)/2*R, -1.5*R), # top-left
            (math.sqrt(3)/2*R, -1.5*R)   # top-right
        ]
        # Precompute vertex offsets for a hexagon (pointy top, flat sides on left/right)
        angles_deg = [30, 90, 150, 210, 270, 330]
        self.vertex_offsets = [
            (R * math.cos(math.radians(a)), R * math.sin(math.radians(a)))
            for a in angles_deg
        ]

    def get_hex_polygons(self, center):
        """
        Return a list of polygons (list of vertices) for each hex,
        given the central position of the center hex.
        """
        cx, cy = center
        polygons = []
        for dx, dy in self.rel_centers:
            hx, hy = cx + dx, cy + dy
            # Build hexagon vertices around (hx, hy)
            poly = [(hx + ox, hy + oy) for (ox, oy) in self.vertex_offsets]
            polygons.append(poly)
        return polygons

    def get_highlight(self, polygons, pointer):
        """
        Given polygons and the pointer (x,y), return the index of the polygon
        that contains the point, or None if none contain it.
        """
        px, py = pointer
        for idx, poly in enumerate(polygons):
            if self.point_in_poly(px, py, poly):
                return idx
        return None

    def point_in_poly(self, x, y, poly):
        """
        Ray-casting algorithm to test if point (x,y) is inside polygon poly.
        Uses the even-odd rule:contentReference[oaicite:13]{index=13}.
        """
        inside = False
        n = len(poly)
        for i in range(n):
            j = (i - 1) % n
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y) != (yj > y):
                # Compute x coordinate of intersection with horizontal ray
                x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < x_intersect:
                    inside = not inside
        return inside

