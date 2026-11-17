# Entregar: what goes into the form

Everything the team uploads, in one folder. One Google Form per team (link sent by email to
registered participants). The last response before the deadline counts.

| Form field | What to put | File in this folder |
|---|---|---|
| Team Name | `Diables`, exactly as in every member's registration | |
| Possession file | the submission CSV | `diables.csv` (local only, see below) |
| Public code repository URL | https://github.com/diablesdigualada-gestio/Bar-aHackaton | `repository_url.txt` |
| Short technical document | the technical document, named after the team | `diables.md` |

## The CSV is not on GitHub on purpose

`diables.csv` is gitignored: `submission/` stays out of the repository by team rule and the
repository is public. It is copied here on the machine that ran the pipeline. To recreate it:

```bash
python run.py --team diables
python <official-repo>/evaluation/validate_submission.py submission/diables.csv   # must say OK
cp submission/diables.csv entregar/diables.csv
```

Upload the exact file that was validated. The run is deterministic, so any machine with the data
bundle gets a byte-identical file.

## Last checks before sending

1. `diables.csv` validated with the official validator: OK.
2. Repository public and without match data.
3. `diables.md` is the same as `docs/diables.md`.
4. Team name identical to the registration form.

Full checklist: [../docs/submission.md](../docs/submission.md).
