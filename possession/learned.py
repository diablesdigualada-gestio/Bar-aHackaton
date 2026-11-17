# Owner: Jordi
"""Multinomial logistic emissions in H, A, D order."""

import json
from pathlib import Path

import numpy as np

from . import config

WEIGHTS_PATH = Path(__file__).with_name("learned_weights.json")
ROBUST_WEIGHTS_PATH = Path(__file__).with_name("robust_weights.json")

# Features that only exist when the ball is tracked. The robust model never sees whether they are
# missing, so "no ball" cannot become a shortcut to D.
BALL_FEATURES = ("d_home", "d_away", "t_home", "t_away", "ball_speed")


def feature_matrix(frame, robust=False):
    """Build the same bounded feature columns for training and prediction.

    robust drops every ball visibility signal: no seen column, no missing flags for ball features,
    and a missing ball feature is filled with a neutral value (far for distances and times, a
    typical live speed for the ball) instead of zero.
    """
    columns = [frame["control"]]
    for name, limit in config.LEARNED_CLIPS.items():
        values = frame[name]
        missing = np.isnan(values)
        if robust and name in BALL_FEATURES:
            fill = config.ROBUST_BALL_SPEED_FILL if name == "ball_speed" else limit
            columns.append(np.where(missing, fill, np.clip(values, 0.0, limit)))
            continue
        columns.append(np.where(missing, 0.0, np.clip(values, 0.0, limit)))
        columns.append(missing)
    columns.extend((frame["out"], frame["active_players"]))
    if not robust:
        columns.append(frame["seen"])
    return np.column_stack(columns).astype(np.float64)


def occlude(ball, live, rng, share=None, shortest=None, longest=None):
    """Copy of ball with simulated tracker dropouts during live play.

    Runs of shortest..longest frames are hidden until share of the live frames is missing, the
    way the real tracker loses the ball behind players. Dead frames are never touched, so the
    model cannot learn that a missing ball means a stoppage.
    """
    share = config.OCCLUSION_SHARE if share is None else share
    shortest = config.OCCLUSION_MIN if shortest is None else shortest
    longest = config.OCCLUSION_MAX if longest is None else longest
    hidden = np.zeros(len(ball), dtype=bool)
    target = share * live.sum()
    while (hidden & live).sum() < target:
        start = int(rng.integers(len(ball)))
        hidden[start:start + int(rng.integers(shortest, longest + 1))] = True
    out = ball.copy()
    out[hidden & live] = np.nan
    return out


def log_softmax(scores):
    """Row-wise log of the softmax, shifted by the row maximum so large scores never overflow."""
    shifted = scores - scores.max(axis=1, keepdims=True)
    return shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))


def fit(matrix, labels):
    """Fit feature scaling and L2-regularized weights on the supplied frames."""
    mean = matrix.mean(axis=0)
    scale = np.maximum(matrix.std(axis=0), config.LEARNED_SCALE_FLOOR)
    x = (matrix - mean) / scale
    targets = np.eye(len(config.LABELS))[labels]
    rng = np.random.default_rng(config.LEARNED_SEED)
    weights = rng.normal(0.0, config.LEARNED_INIT_SCALE, (x.shape[1], targets.shape[1]))
    bias = np.zeros(targets.shape[1])

    for _ in range(config.LEARNED_STEPS):
        residual = np.exp(log_softmax(x @ weights + bias)) - targets
        gradient = (x.T @ residual) / len(x) + config.LEARNED_L2 * weights
        weights -= config.LEARNED_STEP_SIZE * gradient
        bias -= config.LEARNED_STEP_SIZE * residual.mean(axis=0)

    return {"mean": mean, "scale": scale, "weights": weights, "bias": bias}


def log_probabilities(matrix, model):
    """(n, 3) log P(H, A, D) per frame: standardise with the stored scaling, then apply the weights."""
    x = (matrix - model["mean"]) / model["scale"]
    return log_softmax(x @ model["weights"] + model["bias"])


def save(model, path=WEIGHTS_PATH):
    """Write a fitted model (arrays of numbers) as indented JSON, so it can be diffed and committed."""
    values = {name: array.tolist() for name, array in model.items()}
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")


def load(path=WEIGHTS_PATH):
    """Read a model written by save() back into float64 numpy arrays."""
    values = json.loads(path.read_text(encoding="utf-8"))
    return {name: np.array(array, dtype=np.float64) for name, array in values.items()}
