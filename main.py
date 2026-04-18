"""
main.py — IRIS OS kernel
─────────────────────────────────────────────────────────────────────────────
State machine:
  MENU    hex menu visible, IMU shifts it, gestures/caps select
  APP     app owns full screen, pinned to mirage origin by default
  OVERLAY app running but menu briefly visible

Pin modes (per app):
  'pinned'  canvas offset by IMU delta from mirage azimuth/elevation
            looking away slides app off screen into black
  'free'    always centred, ignores IMU
  'world'   app handles IMU itself via on_imu()

Exit — always available regardless of app:
  Both caps hold 1.5s  → pin mirage + home
  Fist + pull          → home

Cap navigation (never exits app):
  Alpha tap  → back/previous (in-app, per cap_hold_secs)
  Beta tap   → confirm/select (per cap_hold_secs)

Keyboard shortcuts (dev):
  ESC         quit
  ←/→/↑/↓    mock IMU
  SPACE       pin/unpin
  A           add mirage
  D           remove last mirage
  R           reset IMU
  S           save scene
  BACKSPACE   home (both caps)
  Z           alpha cap (back)
  X           beta cap (confirm)
"""

import sys, signal, math as _m
import pygame

from core.display          import (screen, canvas, clock, CENTER,
                                    WIDTH, HEIGHT, FPS, BLACK, WHITE, ACCENT)
from core.mpu6050_handler  import Mpu6050Handler
from core.input_handler    import InputHandler, EVT_HOME, EVT_CONFIRM, EVT_BACK
from core.hand_client      import HandClient
from core.gesture          import GestureDetector
from core.geometry         import ease_out
from components.mirage_manager import MirageManager

# ── Config ────────────────────────────────────────────────────────────────────

SCENE_PATH      = 'mirages.json'
IMU_BUS         = 11
IMU_YAW_AXIS    = 'x'
IMU_PITCH_AXIS  = 'z'
IMU_ROLL_AXIS   = 'y'
IMU_ALPHA       = 0.98
IMU_CAL_SAMPLES = 150

# Pixels per degree for pinned app IMU offset (same as hex menu)
PX_PER_DEGREE_YAW   = 28
PX_PER_DEGREE_PITCH = 24

# ── States ────────────────────────────────────────────────────────────────────

STATE_MENU    = 'menu'
STATE_APP     = 'app'
STATE_OVERLAY = 'overlay'


