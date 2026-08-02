"""Deterministic reorder-quantity suggestion from movement history. No
Gemini, no DB — pure over an already-fetched movement list, chronological
(oldest first)."""

import math
from datetime import datetime

from app.matcha.services.pilots.analysis_packs.base import coefficient_of_variation, mean

DEFAULT_COVER_DAYS = 14
LOOKBACK_DAYS = 90


def suggest_order(movements: list[dict], now: datetime) -> dict | None:
    """movements: chronological dicts with keys {kind, quantity,
    quantity_delta, created_at}. Returns None when history is too thin to
    say anything useful (fewer than 2 'out' movements AND no prior 'in'
    receipt) — never guesses from nothing.

    daily_rate: sum of 'out' quantity magnitudes within LOOKBACK_DAYS,
    divided by the number of days actually observed (oldest-in-window to
    now, floored at 1 to avoid a same-day divide-by-zero).

    suggested_quantity: ceil(daily_rate * DEFAULT_COVER_DAYS) when a rate
    exists; else falls back to the most recent 'in' receipt quantity; else
    None (caller must still stage the order — with no history to price it
    from — but the pill says so explicitly).
    """
    cutoff = now.timestamp() - LOOKBACK_DAYS * 86400
    in_window = [m for m in movements if m["created_at"].timestamp() >= cutoff]

    outs = [m for m in in_window if m["kind"] == "out" and m["quantity"] is not None]
    stockouts = [m for m in in_window if m["kind"] == "stockout"]
    receipts = [m for m in in_window if m["kind"] == "in" and m["quantity"] is not None]

    n_out = len(outs)
    if n_out < 2 and not receipts:
        return None

    daily_rate = None
    if outs:
        earliest = min(m["created_at"] for m in outs)
        observed_days = max(1.0, (now - earliest).total_seconds() / 86400)
        daily_rate = sum(float(m["quantity"]) for m in outs) / observed_days

    stockout_intervals = []
    sorted_stockouts = sorted(stockouts, key=lambda m: m["created_at"])
    for prev, curr in zip(sorted_stockouts, sorted_stockouts[1:]):
        stockout_intervals.append((curr["created_at"] - prev["created_at"]).total_seconds() / 86400)
    avg_stockout_interval = mean(stockout_intervals) if stockout_intervals else None

    if daily_rate is not None and daily_rate > 0:
        suggested_quantity = math.ceil(daily_rate * DEFAULT_COVER_DAYS)
    elif receipts:
        last_receipt = max(receipts, key=lambda m: m["created_at"])
        suggested_quantity = float(last_receipt["quantity"])
    else:
        suggested_quantity = None

    cv = coefficient_of_variation(stockout_intervals) if len(stockout_intervals) >= 2 else None
    n_samples = n_out + len(stockouts)
    if n_samples >= 8 and (cv is None or cv < 0.5):
        confidence = "high"
    elif n_samples >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "suggested_quantity": suggested_quantity,
        "daily_rate": daily_rate,
        "avg_stockout_interval_days": avg_stockout_interval,
        "cover_days": DEFAULT_COVER_DAYS,
        "confidence": confidence,
        "n_samples": n_samples,
    }
