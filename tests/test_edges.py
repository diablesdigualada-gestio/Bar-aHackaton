"""Edge cases and failure paths. No real data needed.

Owner: Carles.

    python -m tests.test_edges

test_synthetic.py checks that a clean match comes out right. This file checks what happens when the
input is not clean: broken lines in the raw tracking, a ball that is missing for a long time or at
the very start, frames with nobody on the pitch, files that do not exist, and submission files that
would be rejected by the organisers. Every test here is written so it fails if the guard it checks
is removed.
"""

import os
import tempfile

import numpy as np

from possession import ball as ballmod
from possession import config, features, learned, loading, output, viterbi


def expect_error(error, call, *args):
    """Run call(*args) and fail unless it raises error."""
    try:
        call(*args)
    except error:
        return
    raise AssertionError("{} did not raise {}".format(call.__name__, error.__name__))


def test_submission_rejects_wrong_length():
    """One row short must raise, and nothing may be written to disk."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.csv")
        expect_error(ValueError, output.write_submission, path,
                     np.full(config.N_FRAMES - 1, "D"))
        assert not os.path.exists(path)


def test_submission_rejects_bad_labels():
    """A lower case or blank label must raise: the organisers would drop the file."""
    labels = np.full(config.N_FRAMES, "D", dtype="<U1")
    labels[5] = "h"
    with tempfile.TemporaryDirectory() as tmp:
        expect_error(ValueError, output.write_submission, os.path.join(tmp, "a.csv"), labels)
        labels[5] = ""
        expect_error(ValueError, output.write_submission, os.path.join(tmp, "b.csv"), labels)


def test_submission_format_exact():
    """Header, row count, frame order and line endings exactly as SUBMISSION.md asks."""
    labels = np.full(config.N_FRAMES, "D", dtype="<U1")
    with tempfile.TemporaryDirectory() as tmp:
        path = output.write_submission(os.path.join(tmp, "x.csv"), labels)
        with open(path, "rb") as handle:
            raw = handle.read()
    lines = raw.decode().split("\n")
    assert lines[0] == "frame,label"
    assert lines[-1] == "" and len(lines) == config.N_FRAMES + 2
    assert lines[1] == "0,D" and lines[-2] == "{},D".format(config.N_FRAMES - 1)
    assert b"\r" not in raw


def test_ungraded_frames_are_dead():
    """Frames outside the two halves are forced to D whatever the decoder said."""
    states = np.full(config.N_FRAMES, config.H, dtype=np.int8)
    labels = output.labels_from_states(states)
    first, last = config.HALVES[0]
    assert labels[first - 1] == "D" and labels[first] == "H" and labels[last] == "H"
    assert labels[last + 1] == "D" and labels[-1] == "D"


def test_reader_survives_broken_lines():
    """Malformed, truncated, out of range and duplicated lines must not crash or shift frames."""
    lines = [
        "garbage without separators\n",
        "1:0.5,0.5,1.0;0.2,0.2,1.0:0.5,0.5,0.0\n",
        "2:0.6,0.4:0.5\n",                      # player group too short, ball group too short
        "0:0.9,0.9,1.0;0.9,0.9,1.0:0.9,0.9,0\n",  # frame id 0 maps to row -1: must be skipped
        "99:0.1,0.1,1.0;0.1,0.1,1.0:0.1,0.1,0\n",  # beyond n_frames: must be skipped
        "3:abc,def,ghi;0.1,0.1,1.0:x,y,z\n",      # non numeric values become NaN
        "\n",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "raw.txt")
        with open(path, "w") as handle:
            handle.writelines(lines)
        ball, players, speed = loading.read_atd(path, 2, n_frames=4, pitch=(100.0, 50.0))
    assert np.allclose(ball[0], (50, 25)) and np.allclose(players[0, 1], (20, 10))
    assert np.isnan(ball[1, 0]) and np.isnan(players[1, 0, 0])
    assert np.isnan(ball[2, 0]) and np.isnan(players[2, 0, 0])
    assert np.allclose(players[2, 1], (10, 5))
    assert np.all(np.isnan(ball[3])), "an absent frame must stay missing"


def test_long_and_edge_gaps_are_not_invented():
    """Only short gaps with the ball seen on both sides are filled; the rest stays NaN."""
    n = 60
    ball = np.tile(np.array([[10.0, 10.0]], np.float32), (n, 1))
    ball[0:3] = np.nan                                      # at the start, no left neighbour
    ball[10:13] = np.nan                                    # short, both sides seen
    ball[20:20 + config.MAX_GAP_INTERPOLATED + 1] = np.nan  # one frame too long
    ball[n - 2:] = np.nan                                   # at the end, no right neighbour
    filled, seen = ballmod.fill_gaps(ball)
    assert np.all(np.isnan(filled[0:3])) and np.all(np.isnan(filled[n - 2:]))
    assert not np.any(np.isnan(filled[10:13]))
    assert np.all(np.isnan(filled[20:20 + config.MAX_GAP_INTERPOLATED + 1]))
    assert not seen[10] and seen[9], "seen must describe the raw data, not the filled one"


def test_missing_ball_is_never_out_of_pitch():
    """A NaN ball must not count as out of play: that was the baseline's main mistake."""
    ball = np.array([[np.nan, np.nan], [-5.0, 30.0], [50.0, 30.0]], np.float32)
    out = ballmod.out_of_pitch(ball)
    assert out.tolist() == [False, True, False]


