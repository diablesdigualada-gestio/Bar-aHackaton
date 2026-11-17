"""Three-state decoder (H, A, D) with minimum durations.

Owner: Jordi.

spellF1 matches whole possessions by temporal IoU, so a flickering per-frame answer is worth almost
nothing even when most frames are right. That is why we decode the whole sequence at once with a
Viterbi over an explicit-duration HMM: each state is a left-to-right chain of MIN_DURATION
substates, so no state can be entered and left in fewer frames than that. Switching state pays a
fixed cost. This is the same trick used in temporal action segmentation and in the top solutions
of sequence-labelling Kaggle competitions (sleep state detection, DFL event detection): strong
per-step evidence, then a global decoder that refuses short spurious segments.

Emissions are log-scores, not probabilities. Only differences between states matter.
"""

import numpy as np

from . import config


def build_chains(min_duration):
    """(state_of_sub, first_sub, last_sub) for the expanded state space."""
    state_of_sub, first, last = [], {}, {}
    for state in (config.H, config.A, config.D):
        first[state] = len(state_of_sub)
        state_of_sub.extend([state] * max(1, int(min_duration[state])))
        last[state] = len(state_of_sub) - 1
    return np.array(state_of_sub, dtype=np.int8), first, last


def emissions(control, dead_score, push):
    """(n, 3) log-scores per frame.

    H gets +control, A gets -control, D gets dead_score. The tagging push goes to H or A.
    """
    e = np.zeros((len(control), 3), dtype=np.float32)
    e[:, config.H] = config.CONTROL_WEIGHT * control + push
    e[:, config.A] = -config.CONTROL_WEIGHT * control - push
    e[:, config.D] = dead_score
    return e


def decode(scores, min_duration=config.MIN_DURATION, switch_cost=config.SWITCH_COST):
    """Most likely state per frame. scores is (n, 3); returns int8 array of length n."""
    n = len(scores)
    state_of_sub, first, last = build_chains(min_duration)
    m = len(state_of_sub)
    states = (config.H, config.A, config.D)

    # Start in D: every match begins with a stoppage before kickoff.
    v = np.full(m, -np.inf)
    v[first[config.D]] = scores[0, config.D]
    back = np.zeros((n, m), dtype=np.int16)

    # Precompute the "shift along the chain" predecessor of every substate.
    shift_from = np.arange(m) - 1
    for s in states:
        shift_from[first[s]] = -1

    for t in range(1, n):
        new = np.full(m, -np.inf)
        arg = np.zeros(m, dtype=np.int16)

        # Inside a chain: come from the previous substate.
        inside = shift_from >= 0
        new[inside] = v[shift_from[inside]]
        arg[inside] = shift_from[inside]

        for s in states:
            # The last substate can also stay where it is.
            stay = v[last[s]]
            if stay > new[last[s]]:
                new[last[s]] = stay
                arg[last[s]] = last[s]
            # Entering a chain: from the last substate of another state, paying the switch cost.
            best, best_from = -np.inf, 0
            for r in states:
                if r == s:
                    continue
                cand = v[last[r]] - switch_cost[(r, s)]
                if cand > best:
                    best, best_from = cand, last[r]
            new[first[s]] = best
            arg[first[s]] = best_from

        new += scores[t, state_of_sub]
        v = new
        back[t] = arg

    # Backtrack from the best finishing substate.
    path = np.zeros(n, dtype=np.int8)
    sub = int(np.argmax(v))
    for t in range(n - 1, -1, -1):
        path[t] = state_of_sub[sub]
        sub = back[t, sub]
    return path
