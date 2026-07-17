"""The one place any engine asks "what does breaking this cost, and says who?".

Three engines answer "what does non-compliance cost this company?" and none knew
about the others:

  * `risk_assessment_service` (/app/risk-assessment) — models expected LOSS for
    wage/exempt/HIPAA: shortfall x 2080 hrs x lookback x liquidated damages. For
    wage keys that is the truer number, because the fine was never the money.
  * `compliance_risk` (the compliance cockpit) — statutory BOUNDS from the
    catalog, now parsed from the CFR table that states them.
  * `risk_index._compliance_component` (the broker composite) — posture, from
    per-requirement status.

This module does NOT merge them. It unifies their PROVENANCE: every engine keeps
its own model, but no engine invents a figure.

**The two models must not be blended, and this is the sharp edge.**
`risk_assessment`'s low/high are the 10th/90th PERCENTILES of a loss
distribution — `monte_carlo_service._lognormal_params` fits mu/sigma from them
via Z_90 and draws from it. A statutory bound is not a percentile of anything:
$16,550 is a ceiling a regulator may impose, not "90% of outcomes are below
this". Feeding bounds into that fit produces a confident garbage distribution on
a page that renders exceedance curves. Bounds are returned here for engines that
want to state them; they must never reach the Monte Carlo path.

Everything below resolves through `penalty_item_id` -> `authority_index_items`,
never `metadata->'penalties'->>'source_url'`: the blob is authored by a MODEL on
the research path (`gemini_compliance` prompts for "source_url"), so a figure's
own block cannot vouch for itself. The FK is the unforgeable fact — a model can
write `"grounding": "grounded"`, it cannot fabricate a join to an ingested
statute.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PenaltyTierFact:
    tier: str
    min_usd: Optional[float]
    max_usd: Optional[float]
    per_day: bool
    citation: str
    quote: str


@dataclass(frozen=True)
class PenaltyFact:
    """A sourced statutory penalty schedule for one obligation.

    Exists only when a real authority row is bound. There is no ungrounded
    variant on purpose: an unsourced figure is not a fact, and callers must be
    able to treat `None` as "we cannot say" rather than having to inspect a
    confidence flag they might forget to check.
    """
    regulation_key: str
    citation: str
    source_url: str
    effective_date: Optional[date]
    tiers: List[PenaltyTierFact]
    default_tier: Optional[str]
    enforcing_agency: Optional[str]

    def tier(self, name: str) -> Optional[PenaltyTierFact]:
        return next((t for t in self.tiers if t.tier == name), None)

    @property
    def headline(self) -> Optional[PenaltyTierFact]:
        """The tier a surface should quote when it hasn't picked one.

        For OSHA that is `serious` — willful/repeated is a finding about the
        employer's state of mind that an inspector makes at citation time, not a
        property of the rule. Quoting $165,514 would be assuming the worst tier.
        """
        if self.default_tier:
            t = self.tier(self.default_tier)
            if t:
                return t
        return self.tiers[0] if self.tiers else None


def _parse(raw: Any) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


def _fact_from_row(row) -> Optional[PenaltyFact]:
    pen = _parse(row["penalties"]) or {}
    tiers_raw = pen.get("tiers") or []
    if not isinstance(tiers_raw, list) or not tiers_raw:
        # Bound but with no parsed schedule: not a fact. Rather than surface a
        # figure with a citation that doesn't actually state it, say nothing.
        return None
    tiers = [
        PenaltyTierFact(
            tier=str(t.get("tier")),
            min_usd=t.get("min_usd"),
            max_usd=t.get("max_usd"),
            per_day=bool(t.get("per_day")),
            # Fall back to the section citation, never to a blob-supplied one.
            citation=str(t.get("citation") or row["authority_citation"]),
            quote=str(t.get("quote") or ""),
        )
        for t in tiers_raw
        if isinstance(t, dict) and t.get("tier")
    ]
    if not tiers:
        return None
    return PenaltyFact(
        regulation_key=row["regulation_key"],
        # Citation + url come from the AUTHORITY ROW. The blob's own copies are
        # ignored even when present.
        citation=row["authority_citation"],
        source_url=row["authority_url"],
        effective_date=row["penalty_effective_date"],
        tiers=tiers,
        default_tier=pen.get("default_tier"),
        enforcing_agency=pen.get("enforcing_agency"),
    )


_SELECT = """
    SELECT jr.regulation_key,
           jr.metadata -> 'penalties' AS penalties,
           jr.penalty_effective_date,
           ai.citation   AS authority_citation,
           ai.source_url AS authority_url
    FROM jurisdiction_requirements jr
    JOIN authority_index_items ai ON ai.id = jr.penalty_item_id
    WHERE ai.source_url IS NOT NULL
"""


async def statutory_bounds(
    conn, regulation_key: str, *, jurisdiction_id: Optional[UUID] = None
) -> Optional[PenaltyFact]:
    """The sourced schedule for one obligation, or None if we cannot say.

    `jurisdiction_id` walks the chain city -> ... -> federal and takes the
    NEAREST bound row, mirroring `compliance_risk._wage_penalty_for_location`:
    a state that sets its own amounts must win over the federal floor. Without a
    jurisdiction we take any bound row for the key — safe today because only
    federal rows are bound (the bind pass's own jurisdiction guard), but callers
    with a location should always pass it.
    """
    if not regulation_key:
        return None

    if jurisdiction_id is not None:
        row = await conn.fetchrow(
            f"""
            WITH RECURSIVE chain AS (
                SELECT id, parent_id, 0 AS depth FROM jurisdictions WHERE id = $2
                UNION ALL
                SELECT j.id, j.parent_id, c.depth + 1
                FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
                WHERE c.depth < 10  -- cycle guard, as in compliance_risk
            )
            {_SELECT}
              AND jr.regulation_key = $1
              AND jr.jurisdiction_id IN (SELECT id FROM chain)
            ORDER BY (SELECT depth FROM chain WHERE chain.id = jr.jurisdiction_id) ASC
            LIMIT 1
            """,
            regulation_key, jurisdiction_id,
        )
    else:
        row = await conn.fetchrow(
            f"{_SELECT} AND jr.regulation_key = $1 ORDER BY jr.penalty_verified_at DESC LIMIT 1",
            regulation_key,
        )

    return _fact_from_row(row) if row else None


async def statutory_bounds_many(
    conn, regulation_keys: List[str]
) -> Dict[str, PenaltyFact]:
    """Facts for many keys in one round-trip. Keys with no fact are ABSENT from
    the mapping — callers iterate what exists rather than checking a flag."""
    keys = [k for k in dict.fromkeys(regulation_keys) if k]
    if not keys:
        return {}
    rows = await conn.fetch(
        f"{_SELECT} AND jr.regulation_key = ANY($1::text[])", keys,
    )
    out: Dict[str, PenaltyFact] = {}
    for row in rows:
        fact = _fact_from_row(row)
        if fact and fact.regulation_key not in out:
            out[fact.regulation_key] = fact
    return out


def cite(fact: Optional[PenaltyFact]) -> Dict[str, Any]:
    """Provenance fields for a surface, shaped so an unsourced item is honest.

    `sourced=False` with no url is the signal a UI needs to render plain text
    rather than a link — the same rule the compliance cockpit follows, so a
    number that can't be checked never looks checkable.
    """
    if fact is None:
        return {"sourced": False, "citation": None, "source_url": None,
                "effective_date": None}
    return {
        "sourced": True,
        "citation": fact.citation,
        "source_url": fact.source_url,
        "effective_date": fact.effective_date.isoformat() if fact.effective_date else None,
    }
