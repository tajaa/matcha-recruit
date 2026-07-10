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


# ── ca-labor-code: the core CA wage-hour spine + AB 701 ──────────────────────
# The basic labor law every CA employer owes (§§ below, universal) plus AB 701's
# warehouse-specific quota provisions (§§ 2100-2105, warehousing only). All
# section numbers web-verified 2026-07-10 against leginfo/justia; unverified
# flag stands until a human confirms each value on the page.
_CA_LABOR: List[CuratedRow] = [
    # ── core wage-hour (universal — every CA employer) ──
    {
        "citation": "Cal. Lab. Code § 1182.12",
        "heading": "State minimum wage",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "1182.12"),
    },
    {
        "citation": "Cal. Lab. Code § 515",
        "heading": "Exemptions from overtime; salary basis for the white-collar exemptions (≥ 2× state minimum wage, full-time)",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "515"),
    },
    {
        "citation": "Cal. Lab. Code § 510",
        "heading": "Overtime — 1.5× over 8 hrs/day or 40 hrs/week and first 8 on the 7th day; 2× over 12 hrs/day and over 8 on the 7th day",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "510"),
    },
    {
        "citation": "Cal. Lab. Code § 512",
        "heading": "Meal periods — 30-min unpaid meal by the 5th hour; second meal by the 10th (waiver rules apply)",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "512"),
    },
    # § 226.7 carries two distinct obligations, split into two authority items
    # so each maps to its own regulation_key (one item = one key): (b) the
    # no-work prohibition (rest_break anchor) and (c) the premium-pay penalty
    # (missed_break_penalty). The operational rest rule itself is IWC Wage Order 12.
    {
        "citation": "Cal. Lab. Code § 226.7(b)",
        "heading": "No work required during a meal/rest/recovery period (the Labor Code rest-period anchor; the operational rest rule is IWC Wage Order 12)",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "226.7"),
    },
    {
        "citation": "Cal. Lab. Code § 226.7(c)",
        "heading": "One additional hour of pay per workday for each meal/rest/recovery period not provided (the premium-pay penalty)",
        "hierarchy": {"code": "Labor Code", "part": "Wage & hour"},
        "source_url": _leginfo("LAB", "226.7"),
    },
    {
        "citation": "Cal. Lab. Code § 201",
        "heading": "Final wages due immediately on discharge",
        "hierarchy": {"code": "Labor Code", "part": "Wage payment"},
        "source_url": _leginfo("LAB", "201"),
    },
    {
        "citation": "Cal. Lab. Code § 202",
        "heading": "Final wages within 72 hrs of resignation (immediately if 72 hrs' notice given)",
        "hierarchy": {"code": "Labor Code", "part": "Wage payment"},
        "source_url": _leginfo("LAB", "202"),
    },
    {
        "citation": "Cal. Lab. Code § 203",
        "heading": "Waiting-time penalties — up to 30 days' wages for willful failure to pay final wages",
        "hierarchy": {"code": "Labor Code", "part": "Wage payment"},
        "source_url": _leginfo("LAB", "203"),
    },
    {
        "citation": "Cal. Lab. Code § 204",
        "heading": "Semi-monthly pay frequency and pay-timing rules",
        "hierarchy": {"code": "Labor Code", "part": "Wage payment"},
        "source_url": _leginfo("LAB", "204"),
    },
    {
        "citation": "Cal. Lab. Code § 226",
        "heading": "Itemized wage statement — the nine mandatory line items on every pay stub",
        "hierarchy": {"code": "Labor Code", "part": "Wage payment"},
        "source_url": _leginfo("LAB", "226"),
    },
    {
        "citation": "Cal. Lab. Code § 246",
        "heading": "Paid sick leave (Healthy Workplaces, Healthy Families Act) — ≥ 40 hrs / 5 days per year since 2024",
        "hierarchy": {"code": "Labor Code", "part": "Paid sick days"},
        "source_url": _leginfo("LAB", "246"),
    },
    {
        "citation": "Cal. Lab. Code § 3700",
        "heading": "Mandatory workers'-compensation coverage for every California employer",
        "hierarchy": {"code": "Labor Code", "part": "Workers' compensation"},
        "source_url": _leginfo("LAB", "3700"),
    },
    # ── AB 701 warehouse-quota provisions (§§ 2100-2105, warehousing only) ──
    # AB 701 (2021) added the warehouse distribution center quota law. Scope
    # target: NAICS 493110 (warehousing) — the taxonomy split commit 2 unblocked.
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
# Every citation below was web-verified against the statute/board source on
# 2026-07-10 (an earlier draft carried §1516/§1517/§1524/§2541/§2559.2, which
# were wrong or unverifiable — CE is §1536, contact-lens dispensing is §2542,
# RDO registration is §2550). CCR sections cite the board's official laws/regs
# index — calregs.westlaw permalinks use opaque GUIDs and can't be constructed.
_BOARD_LAWSREGS = "https://www.optometry.ca.gov/lawsregs/index.shtml"

