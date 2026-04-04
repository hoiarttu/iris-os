import os
import pygame

os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
os.environ['SDL_VIDEO_CENTERED']   = '0'
os.environ['SDL_FBDEV_MULTIBUFFER'] = '1'

pygame.init()
pygame.font.init()

screen = pygame.display.set_mode((0, 0), pygame.NOFRAME)
WIDTH  = screen.get_width()
HEIGHT = screen.get_height()
CENTER = (WIDTH // 2, HEIGHT // 2)

pygame.display.set_caption('IRIS')
pygame.mouse.set_visible(False)

canvas = pygame.Surface((WIDTH, HEIGHT))

FPS   = 30
clock = pygame.time.Clock()

BLACK      = (  0,   0,   0)
WHITE      = (255, 255, 255)
ACCENT     = ( 80, 220, 255)
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

_MONO      = '/home/iris/mirage_gui/assets/fonts/Rajdhani-Regular.ttf'
_MONO_BOLD = '/home/iris/mirage_gui/assets/fonts/Rajdhani-Bold.ttf'

FONT_ICON    = pygame.font.Font(_MONO_BOLD, 13)
FONT_TOOLTIP = pygame.font.Font(_MONO,      11)
FONT_DEBUG   = pygame.font.Font(_MONO,      11)
