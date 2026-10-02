"""Writes each audio source to its own WAV file without ever blocking the audio thread."""

from __future__ import annotations

import queue
import threading
import wave
from collections.abc import Callable
from pathlib import Path

from .base import AudioSource

_QUEUE_BLOCKS = 4096


class _Track:
    def __init__(self, source: AudioSource, path: Path) -> None:
        self.source = source
        self.path = path
        self.dropped_blocks = 0
        self.frames_written = 0
        self.paused = False
        self.tap: Callable[[bytes], None] | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=_QUEUE_BLOCKS)
        self._thread = threading.Thread(target=self._write_loop, name=f"ilfu-write-{source.name}")

    def start(self) -> None:
        self._thread.start()
        self.source.start(self._on_audio)

    def stop(self) -> None:
        self.source.stop()
        self._queue.put(None)
        self._thread.join()

    def _on_audio(self, data: bytes) -> None:
        # Runs on the audio thread: never block, drop and count instead.
        if self.paused:
            return
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            self.dropped_blocks += 1

    def _write_loop(self) -> None:
        fmt = self.source.format
        with wave.open(str(self.path), "wb") as wav:
            wav.setnchannels(fmt.channels)
            wav.setsampwidth(fmt.sample_width)
            wav.setframerate(fmt.rate)
            while True:
                data = self._queue.get()
                if data is None:
                    break
                # The wave module keeps the header current, so a crash leaves a playable file.
                wav.writeframes(data)
                self.frames_written += len(data) // (fmt.channels * fmt.sample_width)
                if self.tap is not None:
                    self.tap(data)


class Recorder:
    """Records several named sources, one WAV file per source, into `out_dir`."""

    def __init__(self, sources: dict[str, AudioSource], out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.tracks = {name: _Track(src, out_dir / f"{name}.wav") for name, src in sources.items()}

    def start(self) -> None:
        for track in self.tracks.values():
            track.start()

    def set_tap(self, tap: Callable[[str, bytes], None] | None) -> None:
        """Also hand every recorded block to `tap(source_name, data)`, for live captions."""
        for name, track in self.tracks.items():
            track.tap = None if tap is None else (lambda data, n=name: tap(n, data))

    def pause(self) -> None:
        for track in self.tracks.values():
            track.paused = True

    def resume(self) -> None:
        for track in self.tracks.values():
            track.paused = False

    def stop(self) -> dict[str, int]:
        """Stop everything and return the number of dropped blocks per source."""
        for track in self.tracks.values():
            track.stop()
        return {name: t.dropped_blocks for name, t in self.tracks.items()}
