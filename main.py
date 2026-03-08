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
import pygame

from core.display          import screen, canvas, clock, CENTER, WIDTH, HEIGHT, FPS, BLACK, WHITE, ACCENT
from core.mpu6050_handler  import Mpu6050Handler
from core.input_handler    import InputHandler, EVT_HOME, EVT_CONFIRM, EVT_BACK
from core.hand_client      import HandClient
from components.mirage_manager import MirageManager

# ── Config ────────────────────────────────────────────────────────────────────

SCENE_PATH      = '/home/iris/mirages.json'
IMU_BUS         = 11
IMU_YAW_AXIS    = 'y'
IMU_PITCH_AXIS  = 'z'
IMU_ROLL_AXIS   = 'x'
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

            canvas.fill(BLACK)

            yaw   = 0.0 if self._pinned else imu_state.yaw
            pitch = 0.0 if self._pinned else imu_state.pitch

            if self.state == STATE_MENU:
                self.scene.update(yaw, pitch, dt, self.hand)

            elif self.state == STATE_APP:
                if self._active_app:
                    self._active_app.draw_fullscreen(canvas)
                    self._active_app.update(dt)
                self._draw_home_hint()

            elif self.state == STATE_OVERLAY:
                if self._active_app:
                    self._active_app.draw_fullscreen(canvas)
                    self._active_app.update(dt)
                self.scene.update(yaw, pitch, dt, self.hand)

            screen.blit(canvas, (0, 0))
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
        print('[IRIS] Returned to menu.')

    # ── Input ─────────────────────────────────────────────────────────────────

    def _handle_cap(self, event):
        if event == EVT_HOME:
            if self.state in (STATE_APP, STATE_OVERLAY):
                self.close_app()
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
        f = pygame.font.Font(
            '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 11)
        s = f.render('both caps = home', True, (60, 60, 60))
        canvas.blit(s, (WIDTH//2 - s.get_width()//2, HEIGHT - 20))

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _shutdown(self):
        self.scene.save()
        pygame.quit()
        print('[IRIS] Shutdown.')
        sys.exit(0)


def main():
    iris = IrisOS()
    iris.boot()
    iris.run()


if __name__ == '__main__':
    main()
