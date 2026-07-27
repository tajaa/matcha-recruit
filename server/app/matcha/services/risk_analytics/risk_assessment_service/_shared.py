"""Result dataclasses + the small pure helpers every dimension and cost function
shares: exposure sourcing stamps, the exempt-threshold sentence, and the
score->band mapping.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ._config import _UNSOURCED_REASONS
logger = logging.getLogger(__name__)


def _stamp_sourcing(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Label every exposure line with whether its figures trace to a statute.

    Applied at each return rather than in each dict so a new line item cannot
    ship silently unlabelled — an unknown key defaults to unsourced with a
    generic reason, which is the safe direction: a figure is guilty until it can
    show its authority.

    Mutates in place and returns for chaining.
    """
    for item in line_items:
        item.setdefault("sourced", False)
        if not item["sourced"]:
            item.setdefault(
                "unsourced_reason",
                _UNSOURCED_REASONS.get(
                    item.get("key", ""),
                    "Figures are hand-entered estimates; no statute is bound.",
                ),
            )
    return line_items


def _exempt_threshold_sentence(exempt: list[dict[str, Any]]) -> str:
    """Name the exemption thresholds these violations were measured against.

    Pure, so it is testable without a DB. Reads the `threshold` already carried
    on each violation (compliance_service resolved it from the catalog row for
    that employee's work location) rather than restating a literal that drifts:
    the copy this replaced still said $43,888 while the catalog it was
    implicitly describing said $70,304 for California.

    Silent when no threshold is present — better to say nothing than to name a
    number we did not actually compare against.
    """
    by_state: dict[str, float] = {}
    for v in exempt:
        threshold = v.get("threshold")
        if not threshold:
            continue
        state = (v.get("location_state") or "").strip() or "applicable jurisdiction"
        # Keep the highest per state: a state with several rows (city overlays)
        # is best described by the bar these employees actually had to clear.
        by_state[state] = max(by_state.get(state, 0.0), float(threshold))
    if not by_state:
        return "Each employee is measured against the salary threshold for their work location."
    named = ", ".join(f"{s}: ${t:,.0f}" for s, t in sorted(by_state.items()))
    return (
        "Measured against the salary threshold in force for each employee's work "
        f"location ({named})."
    )


def _band(score: int) -> str:
    if score <= 25:
        return "low"
    elif score <= 50:
        return "moderate"
    elif score <= 75:
        return "high"
    else:
        return "critical"


@dataclass
class DimensionResult:
    score: int
    band: str
    factors: list[str]
    raw_data: dict[str, Any]


@dataclass
class RiskAssessmentResult:
    overall_score: int
    overall_band: str
    dimensions: dict[str, DimensionResult]
    computed_at: datetime
