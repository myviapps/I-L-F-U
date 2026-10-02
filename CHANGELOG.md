# Changelog

All notable changes are listed here. Format based on [Keep a Changelog](https://keepachangelog.com), versioning follows [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- First-run setup screen (agreement, save folder, language and model, model download with progress) and `ilfu setup`.
- Live captions while recording, pause and resume, recording history (search, rename, delete, play, export, re-transcribe), regional language choice.
- New interface: a local web app shown in its own Edge or Chrome window, replacing the first tkinter window. Light and dark themes.
- Project foundation: license, contribution and governance docs, CI on Windows, macOS and Linux.
- Audio capture interface, disk recorder and a Windows (WASAPI) backend.
- Hardware detection with model tiers, transcript export (txt, Markdown, SRT), faster-whisper transcriber.
- Evaluation harness: WER, benchmark manifests and back-to-back report comparison.
- First desktop window with consent reminder, record, transcribe and save (since replaced by the web interface).
- Windows installer script, uninstall script, install guide.
- CLI commands: `devices`, `record`, `tier`, `transcribe`, `eval`, `compare`.
