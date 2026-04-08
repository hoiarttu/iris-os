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

EVT_BACK    = 'back'
EVT_CONFIRM = 'confirm'
EVT_HOME    = 'home'

ESP32_BUS     = 11
ESP32_ADDRESS = 0x42
HOLD_SECS     = 0.5


class InputHandler:

    def __init__(self):
        self._mock_queue  = []
        self._bus         = None
        self._last_hb     = 0.0
        self._connected   = False
        self._alpha_held  = False
        self._beta_held   = False
        self._alpha_since = 0.0
        self._beta_since  = 0.0
        self._both_fired  = False

        try:
            import smbus2
            self._bus = smbus2.SMBus(ESP32_BUS)
            print('[Input] ESP32 connected at 0x42')
        except Exception as e:
            print(f'[Input] ESP32 unavailable ({e}) — mock mode')

    def get_events(self) -> list:
        if self._bus is None:
            return self._drain_mock()
        return self._poll_esp32()

    def _poll_esp32(self) -> list:
        events = []
        try:
            now = time.time()

            # Heartbeat — also sends LED color on first connect
            if now - self._last_hb >= 1.0:
                self._bus.write_byte_data(ESP32_ADDRESS, 0x08, 0x01)
                if not self._connected:
                    self._connected = True
                    self.set_led(80, 220, 255, 0)  # solid cyan on connect
                    print('[Input] LED set to system color')
                self._last_hb = now

            # Read status byte
            status = self._bus.read_byte_data(ESP32_ADDRESS, 0x00)
            alpha = bool(status & 0x01)
            beta  = bool(status & 0x02)

            # Track press timing Pi-side
            if alpha and not self._alpha_held:
                self._alpha_since = now
            if beta and not self._beta_held:
                self._beta_since = now

            both = alpha and beta

            # Both caps = home
            if both and not self._both_fired:
                events.append(EVT_HOME)
                self._both_fired = True
            if not both:
                self._both_fired = False

            # Alpha alone released = back
            if not alpha and self._alpha_held and not beta:
                events.append(EVT_BACK)

            # Beta alone released = confirm
            if not beta and self._beta_held and not alpha:
                events.append(EVT_CONFIRM)

            self._alpha_held = alpha
            self._beta_held  = beta

        except Exception as e:
            print(f'[Input] Read error: {e}')
            self._connected = False

        return events

    def mock_push(self, event: str):
        self._mock_queue.append(event)

    def _drain_mock(self) -> list:
        events = list(self._mock_queue)
        self._mock_queue.clear()
        return events

    def set_led(self, r: int, g: int, b: int, mode: int = 0):
        """Send accent color and mode to ESP32 RGB LED."""
        if self._bus is None:
            return
        try:
            self._bus.write_i2c_block_data(ESP32_ADDRESS, 0x01, [r, g, b, mode])
        except Exception as e:
            print(f'[Input] LED write error: {e}')

    def set_fet(self, brightness: int):
        """Set illumination LED brightness 0-255."""
        if self._bus is None:
            return
        try:
            self._bus.write_byte_data(ESP32_ADDRESS, 0x05, brightness)
        except Exception as e:
            print(f'[Input] FET write error: {e}')
