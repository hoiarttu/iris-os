"""
hand_tracker.py — Hand cursor process v2
─────────────────────────────────────────────────────────────────────────────
Palm detection for acquisition, ROI frame diff for tracking.
No Kalman for now. Simple smoothing only.
Pinch disabled until landmark model is sorted.
"""

import cv2
import numpy as np
import socket, os, json, time

import tflite_runtime.interpreter as tflite

SOCKET_PATH      = '/tmp/iris_hand.sock'
CAMERA_INDEX     = 0
TARGET_FPS       = 10
PALM_MODEL       = './palm_detection.tflite'
PALM_THRESHOLD   = 0.5
#DIFF_THRESH      = 12
MIN_DIFF_AREA    = 800
ROI_PAD          = 0.5
LOST_FRAMES      = 10
ACQUIRE_EVERY    = 3
SMOOTH           = 0.6
DEBUG_VIDEO      = True

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
        print(f'palm score {scores[best]:.2f} too low', end='\r')
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
    print(f'palm found score={scores[best]:.2f} bbox=({px},{py},{pw},{ph})')
    return (px, py, pw, ph)


def clamp_roi(cx, cy, bw, bh, fw, fh):
    pw = int(bw * (1 + ROI_PAD))
    ph = int(bh * (1 + ROI_PAD))
    x  = max(1, int(cx - pw // 2))
    y  = max(1, int(cy - ph // 2))
    pw = min(fw - x - 2, pw)
    ph = min(fh - y - 2, ph)
    return (x, y, max(10, pw), max(10, ph))


def diff_centroid(prev_gray, curr_gray, roi):
    rx, ry, rw, rh = [int(v) for v in roi]
    p = prev_gray[ry:ry+rh, rx:rx+rw]
    c = curr_gray[ry:ry+rh, rx:rx+rw]
    diff = cv2.absdiff(p, c)
    diff = cv2.GaussianBlur(diff, (5, 5), 0)
    _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < MIN_DIFF_AREA:
        return None
    M = cv2.moments(best)
    if M['m00'] == 0:
        return None
    return (rx + int(M['m10'] / M['m00']), ry + int(M['m01'] / M['m00']))


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

    if not cap.isOpened():
        print('[Hand] Camera failed'); return

    ret, frame = cap.read()
    if not ret:
        print('[Hand] No frame'); return

    fh, fw    = frame.shape[:2]
    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    print(f'[Hand] Frame: {fw}x{fh}')

    srv    = make_socket()
    client = None
    delay  = 1.0 / TARGET_FPS

    state       = ACQUIRING
    frame_count = 0
    lost_count  = 0
    sx, sy      = 0.5, 0.5
    last_cx     = fw // 2
    last_cy     = fh // 2
    last_bw     = fw // 3
    last_bh     = fh // 3
    roi         = (1, 1, fw-2, fh-2)

    print('[Hand] Ready.')

    while True:
        t0 = time.time()

        if client is None:
            try:
                client, _ = srv.accept()
                client.setblocking(False)
                print('[Hand] IRIS connected')
            except BlockingIOError:
                pass

        cap.grab()
        ret, frame = cap.retrieve()
        if not ret:
            time.sleep(0.05)
            continue

        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_count += 1
        result = None

        def run_palm():
            img = cv2.resize(frame, (192, 192))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            t   = (img.astype(np.float32) / 255.0)[np.newaxis]
            interp.set_tensor(inp_d['index'], t)
            interp.invoke()
            boxes  = interp.get_tensor(out_d[0]['index'])[0]
            scores = interp.get_tensor(out_d[1]['index'])[0]
            return decode_palm(boxes, scores, fw, fh)

        if state == ACQUIRING:
            if frame_count % ACQUIRE_EVERY == 0:
                bbox = run_palm()
                if bbox:
                    x, y, w, h = bbox
                    last_cx, last_cy = x + w//2, y + h//2
                    last_bw, last_bh = w, h
                    roi   = clamp_roi(last_cx, last_cy, w, h, fw, fh)
                    state = TRACKING
                    lost_count = 0
                    print('[Hand] Tracking', end='\r')

        elif state == TRACKING:
            pos = diff_centroid(prev_gray, curr_gray, roi)
            if pos is not None:
                lost_count = 0
                last_cx, last_cy = pos
                roi    = clamp_roi(last_cx, last_cy, last_bw, last_bh, fw, fh)
                result = (last_cx / fw, last_cy / fh, False)
            else:
                lost_count += 1
                result = (last_cx / fw, last_cy / fh, False)
                if lost_count > LOST_FRAMES:
                    bbox = run_palm()
                    if bbox:
                        x, y, w, h = bbox
                        last_cx, last_cy = x + w//2, y + h//2
                        last_bw, last_bh = w, h
                        roi   = clamp_roi(last_cx, last_cy, w, h, fw, fh)
                        lost_count = 0
                        print('[Hand] Reacquired', end='\r')
                    else:
                        state = ACQUIRING
                        print('[Hand] Lost', end='\r')
        if DEBUG_VIDEO:
             rx2, ry2 = int(last_cx), int(last_cy)
             rrx, rry, rrw, rrh = [int(v) for v in roi]
             cv2.circle(frame, (rx2, ry2), 8, (0,255,0), -1)
             cv2.rectangle(frame, (rrx,rry), (rrx+rrw,rry+rrh), (255,0,0), 2)
             cv2.imshow('IRIS Hand', frame)
             if cv2.waitKey(1) & 0xFF == ord('q'):
                 break
        prev_gray = curr_gray

        if result and client is not None:
            rx, ry, rp = result
            sx = sx * SMOOTH + rx * (1 - SMOOTH)
            sy = sy * SMOOTH + ry * (1 - SMOOTH)
            try:
                msg = json.dumps({'x': round(sx,3), 'y': round(sy,3), 'pinch': rp}) + '\n'
                client.sendall(msg.encode())
            except (BrokenPipeError, BlockingIOError):
                client = None

        elapsed = time.time() - t0
        wait = delay - elapsed
        if wait > 0:
            time.sleep(wait)

    cap.release()


if __name__ == '__main__':
    main()
