# I-L-F-U: open-source call transcriber

A free, open-source transcriber for online video calls. It runs on your own machine, with no accounts, no API keys and no bot joining your meeting.

> **Status: Phase 0 (foundation).** Nothing is installable yet. See [docs/ROADMAP.md](docs/ROADMAP.md) for what is planned and what is done.

## Goals

- **Local by default:** audio is captured and transcribed on your device. Nothing leaves it unless you turn that on.
- **Works on Windows, macOS and Linux**, plus a Chrome extension for web calls and a CLI.
- **Never disturbs the live call:** passive capture, low priority, capped CPU and memory.
- **High, measured accuracy:** every change is compared back to back with the previous version on a public benchmark.
- **Easy setup:** one installer, a short first-run wizard, no config files.
- **Open everything:** code, fine-tuned models, training recipes and evaluation results.

## Building blocks (open models)

Speech-to-text with Whisper via faster-whisper or whisper.cpp, speaker labels with an open diarization model, and optional summaries with a small local LLM. Licenses for every model are tracked in [docs/MODEL_LICENSES.md](docs/MODEL_LICENSES.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `app/` | Desktop app and Chrome extension (planned) |
| `capture/` | Per-OS audio capture (planned) |
| `engine/` | Transcription pipeline (Python package `ilfu`) |
| `training/` | Fine-tuning recipes and dataset manifests (planned) |
| `eval/` | Benchmarks and WER/DER scripts (planned) |
| `docs/` | Roadmap, privacy and consent, sponsorship, model licenses |

## Recording and consent

You are responsible for telling people they are being recorded and for following the law where you and they live. Read [docs/PRIVACY_AND_CONSENT.md](docs/PRIVACY_AND_CONSENT.md).

## Contributing and funding

- Contribute: [CONTRIBUTING.md](CONTRIBUTING.md) (DCO sign-off, no CLA).
- Support maintenance and training compute: [docs/SPONSORS.md](docs/SPONSORS.md). The app is and stays free.

## License

Code is under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). You can use, study, modify and share it freely; if you distribute a modified version, or run one as a network service, you must offer your source under the same license. Models and datasets have their own licenses, listed in [docs/MODEL_LICENSES.md](docs/MODEL_LICENSES.md).
