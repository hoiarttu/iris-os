"""
main.py  —  IRIS OS kernel
────────────────────────────────────────────────────────────────────────────
Pi Zero 2 efficiency contract
  • ONE imu.update() call per frame — result passed everywhere, never re-read.
  • dt comes from clock.tick(), passed into scene.update() — no time.time() in loop.
  • No object allocation in the hot path (surfaces, fonts, state objects all pre-built).
  • canvas.fill() uses a solid colour (DIM) — no alpha, no alloc.
  • screen.blit(canvas) is a single memcpy — post-processing hooks slot in here.

Layer map (imports flow downward only)
  main.py
    core/display.py              ← pygame + constants + POOL + fonts
    core/geometry.py             ← pure math + colour LUT
    core/mpu6050_handler.py      ← IMU or mock
    components/hexmenu.py        ← cached geometry
    components/draw.py           ← pool-based drawing
    components/mirage_manager.py ← scene + dwell + actions

Keyboard shortcuts
  ESC     quit
  ←/→/↑/↓ yaw/pitch  (mock IMU only)
  A       add hexmenu Mirage at current gaze
  D       remove last Mirage
  R       reset IMU integration
  S       save scene
  F1      toggle debug overlay
"""

import os
import sys
import time

import pygame

from core.display import (screen, canvas, clock, CENTER, FPS,
                           DIM, ACCENT, WHITE, BLACK, FONT_DEBUG)
from core.mpu6050_handler  import Mpu6050Handler
from components.draw           import draw_center_glow, draw_pointer
from components.mirage_manager import MirageManager


# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH     = '/home/iris/mirages.json'
BOOT_SIGNAL     = '/tmp/iris_boot_video_done'

IMU_BUS         = 11
IMU_YAW_AXIS    = 'x'
IMU_PITCH_AXIS  = 'y'
IMU_ROLL_AXIS   = 'z'
IMU_ALPHA       = 0.98
IMU_CAL_SAMPLES = 150   # 0 = skip calibration


# ── Debug overlay ─────────────────────────────────────────────────────────────
# Pre-build the static label surfaces once — only value strings change per frame.

_DBG_LABELS = ['yaw', 'pitch', 'roll', 'fps']
_DBG_LABEL_SURFS = [FONT_DEBUG.render(f'{k:<6}', True, ACCENT)
                    for k in _DBG_LABELS]


def _draw_debug(surface, state, fps: float, smooth_yaw: float):
    values = [
        f'{state.yaw:6.1f}  ~{smooth_yaw:5.1f}',
        f'{state.pitch:6.1f}',
        f'{state.roll:6.1f}',
        f'{fps:5.1f}',
    ]
    for i, (label_surf, val) in enumerate(zip(_DBG_LABEL_SURFS, values)):
        val_surf = FONT_DEBUG.render(val, True, WHITE)   # value changes each frame
        y = 6 + i * 14
        surface.blit(label_surf, (6,  y))
        surface.blit(val_surf,   (52, y))


# ── OS kernel ─────────────────────────────────────────────────────────────────

class IrisOS:

    def __init__(self):
        self.settings: dict = {
            'debug':      False,
            'brightness': 1.0,
        }

        self.imu = Mpu6050Handler(
            bus        = IMU_BUS,
            yaw_axis   = IMU_YAW_AXIS,
            pitch_axis = IMU_PITCH_AXIS,
            roll_axis  = IMU_ROLL_AXIS,
            alpha      = IMU_ALPHA,
        )

        self.scene = MirageManager(CONFIG_PATH, os_ref=self)

        self._running = False
        self._pulse   = 0.0

    # ── Boot ──────────────────────────────────────────────────────────────────

    def boot(self):
        if os.path.exists(BOOT_SIGNAL):
            print('[IRIS] Waiting for boot video...')
            while not os.path.exists(BOOT_SIGNAL):
                time.sleep(0.05)
            try:
                os.remove(BOOT_SIGNAL)
            except OSError:
                pass
        else:
            print('[IRIS] Dev mode — no boot signal.')

        # Warm-up: discard first noisy IMU readings
        for _ in range(20):
            self.imu.update()
            time.sleep(0.01)

        if IMU_CAL_SAMPLES > 0:
            self.imu.calibrate(samples=IMU_CAL_SAMPLES)

        print('[IRIS] Boot complete.')

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self):
        self._running = True

        while self._running:
            # ── Timing ──────────────────────────────────────────────────────
            dt = clock.tick(FPS) / 1000.0   # blocks until next frame slot
            self._pulse += dt

            # ── Events ──────────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(event.key)

            # ── ONE sensor read for the entire frame ─────────────────────────
            state = self.imu.update()

            # ── Render ──────────────────────────────────────────────────────
            canvas.fill(DIM)                         # solid fill — fast
            draw_center_glow(canvas, CENTER)
            self.scene.update(                       # dt propagated, no time.time()
                state.yaw, state.pitch, self._pulse, dt)
            draw_pointer(canvas, CENTER)

            if self.settings.get('debug'):
                _draw_debug(canvas, state,
                            clock.get_fps(), self.scene._smooth_yaw)

            # Single blit to physical screen
            screen.blit(canvas, (0, 0))
            pygame.display.flip()

        self._shutdown()

    # ── Input ─────────────────────────────────────────────────────────────────

    def _handle_key(self, key):
        if key == pygame.K_ESCAPE:
            self._running = False

        elif key == pygame.K_a:
            st = self.imu.state   # cached — no new sensor read
            self.scene.add(st.yaw, st.pitch, 'hexmenu')
            print(f'[IRIS] Mirage at yaw={st.yaw:.1f}')

        elif key == pygame.K_d:
            if self.scene.mirages:
                self.scene.remove(len(self.scene.mirages) - 1)

        elif key == pygame.K_r:
            self.imu.reset()
            print('[IRIS] IMU reset')

        elif key == pygame.K_s:
            self.scene.save()

        elif key == pygame.K_F1:
            self.settings['debug'] = not self.settings.get('debug')
            print(f'[IRIS] Debug: {self.settings["debug"]}')

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _shutdown(self):
        self.scene.save()
        pygame.quit()
        print('[IRIS] Shutdown.')
        sys.exit(0)


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    iris = IrisOS()
    iris.boot()
    iris.run()


if __name__ == '__main__':
    main()
