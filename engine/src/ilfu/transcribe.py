"""Speech-to-text. The engine depends on the small `Transcriber` interface, not on one library."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .hardware import Tier, default_cpu_threads
from .models import is_downloaded, model_path, models_root
from .transcript import Segment


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[Segment]: ...


class FasterWhisperTranscriber:
    """Runs Whisper locally through faster-whisper (`pip install 'ilfu[asr]'`).

    Uses the model the setup step already downloaded; if it is missing, faster-whisper fetches
    it into the install folder.
    """

    def __init__(
        self,
        tier: Tier,
        language: str | None = None,
        model: str | None = None,
        beam_size: int = 5,
        cpu_threads: int | None = None,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install speech support: pip install 'ilfu[asr]'") from exc
        name = model or tier.model
        if is_downloaded(name):
            source, root = str(model_path(name)), None
        else:
            source, root = name, str(models_root())
        if cpu_threads is None:
            cpu_threads = default_cpu_threads(os.cpu_count() or 1)
        self._model = WhisperModel(
            source,
            device=tier.device,
            compute_type=tier.compute_type,
            download_root=root,
            cpu_threads=cpu_threads if tier.device == "cpu" else 0,
        )
        self.language = language
        self.beam_size = beam_size

    def transcribe(self, audio_path: Path) -> list[Segment]:
        segments, _info = self._model.transcribe(
            str(audio_path),
            language=self.language,
            vad_filter=True,
            beam_size=self.beam_size,
            condition_on_previous_text=False,
        )
        return [Segment(s.start, s.end, s.text.strip()) for s in segments]
