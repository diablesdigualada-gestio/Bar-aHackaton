# Diables: who has the ball?

Team Diables entry for **More Than a Hack 2027, Phase 1: Ball Possession** (Metrica Sports,
Barca Innovation Hub, Mobile World Capital Barcelona).

For every frame of FC Barcelona vs Athletic Club we answer H (home in possession), A (away in
possession) or D (dead ball), using only the provided tracking (ATD) and Smart Tagging.

Method in one paragraph: per frame, a physics model estimates how strongly each team controls the
ball (proximity, ball speed and the gap between teams; a time to reach the ball model from the
pitch control literature is also implemented), and four independent signals score how likely the
ball is dead. A **three-state explicit-duration HMM** decodes the whole match at once with Viterbi,
so short flickers never become possessions. Parameters are **calibrated on Metrica's open sample
game 3**, never on the challenge match. Full explanation in [docs/diables.md](docs/diables.md).

## Reproduce the submission

Python 3.9+ and numpy. Nothing else is needed for the submission file.

```bash
pip install -r requirements.txt
```

Unpack the data bundle so that `data/tactical/BAR-ATH_tactical_atd.txt` exists, or point
`MTAH_DATA_DIR` at it, then:

```bash
python run.py --team diables
```

That writes `submission/diables.csv` (199319 rows, `frame,label`). The run is deterministic: same
data in, same file out. First run takes a couple of minutes to read the raw tracking, later runs
use the cache in `.cache/`.

Check the format with the official validator:

```bash
python <official-repo>/evaluation/validate_submission.py submission/diables.csv
```

## Tests

```bash
python -m tests.test_synthetic
```

Synthetic match, no real data: checks the raw reader, the minimum duration rule and a full
H, A, D, H scenario.

## Viewer

Nuxt 4 + Nuxt UI app to inspect the result: possession share, ball in play, possession strips
per half and the list of spells.

```bash
python run.py --team diables --viewer     # writes web/public/match.json (gitignored)
cd web
npm install
npm run dev
```

## Layout

| Path | What | Owner |
|---|---|---|
| `possession/loading.py` | raw ATD reader, metadata, Smart Tagging | Roger |
| `possession/ball.py` | ball gaps, ball speed, out of pitch | Roger |
| `possession/features.py` | distance and time to ball, control evidence | Jordi |
| `possession/viterbi.py` | explicit-duration HMM decoder | Jordi |
| `possession/config.py` | every parameter, with its source | Jordi |
| `possession/deadball.py` | dead-ball evidence, tagging priors | Carles |
| `possession/output.py` | submission writer, spells, viewer export | Carles |
| `run.py` | end-to-end command | all |
| `web/` | viewer | Carles |

## Data

The match data is not in this repository and must not be: it is gated by the organisers.
`.gitignore` excludes `data/`, the cache, the submission and the viewer JSON.

## Team

Jordi Balsells, Roger, Carles. Diables d'Igualada.
