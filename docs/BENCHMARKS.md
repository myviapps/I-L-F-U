# Benchmarks

Measured on GitHub's free Linux runners (2 CPU cores), CI run 36961087768, stock faster-whisper models, no tuning. The test audio is a fixed set of Google FLEURS clips (CC BY 4.0): 25 English, 25 Hindi and 25 Telugu. The clip list and checksums are in `benchmark/frozen-clips.json`. Re-run with `ilfu benchmark --model base` (needs the `asr` extra and a network connection for the first download).

Word error rate (WER) is the share of words that are wrong. Lower is better; above 100% means the output has more mistakes than the reference has words.

| Model | English | Hindi | Telugu | Speed (work per second of audio) | Peak memory |
| --- | --- | --- | --- | --- | --- |
| base, 75 clips, 2 cores | 8.8% | 106.4% | 134.3% | 0.29 | 516 MB |
| base, first 8 clips per language, 1 core | 12.3% | 112.5% | 130.2% | 0.35 | 498 MB |
| small, first 8 clips per language, 1 core | 6.5% | 57.5% | 100.6% | 1.83 | 1149 MB |
| large-v3-turbo (Best), first 10 clips per language, 2 cores | 6.0% | 35.2% | 81.4% | 2.11 | 2138 MB |

The small model's full 75-clip run finished, but only its 1-core result could be read back from the logs; the full-set small row is still to be recorded.

## What this tells us

- **English is fine** with both models.
- **Base cannot do Hindi or Telugu.** It writes Hindi in Urdu or Roman letters and produces nonsense for Telugu. This is the model, not the scoring: the sample lines are printed in the CI log.
- **Small is much better for Hindi (57.5%) but still poor**, and Telugu is not usable (100.6%).
- **Speed matters.** Small ran at 1.83 seconds of work per second of audio on one core, so it cannot keep up with live captions on a weak computer; base can (0.35). Live captions on a weak machine should use base for English or fall back to transcribing after the call.
- **large-v3-turbo (Best) is the best of the models tried:** Hindi 35% is readable as a draft, Telugu 81% still has most words wrong. It ran at 2.11 seconds of work per second of audio on 2 cores, so it cannot keep up live on a weak computer; use it with Re-transcribe after the call. It needs about 2.1 GB of memory.
- The medium model (Accurate) is being measured; its row will be added here.

## Limits of these numbers

- 25 clips per language is a small sample; differences of a few points are noise (two identical base runs gave Hindi 107.4% and 106.4%).
- FLEURS is read speech in a quiet room, not a noisy call.
- One CPU core on a shared runner stands in for a weak computer; it is not a real low-end laptop.
