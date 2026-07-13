"""Subscore math + the onboarding-readiness gate. Pure functions, no I/O.

Design rule that everything else follows: **unmeasured is not the same as
perfect**. A jurisdiction with no golden facts has `accuracy = None`, not 100,
and can never reach READY. The whole point of the eval system is to stop the
catalog from looking authoritative merely because nothing has checked it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Onboarding-readiness thresholds ────────────────────────────────────────────
MIN_COMPLETENESS_READY = 90.0
MIN_COMPLETENESS_DEGRADED = 75.0
MIN_ACCURACY_READY = 95.0
MIN_AUTHORITY_READY = 70.0
MIN_FRESHNESS_READY = 80.0
MIN_GOLDEN_FACTS_READY = 10

# Authority: credit per citation class.
AUTHORITY_WEIGHTS: Dict[str, float] = {
    "primary": 1.0,
    "secondary_official": 0.7,
    "aggregator": 0.3,
    "unknown": 0.1,
    "dead": 0.0,
    "missing": 0.0,
}

# A structural industry-tag miss on a focused category means the row is served to
# every company regardless of industry. No amount of clean key naming redeems it.
TAGGING_STRUCTURAL_CAP = 50.0

READY = "READY"
DEGRADED = "DEGRADED"
NOT_READY = "NOT_READY"


@dataclass
class Subscores:
    completeness: Optional[float] = None
    accuracy: Optional[float] = None
    authority: Optional[float] = None
    freshness: Optional[float] = None
    tagging: Optional[float] = None
    scope: Optional[float] = None

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "authority": self.authority,
            "freshness": self.freshness,
            "tagging": self.tagging,
            "scope": self.scope,
        }


@dataclass
class Readiness:
    status: str
    subscores: Subscores
    blocking: List[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == READY


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 2)


def completeness_score(
    present_keys: Dict[str, set],
    expected: Dict[str, set],
    weights: Dict[str, float],
) -> float:
    """Weighted fraction of expected keys present.

    `weights` maps category → 0..1 importance; absent categories weigh 1.0 so an
    unprofiled category is never silently discounted.
    """
    total = 0.0
    got = 0.0
    for cat, keys in expected.items():
        w = weights.get(cat, 1.0)
        have = present_keys.get(cat, set())
        total += w * len(keys)
        got += w * len(keys & have)
    return _pct(got, total)


def missing_keys(
    present_keys: Dict[str, set], expected: Dict[str, set]
) -> Dict[str, List[str]]:
    """Expected-but-absent keys per category, omitting fully covered categories."""
    out: Dict[str, List[str]] = {}
    for cat, keys in expected.items():
        gap = keys - present_keys.get(cat, set())
        if gap:
            out[cat] = sorted(gap)
    return out


def authority_score(class_counts: Dict[str, int]) -> Optional[float]:
    """Weighted citation quality over classified rows. None when there are none."""
    total = sum(class_counts.values())
    if total == 0:
        return None
    earned = sum(AUTHORITY_WEIGHTS.get(k, 0.0) * n for k, n in class_counts.items())
    return _pct(earned, float(total))


def accuracy_score(passed: int, failed: int, critical_failures: int = 0) -> Optional[float]:
    """Golden-fact pass rate. A single critical failure zeroes the cell.

    Rationale: a critical golden fact is something like "CA state minimum wage".
    If the catalog has it wrong, every downstream number the customer sees is
    suspect — averaging that away against 40 passing facts would launder it.
    """
    total = passed + failed
    if total == 0:
        return None
    if critical_failures > 0:
        return 0.0
    return _pct(passed, total)


def freshness_score(within_sla: int, total: int) -> Optional[float]:
    if total == 0:
        return None
    return _pct(within_sla, total)


def tagging_score(
    total_rows: int,
    structural_violations: int,
    integrity_violations: int,
    label_precision: Optional[float] = None,
    label_recall: Optional[float] = None,
) -> Optional[float]:
    """Organization quality: structural tag misses + key/category integrity + labels.

    Structural violations (an industry-specific row with no industry tag) cap the
    score, because that row leaks to every tenant no matter how tidy the rest is.
    """
    if total_rows == 0:
        return None

    violations = structural_violations + integrity_violations
    base = _pct(max(total_rows - violations, 0), total_rows)

    if label_precision is not None and label_recall is not None:
        if label_precision + label_recall > 0:
            f1 = 2 * label_precision * label_recall / (label_precision + label_recall)
        else:
            f1 = 0.0
        base = round(0.6 * base + 0.4 * (100.0 * f1), 2)

    if structural_violations > 0:
        base = min(base, TAGGING_STRUCTURAL_CAP)
    return base


def grounding_score(verified: int, contradicted: int) -> Optional[float]:
    """Fraction of judgeable grounded values that actually appear in their cited
    text. None when nothing was judgeable (all stubs / prose) — unmeasured is not
    100, same rule as every other subscore. Stubs and prose don't enter the
    denominator; they surface as findings, not a laundered pass.
    """
    total = verified + contradicted
    if total == 0:
        return None
    return _pct(verified, total)


def baseline_score(present: int, missing: int) -> Optional[float]:
    """Fraction of the enumerated labor master-list present in a base jurisdiction's
    own catalog. None when the master-list is empty (nothing to measure) — unmeasured
    is not 100, same rule as every other subscore. Not folded into the composite: a
    baseline miss gates through its critical finding, like grounding."""
    total = present + missing
    if total == 0:
        return None
    return _pct(present, total)


def scope_score(
    item_count: int, unclassified: int, without_value: int,
) -> Optional[float]:
    """Fraction of an authority index's items that are fully resolved: confirmed-
    classified AND either excluded or backed by a codified catalog value.

    ``unclassified`` already means "no CONFIRMED classification" (classify.py's
    _refresh_unclassified_count), so provisional work counts against this — the
    registry is only authoritative for what a human confirmed. None when the
    index is empty: unmeasured is not 100, same rule as every other subscore.
    """
    if item_count <= 0:
        return None
    resolved = max(0, item_count - unclassified - without_value)
    return _pct(resolved, item_count)


def composite_score(s: Subscores) -> Optional[float]:
    """Mean of the measured subscores. None if nothing was measured."""
    vals = [v for v in s.as_dict().values() if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def evaluate_readiness(
    s: Subscores,
    *,
    focused_keys_complete: bool,
    open_critical_findings: int,
    golden_fact_count: int,
) -> Readiness:
    """The gate: can a company in this industry onboard into this jurisdiction?"""
    blocking: List[str] = []

    comp = s.completeness if s.completeness is not None else 0.0
    if comp < MIN_COMPLETENESS_READY:
        blocking.append(f"completeness {comp:.0f} < {MIN_COMPLETENESS_READY:.0f}")
    if not focused_keys_complete:
        blocking.append("missing keys in industry-critical categories")
    if open_critical_findings:
        blocking.append(f"{open_critical_findings} open critical finding(s)")

    if s.accuracy is None or golden_fact_count < MIN_GOLDEN_FACTS_READY:
        blocking.append(
            f"accuracy unverified ({golden_fact_count}/{MIN_GOLDEN_FACTS_READY} golden facts)"
        )
    elif s.accuracy < MIN_ACCURACY_READY:
        blocking.append(f"accuracy {s.accuracy:.0f} < {MIN_ACCURACY_READY:.0f}")

    if s.authority is not None and s.authority < MIN_AUTHORITY_READY:
        blocking.append(f"authority {s.authority:.0f} < {MIN_AUTHORITY_READY:.0f}")
    if s.freshness is not None and s.freshness < MIN_FRESHNESS_READY:
        blocking.append(f"freshness {s.freshness:.0f} < {MIN_FRESHNESS_READY:.0f}")

    if not blocking:
        return Readiness(READY, s, [])

    accuracy_blocked = s.accuracy is not None and s.accuracy == 0.0
    if comp >= MIN_COMPLETENESS_DEGRADED and not accuracy_blocked:
        return Readiness(DEGRADED, s, blocking)
    return Readiness(NOT_READY, s, blocking)
