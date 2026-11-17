"""Smoke test on a synthetic match. No real data needed, runs in a few seconds.

Owner: Carles.

    python -m tests.test_synthetic

Script: home carries the ball for 10 s, passes, away intercepts and carries for 10 s, kicks it out,
players walk for 6 s, home restarts and keeps it. We check the decoder finds H, A, D, H in that
order and that the raw ATD reader understands the file format.
"""

import os
import tempfile

import numpy as np

from possession import config, loading, viterbi
from run import build_states

FPS = config.FPS


def synthetic_match():
    """40 s invented match: H carries, passes, A intercepts and carries, kicks it out, walk, H restarts.

    Returns the same dict shape as loading.load_match, so the real pipeline runs on it unchanged."""
    n = FPS * 40
    # Six actors near the ball plus sixteen bystanders far from it, so the match looks live.
    slots = 22
    team = np.array([0, 0, 0, 1, 1, 1] + [0] * 8 + [1] * 8, dtype=np.int8)
    rng = np.random.default_rng(7)

    players = np.zeros((n, slots, 2), dtype=np.float32)
    actors = [[30, 20], [40, 34], [30, 48], [70, 20], [60, 34], [70, 48]]
    bystanders = [[5 + 2 * i, 5 + 7 * i] for i in range(8)] + [[100 - 2 * i, 5 + 7 * i] for i in range(8)]
    base = np.array(actors + bystanders, np.float32)
    players[:] = base
    speed = np.full((n, slots), 4.0, dtype=np.float32)
    ball = np.zeros((n, 2), dtype=np.float32)

    seg = [(0, 10, 1, "H"), (10, 11, None, "pass"), (11, 21, 4, "A"),
           (21, 24, None, "out"), (24, 30, None, "dead"), (30, 40, 1, "H")]
    for a, b, carrier, kind in seg:
        fa, fb = a * FPS, b * FPS
        if carrier is not None:
            # The carrier dribbles slowly and the ball stays at his feet.
            t = np.arange(fb - fa)[:, None]
            players[fa:fb, carrier] = base[carrier] + t * np.array([0.12, 0.0], np.float32)
            ball[fa:fb] = players[fa:fb, carrier] + 0.4
        elif kind == "pass":
            ball[fa:fb] = np.linspace(players[fa - 1, 1], base[4] + 6, fb - fa)
        elif kind == "out":
            ball[fa:fb] = np.linspace([65, 34], [70, -6], fb - fa)
        else:
            ball[fa:fb] = np.nan
            speed[fa:fb] = 0.6
    players += rng.normal(0, 0.05, players.shape).astype(np.float32)
    return {"ball": ball, "players": players, "speed": speed, "team_of_slot": team,
            "names": ("Home FC", "Away FC")}


def compress(states):
    """Collapse runs of equal states into one letter each: [H, H, A, A, D] becomes 'HAD'."""
    keep = [states[0]]
    for s in states[1:]:
        if s != keep[-1]:
            keep.append(s)
    return "".join(config.LABELS[s] for s in keep)


def test_decoder():
    """The full pipeline must find the possessions in order H, A, D, H."""
    states = build_states(synthetic_match(), [])
    sequence = compress(states)
    print("decoded sequence:", sequence)
    assert sequence.strip("D") == "HADH", sequence


def test_reader():
    """The raw ATD reader converts 0..1 coordinates to metres and keeps NaN for missing values."""
    lines = ["1:0.5,0.5,1.0;NaN,NaN,NaN:0.5,0.5,0.0\n", "2:0.6,0.4,2.0;0.1,0.1,0.5:NaN,NaN,NaN\n"]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "raw.txt")
        with open(path, "w") as handle:
            handle.writelines(lines)
        ball, players, speed = loading.read_atd(path, 2, n_frames=3, pitch=(100.0, 50.0))
    assert np.allclose(ball[0], (50, 25)) and np.isnan(ball[1, 0]) and np.isnan(ball[2, 0])
    assert np.allclose(players[1, 0], (60, 20)) and np.isnan(players[0, 1, 0])
    assert speed[1, 1] == np.float32(0.5)


def test_min_duration():
    # A 5-frame blip of A inside H must not survive the 15-frame minimum.
    """A blip shorter than the minimum duration must be absorbed by the surrounding possession."""
    scores = np.zeros((200, 3), dtype=np.float32)
    scores[:, config.H] = 1.0
    scores[100:105, config.A] = 3.0
    scores[100:105, config.H] = 0.0
    assert compress(viterbi.decode(scores)).strip("D") == "H"


if __name__ == "__main__":
    test_reader()
    test_min_duration()
    test_decoder()
    print("all good")
