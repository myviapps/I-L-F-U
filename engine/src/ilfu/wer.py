"""Word error rate, the main accuracy number we track."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)


def normalize(text: str) -> list[str]:
    """Lowercase, drop punctuation, split into words.

    This is a simple normalizer. Before publishing results we will switch to the Whisper
    normalizer so numbers 'ten' and '10' compare fairly, and say so in the results.
    """
    return _PUNCT.sub(" ", text.lower()).split()


@dataclass(frozen=True)
class WerResult:
    errors: int
    ref_words: int

    @property
    def wer(self) -> float:
        return self.errors / self.ref_words if self.ref_words else float(self.errors > 0)


def word_errors(reference: str, hypothesis: str) -> WerResult:
    ref, hyp = normalize(reference), normalize(hypothesis)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return WerResult(errors=prev[-1], ref_words=len(ref))


def corpus_wer(pairs: list[tuple[str, str]]) -> WerResult:
    """WER over many (reference, hypothesis) pairs, weighted by reference length."""
    results = [word_errors(r, h) for r, h in pairs]
    return WerResult(sum(r.errors for r in results), sum(r.ref_words for r in results))
