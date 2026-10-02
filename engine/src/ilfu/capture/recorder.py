"""Writes each audio source to its own WAV file without ever blocking the audio thread."""

from __future__ import annotations

import queue
import threading
import time
import wave
from array import array
from collections.abc import Callable
from pathlib import Path

from .base import AudioSource
from .priority import boost_current_thread

_QUEUE_BLOCKS = 4096
_PAD_AFTER_SECONDS = 0.3  # shorter gaps are normal jitter, not silence


class _Track:
    def __init__(self, source: AudioSource, path: Path) -> None:
        self.source = source
        self.path = path
        self.dropped_blocks = 0
        self.frames_written = 0
        self.paused = False
        self.level = 0.0  # loudest sample of the latest block, 0 to 1
        self.tap: Callable[[bytes], None] | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=_QUEUE_BLOCKS)
        self._thread = threading.Thread(target=self._write_loop, name=f"ilfu-write-{source.name}")
        self._t0 = 0.0
        self._paused_total = 0.0
        self._paused_since = 0.0

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._thread.start()
        self.source.start(self._on_audio)

    def stop(self) -> None:
        self.source.stop()
        self._queue.put(None)
        self._thread.join()

    def pause(self) -> None:
        if not self.paused:
            self._paused_since = time.monotonic()
            self.paused = True

    def resume(self) -> None:
        if self.paused:
            self._paused_total += time.monotonic() - self._paused_since
            self.paused = False

    def _active_seconds(self) -> float:
        now = time.monotonic()
        paused = self._paused_total + (now - self._paused_since if self.paused else 0.0)
        return now - self._t0 - paused

    def _on_audio(self, data: bytes) -> None:
        # Runs on the audio thread: never block, drop and count instead.
        if self.paused:
            return
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            self.dropped_blocks += 1

    def _write(self, wav: wave.Wave_write, data: bytes) -> None:
        fmt = self.source.format
        # The wave module keeps the header current, so a crash leaves a playable file.
        wav.writeframes(data)
        self.frames_written += len(data) // (fmt.channels * fmt.sample_width)
        if self.tap is not None:
            self.tap(data)

    def _pad(self, wav: wave.Wave_write, incoming_frames: int = 0, force: bool = False) -> None:
        """Write silence for time in which the source delivered nothing."""
        fmt = self.source.format
        frame_bytes = fmt.channels * fmt.sample_width
        behind = int(self._active_seconds() * fmt.rate) - self.frames_written - incoming_frames
        if behind < (1 if force else int(_PAD_AFTER_SECONDS * fmt.rate)):
            return
        self.level = 0.0
        while behind > 0:
            frames = min(behind, fmt.rate)  # at most one second at a time
            self._write(wav, bytes(frames * frame_bytes))
            behind -= frames

    def _write_loop(self) -> None:
        boost_current_thread()
        fmt = self.source.format
        frame_bytes = fmt.channels * fmt.sample_width
        with wave.open(str(self.path), "wb") as wav:
            wav.setnchannels(fmt.channels)
            wav.setsampwidth(fmt.sample_width)
            wav.setframerate(fmt.rate)
            while True:
                try:
                    data = self._queue.get(timeout=0.25)
                except queue.Empty:
                    if self.source.pad_silence and not self.paused:
                        self._pad(wav)
                    continue
                if data is None:
                    if self.source.pad_silence:
                        self._pad(wav, force=True)
                    break
                if self.source.pad_silence:
                    self._pad(wav, incoming_frames=len(data) // frame_bytes)
                self._write(wav, data)
                samples = array("h")
                samples.frombytes(data[: len(data) // 2 * 2])
                self.level = min(1.0, max((abs(v) for v in samples[::8]), default=0) / 32768)


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
            track.pause()

    def resume(self) -> None:
        for track in self.tracks.values():
            track.resume()

    def levels(self) -> dict[str, float]:
        """How loud each source is right now, 0 to 1 (for the level meters)."""
        return {name: round(t.level, 3) for name, t in self.tracks.items()}

    def stop(self) -> dict[str, int]:
        """Stop everything and return the number of dropped blocks per source."""
        for track in self.tracks.values():
            track.stop()
        return {name: t.dropped_blocks for name, t in self.tracks.items()}
