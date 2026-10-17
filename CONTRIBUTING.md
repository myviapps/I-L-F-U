# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Ground rules

- **Sign off every commit** with `git commit -s` (Developer Certificate of Origin, https://developercertificate.org). There is no CLA.
- **Do not add code, models or data you cannot license** under terms compatible with AGPL-3.0 (permissive licenses such as MIT, BSD and Apache-2.0 are fine; GPL-2.0-only and non-commercial or proprietary terms are not). Record any model or dataset in `docs/MODEL_LICENSES.md`.
- **Never commit real call recordings or personal data.** Test audio must be synthetic or recorded with written consent from everyone in it.
- **Local by default:** no feature may require an account or an API key. Optional cloud features must be off by default.
- **Never disturb the live call:** capture must stay passive, and heavy work must run at low priority.
- **Accuracy changes need evidence:** include WER/DER results from `eval/` against the previous version.

## Development

```
cd engine
python -m pip install -e ".[dev]"
ruff check .
pytest
```

CI runs the same checks on Linux for pull requests, and on Windows, macOS and Linux for pushes to main, the weekly run and runs started by hand.

## Testing without GitHub Actions

When the Actions minutes run out, CI fails in seconds without running anything. Run the same jobs on your machine instead:

```
scripts/check.sh                                         # Linux, macOS
powershell -ExecutionPolicy Bypass -File scripts\check.ps1   # Windows
```

By default this runs the offline jobs: engine lint and tests, and the web interface tests in a real Chromium. It creates `.venv` at the repository root (use `--no-venv` / `-NoVenv` to skip that) and ends with a PASS/FAIL line per job.

- `--full` (`-Full`) also runs the speech model smoke test and the benchmarks. These download Whisper models and FLEURS clips from Hugging Face, so they need network access and a few GB of disk. Reports go to `.ci-local/`.
- `--indic` also runs the IndicConformer benchmark (installs torch). It needs `HF_TOKEN` set to a Hugging Face token with access to the gated `ai4bharat/indic-conformer-600m-multilingual` model (accept its terms first); without it the job shows SKIP.
- On Windows, `-Installer` and `-SetupExe` run the install script and installer tests. They install into `%LOCALAPPDATA%\ILFU` and uninstall again, so they refuse to run if the app is already installed. `-SetupExe` needs Inno Setup 6.

When CI could not run, paste the summary of a green local run (or link to it) in the pull request, and say which jobs you ran.

Claude Code cloud sessions install the engine automatically through `.claude/hooks/session-start.sh`. The cloud image has another `pytest` on PATH that cannot import `ilfu`; the hook puts the right one first, but if bare `pytest` fails with "No module named ilfu", use `python3 -m pytest` and `python3 -m ruff check .`.

## Reporting problems

Use the issue templates. Report security problems privately, see [SECURITY.md](SECURITY.md).
