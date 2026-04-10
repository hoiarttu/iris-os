"""
components/mirage_manager.py — Scene manager
─────────────────────────────────────────────────────────────────────────────
Draws hex menu, handles dwell selection, draws cursors.
Hand cursor replaces pointer when hand tracker is active.
"""

import os, math, json
import pygame
import platform

from core.display       import canvas, CENTER, WIDTH, HEIGHT, BLACK, WHITE, ACCENT
from core.geometry      import angle_diff, lerp_angle
from components.hexmenu import HexMenu
from components.draw    import draw_hex_border, draw_pointer
import pygame as _pg
from apps.clock_app     import ClockApp

_CURSOR_SURF = None
def _get_cursor():
    global _CURSOR_SURF
    if _CURSOR_SURF is None:
        try:
            img = _pg.image.load('./assets/LOGO.png').convert_alpha()
            img = _pg.transform.smoothscale(img, (36, 36))
            img.set_alpha(128)
            _CURSOR_SURF = img
        except Exception:
            _CURSOR_SURF = False
    return _CURSOR_SURF
from apps.placeholder_app import PlaceholderApp
from apps.system_app    import SystemApp

# ── Tuning ────────────────────────────────────────────────────────────────────

SMOOTH_T       = 0.15
DWELL_SECS     = 0.6
DEV_NO_DWELL   = True   # set False for production
PX_PER_DEGREE_YAW   = 28
PX_PER_DEGREE_PITCH = 24

# ── Default apps ──────────────────────────────────────────────────────────────

def default_apps():
    return [
        None,
        PlaceholderApp('Navigation'),
        SystemApp(),
        PlaceholderApp('Media'),
        PlaceholderApp('Settings'),
        PlaceholderApp('Comms'),
        PlaceholderApp('Vision'),
    ]

# ── Mirage ────────────────────────────────────────────────────────────────────

class Mirage:
    __slots__ = ('azimuth', 'elevation', 'type', 'apps', 'visible')

    def __init__(self, azimuth, elevation, mtype='hexmenu', apps=None):
        self.azimuth   = float(azimuth)
        self.elevation = float(elevation)
        self.type      = mtype
        self.apps      = apps if apps is not None else default_apps()
        self.visible   = False

    def to_dict(self):
        return {'azimuth': self.azimuth, 'elevation': self.elevation, 'type': self.type}

# ── Scene manager ─────────────────────────────────────────────────────────────

