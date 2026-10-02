"""Accuracy and speed benchmark on FLEURS (CC BY 4.0), a public read-speech set with English,
Hindi and Telugu. Clips are picked by a fixed rule, and their hashes are checked against the
committed list, so every version of the app is measured on exactly the same audio.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import time
import struct
from pathlib import Path

from .evaluation import Item
from .transcribe import Transcriber
from .wer import corpus_wer

REPO = "google/fleurs"
# our short tag -> FLEURS config name and the language code Whisper is told to use
LANGUAGES = {
    "en": ("en_us", "en"),
    "hi": ("hi_in", "hi"),
    "te": ("te_in", "te"),
}


def pick(rows: list[tuple[str, str]], count: int) -> list[tuple[str, str]]:
    """Choose `count` clips by a fixed rule: sort by file name, then take evenly spaced ones."""
    rows = sorted(set(rows))
    if count >= len(rows):
        return rows
    step = len(rows) / count
    return [rows[int(i * step)] for i in range(count)]


def read_tsv(path: Path) -> list[tuple[str, str]]:
    """(file name, normalized transcription) from a FLEURS tsv (no header, tab separated)."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[1] and parts[3].strip():
            rows.append((parts[1], parts[3].strip()))
    return rows


def extract(archive: Path, wanted: set[str], out: Path) -> dict[str, Path]:
    """Pull only the wanted wav files out of the (large) archive."""
    out.mkdir(parents=True, exist_ok=True)
    found: dict[str, Path] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = Path(member.name).name
            if member.isfile() and name in wanted:
                target = out / name
                with tar.extractfile(member) as src, target.open("wb") as dst:  # type: ignore[union-attr]
                    dst.write(src.read())
                found[name] = target
                if len(found) == len(wanted):
                    break
    return found


def download(tag: str, workdir: Path, count: int, fetch=None) -> list[Item]:
    """Fetch (or reuse) the frozen clips for one language."""
    config, _ = LANGUAGES[tag]
    if fetch is None:
        from huggingface_hub import hf_hub_download

        def fetch(filename: str) -> Path:
            return Path(hf_hub_download(REPO, filename, repo_type="dataset"))

    rows = pick(read_tsv(fetch(f"data/{config}/test.tsv")), count)
    wanted = {name for name, _ in rows}
    audio_dir = workdir / config
    have = {p.name: p for p in audio_dir.glob("*.wav")} if audio_dir.exists() else {}
    if not wanted <= have.keys():
        have = extract(fetch(f"data/{config}/audio/test.tar.gz"), wanted, audio_dir)
    missing = wanted - have.keys()
    if missing:
        raise RuntimeError(f"{config}: {len(missing)} clips missing from the archive")
    return [Item(have[name], text, tag) for name, text in rows]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_check(items: list[Item], frozen_path: Path) -> tuple[dict[str, str], list[str]]:
    """Compare the clips with the committed hash list. Returns (current hashes, problems)."""
    current = {f"{i.tag}/{i.audio.name}": sha256(i.audio) for i in items}
    problems: list[str] = []
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        for key, digest in current.items():
            if key not in frozen:
                problems.append(f"{key}: not in the frozen list")
            elif frozen[key] != digest:
                problems.append(f"{key}: audio changed")
        problems += [f"{key}: missing" for key in frozen if key not in current]
    return current, problems


def _seconds(path: Path) -> float:
    """Clip length from the RIFF header. Works for float WAVs, which `wave` refuses."""
    data = path.read_bytes()
    pos, rate, frame_bytes = 12, 0, 0
    while pos + 8 <= len(data):
        tag, size = struct.unpack("<4sI", data[pos : pos + 8])
        if tag == b"fmt ":
            _fmt, channels, rate, _br, _al, bits = struct.unpack("<HHIIHH", data[pos + 8 : pos + 24])
            frame_bytes = channels * bits // 8
        elif tag == b"data":
            size = min(size, len(data) - pos - 8)
            return size / frame_bytes / rate if frame_bytes and rate else 0.0
        pos += 8 + size + (size & 1)
    return 0.0


def run(items: list[Item], transcriber: Transcriber, model: str) -> dict:
    """Transcribe every clip, per language, and report WER and speed."""
    by_tag: dict[str, list[Item]] = {}
    for item in items:
        by_tag.setdefault(item.tag, []).append(item)
    pairs_all: list[tuple[str, str]] = []
    wer_by_tag: dict[str, float] = {}
    audio_seconds = work_seconds = 0.0
    for tag, group in sorted(by_tag.items()):
        transcriber.language = LANGUAGES[tag][1]  # type: ignore[attr-defined]
        pairs = []
        for item in group:
            started = time.perf_counter()
            text = " ".join(s.text for s in transcriber.transcribe(item.audio))
            work_seconds += time.perf_counter() - started
            audio_seconds += _seconds(item.audio)
            pairs.append((item.reference, text))
        wer_by_tag[tag] = corpus_wer(pairs).wer
        pairs_all += pairs
    report = {
        "label": model,
        "clips": len(items),
        "wer": corpus_wer(pairs_all).wer,
        "wer_by_tag": wer_by_tag,
        "audio_seconds": round(audio_seconds, 1),
        "seconds_to_transcribe": round(work_seconds, 1),
        # below 1.0 means faster than real time, which live captions need
        "real_time_factor": round(work_seconds / audio_seconds, 3) if audio_seconds else None,
        "cpus": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count(),
    }
    try:
        import resource

        report["peak_memory_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except ImportError:
        pass
    return report


def to_markdown(report: dict) -> str:
    lines = [
        f"### {report['label']} ({report['clips']} clips, {report['cpus']} CPU)",
        "",
        "| Language | Word error rate |",
        "| --- | --- |",
    ]
    names = {"en": "English", "hi": "Hindi", "te": "Telugu"}
    for tag, value in report["wer_by_tag"].items():
        lines.append(f"| {names.get(tag, tag)} | {value:.1%} |")
    lines.append(f"| **All** | **{report['wer']:.1%}** |")
    lines += [
        "",
        (
            f"Speed: {report['real_time_factor']} seconds of work per second of audio "
            f"(under 1.0 keeps up with live captions). "
            f"Peak memory: {report.get('peak_memory_mb', '?')} MB."
        ),
        "",
    ]
    return "\n".join(lines)
