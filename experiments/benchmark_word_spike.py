#!/usr/bin/env python3
"""Repeatable local latency probe for the non-production Word prototype."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.games.word_spike import BoundedLexicon, WordEntry, evaluate_word


def main() -> None:
    lexicon = BoundedLexicon(
        [WordEntry(f"کتاب{suffix}", "noun", rank) for rank, suffix in enumerate("ابتثج")]
    )
    samples: list[float] = []
    iterations = 100_000
    for _ in range(iterations):
        started = time.perf_counter_ns()
        evaluate_word("کتاب", "کباب")
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    # Keep construction visible so accidental import-time data loading is caught.
    assert lexicon is not None
    ordered = sorted(samples)
    p95 = ordered[int(iterations * 0.95) - 1]
    print(
        f"iterations={iterations} median_ms={statistics.median(samples):.6f} "
        f"p95_ms={p95:.6f} max_ms={max(samples):.6f}"
    )


if __name__ == "__main__":
    main()
