"""
core/hand_client.py

Reads hand cursor data from hand_tracker.py via Unix socket.
Non-blocking — never stalls the render loop.
Returns last known position if no new data this frame.
"""

import socket
import os

SOCKET_PATH = '/tmp/iris_hand.sock'


class HandClient:

    def __init__(self):
        self.x      = 0.5
        self.y      = 0.5
        self.pinch  = False
        self.fist   = False   # set True when landmark model detects closed fist
        self.scale  = 1.0    # relative palm bbox scale (for grab push/pull detection)
        self.active = False   # True when hand is detected
        self._sock  = None
        self._buf   = ''
        self._connect()

    def _connect(self):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCKET_PATH)
            s.setblocking(False)
            self._sock = s
            print('[HandClient] Connected to tracker')
        except Exception:
            self._sock = None

    def update(self):
        """
        Call once per frame. Reads all available data from socket.
        Updates self.x, self.y, self.pinch, self.active.
        Non-blocking — returns immediately if no data.
        """
        if self._sock is None:
            if os.path.exists(SOCKET_PATH):
                self._connect()
            return

        try:
            data = self._sock.recv(4096).decode()
            if not data:
                self._sock = None
                self.active = False
                return
            self._buf += data
            lines = self._buf.split('\n')
            self._buf = lines[-1]
            # Use only the latest complete line
            for line in reversed(lines[:-1]):
                line = line.strip()
                if not line:
                    continue
                import json
                msg = json.loads(line)
                self.x      = msg['x']
                self.y      = msg['y']
                self.pinch  = msg['pinch']
                self.active = True
                break
        except BlockingIOError:
            pass
        except Exception:
            self._sock = None
            self.active = False
