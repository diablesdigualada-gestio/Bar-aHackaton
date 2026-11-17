"""Per-frame features and per-team control evidence.

Owner: Jordi.

The idea comes from the individual ball possession literature (Link and Hoernig 2017) and from
event detection on tracking data (Vidal-Codina et al. 2022): a team has the ball when one of its
players is close to it, closer than any opponent, and the ball is slow enough to be under control.
A travelling ball (pass, shot, rebound) gives evidence to nobody. That way the Viterbi keeps the
possession with the team that played it, which is exactly what the challenge rules ask for.

Main output: control[t] in [-1, 1]. Positive means home, negative away, 0 no evidence.
"""

import numpy as np

from . import config


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def nearest_distance_per_team(ball, players, team_of_slot):
    """(d_home, d_away) in metres. NaN when there is no ball or no player of that team."""
    delta = players - ball[:, None, :]
    dist = np.hypot(delta[..., 0], delta[..., 1])
    dist = np.where(np.isnan(dist), np.inf, dist)

    out = []
    for team in (config.H, config.A):
        cols = team_of_slot == team
        if not np.any(cols):
            out.append(np.full(len(ball), np.nan, dtype=np.float32))
            continue
        d = dist[:, cols].min(axis=1)
        out.append(np.where(np.isinf(d), np.nan, d).astype(np.float32))
    return out[0], out[1]


def player_velocity(players, fps=config.FPS):
    """(n, slots, 2) velocity vectors in m/s from centred position differences."""
    vel = np.zeros_like(players)
    vel[1:-1] = (players[2:] - players[:-2]) * (fps / 2.0)
    return np.nan_to_num(vel, nan=0.0)


def time_to_ball_per_team(ball, players, team_of_slot, velocity):
    """(t_home, t_away): seconds the fastest player of each team needs to reach the ball.

    Physics model from Spearman (2018) and Fernandez and Bornn (2018), the one behind pitch
    control: during a reaction time the player keeps his current velocity, then runs straight at
    the ball at top speed. A player 3 m away but running the wrong way loses to one 4 m away
    sprinting at it. Nearest distance cannot tell those two apart; arrival time can.
    """
    react = config.REACTION_TIME
    after_react = players + velocity * react
    delta = after_react - ball[:, None, :]
    run = np.hypot(delta[..., 0], delta[..., 1]) / config.MAX_PLAYER_SPEED
    t = np.where(np.isnan(run), np.inf, run + react)

    out = []
    for team in (config.H, config.A):
        cols = team_of_slot == team
        best = t[:, cols].min(axis=1) if np.any(cols) else np.full(len(ball), np.inf)
        out.append(np.where(np.isinf(best), np.nan, best).astype(np.float32))
    return out[0], out[1]


def control_evidence(d_home, d_away, ball_speed, t_home=None, t_away=None):
    """control[t] in [-1, 1].

    Three factors multiplied:
      close   the nearest player of either team is inside the control radius
      slow    the ball is not flying
      who     gap between the teams, saturated with tanh. Arrival time gap when we have it,
              distance gap otherwise. Both blended so neither can flip the answer alone.
    """
    d_min = np.fmin(d_home, d_away)
    close = sigmoid((config.CONTROL_RADIUS - d_min) / config.CONTROL_SLOPE)
    slow = sigmoid((config.CONTROL_SPEED - ball_speed) / config.SPEED_SLOPE)
    who = np.tanh((d_away - d_home) / config.ADVANTAGE_SCALE)
    if t_home is not None and t_away is not None:
        who_time = np.tanh((t_away - t_home) / config.TIME_ADVANTAGE_SCALE)
        w = config.TIME_BLEND
        who = (1.0 - w) * who + w * who_time

    control = close * slow * who
    # No ball, or one team not tracked: no evidence either way.
    control = np.where(np.isnan(control), 0.0, control)
    return control.astype(np.float32)


def active_players(players):
    """Number of slots with a position on each frame."""
    return np.sum(~np.isnan(players[..., 0]), axis=1).astype(np.int16)


def mean_player_speed(speed):
    """Average speed of tracked players, m/s. NaN if nobody is tracked."""
    valid = ~np.isnan(speed)
    n = valid.sum(axis=1)
    total = np.where(valid, speed, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / n
    mean[n == 0] = np.nan
    return mean.astype(np.float32)
