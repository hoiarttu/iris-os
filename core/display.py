import os
import pygame

os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
os.environ['SDL_VIDEO_CENTERED']   = '0'
os.environ['SDL_FBDEV_MULTIBUFFER'] = '1'

pygame.init()
pygame.font.init()

import os as _os
_DEV_MODE = _os.environ.get('IRIS_DEV', '0') == '1'
if _DEV_MODE:
    screen = pygame.display.set_mode((480, 854))
else:
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME)
WIDTH  = screen.get_width()
HEIGHT = screen.get_height()
CENTER = (WIDTH // 2, HEIGHT // 2)

pygame.display.set_caption('IRIS')
pygame.mouse.set_visible(False)

canvas = pygame.Surface((WIDTH, HEIGHT))

FPS   = 60
clock = pygame.time.Clock()

BLACK      = (  0,   0,   0)
WHITE      = (255, 255, 255)
ACCENT     = ( 80, 220, 255)
SECONDARY  = ( 80,  40, 180)   # IRIS purple — updated by _apply_accent on theme change
DIM        = ( 18,  18,  28)
HIGHLIGHT  = (255, 255, 100)
HEX_NORMAL = ( 60, 130, 220)

POOL = {
    'glow_lg': pygame.Surface((72, 72),        pygame.SRCALPHA),
    'glow_sm': pygame.Surface((48, 48),        pygame.SRCALPHA),
    'cone':    pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA),
}
for _s in POOL.values():
    _s.fill((0, 0, 0, 0))
"""
_MONO      = 'assets/fonts/Rajdhani-Regular.ttf'
_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")

_MONO      = os.path.join(FONT_DIR, "Rajdhani-Regular.ttf")
_MONO_BOLD = os.path.join(FONT_DIR, "Rajdhani-Bold.ttf")

FONT_ICON    = pygame.font.Font(_MONO_BOLD, 13)
FONT_TOOLTIP = pygame.font.Font(_MONO,      11)
FONT_DEBUG   = pygame.font.Font(_MONO,      11)
