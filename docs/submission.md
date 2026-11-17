# Submission checklist

Team Fireware (Roger, Jordi, Carles, Laia). More Than a Hack 2027, Phase 1. Deadline: November 17, 2026.

One Google Form per team (link sent by email to registered participants). The last response
before the deadline is the one scored, and it can be edited.

## What goes in the form

| Field | What we send | Status |
|---|---|---|
| Team name | `Fireware`, exactly as in every member's registration | to fill in |
| Team members names | Roger, Jordi, Carles i Laia | to fill in |
| Possession file (.csv) | `entregar/Fireware.csv`, a copy of `submission/diables.csv` (local only) | ready, validated |
| Public code repository URL | https://github.com/diablesdigualada-gestio/Bar-aHackaton | public |
| Short technical document | `entregar/Fireware.pdf`, made from `docs/diables.md` | ready |

A Google account is needed to upload the files.

## Checks done on the file we upload

- `python <official-repo>/evaluation/validate_submission.py submission/diables.csv` gives `OK`:
  header `frame,label`, 199319 rows, frames 0 to 199318 in order, labels from H A D X.
- Deterministic: two runs of `python run.py --team diables` give byte-identical files.
- Upload the exact file that was validated, not an older copy.

## Checks done on the repository

- No match data: `data/`, `.cache/`, `submission/`, `outputs/`, `web/public/match.json` and every
  video file are gitignored.
- Dependencies pinned: `requirements.txt` (numpy 2.2.5, Python 3.13 used for the submission),
  `requirements-viz.txt` for the optional video tool, `web/package-lock.json` for the viewer.
- Reproduction in the README: data in `data/` (or `MTAH_DATA_DIR`), then
  `pip install -r requirements.txt` and `python run.py --team diables`.
- Tests: `python -m tests.test_synthetic` passes on a synthetic match, no real data needed.

## Technical document coverage

`docs/diables.md` covers what SUBMISSION.md asks for:

| Required section | Where |
|---|---|
| The approach and why | sections 1 to 3 |
| Assets used and dropped | section 5 |
| Training data: source, who labelled it, how much | section 6, calibration and learned emissions |
| Possession rules implemented | section 4 |
| Limitations | section 7, and the robust model results |
| Reproduction | section 8 |

## Rules we follow

- Labels come from the algorithm only. No hand labels on the challenge match, no private ground
  truth. The public 5-minute window is only used to check that the pipeline runs.
- Training and calibration data come from other matches only (Metrica open samples).
- The submission uses the hand emissions. The robust learned model was tested and rejected by a
  rule fixed in advance (it loses with simulated ball dropouts); see `docs/diables.md`.

## Viewer in production

Checked with the real match file on a production build (`npm run build`,
`node .output/server/index.mjs`): page loads, timeline, pitch and possession table render,
playback runs, no console errors, and the match file is served compressed.

## Still to do by the team

1. Fill in and send the form with the four fields above.
2. Watch at least one overlay clip (`python tools/visualize.py clip --start 11185 --seconds 60`)
   as a last sanity check against the video.
