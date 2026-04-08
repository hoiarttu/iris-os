"""
main.py — IRIS OS kernel
─────────────────────────────────────────────────────────────────────────────
State machine:
  MENU    hex menu visible, IMU shifts it, dwell/cap-touch selects
  APP     app owns full screen
  OVERLAY app running but menu briefly visible

Input:
  IMU             gaze direction
  Cap touch       via ESP32 I2C stub
  Hand cursor     via hand_tracker.py Unix socket
  Keyboard        dev fallback

Keyboard shortcuts (dev):
  ESC         quit
  ←/→/↑/↓    mock IMU yaw/pitch
  SPACE       pin/unpin menu
  A           add mirage
  D           remove last mirage
  R           reset IMU
  S           save scene
  BACKSPACE   home (both caps)
  Z           left cap (back)
  X           right cap (confirm)
"""

import sys
import signal
import pygame

from core.display          import screen, canvas, clock, CENTER, WIDTH, HEIGHT, FPS, BLACK, WHITE, ACCENT
from core.mpu6050_handler  import Mpu6050Handler
from core.input_handler    import InputHandler, EVT_HOME, EVT_CONFIRM, EVT_BACK
from core.hand_client      import HandClient
from components.mirage_manager import MirageManager

# ── Config ────────────────────────────────────────────────────────────────────

SCENE_PATH      = 'mirages.json'
IMU_BUS         = 11
IMU_YAW_AXIS    = 'x'
IMU_PITCH_AXIS  = 'z'
IMU_ROLL_AXIS   = 'y'
IMU_ALPHA       = 0.98
IMU_CAL_SAMPLES = 150

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

        self.input = InputHandler()
        self.hand  = HandClient()

        self.scene = MirageManager(
            path   = SCENE_PATH,
            os_ref = self,
        )

        self._running    = False
        self._active_app = None
        self._both_held  = False
        self._both_since = 0.0
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        self._dlp_timer  = 30.0  # fire on first frame
        try:
            import smbus2
            self._dlp_bus = smbus2.SMBus(11)
        except Exception:
            self._dlp_bus = None
        _f = pygame.font.Font(
            'assets/fonts/Rajdhani-Regular.ttf', 11)
        self._home_hint_surf = _f.render('both caps = home', True, (60, 60, 60))

    def boot(self):
        if IMU_CAL_SAMPLES > 0:
            self.imu.calibrate(IMU_CAL_SAMPLES)
        print('[IRIS] Boot complete.')

    def run(self):
        self._running = True
        while self._running:
            dt = clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(event.key)

            for cap_event in self.input.get_events():
                self._handle_cap(cap_event)

            imu_state = self.imu.update()
            self.hand.update()

            # Both caps held — freeze mirage at center
            if self._both_held:
                import time as _t
                both_now = self.input._alpha_held and self.input._beta_held
                if not both_now:
                    # Released — pin at current yaw, reset pitch, spawn
                    held_secs = _t.time() - self._both_since
                    if held_secs >= 1.5:
                        for m in self.scene.mirages:
                            m.azimuth   = imu_state.yaw
                            m.elevation = 0.0
                        self.imu.reset()
                        self.scene.save()
                        self.scene.trigger_spawn()
                        print('[IRIS] Mirage pinned')
                    self._both_held = False
                else:
                    # Still held — override IMU to keep mirage centered
                    imu_state.yaw   = self.scene.mirages[0].azimuth if self.scene.mirages else 0.0
                    imu_state.pitch = 0.0
            self._dlp_timer += dt
            if self._dlp_timer >= 30.0 and self._dlp_bus:
                self._dlp_timer = 0.0
                try:
                    self._dlp_bus.write_i2c_block_data(0x1b, 0x0c, [0x00,0x00,0x00,0x13])
                    self._dlp_bus.write_i2c_block_data(0x1b, 0x0b, [0x00,0x00,0x00,0x00])
                except Exception:
                    pass

            canvas.fill(BLACK)

            if self._pinned:
                imu_state.yaw   = 0.0
                imu_state.pitch = 0.0
                imu_state.roll  = 0.0

            if self.state == STATE_MENU:
                self.scene.update(imu_state, dt, self.hand)

            elif self.state == STATE_APP:
                if self._active_app:
                    self._active_app.draw_fullscreen(canvas)
                    self._active_app.update(dt)
                self._draw_home_hint()

            elif self.state == STATE_OVERLAY:
                if self._active_app:
                    self._active_app.draw_fullscreen(canvas)
                    self._active_app.update(dt)
                self.scene.update(imu_state, dt, self.hand)

            roll = imu_state.roll if not self._pinned else 0.0
            screen_center = (WIDTH // 2, HEIGHT // 2)
            screen.fill(BLACK)
            if self.scene._spawning:
                from core.geometry import ease_out
                t = ease_out(min(1.0, self.scene._spawn_t / self.scene._SPAWN_DUR))
                if t > 0.01:
                    scaled_w = max(1, int(WIDTH * t))
                    scaled_h = max(1, int(HEIGHT * t))
                    scaled = pygame.transform.scale(canvas, (scaled_w, scaled_h))
                    scaled.set_alpha(int(255 * t))
                    rect = scaled.get_rect(center=screen_center)
                    screen.blit(scaled, rect)
            elif abs(roll) > 1.0:
                rotated = pygame.transform.rotate(canvas, -roll)
                rect = rotated.get_rect(center=screen_center)
                screen.blit(rotated, rect)
            else:
                rect = canvas.get_rect(center=screen_center)
                screen.blit(canvas, rect)
            pygame.display.flip()

        self._shutdown()

    # ── App lifecycle ─────────────────────────────────────────────────────────

    def launch_app(self, app):
        if self._active_app:
            self._active_app.suspend()
        self._active_app = app
        self._active_app.launch()
        self.state = STATE_APP
        print(f'[IRIS] Launched: {app.name}')

    def close_app(self):
        if self._active_app:
            self._active_app.close()
            self._active_app = None
        self.state = STATE_MENU
        self.scene.trigger_spawn()
        print('[IRIS] Returned to menu.')

    # ── Input ─────────────────────────────────────────────────────────────────

    def _handle_cap(self, event):
        if event == EVT_HOME:
            if self.state in (STATE_APP, STATE_OVERLAY):
                self.close_app()
            elif self.state == STATE_MENU:
                self._both_held  = True
                self._both_since = __import__('time').time()
        elif event == EVT_CONFIRM:
            self.scene.confirm_selection(self)
        elif event == EVT_BACK:
            if self.state == STATE_APP:
                self.close_app()

    def _handle_key(self, key):
        if key == pygame.K_ESCAPE:
            self._running = False
        elif key == pygame.K_SPACE:
            self._pinned = not self._pinned
            print(f'[IRIS] {"Pinned" if self._pinned else "Unpinned"}')
        elif key == pygame.K_BACKSPACE:
            self._handle_cap(EVT_HOME)
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
                    (WIDTH//2 - self._home_hint_surf.get_width()//2, HEIGHT - 20))

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _handle_sigterm(self, signum, frame):
        self._shutdown()

    def _shutdown(self):
        self.scene.save()
        # Shutdown screen
        try:
            logo = pygame.image.load('assets/LOGO.png').convert_alpha()
            logo = pygame.transform.smoothscale(logo, (200, 200))
            screen.fill(BLACK)
            r = logo.get_rect(center=(WIDTH//2, HEIGHT//2))
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
