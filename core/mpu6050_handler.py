"""
core/mpu6050_handler.py

IMU abstraction — MPU6050 hardware or keyboard mock.
──────────────────────────────────────────────────────
RULES
  • Exactly ONE sensor read per call to update() — no double-reads.
  • update() mutates and returns the same OrientationState object every call
    (zero heap allocation in the hot path).
  • Hardware import is deferred inside RealIMU.__init__ so a missing
    mpu6050 package does not prevent the OS from booting in mock mode.
  • No pygame display calls.  No imports from components/.

Keyboard mock mapping (arrow keys):
  LEFT / RIGHT  → yaw   ±YAW_SPEED  °/s
  UP   / DOWN   → pitch ±PITCH_SPEED °/s
"""

import time
import math


class OrientationState:
    __slots__ = ('yaw', 'pitch', 'roll', 'timestamp')

    def __init__(self):
        self.yaw       = 0.0
        self.pitch     = 0.0
        self.roll      = 0.0
        self.timestamp = time.time()

    def as_dict(self) -> dict:
        return {'yaw': self.yaw, 'pitch': self.pitch, 'roll': self.roll}

    def __repr__(self):
        return (f'OrientationState('
                f'yaw={self.yaw:.1f}, pitch={self.pitch:.1f}, '
                f'roll={self.roll:.1f})')


class RealIMU:
    __slots__ = ('sensor', 'yaw_axis', 'pitch_axis', 'roll_axis',
                 'alpha', '_bias', '_pitch_offset', '_roll_offset',
                 '_state', '_last_time')

    _AXES = ('x', 'y', 'z')

    def __init__(self, address, bus, yaw_axis, pitch_axis, roll_axis, alpha):
        from mpu6050 import mpu6050 as _lib
        self.sensor     = _lib(address, bus=bus)
        self.yaw_axis   = yaw_axis
        self.pitch_axis = pitch_axis
        self.roll_axis  = roll_axis
        self.alpha      = alpha
        self._bias         = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self._pitch_offset = 0.0
        self._roll_offset  = 0.0
        self._state        = OrientationState()
        self._last_time    = time.time()

    def calibrate(self, samples: int = 200) -> dict:
        print(f'[IMU] Calibrating {samples} samples — hold still...')
        acc = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        for _ in range(samples):
            g = self.sensor.get_gyro_data()
            for ax in self._AXES:
                acc[ax] += g[ax]
            time.sleep(0.005)
        self._bias      = {ax: acc[ax] / samples for ax in self._AXES}
        self._state     = OrientationState()
        self._last_time = time.time()
        pacc, racc = 0.0, 0.0
        for _ in range(100):
            accel = self.sensor.get_accel_data()
            pacc += math.degrees(math.atan2(accel['y'], -accel['x']))
            racc += math.degrees(math.atan2(accel['z'], -accel['x']))
            time.sleep(0.005)
        self._pitch_offset = pacc / 100
        self._roll_offset  = racc / 100
        print(f'[IMU] Bias: {self._bias}  pitch_offset={self._pitch_offset:.1f}  roll_offset={self._roll_offset:.1f}')
        # Save bias to file
        from core.config import save_bias
        save_bias({'bias': self._bias,
                   'pitch_offset': self._pitch_offset,
                   'roll_offset':  self._roll_offset})
        print('[IMU] Bias saved')
        return self._bias

    def load_bias(self) -> bool:
        from core.config import load_bias
        data = load_bias()
        if data:
            self._bias         = data.get('bias', {'x':0.0,'y':0.0,'z':0.0})
            self._pitch_offset = data.get('pitch_offset', 0.0)
            self._roll_offset  = data.get('roll_offset',  0.0)
            self._state        = OrientationState()
            self._last_time    = time.time()
            print(f'[IMU] Bias loaded from file')
            return True
        return False

    def reset(self):
        self._state     = OrientationState()
        self._last_time = time.time()

    def update(self) -> OrientationState:
        now = time.time()
        dt  = min(now - self._last_time, 0.1)
        self._last_time = now

        gyro  = self.sensor.get_gyro_data()
        accel = self.sensor.get_accel_data()

        # Safe Gyro math (ignores violent spikes > 1000 deg/s)
        gy = gyro[self.yaw_axis] - self._bias[self.yaw_axis]
        gp = gyro[self.pitch_axis] - self._bias[self.pitch_axis]
        
        if abs(gy) > 1000.0 or abs(gp) > 1000.0:
            self._state.timestamp = now
            return self._state

        self._state.yaw = (self._state.yaw + gy * dt) % 360.0
        self._state.pitch += gp * dt
        gyro_mag = abs(gyro[self.pitch_axis] - self._bias[self.pitch_axis])
        if gyro_mag < 1.0:
            self._state.pitch *= 0.999
        self._state.pitch = max(-89.0, min(89.0, self._state.pitch))

        # Roll — two formula, orientation aware
        ax, ay, az = accel['x'], accel['y'], accel['z']
        abs_ax, abs_ay, abs_az = abs(ax), abs(ay), abs(az)
        if abs_ax > abs_ay and abs_ax > abs_az:
            ar = math.degrees(math.atan2(az, -ax))
        elif abs_az > abs_ax and abs_az > abs_ay:
            ar = 0.0
        else:
            ar = math.degrees(math.atan2(ax, ay))
        self._state.roll = max(-75.0, min(75.0, 0.9 * self._state.roll + 0.1 * ar))

        self._state.timestamp = now
        return self._state


