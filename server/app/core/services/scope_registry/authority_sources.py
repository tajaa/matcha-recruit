"""The authority-index catalog — data, not logic.

Which enumerable federal parts and curated state indexes the scope registry
ingests, plus their applicability *domain* (a coarse descriptor the
classification layer in commit 4 refines into per-category dispositions).

``domain_categories`` / ``domain_excludes`` are free-form domain labels, not
`business_categories` slugs — they mirror how the authority itself partitions
(OSHA's "general industry" vs "construction"). Classification maps them onto
the taxonomy; nothing here has to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = ["FederalPart", "CuratedIndexSpec", "FEDERAL_ECFR_PARTS", "CURATED_INDEXES"]


@dataclass(frozen=True)
class FederalPart:
    """One eCFR (title, part) to enumerate. Federal ⇒ jurisdiction_id NULL."""

    title: int
    part: int
    slug: str
    name: str
    domain_categories: List[str] = field(default_factory=list)
    domain_excludes: List[str] = field(default_factory=list)
    level: str = "federal"
    # This part PRICES other parts' obligations instead of imposing its own —
    # a civil-monetary-penalty schedule (29 CFR 1903.15(d) says what breaking
    # 1910.147 costs). It carries no employer duty, so it is not classifiable
    # and holds no regulation_key: the disposition and key passes skip it, and
    # it must not sit in the admin's "needs classification" queue forever.
    penalty_schedule: bool = False


@dataclass(frozen=True)
class CuratedIndexSpec:
    """A curated (non-enumerable) index and how to resolve its jurisdiction.

    ``jurisdiction`` is the lookup spec for `authority_ingest._resolve_jurisdiction_id`
    — e.g. ``{"state": "CA", "level": "state"}``. Items come from
    ``curated_ca.CURATED_ROWS[slug]``.
    """

    slug: str
    name: str
    jurisdiction: Dict[str, str]
    domain_categories: List[str] = field(default_factory=list)
    domain_excludes: List[str] = field(default_factory=list)
    level: str = "state"


# ── Federal — enumerable via the official eCFR structure API ──────────────────
FEDERAL_ECFR_PARTS: List[FederalPart] = [
    FederalPart(
        title=29, part=1910, slug="ecfr-29-1910",
        name="29 CFR Part 1910 — Occupational Safety and Health Standards (General Industry)",
        domain_categories=["general_industry"],
        domain_excludes=["construction", "agriculture", "maritime"],
    ),
    FederalPart(
        title=29, part=1904, slug="ecfr-29-1904",
        name="29 CFR Part 1904 — Recording and Reporting Occupational Injuries and Illnesses",
        domain_categories=["all_industry"],
        # Partial-exemption NAICS list is a per-section classification concern.
    ),
    FederalPart(
        title=29, part=825, slug="ecfr-29-825",
        name="29 CFR Part 825 — The Family and Medical Leave Act of 1993",
        domain_categories=["all_industry"],
        # Applies only at ≥50 employees — a conditional stratum, not an exclude.
    ),
    FederalPart(
        title=29, part=1903, slug="ecfr-29-1903",
        name="29 CFR Part 1903 — Inspections, Citations, and Proposed Penalties (OSHA)",
        domain_categories=["all_industry"],
        # § 1903.15(d) is the OSHA civil-monetary-penalty schedule — the
        # authority for what a violation of ANY 1910 standard costs. Adjusted
        # for inflation every January under 28 U.S.C. 2461 note, which is why
        # binding to it (and letting drift catch the re-issue) beats copying
        # the figures: the catalog currently holds four vintages of the OSHA
        # serious-violation maximum at once.
        penalty_schedule=True,
    ),
    FederalPart(
        title=40, part=260, slug="ecfr-40-260",
        name="40 CFR Part 260 — Hazardous Waste Management System: General (RCRA)",
        domain_categories=["hazardous_waste_generators"],
    ),
    FederalPart(
        title=40, part=261, slug="ecfr-40-261",
        name="40 CFR Part 261 — Identification and Listing of Hazardous Waste (RCRA)",
        domain_categories=["hazardous_waste_generators"],
    ),
    FederalPart(
        title=40, part=262, slug="ecfr-40-262",
        name="40 CFR Part 262 — Standards Applicable to Generators of Hazardous Waste (RCRA)",
        domain_categories=["hazardous_waste_generators"],
    ),
]


# ── Curated slices (enumerable=false; "curated, not exhaustive") ──────────────
CURATED_INDEXES: List[CuratedIndexSpec] = [
    # Federal FLSA wage-hour floor — statute lives in 29 U.S.C., not eCFR, so
    # it's curated. level='federal' ⇒ jurisdiction_id NULL (applies to all US).
    CuratedIndexSpec(
        slug="us-flsa",
        name="Fair Labor Standards Act — federal wage-hour floor (selected)",
        jurisdiction={},
        level="federal",
        domain_categories=["all_industry"],
    ),
    # The federal labor baseline's statutes — Title VII, ADA, ADEA, WARN, I-9,
    # COBRA, ERISA, NLRA, USERRA, FCRA, EEO-1, garnishment. None are in eCFR's
    # structure API, so they're curated (derived from baseline_masterlist).
    CuratedIndexSpec(
        slug="us-labor-baseline",
        name="US Federal Labor Baseline — general-employer statutes (curated)",
        jurisdiction={},
        level="federal",
        domain_categories=["all_industry"],
    ),
    CuratedIndexSpec(
        slug="ca-labor-code",
        name="California Labor Code — core wage-hour spine + AB 701 (selected)",
        jurisdiction={"state": "CA", "level": "state"},
        domain_categories=["all_ca_employers"],
    ),
    CuratedIndexSpec(
        slug="ca-title-8",
        name="California Code of Regulations, Title 8 (Cal/OSHA) — core slice",
        jurisdiction={"state": "CA", "level": "state"},
        domain_categories=["general_industry"],
    ),
    CuratedIndexSpec(
        slug="ca-title-16",
        name="California Code of Regulations, Title 16 (Professional Licensing Boards) — board slice",
        jurisdiction={"state": "CA", "level": "state"},
        domain_categories=["licensed_professions"],
    ),
]


def federal_part_by_slug(slug: str) -> Optional[FederalPart]:
    return next((p for p in FEDERAL_ECFR_PARTS if p.slug == slug), None)


def curated_index_by_slug(slug: str) -> Optional[CuratedIndexSpec]:
    return next((c for c in CURATED_INDEXES if c.slug == slug), None)


def all_index_slugs() -> List[str]:
    return [p.slug for p in FEDERAL_ECFR_PARTS] + [c.slug for c in CURATED_INDEXES]


def is_penalty_schedule(slug: str) -> bool:
    """Does this index price other parts' obligations rather than impose its own?

    Such an index is ingested and body-fetched like any other — the schedule text
    is the point — but it is never classified and never keyed: there is no
    employer duty in it to give a disposition to, and no obligation for it to be
    the authority FOR. Classifying it would dispose every section ``excluded``
    and then park the index in the admin's unclassified queue permanently.
    """
    part = federal_part_by_slug(slug)
    return bool(part and part.penalty_schedule)
