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

Three states, H, A, D. Each state is expanded into a left-to-right chain of substates (30 frames
for H and A, 20 for D), the classical explicit-duration HMM construction. A state must walk
its chain before a transition, giving minimum durations of 1.2 s for possession and 0.8 s for
stoppages. Switching between teams costs 7 units of log-score. Entering D costs 3
and leaving D costs 2.5. Viterbi finds the best segmentation in one pass.

Emissions: H gets +control, A gets -control, D gets the dead-ball score. During an occlusion
everything is close to zero and the decoder simply stays in the current state.

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

We calibrated six parameter groups against frame labels derived from the public Metrica Sports
Sample Game 3 events. The pipeline still uses fixed rules and a fixed decoder. Other parameter
values come from the literature or football heuristics and are documented in
`possession/config.py`. The calibration used only the open sample match.

## 7. Limitations

- The grid search used one optical-tracking match with event-derived labels. The reported
  scores measure fit to that match. Generalisation to other matches and video tracking
  remains unmeasured.
- The event file can leave restart gaps or place changes of control late. The label rules hold
  D until a recognised restart and retain the current team between control events.
- Tracking slots are tracklets, not people, so we cannot use per-player history (for instance,
  who touched the ball last before an occlusion beyond the current state).
- The Smart Tagging time of the restart is approximated by the centre of the tagged interval.
- Long ball occlusions during live play keep the previous possession; if the ball changed hands
  inside the occlusion the change is detected late.

## Calibration

`python tools/calibrate.py` scores 96 settings on all 143,761 frames of Metrica Sports
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
