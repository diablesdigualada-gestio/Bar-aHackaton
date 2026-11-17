# Entregar: what goes into the form

Everything the team uploads, in one folder. One Google Form per team (link sent by email to
registered participants). The last response before the deadline counts.

| Form field | What to put | File in this folder |
|---|---|---|
| Team name | `Fireware`, exactly as in every member's registration | |
| Team members names | Roger, Jordi, Carles i Laia | |
| Possession file (.csv) | the submission CSV, named after the team | `Fireware.csv` (local only, see below) |
| Public code repository URL | https://github.com/diablesdigualada-gestio/Bar-aHackaton | `repository_url.txt` |
| Short technical document | the technical document, named after the team | `Fireware.pdf` (same text as `Fireware.md`) |

## The CSV is not on GitHub on purpose

`Fireware.csv` is gitignored: `submission/` stays out of the repository by team rule and the
repository is public. It is copied here on the machine that ran the pipeline. To recreate it:

```bash
python run.py --team diables
python <official-repo>/evaluation/validate_submission.py submission/diables.csv   # must say OK
cp submission/diables.csv entregar/Fireware.csv
```

Upload the exact file that was validated. The run is deterministic, so any machine with the data
bundle gets a byte-identical file.

## Last checks before sending

1. `Fireware.csv` validated with the official validator: OK.
2. Repository public and without match data.
3. `Fireware.md` is the same as `docs/diables.md`.
4. Team name `Fireware` identical to the registration form. The board names each row after
   the uploaded file, so the files are named `Fireware.csv` and `Fireware.md`.
5. Files are under the form limit of 10 MB each.

Full checklist: [../docs/submission.md](../docs/submission.md).
