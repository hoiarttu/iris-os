"""
apps/settings_app.py — IRIS Settings
─────────────────────────────────────────────────────────────────────────────
Navigation:
  Hand cursor hover  → highlight item
  Beta tap           → select / toggle / confirm
  Alpha tap          → scroll up
  Both caps hold     → home (system)
"""

import os, json, subprocess, time
import pygame
from apps.base_app import BaseApp
from core.display import WIDTH, HEIGHT, BLACK, WHITE, ACCENT
from core.config  import load_config, save_config

_MONO_BOLD = 'assets/fonts/Rajdhani-Bold.ttf'
_MONO      = 'assets/fonts/Rajdhani-Regular.ttf'

# ── Design constants ──────────────────────────────────────────────────────────

BG          = (  0,   0,   0)
COL_IDLE    = ( 80,  40, 180)
COL_SEL     = ( 80, 220, 255)
COL_DIM     = ( 60,  60,  70)
COL_WARN    = (255, 220,  50)
COL_CRIT    = (255,  80,  80)
COL_TEXT    = (200, 200, 220)
COL_SUBTEXT = (120, 120, 140)

ITEM_H      = 52
ITEM_W      = WIDTH - 80
ITEM_X      = 40
ITEM_Y0     = 60

# ── Accent palette ────────────────────────────────────────────────────────────

ACCENTS = [
    ((80,  220, 255), 'IRIS Cyan'),
    ((255,  80,  80), 'Red'),
    ((80,  255, 120), 'Green'),
    ((255, 220,  50), 'Yellow'),
    ((180,  80, 255), 'Purple'),
    ((255, 160,  40), 'Orange'),
    ((255, 255, 255), 'White'),
]


