# Architecture

Pipeline, all local by default:

capture (mic + system audio, separate channels) -> voice detection -> speech-to-text -> speaker labels -> transcript -> optional summary -> library and export.

Rules the design must keep:

- **Capture is passive:** it copies audio and never changes playback or microphone routing.
- **Capture is isolated:** it writes audio to disk on its own thread and never blocks on the engine. If the engine crashes, recording continues.
- **Every stage sits behind an interface** so models and platforms can be swapped.

Current code: `engine/src/ilfu/capture/` (interfaces, recorder, Windows backend).

## App interface

The interface is a small web page (`engine/src/ilfu/web/index.html`) served by a local-only HTTP server (`server.py`, bound to 127.0.0.1, random token cookie, Host-header check). `ilfu gui` starts the server and opens the page in the Edge or Chrome already on the computer using `--app`, so it looks like a normal desktop window. No extra dependencies and no internet are needed. All behaviour (recording, live captions, history, settings, model download) lives in `core.py`; the server and page are thin layers over it. The server exits when the window closes, unless a recording or download is still running.
