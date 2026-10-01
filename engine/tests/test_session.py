import wave
from pathlib import Path

from ilfu.paths import new_session_dir
from ilfu.session import transcribe_session
from ilfu.transcript import Segment
from ilfu.uninstall import launch_uninstaller


def _wav(path: Path, frames: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * frames)


class Stub:
    def transcribe(self, audio_path: Path):
        if audio_path.name == "mic.wav":
            return [Segment(0.0, 1.0, "hello"), Segment(5.0, 6.0, "bye")]
        return [Segment(2.0, 3.0, "hi there"), Segment(4.0, 4.5, "  ")]


def test_session_merges_and_labels_both_sides(tmp_path):
    _wav(tmp_path / "mic.wav", 100)
    _wav(tmp_path / "system.wav", 100)
    segs = transcribe_session(tmp_path, Stub())
    assert [(s.speaker, s.text) for s in segs] == [
        ("You", "hello"),
        ("Them", "hi there"),
        ("You", "bye"),
    ]


def test_session_skips_missing_or_empty_audio(tmp_path):
    _wav(tmp_path / "mic.wav", 0)
    assert transcribe_session(tmp_path, Stub()) == []


def test_new_session_dir_is_created(tmp_path):
    path = new_session_dir(tmp_path)
    assert path.is_dir() and path.parent == tmp_path


def test_uninstall_message_when_not_installed_by_script():
    assert "pip uninstall ilfu" in launch_uninstaller()
