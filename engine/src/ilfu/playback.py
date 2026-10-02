"""Play a recording back. The two tracks (you and them) are mixed into one file first."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

from .library import TRACKS


def _params(path: Path) -> tuple[int, int, int, int]:
    with wave.open(str(path), "rb") as wav:
        return wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()


def mixed_file(folder: Path) -> Path | None:
    """Return a playable WAV for the folder, creating `mix.wav` when both tracks exist."""
    tracks = [folder / f"{t}.wav" for t in TRACKS if (folder / f"{t}.wav").exists()]
    tracks = [t for t in tracks if _params(t)[3] > 0]
    if not tracks:
        return None
    if len(tracks) == 1:
        return tracks[0]
    mix = folder / "mix.wav"
    newest = max(t.stat().st_mtime for t in tracks)
    if mix.exists() and mix.stat().st_mtime >= newest:
        return mix
    a, b = _params(tracks[0]), _params(tracks[1])
    if a[:3] != b[:3]:
        return max(tracks, key=lambda t: _params(t)[3])  # formats differ: play the longer track
    try:
        import numpy as np
    except ImportError:
        return max(tracks, key=lambda t: _params(t)[3])
    block = 1 << 20
    with (
        wave.open(str(tracks[0]), "rb") as w1,
        wave.open(str(tracks[1]), "rb") as w2,
        wave.open(str(mix), "wb") as out,
    ):
        out.setnchannels(a[0])
        out.setsampwidth(a[1])
        out.setframerate(a[2])
        while True:
            d1, d2 = w1.readframes(block), w2.readframes(block)
            if not d1 and not d2:
                break
            x = np.frombuffer(d1, dtype="<i2").astype(np.int32)
            y = np.frombuffer(d2, dtype="<i2").astype(np.int32)
            total = np.zeros(max(len(x), len(y)), dtype=np.int32)
            total[: len(x)] += x
            total[: len(y)] += y
            out.writeframes(np.clip(total, -32768, 32767).astype("<i2").tobytes())
    return mix


def supported() -> bool:
    return sys.platform == "win32"


def play(path: Path) -> None:
    if not supported():
        raise RuntimeError("Playback inside the app works on Windows only for now.")
    import winsound

    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)


def stop() -> None:
    if supported():
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)
