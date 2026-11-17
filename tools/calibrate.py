# Owner: Roger
"""Calibrate possession parameters on Metrica Sports Sample Game 3.

Run from the repository with: python tools/calibrate.py
"""

import importlib.util
import json
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from itertools import product
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch
from urllib.request import urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run
from possession import config, loading

CACHE = ROOT / ".cache" / "sample"
GAME = "Sample_Game_3"
SOURCE = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data/"
SCORER = Path("C:/mtah_ref/repo/evaluation/possession_metrics.py")
PITCH = (105.0, 68.0)
IOU_THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)

GRID = {
    "CONTROL_RADIUS": (1.6, 2.2, 3.0),
    "CONTROL_WEIGHT": (0.55, 0.85),
    "TIME_BLEND": (0.0, 0.5),
    "TEAM_SWITCH_COST": (7.0, 18.0),
    "DEAD_SWITCH_COSTS": ((3.0, 2.5), (9.0, 8.0)),
    "TEAM_MIN_DURATION": (15, 30),
}


def download(suffix):
    """Download one public sample file and cache it after the transfer finishes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (GAME + "_" + suffix)
    if path.is_file():
        return path
    url = SOURCE + GAME + "/" + path.name
    temporary = None
    try:
        with urlopen(url, timeout=60) as response:
            with NamedTemporaryFile(dir=CACHE, delete=False) as handle:
                temporary = Path(handle.name)
                shutil.copyfileobj(response, handle)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def load_sample(metadata, tracking):
    """Read EPTS positions and map each layout's columns to stable player slots."""
    teams, names = loading.read_metadata(metadata)
    root = ET.parse(metadata).getroot()
    fps = int(root.findtext(".//FrameRate"))
    if fps != config.FPS:
        raise ValueError("Sample frame rate differs from pipeline frame rate")

    player_slots = {player.get("id"): i for i, player in enumerate(root.iter("Player"))}
    channel_slots = {channel.get("id"): player_slots[channel.get("playerId")]
                     for channel in root.iter("PlayerChannel")}
    layouts = []
    for spec in root.iter("DataFormatSpecification"):
        start = int(spec.get("startFrame")) - 1
        stop = int(spec.get("endFrame"))
        columns = [channel_slots[group.find("PlayerChannelRef").get("playerChannelId")]
                   for group in spec.find("SplitRegister").findall("SplitRegister")]
        layouts.append((start, stop, columns))

    n_frames = max(stop for _, stop, _ in layouts)
    n_columns = max(len(columns) for _, _, columns in layouts)
    ball, raw_players, _ = loading.read_atd(tracking, n_columns, n_frames=n_frames,
                                           pitch=PITCH, has_speed=False)
    players = np.full((n_frames, len(teams), 2), np.nan, dtype=np.float32)
    for start, stop, columns in layouts:
        players[start:stop, columns] = raw_players[start:stop, :len(columns)]

    speed = np.full(players.shape[:2], np.nan, dtype=np.float32)
    delta = players[2:] - players[:-2]
    speed[1:-1] = np.hypot(delta[..., 0], delta[..., 1]) * (fps / 2)
    speed[np.isnan(players[..., 0])] = np.nan
    return {"ball": ball, "players": players, "speed": speed,
            "team_of_slot": teams, "names": names, "pitch": PITCH}


