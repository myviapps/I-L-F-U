"""Live captions: transcribe the recording in short chunks while it is still going.

Audio is handed over by the recorder after it has been written to disk, so a slow model can
make the captions lag behind but can never lose or glitch the recording.
"""

from __future__ import annotations

import tempfile
import threading
import wave
from array import array
from collections.abc import Callable
from pathlib import Path

from .capture.base import AudioFormat
from .capture.recorder import Recorder
from .session import LABELS
from .transcribe import Transcriber
from .transcript import Segment

MAX_CHUNK_SECONDS = 28.0  # Whisper works on windows of up to 30 seconds
SILENCE_PEAK = 250  # of 32768; chunks quieter than this are skipped


def _is_silent(pcm: bytes) -> bool:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return True
    return max(abs(v) for v in samples[::16]) < SILENCE_PEAK


class LiveTranscriber:
    def __init__(
        self,
        recorder: Recorder,
        get_transcriber: Callable[[], Transcriber | None],
        on_segments: Callable[[list[Segment]], None],
        on_error: Callable[[str], None] | None = None,
        chunk_seconds: float = 5.0,
    ) -> None:
        self._formats: dict[str, AudioFormat] = {
            name: track.source.format for name, track in recorder.tracks.items()
        }
        self._get_transcriber = get_transcriber
        self._on_segments = on_segments
        self._on_error = on_error
        self._chunk_seconds = chunk_seconds
        self._buffers = {name: bytearray() for name in self._formats}
        self._consumed = dict.fromkeys(self._formats, 0)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ilfu-live", daemon=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="ilfu-live-"))
        self.segments: list[Segment] = []
        self.failed = False
        recorder.set_tap(self._feed)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> list[Segment]:
        """Finish the audio still waiting, then return every caption sorted by time."""
        self._stop.set()
        self._thread.join()
        for name in self._formats:
            self._drain(name, final=True)
        self._cleanup()
        return sorted(self.segments, key=lambda s: (s.start, s.end))

    def lag_seconds(self) -> float:
        with self._lock:
            return max(
                (len(buf) / self._bytes_per_second(n) for n, buf in self._buffers.items()),
                default=0.0,
            )

    # ---- internals ----
    def _bytes_per_second(self, name: str) -> int:
        fmt = self._formats[name]
        return fmt.rate * fmt.channels * fmt.sample_width

    def _feed(self, name: str, data: bytes) -> None:
        with self._lock:
            self._buffers[name] += data

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            if self.failed:
                continue
            for name in self._formats:
                self._drain(name, final=False)

    def _take(self, name: str, final: bool) -> tuple[bytes, float] | None:
        per_second = self._bytes_per_second(name)
        with self._lock:
            buf = self._buffers[name]
            if len(buf) < (0.2 if final else self._chunk_seconds) * per_second:
                return None
            size = min(len(buf), int(MAX_CHUNK_SECONDS * per_second))
            size -= size % (self._formats[name].channels * self._formats[name].sample_width)
            data = bytes(buf[:size])
            del buf[:size]
            offset = self._consumed[name] / per_second
            self._consumed[name] += size
        return data, offset

    def _drain(self, name: str, final: bool) -> None:
        if self.failed:
            return
        while True:
            transcriber = self._get_transcriber()
            if transcriber is None:
                return  # model still loading: keep buffering
            chunk = self._take(name, final)
            if chunk is None:
                return
            data, offset = chunk
            if _is_silent(data):
                continue
            try:
                found = self._transcribe(name, data, offset, transcriber)
            except Exception as exc:  # noqa: BLE001 - captions must never break the recording
                self.failed = True
                if self._on_error:
                    self._on_error(str(exc))
                return
            if found:
                self.segments.extend(found)
                self._on_segments(found)

    def _transcribe(
        self, name: str, data: bytes, offset: float, transcriber: Transcriber
    ) -> list[Segment]:
        fmt = self._formats[name]
        path = self._tmp / f"{name}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(fmt.channels)
            wav.setsampwidth(fmt.sample_width)
            wav.setframerate(fmt.rate)
            wav.writeframes(data)
        label = LABELS.get(name, name)
        return [
            Segment(s.start + offset, s.end + offset, s.text, speaker=label)
            for s in transcriber.transcribe(path)
            if s.text.strip()
        ]

    def _cleanup(self) -> None:
        for item in self._tmp.glob("*"):
            item.unlink(missing_ok=True)
        self._tmp.rmdir()
