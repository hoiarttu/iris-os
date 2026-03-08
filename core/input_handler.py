"""
core/input_handler.py

Cap touch input handler.
─────────────────────────────────────────────────────────────────────────────
Currently a stub — ESP32 firmware not ready yet.
When ready, replace _poll_esp32() with real I2C reads.

ESP32 I2C protocol (to be defined):
  Read 1 byte from ESP32 address on bus 11.
  Bit 0 = left cap touch
  Bit 1 = right cap touch
  Both bits = home gesture
"""

EVT_BACK    = 'back'
EVT_CONFIRM = 'confirm'
EVT_HOME    = 'home'

ESP32_BUS     = 11
ESP32_ADDRESS = 0x42


class InputHandler:

    def __init__(self):
        self._mock_queue    = []
        self._real_hardware = False
        print('[Input] Mock input active — ESP32 firmware pending')

    def get_events(self) -> list:
        return self._drain_mock()

    def mock_push(self, event: str):
        self._mock_queue.append(event)

    def _drain_mock(self) -> list:
        events = list(self._mock_queue)
        self._mock_queue.clear()
        return events
