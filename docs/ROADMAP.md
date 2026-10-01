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

- [ ] Capture on one OS, mic and system audio as separate channels, written to disk continuously
- [ ] Engine: voice detection, faster-whisper, text and Markdown export
- [ ] CLI for files and live devices
- [ ] Evaluation harness, frozen test set, baseline WER for stock Whisper
- [ ] Hardware check, automatic model tier, first-run wizard, one installer
- [ ] Passive-capture check during a live call

**Gate:** a real call transcribed fully offline by someone who did not build it.

## Later phases

2 Meeting features, 3 Better models, 4 Community. Details are kept in the project plan and will be copied here as each phase starts.
