import io
import struct
import tarfile
import wave

import pytest

from ilfu import benchmark
from ilfu.transcript import Segment
from ilfu.wer import normalize, word_errors


def test_wer_keeps_hindi_and_telugu_words_whole():
    assert normalize("कि वह घर गया।") == ["कि", "वह", "घर", "गया"]
    assert normalize("తెలుగు, భాష!") == ["తెలుగు", "భాష"]
    assert word_errors("मैं घर जा रहा हूँ", "मैं घर जा रहा हूँ").errors == 0
    assert word_errors("मैं घर जा रहा हूँ", "मैं घर जा रही हूँ").errors == 1


def test_wer_still_handles_english():
    assert normalize("Don't stop, OK?") == ["don't", "stop", "ok"]


def test_pick_is_deterministic_and_even():
    rows = [(f"clip{i:03d}.wav", f"text {i}") for i in range(100)]
    a = benchmark.pick(rows, 10)
    assert a == benchmark.pick(list(reversed(rows)), 10)  # order of input does not matter
    assert [r[0] for r in a][:3] == ["clip000.wav", "clip010.wav", "clip020.wav"]
    assert len(benchmark.pick(rows[:5], 10)) == 5


def _wav_bytes(value):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<1600h", *([value] * 1600)))
    return buf.getvalue()


@pytest.fixture
def fake_fleurs(tmp_path):
    tsv = tmp_path / "test.tsv"
    names = [f"c{i:02d}.wav" for i in range(12)]
    tsv.write_text(
        "\n".join(f"{i}\t{n}\traw {i}\tword{i} again\tchars\t16000\tMALE" for i, n in enumerate(names)),
        encoding="utf-8",
    )
    tar_path = tmp_path / "test.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for i, n in enumerate(names):
            data = _wav_bytes(100 + i)
            info = tarfile.TarInfo(f"test/{n}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    def fetch(filename):
        return tsv if filename.endswith(".tsv") else tar_path

    return fetch


def test_download_extracts_only_the_picked_clips(tmp_path, fake_fleurs):
    items = benchmark.download("en", tmp_path / "cache", 4, fetch=fake_fleurs)
    assert len(items) == 4 and all(i.audio.exists() and i.tag == "en" for i in items)
    assert len(list((tmp_path / "cache" / "en_us").glob("*.wav"))) == 4
    def tsv_only(filename):
        if not filename.endswith(".tsv"):
            pytest.fail("the audio archive was fetched again")
        return fake_fleurs(filename)

    again = benchmark.download("en", tmp_path / "cache", 4, fetch=tsv_only)
    assert [i.audio.name for i in again] == [i.audio.name for i in items]  # reused from cache


def test_freeze_check_detects_changed_audio(tmp_path, fake_fleurs):
    items = benchmark.download("en", tmp_path / "cache", 4, fetch=fake_fleurs)
    frozen = tmp_path / "frozen.json"
    current, problems = benchmark.freeze_check(items, frozen)
    assert problems == []  # nothing frozen yet
    import json

    frozen.write_text(json.dumps(current))
    assert benchmark.freeze_check(items, frozen)[1] == []
    items[0].audio.write_bytes(b"different")
    problems = benchmark.freeze_check(items, frozen)[1]
    assert problems and "audio changed" in problems[0]


def test_run_reports_wer_per_language_and_speed(tmp_path, fake_fleurs):
    items = benchmark.download("en", tmp_path / "cache", 3, fetch=fake_fleurs)

    class Perfect:
        language = None

        def __init__(self, items):
            self.refs = {i.audio: i.reference for i in items}

        def transcribe(self, path):
            return [Segment(0, 1, self.refs[path])]

    report = benchmark.run(items, Perfect(items), "stub")
    assert report["wer"] == 0 and report["wer_by_tag"] == {"en": 0.0}
    assert report["audio_seconds"] > 0 and report["real_time_factor"] is not None
    assert "English" in benchmark.to_markdown(report)
