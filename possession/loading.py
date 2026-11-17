"""Reading the match data: ATD (FIFA/EPTS) and Smart Tagging.

Owner: Roger.

We do not use kloppy to read the ATD. Loading 199319 frames of 46 slots as Python objects takes
minutes and gigabytes; the raw file is one line per frame and reads in a single pass. The result is
cached as .npz so the second run starts immediately.

One line of the raw file:

    <frame_id>:<x,y,v>;<x,y,v>;...;<x,y,v>:<x,y,v>

Coordinates normalised 0..1, speed in m/s, NaN when missing. frame_id starts at 1 and the
submission at 0, so video_frame = frame_id - 1.
"""

import os
import xml.etree.ElementTree as ET

import numpy as np

from . import config


FIELD_SEP = ":"
GROUP_SEP = ";"


def paths(data_dir, game=config.GAME, source=config.SOURCE):
    """Paths of the three files we use. Same names as games.py in the official repository."""
    base = os.path.join(data_dir, source, "{}_{}".format(game, source))
    return {
        "meta": base + "_atd.xml",
        "raw": base + "_atd.txt",
        "tagging": base + "_smart_tagging.xml",
    }


def check_files(file_paths, required=("meta", "raw")):
    """Readable error if a file is missing. The data is gated and never in the repo."""
    missing = [file_paths[name] for name in required if not os.path.isfile(file_paths[name])]
    if missing:
        raise IOError("match data not found:\n  {}\nUnpack the bundle into data/ or pass "
                      "--data.".format("\n  ".join(missing)))


def read_metadata(meta_path):
    """(team_of_slot, (home_name, away_name)).

    The first Team in the XML is the home side, FIFA/EPTS convention. Every Player entry is a
    tracking slot, not a person: 46 slots for 22 players. The only thing we need from a slot is
    its team.
    """
    root = ET.parse(meta_path).getroot()
    teams = [(t.get("id"), t.findtext("Name")) for t in root.iter("Team")]
    if len(teams) != 2:
        raise ValueError("{}: expected 2 teams, found {}".format(meta_path, len(teams)))

    home_id = teams[0][0]
    slots = [p.get("teamId") for p in root.iter("Player")]
    if not slots:
        raise ValueError("{}: no Player entries".format(meta_path))

    team = np.array([config.H if s == home_id else config.A for s in slots], dtype=np.int8)
    return team, (teams[0][1], teams[1][1])


def _group_floats(text, n):
    """First n values of an 'x,y,v' group. NaN if the group is empty or malformed."""
    pieces = text.split(",")
    if len(pieces) < n:
        return [np.nan] * n
    try:
        return [float(p) for p in pieces[:n]]
    except ValueError:
        return [np.nan] * n


def read_atd(raw_path, n_slots, n_frames=config.N_FRAMES, pitch=config.PITCH, has_speed=True):
    """Read the raw file into arrays in metres.

    ball     (n_frames, 2)           float32, NaN where there is no ball
    players  (n_frames, n_slots, 2)  float32, NaN where the slot is inactive
    speed    (n_frames, n_slots)     float32, m/s as delivered, or NaN when has_speed is false

    Frames absent from the file stay all NaN and are treated as gaps.
    """
    length, width = pitch
    group_size = 3 if has_speed else 2
    ball = np.full((n_frames, 2), np.nan, dtype=np.float32)
    players = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    speed = np.full((n_frames, n_slots), np.nan, dtype=np.float32)

    with open(raw_path) as handle:
        for line in handle:
            parts = line.rstrip("\n").split(FIELD_SEP)
            if len(parts) != 3:
                continue
            row = int(parts[0]) - 1
            if row < 0 or row >= n_frames:
                continue

            groups = parts[1].split(GROUP_SEP)[:n_slots]
            values = np.array([_group_floats(g, group_size) for g in groups], dtype=np.float32)
            k = len(values)
            if k:
                players[row, :k, 0] = values[:, 0] * length
                players[row, :k, 1] = values[:, 1] * width
                if has_speed:
                    speed[row, :k] = values[:, 2]

            bx, by = _group_floats(parts[2], 2)
            ball[row] = (bx * length, by * width)

    return ball, players, speed


def load_match(data_dir, cache_dir=None):
    """Everything the pipeline needs, with an optional .npz cache.

    Returns a dict with ball, players, speed, team_of_slot, names and paths.
    """
    file_paths = paths(data_dir)
    check_files(file_paths)
    team_of_slot, names = read_metadata(file_paths["meta"])
    match = {"team_of_slot": team_of_slot, "names": names, "paths": file_paths}

    cache = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache = os.path.join(cache_dir, "{}_atd.npz".format(config.GAME))
        if os.path.isfile(cache) and os.path.getmtime(cache) >= os.path.getmtime(file_paths["raw"]):
            stored = np.load(cache)
            match.update(ball=stored["ball"], players=stored["players"], speed=stored["speed"])
            return match

    ball, players, speed = read_atd(file_paths["raw"], len(team_of_slot))
    if cache:
        np.savez(cache, ball=ball, players=players, speed=speed)
    match.update(ball=ball, players=players, speed=speed)
    return match


def read_tagging(path, fps=config.FPS):
    """Smart Tagging instances on the video frame axis.

    [{code, start, end, tags}] with code lower case and tags as delivered.
    Missing file gives an empty list: the tagging is a help, not a requirement.
    """
    if not path or not os.path.isfile(path):
        return []
    events = []
    for inst in ET.parse(path).iter("instance"):
        events.append({
            "code": (inst.findtext("code") or "").strip().lower(),
            "start": int(round(float(inst.findtext("start")) * fps)),
            "end": int(round(float(inst.findtext("end")) * fps)),
            "tags": {lab.findtext("group"): (lab.findtext("text") or "").strip()
                     for lab in inst.findall("label")},
        })
    return events
