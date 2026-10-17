# eval

The evaluation code lives in the engine (`engine/src/ilfu/benchmark.py`, `evaluation.py`, `wer.py`); this folder has no scripts of its own yet.

- `ilfu benchmark --model base` measures word error rate and speed on the frozen FLEURS clips (25 English, 25 Hindi, 25 Telugu, CC BY 4.0). The clip list and checksums are in `benchmark/frozen-clips.json`.
- `ilfu eval manifest.jsonl` does the same for your own clips listed in a JSON-lines manifest.
- `ilfu compare baseline.json report.json` exits 1 if WER got worse than the baseline by more than the tolerance. The committed baselines are in `benchmark/`.

Results and how the regression gate works: `docs/BENCHMARKS.md`. The frozen test set is never used for training or tuning. Speaker (DER, cpWER) scores are not written yet.