class MirageManager:

    def __init__(self, path, os_ref=None):
        self.path          = path
        self.os_ref        = os_ref
        self.mirages       = []
        self.hex_menu      = HexMenu(radius=70)
        self._smooth_yaw   = 0.0
        self._dwell        = {}
        self._dwell_key    = None
        self._clock_app    = ClockApp()
        self._focused_app  = self._clock_app
        self._last_focused = None
        self._sel_mirage   = None
        self._sel_idx      = None
        self._spawn_t      = 0.0
        self._spawning     = True
        self._SPAWN_DUR    = 1.2
        self._zoom_t       = {}
        self.load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                raw = json.load(f)
            self.mirages = []
            for e in raw:
                try:
                    self.mirages.append(Mirage(e['azimuth'], e['elevation'], e.get('type','hexmenu')))
                except Exception as ex:
                    print(f'[Scene] Skipped: {ex}')
        else:
            self.mirages = [Mirage(0.0, 0.0)]
        print(f'[Scene] {len(self.mirages)} mirage(s) loaded')

    def save(self):
        with open(self.path, 'w') as f:
            json.dump([m.to_dict() for m in self.mirages], f, indent=2)
        print(f'[Scene] Saved {len(self.mirages)} mirage(s)')

    def add(self, azimuth, elevation, mtype='hexmenu'):
        m = Mirage(azimuth, elevation, mtype)
        self.mirages.append(m)
        return m

    def remove(self, idx):
        if self.mirages:
            self.mirages.pop(idx)

    def trigger_spawn(self):
        self._spawn_t = 0.02
        self._spawning = True
        print('[Scene] trigger_spawn called')

    def confirm_selection(self, os_ref):
        if self._sel_mirage and self._sel_idx is not None:
            app = self._sel_mirage.apps[self._sel_idx]
            if app and os_ref:
                os_ref.launch_app(app)

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, imu_state, dt, hand=None):
        self._clock_app.update(dt)
        self._smooth_yaw = lerp_angle(self._smooth_yaw, imu_state.yaw, SMOOTH_T)

        if self._spawning:
            is_pi = "raspberrypi" in platform.node().lower()

            if self._spawn_t > 0.01 or (not is_pi) or os.path.exists('/tmp/iris_boot_done'):
                self._spawn_t += dt
                if self._spawn_t >= self._SPAWN_DUR:
                    self._spawning = False

        new_focused    = None
        new_sel_mirage = None
        new_sel_idx    = None
        widget_pos     = CENTER

        # Cursor position — hand if active, else screen centre
        if hand and hand.active:
            cursor = (int(hand.x * WIDTH), int(hand.y * HEIGHT))
        else:
            cursor = CENTER

        for m in self.mirages:
            m.visible = True
            for app in m.apps:
                if app:
                    app.update(dt)

            if m.type == 'hexmenu':
                sel, cpt0 = self._render_hexmenu(m, imu_state, dt, cursor)
                if cpt0 is not None:
                    widget_pos = cpt0
                if sel is not None:
                    new_focused    = m.apps[sel]
                    new_sel_mirage = m
                    new_sel_idx    = sel

        # Focus / blur
        if new_focused != self._last_focused:
            if self._last_focused:
                self._last_focused.on_blur()
            if new_focused:
                new_focused.on_focus()
            self._last_focused = new_focused

        self._sel_mirage  = new_sel_mirage
        self._sel_idx     = new_sel_idx
        self._focused_app = new_focused if new_focused else self._clock_app

        self._draw_centre_widget(widget_pos)

        # Draw cursor
        if hand and hand.active:
            self._draw_hand_cursor(cursor, hand.pinch)
        else:
            cur = _get_cursor()
            if cur:
                r = cur.get_rect(center=CENTER)
                canvas.blit(cur, r)
            else:
                draw_pointer(canvas, CENTER)



        # Dwell
        dwell_key = (id(new_sel_mirage), new_sel_idx) if new_sel_mirage else None
        if dwell_key:
            self._dwell[dwell_key] = self._dwell.get(dwell_key, 0.0) + dt
            if not DEV_NO_DWELL and self._dwell[dwell_key] >= DWELL_SECS:
                self.confirm_selection(self.os_ref)
                del self._dwell[dwell_key]
        else:
            if self._dwell_key:
                self._dwell.pop(self._dwell_key, None)
        self._dwell_key = dwell_key

    # ── Centre widget ─────────────────────────────────────────────────────────

    def _draw_centre_widget(self, pos):
        w, h = 200, 140
        rect = pygame.Rect(pos[0] - w//2, pos[1] - h//2, w, h)
        self._focused_app.draw_widget(canvas, rect)

    # ── Hand cursor ───────────────────────────────────────────────────────────

    def _draw_hand_cursor(self, pos, pinch):
        color = ACCENT if pinch else WHITE
        pygame.draw.circle(canvas, color, pos, 6 if pinch else 4)
        pygame.draw.circle(canvas, BLACK, pos, 6 if pinch else 4, 1)

    # ── Hex rendering ─────────────────────────────────────────────────────────

    def _render_hexmenu(self, mirage, imu_state, dt, cursor):
        import math
        yaw   = imu_state.yaw
        pitch = imu_state.pitch
        roll  = imu_state.roll

        yaw_diff = angle_diff(yaw, mirage.azimuth)
        yaw_sign = 1 if ((yaw - mirage.azimuth + 360) % 360) < 180 else -1
        # Raw displacement
        dx = -yaw_sign * yaw_diff * PX_PER_DEGREE_YAW
        dy = pitch * PX_PER_DEGREE_PITCH
        # Rotate displacement by roll angle
        roll_rad = math.radians(imu_state.roll)
        cr, sr = math.cos(roll_rad), math.sin(roll_rad)
        cx = int(CENTER[0] + cr * dx - sr * dy)
        cy = int(CENTER[1] + sr * dx + cr * dy)

        polys   = self.hex_menu.get_rotated_polygons(1.0, 0.0, cx, cy)
        centers = self.hex_menu.get_center_points(1.0, 0.0, cx, cy)
        sel     = self.hex_menu.get_highlight(polys[1:], centers[1:], cursor)
        if sel is not None:
            sel += 1

        # Draw unfocused hexes first, focused on top
        draw_order = [i for i in range(1, len(polys)) if i != sel]
        if sel is not None:
            draw_order.append(sel)

        for i in draw_order:
            poly, cpt = polys[i], centers[i]
            focused = (i == sel)

            if focused:
                self._zoom_t[i] = min(1.0, self._zoom_t.get(i, 0.0) + dt * 4)
            else:
                self._zoom_t[i] = max(0.0, self._zoom_t.get(i, 0.0) - dt * 4)
            zt = self._zoom_t.get(i, 0.0)
            zoom = 1.0 + 0.12 * zt
            zpoly = [
                (int(cpt[0] + (px - cpt[0]) * zoom),
                 int(cpt[1] + (py - cpt[1]) * zoom))
                for px, py in poly
            ]
            draw_hex_border(canvas, zpoly, focused)
            if i < len(mirage.apps) and mirage.apps[i]:
                mirage.apps[i].draw_icon(canvas, cpt, self.hex_menu.radius * 0.5)

        return sel, centers[0]

    @staticmethod
    def _draw_dwell_ring(surface, center, frac):
        r    = 24
        rect = pygame.Rect(center[0]-r, center[1]-r, r*2, r*2)
        pygame.draw.arc(surface, ACCENT, rect,
                        math.pi/2, math.pi/2 + math.pi*2*frac, 2)
