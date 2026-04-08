"""
core/input_handler.py

Cap touch input handler — ESP32 I2C at 0x42 on bus 11.

Register map:
  0x00 R   status byte (bit0=Alpha, bit1=Beta)
  0x09 R   events byte (bit0=Alpha down, bit1=Alpha up,
                        bit2=Beta down,  bit3=Beta up)
  0x0A R   Alpha hold duration (units of 10ms)
  0x0B R   Beta  hold duration (units of 10ms)
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

HOLD_THRESHOLD = 50  # units of 10ms = 500ms for hold


class InputHandler:

    def __init__(self):
        self._mock_queue = []
        self._bus        = None
        self._last_hb    = 0.0
        self._alpha_held = False
        self._beta_held  = False

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
            # Heartbeat every second
            now = time.time()
            if now - self._last_hb >= 1.0:
                self._bus.write_byte_data(ESP32_ADDRESS, 0x08, 0x01)
                self._last_hb = now

            # Read event byte — self-clears on read
            evts = self._bus.read_byte_data(ESP32_ADDRESS, 0x09)

            alpha_down = bool(evts & 0x01)
            alpha_up   = bool(evts & 0x02)
            beta_down  = bool(evts & 0x04)
            beta_up    = bool(evts & 0x08)

            # Read hold durations
            alpha_hold = self._bus.read_byte_data(ESP32_ADDRESS, 0x0A)
            beta_hold  = self._bus.read_byte_data(ESP32_ADDRESS, 0x0B)

            both = self._bus.read_byte_data(ESP32_ADDRESS, 0x00)
            both_pressed = (both & 0x03) == 0x03

            # Both caps = home
            if both_pressed and not (self._alpha_held and self._beta_held):
                events.append(EVT_HOME)

            # Alpha alone = back
            if alpha_up and not beta_down:
                events.append(EVT_BACK)

            # Beta alone = confirm
            if beta_up and not alpha_down:
                events.append(EVT_CONFIRM)

            self._alpha_held = bool(both & 0x01)
            self._beta_held  = bool(both & 0x02)

        except Exception as e:
            print(f'[Input] Read error: {e}')

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
