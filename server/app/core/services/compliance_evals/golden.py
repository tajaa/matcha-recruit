"""Golden-dataset suite — compare the catalog against hand-verified ground truth.

Facts live in ``fixtures/golden/*.json``, not in a table. Code review is curation
review, ``git blame`` is provenance, and a fact can never be edited into existence
without someone approving the diff. The database stores *results*; the repo stores
*truth*.

Every fact carries an ``effective_from``/``effective_to`` window because compliance
law is not static — Los Angeles reindexes its minimum wage every July 1. Only facts
whose window contains today are asserted. A fact whose window has closed with no
successor covering today emits ``golden_stale``: the fixture polices its own
freshness rather than quietly asserting last year's wage forever.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .keys import normalize_key
from .scoring import accuracy_score

logger = logging.getLogger(__name__)

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"

Comparator = str  # numeric_eq | numeric_within | text_contains | date_eq | exists

_NUMERIC_RE = re.compile(r"-?\d[\d,]*\.?\d*")


class GoldenFact(BaseModel):
    requirement_key: str
    category: str
    comparator: Comparator
    expected_numeric: Optional[float] = None
    expected_text: Optional[str] = None
    expected_date: Optional[date] = None
    tolerance: float = 0.0
    effective_from: date
    effective_to: Optional[date] = None
    authority_url: str
    industries: Optional[List[str]] = None
    severity: str = "warn"
    curated_by: str
    curated_at: date
    verified_by: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("comparator")
    @classmethod
    def _known_comparator(cls, v: str) -> str:
        allowed = {"numeric_eq", "numeric_within", "text_contains", "date_eq", "exists"}
        if v not in allowed:
            raise ValueError(f"unknown comparator {v!r}; expected one of {sorted(allowed)}")
        return v

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in {"critical", "warn", "info"}:
            raise ValueError(f"unknown severity {v!r}")
        return v

    @field_validator("authority_url")
    @classmethod
    def _real_url(cls, v: str) -> str:
        if not v.startswith("http"):
            raise ValueError("authority_url must be an absolute http(s) URL")
        return v

    def active_on(self, when: date) -> bool:
        if when < self.effective_from:
            return False
        return self.effective_to is None or when < self.effective_to

    def expired_on(self, when: date) -> bool:
        return self.effective_to is not None and when >= self.effective_to


class GoldenJurisdiction(BaseModel):
    country_code: str = "US"
    state: Optional[str] = None
    city: Optional[str] = None
    level: str


class GoldenFixture(BaseModel):
    fixture_version: str
    jurisdiction: GoldenJurisdiction
    facts: List[GoldenFact] = Field(default_factory=list)


def load_fixtures(directory: Optional[Path] = None) -> List[GoldenFixture]:
    """Parse every fixture file. Raises on malformed input — a bad fixture is a bug."""
    directory = directory or GOLDEN_DIR
    if not directory.exists():
        return []
    fixtures: List[GoldenFixture] = []
    for path in sorted(directory.glob("*.json")):
        with path.open() as fh:
            raw = json.load(fh)
        fixtures.append(GoldenFixture.model_validate(raw))
    return fixtures


def parse_numeric(value: Optional[str]) -> Optional[float]:
    """First number in a free-text value: '$17.87 per hour' → 17.87."""
    if not value:
        return None
    match = _NUMERIC_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def compare(fact: GoldenFact, row: Optional[Dict]) -> Dict:
    """Evaluate one fact against its catalog row. Returns {passed, reason, observed}."""
    if row is None:
        return {"passed": False, "reason": "no catalog row for this key", "observed": None}

    if fact.comparator == "exists":
        return {"passed": True, "reason": "row present", "observed": {"present": True}}

    if fact.comparator in ("numeric_eq", "numeric_within"):
        actual = row.get("numeric_value")
        if actual is None:
            actual = parse_numeric(row.get("current_value"))
        if actual is None:
            return {
                "passed": False,
                "reason": "no numeric value on the catalog row",
                "observed": {"current_value": row.get("current_value")},
            }
        actual = float(actual)
        tol = fact.tolerance if fact.comparator == "numeric_within" else 0.0
        expected = fact.expected_numeric or 0.0
        passed = abs(actual - expected) <= tol + 1e-9
        return {
            "passed": passed,
            "reason": "" if passed else f"expected {expected} (±{tol}), catalog has {actual}",
            "observed": {"numeric_value": actual},
        }

    if fact.comparator == "text_contains":
        haystack = " ".join(
            str(row.get(f) or "") for f in ("current_value", "description", "title")
        ).lower()
        needle = (fact.expected_text or "").lower()
        passed = bool(needle) and needle in haystack
        return {
            "passed": passed,
            "reason": "" if passed else f"catalog text does not contain {fact.expected_text!r}",
            "observed": {"current_value": row.get("current_value")},
        }

    if fact.comparator == "date_eq":
        actual = row.get("effective_date")
        if isinstance(actual, datetime):
            actual = actual.date()
        passed = actual == fact.expected_date
        return {
            "passed": passed,
            "reason": "" if passed else f"expected effective_date {fact.expected_date}, catalog has {actual}",
            "observed": {"effective_date": str(actual) if actual else None},
        }

    return {"passed": False, "reason": f"unhandled comparator {fact.comparator}", "observed": None}


async def _resolve_jurisdiction_id(conn, jur: GoldenJurisdiction):
    if jur.level in ("federal", "national"):
        # Pin country_code: 'national' is shared by every country's root (US
        # 'federal' + UK/MX/SG 'national'), so an unpinned LIMIT 1 could resolve a
        # US-federal fixture to a foreign row. `level='federal' DESC` keeps the US
        # root deterministic even if a stray US 'national' row exists.
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE level::text IN ('federal','national') "
            "AND COALESCE(country_code,'US') = $1 "
            "ORDER BY (level::text = 'federal') DESC LIMIT 1",
            jur.country_code,
        )
    elif jur.level == "state":
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE level::text = 'state' "
            "AND state = $1 AND COALESCE(country_code,'US') = $2 LIMIT 1",
            jur.state, jur.country_code,
        )
    else:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE LOWER(city) = LOWER($1) AND state = $2 "
            "AND COALESCE(country_code,'US') = $3 LIMIT 1",
            jur.city, jur.state, jur.country_code,
        )
    return row["id"] if row else None


async def _rows_for(conn, jurisdiction_id) -> Dict[str, Dict]:
    """Catalog rows for one jurisdiction, indexed by `category:normalized_key`.

    Normalization matters here: a city's minimum-wage row is stored under the
    rate_type `general`, while a golden fact names it `local_minimum_wage`.
    """
    rows = await conn.fetch("""
        SELECT jr.regulation_key, jr.requirement_key, jr.category, jr.title,
               jr.description, jr.current_value, jr.numeric_value, jr.effective_date,
               j.level::text AS level, COALESCE(j.country_code, 'US') AS country_code
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
        WHERE jr.jurisdiction_id = $1
    """, jurisdiction_id)
    out: Dict[str, Dict] = {}
    for r in rows:
        key = r["regulation_key"]
        if not key and r["requirement_key"] and ":" in r["requirement_key"]:
            key = r["requirement_key"].rsplit(":", 1)[-1]
        if not key:
            continue
        key = normalize_key(r["category"], key, r["level"], r["country_code"])
        out[f"{r['category']}:{key}"] = dict(r)
    return out


async def run_golden(conn, today: Optional[date] = None) -> Dict:
    """Assert every active golden fact. Emits golden_fail / golden_stale findings."""
    today = today or date.today()
    fixtures = load_fixtures()

    findings: List[Dict] = []
    per_jur: Dict = {}

    for fixture in fixtures:
        jid = await _resolve_jurisdiction_id(conn, fixture.jurisdiction)
        if jid is None:
            logger.warning(
                "golden fixture references an unknown jurisdiction: %s",
                fixture.jurisdiction.model_dump(),
            )
            continue

        catalog = await _rows_for(conn, jid)
        stats = per_jur.setdefault(jid, {"passed": 0, "failed": 0, "critical_failures": 0})

        # Any key with an active fact needs no staleness warning for its predecessors.
        active_keys = {f.requirement_key for f in fixture.facts if f.active_on(today)}

        for fact in fixture.facts:
            if not fact.active_on(today):
                if fact.expired_on(today) and fact.requirement_key not in active_keys:
                    findings.append({
                        "suite": "golden",
                        "finding_type": "golden_stale",
                        "severity": "warn",
                        "jurisdiction_id": jid,
                        "requirement_key": fact.requirement_key,
                        "category": fact.category,
                        "expected": {
                            "effective_to": str(fact.effective_to),
                            "action": "curate a successor fact covering today",
                        },
                        "observed": {"as_of": str(today)},
                    })
                continue

            row = catalog.get(f"{fact.category}:{fact.requirement_key}")
            verdict = compare(fact, row)

            if verdict["passed"]:
                stats["passed"] += 1
                continue

            stats["failed"] += 1
            if fact.severity == "critical":
                stats["critical_failures"] += 1
            findings.append({
                "suite": "golden",
                "finding_type": "golden_fail",
                "severity": fact.severity,
                "jurisdiction_id": jid,
                "requirement_key": fact.requirement_key,
                "category": fact.category,
                "expected": {
                    "comparator": fact.comparator,
                    "numeric": fact.expected_numeric,
                    "text": fact.expected_text,
                    "date": str(fact.expected_date) if fact.expected_date else None,
                    "authority_url": fact.authority_url,
                },
                "observed": {**(verdict["observed"] or {}), "reason": verdict["reason"]},
            })

    # Chain inheritance: a CA fact IS an assertion about Los Angeles — state and
    # federal law apply in the city. Scoring each jurisdiction only against facts
    # whose fixture happens to name it left LA(6)/SF(4)/NYC(4) permanently under
    # MIN_GOLDEN_FACTS_READY and therefore permanently DEGRADED, no matter how
    # correct their data was (COMPLIANCE_SYSTEM_GAP_REVIEW.md §5). Each fact is
    # still ASSERTED against its own jurisdiction's rows (a CA fact checks CA's
    # row, not LA's); only the roll-up inherits.
    effective = await _inherit_along_chains(conn, per_jur)

    results = {
        jid: {
            "score": accuracy_score(s["passed"], s["failed"], s["critical_failures"]),
            "detail": s,
        }
        for jid, s in effective.items()
    }
    return {"results": results, "findings": findings, "fact_counts": {
        jid: s["passed"] + s["failed"] for jid, s in effective.items()
    }}


async def _inherit_along_chains(conn, per_jur: Dict) -> Dict:
    """Roll each jurisdiction's own fact stats up with its ancestors' (city →
    state → federal). Pure aggregation over ``per_jur``; no new assertions.
    """
    if not per_jur:
        return per_jur

    rows = await conn.fetch(
        "SELECT id, level::text AS level, state, COALESCE(country_code,'US') AS country_code "
        "FROM jurisdictions WHERE id = ANY($1::uuid[])",
        list(per_jur.keys()),
    )
    # Ancestors of a sub-state jurisdiction: its state's row + the federal row.
    # Looked up among the fixture jurisdictions only — a fixture-less ancestor
    # contributes no facts, so it can't contribute stats either.
    #
    # BOTH lookups are keyed by country. "Federal law applies everywhere" means
    # everywhere in ITS OWN country: the first non-US national fixture would
    # otherwise roll UK facts into every US city and vice versa — the same
    # bucket-confusion completeness.py documents as a real past bug ("a US city
    # inheriting from the United Kingdom").
    by_level_state = {}
    federal_by_country: Dict[str, List] = {}
    for r in rows:
        if r["level"] in ("federal", "national"):
            federal_by_country.setdefault(r["country_code"], []).append(r["id"])
        elif r["level"] == "state":
            by_level_state[(r["state"], r["country_code"])] = r["id"]

    effective: Dict = {}
    for r in rows:
        jid = r["id"]
        own = per_jur[jid]
        ancestors = []
        if r["level"] not in ("federal", "national"):
            ancestors.extend(federal_by_country.get(r["country_code"], []))
        if r["level"] not in ("federal", "national", "state"):
            state_id = by_level_state.get((r["state"], r["country_code"]))
            if state_id:
                ancestors.append(state_id)

        merged = dict(own)
        for aid in ancestors:
            anc = per_jur.get(aid)
            if not anc:
                continue
            for k in ("passed", "failed", "critical_failures"):
                merged[k] += anc[k]
        effective[jid] = merged
    return effective