def test_no_players_gives_no_control():
    """Frames with nobody tracked give zero control evidence, not a crash or a NaN."""
    n = 10
    ball = np.full((n, 2), 30.0, np.float32)
    players = np.full((n, 4, 2), np.nan, np.float32)
    team = np.array([0, 0, 1, 1], np.int8)
    d_home, d_away = features.nearest_distance_per_team(ball, players, team)
    speed = ballmod.speed(ball)
    control = features.control_evidence(d_home, d_away, speed)
    assert np.all(np.isfinite(control)) and np.allclose(control, 0.0)


def test_decoder_with_flat_evidence_is_stable():
    """All-zero or all-equal scores must still give one valid state per frame."""
    for scores in (np.zeros((500, 3), np.float32), np.full((500, 3), -7.0, np.float32)):
        states = viterbi.decode(scores)
        assert len(states) == 500 and set(np.unique(states)) <= {config.H, config.A, config.D}
        assert len(np.flatnonzero(np.diff(states))) == 0, "no evidence must not invent switches"


def test_decoder_shorter_than_min_duration():
    """A sequence shorter than the minimum duration must still decode without error."""
    scores = np.zeros((5, 3), np.float32)
    scores[:, config.A] = 1.0
    states = viterbi.decode(scores)
    assert len(states) == 5


def test_occlusion_never_touches_dead_frames():
    """Simulated dropouts hide the ball only in live play, at the requested share."""
    rng = np.random.default_rng(0)
    n = 5000
    ball = np.ones((n, 2), np.float32)
    live = np.zeros(n, bool)
    live[1000:4000] = True
    hidden = learned.occlude(ball, live, rng)
    assert not np.any(np.isnan(hidden[~live]))
    share = np.isnan(hidden[live, 0]).mean()
    assert config.OCCLUSION_SHARE <= share < config.OCCLUSION_SHARE + 0.05, share
    assert not np.any(np.isnan(ball)), "the input must not be modified"


def test_robust_features_ignore_visibility():
    """The robust matrix must be identical whether a frame's ball was seen or only filled."""
    n = 4
    frame = {"control": np.zeros(n), "out": np.zeros(n, bool),
             "active_players": np.full(n, 22.0), "seen": np.array([True, False, True, False])}
    for name in config.LEARNED_CLIPS:
        frame[name] = np.array([1.0, np.nan, 1.0, np.nan])
    frame["mean_player_speed"] = np.full(n, 2.0)
    robust = learned.feature_matrix(frame, robust=True)
    plain = learned.feature_matrix(frame)
    assert not np.any(np.isnan(robust)) and not np.any(np.isnan(plain))
    assert robust.shape[1] < plain.shape[1], "seen and missing flags must be gone"
    seen_twin = dict(frame, seen=np.ones(n, bool))
    assert np.array_equal(learned.feature_matrix(seen_twin, robust=True), robust)


def test_missing_files_are_reported():
    """A missing data bundle gives a readable IOError naming the file, not a traceback deep inside."""
    with tempfile.TemporaryDirectory() as tmp:
        file_paths = loading.paths(tmp)
        try:
            loading.check_files(file_paths)
        except IOError as error:
            assert "BAR-ATH_tactical_atd" in str(error)
        else:
            raise AssertionError("check_files accepted a missing bundle")
        assert loading.read_tagging(os.path.join(tmp, "nope.xml")) == []


def test_video_with_download_suffix_is_found():
    """BAR-ATH_tactical-001.mp4 is found; the exact name wins when both exist."""
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "BAR-ATH_tactical")
        open(base + "-001.mp4", "w").close()
        assert loading.find_video(base).endswith("-001.mp4")
        open(base + ".mp4", "w").close()
        assert loading.find_video(base) == base + ".mp4"


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for test in TESTS:
        try:
            test()
            print("ok    ", test.__name__)
        except Exception as error:  # report every failure, not only the first
            failed += 1
            print("FAIL  ", test.__name__, "->", repr(error))
    print("{} passed, {} failed".format(len(TESTS) - failed, failed))
    raise SystemExit(1 if failed else 0)
