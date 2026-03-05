"""
core/display.py
"""

import pygame

pygame.init()
pygame.font.init()

WIDTH  = 640
HEIGHT = 360
CENTER = (WIDTH // 2, HEIGHT // 2)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('IRIS')

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
    'glow_sm': pygame.Surface((48, 48),
