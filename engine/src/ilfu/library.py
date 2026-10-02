"""The list of past recordings: read, rename and delete. Each recording is one folder."""

from __future__ import annotations

import json
import shutil
import time
import wave
from dataclasses import dataclass
from pathlib import Path

TRACKS = ("mic", "system")


@dataclass(frozen=True)
class SessionInfo:
    path: Path
    title: str
    created: str
    duration: float
    has_transcript: bool


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (OSError, EOFError, wave.Error):
        return 0.0


def audio_seconds(folder: Path) -> float:
    return max((_wav_seconds(folder / f"{t}.wav") for t in TRACKS), default=0.0)


def read_meta(folder: Path) -> dict:
    try:
        return json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_meta(folder: Path, **changes: object) -> None:
    meta = read_meta(folder)
    meta.update(changes)
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _created_from_name(name: str) -> str:
    try:
        return time.strftime("%d %b %Y, %H:%M", time.strptime(name, "%Y%m%d-%H%M%S"))
    except ValueError:
        return name


def describe(folder: Path) -> SessionInfo:
    meta = read_meta(folder)
    created = _created_from_name(folder.name)
    return SessionInfo(
        path=folder,
        title=meta.get("title") or f"Call on {created}",
        created=created,
        duration=float(meta.get("duration") or audio_seconds(folder)),
        has_transcript=(folder / "transcript.md").exists(),
    )


def list_sessions(base: Path) -> list[SessionInfo]:
    """Newest first. Folders without audio or a transcript are ignored."""
    if not base.exists():
        return []
    found = [
        describe(d)
        for d in base.iterdir()
        if d.is_dir() and any((d / f"{t}.wav").exists() for t in TRACKS)
    ]
    return sorted(found, key=lambda s: s.path.name, reverse=True)


def read_transcript(folder: Path) -> str:
    try:
        return (folder / "transcript.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def rename(folder: Path, title: str) -> None:
    write_meta(folder, title=title.strip())


def delete(folder: Path) -> None:
    """Remove the whole recording folder. Only call this after the user confirmed."""
    shutil.rmtree(folder)


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
