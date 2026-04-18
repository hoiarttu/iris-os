"""
apps/etch_app.py — IRIS Etch
─────────────────────────────────────────────────────────────────────────────
A world-space drawing app. The canvas spans 360° azimuth × ~120° pitch.
IMU pans the viewport. Pinch draws. The canvas lives in yaw/pitch space
exactly like the mirage menu — same coordinate principle.

Canvas mapping:
  canvas_x = (yaw / 360.0) * CANVAS_W          (wraps)
  canvas_y = ((pitch + 60) / 120.0) * CANVAS_H  (clamped)

Viewport is screen-sized window into canvas, blitted with wraparound at seam.

Input:
  Pinch held      → draw at current IMU position
  Pinch release   → lift pen
  Beta cap        → cycle color
  Alpha cap held  → clear canvas (via on_gesture from kernel)
  Fist + pull     → home (system handles)

Save on close → assets/media/etch_<timestamp>.png
"""

import os, time, math
import pygame
from apps.base_app import BaseApp
from core.display import WIDTH, HEIGHT, BLACK, WHITE

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'

# ── Canvas config ─────────────────────────────────────────────────────────────

CANVAS_W    = 2048   # pixels representing 360° yaw
CANVAS_H    = 2048   # pixels representing 120° pitch (-60 to +60)
PITCH_RANGE = 120.0  # degrees total
PITCH_MIN   = -60.0

# ── Palette ───────────────────────────────────────────────────────────────────

COLORS = [
    (255, 255, 255),   # white
    (80,  220, 255),   # IRIS cyan
    (255,  80,  80),   # red
    (255, 220,  50),   # yellow
    (80,  255, 120),   # green
    (0,   0,   0),     # black (erase)
]

BRUSH_RADIUS = 3   # pixels on canvas


