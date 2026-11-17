"""Dead-ball evidence and per-team push from the Smart Tagging.

Owner: Carles.

The official baseline only knows "I cannot see the ball". We add four more signals:

  1. ball clearly past the lines
  2. players walking: in a stoppage the average speed drops sharply
  3. few tracked players: halftime, before kickoff, after the final whistle
  4. the Smart Tagging marks set pieces, and every restart closes a stretch of D

Everything comes out as per-frame scores that the Viterbi adds to its emission. No single signal
decides on its own, on purpose: the tagging is inferred and has errors.
"""

from difflib import SequenceMatcher

import numpy as np

from . import config
from .ball import moving_mean

SET_PIECE_CODE = "set pieces"
# Codes where the tagged team is the attacking side, and codes where it is the defending side.
ATTACK_CODES = ("build up", "progression", "creating chances", "attacking transition",
                "ball in final third", "ball in the box", "long ball")
DEFENCE_CODES = ("defending in defensive third", "defending in middle third",
                 "defending in attacking third", "defensive transition")


def dead_evidence(ball_seen, out, player_speed, n_players):
    """Per-frame score in favour of D. Negative when everything says live play."""
    pace = moving_mean(player_speed, config.PLAYER_SPEED_WINDOW)
    pace = np.where(np.isnan(pace), 0.0, pace)
    factor = np.clip((config.STOPPAGE_PLAYER_SPEED - pace) / config.STOPPAGE_PLAYER_SPEED, -1, 1)

    score = config.SLOW_PLAYERS_WEIGHT * factor
    score += config.OUT_OF_PITCH_WEIGHT * out
    score += config.NO_BALL_WEIGHT * (~ball_seen)
    # Outside the match D has to win every time, hence the large weight.
    score += 5.0 * (n_players < config.MIN_PLAYERS_IN_MATCH)
    return score.astype(np.float32)


def team_of_tag(tag_name, names):
    """H, A or None. Fuzzy match because the tagging spells it 'Atletic Club'."""
    if not tag_name or tag_name.strip().upper() == "N/A":
        return None
    name = tag_name.lower()
    s_home = SequenceMatcher(None, name, (names[0] or "").lower()).ratio()
    s_away = SequenceMatcher(None, name, (names[1] or "").lower()).ratio()
    if max(s_home, s_away) < 0.4:
        return None
    return config.H if s_home >= s_away else config.A


def tagging_priors(events, names, n_frames, fps=config.FPS):
    """(dead_score, push) per frame from the Smart Tagging.

    Positive push favours home, negative favours away.
    """
    dead = np.zeros(n_frames, dtype=np.float32)
    push = np.zeros(n_frames, dtype=np.float32)
    pre = int(config.PRE_RESTART_S * fps)
    post = int(config.POST_RESTART_S * fps)

    for ev in events:
        team = team_of_tag(ev["tags"].get("Team"), names)
        sign = 0.0 if team is None else (1.0 if team == config.H else -1.0)
        start = max(0, ev["start"])
        end = min(n_frames, ev["end"])

        if ev["code"] == SET_PIECE_CODE:
            # The tagging covers about 5 s around the restart: we take its centre as the restart.
            centre = (start + end) // 2
            dead[max(0, centre - pre):centre] += config.RESTART_DEAD_WEIGHT
            push[centre:min(n_frames, centre + post)] += sign * config.RESTART_TEAM_WEIGHT
        elif config.USE_PHASES and ev["code"] in ATTACK_CODES:
            push[start:end] += sign * config.PHASE_TEAM_WEIGHT
        elif config.USE_PHASES and ev["code"] in DEFENCE_CODES:
            push[start:end] -= sign * config.PHASE_TEAM_WEIGHT

    return dead, push
