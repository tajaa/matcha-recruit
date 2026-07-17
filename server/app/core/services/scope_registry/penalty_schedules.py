"""Civil-monetary-penalty schedules, parsed from the CFR text that states them.

Every federal agency must adjust its civil monetary penalties for inflation each
January (Federal Civil Penalties Inflation Adjustment Act Improvements Act of
2015, 28 U.S.C. 2461 note) and publish the result in its own CFR penalty table.
Those tables are the authoritative repository for "what does breaking this cost",
and they are ordinary eCFR parts — the same thing `FEDERAL_ECFR_PARTS` already
ingests.

Why parse instead of ask a model: the catalog currently holds **four vintages of
the OSHA serious-violation maximum at once** (16,131 / 15,873 / 165,514 /
161,323), three with no source_url, one filed under the agency
"CMS / State Licensing Boards / OSHA". Those came from model recall at different
times. The text below is regular enough to parse deterministically, and a parse
can be re-run in January.

Two facts that shape the design:

* **A penalty lives in a different section from the obligation.** 29 CFR 1910.147
  says lock out the machine; 29 CFR 1903.15(d) says what it costs. So penalty
  authority is its own binding (`penalty_item_id`), never a second use of
  `citation_item_id`.
* **A penalty is a schedule by tier, not a number.** Every OSHA standard shares
  one schedule; which tier applies (serious vs willful) is decided at citation
  time, by the inspector — it is not a property of the requirement. Collapsing
  that to a single min/max is how the willful floor ($11,823) and the serious
  ceiling ($16,550) got blended into incoherent pairs.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Canonical tier vocabulary. The label in the CFR is prose ("Other-than-serious
# violation."), so it is normalized to these.
TIERS = (
    "willful",
    "repeated",
    "serious",
    "other_than_serious",
    "failure_to_correct",
    "posting",
)


@dataclass(frozen=True)
class PenaltyTier:
    tier: str
    min_usd: Optional[float]
    max_usd: Optional[float]
    per_day: bool
    citation: str
    quote: str


@dataclass(frozen=True)
class PenaltySchedule:
    """One agency's adjusted-penalty table, as parsed from its own CFR text."""
    citation: str
    tiers: List[PenaltyTier] = field(default_factory=list)
    effective_date: Optional[date] = None
    source_url: Optional[str] = None

    def tier(self, name: str) -> Optional[PenaltyTier]:
        return next((t for t in self.tiers if t.tier == name), None)


# ── OSHA — 29 CFR 1903.15(d) ────────────────────────────────────────────────

_OSHA_TIER_LABELS: Dict[str, str] = {
    "willful violation": "willful",
    "repeated violation": "repeated",
    "serious violation": "serious",
    "other-than-serious violation": "other_than_serious",
    "failure to correct violation": "failure_to_correct",
    "posting requirement violation": "posting",
}

# "(d) Adjusted civil monetary penalties. The adjusted civil penalties for
#  penalties proposed after January 15, 2025 are as follows:"
_OSHA_D_START = re.compile(r"\(d\)\s*Adjusted civil monetary penalties\.", re.I)
_OSHA_EFFECTIVE = re.compile(
    r"penalties proposed (?:on or )?after\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", re.I
)
# Each tier is "(N) <Label>. <sentence>." — stop at the next "(N) " or the
# amendment-history bracket "[36 FR 17850, ...]" that closes the section.
_OSHA_TIER_BLOCK = re.compile(
    r"\((\d+)\)\s*([^.]+?)\.\s*(.+?)(?=\(\d+\)\s*[A-Z]|\[\d+\s*FR|\Z)", re.S
)
_MONEY = r"\$([\d,]+(?:\.\d{2})?)"
_NOT_LESS_THAN = re.compile(r"not be less than\s*" + _MONEY, re.I)
_NOT_EXCEED = re.compile(r"not exceed\s*" + _MONEY, re.I)


