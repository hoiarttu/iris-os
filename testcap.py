"""
test_cap_pocket.py — pocket cap hold tester + IMU monitor
Stick it in your pocket and watch the output.
Ctrl+C to exit.
"""

import time
import math

ESP32_BUS     = 11
ESP32_ADDRESS = 0x42
IMU_ADDRESS   = 0x68
IMU_BUS       = 11

# ── Hardware init ─────────────────────────────────────────────────────────────

try:
    import smbus2
    bus = smbus2.SMBus(ESP32_BUS)
    print(f'[OK] ESP32 found on bus {ESP32_BUS}')
except Exception as e:
    print(f'[FAIL] Could not connect to ESP32: {e}')
    exit(1)

try:
    from mpu6050 import mpu6050
    imu = mpu6050(IMU_ADDRESS, bus=IMU_BUS)
    imu_ok = True
    print(f'[OK] MPU6050 found')
except Exception as e:
    imu = None
    imu_ok = False
    print(f'[WARN] IMU unavailable: {e}')

print('Monitoring caps + IMU... Ctrl+C to stop.\n')

# ── State ─────────────────────────────────────────────────────────────────────

alpha_since = None
beta_since  = None
both_since  = None
warned_10   = warned_15 = warned_20 = False

yaw         = 0.0
pitch       = 0.0
last_imu_t  = time.time()
still_timer = 0.0
prev_yaw    = 0.0
prev_pitch  = 0.0

IMU_PRINT_INTERVAL = 2.0
last_imu_print     = 0.0

# ── Helpers ───────────────────────────────────────────────────────────────────

def ts():
    return time.strftime("%H:%M:%S")

def read_imu(dt):
    global yaw, pitch
    if not imu_ok:
        return
    try:
        g     = imu.get_gyro_data()
        yaw   = (yaw + g['x'] * dt) % 360.0
        pitch = max(-89.0, min(89.0, pitch + g['z'] * dt))
    except Exception:
        pass

# ── Main loop ─────────────────────────────────────────────────────────────────

while True:
    try:
        now = time.time()
        dt  = now - last_imu_t
        last_imu_t = now

        # ── IMU ───────────────────────────────────────────────────────────────
        read_imu(dt)

        dyaw   = abs(yaw   - prev_yaw)
        dpitch = abs(pitch - prev_pitch)
        moving = (dyaw + dpitch) > 0.4
        prev_yaw, prev_pitch = yaw, pitch

        if moving:
            still_timer = 0.0
        else:
            still_timer += dt

        if now - last_imu_print >= IMU_PRINT_INTERVAL:
            last_imu_print = now
            still_str  = f'{still_timer:.0f}s still'
            dlp_warn   = ' ⚠️  DLP sleeps at 30s!' if still_timer >= 25.0 else ''
            pitch_warn = ' 🚨 bad orientation — DLP would cut' if pitch < -75.0 else ''
            if imu_ok:
                print(f'  [IMU] yaw={yaw:.1f}°  pitch={pitch:.1f}°  {still_str}{dlp_warn}{pitch_warn}')
            else:
                print(f'  [IMU] unavailable  {still_str}{dlp_warn}')

        # ── Caps ──────────────────────────────────────────────────────────────
        status = bus.read_byte_data(ESP32_ADDRESS, 0x00)
        alpha  = bool(status & 0x01)
        beta   = bool(status & 0x02)

        if alpha and alpha_since is None:
            alpha_since = now
            print(f'[{ts()}] ALPHA pressed')
        elif not alpha and alpha_since is not None:
            print(f'[{ts()}] ALPHA released — held {now - alpha_since:.2f}s')
            alpha_since = None

        if beta and beta_since is None:
            beta_since = now
            print(f'[{ts()}] BETA pressed')
        elif not beta and beta_since is not None:
            print(f'[{ts()}] BETA released — held {now - beta_since:.2f}s')
            beta_since = None

        if alpha and beta:
            if both_since is None:
                both_since = now
                warned_10 = warned_15 = warned_20 = False
                print(f'[{ts()}] BOTH held — watching...')
            else:
                held = now - both_since
                if held >= 10.0 and not warned_10:
                    warned_10 = True
                    print(f'  ⚠️  10s — getting spicy')
                if held >= 15.0 and not warned_15:
                    warned_15 = True
                    print(f'  ⚠️  15s — danger zone')
                if held >= 20.0 and not warned_20:
                    warned_20 = True
                    print(f'  🚨 20s — THIS WOULD HAVE WIPED + SHUTDOWN')
        else:
            if both_since is not None:
                print(f'[{ts()}] BOTH released — held {now - both_since:.2f}s total')
                both_since = None

        time.sleep(0.05)

    except KeyboardInterrupt:
        print('\nDone.')
        break
    except Exception as e:
        print(f'[ERR] {e}')
        time.sleep(0.5)
