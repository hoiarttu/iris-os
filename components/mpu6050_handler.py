"""
core/mpu6050_handler.py

Hardware abstraction layer for the MPU6050 IMU.
Handles gyro integration, accelerometer fusion, calibration,
and drift correction. Designed to be consumed by any OS component
that needs orientation data — no pygame or display dependencies.
"""

import time
import math
from mpu6050 import mpu6050


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

class OrientationState:
    """Plain data object — decoupled from any sensor implementation."""
    __slots__ = ('yaw', 'pitch', 'roll', 'timestamp')

    def __init__(self, yaw=0.0, pitch=0.0, roll=0.0):
        self.yaw = yaw
        self.pitch = pitch
        self.roll = roll
        self.timestamp = time.time()

    def as_dict(self):
        return {'yaw': self.yaw, 'pitch': self.pitch, 'roll': self.roll}

    def __repr__(self):
        return (f'OrientationState(yaw={self.yaw:.1f}°, '
                f'pitch={self.pitch:.1f}°, roll={self.roll:.1f}°)')


# ---------------------------------------------------------------------------
# Axis mapping helper
# ---------------------------------------------------------------------------

AXIS_KEYS = ('x', 'y', 'z')

def _resolve_axis(name: str) -> str:
    name = name.lower().strip()
    if name not in AXIS_KEYS:
        raise ValueError(f"Axis must be one of {AXIS_KEYS}, got '{name}'")
    return name


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

class Mpu6050Handler:
    """
    Reads MPU6050 gyro + accelerometer and fuses them into
    yaw / pitch / roll using a complementary filter.

    Axis mapping lets you remap physical sensor axes to logical
    orientation axes without changing any caller code.

    Usage
    -----
        imu = Mpu6050Handler(bus=11, yaw_axis='x')
        imu.calibrate(samples=200)          # optional; call once at boot
        state = imu.update()                # returns OrientationState
        print(state.yaw, state.pitch)
    """

    def __init__(
        self,
        address: int = 0x68,
        bus: int = 1,
        yaw_axis: str = 'z',
        pitch_axis: str = 'y',
        roll_axis: str = 'x',
        alpha: float = 0.98,
    ):
        """
        Parameters
        ----------
        address   : I²C address of the sensor (default 0x68)
        bus       : I²C bus number (RPi usually 1; custom HATs may differ)
        yaw_axis  : which raw gyro axis drives yaw   ('x' | 'y' | 'z')
        pitch_axis: which raw gyro axis drives pitch
        roll_axis : which raw gyro axis drives roll
        alpha     : complementary filter weight (0..1).
                    Higher → trust gyro more; lower → trust accel more.
        """
        self.sensor = mpu6050(address, bus=bus)
        self.yaw_axis   = _resolve_axis(yaw_axis)
        self.pitch_axis = _resolve_axis(pitch_axis)
        self.roll_axis  = _resolve_axis(roll_axis)
        self.alpha = alpha

        self._state = OrientationState()
        self._bias = {'x': 0.0, 'y': 0.0, 'z': 0.0}   # gyro bias offsets
        self._last_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(self, samples: int = 200, delay: float = 0.005) -> dict:
        """
        Collect `samples` gyro readings at rest to estimate drift bias.
        Call once after boot before the main loop.

        Returns the bias dict for logging/persistence.
        """
        print(f"[IMU] Calibrating over {samples} samples — keep sensor still...")
        acc = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        for _ in range(samples):
            g = self.sensor.get_gyro_data()
            for ax in AXIS_KEYS:
                acc[ax] += g[ax]
            time.sleep(delay)
        self._bias = {ax: acc[ax] / samples for ax in AXIS_KEYS}
        # Reset integration after calibration
        self._state = OrientationState()
        self._last_time = time.time()
        print(f"[IMU] Bias: {self._bias}")
        return self._bias

    def reset(self):
        """Zero out all integrated angles."""
        self._state = OrientationState()
        self._last_time = time.time()

    def update(self) -> OrientationState:
        """
        Read sensor, integrate gyro, apply complementary filter for
        pitch and roll. Yaw remains gyro-only (no mag available).

        Returns
        -------
        OrientationState  — same object mutated in place for zero GC pressure.
        """
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        # Guard against absurd dt on first tick or after sleep
        dt = min(dt, 0.1)

        # --- Gyro (deg/s → deg) with bias removal ---
        gyro = self.sensor.get_gyro_data()
        gyro_yaw   = gyro[self.yaw_axis]   - self._bias[self.yaw_axis]
        gyro_pitch = gyro[self.pitch_axis] - self._bias[self.pitch_axis]
        gyro_roll  = gyro[self.roll_axis]  - self._bias[self.roll_axis]

        self._state.yaw   = (self._state.yaw + gyro_yaw * dt) % 360
        self._state.pitch += gyro_pitch * dt
        self._state.roll  += gyro_roll  * dt

        # --- Accelerometer tilt angles ---
        accel = self.sensor.get_accel_data()
        ax, ay, az = accel['x'], accel['y'], accel['z']

        accel_pitch = math.degrees(math.atan2(-ax, math.sqrt(ay*ay + az*az)))
        accel_roll  = math.degrees(math.atan2(ay, az))

        # --- Complementary filter ---
        self._state.pitch = self.alpha * self._state.pitch + (1 - self.alpha) * accel_pitch
        self._state.roll  = self.alpha * self._state.roll  + (1 - self.alpha) * accel_roll

        # Clamp pitch/roll to ±90° to avoid gimbal confusion
        self._state.pitch = max(-90.0, min(90.0, self._state.pitch))
        self._state.roll  = max(-90.0, min(90.0, self._state.roll))

        self._state.timestamp = now
        return self._state

    # ------------------------------------------------------------------
    # Properties for convenient one-liner reads
    # ------------------------------------------------------------------

    @property
    def yaw(self) -> float:
        return self._state.yaw

    @property
    def pitch(self) -> float:
        return self._state.pitch

    @property
    def roll(self) -> float:
        return self._state.roll