def _money(raw: str) -> float:
    return float(raw.replace(",", ""))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_osha_schedule(
    body_text: str, *, citation: str = "29 CFR 1903.15", source_url: Optional[str] = None
) -> Optional[PenaltySchedule]:
    """Parse 29 CFR 1903.15(d) into tiers. Returns None if (d) isn't present.

    Deliberately all-or-nothing on the (d) block: a body that has changed shape
    enough that we cannot find the adjusted-penalty paragraph must yield NO
    schedule rather than a half-parsed one. A missing schedule is visible (rows
    stay ungrounded); a partial schedule silently prices a violation wrong.
    """
    if not body_text:
        return None
    m = _OSHA_D_START.search(body_text)
    if not m:
        logger.warning("penalty parse: no (d) block in %s", citation)
        return None

    # (d) runs to the amendment-history bracket, or to the end.
    tail = body_text[m.end():]
    end = re.search(r"\[\d+\s*FR", tail)
    block = tail[: end.start()] if end else tail

    effective: Optional[date] = None
    eff_m = _OSHA_EFFECTIVE.search(body_text[m.start(): m.end() + 300])
    if eff_m:
        try:
            effective = datetime.strptime(_squash(eff_m.group(1)), "%B %d, %Y").date()
        except ValueError:
            logger.warning("penalty parse: bad effective date %r", eff_m.group(1))

    tiers: List[PenaltyTier] = []
    for num, label, sentence in _OSHA_TIER_BLOCK.findall(block):
        key = _OSHA_TIER_LABELS.get(_squash(label).lower())
        if key is None:
            # An unrecognised tier is skipped, not guessed into the vocabulary —
            # if OSHA adds one, it shows up as absent rather than mislabelled.
            logger.info("penalty parse: unknown tier label %r in %s", label, citation)
            continue
        quote = _squash(sentence)
        lo = _NOT_LESS_THAN.search(quote)
        hi = _NOT_EXCEED.search(quote)
        if not hi:
            continue  # A tier with no ceiling states no figure — skip it.
        tiers.append(PenaltyTier(
            tier=key,
            min_usd=_money(lo.group(1)) if lo else None,
            max_usd=_money(hi.group(1)),
            # "shall not exceed $16,550 per day" — the multiplier is IN the text.
            per_day=bool(re.search(r"per day", quote, re.I)),
            citation=f"{citation}(d)({num})",
            quote=quote,
        ))

    if not tiers:
        return None
    return PenaltySchedule(
        citation=f"{citation}(d)",
        tiers=tiers,
        effective_date=effective,
        source_url=source_url,
    )


# ── agency → schedule source ────────────────────────────────────────────────

@dataclass(frozen=True)
class ScheduleSource:
    """Where one agency's schedule lives, and which tier speaks for it by default."""
    slug: str          # authority index slug
    section: str       # the item citation carrying the table
    parser: str        # 'osha' — dispatch key
    default_tier: str  # the tier that fills the flat civil_penalty_min/max pair


# ⚠️  PARTIAL TABLE — deliberately incomplete, same rule as
# `risk_transfer._STATE_ANTI_INDEMNITY` and `compliance_risk_dims`. An agency is
# here only if its schedule has been sourced and a parser proven against the real
# text. Unmapped agencies get NO schedule and stay ungrounded — visibly so.
#
# Matching is EXACT and case-insensitive on the whole string, never substring:
# the live catalog contains "Cal/OSHA", "CMS / State Licensing Boards / OSHA" and
# "California State Board of Pharmacy / Cal/OSHA". A substring match on "OSHA"
# would stamp federal dollars on all of them. Cal/OSHA is a genuinely DIFFERENT
# schedule (California sets its own amounts) — it stays out until sourced.
_AGENCY_SCHEDULES: Dict[str, ScheduleSource] = {
    "osha": ScheduleSource(
        slug="ecfr-29-1903", section="29 CFR 1903.15",
        parser="osha",
        # Serious is the modal OSHA citation and the honest default: willful is a
        # finding about the employer's state of mind, not a property of the rule.
        default_tier="serious",
    ),
    "occupational safety and health administration (osha)": ScheduleSource(
        slug="ecfr-29-1903", section="29 CFR 1903.15",
        parser="osha", default_tier="serious",
    ),
}


def schedule_source_for_agency(agency: Optional[str]) -> Optional[ScheduleSource]:
    """Exact-match an enforcing_agency string to its schedule. Never fuzzy."""
    if not agency:
        return None
    return _AGENCY_SCHEDULES.get(agency.strip().lower())


def mapped_agencies() -> List[str]:
    return sorted(_AGENCY_SCHEDULES)


_PARSERS = {"osha": parse_osha_schedule}


def parse_schedule(
    parser: str, body_text: str, *, citation: str, source_url: Optional[str] = None
) -> Optional[PenaltySchedule]:
    fn = _PARSERS.get(parser)
    if fn is None:
        return None
    return fn(body_text, citation=citation, source_url=source_url)


# ── wire shape ──────────────────────────────────────────────────────────────

def penalties_payload(
    schedule: PenaltySchedule, source: ScheduleSource, *, keep: Optional[dict] = None
) -> dict:
    """The `metadata->'penalties'` block for a bound requirement.

    `tiers[]` is additive: `civil_penalty_min/max` stay populated from the default
    tier so every existing reader (RiskPenalty, compute_exposure, the cockpit
    tile, _wage_penalty_for_location) keeps working untouched.

    `keep` carries the model's prose (`summary`, `criminal`) forward — it is
    genuinely useful where the statute states no figure — but it can never
    override a parsed number.
    """
    default = schedule.tier(source.default_tier) or schedule.tiers[0]
    out = {
        "enforcing_agency": (keep or {}).get("enforcing_agency"),
        # A tier ceiling is "shall not exceed $X": a maximum with no statutory
        # floor. Only willful carries a floor, so min is None for serious —
        # compute_exposure's lo-borrows-hi rule then reads it correctly.
        "civil_penalty_min": default.min_usd,
        "civil_penalty_max": default.max_usd,
        "per_violation": True,
        "annual_cap": None,
        "default_tier": default.tier,
        "tiers": [
            {
                "tier": t.tier, "min_usd": t.min_usd, "max_usd": t.max_usd,
                "per_day": t.per_day, "citation": t.citation, "quote": t.quote,
            }
            for t in schedule.tiers
        ],
        "citation": schedule.citation,
        "effective_date": schedule.effective_date.isoformat() if schedule.effective_date else None,
        "source_url": schedule.source_url,
        "grounding": "grounded",
    }
    for prose in ("summary", "criminal"):
        if (keep or {}).get(prose):
            out[prose] = keep[prose]
    return {k: v for k, v in out.items() if v is not None or k in ("annual_cap", "civil_penalty_min")}