def event_labels(path, names, n_frames):
    """Return H/A/D state codes from the public event timeline.

    Event frame IDs align with the one-based tracking IDs. Play starts dead.
    A valid SET PIECE or a PASS/BALL LOST tagged GOAL KICK restarts play
    for its team at the event start. A set piece marked RETAKEN is ignored.
    While live, PASS, CARRY, SHOT and RECOVERY establish control at the
    start frame. A BLOCKED recovery, a challenge, and an ordinary BALL LOST
    leave the previous team in control. Ordinary events cannot resume play.

    BALL OUT, goals, shots tagged OUT, offsides, handballs and half endings
    enter D at the event end. A FAULT RECEIVED, a FAULT subtype or a CARD
    enters D at the start. Advantage challenges have no effect.
    D continues until the next restart. At the same frame, a restart takes
    priority over a stoppage, and a stoppage over ordinary control.
    Ties within the same group follow the last event in source order.
    """
    with path.open(encoding="utf-8-sig") as handle:
        events = json.load(handle)["data"]
    controls = {"PASS", "CARRY", "SHOT", "RECOVERY"}
    end_stops = {"OFFSIDE", "HAND BALL", "END HALF"}
    teams = dict(zip(names, (config.H, config.A)))
    changes = defaultdict(list)
    for event in events:
        kind = event["type"]["name"]
        subtypes = event["subtypes"] or []
        if isinstance(subtypes, dict):
            subtypes = [subtypes]
        tags = {subtype["name"] for subtype in subtypes}
        start = event["start"]["frame"] - 1
        end = event["end"]["frame"] - 1
        team = teams.get((event["team"] or {}).get("name"))

        if (kind == "BALL OUT" or end_stops & tags
                or (kind == "SHOT" and {"OUT", "GOAL"} & tags)):
            changes[end].append((1, config.D))
        fault = "FAULT" in tags and "ADVANTAGE" not in tags
        if kind in {"FAULT RECEIVED", "CARD"} or fault:
            changes[start].append((1, config.D))

        restart = kind == "SET PIECE" and "RETAKEN" not in tags
        goal_kick = kind in {"PASS", "BALL LOST"} and "GOAL KICK" in tags
        if team is not None and (restart or goal_kick):
            changes[start].append((2, team))
        elif (team is not None and kind in controls
              and not (kind == "RECOVERY" and "BLOCKED" in tags)):
            changes[start].append((0, team))

    labels = np.full(n_frames, config.D, dtype=np.int8)
    state = config.D
    previous = 0
    for frame, candidates in sorted(changes.items()):
        if not 0 <= frame < n_frames:
            raise ValueError("Event frame outside sample tracking: {}".format(frame + 1))
        labels[previous:frame] = state
        priority, next_state = max(reversed(candidates), key=lambda change: change[0])
        if priority or state != config.D:
            state = next_state
        previous = frame
    labels[previous:] = state
    return labels


def load_official_scorer():
    """Use the local official metrics module when its source can be read."""
    try:
        with SCORER.open("rb"):
            pass
    except OSError:
        return None
    spec = importlib.util.spec_from_file_location("calibration_possession_metrics", SCORER)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    return scorer


def spells(labels):
    """Return maximal H/A runs with half-open frame bounds."""
    if len(labels) == 0:
        return []
    boundaries = np.flatnonzero(np.r_[True, labels[1:] != labels[:-1], True])
    return [(start, stop, labels[start])
            for start, stop in zip(boundaries, boundaries[1:])
            if labels[start] in (config.H, config.A)]


def spell_f1(truth, prediction):
    """Greedily match same-team spells one to one in descending IoU order."""
    actual, predicted = spells(truth), spells(prediction)
    overlaps = []
    i, j = 0, 0
    while i < len(actual) and j < len(predicted):
        a, b, team = actual[i]
        c, d, other_team = predicted[j]
        intersection = min(b, d) - max(a, c)
        if intersection > 0 and team == other_team:
            overlaps.append((intersection / (max(b, d) - min(a, c)), i, j))
        if b <= d:
            i += 1
        if d <= b:
            j += 1
    overlaps.sort(key=lambda pair: (-pair[0], pair[1], pair[2]))

    total = len(actual) + len(predicted)
    scores = []
    for threshold in IOU_THRESHOLDS:
        used_actual, used_predicted = set(), set()
        for iou, i, j in overlaps:
            if iou < threshold:
                break
            if i not in used_actual and j not in used_predicted:
                used_actual.add(i)
                used_predicted.add(j)
        scores.append(2 * len(used_actual) / total if total else 0.0)
    return float(np.mean(scores))


def scores(truth, prediction, official):
    if official is not None:
        spell_score = official.spell_scores(truth, prediction, [(0, len(truth))])["mean_f1"]
        matrix = official.scored_confusion(official.confusion(truth, prediction))
        return spell_score, official.macro_f1(matrix)

    matrix = np.bincount(3 * truth + prediction, minlength=9).reshape(3, 3)
    counts = matrix.sum(axis=0) + matrix.sum(axis=1)
    f1 = np.divide(2 * matrix.diagonal(), counts, out=np.zeros(3), where=counts != 0)
    return spell_f1(truth, prediction), float(f1.mean())


