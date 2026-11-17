"""Ball possession from tracking data. Team Diables, More Than a Hack 2027.

How a run flows through the package (run.py drives it):

    loading.py   raw ATD, metadata and Smart Tagging into numpy arrays in metres     (Roger)
    ball.py      fill short ball gaps, ball speed, ball out of the pitch              (Roger)
    features.py  per team distance and arrival time to the ball, control evidence    (Jordi)
    deadball.py  evidence that the ball is dead, Smart Tagging priors                (Carles)
    viterbi.py   per frame log-scores to H, A, D segments with minimum durations     (Jordi)
    output.py    validated submission CSV, possession spells, viewer JSON             (Carles)

config.py holds every parameter with its source, and learned.py the optional learned emissions.
"""
