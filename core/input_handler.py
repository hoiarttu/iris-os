"""
core/input_handler.py

Cap touch input handler — ESP32 I2C at 0x42 on bus 11.

Register map:
  0x00 R   status byte (bit0=Alpha, bit1=Beta)
  0x01 W   RGB R
  0x02 W   RGB G
  0x03 W   RGB B
  0x04 W   RGB mode (0=static,1=pulse,2=blink,3=off)
  0x05 W   FET LED brightness (0-255)
  0x08 W   Heartbeat
"""

import time

# ── Feature Keep: Constants ───────────────────────────────────────────────────
EVT_BACK       = 'back'
EVT_CONFIRM    = 'confirm'
EVT_HOME       = 'home'

ESP32_BUS      = 11
ESP32_ADDRESS  = 0x42
HOLD_SECS      = 0.5
MIN_PRESS_SECS = 0.08  # Cap must be held this long before release counts

class InputHandler:

    def __init__(self):
        # ── Feature Keep: Original State Variables ────────────────────────────
        self._mock_queue  = []
        self._bus         = None
        self._last_hb     = 0.0
        self._connected   = False
        self._alpha_held  = False
        self._beta_held   = False
        self._alpha_since = 0.0
        self._beta_since  = 0.0
        self._both_fired  = False

        # ── Resilience Tracking ───────────────────────────────────────────────
        self._error_count = 0
        
        # Initial hardware attempt
        self._init_bus()

    def _init_bus(self):
        """Feature Keep: Graceful fallback to mock mode if on Desktop."""
        try:
            import smbus2
            # Physically reset the bus handle if it exists
            if self._bus:
                try: self._bus.close()
                except: pass
            self._bus = smbus2.SMBus(ESP32_BUS)
            print(f'[Input] ESP32 connected at 0x42 on Bus {ESP32_BUS}')
            self._error_count = 0
        except Exception as e:
            # If on Laptop/Mac, this falls back to Mock Mode
            if self._bus is None:
                print(f'[Input] ESP32 unavailable ({e}) — mock mode')
            self._bus = None

    def get_events(self) -> list:
        """Feature Keep: Combined Hardware + Mock Event stream."""
        events = []
        
        # 1. Hardware Poll
        if self._bus is not None:
            events.extend(self._poll_esp32())
        else:
            # If we're on Pi but bus glitched, try a quiet re-init
            self._init_bus()

        # 2. Mock Poll (Keyboard hits from main.py)
        if self._mock_queue:
            events.extend(self._mock_queue)
            self._mock_queue.clear()
            
        return events

    def _poll_esp32(self) -> list:
        hw_events = []
        try:
            now = time.time()

            # ── Feature Keep: Heartbeat + Connect Sync ────────────────────────
            if now - self._last_hb >= 1.0:
                # Register 0x08 heartbeat
                self._bus.write_byte_data(ESP32_ADDRESS, 0x08, 0x01)
                if not self._connected:
                    self._connected = True
                    # Register 0x01-0x03 system cyan (solid)
                    self.set_led(80, 220, 255, 0)
                    print('[Input] Handshake success — LED synced')
                self._last_hb = now

            # ── Feature Keep: Register 0x00 Status ────────────────────────────
            status = self._bus.read_byte_data(ESP32_ADDRESS, 0x00)
            self._error_count = 0 
            
            alpha = bool(status & 0x01)
            beta  = bool(status & 0x02)

            # ── Feature Keep: Press timing ────────────────────────────────────
            if alpha and not self._alpha_held:
                self._alpha_since = now
            if beta and not self._beta_held:
                self._beta_since = now

            both = alpha and beta

            # ── Feature Keep: Release Logic ───────────────────────────────────
            # Alpha alone released = back
            if not alpha and self._alpha_held and not both:
                if now - self._alpha_since >= MIN_PRESS_SECS:
                    hw_events.append(EVT_BACK)

            # Beta alone released = confirm
            if not beta and self._beta_held and not both:
                if now - self._beta_since >= MIN_PRESS_SECS:
                    hw_events.append(EVT_CONFIRM)

            self._alpha_held = alpha
            self._beta_held  = beta

        except Exception as e:
            # Resilience: Auto-healing for the I2C line
            self._error_count += 1
            self._connected = False
            if self._error_count >= 5:
                print(f'[Input] persistent I2C error: {e}. Re-initializing...')
                self._init_bus()

        return hw_events

    def mock_push(self, event: str):
        """Feature Keep: Desktop keyboard shortcut support."""
        self._mock_queue.append(event)

    def set_led(self, r: int, g: int, b: int, mode: int = 0):
        """Feature Keep: Register 0x01-0x04 control."""
        if self._bus is None: return
        try:
            # Block write to registers 0x01, 0x02, 0x03, 0x04
            self._bus.write_i2c_block_data(ESP32_ADDRESS, 0x01, [r, g, b, mode])
        except Exception as e:
            print(f'[Input] LED write error: {e}')

    def set_fet(self, brightness: int):
        """Feature Keep: Register 0x05 control."""
        if self._bus is None: return
        try:
            self._bus.write_byte_data(ESP32_ADDRESS, 0x05, brightness)
        except Exception as e:
            print(f'[Input] FET write error: {e}')
