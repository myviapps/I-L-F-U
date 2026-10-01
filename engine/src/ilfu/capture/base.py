"""Capture interfaces shared by every operating system backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    """Raw PCM format: signed 16-bit little-endian samples."""

    rate: int
    channels: int
    sample_width: int = 2


# Called from the audio thread with a block of raw PCM bytes. It must return quickly.
FrameCallback = Callable[[bytes], None]


class AudioSource(ABC):
    """One stream of audio, for example the microphone or the system output."""

    name: str
    format: AudioFormat

    @abstractmethod
    def start(self, callback: FrameCallback) -> None:
        """Begin delivering audio blocks to `callback`."""

    @abstractmethod
    def stop(self) -> None:
        """Stop delivering audio and release the device."""


class CaptureBackend(ABC):
    """Opens audio sources on one operating system."""

    @abstractmethod
    def list_devices(self) -> list[str]:
        """Human-readable device names, for `ilfu devices`."""

    @abstractmethod
    def open_system_audio(self) -> AudioSource:
        """What the user hears (the call's other participants)."""

    @abstractmethod
    def open_microphone(self) -> AudioSource:
        """What the user says."""
