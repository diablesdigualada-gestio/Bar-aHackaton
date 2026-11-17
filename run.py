"""Regenerate the submission from the provided data.

    pip install -r requirements.txt
    python run.py --data data --team diables

Writes submission/<team>.csv and, with --viewer, web/public/match.json for the viewer.
Deterministic: same data in, same file out, byte for byte.
"""

import argparse
import os
import time

import numpy as np

from possession import ball as ballmod
from possession import config, deadball, features, loading, output, viterbi

HERE = os.path.dirname(os.path.abspath(__file__))


def build_states(match, events):
    """Whole pipeline after loading: features, evidence, decode. Returns int8 states."""
    ball, seen = ballmod.fill_gaps(match["ball"])
    speed = ballmod.speed(ball)
    out = ballmod.out_of_pitch(ball)

    d_home, d_away = features.nearest_distance_per_team(ball, match["players"],
                                                        match["team_of_slot"])
    velocity = features.player_velocity(match["players"])
    t_home, t_away = features.time_to_ball_per_team(ball, match["players"],
                                                    match["team_of_slot"], velocity)
    control = features.control_evidence(d_home, d_away, speed, t_home, t_away)

    dead = deadball.dead_evidence(seen, out, features.mean_player_speed(match["speed"]),
                                  features.active_players(match["players"]))
    tag_dead, push = deadball.tagging_priors(events, match["names"], len(ball))

    scores = viterbi.emissions(control, dead + tag_dead, push)
    return viterbi.decode(scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=os.environ.get("MTAH_DATA_DIR",
                                                         os.path.join(HERE, "data")))
    parser.add_argument("--team", default="diables")
    parser.add_argument("--out", default=os.path.join(HERE, "submission"))
    parser.add_argument("--cache", default=os.path.join(HERE, ".cache"))
    parser.add_argument("--no-tagging", action="store_true", help="ignore the Smart Tagging")
    parser.add_argument("--viewer", action="store_true", help="also write web/public/match.json")
    args = parser.parse_args()

    t0 = time.time()
    match = loading.load_match(args.data, args.cache)
    print("loaded tracking in {:.1f} s, H = {}, A = {}".format(time.time() - t0, *match["names"]))

    events = [] if args.no_tagging else loading.read_tagging(match["paths"]["tagging"])
    print("smart tagging instances: {}".format(len(events)))

    t1 = time.time()
    states = build_states(match, events)
    labels = output.labels_from_states(states)
    print("decoded in {:.1f} s".format(time.time() - t1))

    path = output.write_submission(os.path.join(args.out, "{}.csv".format(args.team)), labels)
    s = output.summary(labels, match["names"])
    print("wrote {}".format(path))
    print("possession {:.1%} / {:.1%}, ball in play {:.1%}, spells H {} A {} D {}".format(
        s["possession_home"], s["possession_away"], s["ball_in_play"],
        s["spells"]["H"], s["spells"]["A"], s["spells"]["D"]))

    if args.viewer:
        viewer = output.export_viewer(os.path.join(HERE, "web", "public", "match.json"),
                                      labels, match["names"], match)
        print("viewer data {}".format(viewer))


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    main()
