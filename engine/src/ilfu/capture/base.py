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
    # Windows loopback delivers nothing while the computer is silent. Sources like that set this
    # so the recorder fills the gaps with silence and the tracks stay in step with the clock.
    pad_silence: bool = False

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

    def list_microphones(self) -> list[str]:
        """Names of microphones the user can pick. Empty when the OS cannot say."""
        return []

    def list_speakers(self) -> list[str]:
        """Names of outputs whose sound can be captured (speakers, headphones, headsets)."""
        return []

    @abstractmethod
    def open_system_audio(self, device: str | None = None) -> AudioSource:
        """What the user hears (the call's other participants). None means the OS default."""

    @abstractmethod
    def open_microphone(self, device: str | None = None) -> AudioSource:
        """What the user says. None means the OS default."""

    def close(self) -> None:
        """Release the audio system. Called when recording is over."""
