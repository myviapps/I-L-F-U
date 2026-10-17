"""Benchmark runner: manifest in, WER report out, comparison against a previous report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .transcribe import Transcriber
from .wer import corpus_wer


@dataclass(frozen=True)
class Item:
    audio: Path
    reference: str
    tag: str = "all"


def load_manifest(path: Path) -> list[Item]:
    """JSON lines, one per clip: {"audio": "a.wav", "reference": "text", "tag": "accent-x"}."""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items.append(Item(path.parent / row["audio"], row["reference"], row.get("tag", "all")))
    return items


def evaluate(items: list[Item], transcriber: Transcriber, label: str) -> dict:
    pairs: dict[str, list[tuple[str, str]]] = {}
    for item in items:
        hyp = " ".join(s.text for s in transcriber.transcribe(item.audio))
        pairs.setdefault(item.tag, []).append((item.reference, hyp))
    all_pairs = [p for group in pairs.values() for p in group]
    return {
        "label": label,
        "clips": len(all_pairs),
        "wer": corpus_wer(all_pairs).wer,
        "wer_by_tag": {tag: corpus_wer(group).wer for tag, group in sorted(pairs.items())},
    }


# Two identical base runs on the 25 frozen clips per language gave Hindi 107.4% and 106.4%
# (docs/BENCHMARKS.md), so a gap of a point or so is noise. Two points leaves some room.
DEFAULT_TOLERANCE = 0.02


def load_report(path: Path) -> dict:
    """A full report from `ilfu benchmark`/`ilfu eval`, or a summary baseline with only
    per-language WER (`wer_by_tag`) and notes on where the numbers came from."""
    report = json.loads(path.read_text(encoding="utf-8"))
    wer_by_tag = report.get("wer_by_tag") if isinstance(report, dict) else None
    if not isinstance(wer_by_tag, dict):
        raise TypeError(f"{path}: not a report, it has no 'wer_by_tag'")
    return report


def compare(
    old: dict, new: dict, max_regression: float = DEFAULT_TOLERANCE
) -> tuple[bool, list[str]]:
    """Compare a new report with a baseline. Fails if overall or any language's WER worsens by
    more than `max_regression` (a fraction: 0.02 is two points), or if a baseline language is
    missing from the new report. Speed is printed but never fails: shared runners vary.
    """
    lines, failed = [], []
    rows = []
    if "wer" in old and "wer" in new:  # summary baselines have no overall number
        rows.append(("all", old["wer"], new["wer"]))
    for tag, before in old["wer_by_tag"].items():
        if tag not in new["wer_by_tag"]:
            failed.append(tag)
            lines.append(f"{tag}: {before:.1%} -> missing from the new report MISSING")
            continue
        rows.append((tag, before, new["wer_by_tag"][tag]))
    for tag, before, after in rows:
        # Compare in rounded points so a change of exactly the limit passes whatever the
        # float rounding (0.549 -> 0.569 and 1.064 -> 1.084 are both +2.0 points).
        worse = round((after - before) * 100, 6) > round(max_regression * 100, 6)
        if worse:
            failed.append(tag)
        change = (after - before) * 100
        verdict = "REGRESSION" if worse else "ok"
        lines.append(f"{tag}: {before:.1%} -> {after:.1%} ({change:+.1f} points) {verdict}")
    for tag, after in new["wer_by_tag"].items():
        if tag not in old["wer_by_tag"]:
            lines.append(f"{tag}: new, no baseline {after:.1%}")
    if old.get("real_time_factor") and new.get("real_time_factor"):
        lines.append(
            f"speed: {old['real_time_factor']} -> {new['real_time_factor']} seconds of work "
            "per second of audio (not checked, shared runners vary)"
        )
    if old.get("clips") and new.get("clips") and old["clips"] != new["clips"]:
        lines.append(f"note: baseline has {old['clips']} clips, new report {new['clips']}")
    if failed:
        lines.append(
            f"FAILED: worse than the baseline by more than {max_regression * 100:.1f} points, "
            f"or missing: {', '.join(failed)}"
        )
    return not failed, lines
