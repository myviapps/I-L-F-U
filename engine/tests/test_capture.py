import time
import wave

from ilfu.capture import Recorder, get_backend
from ilfu.cli import main


def test_recorder_writes_one_wav_per_source(tmp_path):
    backend = get_backend("fake")
    recorder = Recorder(
        {"system": backend.open_system_audio(), "mic": backend.open_microphone()}, tmp_path
    )
    recorder.start()
    time.sleep(0.5)
    dropped = recorder.stop()

    assert dropped == {"system": 0, "mic": 0}
    for name in ("system", "mic"):
        with wave.open(str(tmp_path / f"{name}.wav"), "rb") as wav:
            assert wav.getframerate() == 16000
            assert wav.getnchannels() == 1
            assert wav.getnframes() > 16000 * 0.1


def test_cli_record_with_fake_backend(tmp_path, capsys):
    code = main(["--backend", "fake", "record", "--seconds", "0.3", "--out", str(tmp_path / "r")])
    assert code == 0
    assert (tmp_path / "r" / "system.wav").exists()
    assert "Dropped blocks" in capsys.readouterr().out


def test_cli_lists_fake_devices(capsys):
    assert main(["--backend", "fake", "devices"]) == 0
    assert "fake microphone" in capsys.readouterr().out


class Bursty:
    """Like Windows loopback: delivers audio in bursts with silent gaps (no data at all)."""

    name = "system"
    pad_silence = True

    def __init__(self):
        from ilfu.capture.base import AudioFormat

        self.format = AudioFormat(rate=16000, channels=1)
        self._stop = False

    def start(self, callback):
        import struct
        import threading

        def run():
            block = struct.pack("<1600h", *([4000, -4000] * 800))  # 0.1 s
            for _ in range(3):
                if self._stop:
                    return
                callback(block)
                time.sleep(0.1)
            time.sleep(1.5)  # nothing playing: no data at all
            while not self._stop:
                callback(block)
                time.sleep(0.1)

        self._t = threading.Thread(target=run, daemon=True)
        self._t.start()

    def stop(self):
        self._stop = True
        self._t.join()


def test_silent_gaps_are_filled_so_tracks_stay_on_the_clock(tmp_path):
    rec = Recorder({"system": Bursty()}, tmp_path)
    rec.start()
    time.sleep(3.0)
    rec.stop()
    with wave.open(str(tmp_path / "system.wav"), "rb") as wav:
        seconds = wav.getnframes() / 16000
    assert 2.7 < seconds < 3.4, seconds  # without padding this would be about 1.5 s


def test_pause_is_not_filled_with_silence(tmp_path):
    rec = Recorder({"system": Bursty()}, tmp_path)
    rec.start()
    time.sleep(1.0)
    rec.pause()
    time.sleep(1.5)
    rec.resume()
    time.sleep(1.0)
    rec.stop()
    with wave.open(str(tmp_path / "system.wav"), "rb") as wav:
        seconds = wav.getnframes() / 16000
    assert 1.7 < seconds < 2.5, seconds  # about 2 s recorded, the 1.5 s pause left out


def test_levels_follow_the_audio(tmp_path):
    backend = get_backend("fake")
    rec = Recorder({"mic": backend.open_microphone()}, tmp_path)
    rec.start()
    time.sleep(0.5)
    level = rec.levels()["mic"]
    rec.stop()
    assert 0.1 < level <= 1.0
