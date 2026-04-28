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

import sys, signal, math as _m, subprocess, os
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

        self._dlp_timer = 0.0
        try:
            import smbus2
            self._dlp_bus = smbus2.SMBus(11)
        except Exception:
            self._dlp_bus = None

        # DLP power via GPIO 27
        self._dlp_on        = True
        self._dlp_off_timer = 0.0
        self._dlp_still_timer = 0.0
        self._DLP_STILL_DELAY = 10.0
        self._DLP_MOVE_THRESH = 5.0
        self._last_yaw        = 0.0
        self._last_pitch      = 0.0
        self._DLP_OFF_DELAY = 1.0   # seconds off-screen before DLP powers down
        self._DLP_THRESHOLD = 30.0  # degrees off-mirage before considering blank
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(27, GPIO.OUT)
            GPIO.output(27, GPIO.HIGH)
            self._gpio = GPIO
            print('[IRIS] DLP GPIO 27 ready')
        except Exception as e:
            self._gpio = None
            print(f'[IRIS] GPIO unavailable ({e})')

        # Load config
        from core.config import load_config
        self._config = load_config()
        self._apply_accent(self._config['accent'])

        _f = pygame.font.Font('assets/fonts/Rajdhani-Regular.ttf', 11)
        self._home_hint_surf = _f.render('both caps = home', True, (60, 60, 60))

    def boot(self):
        # Auto-start hand tracker as background process
        try:
            tracker_path = os.path.join(os.path.dirname(__file__), 'hand_tracker.py')
            self._tracker_proc = subprocess.Popen(
                ['nice', '-n', '-5', sys.executable, tracker_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print('[IRIS] Hand tracker started')
        except Exception as e:
            print(f'[IRIS] Hand tracker failed to start: {e}')
            self._tracker_proc = None

        # Load saved bias — only recalibrate if no saved bias exists
        if not self.imu.load_bias():
            print('[IRIS] No saved bias — running first-time calibration')
            self.imu.calibrate(500)
        print('[IRIS] Boot complete.')

    def run(self):
        self._running = True
        while self._running:
            import core.display as _cd
            dt = clock.tick(_cd.FPS) / 1000.0

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
            # Always drain events to prevent buildup
            # Block from reaching app during spawn or when both caps held
            both_held = self.input._alpha_held and self.input._beta_held
            cap_events = self.input.get_events()
            if not self.scene._spawning and not both_held:
                for cap_event in cap_events:
                    self._handle_cap(cap_event)

            if getattr(self, "_cal_thread_started", False):
                imu_state = self.imu.state
            else:
                imu_state = self.imu.update()
            self.hand.update()

            # ── Gesture detection (disabled — no landmark model available) ──
            # gesture_list = self.gestures.update(self.hand)
            # for gesture in gesture_list:
            #     self._handle_gesture(gesture)

            # ── Thermal management
            self._update_thermal(dt)

            # ── DLP power management ──────────────────────────────────────────
            self._update_dlp(imu_state, dt)

            # ── Both-caps hold logic ──────────────────────────────────────────
            # Single tap  → recenter yaw
            # Double tap  → home
            # Hold 1.5s+  → pin mirage + home
            # Hold 20s+   → wipe IMU bias + shutdown
            import time as _t
            both_raw = self.input._alpha_held and self.input._beta_held
            if both_raw:
                self._both_loss_t = 0.0
            else:
                self._both_loss_t = getattr(self, '_both_loss_t', 0.0) + dt
            both_now = self._both_loss_t < 0.25

            if both_now and not self._both_held:
                self._both_held  = True
                self._both_since = _t.time()

            elif not both_now and self._both_held:
                held = _t.time() - self._both_since
                self._recal_done = False

                if held >= 1.5:
                    # Long hold — pin mirage + home
                    self._do_pin_and_home(imu_state)
                elif held >= 0.3:
                    # Short tap — recenter yaw to current gaze
                    for m in self.scene.mirages:
                        m.azimuth = imu_state.yaw
                    self.scene.save()
                    print('[IRIS] Both-caps tap — recentered')

                self._both_held = False

            elif both_now and self._both_held:
                held = _t.time() - self._both_since
                # While held, freeze display
                if self.scene.mirages:
                    imu_state.yaw   = self.scene.mirages[0].azimuth
                    imu_state.pitch = 0.0
                    imu_state.roll  = 0.0
                # 20s — wipe IMU bias + shutdown
                if held >= 20.0 and not getattr(self, '_recal_done', False):
                    self._recal_done = True
                    print('[IRIS] 20s hold — wiping IMU bias and shutting down')
                    try:
                        import os as _os2
                        _os2.remove(_os2.path.expanduser('~/.iris/imu_bias.json'))
                    except Exception:
                        pass
                    self._power_action('shutdown')

            # ── Cap hold → app draw state ────────────────────────────────────────
            if self._active_app and hasattr(self._active_app, '_cap_draw'):
                self._active_app._cap_draw = (self.input._beta_held
                                               and not self.input._alpha_held)

            # ── DLP keepalive ─────────────────────────────────────────────────
            self._dlp_timer += dt
            if self._dlp_timer >= 0.1 and self._dlp_bus:
                self._dlp_timer = 0.0
                try:
                    self._dlp_bus.write_i2c_block_data(
                        0x1b, 0x0c, [0x00, 0x00, 0x00, 0x13])
                    self._dlp_bus.write_i2c_block_data(
                        0x1b, 0x0b, [0x00, 0x00, 0x00, 0x00])
                except Exception:
                    pass

            # ── Deep Sleep Render Bypass ──────────────────────────────────────
            if not self._dlp_on:
                continue  # Skip all pygame rendering and flipping

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
                        dy = (imu_state.pitch - m.elevation) * PX_PER_DEGREE_PITCH

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
                # Pad canvas before rotation to prevent framebuffer edge blink
                pad    = 60
                padded = pygame.Surface((WIDTH + pad*2, HEIGHT + pad*2))
                padded.fill(BLACK)
                padded.blit(canvas, (pad, pad))
                rotated = pygame.transform.rotate(padded, -roll)
                rect    = rotated.get_rect(center=screen_center)
                screen.blit(rotated, rect)
            else:
                screen.blit(canvas, (0, 0))

            pygame.display.flip()

        self._shutdown()

    # ── Accent color ─────────────────────────────────────────────────────────────

    def _apply_accent(self, rgb: list):
        import core.display as _cd
        import components.draw as _dr
        import apps.settings_app as _sa
        r, g, b = rgb
        # Primary
        _cd.ACCENT             = (r, g, b)
        _dr.HEX_BORDER_FOCUSED = (r, g, b)
        self.input.set_led(r, g, b, 0)
        # Secondary — same hue, darkened
        # Special cases for specific themes
        if (r, g, b) == (80, 220, 255):
            sr, sg, sb = 80, 40, 180    # IRIS cyan → IRIS purple
        elif (r, g, b) == (255, 255, 255):
            sr, sg, sb = 40, 40, 55    # White → dark slate secondary
        else:
            sr = max(0, int(r * 0.30))
            sg = max(0, int(g * 0.15))
            sb = max(0, min(255, int(b * 0.70 + 50)))
        _cd.SECONDARY          = (sr, sg, sb)
        _dr.HEX_BORDER_IDLE    = (sr, sg, sb)
        _sa.COL_SEL            = (r, g, b)
        _sa.COL_IDLE           = (sr, sg, sb)
        print(f'[IRIS] Accent {rgb} → secondary ({sr},{sg},{sb})')

    # ── DLP power management ─────────────────────────────────────────────────────

    def _update_thermal(self, dt):
        # Read CPU temp every 2s, scale FPS, shut DLP if overheating
        self._thermal_tick = getattr(self, '_thermal_tick', 0.0) + dt
        if self._thermal_tick < 2.0:
            return
        self._thermal_tick = 0.0
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as _f:
                temp = int(_f.read().strip()) / 1000.0
        except Exception:
            return
        self._last_temp = temp
        if temp >= 70.0:
            print(f'[IRIS] OVERHEAT {temp:.0f}C - emergency DLP off')
            if getattr(self, '_gpio', None):
                self._gpio.output(27, self._gpio.LOW)
                self._dlp_on = False
            import core.display as _cd
            _cd.FPS = 15
            open('/tmp/iris_tracker_fps', 'w').write('0')
            return
        if temp <= 50.0:
            target_fps  = 60
            tracker_fps = 15
        else:
            frac        = (temp - 50.0) / 20.0
            target_fps  = int(60 - frac * 45)   # 60fps at 50C -> 15fps at 70C
            tracker_fps = int(15 - frac * 12)   # 15fps at 50C -> 3fps at 70C
        import core.display as _cd
        if _cd.FPS != target_fps:
            print(f'[IRIS] Thermal: {temp:.0f}C -> {target_fps}fps, tracker {tracker_fps}fps')
            _cd.FPS = target_fps
        open('/tmp/iris_tracker_fps', 'w').write(str(tracker_fps))

    def _update_dlp(self, imu_state, dt):
        if not getattr(self, '_gpio', None): return
        try:
            from core.geometry import angle_diff
            
            in_view = False
            if getattr(self.scene, 'mirages', None):
                # Check ALL pinned mirages, not just index 0
                for m in self.scene.mirages:
                    if abs(angle_diff(imu_state.yaw, m.azimuth)) < self._DLP_THRESHOLD and abs(imu_state.pitch - m.elevation) < self._DLP_THRESHOLD:
                        in_view = True
                        break
                
            if self.state == STATE_APP and self._active_app and getattr(self._active_app, 'pin_mode', 'pinned') != 'pinned':
                in_view = True

            # Any cap press = wake, no timeout
            cap_active = self.input._alpha_held or self.input._beta_held

            # Hand stuck failsafe (if hand doesn't move 1 pixel for 2s, ignore it)
            hand_active = False
            if self.hand and self.hand.active:
                hx, hy = getattr(self.hand, 'x', -1), getattr(self.hand, 'y', -1)
                if hx == getattr(self, '_last_hx', -2) and hy == getattr(self, '_last_hy', -2):
                    self._hand_stuck_t = getattr(self, '_hand_stuck_t', 0.0) + dt
                else:
                    self._hand_stuck_t = 0.0
                self._last_hx, self._last_hy = hx, hy
                
                if self._hand_stuck_t < 2.0:
                    hand_active = True

            app_allows = (self._active_app is None or getattr(self._active_app, 'dlp_auto_off', True))

            # Still timer — sleep after 30s no movement in menu
            dyaw   = abs(angle_diff(imu_state.yaw,   getattr(self, '_still_yaw',   imu_state.yaw)))
            dpitch = abs(imu_state.pitch - getattr(self, '_still_pitch', imu_state.pitch))
            self._still_yaw   = imu_state.yaw
            self._still_pitch = imu_state.pitch
            moving = (dyaw + dpitch) > 0.4

            if moving or cap_active or hand_active:
                self._dlp_still_timer = 0.0
            else:
                self._dlp_still_timer += dt

            still_sleep = (
                self._dlp_still_timer >= 30.0 and
                (self.state == STATE_MENU or
                 getattr(self._active_app, 'dlp_sleep_on_still', False))
            )

            # bad_orientation and still_sleep override in_view
            bad_orientation = imu_state.pitch < -75.0
            force_off = bad_orientation or still_sleep

            if (in_view or cap_active or hand_active) and not force_off:
                self._dlp_off_timer = 0.0
                if not self._dlp_on:
                    self._gpio.output(27, self._gpio.HIGH)
                    self._dlp_on = True
            else:
                self._dlp_off_timer += dt
                if self._dlp_off_timer >= 1.5 and self._dlp_on and app_allows:
                    self._gpio.output(27, self._gpio.LOW)
                    self._dlp_on = False
                    reason = 'orientation' if bad_orientation else 'still' if still_sleep else 'out of view'
                    print(f'[IRIS] DLP off ({reason})')
        except Exception as e:
            print(f"[IRIS] DLP Logic Error: {e}")

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
            m.elevation = imu_state.pitch
        # Don't reset IMU — causes snap. Just save new azimuth.
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
        # Inject os_ref for apps that need kernel access
        if hasattr(self._active_app, '_os_ref'):
            self._active_app._os_ref = self
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
            # Alpha tap — call _handle_alpha if app has it, else navigate
            if self._active_app:
                if hasattr(self._active_app, '_handle_alpha'):
                    self._active_app._handle_alpha()
                else:
                    self._active_app.on_gesture('swipe_left')

        elif event == EVT_CONFIRM:
            if self.state == STATE_MENU:
                self.scene.confirm_selection(self)
            elif self._active_app:
                if hasattr(self._active_app, '_handle_beta'):
                    self._active_app._handle_beta()
                else:
                    self._active_app.on_gesture('pinch')



    def _handle_key(self, key):
        if key == pygame.K_ESCAPE:
            self._running = False
        elif key == pygame.K_SPACE:
            self._pinned = not self._pinned
            print(f'[IRIS] {"Pinned" if self._pinned else "Unpinned"}')
        elif key == pygame.K_BACKSPACE:
            if self.state == STATE_APP:
                self.close_app()
        elif key == pygame.K_ESCAPE:
            if self.state == STATE_APP:
                self.close_app()
            else:
                self._running = False
        elif key == pygame.K_ESCAPE:
            if self.state == STATE_APP:
                self.close_app()
            else:
                self._running = False
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
        pass   # removed — minimal UI

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _handle_sigterm(self, signum, frame):
        self._shutdown()

    def _power_action(self, action: str):
        """Graceful reboot/shutdown: LOGO -> DLP off -> pygame quit -> os cmd."""
        import os as _os
        self.scene.reset_to_default()
        self.scene.save()
        try:
            logo = pygame.image.load('assets/LOGO.png').convert_alpha()
            logo = pygame.transform.smoothscale(logo, (200, 200))
            screen.fill(BLACK)
            r = logo.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(logo, r)
            pygame.display.flip()
            pygame.time.wait(1800)
        except Exception:
            pass
        if hasattr(self, '_gpio') and self._gpio:
            self._gpio.output(27, self._gpio.LOW)
            self._gpio.cleanup()
        if hasattr(self, '_tracker_proc') and self._tracker_proc:
            self._tracker_proc.terminate()
        pygame.quit()
        if action == 'reboot':
            _os.system('sudo reboot')
        else:
            _os.system('sudo shutdown -h now')
        sys.exit(0)

    def _shutdown(self):
        self.scene.reset_to_default()
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
        if hasattr(self, '_tracker_proc') and self._tracker_proc:
            self._tracker_proc.terminate()
            print('[IRIS] Hand tracker stopped')
        if hasattr(self, '_gpio') and self._gpio:
            self._gpio.output(27, self._gpio.LOW)
            self._gpio.cleanup()
            print('[IRIS] GPIO cleaned up')
        pygame.quit()
        print('[IRIS] Shutdown.')
        sys.exit(0)


def main():
    iris = IrisOS()
    iris.boot()
    iris.run()


if __name__ == '__main__':
    main()
