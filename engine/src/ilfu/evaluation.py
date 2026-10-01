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


def compare(old: dict, new: dict, max_regression: float = 0.005) -> tuple[bool, list[str]]:
    """Back-to-back comparison. Fails if overall or any tag's WER worsens by more than the limit.

    The limit is a placeholder until we know run-to-run noise on the real benchmark.
    """
    lines, ok = [], True
    rows = [("all", old["wer"], new["wer"])]
    rows += [(t, w, new["wer_by_tag"][t]) for t, w in old["wer_by_tag"].items() if t in new["wer_by_tag"]]
    for tag, before, after in rows:
        worse = after - before > max_regression
        ok = ok and not worse
        lines.append(f"{tag}: {before:.3f} -> {after:.3f} {'REGRESSION' if worse else 'ok'}")
    return ok, lines
