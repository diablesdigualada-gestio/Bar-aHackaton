"""Pipeline parameters.

Owner: Jordi.

Every magic number lives here and only here. If one shows up inside another module, it gets moved
back. Each value says where it comes from: the literature, football common sense, or something we
measured by watching the video. Selected values were calibrated on the open Metrica sample.
None of them was fitted against the public 5-minute ground truth;
that window is used to check that the pipeline runs end to end and nothing else.
"""

# Match and files
GAME = "BAR-ATH"
SOURCE = "tactical"
FPS = 25
N_FRAMES = 199319
PITCH = (105.3, 68.0)          # metres, same value as games.py in the official repository

# Graded video frames, inclusive. Outside these we write D and it costs nothing.
HALVES = ((11185, 90651), (110808, 190197))

# Internal state codes. Order matters: it is the index into the Viterbi matrices.
H, A, D = 0, 1, 2
LABELS = ("H", "A", "D")

# Ball (Roger)
MAX_GAP_INTERPOLATED = 12      # frames: gaps up to half a second are filled with a straight line
OUT_OF_PITCH_MARGIN = 0.6      # metres past the line before we believe the ball went out
BALL_SPEED_WINDOW = 5          # frames used to smooth ball speed

# Ball control (Jordi)
# Link and Hoernig (2017) use an influence radius of roughly 1.5 to 2 m for individual control.
# Original radius rationale: automatic video tracking is noisier than optical multi-camera
# systems, so we open it up a bit.
CONTROL_RADIUS = 1.6           # metres, calibrated on Metrica Sample Game 3
CONTROL_SLOPE = 0.6            # metres, softness of the radius sigmoid
CONTROL_SPEED = 13.0           # m/s, above this the ball is travelling and nobody controls it
SPEED_SLOPE = 2.0              # m/s
ADVANTAGE_SCALE = 1.5          # metres of distance gap between teams that saturates the evidence
CONTROL_WEIGHT = 0.85          # per-frame evidence when one team clearly has the ball, calibrated on Metrica Sample Game 3

# Time to ball (Jordi). Values from Spearman (2018): reaction 0.7 s, top speed 5 m/s.
REACTION_TIME = 0.7            # seconds
MAX_PLAYER_SPEED = 5.0         # m/s
TIME_ADVANTAGE_SCALE = 0.4     # seconds of arrival gap that saturates the evidence
TIME_BLEND = 0.0               # 0 = distance only, 1 = arrival time only, calibrated on Metrica Sample Game 3

# Dead ball (Carles)
STOPPAGE_PLAYER_SPEED = 1.6    # m/s team average: below this the game looks stopped
SLOW_PLAYERS_WEIGHT = 0.35
OUT_OF_PITCH_WEIGHT = 1.2
NO_BALL_WEIGHT = 0.04          # tiny on purpose: the ball goes missing all the time in live play
MIN_PLAYERS_IN_MATCH = 12      # fewer tracked players means halftime or before/after the match
PLAYER_SPEED_WINDOW = 50       # frames used to smooth the average player speed

# Smart Tagging priors (Carles). Inferred automatically by Metrica, hence the small weights.
PRE_RESTART_S = 4.0            # seconds before a set piece centre that we push towards D
POST_RESTART_S = 3.0           # seconds after it that we push towards the restarting team
RESTART_DEAD_WEIGHT = 0.6
RESTART_TEAM_WEIGHT = 0.25
PHASE_TEAM_WEIGHT = 0.03       # tagged phases (BUILD UP, PROGRESSION...) give a very weak push
USE_PHASES = True

# Emissions (Jordi)
EMISSIONS = "hand"             # "hand", "learned" or "robust", see docs/diables.md for why hand
# Upper bounds for distance (m), arrival time (s) and speed (m/s) features.
LEARNED_CLIPS = {
    "d_home": 25.0, "d_away": 25.0,
    "t_home": 6.0, "t_away": 6.0,
    "ball_speed": 40.0, "mean_player_speed": 8.0,
}
LEARNED_SCALE_FLOOR = 0.1     # avoid amplifying almost constant features
LEARNED_SEED = 7
LEARNED_INIT_SCALE = 0.01
LEARNED_STEPS = 200
LEARNED_STEP_SIZE = 0.2
LEARNED_L2 = 0.01

# Robust learned emissions (Jordi). The plain learned model leans on "ball not seen" to say D, which
# is wrong here: the ball is missing on 41% of graded frames, almost always in live play. The robust
# model drops every visibility signal and trains on Metrica samples with simulated dropouts.
ROBUST_BALL_SPEED_FILL = 5.0   # m/s, a typical live ball speed: no hint towards control or D
OCCLUSION_SHARE = 0.35         # share of live frames hidden in training and in the stress test
OCCLUSION_MIN = 5              # frames, shortest simulated dropout
OCCLUSION_MAX = 60             # frames, longest simulated dropout (2.4 s)
OCCLUSION_SEED = 11

# Viterbi (Jordi)
# Minimum durations in frames. A possession shorter than 0.6 s is a rebound, not a possession.
MIN_DURATION = {H: 45, A: 45, D: 20}  # grid on Metrica games 1 to 3, clean and with dropouts, see docs
# Cost of switching state. Higher means fewer invented possessions, which spellF1 punishes hard.
SWITCH_COST = {
    (H, A): 7.0, (A, H): 7.0,
    (H, D): 3.0, (A, D): 3.0,
    (D, H): 2.5, (D, A): 2.5,
}

# Learned decoder settings ranked by mean training score across folds.
LEARNED_MIN_DURATION = {H: 45, A: 45, D: 30}
LEARNED_SWITCH_COST = {
    (H, A): 18.0, (A, H): 18.0,
    (H, D): 9.0, (A, D): 9.0,
    (D, H): 8.0, (D, A): 8.0,
}
