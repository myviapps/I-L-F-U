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
        # Loopback sends no audio at all while nothing is playing; keep the timeline honest.
        self.pad_silence = bool(device.get("isLoopbackDevice"))
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

    def _wasapi_devices(self) -> list[dict[str, Any]]:
        wasapi = self._wasapi()["index"]
        found = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info.get("hostApi") == wasapi:
                found.append(info)
        return found

    def list_microphones(self) -> list[str]:
        return [
            d["name"]
            for d in self._wasapi_devices()
            if d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice")
        ]

    def list_speakers(self) -> list[str]:
        return [d["name"] for d in self._wasapi_devices() if d["maxOutputChannels"] > 0]

    def _loopback_device(self, device: str | None = None) -> dict[str, Any]:
        if device:
            wanted = device
        else:
            speakers = self._pa.get_device_info_by_index(self._wasapi()["defaultOutputDevice"])
            if speakers.get("isLoopbackDevice"):
                return speakers
            wanted = speakers["name"]
        for loopback in self._pa.get_loopback_device_info_generator():
            if wanted in loopback["name"]:
                return loopback
        raise RuntimeError(f"No loopback device found for: {wanted}")

    def list_devices(self) -> list[str]:
        names = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                kind = "loopback" if info.get("isLoopbackDevice") else "input"
                names.append(f"{info['name']} ({kind})")
        return names

    def open_system_audio(self, device: str | None = None) -> AudioSource:
        return _WasapiSource(self._pa, self._pyaudio, "system", self._loopback_device(device))

    def open_microphone(self, device: str | None = None) -> AudioSource:
        if device:
            for info in self._wasapi_devices():
                if info["name"] == device and info["maxInputChannels"] > 0:
                    return _WasapiSource(self._pa, self._pyaudio, "mic", info)
            raise RuntimeError(f"Microphone not found: {device}")
        info = self._pa.get_device_info_by_index(self._wasapi()["defaultInputDevice"])
        return _WasapiSource(self._pa, self._pyaudio, "mic", info)

    def close(self) -> None:
        self._pa.terminate()
