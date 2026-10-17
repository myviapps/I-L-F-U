# Roadmap

Week counts are rough estimates. The gate is the real milestone. Tick a box only when its proof (merged PR, CI run, published file, test result) is linked beside it.

## Phase 0: Foundation (weeks 0 to 2)

- [x] License: AGPL-3.0 (`LICENSE`), chosen by the maintainer
- [x] README, CONTRIBUTING (DCO), CODE_OF_CONDUCT, SECURITY, GOVERNANCE, issue and PR templates
- [x] CI on Windows, macOS and Linux (lint and tests)
- [x] Funding file template and `docs/SPONSORS.md`
- [x] Privacy and consent page, model license manifest
- [ ] Branch protection on the main branch
- [ ] Enable the donation accounts and uncomment `.github/FUNDING.yml`
- [ ] CI seen green on all three OS

**Gate:** public repo with license, three-OS CI green, donation links live.

## Phase 1: MVP (weeks 2 to 8)

- [ ] Capture on Windows first, mic and system audio as separate channels, written to disk continuously
    - [x] Interfaces, disk recorder and tests with a fake source
    - [ ] Windows WASAPI backend run on a real Windows machine during a real call (code written, not yet run)
- [ ] Engine: voice detection, faster-whisper, text and Markdown export
    - [x] Export to txt, Markdown and SRT, with tests
    - [x] faster-whisper run end to end on real speech (FLEURS clips, in CI)
- [ ] CLI for files and live devices
    - [x] `ilfu devices`, `record`, `tier`, `transcribe`, `eval`, `compare` (record and transcribe not yet run on real audio)
- [ ] Evaluation harness, frozen test set, baseline WER for stock Whisper
    - [x] WER, manifest runner and back-to-back `compare` with tests
    - [x] Frozen test set: FLEURS en/hi/te, 25 clips each, CC BY 4.0, checksums in `benchmark/frozen-clips.json`
    - [x] Baseline WER for stock Whisper base, small, medium and large-v3-turbo (`docs/BENCHMARKS.md`)
    - [x] Commit machine-readable baselines so CI can fail on a regression (`benchmark/baseline-base.json`, `benchmark/baseline-small.json`; tests in `engine/tests/test_compare.py`)
- [ ] Hardware check, automatic model tier, first-run wizard, one installer
    - [x] App interface (local web app in its own Edge/Chrome window): record, pause, live captions, history with search, rename, delete, audio player, export, re-transcribe; tested in a real browser and, with the real model and a fake audio source, on Windows in CI
    - [x] Speed and memory measured on 1 CPU core in CI (base keeps up, small does not); a real low-end PC is still to be tested
    - [x] Windows install script and uninstall (Settings > Apps, Help > Uninstall, script), install and uninstall tested in CI
    - [x] Hardware detection and tier choice (thresholds are guesses, to be measured)
    - [x] First-run setup screen: agreement, save folder, language and model, model download with progress (tested in a real browser in CI)
    - [x] One-file installer built, silently installed and uninstalled in CI (unsigned)
    - [ ] Code-signing certificate, so Windows SmartScreen stops warning
    - [x] Choose microphone and call-sound devices (external headsets), silence-safe capture, low-voice boost, low-priority transcription (tested with fake devices)
    - [ ] Tested with real external devices on a real PC
- [ ] Passive-capture check during a live call

**Gate:** a real call transcribed fully offline by someone who did not build it.

## Later phases

2 Meeting features, 3 Better models, 4 Community. Details are kept in the project plan and will be copied here as each phase starts.
