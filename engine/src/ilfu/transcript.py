"""Transcript data and export formats."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


def _stamp(seconds: float, sep: str = ",") -> str:
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _line(seg: Segment) -> str:
    return f"{seg.speaker}: {seg.text}" if seg.speaker else seg.text


def to_text(segments: list[Segment]) -> str:
    return "\n".join(_line(s) for s in segments) + "\n"


def to_markdown(segments: list[Segment]) -> str:
    return "\n\n".join(f"**[{_stamp(s.start, '.')[:8]}]** {_line(s)}" for s in segments) + "\n"


def to_srt(segments: list[Segment]) -> str:
    blocks = [
        f"{i}\n{_stamp(s.start)} --> {_stamp(s.end)}\n{_line(s)}\n"
        for i, s in enumerate(segments, 1)
    ]
    return "\n".join(blocks)


FORMATS = {"txt": to_text, "md": to_markdown, "srt": to_srt}
