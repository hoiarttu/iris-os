"""
hand_tracker.py — Hand cursor process v3
─────────────────────────────────────────────────────────────────────────────
Improvements over v2:
  - Palm detection only for initial acquire + reacquire after long loss
  - Diff tracking uses larger ROI and is more tolerant of stillness
  - Stillness detection — if no motion, hold last position (don't lose track)
  - Velocity-based ROI expansion for fast movement
  - Cleaner coordinate mapping for 90° CW mounted camera
  - No spurious fw/fh swap
"""

import cv2
import numpy as np
import socket, os, json, time
import tflite_runtime.interpreter as tflite

SOCKET_PATH      = '/tmp/iris_hand.sock'
CAMERA_INDEX     = 0
TARGET_FPS       = 8
PALM_MODEL       = './palm_detection.tflite'
PALM_THRESHOLD   = 0.55
MIN_DIFF_AREA    = 100    # lower = more sensitive to small motion
ROI_PAD          = 0.8    # generous ROI padding
LOST_FRAMES      = 25     # more tolerant before giving up
ACQUIRE_EVERY    = 5      # palm detection every N frames while acquiring
SMOOTH           = 0.85   # output smoothing (higher = smoother but laggier)
DEBUG_VIDEO      = False

# Coordinate stretch — hand rarely reaches true frame edges
# Tune these to your physical setup
STRETCH_X_LO     = 0.30
STRETCH_X_HI     = 0.70
STRETCH_Y_LO     = 0.25
STRETCH_Y_HI     = 0.75

ACQUIRING = 0
TRACKING  = 1


def make_socket():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    srv.listen(1)
    srv.setblocking(False)
    os.chmod(SOCKET_PATH, 0o666)
    return srv


def generate_anchors():
    strides = [8, 16, 16, 16]
    anchors = []
    for stride in strides:
        grid = 192 // stride
        for y in range(grid):
            for x in range(grid):
                for _ in range(2):
                    anchors.append([(x + 0.5) / grid, (y + 0.5) / grid])
    return np.array(anchors, dtype=np.float32)

ANCHORS = generate_anchors()


def decode_palm(raw_boxes, raw_scores, fw, fh):
    scores = 1.0 / (1.0 + np.exp(-raw_scores[:, 0]))
    best   = int(np.argmax(scores))
    if scores[best] < PALM_THRESHOLD:
        return None
    anchor = ANCHORS[best]
    box    = raw_boxes[best]
    scale  = 192.0
    cx = anchor[0] + box[0] / scale
    cy = anchor[1] + box[1] / scale
    w  = box[2] / scale
    h  = box[3] / scale
    px = int((cx - w/2) * fw)
    py = int((cy - h/2) * fh)
    pw = int(w * fw)
    ph = int(h * fh)
    print(f'[Hand] Palm score={scores[best]:.2f} bbox=({px},{py},{pw},{ph})')
    return (px, py, pw, ph)


