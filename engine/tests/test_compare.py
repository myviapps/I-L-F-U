import json
from pathlib import Path

import pytest

from ilfu.cli import main
from ilfu.evaluation import compare, load_report

BENCHMARK = Path(__file__).resolve().parents[2] / "benchmark"


def _report(en, hi, te, rtf=0.3):
    wer_by_tag = {"en": en, "hi": hi, "te": te}
    return {"label": "base", "clips": 75, "wer_by_tag": wer_by_tag, "real_time_factor": rtf}


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("model", ["base", "small"])
def test_committed_summary_baselines_load(model):
    baseline = load_report(BENCHMARK / f"baseline-{model}.json")
    assert set(baseline["wer_by_tag"]) == {"en", "hi", "te"}
    assert baseline["clips"] == 75 and "36961087768" in baseline["source"]
    assert "wer" not in baseline  # only the per-language numbers we measured, nothing made up
    assert compare(baseline, baseline)[0]


def test_noise_within_tolerance_passes():
    # the documented noise: two identical base runs, Hindi 106.4% and 107.4%
    ok, lines = compare(_report(0.088, 1.064, 1.343), _report(0.090, 1.074, 1.343, rtf=0.9))
    assert ok and not any("REGRESSION" in line for line in lines)
    assert any("speed" in line and "not checked" in line for line in lines)  # speed never fails


def test_regression_beyond_tolerance_fails_with_clear_message():
    ok, lines = compare(_report(0.068, 0.549, 1.182), _report(0.068, 0.600, 1.182))
    assert not ok
    hindi = [line for line in lines if line.startswith("hi:")]
    assert hindi and "REGRESSION" in hindi[0] and "+5.1 points" in hindi[0]
    assert lines[-1].startswith("FAILED") and "hi" in lines[-1]


@pytest.mark.parametrize(("before", "after"), [(0.549, 0.569), (1.064, 1.084), (0.088, 0.108)])
def test_exactly_the_limit_passes_and_just_over_fails(before, after):
    # float rounding must not decide the verdict at the documented limit ("more than 2 points")
    assert compare(_report(0.1, before, 1.0), _report(0.1, after, 1.0))[0]
    assert not compare(_report(0.1, before, 1.0), _report(0.1, after + 0.0001, 1.0))[0]


def test_improvement_passes():
    assert compare(_report(0.088, 1.064, 1.343), _report(0.05, 0.6, 1.0))[0]


def test_missing_language_fails_and_new_language_is_listed():
    old = _report(0.088, 1.064, 1.343)
    new = {"wer": 0.1, "wer_by_tag": {"en": 0.088, "hi": 1.064, "ta": 0.5}}
    ok, lines = compare(old, new)
    assert not ok
    assert any(line.startswith("te:") and "MISSING" in line for line in lines)
    assert any(line.startswith("ta:") and "no baseline" in line for line in lines)


def test_cli_tolerance_option(tmp_path):
    old = _write(tmp_path, "old.json", _report(0.068, 0.549, 1.182))
    new = _write(tmp_path, "new.json", _report(0.068, 0.579, 1.182))  # +3 points on Hindi
    assert main(["compare", str(old), str(new)]) == 1
    assert main(["compare", str(old), str(new), "--tolerance", "5"]) == 0
    assert main(["compare", str(old), str(new), "--max-regression", "0.05"]) == 0


def test_cli_full_report_against_summary_baseline(tmp_path, capsys):
    full = _report(0.07, 0.55, 1.18, rtf=2.5) | {"wer": 0.6, "samples": {}, "cpus": 2}
    new = _write(tmp_path, "report-small.json", full)
    assert main(["compare", str(BENCHMARK / "baseline-small.json"), str(new)]) == 0
    assert "speed: 2.18 -> 2.5" in capsys.readouterr().out


def test_cli_rejects_a_file_that_is_not_a_report(tmp_path):
    bad = _write(tmp_path, "bad.json", {"hello": 1})
    assert main(["compare", str(bad), str(bad)]) == 2
