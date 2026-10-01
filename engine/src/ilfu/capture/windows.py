"""Windows capture using WASAPI loopback (what you hear) and the default microphone.

Uses the PyAudioWPatch package (`pip install ilfu[windows]`). It is imported lazily so the
rest of the engine works on any OS.

Status: written against the PyAudioWPatch API but not yet run on a real Windows machine
with a call open. See docs/ROADMAP.md, Phase 1 gate.
"""

from __future__ import annotations

from typing import Any

from .base import AudioFormat, AudioSource, CaptureBackend, FrameCallback

_BLOCK_FRAMES = 1024


def _import_pyaudio() -> Any:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as exc:  # pragma: no cover - depends on the platform
        raise RuntimeError(
            "Windows capture needs PyAudioWPatch: pip install 'ilfu[windows]'"
        ) from exc
    return pyaudio


class _WasapiSource(AudioSource):
    def __init__(self, pa: Any, pyaudio: Any, name: str, device: dict[str, Any]) -> None:
        self.name = name
        self._pa = pa
        self._pyaudio = pyaudio
        self._device = device
        self.format = AudioFormat(
            rate=int(device["defaultSampleRate"]), channels=int(device["maxInputChannels"])
        )
        self._stream: Any = None

    def start(self, callback: FrameCallback) -> None:
        pyaudio = self._pyaudio

        def on_audio(in_data: bytes, frame_count: int, time_info: Any, status: Any):
            callback(in_data)
            return (None, pyaudio.paContinue)

        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self.format.channels,
            rate=self.format.rate,
            input=True,
            input_device_index=self._device["index"],
            frames_per_buffer=_BLOCK_FRAMES,
            stream_callback=on_audio,
        )

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None


class WindowsBackend(CaptureBackend):
    def __init__(self) -> None:
        self._pyaudio = _import_pyaudio()
        self._pa = self._pyaudio.PyAudio()

    def _wasapi(self) -> dict[str, Any]:
        return self._pa.get_host_api_info_by_type(self._pyaudio.paWASAPI)

    def _loopback_device(self) -> dict[str, Any]:
        speakers = self._pa.get_device_info_by_index(self._wasapi()["defaultOutputDevice"])
        if speakers.get("isLoopbackDevice"):
            return speakers
        for loopback in self._pa.get_loopback_device_info_generator():
            if speakers["name"] in loopback["name"]:
                return loopback
        raise RuntimeError("No loopback device found for the default speakers")

    def list_devices(self) -> list[str]:
        names = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                kind = "loopback" if info.get("isLoopbackDevice") else "input"
                names.append(f"{info['name']} ({kind})")
        return names

    def open_system_audio(self) -> AudioSource:
        return _WasapiSource(self._pa, self._pyaudio, "system", self._loopback_device())

    def open_microphone(self) -> AudioSource:
        device = self._pa.get_device_info_by_index(self._wasapi()["defaultInputDevice"])
        return _WasapiSource(self._pa, self._pyaudio, "mic", device)
