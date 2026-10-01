# Architecture

Pipeline, all local by default:

capture (mic + system audio, separate channels) -> voice detection -> speech-to-text -> speaker labels -> transcript -> optional summary -> library and export.

Rules the design must keep:

- **Capture is passive:** it copies audio and never changes playback or microphone routing.
- **Capture is isolated:** it writes audio to disk on its own thread and never blocks on the engine. If the engine crashes, recording continues.
- **Every stage sits behind an interface** so models and platforms can be swapped.

Current code: `engine/src/ilfu/capture/` (interfaces, recorder, Windows backend).
