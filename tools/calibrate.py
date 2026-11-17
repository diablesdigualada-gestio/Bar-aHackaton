# Owner: Roger
"""Calibrate possession on the public Metrica Sports samples.

Run from the repository with: python tools/calibrate.py
Use --hand-grid to repeat the original Game 3 calibration.
"""

import argparse
import csv
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
from possession import config, learned, loading, viterbi

CACHE = ROOT / ".cache" / "sample"
GAME = "Sample_Game_3"
SOURCE = "https://raw.githubusercontent.com/metrica-sports/sample-data/master/data/"
SCORER = Path("C:/mtah_ref/repo/evaluation/possession_metrics.py")
GAMES = ("Sample_Game_1", "Sample_Game_2", GAME)
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


# Symmetric H/A costs, paired D entry/exit costs and paired duration choices.
LEARNED_GRID = tuple(product(
    (7.0, 18.0, 35.0), ((3.0, 2.5), (9.0, 8.0)), ((15, 10), (30, 20), (45, 30))
))


def download(suffix, game=GAME):
    """Download one public sample file and cache it after the transfer finishes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (game + "_" + suffix)
    if path.is_file():
        return path
    url = SOURCE + game + "/" + path.name
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

    return {"ball": ball, "players": players, "speed": player_speed(players, fps),
            "team_of_slot": teams, "names": names, "pitch": PITCH}


def player_speed(players, fps):
    """Use centred differences and leave gaps in a player's track as NaN."""
    speed = np.full(players.shape[:2], np.nan, dtype=np.float32)
    delta = players[2:] - players[:-2]
    speed[1:-1] = np.hypot(delta[..., 0], delta[..., 1]) * (fps / 2)
    speed[np.isnan(players[..., 0])] = np.nan
    return speed


def read_tracking_csv(path):
    """Read the period, frame, timestamp and position pairs for one team."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        next(rows)
        next(rows)
        header = next(rows)
        if header[:3] != ["Period", "Frame", "Time [s]"] or header[-2] != "Ball":
            raise ValueError("Unexpected tracking columns in {}".format(path.name))
        tracking = np.loadtxt(handle, delimiter=",", dtype=np.float64)
    if (not np.array_equal(tracking[:, 1], np.arange(1, len(tracking) + 1))
            or not np.allclose(np.diff(tracking[:, 2]), 1 / config.FPS)):
        raise ValueError("Expected contiguous 25 fps tracking in {}".format(path.name))
    return tracking


def load_csv_sample(home_path, away_path):
    """Join the two tracking files and convert normalized coordinates to metres."""
    home = read_tracking_csv(home_path)
    away = read_tracking_csv(away_path)
    if not np.array_equal(home[:, :3], away[:, :3]):
        raise ValueError("Home and away tracking frames do not align")
    if not np.array_equal(home[:, -2:], away[:, -2:], equal_nan=True):
        raise ValueError("Home and away ball tracks differ")

    positions = np.concatenate((home[:, 3:-2], away[:, 3:-2]), axis=1)
    players = (positions.reshape(len(home), -1, 2) * PITCH).astype(np.float32)
    ball = (home[:, -2:] * PITCH).astype(np.float32)
    teams = np.full(players.shape[1], config.A, dtype=np.int8)
    teams[:(home.shape[1] - 5) // 2] = config.H
    speed = player_speed(players, config.FPS)
    # The CSV frame IDs are contiguous across halftime, but the players have moved.
    period_starts = np.flatnonzero(home[1:, 0] != home[:-1, 0]) + 1
    speed[period_starts - 1] = np.nan
    speed[period_starts] = np.nan
    return {"ball": ball, "players": players, "speed": speed,
            "team_of_slot": teams, "names": ("Home", "Away"), "pitch": PITCH}


def read_events(path):
    """Yield kind, tags, zero-based frame bounds and team from either format."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        if path.suffix == ".csv":
            for event in csv.DictReader(handle):
                tags = {tag.strip() for tag in event["Subtype"].split("-") if tag.strip()}
                yield (event["Type"], tags, int(event["Start Frame"]) - 1,
                       int(event["End Frame"]) - 1, event["Team"])
        else:
            for event in json.load(handle)["data"]:
                subtypes = event["subtypes"] or []
                if isinstance(subtypes, dict):
                    subtypes = [subtypes]
                tags = {subtype["name"] for subtype in subtypes}
                yield (event["type"]["name"], tags, event["start"]["frame"] - 1,
                       event["end"]["frame"] - 1, (event["team"] or {}).get("name"))


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
    controls = {"PASS", "CARRY", "SHOT", "RECOVERY"}
    end_stops = {"OFFSIDE", "HAND BALL", "END HALF"}
    teams = dict(zip(names, (config.H, config.A)))
    changes = defaultdict(list)
    for kind, tags, start, end, name in read_events(path):
        team = teams.get(name)

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


