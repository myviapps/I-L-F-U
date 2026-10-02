import struct
import time
import wave
from pathlib import Path

from ilfu import config, library, models
from ilfu.capture import Recorder
from ilfu.capture.base import AudioFormat, AudioSource
from ilfu.live import LiveTranscriber
from ilfu.transcript import Segment


def _wav(path: Path, frames: int, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)


# ---- config ----
def test_config_round_trip_and_unknown_keys(tmp_path):
    path = tmp_path / "c.json"
    cfg = config.Config(save_dir=str(tmp_path), model="small", language="hi", setup_done=True)
    cfg.terms_version = config.TERMS_VERSION
    config.save(cfg, path)
    loaded = config.load(path)
    assert loaded == cfg
    assert loaded.language_code() == "hi"
    assert not config.needs_setup(loaded)
    path.write_text('{"model": "base", "future_key": 1}')
    assert config.load(path).model == "base"


def test_config_missing_or_broken_file_means_setup_needed(tmp_path):
    assert config.needs_setup(config.load(tmp_path / "none.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert config.needs_setup(config.load(bad))


def test_old_terms_version_asks_again():
    cfg = config.Config(terms_version=0, setup_done=True, model="base")
    assert config.needs_setup(cfg)


def test_auto_language_means_detect():
    assert config.Config(language="auto").language_code() is None


def test_regional_languages_are_offered():
    for code in ("hi", "te", "ta", "kn", "ml", "mr", "bn"):
        assert code in config.LANGUAGES


# ---- models ----
def test_download_writes_marker_and_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)
    seen = []

    def fake_fetch(repo, target):
        (target / "model.bin").write_bytes(b"x" * 1000)

    assert not models.is_downloaded("base")
    models.download("base", seen.append, fetch=fake_fetch)
    assert models.is_downloaded("base")
    assert seen[-1] == 1.0
    models.remove("base")
    assert not models.is_downloaded("base")


def test_failed_download_is_not_marked_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_root", lambda: tmp_path)

    def broken(repo, target):
        raise OSError("offline")

    try:
        models.download("base", fetch=broken)
    except OSError:
        pass
    assert not models.is_downloaded("base")


def test_recommended_model_by_hardware():
    assert models.recommended(2, 4, False) == "base"
    assert models.recommended(8, 16, False) == "small"
    assert models.recommended(8, 16, True) == "large-v3-turbo"


# ---- library ----
def test_library_list_rename_delete(tmp_path):
    a = tmp_path / "20260101-100000"
    b = tmp_path / "20260102-100000"
    for d in (a, b):
        d.mkdir()
        _wav(d / "mic.wav", 16000 * 2)
    (tmp_path / "empty").mkdir()
    found = library.list_sessions(tmp_path)
    assert [s.path for s in found] == [b, a]
    assert round(found[0].duration) == 2
    library.rename(a, "  Standup  ")
    assert library.describe(a).title == "Standup"
    library.delete(a)
    assert not a.exists()
    assert len(library.list_sessions(tmp_path)) == 1


def test_library_reads_transcript(tmp_path):
    assert library.read_transcript(tmp_path) == ""
    (tmp_path / "transcript.md").write_text("hello", encoding="utf-8")
    assert library.read_transcript(tmp_path) == "hello"


# ---- pause and live captions ----
class Tone(AudioSource):
    """Loud audio so the live captioner does not skip it as silence."""

    def __init__(self, name):
        self.name = name
        self.format = AudioFormat(rate=16000, channels=1)
        self._on = False

    def start(self, callback):
        import threading

        self._on = True

        def run():
            block = struct.pack("<1600h", *([5000, -5000] * 800))
            while self._on:
                callback(block)
                time.sleep(0.02)

        self._t = threading.Thread(target=run, daemon=True)
        self._t.start()

    def stop(self):
        self._on = False
        self._t.join()


def test_pause_stops_writing_audio(tmp_path):
    rec = Recorder({"mic": Tone("mic")}, tmp_path)
    rec.start()
    time.sleep(0.3)
    rec.pause()
    time.sleep(0.1)
    before = rec.tracks["mic"].frames_written
    time.sleep(0.3)
    assert rec.tracks["mic"].frames_written == before
    rec.resume()
    time.sleep(0.3)
    rec.stop()
    assert rec.tracks["mic"].frames_written > before


class FakeTranscriber:
    language = None

    def __init__(self):
        self.calls = 0

    def transcribe(self, path):
        self.calls += 1
        return [Segment(0.0, 1.0, f"words {self.calls}")]


def test_live_captions_are_labelled_offset_and_sorted(tmp_path):
    rec = Recorder({"mic": Tone("mic"), "system": Tone("system")}, tmp_path)
    fake = FakeTranscriber()
    got = []
    live = LiveTranscriber(rec, lambda: fake, got.extend, chunk_seconds=0.5)
    rec.start()
    live.start()
    time.sleep(2.0)
    rec.stop()
    segments = live.stop()
    assert segments, "no captions produced"
    assert {s.speaker for s in segments} == {"You", "Them"}
    mic = [s for s in segments if s.speaker == "You"]
    assert mic[0].start == 0.0
    assert mic[-1].start > mic[0].start  # later chunks are shifted by their position
    assert segments == sorted(segments, key=lambda s: (s.start, s.end))
    assert len(got) == len(segments)


def test_live_waits_for_the_model_then_catches_up(tmp_path):
    rec = Recorder({"mic": Tone("mic")}, tmp_path)
    holder = {"t": None}
    live = LiveTranscriber(rec, lambda: holder["t"], lambda s: None, chunk_seconds=0.5)
    rec.start()
    live.start()
    time.sleep(1.2)
    assert live.lag_seconds() > 0.5  # audio is buffered while the model loads
    holder["t"] = FakeTranscriber()
    time.sleep(1.0)
    rec.stop()
    assert live.stop()


def test_live_error_does_not_break_recording(tmp_path):
    class Boom:
        def transcribe(self, path):
            raise RuntimeError("model exploded")

    rec = Recorder({"mic": Tone("mic")}, tmp_path)
    errors = []
    live = LiveTranscriber(rec, Boom, lambda s: None, errors.append, chunk_seconds=0.4)
    rec.start()
    live.start()
    time.sleep(1.2)
    rec.stop()
    live.stop()
    assert errors == ["model exploded"]
    assert live.failed
    with wave.open(str(tmp_path / "mic.wav"), "rb") as w:
        assert w.getnframes() > 0


def test_silence_is_not_transcribed(tmp_path):

    class Quiet(Tone):
        def start(self, callback):
            import threading

            self._on = True

            def run():
                while self._on:
                    callback(b"\x00\x00" * 1600)
                    time.sleep(0.02)

            self._t = threading.Thread(target=run, daemon=True)
            self._t.start()

    rec = Recorder({"mic": Quiet("mic")}, tmp_path)
    fake = FakeTranscriber()
    live = LiveTranscriber(rec, lambda: fake, lambda s: None, chunk_seconds=0.4)
    rec.start()
    live.start()
    time.sleep(1.5)
    rec.stop()
    live.stop()
    assert fake.calls == 0


def test_mix_combines_two_tracks(tmp_path):
    import pytest

    pytest.importorskip("numpy")
    from ilfu import playback

    for name in ("mic", "system"):
        with wave.open(str(tmp_path / f"{name}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<4h", 1000, 1000, 1000, 1000))
    mix = playback.mixed_file(tmp_path)
    assert mix == tmp_path / "mix.wav"
    with wave.open(str(mix), "rb") as w:
        assert struct.unpack("<4h", w.readframes(4)) == (2000, 2000, 2000, 2000)


def test_playback_of_empty_recording_is_none(tmp_path):
    from ilfu import playback

    _wav(tmp_path / "mic.wav", 0)
    assert playback.mixed_file(tmp_path) is None


def test_cli_setup_requires_agreement(capsys):
    from ilfu.cli import main

    assert main(["setup"]) == 2


def test_cli_setup_downloads_and_saves(tmp_path, monkeypatch):
    from ilfu.cli import main

    monkeypatch.setattr(models, "models_root", lambda: tmp_path / "m")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "cfg.json")
    monkeypatch.setattr(
        models, "_hub_fetch", lambda repo, target: (target / "model.bin").write_bytes(b"x")
    )
    assert main(["setup", "--model", "base", "--accept-terms", "--save-dir", str(tmp_path)]) == 0
    cfg = config.load(tmp_path / "cfg.json")
    assert cfg.model == "base" and cfg.setup_done
    assert not config.needs_setup(cfg)