def current_settings():
    return {
        "CONTROL_RADIUS": config.CONTROL_RADIUS,
        "CONTROL_WEIGHT": config.CONTROL_WEIGHT,
        "TIME_BLEND": config.TIME_BLEND,
        "TEAM_SWITCH_COST": config.SWITCH_COST[config.H, config.A],
        "DEAD_SWITCH_COSTS": (config.SWITCH_COST[config.H, config.D],
                              config.SWITCH_COST[config.D, config.H]),
        "TEAM_MIN_DURATION": config.MIN_DURATION[config.H],
    }


def predict(match, settings):
    h, a, d = config.H, config.A, config.D
    team_cost = settings["TEAM_SWITCH_COST"]
    enter_dead, leave_dead = settings["DEAD_SWITCH_COSTS"]
    duration = settings["TEAM_MIN_DURATION"]
    costs = {(h, a): team_cost, (a, h): team_cost,
             (h, d): enter_dead, (a, d): enter_dead,
             (d, h): leave_dead, (d, a): leave_dead}
    # Decode captures these dictionaries as defaults, so patch their contents in place.
    with patch.multiple(config, CONTROL_RADIUS=settings["CONTROL_RADIUS"],
                        CONTROL_WEIGHT=settings["CONTROL_WEIGHT"],
                        TIME_BLEND=settings["TIME_BLEND"]), \
            patch.dict(config.SWITCH_COST, costs), \
            patch.dict(config.MIN_DURATION, {h: duration, a: duration}):
        return run.build_states(match, [])


def grid_search(match, truth, official):
    baseline = scores(truth, run.build_states(match, []), official)
    original = current_settings()
    print("Current config: spellF1 {:.4f}, macroF1 {:.4f}".format(*baseline), flush=True)

    results = []
    combinations = list(product(*GRID.values()))
    for index, values in enumerate(combinations, 1):
        settings = dict(zip(GRID, values))
        result = baseline if settings == original else scores(
            truth, predict(match, settings), official)
        results.append((result, settings))
        if index % 12 == 0:
            print("Scored {}/{} settings".format(index, len(combinations)), flush=True)
    results.sort(key=lambda row: row[0], reverse=True)
    return baseline, results


def main():
    started = time.monotonic()
    match = load_sample(download("metadata.xml"), download("tracking.txt"))
    truth = event_labels(download("events.json"), match["names"], len(match["ball"]))
    counts = dict(zip(config.LABELS, np.bincount(truth, minlength=3).tolist()))
    print("{}: {} frames {}".format(GAME, len(truth), counts), flush=True)
    official = load_official_scorer()
    print("Scorer: {}".format("official" if official is not None else "local"), flush=True)
    baseline, results = grid_search(match, truth, official)

    print("\nRank  Radius  Weight  Blend  H/A cost  Into D  Out of D  H/A min  spellF1  macroF1")
    for rank, (result, settings) in enumerate(results[:10], 1):
        enter_dead, leave_dead = settings["DEAD_SWITCH_COSTS"]
        print("{:4d}  {:6.2f}  {:6.2f}  {:5.2f}  {:8.1f}  {:6.1f}  {:8.1f}  {:7d}"
              "  {:7.4f}  {:7.4f}".format(
                  rank, settings["CONTROL_RADIUS"], settings["CONTROL_WEIGHT"],
                  settings["TIME_BLEND"], settings["TEAM_SWITCH_COST"], enter_dead,
                  leave_dead, settings["TEAM_MIN_DURATION"], *result))

    (spell_score, macro_score), settings = results[0]
    report = {"sample": GAME, "settings": settings,
              "spellF1": spell_score, "macroF1": macro_score,
              "baseline": {"settings": current_settings(),
                           "spellF1": baseline[0], "macroF1": baseline[1]}}
    path = ROOT / "tools" / "calibrated.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\nBest spellF1 {:.4f} vs {:.4f} before. Wrote {} in {:.1f} seconds.".format(
        spell_score, baseline[0], path.relative_to(ROOT), time.monotonic() - started))


if __name__ == "__main__":
    main()