# ── bind ────────────────────────────────────────────────────────────────────

async def bind_penalties(conn, *, agency: Optional[str] = None) -> Dict[str, Any]:
    """Stamp parsed schedules onto the catalog rows they govern.

    Guards, each of which is a way this could quietly cite the wrong law at a
    business:

    * **Exact agency match only** — `schedule_source_for_agency` never matches a
      substring, so "Cal/OSHA" and "CMS / State Licensing Boards / OSHA" (both
      live in the catalog) do not collect federal figures.
    * **Federal rows only.** Agency alone is NOT enough: 4 state-level and 5
      national-level rows also carry the agency "OSHA". `national` means FOREIGN
      COUNTRY in this schema, and state-plan states (Cal/OSHA et al.) set their
      own amounts. Stamping 1903.15(d) dollars on either recreates exactly the
      jurisdiction-governance bug `codify._authority_governs` exists to prevent.
    * **All-or-nothing parse.** A schedule that won't parse binds nothing; the
      rows stay ungrounded and visibly so.
    """
    from .grounded import sanitize_penalties_for_persist

    sources = (
        {agency.strip().lower(): _AGENCY_SCHEDULES[agency.strip().lower()]}
        if agency and agency.strip().lower() in _AGENCY_SCHEDULES
        else dict(_AGENCY_SCHEDULES)
    )
    out: Dict[str, Any] = {"bound": 0, "skipped_unparsed": 0, "agencies": [], "warnings": []}
    seen_slugs: Dict[Tuple[str, str], Optional[PenaltySchedule]] = {}

    for agency_key, source in sources.items():
        item = await conn.fetchrow(
            """
            SELECT i.id, i.body_text,
                   -- The READABLE page, not body_source_url. The latter is the
                   -- versioner API endpoint we fetch XML from
                   -- (…/api/versioner/v1/full/2026-07-06/title-29.xml?part=1903)
                   -- — a person following the citation to check our figure needs
                   -- the eCFR page, not a snapshot-dated XML dump.
                   COALESCE(i.source_url, i.body_source_url) AS source_url
            FROM authority_index_items i
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE ai.slug = $1 AND i.citation = $2
            """,
            source.slug, source.section,
        )
        if item is None or not item["body_text"]:
            out["warnings"].append(
                f"{agency_key}: {source.section} not ingested (or no body) — nothing bound"
            )
            continue

        cache_key = (source.slug, source.section)
        if cache_key not in seen_slugs:
            seen_slugs[cache_key] = parse_schedule(
                source.parser, item["body_text"],
                citation=source.section, source_url=item["source_url"],
            )
        schedule = seen_slugs[cache_key]
        if schedule is None:
            out["skipped_unparsed"] += 1
            out["warnings"].append(f"{agency_key}: {source.section} did not parse — nothing bound")
            continue

        rows = await conn.fetch(
            """
            SELECT jr.id, jr.metadata -> 'penalties' AS penalties
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE lower(trim(jr.metadata -> 'penalties' ->> 'enforcing_agency')) = $1
              AND j.level = 'federal'
              AND j.country_code = 'US'
            """,
            agency_key,
        )
        for r in rows:
            # metadata->'penalties' arrives as a dict or a JSON string depending
            # on the driver's jsonb handling — same defensive parse as
            # compliance_risk._parse_penalties.
            keep = r["penalties"]
            if isinstance(keep, str):
                try:
                    keep = json.loads(keep)
                except ValueError:
                    keep = None
            if not isinstance(keep, dict):
                keep = None
            payload = penalties_payload(schedule, source, keep=keep)
            sanitize_penalties_for_persist(payload)
            await conn.execute(
                """
                UPDATE jurisdiction_requirements
                SET metadata = jsonb_set(
                        COALESCE(metadata, '{}'::jsonb), '{penalties}', $2::jsonb, true),
                    penalty_item_id = $3,
                    penalty_verified_at = NOW(),
                    penalty_effective_date = $4,
                    updated_at = NOW()
                WHERE id = $1
                """,
                r["id"], json.dumps(payload), item["id"], schedule.effective_date,
            )
            out["bound"] += 1
        out["agencies"].append({"agency": agency_key, "rows": len(rows),
                                "citation": schedule.citation,
                                "effective_date": str(schedule.effective_date)})
    return out