def test_quiet_voice_is_boosted_and_loud_or_silent_audio_is_not():
    import pytest

    pytest.importorskip("numpy")
    from ilfu.audio_utils import MAX_GAIN, boost_pcm16, gain_for

    quiet = struct.pack("<400h", *([600, -600] * 200))  # peak about 1.8% of full scale
    out = struct.unpack("<400h", boost_pcm16(quiet))
    assert max(out) > 600 * 8
    loud = struct.pack("<400h", *([20000, -20000] * 200))
    assert boost_pcm16(loud) == loud
    silent = bytes(800)
    assert boost_pcm16(silent) == silent
    assert gain_for(0.0041) <= MAX_GAIN  # hiss is never boosted without limit
    assert gain_for(0.001) == 1.0


def test_session_transcription_boosts_quiet_tracks(tmp_path):
    import pytest

    pytest.importorskip("numpy")
    from ilfu.session import transcribe_session

    with wave.open(str(tmp_path / "mic.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<1600h", *([500, -500] * 800)))
    seen = {}

    class Spy:
        def transcribe(self, path):
            with wave.open(str(path), "rb") as w:
                seen["peak"] = max(struct.unpack(f"<{w.getnframes()}h", w.readframes(w.getnframes())))
            return [Segment(0, 1, "quiet words")]

    segs = transcribe_session(tmp_path, Spy())
    assert segs[0].text == "quiet words" and seen["peak"] > 500 * 8


def test_heavy_transcription_never_costs_recorded_audio(tmp_path):
    """A transcriber that hogs the CPU may delay captions but must not lose or gap the audio."""
    import time as _time

    class Hog:
        def transcribe(self, path):
            end = _time.time() + 0.6
            while _time.time() < end:  # busy loop, as a heavy model would
                sum(range(2000))
            return [Segment(0.0, 1.0, "slow words")]

    rec = Recorder({"mic": Tone("mic"), "system": Tone("system")}, tmp_path)
    live = LiveTranscriber(rec, lambda: Hog(), lambda s: None, chunk_seconds=0.5)
    rec.start()
    live.start()
    time.sleep(3.0)
    dropped = rec.stop()
    live.stop()
    assert dropped == {"mic": 0, "system": 0}
    for name in ("mic", "system"):
        with wave.open(str(tmp_path / f"{name}.wav"), "rb") as w:
            assert 2.4 < w.getnframes() / 16000 < 3.4  # about as long as the recording


def test_background_priority_is_lowered():
    import subprocess
    import sys

    code = (
        "import os; from ilfu.capture.priority import lower_process_priority as f; "
        "a = os.nice(0); f(); print(os.nice(0) - a)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if sys.platform != "win32":
        assert int(out.stdout.strip()) > 0
