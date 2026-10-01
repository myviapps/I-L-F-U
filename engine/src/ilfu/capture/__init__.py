"""Audio capture: interfaces, recorder and per-OS backends."""

from __future__ import annotations

import sys

from .base import AudioFormat, AudioSource, CaptureBackend
from .recorder import Recorder

__all__ = ["AudioFormat", "AudioSource", "CaptureBackend", "Recorder", "get_backend"]


def get_backend(name: str = "auto") -> CaptureBackend:
    """Pick a capture backend. `auto` chooses by operating system."""
    if name == "fake":
        from .fake import FakeBackend

        return FakeBackend()
    if name in ("auto", "windows") and sys.platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    raise RuntimeError(
        f"No capture backend for '{name}' on {sys.platform} yet. "
        "Windows is first; macOS and Linux come later. Use --backend fake to try the CLI."
    )
