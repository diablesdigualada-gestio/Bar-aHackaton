# Diables: ball possession from tracking with a duration-aware decoder

Team Diables. More Than a Hack 2027, Phase 1.

## 1. Idea

The leaderboard metric, spellF1, matches whole possessions by temporal overlap. A system that is
right on most frames but flickers scores almost nothing: the official nearest-player baseline has
macroF1 0.65 and spellF1 0.05. So the problem is not "who is closest to the ball on this frame",
it is "segment the match into possessions and stoppages". We split it in two layers:

1. **Evidence per frame**, from physics and football rules.
2. **One global decoder** that turns that evidence into segments and refuses segments that are too
   short to be real possessions.

This is the structure of temporal action segmentation (frame scores, then a structured decoder),
and of the strongest public solutions in Kaggle sequence-labelling competitions such as the DFL
Bundesliga event detection and the sleep state detection challenges, where per-step scores were
always followed by a decoder or peak logic that enforces the shape of real events.

## 2. Evidence per frame

### 2.1 Who controls the ball

For every frame and team we compute two quantities:

- **Nearest distance** from the team to the ball, in metres.
- **Time to ball**: seconds the fastest player of the team needs to reach the ball. Each player
  keeps his current velocity for a reaction time of 0.7 s, then runs straight at the ball at
  5 m/s. This is the motion model behind pitch control (Spearman 2018; Fernandez and Bornn 2018).
  It separates a player 3 m away running the wrong way from one 4 m away sprinting at the ball,
  which nearest distance cannot do.

The control evidence is the product of three factors:

- *close*: the nearest player of either team is within a control radius of 1.6 m.
  Link and Hoernig (2017) report a range of 1.5 to 2 m for individual possession.
- *slow*: the ball moves below 13 m/s, so it is at a player's feet and not travelling.
- *who*: the distance gap between teams, saturated with tanh. The arrival-time blend is
  available through `TIME_BLEND` and calibrated to zero.

A ball in flight gives evidence to nobody. The decoder then keeps the possession with the team
that played it, which is the challenge rule: passes, deflections that do not intercept and aerial
duels without control do not change possession.

### 2.2 Is the ball dead

Four signals, added as a score for D:

1. ball clearly outside the lines (0.6 m margin),
2. players walking: average tracked player speed, smoothed over 2 s, below 1.6 m/s,
3. fewer than 12 tracked players: halftime, before kickoff, after the final whistle,
4. Smart Tagging set pieces: each one is a restart, and a restart closes a dead-ball stretch. We
   push towards D in the 4 s before the centre of each set piece interval, and towards the tagged
   restarting team in the 3 s after.

A missing ball adds only a tiny amount: the ball is missing on 41% of graded frames, mostly during
live play (occlusions), so treating "no ball" as "dead ball" is the main error of the baseline.
Short gaps (up to 0.5 s) are filled by linear interpolation.

Tagged phases with a team (BUILD UP, PROGRESSION, DEFENDING IN...) add a very weak push towards the
attacking team. Weak on purpose: they are phases, not possessions, and they are inferred.

## 3. Decoder

Three states, H, A, D. Each state is expanded into a left-to-right chain of substates,
the classical explicit-duration HMM construction. A state must walk
its chain before a transition. The calibrated hand settings require 1.2 s for possession and
0.8 s for stoppages. Switching between teams costs 7 units of log-score, entering D costs 3,
and leaving D costs 2.5. Viterbi finds the best segmentation in one pass.

With hand emissions, H gets +control, A gets -control, and D gets the dead-ball score.
During an occlusion, the hand scores are close to zero and the decoder tends to stay in the
current state. Both emission modes add the Smart Tagging scores before decoding.

## 4. Possession rules implemented

- A possession is a maximal run of one team with the ball alive. Dead ball is never a possession.
- Possession changes only with controlled possession by the other team: close, slow ball, clear
  advantage, sustained long enough to pay the switch cost.
- Touches without control, deflections and balls in flight do not change possession (no evidence).
- Frames outside the graded halves are written as D.

## 5. Assets

| Asset | Used | How |
|---|---|---|
| Tactical ATD | yes | players, ball, speeds; team of every slot from the metadata |
| Smart Tagging | yes | set pieces as restart priors, team phases as weak priors |
| Homography | no | positions are already in pitch coordinates in the ATD |
| Videos | no, only watched | to sanity-check behaviour by eye, no labels taken from them |
| Broadcast ATD | no | different timeline, not needed |

## 6. Training data

