"""A fake backend that produces a sine tone, for tests and for trying the CLI anywhere."""

from __future__ import annotations

import math
import struct
import threading
import time

from .base import AudioFormat, AudioSource, CaptureBackend, FrameCallback


class _ToneSource(AudioSource):
    def __init__(self, name: str, freq: float, rate: int = 16000, block_ms: int = 20) -> None:
        self.name = name
        self.format = AudioFormat(rate=rate, channels=1)
        self._freq = freq
        self._block = rate * block_ms // 1000
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, callback: FrameCallback) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()

    def _run(self, callback: FrameCallback) -> None:
        n = 0
        rate = self.format.rate
        while not self._stop.is_set():
            samples = [
                int(8000 * math.sin(2 * math.pi * self._freq * (n + i) / rate))
                for i in range(self._block)
            ]
            callback(struct.pack(f"<{self._block}h", *samples))
            n += self._block
            time.sleep(self._block / rate)


class FakeBackend(CaptureBackend):
    def list_devices(self) -> list[str]:
        return ["fake system audio (440 Hz)", "fake microphone (880 Hz)"]

    def list_microphones(self) -> list[str]:
        return ["Fake microphone", "Fake headset microphone"]

    def list_speakers(self) -> list[str]:
        return ["Fake speakers", "Fake headset"]

    def open_system_audio(self, device: str | None = None) -> AudioSource:
        if device and device not in self.list_speakers():
            raise RuntimeError(f"Output device not found: {device}")
        return _ToneSource("system", 440.0)

    def open_microphone(self, device: str | None = None) -> AudioSource:
        if device and device not in self.list_microphones():
            raise RuntimeError(f"Microphone not found: {device}")
        return _ToneSource("mic", 880.0)
