"""Baseline labor master-list — the enumerated "entirety" a US employer owes.

Every other coverage number in this system is emergent: `EXPECTED_REGULATION_KEYS`
is whatever the research model has produced keys for, so "is federal done?" had no
checkable answer. This module is the answer — a hand-curated, individually-cited
enumeration of the federal and California-state labor obligations a general employer
is responsible for. The `baseline` eval scores the federal + CA-state jurisdictions
directly against it.

Curation doctrine (same as `scope_registry/curated_ca.py` + the golden fixtures):
every entry cites a REAL primary source (`citation` + `authority_url`); no invented
law. `curated_by` is claude-research and the list is UNVERIFIED until a human opens
each URL and confirms the section — it enumerates *scope* (what must exist), it does
not assert the *value* (that's the grounded-research pipeline's job, audited by the
grounding suite).

Scope boundaries:
  * General private-employer obligations only. Federal-contractor-only regimes
    (EO 11246 affirmative action, Service Contract Act, Davis-Bacon) are EXCLUDED —
    they apply to a subset of employers and belong in a contractor overlay, not the
    universal baseline.
  * Each `key` MUST exist in `compliance_registry.EXPECTED_REGULATION_KEYS[category]`
    (a pure test enforces this; `baseline01` seeds any key not yet in the vocabulary).

Pure: no DB, no network, no model. `masterlist_keys()` flattens to the
`{category: frozenset(keys)}` shape the eval consumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List


@dataclass(frozen=True)
class BaselineObligation:
    key: str          # regulation key — must be in EXPECTED_REGULATION_KEYS[category]
    category: str     # a LABOR_CATEGORIES | SUPPLEMENTARY_CATEGORIES member
    citation: str     # primary-source citation, e.g. "29 U.S.C. § 207"
    authority_url: str  # server-rendered primary source (cornell LII / ecfr / leginfo)
    applies_note: str = ""  # threshold / scope note (e.g. FMLA's 50-employee floor)


def _lii_usc(title: int, section: str) -> str:
    # Cornell LII — server-rendered (grounding pipeline can actually fetch the text).
    return f"https://www.law.cornell.edu/uscode/text/{title}/{section}"


def _ecfr(title: int, part: str) -> str:
    return f"https://www.ecfr.gov/current/title-{title}/part-{part}"


def _leginfo(code: str, section: str) -> str:
    return (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
        f"?lawCode={code}&sectionNum={section}"
    )


# ── Federal general-employer labor baseline ─────────────────────────────────────
FEDERAL_LABOR_MASTERLIST: List[BaselineObligation] = [
    # FLSA — wage & hour. Key is `national_minimum_wage` to match the established
    # catalog + completeness convention (not a new `federal_minimum_wage` synonym).
    BaselineObligation("national_minimum_wage", "minimum_wage",
                       "29 U.S.C. § 206", _lii_usc(29, "206")),
    BaselineObligation("daily_weekly_overtime", "overtime",
                       "29 U.S.C. § 207", _lii_usc(29, "207"),
                       "1.5× regular rate over 40 hrs/week"),
    # Filed under minimum_wage (not overtime) to match the catalog's canonical home
    # for this obligation (scope_registry/seed.py maps 29 CFR 541 → minimum_wage).
    BaselineObligation("exempt_salary_threshold", "minimum_wage",
                       "29 C.F.R. Part 541", _ecfr(29, "541"),
                       "white-collar exemption salary + duties tests"),
    BaselineObligation("flsa_recordkeeping", "employee_classification",
                       "29 C.F.R. Part 516", _ecfr(29, "516")),
    BaselineObligation("exempt_classification", "employee_classification",
                       "29 U.S.C. § 213", _lii_usc(29, "213")),
    BaselineObligation("pump_act_lactation", "pregnancy_accommodation",
                       "29 U.S.C. § 218d", _lii_usc(29, "218d"),
                       "reasonable break time + space to express milk"),
    # FMLA
    BaselineObligation("fmla", "leave",
                       "29 C.F.R. Part 825", _ecfr(29, "825"),
                       "50+ employees within 75 mi; 12 wks unpaid"),
    # Title VII / PDA / PWFA / ADA / ADEA / GINA — anti-discrimination
    BaselineObligation("protected_classes", "anti_discrimination",
                       "42 U.S.C. § 2000e-2", _lii_usc(42, "2000e-2"),
                       "Title VII: race, color, religion, sex, national origin; 15+ employees"),
    BaselineObligation("reasonable_accommodation", "anti_discrimination",
                       "42 U.S.C. § 12112", _lii_usc(42, "12112"),
                       "ADA Title I; 15+ employees"),
    BaselineObligation("age_discrimination_adea", "anti_discrimination",
                       "29 U.S.C. § 623", _lii_usc(29, "623"),
                       "ADEA; 40+ years, 20+ employees"),
    BaselineObligation("genetic_information_gina", "anti_discrimination",
                       "42 U.S.C. § 2000ff-1", _lii_usc(42, "2000ff-1")),
    BaselineObligation("harassment_prevention_training", "anti_discrimination",
                       "29 C.F.R. Part 1604", _ecfr(29, "1604")),
    # Pregnancy Workers Fairness Act
    BaselineObligation("pregnancy_accommodation", "pregnancy_accommodation",
                       "42 U.S.C. § 2000gg-1", _lii_usc(42, "2000gg-1"),
                       "PWFA; reasonable accommodation for pregnancy; 15+ employees"),
    # Equal Pay Act
    BaselineObligation("federal_equal_pay", "equal_pay",
                       "29 U.S.C. § 206(d)", _lii_usc(29, "206")),
    # OSHA
    BaselineObligation("osha_general_duty", "workplace_safety",
                       "29 U.S.C. § 654", _lii_usc(29, "654"),
                       "general duty clause — hazard-free workplace"),
    BaselineObligation("injury_illness_recordkeeping", "workplace_safety",
                       "29 C.F.R. Part 1904", _ecfr(29, "1904"),
                       "OSHA 300/301/300A; 10+ employees unless exempt industry"),
    # WARN
    BaselineObligation("federal_warn_notice", "warn_act",
                       "29 U.S.C. § 2102", _lii_usc(29, "2102"),
                       "60-day notice; 100+ employees; mass layoff/plant closing"),
    # IRCA / I-9
    BaselineObligation("form_i9_verification", "i9_everify",
                       "8 U.S.C. § 1324a", _lii_usc(8, "1324a"),
                       "employment eligibility verification, all employers"),
    # ERISA
    BaselineObligation("spd_disclosure", "erisa_benefits",
                       "29 U.S.C. § 1022", _lii_usc(29, "1022"),
                       "summary plan description to participants"),
    BaselineObligation("form_5500", "erisa_benefits",
                       "29 C.F.R. Part 2520", _ecfr(29, "2520"),
                       "annual reporting for covered plans"),
    # COBRA
    BaselineObligation("cobra_continuation", "cobra",
                       "29 U.S.C. § 1161", _lii_usc(29, "1161"),
                       "group-health continuation; 20+ employees"),
    # NLRA
    BaselineObligation("protected_concerted_activity", "nlra_organizing",
                       "29 U.S.C. § 157", _lii_usc(29, "157"),
                       "§7 rights; applies to most private employers regardless of union"),
    # USERRA
    BaselineObligation("userra_reemployment", "userra",
                       "38 U.S.C. § 4311", _lii_usc(38, "4311"),
                       "military leave + reemployment; all employers"),
    # FCRA background checks
    BaselineObligation("fcra_disclosure_authorization", "background_checks",
                       "15 U.S.C. § 1681b(b)", _lii_usc(15, "1681b"),
                       "standalone disclosure + authorization before a consumer report"),
    BaselineObligation("adverse_action_process", "background_checks",
                       "15 U.S.C. § 1681m", _lii_usc(15, "1681m"),
                       "pre- and post-adverse-action notice"),
    # EEO-1
    BaselineObligation("eeo1_report", "eeo_reporting",
                       "29 C.F.R. Part 1602", _ecfr(29, "1602"),
                       "100+ employees (or federal contractor 50+)"),
    # Wage garnishment (CCPA Title III)
    BaselineObligation("garnishment_limits", "garnishment",
                       "15 U.S.C. § 1673", _lii_usc(15, "1673"),
                       "disposable-earnings cap + anti-discharge protection"),
]

# ── California-state general-employer labor baseline ────────────────────────────
# Mostly reuses the existing CA catalog's keys; enumerated here so CA-state is
# scored against a fixed list rather than against whatever happens to be present.
CA_STATE_LABOR_MASTERLIST: List[BaselineObligation] = [
    BaselineObligation("state_minimum_wage", "minimum_wage",
                       "Cal. Lab. Code § 1182.12", _leginfo("LAB", "1182.12")),
    BaselineObligation("daily_weekly_overtime", "overtime",
                       "Cal. Lab. Code § 510", _leginfo("LAB", "510"),
                       "daily OT >8h, double time >12h, 7th-day"),
    BaselineObligation("exempt_salary_threshold", "minimum_wage",
                       "Cal. Lab. Code § 515", _leginfo("LAB", "515")),
    BaselineObligation("meal_break", "meal_breaks",
                       "Cal. Lab. Code § 512", _leginfo("LAB", "512")),
    BaselineObligation("rest_break", "meal_breaks",
                       "8 C.C.R. § 11040", "https://www.dir.ca.gov/title8/11040.html"),
    BaselineObligation("missed_break_penalty", "meal_breaks",
                       "Cal. Lab. Code § 226.7", _leginfo("LAB", "226.7")),
    BaselineObligation("state_paid_sick_leave", "sick_leave",
                       "Cal. Lab. Code § 246", _leginfo("LAB", "246"),
                       "40 hrs / 5 days accrual (SB 616)"),
    BaselineObligation("final_pay_termination", "final_pay",
                       "Cal. Lab. Code § 201", _leginfo("LAB", "201")),
    BaselineObligation("final_pay_resignation", "final_pay",
                       "Cal. Lab. Code § 202", _leginfo("LAB", "202")),
    BaselineObligation("waiting_time_penalty", "final_pay",
                       "Cal. Lab. Code § 203", _leginfo("LAB", "203")),
    BaselineObligation("wage_notice", "pay_frequency",
                       "Cal. Lab. Code § 2810.5", _leginfo("LAB", "2810.5"),
                       "Wage Theft Prevention Act notice"),
    BaselineObligation("standard_pay_frequency", "pay_frequency",
                       "Cal. Lab. Code § 204", _leginfo("LAB", "204")),
    BaselineObligation("reporting_time_pay", "scheduling_reporting",
                       "8 C.C.R. § 11040", "https://www.dir.ca.gov/title8/11040.html"),
    BaselineObligation("state_family_leave", "leave",
                       "Cal. Gov. Code § 12945.2", _leginfo("GOV", "12945.2"),
                       "CFRA; 5+ employees (broader than FMLA)"),
    BaselineObligation("state_paid_family_leave", "leave",
                       "Cal. Unemp. Ins. Code § 3301", _leginfo("UIC", "3301")),
    BaselineObligation("pregnancy_disability_leave", "leave",
                       "Cal. Gov. Code § 12945", _leginfo("GOV", "12945")),
    BaselineObligation("mandatory_coverage", "workers_comp",
                       "Cal. Lab. Code § 3700", _leginfo("LAB", "3700"),
                       "all employers, no small-employer exemption"),
    BaselineObligation("heat_illness_prevention", "workplace_safety",
                       "8 C.C.R. § 3395", "https://www.dir.ca.gov/title8/3395.html"),
    BaselineObligation("workplace_violence_prevention", "workplace_safety",
                       "Cal. Lab. Code § 6401.9", _leginfo("LAB", "6401.9"),
                       "SB 553; WVPP required since 2024-07-01"),
    BaselineObligation("harassment_prevention_training", "anti_discrimination",
                       "Cal. Gov. Code § 12950.1", _leginfo("GOV", "12950.1"),
                       "SB 1343; 5+ employees"),
    BaselineObligation("protected_classes", "anti_discrimination",
                       "Cal. Gov. Code § 12940", _leginfo("GOV", "12940"),
                       "FEHA; 5+ employees"),
    BaselineObligation("pay_transparency", "anti_discrimination",
                       "Cal. Lab. Code § 432.3", _leginfo("LAB", "432.3"),
                       "SB 1162 pay scale on postings; 15+ employees"),
    BaselineObligation("salary_history_ban", "anti_discrimination",
                       "Cal. Lab. Code § 432.3", _leginfo("LAB", "432.3")),
]


def masterlist_keys(entries: List[BaselineObligation]) -> Dict[str, FrozenSet[str]]:
    """Flatten a master-list to `{category: frozenset(keys)}`. Used by the vocabulary
    test (every key must exist in EXPECTED_REGULATION_KEYS[category])."""
    out: Dict[str, set] = {}
    for e in entries:
        out.setdefault(e.category, set()).add(e.key)
    return {cat: frozenset(keys) for cat, keys in out.items()}


# The jurisdictions the baseline suite scores. `slug` is the STABLE key used for
# totals + result detail (display `label` may change; slug must not — downstream
# reads `federal_present` etc.).
BASELINE_JURISDICTIONS = (
    {"slug": "federal", "level": "federal", "label": "US Federal",
     "entries": FEDERAL_LABOR_MASTERLIST},
    {"slug": "ca", "level": "state", "state": "CA", "label": "California",
     "entries": CA_STATE_LABOR_MASTERLIST},
)
