# Owner: Jordi
"""Multinomial logistic emissions in H, A, D order."""

import json
from pathlib import Path

import numpy as np

from . import config

WEIGHTS_PATH = Path(__file__).with_name("learned_weights.json")


def feature_matrix(frame):
    """Build the same bounded feature columns for training and prediction."""
    columns = [frame["control"]]
    for name, limit in config.LEARNED_CLIPS.items():
        values = frame[name]
        missing = np.isnan(values)
        columns.append(np.where(missing, 0.0, np.clip(values, 0.0, limit)))
        columns.append(missing)
    columns.extend((frame["out"], frame["active_players"], frame["seen"]))
    return np.column_stack(columns).astype(np.float64)


def log_softmax(scores):
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
    x = (matrix - model["mean"]) / model["scale"]
    return log_softmax(x @ model["weights"] + model["bias"])


def save(model, path=WEIGHTS_PATH):
    values = {name: array.tolist() for name, array in model.items()}
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")


def load(path=WEIGHTS_PATH):
    values = json.loads(path.read_text(encoding="utf-8"))
    return {name: np.array(array, dtype=np.float64) for name, array in values.items()}
