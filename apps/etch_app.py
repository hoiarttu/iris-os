"""
apps/etch_app.py — IRIS Etch
─────────────────────────────────────────────────────────────────────────────
World-space drawing app. Canvas is a large pixel buffer panned by IMU.
Uses same PX_PER_DEGREE constants as mirage menu for consistent feel.

Input:
  Beta held       → draw at hand/cursor position
  Beta tap        → cycle color forward
  Alpha tap       → cycle color backward
  Both hold 1.5s  → home (system)

Save on close → assets/media/etch_<timestamp>.png
"""

import os, time
import pygame
from apps.base_app import BaseApp
from core.display import WIDTH, HEIGHT, BLACK, WHITE, ACCENT

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

# ── Canvas config ─────────────────────────────────────────────────────────────

CANVAS_W   = 4096
CANVAS_H   = 2048
PX_PER_YAW = 28     # matches main.py PX_PER_DEGREE_YAW
PX_PER_PITCH = 24   # matches main.py PX_PER_DEGREE_PITCH

# ── Palette ───────────────────────────────────────────────────────────────────

COLORS = [
    (255, 255, 255),   # white
    (80,  220, 255),   # IRIS cyan
    (255,  80,  80),   # red
    (255, 220,  50),   # yellow
    (80,  255, 120),   # green
    (0,   0,   0),     # black (erase)
]

BRUSH_RADIUS = 3


class EtchApp(BaseApp):
    name          = 'IRIS Etch'
    description   = 'Draw on the world'
    pin_mode      = 'free'
    show_cursor   = True
    cap_hold_secs = 0.0

    def __init__(self):
        super().__init__()

        self._canvas = pygame.Surface((CANVAS_W, CANVAS_H))
        self._canvas.fill(BLACK)

        # IMU state
        self._imu_yaw    = 0.0
        self._imu_pitch  = 0.0
        self._origin_yaw = 0.0
        self._origin_pitch = 0.0

        # Drawing state
        self._drawing  = False
        self._last_cx  = None
        self._last_cy  = None
        self._color_idx = 0
        self._color    = COLORS[0]

        # Hand state
        self._hand_active = False
        self._hand_x      = 0.5
        self._hand_y      = 0.5

        # Cap draw state — set by kernel each frame
        self._cap_draw = False

        # Fonts
        self._font     = pygame.font.Font(_MONO_BOLD, 14)
        self._font_big = pygame.font.Font(_MONO_BOLD, 18)

        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)
        self._name_surf = fn.render('IRIS Etch', True, WHITE)
        self._icon_surf = fi.render('ET',        True, WHITE)

        os.makedirs('assets/media', exist_ok=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def launch(self):
        # Capture IMU position at launch as canvas origin
        self._origin_yaw   = self._imu_yaw
        self._origin_pitch = self._imu_pitch

    def close(self):
        self._save()
        super().close()

    # ── Coordinate mapping ────────────────────────────────────────────────────

    def _viewport_offset(self):
        # Delta from launch position — same math as mirage menu
        dyaw   = self._imu_yaw   - self._origin_yaw
        dpitch = self._imu_pitch - self._origin_pitch
        # Wrap yaw delta to -180..180
        dyaw = (dyaw + 180) % 360 - 180
        cx = int(CANVAS_W // 2 + dyaw   * PX_PER_YAW)
        cy = int(CANVAS_H // 2 + dpitch * PX_PER_PITCH)
        ox = (cx - WIDTH  // 2) % CANVAS_W
        oy = cy - HEIGHT // 2
        oy = max(0, min(CANVAS_H - HEIGHT, oy))
        return ox, oy

    # ── Kernel hooks ──────────────────────────────────────────────────────────

    def on_imu(self, imu_state, hand=None):
        self._imu_yaw   = imu_state.yaw
        self._imu_pitch = imu_state.pitch

        if hand and hand.active:
            self._hand_active = True
            self._hand_x      = hand.x
            self._hand_y      = hand.y
        else:
            self._hand_active = False
            self._hand_x      = 0.5
            self._hand_y      = 0.5

        # Draw if cap held or pinch
        pinch = getattr(hand, 'pinch', False) if hand else False
        if self._cap_draw or pinch:
            self._do_draw()
        else:
            self._last_cx = None
            self._last_cy = None
            self._drawing = False

    def on_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                self._cycle_color(1)
            elif event.key == pygame.K_DELETE:
                self._canvas.fill(BLACK)

    def on_gesture(self, gesture):
        pass

    def _handle_beta(self):
        if not self._cap_draw:
            self._cycle_color(1)

    def _handle_alpha(self):
        self._cycle_color(-1)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _do_draw(self):
        ox, oy = self._viewport_offset()
        sx = int(self._hand_x * WIDTH)
        sy = int(self._hand_y * HEIGHT)
        cx = (ox + sx) % CANVAS_W
        cy = max(0, min(CANVAS_H - 1, oy + sy))

        if self._last_cx is not None:
            # Skip line if crossing wraparound seam
            if abs(cx - self._last_cx) < CANVAS_W // 2:
                pygame.draw.line(self._canvas, self._color,
                                 (self._last_cx, self._last_cy),
                                 (cx, cy), BRUSH_RADIUS * 2)
            else:
                pygame.draw.circle(self._canvas, self._color,
                                   (cx, cy), BRUSH_RADIUS)
        else:
            pygame.draw.circle(self._canvas, self._color,
                               (cx, cy), BRUSH_RADIUS)

        self._last_cx = cx
        self._last_cy = cy
        self._drawing = True

    def _cycle_color(self, direction=1):
        self._color_idx = (self._color_idx + direction) % len(COLORS)
        self._color     = COLORS[self._color_idx]

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        try:
            ts   = time.strftime('%Y%m%d_%H%M%S')
            path = f'assets/media/etch_{ts}.png'
            pygame.image.save(self._canvas, path)
            print(f'[Etch] Saved to {path}')
        except Exception as e:
            print(f'[Etch] Save failed: {e}')

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_fullscreen(self, surface):
        ox, oy = self._viewport_offset()
        right_edge = ox + WIDTH

        if right_edge <= CANVAS_W:
            surface.blit(self._canvas, (0, 0),
                         pygame.Rect(ox, oy, WIDTH, HEIGHT))
        else:
            first_w  = CANVAS_W - ox
            second_w = WIDTH - first_w
            surface.blit(self._canvas, (0,       0),
                         pygame.Rect(ox, oy, first_w,  HEIGHT))
            surface.blit(self._canvas, (first_w, 0),
                         pygame.Rect(0,  oy, second_w, HEIGHT))

        # HUD
        pygame.draw.circle(surface, self._color, (20, 20), 8)
        pygame.draw.circle(surface, WHITE,        (20, 20), 8, 1)
        label = self._font.render(
            f'{self._color_idx + 1}/{len(COLORS)}', True, WHITE)
        surface.blit(label, (34, 13))

        if self._drawing:
            dot = self._font.render('●', True, self._color)
            surface.blit(dot, (WIDTH - 20, 10))

        hint = self._font_big.render(
            'hold β=draw  β/α=color', True, (60, 60, 60))
        surface.blit(hint,
                     (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 24))

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx,
                                       centery=rect.centery - 8)
        surface.blit(self._name_surf, nr)
        x = rect.centerx - (len(COLORS) * 14) // 2
        for c in COLORS:
            pygame.draw.circle(surface, c, (x, rect.centery + 14), 5)
            x += 14
