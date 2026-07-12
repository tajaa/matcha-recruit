"""Curated U.S. federal labor authority — the statutes behind the baseline.

The federal labor baseline (`compliance_evals/baseline_masterlist.py`) enumerates the
obligations a general employer owes. Most of them live in statutes with **no
machine-readable index**: Title VII, ADA, ADEA, WARN, IRCA/I-9, COBRA, ERISA, NLRA,
USERRA, FCRA, EEO-1, the CCPA garnishment cap. Only OSHA (29 CFR 1910/1904), FMLA
(29 CFR 825) and the FLSA slice are ingested today, so those obligations had no
authority item to classify — and therefore nothing to **codify** against.

This module supplies that missing ingest side. Rows are **derived from the
master-list** (single source of truth for citation + primary-source URL) rather than
re-typed, so the two can't drift: the obligation the baseline eval scores and the
authority item it binds to carry the same citation by construction.

Same doctrine as ``curated_ca``: hand-curated, `enumerable=false` (a curated slice,
never "all federal law"), and **UNVERIFIED** until a human opens each `source_url`
and confirms the section. It enumerates SCOPE — it does not assert values. Values
come from research + the grounding gate.

Body text: `body_fetch` intercepts U.S. Code citations and pulls the official text
from **govinfo** (the Cornell URL is a scope pointer only — see body_fetch.py); CFR
citations fetch the ecfr.gov page. So both halves ground.
"""
from __future__ import annotations

from typing import Dict, List

from app.core.services.compliance_evals.baseline_masterlist import (
    FEDERAL_LABOR_MASTERLIST,
    BaselineObligation,
)

from .curated_ca import CuratedRow

SLUG = "us-labor-baseline"

# Citations already carried by an ingested index — re-curating them here would mint a
# second authority item for the same section. `us-flsa` holds 29 U.S.C. §§ 206/207/213
# + 29 CFR § 541.600; `ecfr-29-825` (FMLA) and `ecfr-29-1904` (recordkeeping) are
# enumerated from the eCFR structure API as parts/subparts.
ALREADY_INGESTED = frozenset({
    "29 U.S.C. § 206",       # us-flsa — national_minimum_wage
    "29 U.S.C. § 207",       # us-flsa — daily_weekly_overtime
    "29 C.F.R. Part 541",    # us-flsa carries § 541.600 — exempt_salary_threshold
    "29 C.F.R. Part 825",    # ecfr-29-825 subparts — fmla
    "29 C.F.R. Part 1904",   # ecfr-29-1904 subparts — injury_illness_recordkeeping
})


def _heading_for(e: BaselineObligation) -> str:
    """A human label for the section: the obligation key, plus its scope note."""
    label = e.key.replace("_", " ").title()
    return f"{label} — {e.applies_note}" if e.applies_note else label


def _rows() -> List[CuratedRow]:
    return [
        {
            "citation": e.citation,
            "heading": _heading_for(e),
            # `part` groups by obligation category so the Scope Studio list sections.
            "hierarchy": {"code": "US Federal Labor", "part": e.category},
            "source_url": e.authority_url,
        }
        for e in FEDERAL_LABOR_MASTERLIST
        if e.citation not in ALREADY_INGESTED
    ]


# slug → rows. Merged into curated_ca.CURATED_ROWS, which authority_ingest reads.
CURATED_US_ROWS: Dict[str, List[CuratedRow]] = {SLUG: _rows()}
