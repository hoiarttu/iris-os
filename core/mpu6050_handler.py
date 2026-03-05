"""
core/mpu6050_handler.py
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

    def __repr__(self):
        return (f'OrientationState('
                f'yaw={self.yaw:.1f}, pitch={self.pitch:.1f}, '
                f'roll={self.roll:.1f})')


class RealIMU:
    __slots__ = ('sensor', 'yaw_axis', 'pitch_axis', 'roll_axis',
                 'alpha', '_bias', '_state', '_last_time')
    _AXES = ('x', 'y', 'z')

    def __init__(self, address, bus, yaw_axis, pitch_axis, roll_axis, alpha):
        from mpu6050 import mpu6050 as _lib
        self.sensor     = _lib(address, bus=bus)
        self.yaw_axis   = yaw_axis
        self.pitch_axis = pitch_axis
        self.roll_axis  = roll_axis
        self.alpha      = alpha
        self._bias      = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self._state     = OrientationState()
        self._last_time = time.time()

    def calibrate(self, samples=200):
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
        print(f'[IMU] Bias: {self._bias}')
        return self._bias

    def reset(self):
        self._state     = OrientationState()
        self._last_time = time.time()

    def update(self):
        now = time.time()
        dt  = min(now - self._last_time, 0.1)
        self._last_time = now

        gyro  = self.sensor.get_gyro_data()
        accel = self.sensor.get_accel_data()

        self._state.yaw   = (self._state.yaw +
            (gyro[self.yaw_axis]   - self._bias[self.yaw_axis])   * dt) % 360.0
        self._state.pitch += (gyro[self.pitch_axis] - self._bias[self.pitch_axis]) * dt
        self._state.roll  += (gyro[self.roll_axis]  - self._bias[self.roll_axis])  * dt

        ax, ay, az = accel['x'], accel['y'], accel['z']
        ap = math.degrees(math.atan2(-ax, math.sqrt(ay*ay + az*az)))
        ar = math.degrees(math.atan2(ay, az))

        a = self.alpha
        self._state.pitch = max(-90.0, min(90.0, a * self._state.pitch + (1-a) * ap))
        self._state.roll  = max(-90.0, min(90.0, a * self._state.roll  + (1-a) * ar))
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

    def calibrate(self, samples=0, **_):
        pass

    def reset(self):
        self._state     = OrientationState()
        self._last_time = time.time()

    def update(self):
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

    def reset(self):
        self._backend.reset()

    def update(self):
        return self._backend.update()

    @property
    def state(self):
        return self._backend._state