class MockIMU:
    __slots__ = ('_pygame', '_state', '_last_time')

    YAW_SPEED   = 45.0
    PITCH_SPEED = 30.0

    def __init__(self):
        import pygame as _pg
        self._pygame    = _pg
        self._state     = OrientationState()
        self._last_time = time.time()
        print('[IMU] No hardware — keyboard mock active.')
        print('[IMU] LEFT/RIGHT=yaw  UP/DOWN=pitch  R=reset')

    def calibrate(self, samples=0, **_):
        pass

    def reset(self):
        self._state     = OrientationState()
        self._last_time = time.time()

    def update(self) -> OrientationState:
        pg  = self._pygame
        now = time.time()
        dt  = min(now - self._last_time, 0.1)
        self._last_time = now

        keys = pg.key.get_pressed()
        if keys[pg.K_LEFT]:
            self._state.yaw = (self._state.yaw - self.YAW_SPEED  * dt) % 360.0
        if keys[pg.K_RIGHT]:
            self._state.yaw = (self._state.yaw + self.YAW_SPEED  * dt) % 360.0
        if keys[pg.K_UP]:
            self._state.pitch = max(-90.0, self._state.pitch - self.PITCH_SPEED * dt)
        if keys[pg.K_DOWN]:
            self._state.pitch = min( 90.0, self._state.pitch + self.PITCH_SPEED * dt)
        if keys[pg.K_r]:
            self.reset()

        self._state.timestamp = now
        return self._state


class Mpu6050Handler:
    __slots__ = ('_backend',)

    def __init__(self, address=0x68, bus=1,
                 yaw_axis='z', pitch_axis='y', roll_axis='x', alpha=0.98):
        try:
            self._backend = RealIMU(address, bus,
                                    yaw_axis, pitch_axis, roll_axis, alpha)
            print(f'[IMU] MPU6050 on bus {bus}, addr 0x{address:02X}')
        except Exception as e:
            print(f'[IMU] Hardware unavailable ({e})')
            self._backend = MockIMU()

    def calibrate(self, samples=200):
        return self._backend.calibrate(samples=samples)

    def load_bias(self) -> bool:
        if hasattr(self._backend, 'load_bias'):
            return self._backend.load_bias()
        return False

    def reset(self):
        self._backend.reset()

    def update(self) -> OrientationState:
        return self._backend.update()

    @property
    def state(self) -> OrientationState:
        return self._backend._state
