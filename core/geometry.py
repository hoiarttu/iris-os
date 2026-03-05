import math

def hex_points(center, radius):
    cx, cy = center
    return [(cx + radius * math.cos(math.radians(60 * i - 30)),
             cy + radius * math.sin(math.radians(60 * i - 30))) for i in range(6)]

def ease_out(t):
    return 1 - (1 - t)**3

def animated_color(t):
    r = max(0, min(255, int(100 + 50 * math.sin(t))))
    g = max(0, min(255, int(180 + 60 * math.sin(t + 2))))
    b = max(0, min(255, int(255 + 30 * math.cos(t + 1))))
    return (r, g, b)

def angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)

def distance(p1, p2):
    """
    Euclidean distance between two points p1 and p2.
    p1, p2: (x, y) tuples
    """
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.hypot(dx, dy)

