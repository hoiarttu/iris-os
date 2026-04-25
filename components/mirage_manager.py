"""
components/mirage_manager.py — Scene manager
─────────────────────────────────────────────────────────────────────────────
Draws hex menu, handles dwell/pinch selection, draws universal cursor.
Grab repositioning: on_grab_start/on_grab_pin/on_grab_cancel.
"""

import os, math, json, platform
import pygame

from core.display       import canvas, CENTER, WIDTH, HEIGHT, BLACK, WHITE, ACCENT
from core.geometry      import angle_diff, lerp_angle, lerp
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
            img.set_alpha(200)
            _CURSOR_SURF = img
        except Exception:
            _CURSOR_SURF = False
    return _CURSOR_SURF

from apps.placeholder_app import PlaceholderApp
from apps.system_app      import SystemApp
from apps.testgame_app    import TestgameApp
from apps.etch_app        import EtchApp
from apps.settings_app    import SettingsApp
from apps.stocks_app      import StockApp

# ── Tuning ────────────────────────────────────────────────────────────────────

SMOOTH_T            = 0.01
DWELL_SECS          = 0.6
DEV_NO_DWELL        = True
PX_PER_DEGREE_YAW   = 32
PX_PER_DEGREE_PITCH = 32
CURSOR_SMOOTH       = 0.35   # render-side lerp (lower = more smoothing)

# ── Default apps ──────────────────────────────────────────────────────────────

