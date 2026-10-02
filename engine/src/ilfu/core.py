"""The app's brain, with no screen code: recording, live captions, history and settings.

The web interface (`server.py`) is a thin layer over this class.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import threading
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__, library, models, playback
from .capture import Recorder, get_backend
from .config import (
    LANGUAGES,
    TERMS_VERSION,
    Config,
    default_save_dir,
    load,
    needs_setup,
    save,
)
from .hardware import choose_tier, detect_hardware
from .live import LiveTranscriber
from .paths import new_session_dir
from .session import transcribe_session
from .terms import TERMS
from .transcript import FORMATS, Segment, to_markdown

log = logging.getLogger("ilfu")


class ApiError(Exception):
    """A problem the user should be told about, in plain words."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _seg_dict(seg: Segment) -> dict:
    return {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text,
            "speaker": seg.speaker}


def _writable(folder: Path) -> str | None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".ilfu-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return f"Cannot write to that folder: {exc}"
    return None


class Controller:
    def __init__(
        self, backend: str = "auto", cfg: Config | None = None, preload: bool = True
    ) -> None:
        self.backend_name = backend
        self.cfg = cfg or load()
        self.lock = threading.RLock()
        self.recorder: Recorder | None = None
        self.live: LiveTranscriber | None = None
        self.session_dir: Path | None = None
        self.transcriber = None
        self.model_state = "none"  # none | loading | ready | error
        self.model_error = ""
        self.busy = ""  # "" | finishing | retranscribing
        self.busy_id = ""
        self.segments: list[dict] = []
        self.live_error = ""
        self.record_seconds = 0.0
        self.resumed_at = 0.0
        self.paused = False
        self.last_finished = ""
        self.error = ""
        self.download: dict = {"state": "idle", "model": "", "progress": 0.0, "error": ""}
        self._pending: dict = {}
        hw = detect_hardware()
        self.hardware = {"cores": hw.cpu_cores, "ram_gb": hw.ram_gb, "cuda": hw.has_cuda}
        self.recommended = models.recommended(hw.cpu_cores, hw.ram_gb, hw.has_cuda)
        if preload:
            self.load_model()

    # ---- model ----
    def load_model(self) -> None:
        if not self.cfg.model or not models.is_downloaded(self.cfg.model):
            self.model_state = "none"
            return
        self.model_state = "loading"
        self.transcriber = None
        name = self.cfg.model

        def work() -> None:
            try:
                from .transcribe import FasterWhisperTranscriber

                tier = choose_tier(detect_hardware())
                loaded = FasterWhisperTranscriber(
                    tier, self.cfg.language_code(), model=name, beam_size=1
                )
                with self.lock:
                    if self.cfg.model == name:
                        self.transcriber = loaded
                        self.model_state = "ready"
            except Exception as exc:
                log.exception("model load failed")
                self.model_state = "error"
                self.model_error = str(exc)

        threading.Thread(target=work, daemon=True, name="ilfu-model").start()

    # ---- state for the interface ----
    def elapsed(self) -> float:
        if self.recorder is None:
            return 0.0
        return self.record_seconds + (0 if self.paused else time.time() - self.resumed_at)

    def state(self, since: int = 0) -> dict:
        with self.lock:
            live = self.live
            return {
                "version": __version__,
                "setup_needed": needs_setup(self.cfg) or not models.is_downloaded(self.cfg.model),
                "recording": self.recorder is not None,
                "paused": self.paused,
                "elapsed": round(self.elapsed(), 1),
                "busy": self.busy,
                "busy_id": self.busy_id,
                "session_id": self.session_dir.name if self.recorder and self.session_dir else "",
                "last_finished": self.last_finished,
                "model_state": self.model_state,
                "model_error": self.model_error,
                "lag": round(live.lag_seconds(), 1) if live and not self.paused else 0,
                "live_error": self.live_error,
                "segments": self.segments[since:],
                "segment_total": len(self.segments),
                "download": dict(self.download),
                "config": {
                    "language": self.cfg.language,
                    "model": self.cfg.model,
                    "save_dir": str(self.cfg.save_dir or default_save_dir()),
                },
                "error": self.error,
            }

    def catalog(self) -> dict:
        return {
            "languages": [{"code": c, "name": n} for c, n in LANGUAGES.items()],
            "models": [
                {**asdict(m), "downloaded": models.is_downloaded(m.name),
                 "recommended": m.name == self.recommended}
                for m in models.MODELS
            ],
            "terms": TERMS,
            "terms_version": TERMS_VERSION,
            "hardware": self.hardware,
            "default_save_dir": str(default_save_dir()),
            "playback_in_browser": True,
        }

    # ---- setup and settings ----
    def setup(self, accept_terms: bool, save_dir: str, language: str, model: str) -> None:
        if not accept_terms:
            raise ApiError("Please accept the agreement to continue.")
        if language not in LANGUAGES:
            raise ApiError("Unknown language.")
        info = next((m for m in models.MODELS if m.name == model), None)
        if info is None:
            raise ApiError("Unknown model.")
        folder = Path(save_dir.strip() or str(default_save_dir()))
        problem = _writable(folder)
        if problem:
            raise ApiError(problem)
        if self.recorder is not None or self.busy:
            raise ApiError("Finish the current recording first.")
        if self.download["state"] == "running":
            raise ApiError("A download is already running.")
        self.cfg.terms_version = TERMS_VERSION
        self.cfg.save_dir = str(folder)
        self.cfg.language = language
        if self.transcriber is not None:
            self.transcriber.language = self.cfg.language_code()
        save(self.cfg)
        if models.is_downloaded(model):
            self._apply_model(model)
            return
        self._pending = {"model": model}
        self.download = {"state": "running", "model": model, "progress": 0.0, "error": ""}

        def work() -> None:
            try:
                models.download(model, self._download_progress)
                self.download = {"state": "done", "model": model, "progress": 1.0, "error": ""}
                self._apply_model(model)
            except Exception as exc:
                log.exception("model download failed")
                self.download = {"state": "error", "model": model, "progress": 0.0,
                                 "error": str(exc)}

        threading.Thread(target=work, daemon=True, name="ilfu-download").start()

    def _download_progress(self, fraction: float) -> None:
        self.download["progress"] = round(fraction, 3)

    def _apply_model(self, model: str) -> None:
        with self.lock:
            changed = model != self.cfg.model or self.model_state in ("none", "error")
            self.cfg.model = model
            self.cfg.setup_done = True
            self.cfg.terms_version = TERMS_VERSION
            save(self.cfg)
        if changed:
            self.load_model()

    # ---- recording ----
    def start_recording(self) -> None:
        with self.lock:
            if self.recorder is not None:
                raise ApiError("Already recording.")
            if self.busy:
                raise ApiError("Please wait until the current recording is finished.")
            if needs_setup(self.cfg):
                raise ApiError("Finish the setup first.")
            try:
                backend = get_backend(self.backend_name)
                session = new_session_dir(self.cfg.sessions_dir())
                recorder = Recorder(
                    {"system": backend.open_system_audio(), "mic": backend.open_microphone()},
                    session,
                )
                self.segments = []
                self.live_error = ""
                self.live = LiveTranscriber(
                    recorder,
                    lambda: self.transcriber,
                    self._on_segments,
                    self._on_live_error,
                )
                recorder.start()
                self.live.start()
            except Exception as exc:
                log.exception("could not start recording")
                self.live = None
                raise ApiError(f"Could not start recording: {exc}") from exc
            self.recorder = recorder
            self.session_dir = session
            self.record_seconds = 0.0
            self.resumed_at = time.time()
            self.paused = False
            self.error = ""

    def _on_segments(self, segs: list[Segment]) -> None:
        with self.lock:
            self.segments.extend(_seg_dict(s) for s in segs)

    def _on_live_error(self, message: str) -> None:
        log.error("live captions stopped: %s", message)
        self.live_error = message

    def pause(self) -> None:
        with self.lock:
            if self.recorder is None or self.paused:
                return
            self.recorder.pause()
            self.record_seconds += time.time() - self.resumed_at
            self.paused = True

    def resume(self) -> None:
        with self.lock:
            if self.recorder is None or not self.paused:
                return
            self.recorder.resume()
            self.resumed_at = time.time()
            self.paused = False

    def stop_recording(self) -> None:
        with self.lock:
            recorder, live, session = self.recorder, self.live, self.session_dir
            if recorder is None or live is None or session is None:
                raise ApiError("Not recording.")
            duration = self.elapsed()
            self.recorder = None
            self.live = None
            self.busy = "finishing"
            self.busy_id = session.name

        def work() -> None:
            try:
                recorder.stop()
                segments = live.stop()
                self._save_transcript(session, segments)
                library.write_meta(
                    session, duration=round(duration, 1), language=self.cfg.language,
                    model=self.cfg.model, failed=live.failed,
                )
                self.last_finished = session.name
            except Exception as exc:
                log.exception("finishing the recording failed")
                self.error = f"Problem while saving: {exc}"
            finally:
                self.busy = ""

        threading.Thread(target=work, daemon=True, name="ilfu-finish").start()

    @staticmethod
    def _save_transcript(folder: Path, segments: list[Segment]) -> None:
        if not segments:
            return
        (folder / "transcript.md").write_text(to_markdown(segments), encoding="utf-8")
        (folder / "transcript.json").write_text(
            json.dumps([_seg_dict(s) for s in segments], ensure_ascii=False), encoding="utf-8"
        )

    def shutdown(self) -> None:
        """Keep the audio if the program is closed in the middle of a recording."""
        with self.lock:
            recorder, session = self.recorder, self.session_dir
            duration = self.elapsed()
            self.recorder = None
        if recorder is not None:
            with contextlib.suppress(Exception):
                recorder.stop()
            if session is not None:
                with contextlib.suppress(Exception):
                    library.write_meta(session, duration=round(duration, 1))

    # ---- history ----
    def _folder(self, sid: str) -> Path:
        base = self.cfg.sessions_dir()
        folder = base / sid
        if "/" in sid or "\\" in sid or sid in ("", ".", "..") or not folder.is_dir():
            raise ApiError("Recording not found.", 404)
        return folder

    @staticmethod
    def _info(info: library.SessionInfo) -> dict:
        meta = library.read_meta(info.path)
        return {
            "id": info.path.name, "title": info.title, "created": info.created,
            "duration": round(info.duration, 1), "has_transcript": info.has_transcript,
            "language": meta.get("language", ""), "model": meta.get("model", ""),
        }

    def sessions(self) -> list[dict]:
        return [self._info(s) for s in library.list_sessions(self.cfg.sessions_dir())]

    def session(self, sid: str) -> dict:
        folder = self._folder(sid)
        data = self._info(library.describe(folder))
        segments: list[dict] = []
        raw = folder / "transcript.json"
        if raw.exists():
            with contextlib.suppress(OSError, ValueError):
                segments = json.loads(raw.read_text(encoding="utf-8"))
        if not segments:
            segments = self._segments_from_markdown(library.read_transcript(folder))
        data["segments"] = segments
        data["playable"] = playback.mixed_file(folder) is not None
        return data

    @staticmethod
    def _segments_from_markdown(markdown: str) -> list[dict]:
        found = []
        for line in markdown.splitlines():
            m = re.match(r"\*\*\[(\d+):(\d+):(\d+)\]\*\* (?:(You|Them): )?(.*)", line)
            if m:
                start = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
                found.append({"start": start, "end": start, "text": m[5], "speaker": m[4]})
        return found

    def rename(self, sid: str, title: str) -> None:
        title = title.strip()
        if not title:
            raise ApiError("The name cannot be empty.")
        library.rename(self._folder(sid), title[:120])

    def delete(self, sid: str) -> None:
        folder = self._folder(sid)
        if self.session_dir == folder and (self.recorder is not None or self.busy):
            raise ApiError("This recording is still in progress.")
        library.delete(folder)

    def audio_file(self, sid: str) -> Path:
        path = playback.mixed_file(self._folder(sid))
        if path is None:
            raise ApiError("This recording has no audio.", 404)
        return path

    def export(self, sid: str, fmt: str) -> tuple[str, str]:
        folder = self._folder(sid)
        if fmt not in FORMATS:
            raise ApiError("Unknown format.")
        data = self.session(sid)
        segs = [Segment(s["start"], s["end"], s["text"], s["speaker"]) for s in data["segments"]]
        if not segs:
            raise ApiError("This recording has no transcript yet.")
        return FORMATS[fmt](segs), f"{library.describe(folder).title}.{fmt}"

    def retranscribe(self, sid: str) -> None:
        folder = self._folder(sid)
        with self.lock:
            if self.recorder is not None or self.busy:
                raise ApiError("Please wait until the current work is finished.")
            transcriber = self.transcriber
            if transcriber is None:
                raise ApiError("The speech model is still loading. Try again in a moment.")
            self.busy, self.busy_id = "retranscribing", sid

        def work() -> None:
            try:
                transcriber.beam_size = 5
                segments = transcribe_session(folder, transcriber)
                self._save_transcript(folder, segments)
                if not segments:
                    (folder / "transcript.md").write_text("(No speech found.)\n", encoding="utf-8")
                self.last_finished = sid
            except Exception as exc:
                log.exception("re-transcribe failed")
                self.error = f"Re-transcribing failed: {exc}"
            finally:
                transcriber.beam_size = 1
                self.busy = ""

        threading.Thread(target=work, daemon=True, name="ilfu-retranscribe").start()

    def set_language(self, code: str) -> None:
        if code not in LANGUAGES:
            raise ApiError("Unknown language.")
        self.cfg.language = code
        save(self.cfg)
        if self.transcriber is not None:
            self.transcriber.language = self.cfg.language_code()

    def clear_error(self) -> None:
        self.error = ""
