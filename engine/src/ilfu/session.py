"""Turn a recorded session folder (mic.wav, system.wav) into one labelled transcript."""

from __future__ import annotations

import wave
from pathlib import Path

from .transcribe import Transcriber
from .transcript import Segment

# The microphone is the user; the system audio is everyone else on the call.
LABELS = {"mic": "You", "system": "Them"}


def _has_audio(path: Path) -> bool:
    if not path.exists():
        return False
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() > 0


def transcribe_session(session_dir: Path, transcriber: Transcriber) -> list[Segment]:
    segments: list[Segment] = []
    for name, label in LABELS.items():
        wav_path = session_dir / f"{name}.wav"
        if not _has_audio(wav_path):
            continue
        for seg in transcriber.transcribe(wav_path):
            if seg.text.strip():
                segments.append(Segment(seg.start, seg.end, seg.text, speaker=label))
    return sorted(segments, key=lambda s: (s.start, s.end))