We used the three Metrica Sports open sample games for training and evaluation. Games 1 and 2
supply CSV tracking and events. Game 3 supplies EPTS tracking and JSON events. We derived H, A
and D frame labels from the public events using the same rules for all three games. Play starts
dead, recognised restarts resume play, and passes, carries, shots and controlled recoveries can
change possession while live. Stoppages hold D until the next recognised restart. The challenge
match contributed no tracking, events or labels to calibration or training.
[Metrica Sports sample data](https://github.com/metrica-sports/sample-data)

## 7. Limitations

- All three sample games use event-derived labels and optical tracking. Generalisation to
  challenge video tracking remains unmeasured.
- The event file can leave restart gaps or place changes of control late. The label rules hold
  D until a recognised restart and retain the current team between control events.
- Tracking slots are tracklets, not people, so we cannot use per-player history (for instance,
  who touched the ball last before an occlusion beyond the current state).
- The Smart Tagging time of the restart is approximated by the centre of the tagged interval.
- Long ball occlusions during live play keep the previous possession; if the ball changed hands
  inside the occlusion the change is detected late.

## Calibration

`python tools/calibrate.py --hand-grid` scores 96 settings on all 143,761 frames of Metrica Sports
Sample Game 3. The frame labels come from its public event data. Passes, carries, shots and controlled
recoveries establish team possession. Stoppages persist until a tagged restart. The exact
rules are in `event_labels` in `tools/calibrate.py`. Calibration used no challenge-match
data. Every run used an empty Smart Tagging list. [Public sample files](https://github.com/metrica-sports/sample-data/tree/master/data/Sample_Game_3)

| Parameter | Grid values |
|---|---|
| Control radius (m) | 1.6, 2.2, 3.0 |
| Control weight | 0.55, 0.85 |
| Time blend | 0.0, 0.5 |
| H-to-A and A-to-H switch cost | 7.0, 18.0 |
| Switch costs (into D, out of D) | (3.0, 2.5), (9.0, 8.0) |
| Minimum H and A duration (frames) | 15, 30 |

The grid ranks settings by mean spellF1 across IoUs 0.3 through 0.7, with macroF1 breaking
ties. The minimum D duration stays at 20 frames.

The winning setting used a 1.6 m radius, 0.85 control weight, 0.0 time blend,
a team switch cost of 7, D switch costs of 3 in and 2.5 out, and a 30-frame
H/A minimum. With the official scorer, spellF1 went from 0.5385 to 0.5876
and macroF1 went from 0.8784 to 0.8944. The scores and settings are recorded in
`tools/calibrated.json`.

## Learned emissions

The learned model is NumPy multinomial logistic regression over H, A and D. Its frame inputs
are control evidence, nearest-player distance and time to ball per team, ball speed, out-of-pitch
status, mean player speed, active-player count and whether the ball was seen. Distances, arrival
times and speeds are clipped and have missing-value indicators. The model standardises the inputs
using the training games and fits with full-batch gradient descent, L2 regularisation and a fixed
seed. Its log-probabilities go into the same Viterbi decoder as the hand scores.

`python tools/calibrate.py` reproduces the leave-one-game-out evaluation and saves the final
model, fitted to all three open games, in `possession/learned_weights.json`. Each fold fits
scaling and weights on the other two games. The learned decoder grid uses those same two
training games and ranks settings by average spellF1, with macroF1 as the tiebreaker.
The grid crosses team switch costs of 7, 18 and 35 with D entry and exit cost pairs of
(3, 2.5) and (9, 8), and H/A and D minimum-duration pairs of (15, 10), (30, 20)
and (45, 30) frames. All sample evaluations use an empty Smart Tagging list.

The hand settings were fixed before this comparison. Their original calibration used Game 3,
so the hand score for Game 3 is an in-sample reference. The learned scores for all three games
come from held-out evaluation.

### Leave-one-game-out results

The official scorer measures frame macroF1 across H, A and D and averages spellF1 over IoU
thresholds from 0.3 to 0.7 in steps of 0.1. Learned fixed uses the calibrated hand decoder settings.
Learned tuned uses the decoder settings selected within each training fold.

| Scored game | Hand spellF1 | Hand macroF1 | Learned fixed spellF1 | Learned fixed macroF1 | Learned tuned spellF1 | Learned tuned macroF1 |
|---|---:|---:|---:|---:|---:|---:|
| Sample Game 1 | 0.5928 | 0.8542 | 0.5484 | 0.8471 | 0.6468 | 0.8623 |
| Sample Game 2 | 0.6109 | 0.8756 | 0.5597 | 0.8924 | 0.6597 | 0.9048 |
| Sample Game 3 | 0.5876 | 0.8944 | 0.5511 | 0.9092 | 0.6283 | 0.9217 |
| Mean | 0.5971 | 0.8747 | 0.5531 | 0.8829 | 0.6450 | 0.8963 |

We submit `EMISSIONS = "learned"`. With the tuned decoder, learned emissions scored 0.6450 mean
spellF1 versus 0.5971 for hand emissions and improved spellF1 on all three games. For the final
model, we ranked decoder settings by their mean training scores across the folds. The selected
settings use a team switch cost of 18, D entry and exit costs of 9 and 8, and minimum durations
of 45 frames for H and A and 30 frames for D. Smart Tagging scores are added at inference.

## 8. Reproduction

```bash
pip install -r requirements.txt
python run.py --team diables          # data in ./data or MTAH_DATA_DIR
```

Output `submission/diables.csv`, deterministic. Tests: `python -m tests.test_synthetic`.

## References

- Link, D. and Hoernig, M. (2017). Individual ball possession in soccer. PLOS ONE 12(7).
- Spearman, W. (2018). Beyond Expected Goals. MIT Sloan Sports Analytics Conference.
- Fernandez, J. and Bornn, L. (2018). Wide Open Spaces: a statistical technique for measuring
  space creation in professional soccer. MIT Sloan Sports Analytics Conference.
- Vidal-Codina, F., Evans, N., El Fakir, B. and Billingham, J. (2022). Automatic event detection
  in football using tracking data. Sports Engineering 25.
- Yu, S.-Z. (2010). Hidden semi-Markov models. Artificial Intelligence 174(2).
- Farha, Y. A. and Gall, J. (2019). MS-TCN: Multi-stage temporal convolutional network for action
  segmentation. CVPR.

## Why hand emissions by default

The learned model wins on the open sample games, but its weights push hard towards D whenever
the ball is not tracked (all the missing-value indicators point the same way). In the open
samples a missing ball mostly means a stoppage. In the challenge match the ball is missing on
41% of graded frames, mostly because of occlusions during live play, which is exactly the mistake
the official baseline makes. That is a change of data distribution we cannot measure without
labels on the challenge match, which we are not allowed to use. So the submission uses the hand
emissions, where a missing ball adds almost nothing, and the learned model stays available with
`EMISSIONS = "learned"` in `possession/config.py`.
