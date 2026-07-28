"""Scoring point values and caps, the exposure-sourcing reason vocabulary, the
Gemini fallback-model list, and the default dimension weights. Leaf.
"""
import logging

logger = logging.getLogger(__name__)


COMPLIANCE_CRITICAL_ALERT_POINTS = 35


COMPLIANCE_CRITICAL_ALERT_CAP = 70


COMPLIANCE_WARNING_ALERT_POINTS = 15


COMPLIANCE_WARNING_ALERT_CAP = 30


COMPLIANCE_WAGE_VIOLATION_POINTS = 10


COMPLIANCE_WAGE_VIOLATION_CAP = 80


COMPLIANCE_WAGE_LOCATION_POINTS = 5


COMPLIANCE_WAGE_LOCATION_CAP = 20


ER_PENDING_POINTS = 15


ER_PENDING_CAP = 60


ER_IN_REVIEW_POINTS = 10


ER_IN_REVIEW_CAP = 20


ER_OPEN_POINTS = 5


ER_OPEN_CAP = 25


ER_MAJOR_POLICY_POINTS = 10


ER_HIGH_DISCREPANCY_POINTS = 5


# Where each exposure line's DOLLAR FIGURES come from.
#
# `sourced` means one thing only: the amounts trace to a statute we ingested and
# can link (see core/services/penalty_facts.py — bound via penalty_item_id to an
# authority_index_items row). Today NOTHING on this page clears that bar, and
# saying so is the point: the compliance cockpit can now cite 29 CFR 1903.15(d)(3)
# for its $16,550, while these figures are constants someone typed. That gap was
# invisible, which is how "$43,888" sat two years stale in a string a customer
# was asked to act on.
#
# A line flips to sourced when its authority is ingested and parsed — HIPAA's is
# 45 CFR 102.3, reachable today, blocked only on a <TABLE> parser.
_UNSOURCED_REASONS: dict[str, str] = {
    "hourly_wage_shortfall":
        "Shortfall is measured against this location's actual minimum-wage row; the "
        "lookback and liquidated-damages multipliers are FLSA § 216(b) structure, "
        "not adjusted figures. The statute is not yet ingested, so nothing links.",
    "exempt_misclassification":
        "Salary threshold comes from this location's catalog row; the OT and "
        "damages multipliers are FLSA § 207 structure. The statute is not yet "
        "ingested, so nothing links.",
    "hipaa_breach_exposure":
        "Per-record amounts and the tier figures are hand-entered. Authority is "
        "45 CFR 102.3 (Table 1), reachable but not yet parsed.",
    "lapsed_credential_risk":
        "Per-credential range is a hand-entered estimate spanning many state boards; "
        "no single authority states it.",
    "pending_determination": "EEOC merit rate and settlement range are hand-entered estimates.",
    "in_review": "EEOC merit rate and settlement range are hand-entered estimates.",
    "open_cases": "EEOC merit rate and settlement range are hand-entered estimates.",
    "critical_incidents": "Per-incident range is a hand-entered estimate.",
    "high_incidents": "Per-incident range is a hand-entered estimate.",
    "medium_incidents": "Per-incident range is a hand-entered estimate.",
}


FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]


DEFAULT_WEIGHTS: dict[str, float] = {
    "compliance": 0.30,
    "incidents": 0.25,
    "er_cases": 0.25,
    "workforce": 0.15,
    "legislative": 0.05,
}


_WEIGHT_KEYS = set(DEFAULT_WEIGHTS)