class SettingsApp(BaseApp):
    name          = 'Settings'
    description   = 'System settings'
    pin_mode      = 'pinned'
    show_cursor   = True
    cap_hold_secs = 0.0

    def __init__(self):
        super().__init__()
        self._os_ref    = None
        self._config    = load_config()

        # Fonts
        self._f_title = pygame.font.Font(_MONO_BOLD, 32)
        self._f_item  = pygame.font.Font(_MONO_BOLD, 20)
        self._f_sub   = pygame.font.Font(_MONO,      14)
        self._f_small = pygame.font.Font(_MONO_BOLD, 14)

        fn = pygame.font.Font(_MONO_BOLD, 20)
        fi = pygame.font.Font(_MONO_BOLD, 16)
        self._name_surf = fn.render('SETTINGS', True, WHITE)
        self._icon_surf = fi.render('SE',       True, WHITE)

        # Cursor state
        self._hover_idx = 0
        self._hand_x    = 0.5
        self._hand_y    = 0.5

        # Submenu state
        self._submenu       = None   # None | 'wifi' | 'accent'
        self._submenu_items = []
        self._submenu_hover = 0

        # Async op state
        self._status_msg  = ''
        self._status_t    = 0.0
        self._status_action = None
        self._calibrating = False
        self._calibrate_t = 0.0

        # Build menu
        self._build_menu()

    # ── Menu definition ───────────────────────────────────────────────────────

    def _build_menu(self):
        wifi_ssid = self._get_current_wifi()
        bt_on     = self._get_bt()

        self._items = [
            {'label': 'WiFi',
             'sub':   wifi_ssid or 'not connected',
             'action': 'wifi'},
            {'label': 'Bluetooth',
             'sub':   'on' if bt_on else 'off',
             'action': 'bt_toggle'},
            {'label': 'Accent Color',
             'sub':   self._accent_name(),
             'action': 'accent'},
            {'label': 'Recalibrate IMU',
             'sub':   'hold still during calibration',
             'action': 'recalibrate'},
            {'label': 'Software Update',
             'sub':   'git pull from github',
             'action': 'update'},
            {'label': 'Reboot',
             'sub':   'restart raspberry pi',
             'action': 'reboot'},
            {'label': 'Shutdown',
             'sub':   'power off',
             'action': 'shutdown'},
            {'label': 'About',
             'sub':   self._get_about(),
             'action': 'about'},
        ]

    # ── System reads ──────────────────────────────────────────────────────────

    def _get_current_wifi(self):
        try:
            return subprocess.check_output(
                ['iwgetid', '-r'], text=True).strip()
        except:
            return None

    def _get_known_wifi(self):
        networks = []
        try:
            with open('/etc/wpa_supplicant/wpa_supplicant.conf') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('ssid='):
                        networks.append(line[6:-1])  # strip ssid=" and "
        except:
            pass
        return networks

    def _get_bt(self):
        try:
            out = subprocess.check_output(['hciconfig'], text=True)
            return 'UP RUNNING' in out
        except:
            return False

    def _get_about(self):
        try:
            import socket
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            uptime = open('/proc/uptime').read().split()[0]
            mins   = int(float(uptime)) // 60
            return f'{hostname}  {ip}  up {mins}m'
        except:
            return 'IRIS OS'

    def _accent_name(self):
        current = tuple(self._config.get('accent', [80, 220, 255]))
        for rgb, name in ACCENTS:
            if rgb == current:
                return name
        return 'Custom'

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_action(self, action):
        if action == 'wifi':
            networks = self._get_known_wifi()
            if networks:
                self._submenu       = 'wifi'
                self._submenu_items = networks
                self._submenu_hover = 0
            else:
                self._set_status('No known networks found')

        elif action == 'bt_toggle':
            try:
                bt = self._get_bt()
                if bt:
                    subprocess.Popen(['sudo', 'hciconfig', 'hci0', 'down'])
                    self._set_status('Bluetooth off')
                else:
                    subprocess.Popen(['sudo', 'hciconfig', 'hci0', 'up'])
                    self._set_status('Bluetooth on')
                self._build_menu()
            except Exception as e:
                self._set_status(f'BT error: {e}')

        elif action == 'accent':
            self._submenu       = 'accent'
            self._submenu_items = [name for _, name in ACCENTS]
            self._submenu_hover = 0

        elif action == 'recalibrate':
            if self._os_ref:
                self._set_status('Hold still — starting in 3s...')
                self._calibrating = True
                self._calibrate_t = time.time()

        elif action == 'update':
            self._set_status('Updating...')
            try:
                result = subprocess.check_output(
                    ['git', 'pull'], cwd='/home/iris/mirage_gui',
                    text=True, stderr=subprocess.STDOUT)
                self._set_status('Updated! Restart to apply.')
            except Exception as e:
                self._set_status(f'Update failed: {e}')

        elif action == 'reboot':
            self._set_status('Rebooting...')
            if self._os_ref:
                self._os_ref._power_action('reboot')

        elif action == 'shutdown':
            self._set_status('Shutting down...')
            if self._os_ref:
                self._os_ref._power_action('shutdown')

        elif action == 'about':
            self._set_status(self._get_about())

    def _do_submenu_action(self, idx):
        if self._submenu == 'wifi':
            ssid = self._submenu_items[idx]
            try:
                subprocess.Popen(
                    ['sudo', 'wpa_cli', '-i', 'wlan0', 'select_network',
                     str(idx)])
                self._set_status(f'Connecting to {ssid}...')
            except Exception as e:
                self._set_status(f'WiFi error: {e}')
            self._submenu = None
            self._build_menu()

        elif self._submenu == 'accent':
            rgb, name = ACCENTS[idx]
            self._config['accent'] = list(rgb)
            save_config(self._config)
            if self._os_ref:
                self._os_ref._apply_accent(list(rgb))
            self._set_status(f'Accent: {name}')
            self._submenu = None
            self._build_menu()

    def _set_status(self, msg):
        self._status_msg = msg
        self._status_t   = time.time()

    # ── Kernel hooks ──────────────────────────────────────────────────────────

    def launch(self):
        # os_ref injected by kernel after construction
        pass

    def update(self, dt):
        # Handle calibration with countdown
        if self._calibrating and self._os_ref:
            elapsed = time.time() - self._calibrate_t
            remaining = 3.0 - elapsed
            self._status_action = 'recalibrate'
            if remaining > 0:
                self._status_msg = f'Hold still — {remaining:.0f}s...'
                self._status_t   = time.time()
            elif not getattr(self, '_cal_thread_started', False):
                self._cal_thread_started = True
                self._os_ref._cal_thread_started = True
                self._set_status('Calibrating — hold still...')
                import threading as _th
                def _do_cal():
                    try:
                        self._os_ref.imu.calibrate(500)
                    except Exception as e:
                        print(f'[Settings] Calib error: {e}')
                    finally:
                        self._calibrating        = False
                        self._cal_thread_started = False
                        self._os_ref._cal_thread_started = False
                        self._set_status('Done! Calibration saved.')
                _th.Thread(target=_do_cal, daemon=True).start()

        # Rebuild about string periodically
        if int(time.time()) % 10 == 0:
            if self._items:
                self._items[-1]['sub'] = self._get_about()

    def on_imu(self, imu_state, hand=None):
        self._imu_state = imu_state
        items = self._submenu_items if self._submenu else self._items
        n = len(items)

        if hand and hand.active:
            self._hand_x = hand.x
            self._hand_y = hand.y
            import math
            from core.geometry import angle_diff
            from core.display import WIDTH, HEIGHT
            # Compute pinned-canvas offset same as kernel
            mirage_az = 0.0
            if self._os_ref and self._os_ref._active_mirage:
                mirage_az = self._os_ref._active_mirage.azimuth
            PX_YAW, PX_PITCH = 28, 24
            yaw_diff = angle_diff(imu_state.yaw, mirage_az)
            yaw_sign = 1 if ((imu_state.yaw - mirage_az + 360) % 360) < 180 else -1
            dx = -yaw_sign * yaw_diff * PX_YAW
            dy = -imu_state.pitch * PX_PITCH
            roll_rad = math.radians(imu_state.roll)
            cr, sr = math.cos(roll_rad), math.sin(roll_rad)
            ox = int(cr * dx - sr * dy)
            oy = int(sr * dx + cr * dy)
            canvas_x = hand.x * WIDTH  - ox
            canvas_y = hand.y * HEIGHT - oy
            hit = None
            for i in range(n):
                iy = ITEM_Y0 + i * ITEM_H
                if ITEM_X <= canvas_x <= ITEM_X + ITEM_W and iy <= canvas_y <= iy + ITEM_H:
                    hit = i
                    break
            if self._submenu:
                self._submenu_hover = hit if hit is not None else self._submenu_hover
            else:
                self._hover_idx = hit

        else:
            # No hand — use pitch to navigate: tilt down = go down the list
            # Pitch range roughly -30 to +30 covers the menu
            pitch_clamped = max(-30.0, min(30.0, imu_state.pitch))
            idx = int((pitch_clamped + 30.0) / 60.0 * n)
            idx = max(0, min(n - 1, idx))
            if self._submenu:
                self._submenu_hover = idx
            else:
                self._hover_idx = idx

    def _handle_beta(self):
        if self._submenu:
            if self._submenu_hover is None:
                return
            self._status_action = self._submenu_items[self._submenu_hover]
            self._do_submenu_action(self._submenu_hover)
        else:
            if self._hover_idx is None:
                return
            action = self._items[self._hover_idx]['action']
            self._status_action = action
            self._do_action(action)

    def _handle_alpha(self):
        if self._submenu:
            self._submenu = None
        else:
            if self._hover_idx is None:
                self._hover_idx = 0
            else:
                self._hover_idx = max(0, self._hover_idx - 1)

    def _handle_alpha_held(self):
        pass   # prevent clear canvas from base

    def on_event(self, event):
        if event.type == pygame.KEYDOWN:
            n = len(self._submenu_items) if self._submenu else len(self._items)
            if event.key == pygame.K_UP:
                if self._submenu:
                    self._submenu_hover = max(0, self._submenu_hover - 1)
                else:
                    self._hover_idx = max(0, self._hover_idx - 1)
            elif event.key == pygame.K_DOWN:
                if self._submenu:
                    self._submenu_hover = min(n-1, self._submenu_hover + 1)
                else:
                    self._hover_idx = min(n-1, self._hover_idx + 1)
            elif event.key == pygame.K_RETURN:
                self._handle_beta()
            elif event.key == pygame.K_ESCAPE:
                if self._submenu:
                    self._submenu = None
            elif event.key == pygame.K_z:
                self._handle_alpha()
            elif event.key == pygame.K_x:
                self._handle_beta()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _draw_item(self, surface, idx, item, selected, y):
        x = ITEM_X
        w = ITEM_W
        h = ITEM_H

        # Background
        bg_col = (16, 16, 28) if not selected else (20, 20, 36)
        pygame.draw.rect(surface, bg_col, (x, y, w, h), border_radius=6)

        # Left accent bar
        bar_col = COL_SEL if selected else COL_IDLE
        pygame.draw.rect(surface, bar_col, (x, y, 4, h), border_radius=2)

        # Border
        pygame.draw.rect(surface, bar_col, (x, y, w, h), 1, border_radius=6)

        # Label
        lbl = self._f_item.render(item['label'], True,
                                   COL_SEL if selected else COL_TEXT)
        surface.blit(lbl, (x + 16, y + 8))

        # Subtext
        sub = self._f_sub.render(item['sub'], True, COL_SUBTEXT)
        surface.blit(sub, (x + 16, y + 30))

        # Right-aligned status
        import time
        is_status_target = (item.get('action') == getattr(self, '_status_action', None)) or (item.get('label') == getattr(self, '_status_action', None))
        if is_status_target and self._status_msg and time.time() - self._status_t < 4.0:
            sm = self._f_small.render(self._status_msg, True, COL_SEL)
            surface.blit(sm, (x + w - sm.get_width() - 16, y + h // 2 - sm.get_height() // 2))

    def draw_fullscreen(self, surface):
        surface.fill(BG)
        W, H = surface.get_size()

        # Title
        t = self._f_title.render('SETTINGS', True, COL_SEL)
        surface.blit(t, (ITEM_X, 14))
        pygame.draw.line(surface, COL_DIM, (ITEM_X, 54),
                         (ITEM_X + ITEM_W, 54), 1)

        items  = self._submenu_items if self._submenu else [i['label'] for i in self._items]
        hover  = self._submenu_hover if self._submenu else self._hover_idx
        source = self._submenu_items if self._submenu else self._items

        if self._submenu:
            # Submenu title
            st = self._f_item.render(
                self._submenu.upper(), True, COL_SUBTEXT)
            surface.blit(st, (ITEM_X, ITEM_Y0 - 22))

            for i, name in enumerate(self._submenu_items):
                y   = ITEM_Y0 + i * ITEM_H
                sel = (i == hover)
                self._draw_item(surface, i,
                                {'label': name, 'sub': ''},
                                sel, y)
        else:
            for i, item in enumerate(self._items):
                y   = ITEM_Y0 + i * ITEM_H
                sel = (hover is not None and i == hover)
                if y + ITEM_H > H - 30:
                    break
                self._draw_item(surface, i, item, sel, y)


        # Hint
        hint = self._f_sub.render(
            'β=select  α=back/up', True, COL_DIM)
        surface.blit(hint, (W - hint.get_width() - 20, H - 20))

    def draw_icon(self, surface, center, radius):
        r = self._icon_surf.get_rect(center=center)
        surface.blit(self._icon_surf, r)

    def draw_widget(self, surface, rect):
        nr = self._name_surf.get_rect(centerx=rect.centerx,
                                       centery=rect.centery)
        surface.blit(self._name_surf, nr)
