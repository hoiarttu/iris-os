# components/draw.py
import pygame

def draw_hex(surface, points, fill_color, border_color=(0,0,0), border_width=2):
    """
    Draw a single hexagon given its vertex list.
    """
    # Filled polygon
    pygame.draw.polygon(surface, fill_color, points)
    # Optional border
    if border_width > 0:
        pygame.draw.polygon(surface, border_color, points, border_width)

def draw_hex_menu(surface, polygons, highlight_idx=None):
    """
    Draw all hexagons in the menu. The polygon list is a list of point-lists.
    The highlighted hex is drawn in a distinct color.
    """
    for idx, poly in enumerate(polygons):
        if idx == highlight_idx:
            color = (255, 255, 100)  # Highlight color (light yellow)
        else:
            color = (100, 150, 255)  # Normal color (light blue)
        draw_hex(surface, poly, fill_color=color, border_color=(0,0,0), border_width=2)

def draw_pointer(surface, pos, color=(255,255,255), size=3):
    """
    Draw a small circle at the pointer position (screen center).
    """
    pygame.draw.circle(surface, color, pos, size)

