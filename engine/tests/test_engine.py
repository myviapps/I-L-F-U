import json
from pathlib import Path

from ilfu.cli import main
from ilfu.evaluation import Item, compare, evaluate, load_manifest
from ilfu.hardware import Hardware, choose_tier
from ilfu.transcript import Segment, to_markdown, to_srt, to_text
from ilfu.wer import corpus_wer, normalize, word_errors


def test_wer_counts_substitutions_insertions_deletions():
    assert word_errors("the cat sat", "the cat sat").wer == 0
    assert word_errors("the cat sat", "the dog sat").errors == 1
    assert word_errors("the cat sat", "the cat sat down").errors == 1
    assert word_errors("the cat sat", "the sat").errors == 1
    assert word_errors("a b c d", "").wer == 1.0


def test_wer_ignores_case_and_punctuation():
    assert normalize("Hello, World!") == ["hello", "world"]
    assert word_errors("Hello, world.", "hello world").errors == 0


def test_corpus_wer_is_weighted_by_length():
    result = corpus_wer([("a b c d", "a b c d"), ("x y", "x z")])
    assert (result.errors, result.ref_words) == (1, 6)


def test_tier_choice():
    assert choose_tier(Hardware(2, 4, False)).name == "minimal"
    assert choose_tier(Hardware(4, 8, False)).name == "light"
    assert choose_tier(Hardware(8, 16, False)).model == "large-v3-turbo"
    gpu = choose_tier(Hardware(4, 16, True))
    assert (gpu.device, gpu.compute_type) == ("cuda", "float16")


def test_exports():
    segs = [Segment(0.0, 1.5, "Hello there", "You"), Segment(3661.25, 3662.0, "Bye")]
    assert to_text(segs) == "You: Hello there\nBye\n"
    assert "00:00:00,000 --> 00:00:01,500" in to_srt(segs)
    assert "01:01:01,250 --> 01:01:02,000" in to_srt(segs)
    assert to_markdown(segs).startswith("**[00:00:00]** You: Hello there")


class StubTranscriber:
    def __init__(self, outputs):
        self.outputs = outputs

    def transcribe(self, audio_path):
        return [Segment(0, 1, self.outputs[audio_path.name])]


def test_evaluate_and_compare(tmp_path: Path):
    manifest = tmp_path / "m.jsonl"
    rows = [
        {"audio": "a.wav", "reference": "one two three", "tag": "clean"},
        {"audio": "b.wav", "reference": "four five six", "tag": "noisy"},
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    items = load_manifest(manifest)
    assert items[0] == Item(tmp_path / "a.wav", "one two three", "clean")

    good = evaluate(items, StubTranscriber({"a.wav": "one two three", "b.wav": "four five six"}), "v1")
    worse = evaluate(items, StubTranscriber({"a.wav": "one two three", "b.wav": "four nine six"}), "v2")
    assert good["wer"] == 0 and good["wer_by_tag"] == {"clean": 0, "noisy": 0}
    ok, lines = compare(good, worse)
    assert not ok and any("noisy" in line and "REGRESSION" in line for line in lines)
    assert compare(good, good)[0]


def test_cli_compare_exit_code(tmp_path: Path):
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps({"wer": 0.10, "wer_by_tag": {"all": 0.10}}))
    new.write_text(json.dumps({"wer": 0.20, "wer_by_tag": {"all": 0.20}}))
    assert main(["compare", str(old), str(new)]) == 1
    assert main(["compare", str(old), str(old)]) == 0


def test_cli_tier_runs(capsys):
    assert main(["tier"]) == 0
    assert "Tier:" in capsys.readouterr().out