class EtchApp(BaseApp):
    name          = 'IRIS Etch'
    description   = 'Draw on the world'
    pin_mode      = 'free'    # kernel must not offset canvas — we do our own IMU mapping
    show_cursor   = True
    cap_hold_secs = 0.0

    def __init__(self):
        super().__init__()

        # Canvas — world-space pixel buffer
        self._canvas    = pygame.Surface((CANVAS_W, CANVAS_H))
        self._canvas.fill(BLACK)

        # Viewport state
        self._imu_yaw   = 0.0
        self._imu_pitch = 0.0

        # Drawing state
        self._drawing   = False
        self._last_cx   = None   # last canvas-space draw position
        self._last_cy   = None
        self._color_idx = 0
        self._color     = COLORS[0]

        # Hand override
        self._hand_active = False
        self._hand_x      = 0.5
        self._hand_y      = 0.5

        # Cap draw state — set by kernel each frame
        self._cap_draw    = False   # beta held = draw

        # UI fonts
        self._font      = pygame.font.Font(_MONO_BOLD, 14)
        self._font_big  = pygame.font.Font(_MONO_BOLD, 22)

        # Icon/widget surfs
        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)
        self._name_surf = fn.render('IRIS Etch', True, WHITE)
        self._icon_surf = fi.render('ET',        True, WHITE)

        os.makedirs('assets/media', exist_ok=True)

    # ── Coordinate mapping ────────────────────────────────────────────────────

    def _imu_to_canvas(self, yaw, pitch):
        """Convert IMU yaw/pitch to canvas pixel coordinates."""
        cx = int((yaw % 360.0) / 360.0 * CANVAS_W)
        cy = int((pitch - PITCH_MIN) / PITCH_RANGE * CANVAS_H)
        cy = max(0, min(CANVAS_H - 1, cy))
        return cx, cy

    def _canvas_viewport_offset(self, yaw, pitch):
        """
        Top-left corner of the screen-sized viewport into the canvas.
        Canvas x wraps, y is clamped.
        """
        cx, cy = self._imu_to_canvas(yaw, pitch)
        # Centre the viewport on the IMU position
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
            # Pinch or cap held = draw
            pinch = getattr(hand, 'pinch', False)
            if pinch or self._cap_draw:
                self._do_draw_hand()
            else:
                self._last_cx = None
                self._last_cy = None
                self._drawing = False
        else:
            self._hand_active = False
            # Cap draw still works without hand — draws at screen center
            if self._cap_draw:
                self._hand_x = 0.5
                self._hand_y = 0.5
                self._do_draw_hand()
            else:
                self._last_cx = None
                self._last_cy = None
                self._drawing = False

    def on_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                self._cycle_color()
            elif event.key == pygame.K_DELETE:
                self._clear()

    def on_gesture(self, gesture):
        if gesture == 'pinch':
            pass   # pinch draw handled in on_imu via hand.pinch flag

    def _handle_beta(self):
        """Beta tap — cycle color forward (only if not drawing)."""
        if not self._cap_draw:
            self._cycle_color(1)

    def _handle_alpha(self):
        """Alpha tap — cycle color backward."""
        self._cycle_color(-1)

    def _handle_alpha_held(self):
        """Called by kernel alpha cap hold — clear canvas."""
        self._clear()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _do_draw_hand(self):
        """
        Draw at hand position mapped into canvas space via current viewport.
        Hand x/y (0-1 normalised screen) → screen pixel → canvas pixel.
        """
        ox, oy = self._canvas_viewport_offset(self._imu_yaw, self._imu_pitch)

        # Screen position of hand
        sx = int(self._hand_x * WIDTH)
        sy = int(self._hand_y * HEIGHT)

        # Canvas position = viewport offset + screen position (with x wraparound)
        cx = (ox + sx) % CANVAS_W
        cy = oy + sy
        cy = max(0, min(CANVAS_H - 1, cy))

        if self._last_cx is not None:
            # Skip line if crossing the wraparound seam
            if abs(cx - self._last_cx) < CANVAS_W // 2:
                pygame.draw.line(self._canvas, self._color,
                                 (self._last_cx, self._last_cy),
                                 (cx, cy), BRUSH_RADIUS * 2)
            else:
                # Seam crossing — just draw a dot at new position
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

    def _clear(self):
        self._canvas.fill(BLACK)
        self._last_cx = None
        self._last_cy = None
        print('[Etch] Canvas cleared')

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        try:
            import PIL.Image
            data     = pygame.image.tostring(self._canvas, 'RGB')
            img      = PIL.Image.frombytes('RGB', (CANVAS_W, CANVAS_H), data)
            ts       = time.strftime('%Y%m%d_%H%M%S')
            path     = f'assets/media/etch_{ts}.png'
            img.save(path)
            print(f'[Etch] Saved to {path}')
        except ImportError:
            # PIL not available — fallback to pygame save
            ts   = time.strftime('%Y%m%d_%H%M%S')
            path = f'assets/media/etch_{ts}.png'
            pygame.image.save(self._canvas, path)
            print(f'[Etch] Saved (pygame) to {path}')
        except Exception as e:
            print(f'[Etch] Save failed: {e}')

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self):
        self._save()
        super().close()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw_fullscreen(self, surface):
        """
        Blit the visible viewport of the world canvas onto surface.
        Handles wraparound at the yaw=0/360 seam.
        """
        ox, oy = self._canvas_viewport_offset(self._imu_yaw, self._imu_pitch)

        right_edge = ox + WIDTH

        if right_edge <= CANVAS_W:
            # No wraparound — simple blit
            src_rect = pygame.Rect(ox, oy, WIDTH, HEIGHT)
            surface.blit(self._canvas, (0, 0), src_rect)
        else:
            # Viewport straddles the seam — two blits
            first_w  = CANVAS_W - ox
            second_w = WIDTH - first_w

            src_left  = pygame.Rect(ox,  oy, first_w,  HEIGHT)
            src_right = pygame.Rect(0,   oy, second_w, HEIGHT)

            surface.blit(self._canvas, (0,       0), src_left)
            surface.blit(self._canvas, (first_w, 0), src_right)

        # ── HUD ───────────────────────────────────────────────────────────────
        # Color swatch
        pygame.draw.circle(surface, self._color, (20, 20), 8)
        pygame.draw.circle(surface, WHITE,        (20, 20), 8, 1)

        # Color name / index
        label = self._font.render(
            f'{self._color_idx + 1}/{len(COLORS)}', True, WHITE)
        surface.blit(label, (34, 13))

        # Drawing indicator
        if self._drawing:
            dot = self._font.render('●', True, self._color)
            surface.blit(dot, (WIDTH - 20, 10))

        # Instructions
        hint = self._font_big.render(
            'hold β=draw  β/α=color  black=last', True, (60, 60, 60))
        surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 24))

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx,
                                       centery=rect.centery - 8)
        surface.blit(self._name_surf, nr)
        # Small color dots as preview
        x = rect.centerx - (len(COLORS) * 14) // 2
        for c in COLORS:
            pygame.draw.circle(surface, c, (x, rect.centery + 14), 5)
            x += 14
