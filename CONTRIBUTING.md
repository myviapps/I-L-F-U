# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Ground rules

- **Sign off every commit** with `git commit -s` (Developer Certificate of Origin, https://developercertificate.org). There is no CLA.
- **Do not add code, models or data you cannot license** under terms compatible with Apache-2.0. Record any model or dataset in `docs/MODEL_LICENSES.md`.
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

CI runs the same checks on Windows, macOS and Linux.

## Reporting problems

Use the issue templates. Report security problems privately, see [SECURITY.md](SECURITY.md).