def clamp_roi(cx, cy, bw, bh, fw, fh):
    """Generous ROI around last known position."""
    pw = int(bw * (1 + ROI_PAD))
    ph = int(bh * (1 + ROI_PAD))
    x  = max(1, int(cx - pw // 2))
    y  = max(1, int(cy - ph // 2))
    pw = min(fw - x - 2, pw)
    ph = min(fh - y - 2, ph)
    return (x, y, max(10, pw), max(10, ph))


def diff_centroid(prev_gray, curr_gray, roi):
    """
    Frame diff within ROI. Returns centroid of largest moving region.
    Returns None if nothing moves (stillness) — caller holds last position.
    """
    rx, ry, rw, rh = [int(v) for v in roi]
    p    = prev_gray[ry:ry+rh, rx:rx+rw]
    c    = curr_gray[ry:ry+rh, rx:rx+rw]
    diff = cv2.absdiff(p, c)
    diff = cv2.GaussianBlur(diff, (5, 5), 0)
    _, mask = cv2.threshold(diff, 0, 255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < MIN_DIFF_AREA:
        return None
    M = cv2.moments(best)
    if M['m00'] == 0:
        return None
    return (rx + int(M['m10'] / M['m00']),
            ry + int(M['m01'] / M['m00']))


def stretch(v, lo, hi):
    """Remap v from [lo,hi] to [0,1], clamped."""
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def remap(sx, sy):
    """
    Camera mounted cable-right (90° CW rotation).
    Raw sx/sy are normalised camera coords (0-1).
    Returns (screen_x, screen_y) normalised.
    """
    mx = stretch(1.0 - sx, STRETCH_X_LO, STRETCH_X_HI)
    my = stretch(1.0 - sy, STRETCH_Y_LO, STRETCH_Y_HI)
    return mx, my


def run_palm(interp, inp_d, out_d, frame, fw, fh):
    img = cv2.resize(frame, (192, 192))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    t   = (img.astype(np.float32) / 255.0)[np.newaxis]
    interp.set_tensor(inp_d['index'], t)
    interp.invoke()
    boxes  = interp.get_tensor(out_d[0]['index'])[0]
    scores = interp.get_tensor(out_d[1]['index'])[0]
    return decode_palm(boxes, scores, fw, fh)


def main():
    print('[Hand] Starting...')

    interp = tflite.Interpreter(PALM_MODEL)
    interp.allocate_tensors()
    inp_d  = interp.get_input_details()[0]
    out_d  = interp.get_output_details()
    print('[Hand] Palm model loaded')

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y','U','Y','V'))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    if not cap.isOpened():
        print('[Hand] Camera failed'); return

    ret, frame = cap.read()
    if not ret:
        print('[Hand] No frame'); return

    # Rotate frame to correct for camera orientation
    frame     = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    fh, fw    = frame.shape[:2]   # after rotation
    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    print(f'[Hand] Frame: {fw}x{fh}')

    srv    = make_socket()
    client = None
    delay  = 1.0 / TARGET_FPS

    state       = ACQUIRING
    frame_count = 0
    lost_count  = 0
    still_count = 0           # frames with no motion detected
    STILL_MAX   = 15           # hold position this many frames before counting as lost

    # Smoothed output coords
    sx, sy      = 0.5, 0.5

    # Last known hand position in pixels
    last_cx     = fw // 2
    last_cy     = fh // 2
    last_bw     = fw // 4
    last_bh     = fh // 4
    roi         = (1, 1, fw - 2, fh - 2)

    print('[Hand] Ready.')

    while True:
        t0 = time.time()

        # ── Accept new IRIS connection ────────────────────────────────────────
        if client is None:
            try:
                client, _ = srv.accept()
                client.setblocking(False)
                print('[Hand] IRIS connected')
            except BlockingIOError:
                pass

        # ── Grab frame ────────────────────────────────────────────────────────
        cap.grab()
        ret, frame = cap.retrieve()
        if not ret:
            time.sleep(0.05)
            continue

        frame     = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_count += 1
        result = None

        # ── State machine ─────────────────────────────────────────────────────

        if state == ACQUIRING:
            # Run palm detector every ACQUIRE_EVERY frames
            if frame_count % ACQUIRE_EVERY == 0:
                bbox = run_palm(interp, inp_d, out_d, frame, fw, fh)
                if bbox:
                    x, y, w, h   = bbox
                    last_cx      = x + w // 2
                    last_cy      = y + h // 2
                    last_bw, last_bh = w, h
                    roi          = clamp_roi(last_cx, last_cy, w, h, fw, fh)
                    state        = TRACKING
                    lost_count   = 0
                    still_count  = 0
                    print('[Hand] Acquired', end='\r')
            # While acquiring, send nothing (cursor stays at last position)

        elif state == TRACKING:
            pos = diff_centroid(prev_gray, curr_gray, roi)

            if pos is not None:
                # Good motion detected — update position
                lost_count  = 0
                still_count = 0
                last_cx, last_cy = pos
                # Expand ROI with velocity — bigger ROI if moving fast
                vx = abs(pos[0] - last_cx)
                vy = abs(pos[1] - last_cy)
                speed_pad = min(1.5, ROI_PAD + (vx + vy) / 50.0)
                roi = clamp_roi(last_cx, last_cy, last_bw, last_bh, fw, fh)
                result = (last_cx / fw, last_cy / fh, False)

            else:
                # No motion — could be still hand or lost hand
                still_count += 1

                if still_count <= STILL_MAX:
                    # Hand probably still — hold last position, don't count as lost
                    result = (last_cx / fw, last_cy / fh, False)
                else:
                    # Been still too long — start counting as lost
                    lost_count += 1
                    result = (last_cx / fw, last_cy / fh, False)

                    if lost_count > LOST_FRAMES:
                        # Try reacquire with palm detector
                        bbox = run_palm(interp, inp_d, out_d, frame, fw, fh)
                        if bbox:
                            x, y, w, h   = bbox
                            last_cx      = x + w // 2
                            last_cy      = y + h // 2
                            last_bw, last_bh = w, h
                            roi          = clamp_roi(last_cx, last_cy,
                                                     w, h, fw, fh)
                            lost_count   = 0
                            still_count  = 0
                            print('[Hand] Reacquired', end='\r')
                        else:
                            # Truly lost — go to center
                            state  = ACQUIRING
                            result = (0.5, 0.5, False)
                            sx, sy = 0.5, 0.5   # reset smoother too
                            print('[Hand] Lost       ', end='\r')

        prev_gray = curr_gray

        # ── Send to IRIS ──────────────────────────────────────────────────────
        if result is not None and client is not None:
            rx, ry, rp = result
            sx = sx * SMOOTH + rx * (1 - SMOOTH)
            sy = sy * SMOOTH + ry * (1 - SMOOTH)
            mx, my = remap(sx, sy)
            print(f'st={state} still={still_count:02d} lost={lost_count:02d} '
                  f'raw=({rx:.2f},{ry:.2f}) out=({mx:.2f},{my:.2f})', end='\r')
            try:
                msg = json.dumps({'x': mx, 'y': my, 'pinch': rp}) + '\n'
                client.sendall(msg.encode())
            except (BrokenPipeError, BlockingIOError):
                client = None

        # ── Timing ────────────────────────────────────────────────────────────
        elapsed = time.time() - t0
        wait    = delay - elapsed
        if wait > 0:
            time.sleep(wait)


if __name__ == '__main__':
    main()
