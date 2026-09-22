"""Peel staffing curves into practical shift intervals with coverage proof."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .policy import POLICY_BREAK_THRESHOLD_MINUTES, POLICY_DEFAULT_BREAK_MINUTES


def peel_layers(curve: list[int]) -> list[tuple[int, int, int]]:
    intervals: list[tuple[int, int, int]] = []
    for layer in range(1, max(curve or [0]) + 1):
        start = None
        for index in range(len(curve) + 1):
            active = index < len(curve) and curve[index] >= layer
            if active and start is None:
                start = index
            elif not active and start is not None:
                intervals.append((layer, start, index))
                start = None
    return intervals


def fit_interval(
    start: int, end: int, *, n: int, min_slots: int, max_slots: int, layer: int,
) -> tuple[list[tuple[int, int]], int, int]:
    length = end - start
    if min_slots <= length <= max_slots:
        return [(start, end)], 0, 0
    if length > max_slots:
        pieces = ceil(length / max_slots)
        if pieces > 1 and length // pieces < min_slots:
            out = [(start + i * max_slots, min(end, start + (i + 1) * max_slots)) for i in range(pieces - 1)]
            out.append((max(start, end - max_slots), end))
            return out, sum(b - a for a, b in out) - length, 0
        base, extra = divmod(length, pieces)
        sizes = [base + (1 if i < extra else 0) for i in range(pieces)]
        if layer % 2 == 0:
            sizes.reverse()
        out, cursor = [], start
        for size in sizes:
            out.append((cursor, cursor + size))
            cursor += size
        return out, 0, 0
    if n < min_slots:
        return ([(0, n)], n - length, 0) if n >= 4 else ([], 0, length)
    needed = min_slots - length
    add_end = min(needed, n - end)
    end += add_end
    start -= min(needed - add_end, start)
    return [(start, end)], needed, 0


@dataclass(frozen=True)
class CutResult:
    intervals: list[tuple[int, int]]
    over_coverage: int
    dropped: int
    notes: tuple[str, ...]


def cut_shifts(curve: list[int], *, min_slots: int, max_slots: int) -> CutResult:
    intervals: list[tuple[int, int]] = []
    over = dropped = 0
    for layer, start, end in peel_layers(curve):
        fitted, extra, lost = fit_interval(
            start, end, n=len(curve), min_slots=min_slots, max_slots=max_slots, layer=layer,
        )
        intervals.extend(fitted)
        over += extra
        dropped += lost
    coverage = [0] * len(curve)
    for start, end in intervals:
        for index in range(start, end):
            coverage[index] += 1
    uncovered = sum(max(0, need - have) for have, need in zip(coverage, curve))
    assert uncovered == dropped, "shift cutting lost required coverage"
    notes = []
    if over:
        notes.append(f"minimum/maximum shift bounds add {over * 30} minutes of coverage")
    if dropped:
        notes.append(f"{dropped * 30} minutes in a sub-two-hour window could not form a shift")
    return CutResult(intervals, over, dropped, tuple(notes))


def break_minutes_for(span_minutes: int) -> int:
    return POLICY_DEFAULT_BREAK_MINUTES if span_minutes >= POLICY_BREAK_THRESHOLD_MINUTES else 0