def switch_costs(team_cost, dead_costs):
    h, a, d = config.H, config.A, config.D
    enter_dead, leave_dead = dead_costs
    return {(h, a): team_cost, (a, h): team_cost,
            (h, d): enter_dead, (a, d): enter_dead,
            (d, h): leave_dead, (d, a): leave_dead}


def predict(match, settings):
    h, a, d = config.H, config.A, config.D
    duration = settings["TEAM_MIN_DURATION"]
    costs = switch_costs(settings["TEAM_SWITCH_COST"], settings["DEAD_SWITCH_COSTS"])
    with patch.multiple(config, CONTROL_RADIUS=settings["CONTROL_RADIUS"],
                        CONTROL_WEIGHT=settings["CONTROL_WEIGHT"],
                        TIME_BLEND=settings["TIME_BLEND"]):
        emissions = run.hand_emissions(run.frame_features(match))
    return viterbi.decode(emissions, {h: duration, a: duration, d: config.MIN_DURATION[d]}, costs)


def grid_search(match, truth, official):
    original = current_settings()
    baseline = scores(truth, predict(match, original), official)
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


def hand_grid():
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


def load_game(game):
    if game == GAME:
        match = load_sample(download("metadata.xml"), download("tracking.txt"))
        events = download("events.json")
    else:
        home = download("RawTrackingData_Home_Team.csv", game)
        away = download("RawTrackingData_Away_Team.csv", game)
        match = load_csv_sample(home, away)
        events = download("RawEventsData.csv", game)
    truth = event_labels(events, match["names"], len(match["ball"]))
    return match, truth


def learned_prediction(emissions, settings):
    team_cost, dead_costs, (team_duration, dead_duration) = settings
    durations = {config.H: team_duration, config.A: team_duration, config.D: dead_duration}
    return viterbi.decode(emissions, durations, switch_costs(team_cost, dead_costs))


def tune_decoder(emissions, truths, official):
    """Rank decoder settings by mean training spellF1, then by mean macroF1."""
    results = {}
    for settings in LEARNED_GRID:
        training_scores = [scores(truth, learned_prediction(values, settings), official)
                           for values, truth in zip(emissions, truths)]
        results[settings] = tuple(np.mean(training_scores, axis=0))
    return results


def fit_games(matrices, truths):
    return learned.fit(np.concatenate(matrices), np.concatenate(truths))


def leave_one_out():
    official = load_official_scorer()
    print("Scorer: {}".format("official" if official is not None else "local"), flush=True)
    matrices, truths, hand_scores = [], [], []
    for game in GAMES:
        match, truth = load_game(game)
        counts = dict(zip(config.LABELS, np.bincount(truth, minlength=3).tolist()))
        print("{}: {} frames {}".format(game, len(truth), counts), flush=True)
        frame = run.frame_features(match)
        matrices.append(learned.feature_matrix(frame))
        truths.append(truth)
        prediction = viterbi.decode(run.hand_emissions(frame), config.MIN_DURATION,
                                    config.SWITCH_COST)
        hand_scores.append(scores(truth, prediction, official))

    rows, training_results = [], []
    for held_out, game in enumerate(GAMES):
        train = [i for i in range(len(GAMES)) if i != held_out]
        train_matrices = [matrices[i] for i in train]
        train_truths = [truths[i] for i in train]
        print("Fitting and tuning without {}".format(game), flush=True)
        model = fit_games(train_matrices, train_truths)
        train_emissions = [learned.log_probabilities(matrix, model) for matrix in train_matrices]
        results = tune_decoder(train_emissions, train_truths, official)
        training_results.append(results)
        settings = max(results, key=results.get)

        values = learned.log_probabilities(matrices[held_out], model)
        fixed = viterbi.decode(values, config.MIN_DURATION, config.SWITCH_COST)
        tuned = learned_prediction(values, settings)
        row = hand_scores[held_out] + scores(truths[held_out], fixed, official) + scores(
            truths[held_out], tuned, official)
        rows.append(row)
        print("{} decoder: {}".format(game, settings), flush=True)

    mean = np.mean(rows, axis=0)
    mode = "learned" if mean[4] > mean[0] else "hand"
    print("\n                 Hand spell/macro  Learned fixed     Learned tuned")
    for game, row in zip((*GAMES, "Mean"), (*rows, mean)):
        print("{:14s}   {:.4f}   {:.4f}    {:.4f}   {:.4f}    {:.4f}   {:.4f}".format(game, *row))
    # Choose settings for the all-game model using only the fold training scores.
    average_training = {}
    for settings in LEARNED_GRID:
        fold_scores = [result[settings] for result in training_results]
        average_training[settings] = tuple(np.mean(fold_scores, axis=0))
    final_settings = max(average_training, key=average_training.get)
    learned.save(fit_games(matrices, truths))
    print("Selected mode: {}. Learned decoder settings: {}.".format(mode, final_settings))
    print("Wrote {}".format(learned.WEIGHTS_PATH.relative_to(ROOT)))


