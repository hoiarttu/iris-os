"""
hand_tracker.py — Hand cursor process v15 (Fingertip Tracker & Rolling Buffer)
─────────────────────────────────────────────────────────────────────────────
Upgrades:
  - Replaced bounding boxes and moments with the 'Topmost Pixel' (Fingertip) 
    to stop the blob shape-shift effect.
  - Implemented a Rolling Frame Buffer (Moving Average) to completely 
    absorb zig-zags and enforce perfectly straight lines.
"""

import cv2
import numpy as np
import socket, os, json, time, threading
from collections import deque

SOCKET_PATH      = '/tmp/iris_hand.sock'
CAMERA_INDEX     = 0
TARGET_FPS       = 20     

# --- HSV SKIN COLOR CALIBRATION ---
LOWER_SKIN = np.array([0, 20, 70], dtype=np.uint8)
UPPER_SKIN = np.array([20, 255, 255], dtype=np.uint8)

MIN_AREA   = 400          

# --- DELAY vs. SMOOTHNESS TUNING ---
# How many frames to average together. 
# 6 frames @ 20 FPS = ~300ms delay. Increase to 10 for a heavier, smoother feel.
BUFFER_SIZE = 6

# --- VIRTUAL TRACKPAD BOUNDARIES ---
RAW_X_LEFT  = 0.60  
RAW_X_RIGHT = 0.10  
RAW_Y_UP    = 0.30  
RAW_Y_DOWN  = 0.05  

# ─── THREADED CAMERA I/O ────────────────────────────────────────────
class CameraStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y','U','Y','V'))
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 160)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)
        self.frame = None
        self.stopped = False
        
        if not self.stream.isOpened():
            print('[Pointer] Camera failed to open')
            self.stopped = True
            
    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            grabbed, frame = self.stream.read()
            if grabbed:
                self.frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            time.sleep(0.01)

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()

# ─── UTILS ──────────────────────────────────────────────────────────
def make_socket():
    if os.path.exists(SOCKET_PATH): os.remove(SOCKET_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    srv.listen(1)
    srv.setblocking(False)
    os.chmod(SOCKET_PATH, 0o666)
    return srv

def remap(sx, sy):
    mx = (sx - RAW_X_LEFT) / (RAW_X_RIGHT - RAW_X_LEFT)
    my = (sy - RAW_Y_UP) / (RAW_Y_DOWN - RAW_Y_UP)
    return max(0.0, min(1.0, mx)), max(0.0, min(1.0, my))

# ─── MAIN LOOP ──────────────────────────────────────────────────────
def main():
    print('[Pointer] Starting v15 (Fingertip & Rolling Buffer)...')

    vs = CameraStream(CAMERA_INDEX).start()
    time.sleep(1.0) 
    if vs.stopped: return

    frame = vs.read()
    fh, fw = frame.shape[:2]
    print(f'[Pointer] Frame: {fw}x{fh} @ {TARGET_FPS} FPS')

    srv    = make_socket()
    client = None
    delay  = 1.0 / TARGET_FPS

    # Set up the rolling buffers
    hist_x = deque(maxlen=BUFFER_SIZE)
    hist_y = deque(maxlen=BUFFER_SIZE)
    
    # Final smoothed output coordinates
    sx = (RAW_X_LEFT + RAW_X_RIGHT) / 2.0
    sy = (RAW_Y_UP + RAW_Y_DOWN) / 2.0
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    print(f'[Pointer] Ready. Frame Buffer set to {BUFFER_SIZE}.')

    try:
        while True:
            t0 = time.time()

            if client is None:
                try:
                    client, _ = srv.accept()
                    client.setblocking(False)
                    print('[Pointer] IRIS connected')
                except BlockingIOError: pass

            frame = vs.read()
            if frame is None: continue

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, LOWER_SKIN, UPPER_SKIN)

            mask = cv2.erode(mask, kernel, iterations=1)
            mask = cv2.dilate(mask, kernel, iterations=2)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            found_hand = False

            if contours:
                best_contour = max(contours, key=cv2.contourArea)
                if cv2.contourArea(best_contour) > MIN_AREA:
                    
                    # --- THE FINGERTIP TRACKER ---
                    # Ignore the center of mass. Find the absolute topmost point (lowest Y).
                    topmost = tuple(best_contour[best_contour[:, :, 1].argmax()][0])
                    
                    raw_x = topmost[0] / fw
                    raw_y = topmost[1] / fh
                    
                    # Add new points to the rolling buffer
                    hist_x.append(raw_x)
                    hist_y.append(raw_y)
                    
                    found_hand = True

            if found_hand and len(hist_x) > 0:
                # --- THE ROLLING AVERAGE MATH ---
                # Calculate the exact center of the history buffer to draw a perfectly straight line
                avg_x = sum(hist_x) / len(hist_x)
                avg_y = sum(hist_y) / len(hist_y)
                
                # Apply a gentle final glide to the averaged point
                sx = sx * 0.7 + avg_x * 0.3
                sy = sy * 0.7 + avg_y * 0.3
                
            else:
                # When hand is put down, clear the buffer and drift to center
                hist_x.clear()
                hist_y.clear()
                
                target_x = (RAW_X_LEFT + RAW_X_RIGHT) / 2.0
                target_y = (RAW_Y_UP + RAW_Y_DOWN) / 2.0
                
                sx = sx * 0.9 + target_x * 0.1
                sy = sy * 0.9 + target_y * 0.1

            if client is not None:
                mx, my = remap(sx, sy)
                
                print(f'[BUFFER: {len(hist_x)}] out=({mx:.2f},{my:.2f})    ', end='\r')
                
                try:
                    msg = json.dumps({'x': mx, 'y': my, 'pinch': False}) + '\n'
                    client.sendall(msg.encode())
                except (BrokenPipeError, BlockingIOError):
                    client = None

            elapsed = time.time() - t0
            wait    = delay - elapsed
            if wait > 0: time.sleep(wait)
                
    except KeyboardInterrupt:
        print("\n[Pointer] Shutting down...")
    finally:
        vs.stop()

if __name__ == '__main__':
    main()
