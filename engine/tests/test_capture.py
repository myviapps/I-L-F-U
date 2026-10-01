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
            assert wav.getnframes() > 16000 * 0.3


def test_cli_record_with_fake_backend(tmp_path, capsys):
    code = main(["--backend", "fake", "record", "--seconds", "0.3", "--out", str(tmp_path / "r")])
    assert code == 0
    assert (tmp_path / "r" / "system.wav").exists()
    assert "Dropped blocks" in capsys.readouterr().out


def test_cli_lists_fake_devices(capsys):
    assert main(["--backend", "fake", "devices"]) == 0
    assert "fake microphone" in capsys.readouterr().out
