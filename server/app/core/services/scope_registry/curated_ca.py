"""Curated California authority items — hand-authored, UNVERIFIED.

California has no open, exhaustive machine-readable index of its Labor Code,
Title 8 (Cal/OSHA), or Title 16 (licensing boards), so these are curated
slices, not enumerations. ``enumerable=false`` downstream: ``unclassified_count
== 0`` for these will mean "the curated list is fully classified", never "all
CA law is scoped".

**Verification status.** Every row carries ``curated_by='claude-research'`` and
``verified=False`` — the same rule the golden fixtures follow (see
``compliance_evals/fixtures/golden/README.md``): a fact does not count as
confirmed until a human opens its ``source_url`` and checks the section on the
page. The citations point at real statutes/regulations (no invented law), but
exact section headings and boundaries are what a verifier confirms. Until then
these enumerate scope, they do not assert values.

Citation forms:
  * Labor Code   → "Cal. Lab. Code § 2101"
  * Title 8 CCR  → "8 CCR § 3203"
  * Title 16 CCR → "16 CCR § 1516"   (+ Business & Professions Code where the
                    practice act, not the regulation, is the authority)

`hierarchy` mirrors the JSONB column loosely for curated rows: a `code`/`part`
grouping so the UI can section them. No parent linkage (curated rows are flat).
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class CuratedRow(TypedDict):
    citation: str
    heading: str
    hierarchy: Dict[str, str]
    source_url: str


def _leginfo(code: str, section: str) -> str:
    return (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
        f"?lawCode={code}&sectionNum={section}"
    )


def _title8(section: str) -> str:
    return f"https://www.dir.ca.gov/title8/{section}.html"


# ── ca-labor-code: AB 701 warehouse-quota provisions (Lab. Code §§ 2100–2112) ─
# AB 701 (2021) added the warehouse distribution center quota law. Scope target:
# NAICS 493110 (warehousing) — the taxonomy split commit 2 unblocked.
_AB701: List[CuratedRow] = [
    {
        "citation": "Cal. Lab. Code § 2100",
        "heading": "Definitions — 'employee', 'employer', 'quota', 'warehouse distribution center' (by NAICS 493110, 423, 424, 454110)",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2100"),
    },
    {
        "citation": "Cal. Lab. Code § 2101",
        "heading": "Written description of each quota required to be provided to employee at time of hire",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2101"),
    },
    {
        "citation": "Cal. Lab. Code § 2102",
        "heading": "Employee/former-employee right to request written quota description and personal work-speed data",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2102"),
    },
    {
        "citation": "Cal. Lab. Code § 2103",
        "heading": "No quota that prevents meal/rest periods, bathroom breaks, or occupational health & safety law compliance",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2103"),
    },
    {
        "citation": "Cal. Lab. Code § 2104",
        "heading": "Rebuttable presumption of retaliation for adverse action within 90 days of a protected request/complaint",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2104"),
    },
    {
        "citation": "Cal. Lab. Code § 2105",
        "heading": "Private right of action for injunctive relief; former employee standing",
        "hierarchy": {"code": "Labor Code", "part": "AB 701 (warehouse quotas)"},
        "source_url": _leginfo("LAB", "2105"),
    },
]


# ── ca-title-8: Cal/OSHA core slice (general industry) ────────────────────────
_TITLE8: List[CuratedRow] = [
    {
        "citation": "8 CCR § 3203",
        "heading": "Injury and Illness Prevention Program (IIPP) — the foundational Cal/OSHA program requirement",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("3203"),
    },
    {
        "citation": "8 CCR § 3204",
        "heading": "Access to employee exposure and medical records",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("3204"),
    },
    {
        "citation": "8 CCR § 3395",
        "heading": "Heat Illness Prevention (outdoor places of employment)",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("3395"),
    },
    {
        "citation": "8 CCR § 3396",
        "heading": "Heat Illness Prevention in Indoor Places of Employment (2024)",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("3396"),
    },
    {
        "citation": "8 CCR § 5194",
        "heading": "Hazard Communication",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("5194"),
    },
    {
        "citation": "8 CCR § 5199",
        "heading": "Aerosol Transmissible Diseases (ATD) — referral/healthcare exposure",
        "hierarchy": {"code": "Title 8 CCR", "part": "General Industry Safety Orders"},
        "source_url": _title8("5199"),
    },
]


# ── ca-title-16: professional licensing board slice (optometry / opticianry) ──
# Ophthalmology's California obligations live in the licensing boards, not OSHA.
_TITLE16: List[CuratedRow] = [
    {
        "citation": "Cal. Bus. & Prof. Code § 3040",
        "heading": "Optometry Practice Act — scope of practice of optometry",
        "hierarchy": {"code": "Business & Professions Code", "part": "Optometry"},
        "source_url": _leginfo("BPC", "3040"),
    },
    {
        "citation": "16 CCR § 1516",
        "heading": "State Board of Optometry — continuing education requirements",
        "hierarchy": {"code": "Title 16 CCR", "part": "Board of Optometry (Div. 15)"},
        "source_url": "https://govt.westlaw.com/calregs/Document/16CCR1516",
    },
    {
        "citation": "16 CCR § 1517",
        "heading": "Minimum standards for the practice of optometry (examination requirements)",
        "hierarchy": {"code": "Title 16 CCR", "part": "Board of Optometry (Div. 15)"},
        "source_url": "https://govt.westlaw.com/calregs/Document/16CCR1517",
    },
    {
        "citation": "16 CCR § 1524",
        "heading": "Therapeutic pharmaceutical agent (TPA) certification requirements",
        "hierarchy": {"code": "Title 16 CCR", "part": "Board of Optometry (Div. 15)"},
        "source_url": "https://govt.westlaw.com/calregs/Document/16CCR1524",
    },
    {
        "citation": "Cal. Bus. & Prof. Code § 2541",
        "heading": "Contact lens prescription — release and verification (Fairness to Contact Lens Consumers overlaps FTC rule)",
        "hierarchy": {"code": "Business & Professions Code", "part": "Opticianry / contact lenses"},
        "source_url": _leginfo("BPC", "2541"),
    },
    {
        "citation": "Cal. Bus. & Prof. Code § 2559.2",
        "heading": "Registered dispensing optician — registration and standards",
        "hierarchy": {"code": "Business & Professions Code", "part": "Opticianry / contact lenses"},
        "source_url": _leginfo("BPC", "2559.2"),
    },
]


# slug → rows. Consumed by authority_ingest.ingest_curated_index.
CURATED_ROWS: Dict[str, List[CuratedRow]] = {
    "ca-labor-code": _AB701,
    "ca-title-8": _TITLE8,
    "ca-title-16": _TITLE16,
}
