"""Small audio helpers. Quiet speakers are boosted before transcription so they are not missed."""

from __future__ import annotations

import wave
from pathlib import Path

TARGET_LEVEL = 0.5  # aim for speech peaking at half of full scale
MAX_GAIN = 16.0  # never boost more than this, so background hiss does not become speech
FLOOR = 0.004  # quieter than this is treated as silence and left alone


def gain_for(level: float) -> float:
    """How much to amplify audio whose loud parts reach `level` (0 to 1)."""
    if level < FLOOR or level >= TARGET_LEVEL:
        return 1.0
    return min(MAX_GAIN, TARGET_LEVEL / level)


def _level(samples) -> float:
    import numpy as np

    if samples.size == 0:
        return 0.0
    # The 99.5th percentile ignores a single click or cough that would hide a quiet voice.
    return float(np.percentile(np.abs(samples[::4].astype(np.float32)), 99.5)) / 32768


def boost_pcm16(data: bytes) -> bytes:
    """Amplify little-endian 16-bit audio when it is quiet. Loud audio is returned unchanged."""
    try:
        import numpy as np
    except ImportError:
        return data
    samples = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2")
    gain = gain_for(_level(samples))
    if gain == 1.0:
        return data
    return np.clip(samples.astype(np.float32) * gain, -32768, 32767).astype("<i2").tobytes()


def boosted_copy(src: Path, dst: Path) -> Path:
    """Return `dst` holding a boosted copy of a WAV, or `src` itself when no boost is needed."""
    try:
        import numpy as np
    except ImportError:
        return src
    with wave.open(str(src), "rb") as wav:
        if wav.getsampwidth() != 2:
            return src
        frames = wav.getnframes()
        block = 1 << 20
        levels = []
        while True:
            raw = wav.readframes(block)
            if not raw:
                break
            levels.append(_level(np.frombuffer(raw, dtype="<i2")))
    if not levels or frames == 0:
        return src
    gain = gain_for(float(np.median([v for v in levels if v >= FLOOR] or [1.0])))
    if gain == 1.0:
        return src
    with wave.open(str(src), "rb") as wav, wave.open(str(dst), "wb") as out:
        out.setnchannels(wav.getnchannels())
        out.setsampwidth(2)
        out.setframerate(wav.getframerate())
        while True:
            raw = wav.readframes(block)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) * gain
            out.writeframes(np.clip(samples, -32768, 32767).astype("<i2").tobytes())
    return dst
