"""
core/gesture.py

Central gesture detector — reads hand state each frame, emits named gestures.
─────────────────────────────────────────────────────────────────────────────
Gestures emitted (strings):
  'pinch'        index+thumb close, registered on onset
  'swipe_left'   fast horizontal left
  'swipe_right'  fast horizontal right
  'swipe_up'     fast vertical up
  'swipe_down'   fast vertical down
  'grab'         fist detected (onset)
  'grab_pin'     fist + push toward screen (bbox shrink)
  'grab_pull'    fist + pull toward camera (bbox grow)
  'grab_cancel'  fist released without push/pull

RULES
  • No pygame. No hardware.
  • Called once per frame from kernel with latest hand state.
  • Returns list of gesture strings (usually empty).
"""

import time

# ── Tuning ────────────────────────────────────────────────────────────────────

SWIPE_WINDOW      = 0.25   # seconds of velocity history
SWIPE_VEL_THRESH  = 0.40   # normalised units/s

GRAB_PUSH_SCALE   = 1.20   # bbox scale ratio to trigger grab_pin
GRAB_PULL_SCALE   = 0.80   # bbox scale ratio to trigger grab_pull
GRAB_SCALE_WINDOW = 0.30   # seconds to measure scale change over


class GestureDetector:
    """
    Instantiated once by the kernel. Call update() every frame.
    Returns list of gesture event strings for that frame.
    """

    def __init__(self):
        self._swipe_hist  = []   # [(t, nx, ny), ...]
        self._scale_hist  = []   # [(t, scale), ...]

        self._was_pinch   = False
        self._was_fist    = False
        self._grab_active = False
        self._grab_pulled = False
        self._grab_pushed = False

    # ── Public ────────────────────────────────────────────────────────────────

    def update(self, hand) -> list:
        """
        hand — HandClient instance (hand.active, hand.x, hand.y,
                hand.pinch, hand.fist, hand.scale)
        Returns list of gesture strings fired this frame.
        """
        if not hand or not hand.active:
            gestures = []
            if self._grab_active:
                gestures.append('grab_cancel')
            self._reset()
            return gestures

        now      = time.time()
        gestures = []

        # ── Swipe detection ───────────────────────────────────────────────────
        self._swipe_hist.append((now, hand.x, hand.y))
        self._swipe_hist = [(t, x, y) for t, x, y in self._swipe_hist
                            if now - t <= SWIPE_WINDOW]

        if len(self._swipe_hist) >= 2:
            dx  = self._swipe_hist[-1][1] - self._swipe_hist[0][1]
            dy  = self._swipe_hist[-1][2] - self._swipe_hist[0][2]
            dtw = max(self._swipe_hist[-1][0] - self._swipe_hist[0][0], 1e-6)
            vx  = dx / dtw
            vy  = dy / dtw

            if abs(vx) > abs(vy):   # horizontal dominant
                if vx < -SWIPE_VEL_THRESH:
                    gestures.append('swipe_left')
                    self._swipe_hist.clear()
                elif vx > SWIPE_VEL_THRESH:
                    gestures.append('swipe_right')
                    self._swipe_hist.clear()
            else:                   # vertical dominant
                if vy < -SWIPE_VEL_THRESH:
                    gestures.append('swipe_up')
                    self._swipe_hist.clear()
                elif vy > SWIPE_VEL_THRESH:
                    gestures.append('swipe_down')
                    self._swipe_hist.clear()

        # ── Pinch detection ───────────────────────────────────────────────────
        pinch_now = getattr(hand, 'pinch', False)
        if pinch_now and not self._was_pinch:
            gestures.append('pinch')
        self._was_pinch = pinch_now

        # ── Fist / grab detection ─────────────────────────────────────────────
        fist_now = getattr(hand, 'fist', False)

        if fist_now and not self._was_fist:
            # Fist onset — grab starts
            self._grab_active = True
            self._grab_pulled = False
            self._grab_pushed = False
            self._scale_hist.clear()
            gestures.append('grab')

        if self._grab_active and fist_now:
            # Track bbox scale for push/pull
            scale = getattr(hand, 'scale', 1.0)
            self._scale_hist.append((now, scale))
            self._scale_hist = [(t, s) for t, s in self._scale_hist
                                if now - t <= GRAB_SCALE_WINDOW]

            if len(self._scale_hist) >= 2:
                s0 = self._scale_hist[0][1]
                s1 = self._scale_hist[-1][1]
                ratio = s1 / s0 if s0 > 0 else 1.0

                if ratio > GRAB_PUSH_SCALE and not self._grab_pushed:
                    self._grab_pushed = True
                    gestures.append('grab_pin')
                elif ratio < GRAB_PULL_SCALE and not self._grab_pulled:
                    self._grab_pulled = True
                    gestures.append('grab_pull')

        if not fist_now and self._was_fist:
            # Fist released
            if self._grab_active:
                if not self._grab_pushed and not self._grab_pulled:
                    gestures.append('grab_cancel')
                self._grab_active = False

        self._was_fist = fist_now
        return gestures

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reset(self):
        self._swipe_hist.clear()
        self._scale_hist.clear()
        self._was_pinch   = False
        self._was_fist    = False
        self._grab_active = False
        self._grab_pulled = False
        self._grab_pushed = False