_TITLE16: List[CuratedRow] = [
    {
        "citation": "Cal. Bus. & Prof. Code § 3041",
        "heading": "Practice of optometry — statutory scope (examination, refraction, lenses; anterior-segment treatment for certified optometrists)",
        "hierarchy": {"code": "Business & Professions Code", "part": "Optometry (Ch. 7)"},
        "source_url": _leginfo("BPC", "3041"),
    },
    {
        "citation": "Cal. Bus. & Prof. Code § 3041.3",
        "heading": "Therapeutic pharmaceutical agent (TPA) certification for optometrists",
        "hierarchy": {"code": "Business & Professions Code", "part": "Optometry (Ch. 7)"},
        "source_url": _leginfo("BPC", "3041.3"),
    },
    {
        "citation": "16 CCR § 1536",
        "heading": "State Board of Optometry — continuing education (40 hrs / 2 yrs; 50 hrs incl. 35 ocular-disease for TPA-certified)",
        "hierarchy": {"code": "Title 16 CCR", "part": "Board of Optometry (Div. 15)"},
        "source_url": _BOARD_LAWSREGS,
    },
    {
        "citation": "Cal. Bus. & Prof. Code § 2542",
        "heading": "Registered dispensing optician — contact lenses fitted/dispensed only on a valid prescription of a physician or optometrist",
        "hierarchy": {"code": "Business & Professions Code", "part": "Opticianry (Ch. 5.5)"},
        "source_url": _leginfo("BPC", "2542"),
    },
    {
        "citation": "Cal. Bus. & Prof. Code § 2550",
        "heading": "Registered dispensing optician — registration with the State Board of Optometry (definitions incl. spectacle and contact lens dispensers)",
        "hierarchy": {"code": "Business & Professions Code", "part": "Opticianry (Ch. 5.5)"},
        "source_url": _leginfo("BPC", "2550"),
    },
]


# ── us-flsa: the federal wage-hour floor (statute + the exempt-salary rule) ──
# The FLSA rate/multiplier live in statute (29 U.S.C.), not eCFR, so they are
# curated, not machine-ingestable. All universal (every US employer).
def _cornell_usc(title: str, section: str) -> str:
    return f"https://www.law.cornell.edu/uscode/text/{title}/{section}"


_FLSA: List[CuratedRow] = [
    {
        "citation": "29 U.S.C. § 206",
        "heading": "Federal minimum wage ($7.25/hr)",
        "hierarchy": {"code": "U.S. Code", "part": "FLSA"},
        "source_url": _cornell_usc("29", "206"),
    },
    {
        "citation": "29 U.S.C. § 207",
        "heading": "Overtime — 1.5× the regular rate over 40 hours in a workweek",
        "hierarchy": {"code": "U.S. Code", "part": "FLSA"},
        "source_url": _cornell_usc("29", "207"),
    },
    {
        "citation": "29 U.S.C. § 213",
        "heading": "Exemptions from minimum wage and overtime (executive, administrative, professional, outside sales)",
        "hierarchy": {"code": "U.S. Code", "part": "FLSA"},
        "source_url": _cornell_usc("29", "213"),
    },
    {
        "citation": "29 CFR § 541.600",
        "heading": "Exempt salary threshold — $684/week ($35,568/yr); the 2024 $58,656 rule was vacated in Texas v. DOL",
        "hierarchy": {"code": "29 CFR", "part": "Part 541 (white-collar exemptions)"},
        "source_url": "https://www.ecfr.gov/current/title-29/section-541.600",
    },
]


# slug → rows. Consumed by authority_ingest.ingest_curated_index.
CURATED_ROWS: Dict[str, List[CuratedRow]] = {
    "us-flsa": _FLSA,
    "ca-labor-code": _CA_LABOR,
    "ca-title-8": _TITLE8,
    "ca-title-16": _TITLE16,
}
