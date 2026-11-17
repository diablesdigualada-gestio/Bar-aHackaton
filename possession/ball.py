"""Ball cleaning: short gaps, speed, and in or out of the pitch.

Owner: Roger.

The ball is missing on 41% of graded frames. Most gaps are short occlusions (a player in front of
the camera, a header) and not stoppages. Short gaps get a straight line; long ones stay NaN and the
Viterbi decides with the rest of the evidence.
"""

import numpy as np

from . import config


def runs(mask):
    """List of (start, end_exclusive) for every run where mask is True."""
    m = np.concatenate(([False], mask, [False])).astype(np.int8)
    edges = np.diff(m)
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def fill_gaps(ball, max_gap=config.MAX_GAP_INTERPOLATED):
    """(filled_ball, seen_mask).

    Only gaps with a seen ball on both sides and at most max_gap frames long are filled.
    """
    ball = ball.copy()
    seen = ~np.isnan(ball[:, 0])
    n = len(ball)
    for start, end in runs(~seen):
        if start == 0 or end >= n or end - start > max_gap:
            continue
        a, b = ball[start - 1], ball[end]
        t = (np.arange(1, end - start + 1, dtype=np.float32) / (end - start + 1))[:, None]
        ball[start:end] = a + (b - a) * t
    return ball, seen


def moving_mean(x, window):
    """Centred mean that ignores NaN. Cumulative sums, so cost does not depend on the window."""
    if window <= 1:
        return x.astype(np.float32)
    valid = ~np.isnan(x)
    v = np.where(valid, x, 0.0).astype(np.float64)
    total = np.concatenate(([0.0], np.cumsum(v)))
    count = np.concatenate(([0], np.cumsum(valid)))
    idx = np.arange(len(x))
    half = window // 2
    lo = np.maximum(0, idx - half)
    hi = np.minimum(len(x), idx + half + 1)
    c = count[hi] - count[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (total[hi] - total[lo]) / c
    out[c == 0] = np.nan
    return out.astype(np.float32)


def speed(ball, fps=config.FPS, window=config.BALL_SPEED_WINDOW):
    """Ball speed in m/s, centred differences then smoothed."""
    s = np.full(len(ball), np.nan, dtype=np.float32)
    step = ball[2:] - ball[:-2]
    s[1:-1] = np.hypot(step[:, 0], step[:, 1]) * fps / 2.0
    return moving_mean(s, window)


def out_of_pitch(ball, pitch=config.PITCH, margin=config.OUT_OF_PITCH_MARGIN):
    """True where the ball is clearly past the lines. False where there is no ball."""
    length, width = pitch
    x, y = ball[:, 0], ball[:, 1]
    with np.errstate(invalid="ignore"):
        out = (x < -margin) | (x > length + margin) | (y < -margin) | (y > width + margin)
    return out & ~np.isnan(x)