class IrisOS:

    def __init__(self):
        self.state   = STATE_MENU
        self._pinned = False

        self.imu = Mpu6050Handler(
            address    = 0x68,
            bus        = IMU_BUS,
            yaw_axis   = IMU_YAW_AXIS,
            pitch_axis = IMU_PITCH_AXIS,
            roll_axis  = IMU_ROLL_AXIS,
            alpha      = IMU_ALPHA,
        )

        self.input    = InputHandler()
        self.hand     = HandClient()
        self.gestures = GestureDetector()

        self.scene = MirageManager(
            path   = SCENE_PATH,
            os_ref = self,
        )

        self._running       = False
        self._active_app    = None
        self._active_mirage = None   # mirage the active app was launched from

        # Both-caps state
        self._both_held  = False
        self._both_since = 0.0

        # Single cap hold tracking (per-app duration)
        self._alpha_held  = False
        self._alpha_since = 0.0
        self._beta_held   = False
        self._beta_since  = 0.0

        # Grab state (for mirage/app repositioning)
        self._grab_active  = False
        self._grab_subject = None   # mirage being dragged

        # Pin animation
        self._pin_anim = 0.0
        self._PIN_DUR  = 0.4

        signal.signal(signal.SIGTERM, self._handle_sigterm)

        self._dlp_timer = 30.0
        try:
            import smbus2
            self._dlp_bus = smbus2.SMBus(11)
        except Exception:
            self._dlp_bus = None

        _f = pygame.font.Font('assets/fonts/Rajdhani-Regular.ttf', 11)
        self._home_hint_surf = _f.render('both caps = home', True, (60, 60, 60))

    def boot(self):
        if IMU_CAL_SAMPLES > 0:
            self.imu.calibrate(IMU_CAL_SAMPLES)
        print('[IRIS] Boot complete.')

    def run(self):
        self._running = True
        while self._running:
            dt = clock.tick(FPS) / 1000.0

            # ── Collect events ────────────────────────────────────────────────
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(event.key)

            # Forward raw events to active app
            if self._active_app:
                for event in events:
                    self._active_app.on_event(event)

            # ── Hardware input ────────────────────────────────────────────────
            for cap_event in self.input.get_events():
                self._handle_cap(cap_event)

            imu_state = self.imu.update()
            self.hand.update()

            # ── Gesture detection ─────────────────────────────────────────────
            gesture_list = self.gestures.update(self.hand)
            for gesture in gesture_list:
                self._handle_gesture(gesture)

            # ── Both-caps hold logic (pin + home, unkillable) ─────────────────
            import time as _t
            both_now = self.input._alpha_held and self.input._beta_held
            if both_now and not self._both_held:
                self._both_held  = True
                self._both_since = _t.time()
            elif not both_now and self._both_held:
                held = _t.time() - self._both_since
                if held >= 1.5:
                    self._do_pin_and_home(imu_state)
                elif self.state == STATE_APP:
                    # Short both-tap in app = exit app
                    self.close_app()
                self._both_held = False
            elif both_now and self._both_held:
                # While held, freeze display to mirage pos
                # Also reset IMU backend so no drift accumulates
                if self.scene.mirages:
                    imu_state.yaw   = self.scene.mirages[0].azimuth
                    imu_state.pitch = 0.0
                    imu_state.roll  = 0.0
                    # Reset backend state to match so no snap on release
                    self.imu._backend._state.yaw   = imu_state.yaw
                    self.imu._backend._state.pitch  = 0.0
                    self.imu._backend._state.roll   = 0.0

            # ── Single cap hold tracking ──────────────────────────────────────
            # (alpha/beta fire via get_events, but hold dur enforced here)
            # Handled in _handle_cap via input_handler timing

            # ── DLP keepalive ─────────────────────────────────────────────────
            self._dlp_timer += dt
            if self._dlp_timer >= 30.0 and self._dlp_bus:
                self._dlp_timer = 0.0
                try:
                    self._dlp_bus.write_i2c_block_data(
                        0x1b, 0x0c, [0x00, 0x00, 0x00, 0x13])
                    self._dlp_bus.write_i2c_block_data(
                        0x1b, 0x0b, [0x00, 0x00, 0x00, 0x00])
                except Exception:
                    pass

            if self._pinned:
                imu_state.yaw   = 0.0
                imu_state.pitch = 0.0
                imu_state.roll  = 0.0

            canvas.fill(BLACK)

            # ── State rendering ───────────────────────────────────────────────
            if self.state == STATE_MENU:
                self.scene.update(imu_state, dt, self.hand)

            elif self.state == STATE_APP:
                app = self._active_app
                if app:
                    # Forward IMU to app every frame
                    app.on_imu(imu_state, self.hand)
                    app.update(dt)

                    if app.pin_mode == 'world':
                        # App handles everything — just draw
                        app.draw_fullscreen(canvas)

                    elif app.pin_mode == 'pinned' and self._active_mirage:
                        # Offset canvas by IMU delta from mirage origin
                        # Same math as hex menu positioning
                        from core.geometry import angle_diff
                        m        = self._active_mirage
                        yaw_diff = angle_diff(imu_state.yaw, m.azimuth)
                        yaw_sign = (1 if ((imu_state.yaw - m.azimuth + 360)
                                          % 360) < 180 else -1)
                        dx = -yaw_sign * yaw_diff * PX_PER_DEGREE_YAW
                        dy = imu_state.pitch * PX_PER_DEGREE_PITCH

                        roll_rad = _m.radians(imu_state.roll)
                        cr, sr   = _m.cos(roll_rad), _m.sin(roll_rad)
                        ox = int(cr * dx - sr * dy)
                        oy = int(sr * dx + cr * dy)

                        tmp = pygame.Surface((WIDTH, HEIGHT))
                        tmp.fill(BLACK)
                        app.draw_fullscreen(tmp)
                        # Blit offset — black shows through at edges
                        canvas.blit(tmp, (ox, oy))

                    else:   # 'free'
                        app.draw_fullscreen(canvas)

                    # Universal cursor unless app opts out
                    if app.show_cursor:
                        self._draw_universal_cursor()

                    self._draw_home_hint()

            elif self.state == STATE_OVERLAY:
                if self._active_app:
                    self._active_app.on_imu(imu_state, self.hand)
                    self._active_app.update(dt)
                    self._active_app.draw_fullscreen(canvas)
                self.scene.update(imu_state, dt, self.hand)

            # ── Pin animation pulse ───────────────────────────────────────────
            if self._pin_anim > 0.0:
                self._pin_anim -= dt
                t      = 1.0 - (self._pin_anim / self._PIN_DUR)
                scale  = 1.0 + 0.06 * _m.sin(t * _m.pi)
                pw     = max(1, int(WIDTH  * scale))
                ph     = max(1, int(HEIGHT * scale))
                pulsed = pygame.transform.scale(canvas, (pw, ph))
                prect  = pulsed.get_rect(center=(WIDTH // 2, HEIGHT // 2))
                screen.fill(BLACK)
                screen.blit(pulsed, prect)
                pygame.display.flip()
                continue

            # ── Roll correction + spawn composite ─────────────────────────────
            roll          = imu_state.roll if not self._pinned else 0.0
            screen_center = (WIDTH // 2, HEIGHT // 2)
            screen.fill(BLACK)

            if self.scene._spawning:
                t = ease_out(min(1.0, self.scene._spawn_t / self.scene._SPAWN_DUR))
                if t > 0.01:
                    sw     = max(1, int(WIDTH  * t))
                    sh     = max(1, int(HEIGHT * t))
                    scaled = pygame.transform.scale(canvas, (sw, sh))
                    scaled.set_alpha(int(255 * t))
                    rect   = scaled.get_rect(center=screen_center)
                    screen.blit(scaled, rect)
            elif abs(roll) > 1.0:
                rotated = pygame.transform.rotate(canvas, -roll)
                rect    = rotated.get_rect(center=screen_center)
                screen.blit(rotated, rect)
            else:
                rect = canvas.get_rect(center=screen_center)
                screen.blit(canvas, rect)

            pygame.display.flip()

        self._shutdown()

    # ── Universal cursor ──────────────────────────────────────────────────────

    def _draw_universal_cursor(self):
        from components.mirage_manager import _get_cursor
        from components.draw import draw_pointer
        if self.hand and self.hand.active:
            cx = int(self.hand.x * WIDTH)
            cy = int(self.hand.y * HEIGHT)
        else:
            cx, cy = CENTER
        cur = _get_cursor()
        if cur:
            r = cur.get_rect(center=(cx, cy))
            canvas.blit(cur, r)
        else:
            draw_pointer(canvas, (cx, cy))
        # Pinch ring
        if self.hand and self.hand.active and self.hand.pinch:
            pygame.draw.circle(canvas, ACCENT, (cx, cy), 8, 2)

    # ── Pin + home ────────────────────────────────────────────────────────────

    def _do_pin_and_home(self, imu_state):
        """Both-caps held 1.5s — pin mirage to current gaze, return to menu."""
        for m in self.scene.mirages:
            m.azimuth   = imu_state.yaw
            m.elevation = 0.0
        self.imu.reset()
        self.scene.save()
        self._pin_anim = self._PIN_DUR
        print('[IRIS] Mirage pinned')
        if self.state == STATE_APP:
            self.close_app()

    # ── App lifecycle ─────────────────────────────────────────────────────────

    def launch_app(self, app, mirage=None):
        if self._active_app is app:
            return   # already running — ignore
        if self._active_app:
            self._active_app.suspend()
        self._active_app    = app
        self._active_mirage = mirage
        self._active_app.launch()
        self.state = STATE_APP
        print(f'[IRIS] Launched: {app.name}  pin={app.pin_mode}')

    def close_app(self):
        if self._active_app:
            self._active_app.close()
            self._active_app    = None
            self._active_mirage = None
        self.state = STATE_MENU
        self.scene.trigger_spawn()
        print('[IRIS] Returned to menu.')

    # ── Gesture routing ───────────────────────────────────────────────────────

    def _handle_gesture(self, gesture: str):
        # System-level gestures handled by kernel
        if gesture == 'grab_pull':
            # Home from anywhere — unkillable
            if self.state == STATE_APP:
                self.close_app()
            return

        if gesture == 'grab_pin':
            # Pin mirage/app to hand position
            # Scene manager handles visual repositioning
            self.scene.on_grab_pin(self.hand)
            return

        if gesture == 'grab_cancel':
            self.scene.on_grab_cancel()
            return

        if gesture == 'grab':
            self.scene.on_grab_start(self.hand)

        if gesture == 'pinch' and self.state == STATE_MENU:
            self.scene.confirm_selection(self)
            return

        # Forward all gestures to active app too
        if self._active_app:
            self._active_app.on_gesture(gesture)

        # Swipe left/right = back/forward navigation in app
        if self.state == STATE_APP:
            if gesture == 'swipe_left':
                if self._active_app:
                    self._active_app.on_gesture('swipe_left')
            elif gesture == 'swipe_right':
                if self._active_app:
                    self._active_app.on_gesture('swipe_right')

    # ── Cap input ─────────────────────────────────────────────────────────────

    def _handle_cap(self, event):
        """
        Cap events from InputHandler.
        Alpha = back/navigate (never exits app).
        Beta  = confirm/select.
        Per-app cap_hold_secs enforced by InputHandler timing.
        """
        if event == EVT_BACK:
            # In-app back navigation — forward to app
            if self._active_app:
                self._active_app.on_gesture('swipe_left')
            elif self.state == STATE_MENU:
                pass   # nothing to go back to in menu

        elif event == EVT_CONFIRM:
            if self.state == STATE_MENU:
                self.scene.confirm_selection(self)
            elif self._active_app:
                self._active_app.on_gesture('pinch')

        elif event == EVT_HOME:
            # Legacy — both-caps short tap now handled in run() loop
            pass

    def _handle_key(self, key):
        if key == pygame.K_ESCAPE:
            self._running = False
        elif key == pygame.K_SPACE:
            self._pinned = not self._pinned
            print(f'[IRIS] {"Pinned" if self._pinned else "Unpinned"}')
        elif key == pygame.K_BACKSPACE:
            if self.state == STATE_APP:
                self.close_app()
        elif key == pygame.K_z:
            self._handle_cap(EVT_BACK)
        elif key == pygame.K_x:
            self._handle_cap(EVT_CONFIRM)
        elif key == pygame.K_a:
            s = self.imu.state
            self.scene.add(s.yaw, s.pitch)
        elif key == pygame.K_d:
            self.scene.remove(-1)
        elif key == pygame.K_r:
            self.imu.reset()
        elif key == pygame.K_s:
            self.scene.save()

    def _draw_home_hint(self):
        canvas.blit(self._home_hint_surf,
                    (WIDTH // 2 - self._home_hint_surf.get_width() // 2,
                     HEIGHT - 20))

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _handle_sigterm(self, signum, frame):
        self._shutdown()

    def _shutdown(self):
        self.scene.save()
        try:
            logo = pygame.image.load('assets/LOGO.png').convert_alpha()
            logo = pygame.transform.smoothscale(logo, (200, 200))
            screen.fill(BLACK)
            r = logo.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(logo, r)
            pygame.display.flip()
            pygame.time.wait(1500)
        except Exception:
            screen.fill(BLACK)
            pygame.display.flip()
            pygame.time.wait(500)
        pygame.quit()
        print('[IRIS] Shutdown.')
        sys.exit(0)


def main():
    iris = IrisOS()
    iris.boot()
    iris.run()


if __name__ == '__main__':
    main()
