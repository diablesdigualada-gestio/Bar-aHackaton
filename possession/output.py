"""Submission file, possession spells and the JSON the viewer reads.

Owner: Carles.

The CSV contract is strict (SUBMISSION.md): header frame,label, exactly 199319 rows, frames
0..199318 in order, labels from H A D X, no blanks. We check it ourselves before writing so a typo
never costs us the whole entry.
"""

import json
import os

import numpy as np

from . import config


def labels_from_states(states):
    """int8 states to an array of 'H' 'A' 'D'. Ungraded frames are forced to D."""
    labels = np.array(config.LABELS, dtype="<U1")[states]
    graded = graded_mask(len(states))
    labels[~graded] = "D"
    return labels


def graded_mask(n):
    """Boolean mask of length n, True on the frames the organisers score (config.HALVES, inclusive)."""
    mask = np.zeros(n, dtype=bool)
    for first, last in config.HALVES:
        mask[first:last + 1] = True
    return mask


def write_submission(path, labels):
    """Validate and write frame,label. Raises before touching the disk if anything is off."""
    if len(labels) != config.N_FRAMES:
        raise ValueError("expected {} rows, have {}".format(config.N_FRAMES, len(labels)))
    bad = set(np.unique(labels)) - {"H", "A", "D", "X"}
    if bad:
        raise ValueError("unexpected labels: {}".format(sorted(bad)))

    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="\n") as handle:
        handle.write("frame,label\n")
        handle.writelines("{},{}\n".format(i, lab) for i, lab in enumerate(labels))
    return path


def spells(labels, fps=config.FPS):
    """Maximal runs of the same label inside graded frames: [{label, start, end, seconds}]."""
    graded = graded_mask(len(labels))
    out = []
    start = None
    for i in range(len(labels) + 1):
        current = labels[i] if i < len(labels) and graded[i] else None
        if start is not None and (current != labels[start]):
            out.append({"label": str(labels[start]), "start": int(start), "end": int(i - 1),
                        "seconds": round((i - start) / fps, 2)})
            start = None
        if start is None and current is not None:
            start = i
    return out


def summary(labels, names):
    """Possession share in live play, ball in play share, and spell counts."""
    graded = graded_mask(len(labels))
    g = labels[graded]
    n_h, n_a, n_d = (int(np.sum(g == x)) for x in ("H", "A", "D"))
    live = max(1, n_h + n_a)
    runs = spells(labels)
    return {
        "home": names[0], "away": names[1],
        "frames": {"H": n_h, "A": n_a, "D": n_d},
        "possession_home": round(n_h / live, 4),
        "possession_away": round(n_a / live, 4),
        "ball_in_play": round(live / max(1, len(g)), 4),
        "spells": {lab: sum(1 for r in runs if r["label"] == lab) for lab in ("H", "A", "D")},
    }


def export_viewer(path, labels, names, match=None, step=5):
    """JSON for the web viewer. Tracking is included only when match is given.

    The file contains match data, so it goes to a gitignored folder and never to the repo.
    """
    data = {
        "summary": summary(labels, names),
        "spells": spells(labels),
        "fps": config.FPS,
        "halves": config.HALVES,
        "timeline_step": step,
        "timeline": "".join(labels[::step].tolist()),
    }
    if match is not None:
        ball = match["ball"][::step]
        players = match["players"][::step]
        team = match["team_of_slot"].tolist()
        data["tracking"] = {
            "step": step,
            "team_of_slot": team,
            "ball": np.round(np.nan_to_num(ball, nan=-99.0), 1).tolist(),
            "players": np.round(np.nan_to_num(players, nan=-99.0), 1).tolist(),
            "pitch": config.PITCH,
        }
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    return path
