"""Speech-to-text. The engine depends on the small `Transcriber` interface, not on one library."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .hardware import Tier
from .paths import model_dir
from .transcript import Segment


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[Segment]: ...


class FasterWhisperTranscriber:
    """Runs Whisper locally through faster-whisper (`pip install 'ilfu[asr]'`).

    The model is downloaded on first use. Not yet run end to end in CI because it needs a
    model download; see docs/ROADMAP.md.
    """

    def __init__(self, tier: Tier, language: str | None = None) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install speech support: pip install 'ilfu[asr]'") from exc
        cache = model_dir()
        self._model = WhisperModel(
            tier.model,
            device=tier.device,
            compute_type=tier.compute_type,
            download_root=str(cache) if cache else None,
        )
        self._language = language

    def transcribe(self, audio_path: Path) -> list[Segment]:
        segments, _info = self._model.transcribe(
            str(audio_path), language=self._language, vad_filter=True
        )
        return [Segment(s.start, s.end, s.text.strip()) for s in segments]