def default_apps():
    return [
        None,
        TestgameApp(),
        SystemApp(),
        EtchApp(),
        SettingsApp(),
        PlaceholderApp('Comms'),
        StockApp(),
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
        return {'azimuth': self.azimuth,
                'elevation': self.elevation,
                'type': self.type}

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
        self._spawn_forced = False
        self._SPAWN_DUR    = 2.0
        self._spawn_frames = 0   # frame counter — must see N frames
        self._zoom_t       = {}

        # Render-side cursor smoothing
        self._cursor_sx    = float(CENTER[0])
        self._cursor_sy    = float(CENTER[1])

        # Grab repositioning state
        self._grab_mirage      = None   # mirage being dragged
        self._grab_origin_az   = 0.0    # azimuth before grab started
        self._grab_origin_el   = 0.0
        self._grab_hand_origin = None   # (x, y) when grab started

        self.load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def reset_to_default(self):
        """Reset all mirages to default position — call before shutdown/reboot."""
        self.mirages = [Mirage(0.0, 0.0)]
        print('[Scene] Mirages reset to default')

    def load(self):
        self.mirages = []
        try:
            if os.path.exists(self.path):
                with open(self.path) as f:
                    raw = json.load(f)
                for e in raw:
                    try:
                        self.mirages.append(
                            Mirage(e['azimuth'], e['elevation'],
                                   e.get('type', 'hexmenu')))
                    except Exception as ex:
                        print(f'[Scene] Skipped: {ex}')
        except Exception as ex:
            print(f'[Scene] Failed to load mirages.json ({ex}) — using default')
        if not self.mirages:
            self.mirages = [Mirage(0.0, 0.0)]
            self.save()   # write clean default immediately
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
        self._spawn_t      = 0.0
        self._spawn_frames = 0
        self._spawning     = True
        self._spawn_forced = True

    def confirm_selection(self, os_ref):
        if self._spawning:
            return   # block selection during spawn animation
        if self._sel_mirage and self._sel_idx is not None:
            app = self._sel_mirage.apps[self._sel_idx]
            if app and os_ref:
                if os_ref._active_app is app:
                    return   # already running — ignore
                os_ref.launch_app(app, mirage=self._sel_mirage)

    # ── Grab repositioning ────────────────────────────────────────────────────

    def on_grab_start(self, hand):
        """Fist onset — grab the nearest/focused mirage."""
        if not self.mirages:
            return
        # Grab the currently focused mirage (first one for now)
        self._grab_mirage      = self.mirages[0]
        self._grab_origin_az   = self._grab_mirage.azimuth
        self._grab_origin_el   = self._grab_mirage.elevation
        self._grab_hand_origin = (hand.x, hand.y) if hand and hand.active else None
        print('[Scene] Grab started')

    def on_grab_pin(self, hand):
        """Fist + push — pin mirage at current hand-dragged position."""
        if self._grab_mirage:
            self.save()
            print(f'[Scene] Pinned at az={self._grab_mirage.azimuth:.1f}')
        self._grab_mirage = None

    def on_grab_cancel(self):
        """Fist released without push/pull — float back to origin."""
        if self._grab_mirage and self._grab_hand_origin:
            self._grab_mirage.azimuth   = self._grab_origin_az
            self._grab_mirage.elevation = self._grab_origin_el
            print('[Scene] Grab cancelled — floating back')
        self._grab_mirage = None

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, imu_state, dt, hand=None):
        self._clock_app.update(dt)
        self._smooth_yaw = lerp_angle(self._smooth_yaw, imu_state.yaw, SMOOTH_T)

        if self._spawning:
            # Cap dt to avoid single huge frame skipping animation
            self._spawn_t += min(dt, 0.05)
            self._spawn_frames += 1
            # Must run for both min duration AND min frames
            if self._spawn_t >= self._SPAWN_DUR and self._spawn_frames >= 30:
                self._spawning = False

        # Live drag — mirage follows hand while grabbed
        if self._grab_mirage and self._grab_hand_origin and hand and hand.active:
            dx_norm = hand.x - self._grab_hand_origin[0]
            # Map hand x delta to azimuth delta (rough calibration)
            self._grab_mirage.azimuth = (
                self._grab_origin_az - dx_norm * 90.0) % 360.0

        # ── Cursor target ─────────────────────────────────────────────────────
        if hand and hand.active:
            raw_cx = hand.x * WIDTH
            raw_cy = hand.y * HEIGHT
        else:
            raw_cx = float(CENTER[0])
            raw_cy = float(CENTER[1])

        # Render-side smoothing
        self._cursor_sx += (raw_cx - self._cursor_sx) * CURSOR_SMOOTH
        self._cursor_sy += (raw_cy - self._cursor_sy) * CURSOR_SMOOTH
        cursor_pos = (int(self._cursor_sx), int(self._cursor_sy))

        # ── Mirage rendering ──────────────────────────────────────────────────
        new_focused    = None
        new_sel_mirage = None
        new_sel_idx    = None
        widget_pos     = CENTER

        for m in self.mirages:
            m.visible = True
            for app in m.apps:
                if app:
                    app.update(dt)

            if m.type == 'hexmenu':
                sel, cpt0 = self._render_hexmenu(m, imu_state, dt, cursor_pos)
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

        # ── Universal cursor ──────────────────────────────────────────────────
        cur = _get_cursor()
        if cur:
            r = cur.get_rect(center=cursor_pos)
            canvas.blit(cur, r)
        else:
            draw_pointer(canvas, cursor_pos)

        # Pinch ring indicator
        if hand and hand.active and getattr(hand, 'pinch', False):
            pygame.draw.circle(canvas, ACCENT, cursor_pos, 8, 2)

        # Grab indicator
        if hand and hand.active and getattr(hand, 'fist', False):
            pygame.draw.circle(canvas, (255, 180, 0), cursor_pos, 10, 2)

        # ── Dwell ─────────────────────────────────────────────────────────────
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
        rect = pygame.Rect(pos[0] - w // 2, pos[1] - h // 2, w, h)
        self._focused_app.draw_widget(canvas, rect)

    # ── Hex rendering ─────────────────────────────────────────────────────────

    def _render_hexmenu(self, mirage, imu_state, dt, cursor):
        yaw   = imu_state.yaw
        pitch = imu_state.pitch

        yaw_diff = angle_diff(yaw, mirage.azimuth)
        yaw_sign = 1 if ((yaw - mirage.azimuth + 360) % 360) < 180 else -1
        dx = -yaw_sign * yaw_diff * PX_PER_DEGREE_YAW
        dy = pitch * PX_PER_DEGREE_PITCH

        roll_rad = math.radians(imu_state.roll)
        cr, sr   = math.cos(roll_rad), math.sin(roll_rad)
        cx = int(CENTER[0] + cr * dx - sr * dy)
        cy = int(CENTER[1] + sr * dx + cr * dy)

        polys   = self.hex_menu.get_rotated_polygons(1.0, 0.0, cx, cy)
        centers = self.hex_menu.get_center_points(1.0, 0.0, cx, cy)
        sel     = self.hex_menu.get_highlight(polys[1:], centers[1:], cursor)
        if sel is not None:
            sel += 1

        draw_order = [i for i in range(1, len(polys)) if i != sel]
        if sel is not None:
            draw_order.append(sel)

        for i in draw_order:
            poly, cpt = polys[i], centers[i]
            focused   = (i == sel)

            if focused:
                self._zoom_t[i] = min(1.0, self._zoom_t.get(i, 0.0) + dt * 4)
            else:
                self._zoom_t[i] = max(0.0, self._zoom_t.get(i, 0.0) - dt * 4)
            zt   = self._zoom_t.get(i, 0.0)
            zoom = 1.0 + 0.12 * zt
            zpoly = [
                (int(cpt[0] + (px - cpt[0]) * zoom),
                 int(cpt[1] + (py - cpt[1]) * zoom))
                for px, py in poly
            ]
            draw_hex_border(canvas, zpoly, focused)
            if i < len(mirage.apps) and mirage.apps[i]:
                mirage.apps[i].draw_icon(canvas, cpt,
                                          self.hex_menu.radius * 0.5)

        return sel, centers[0]

    @staticmethod
    def _draw_dwell_ring(surface, center, frac):
        r    = 24
        rect = pygame.Rect(center[0] - r, center[1] - r, r * 2, r * 2)
        pygame.draw.arc(surface, ACCENT, rect,
                        math.pi / 2, math.pi / 2 + math.pi * 2 * frac, 2)