def occluded_match(match, truth, seed):
    """Same match with simulated ball dropouts during live play."""
    rng = np.random.default_rng(seed)
    hidden = dict(match)
    hidden["ball"] = learned.occlude(match["ball"], truth != config.D, rng)
    return hidden


def robust():
    """Leave one game out: hand emissions against the robust learned model.

    Training uses occluded copies of the other games only. Each held-out game is scored twice, as
    delivered and with simulated dropouts. The robust model is selected only if its mean spellF1
    beats the hand emissions in both conditions.
    """
    official = load_official_scorer()
    print("Scorer: {}".format("official" if official is not None else "local"), flush=True)
    clean, hidden, truths = [], [], []
    for k, game in enumerate(GAMES):
        match, truth = load_game(game)
        print("{}: {} frames".format(game, len(truth)), flush=True)
        clean.append(run.frame_features(match))
        hidden.append(run.frame_features(occluded_match(match, truth, config.OCCLUSION_SEED + k)))
        truths.append(truth)

    def hand(frame):
        return viterbi.decode(run.hand_emissions(frame), config.MIN_DURATION, config.SWITCH_COST)

    rows, training_results = [], []
    for held_out, game in enumerate(GAMES):
        train = [i for i in range(len(GAMES)) if i != held_out]
        matrices = [learned.feature_matrix(hidden[i], robust=True) for i in train]
        model = fit_games(matrices, [truths[i] for i in train])
        emissions = [learned.log_probabilities(m, model) for m in matrices]
        results = tune_decoder(emissions, [truths[i] for i in train], official)
        training_results.append(results)
        settings = max(results, key=results.get)

        row = []
        for frame in (clean[held_out], hidden[held_out]):
            values = learned.log_probabilities(learned.feature_matrix(frame, robust=True), model)
            row += scores(truths[held_out], hand(frame), official)
            row += scores(truths[held_out], learned_prediction(values, settings), official)
        rows.append(row)
        print("{} decoder: {}".format(game, settings), flush=True)

    mean = np.mean(rows, axis=0)
    print("\n                 Clean: hand          robust            "
          "Occluded: hand       robust")
    for game, row in zip((*GAMES, "Mean"), (*rows, mean)):
        print("{:14s}   {:.4f} {:.4f}    {:.4f} {:.4f}    {:.4f} {:.4f}    {:.4f} {:.4f}".format(
            game, *row))
    wins = mean[2] > mean[0] and mean[6] > mean[4]
    print("Robust wins clean and occluded: {}".format(wins))

    average = {s: tuple(np.mean([r[s] for r in training_results], axis=0)) for s in LEARNED_GRID}
    team_cost, (to_dead, from_dead), (team_duration, dead_duration) = max(average,
                                                                          key=average.get)
    model = fit_games([learned.feature_matrix(f, robust=True) for f in hidden], truths)
    model["decoder"] = np.array([team_cost, to_dead, from_dead, team_duration, dead_duration])
    learned.save(model, learned.ROBUST_WEIGHTS_PATH)
    report = {"rows": dict(zip((*GAMES, "Mean"), [list(map(float, r)) for r in (*rows, mean)])),
              "columns": ["clean_hand_spell", "clean_hand_macro", "clean_robust_spell",
                          "clean_robust_macro", "occluded_hand_spell", "occluded_hand_macro",
                          "occluded_robust_spell", "occluded_robust_macro"],
              "robust_wins": bool(wins), "decoder": model["decoder"].tolist()}
    path = ROOT / "tools" / "robust.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Wrote {} and {}".format(learned.ROBUST_WEIGHTS_PATH.relative_to(ROOT),
                                   path.relative_to(ROOT)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hand-grid", action="store_true", help="repeat the Game 3 hand grid")
    parser.add_argument("--robust", action="store_true",
                        help="train and test the robust model with simulated dropouts")
    args = parser.parse_args()
    if args.hand_grid:
        hand_grid()
    elif args.robust:
        robust()
    else:
        leave_one_out()


if __name__ == "__main__":
    main()

