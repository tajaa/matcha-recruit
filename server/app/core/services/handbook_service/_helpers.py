"""Handbook module-level helpers — scope/normalize, section + addendum builders,
requirement formatting, operational hooks, guided-question builders (J6 split)."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import html
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

import asyncpg

if TYPE_CHECKING:  # type-only: the service never depends on FastAPI at runtime
    from fastapi import BackgroundTasks

from app.config import get_settings
from app.database import get_connection
from app.core.services.storage import get_storage
from app.core.models.handbook import (
    CompanyHandbookProfileInput,
    CompanyHandbookProfileResponse,
    HandbookAcknowledgementSummary,
    HandbookChangeRequestResponse,
    HandbookCoverageByState,
    HandbookCoverageResponse,
    HandbookCoverageSummary,
    HandbookCreateRequest,
    HandbookDetailResponse,
    HandbookDistributionRecipientResponse,
    HandbookDistributionResponse,
    HandbookFreshnessCheckResponse,
    HandbookFreshnessFindingResponse,
    HandbookGuidedDraftRequest,
    HandbookGuidedDraftResponse,
    HandbookGuidedQuestion,
    HandbookGuidedSectionSuggestion,
    HandbookListItemResponse,
    HandbookMissingSectionResponse,
    HandbookPublishResponse,
    HandbookScopeInput,
    HandbookScopeResponse,
    HandbookSectionInput,
    HandbookSectionResponse,
    HandbookUpdateRequest,
    HandbookWizardDraftResponse,
)

from app.core.services.handbook_service._constants import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

__all__ = [
    "GuidedDraftRateLimitError",
    "_normalize_scope",
    "_normalize_profile",
    "_normalize_city_token",
    "_city_matches_scope",
    "_collect_state_city_scope",
    "_build_core_sections",
    "_normalize_text_snippet",
    "_format_requirement_line",
    "_requirement_to_prose",
    "_apply_most_generous_per_category",
    "_select_representative_requirements",
    "_build_state_addendum_content",
    "_build_state_sections",
    "_slugify_key",
    "_normalize_custom_sections",
    "_coerce_jurisdiction_scope",
    "_sanitize_wizard_draft_state",
    "_translate_handbook_db_error",
    "derive_handbook_scopes_from_employees",
    "_fetch_state_requirements",
    "_requirements_cover_topic",
    "_stringify_temporal",
    "_build_requirements_fingerprint",
    "_state_section_key",
    "_normalize_section_content",
    "_select_finding_source_url",
    "_select_latest_effective_date",
    "_find_missing_state_topics",
    "_validate_required_state_coverage",
    "_auto_research_missing_handbook_topics",
    "_build_template_sections",
    "_handbook_filename",
    "_get_employee_document_columns",
    "_validate_handbook_file_reference",
    "_normalize_industry",
    "_sanitize_answer_map",
    "_normalize_hook_text",
    "_extract_email",
    "_normalize_workweek_day",
    "_parse_workweek_definition",
    "_build_operational_hook_values",
    "_apply_operational_hooks_to_sections",
    "_extract_hooks_from_existing_content",
    "_apply_hooks_to_content",
    "_parse_bool_like",
    "_build_guided_question_list",
    "_filter_unanswered_questions",
    "_sanitize_guided_questions",
    "_default_profile_updates_for_industry",
    "_build_default_section_suggestions",
    "_normalize_existing_section_titles",
    "_sanitize_guided_profile_updates",
    "_sanitize_guided_sections",
    "_merge_guided_sections",
    "_extract_json_payload",
]


class GuidedDraftRateLimitError(Exception):
    """Raised when guided draft generation exceeds configured rate limits."""
def _normalize_scope(scope: HandbookScopeInput) -> dict[str, Any]:
    return {
        "state": scope.state.upper(),
        "city": scope.city,
        "zipcode": scope.zipcode,
        "location_id": scope.location_id,
    }
def _normalize_profile(profile: CompanyHandbookProfileInput) -> dict[str, Any]:
    return {
        "legal_name": profile.legal_name.strip(),
        "dba": profile.dba.strip() if profile.dba else None,
        "ceo_or_president": profile.ceo_or_president.strip(),
        "headcount": profile.headcount,
        "remote_workers": profile.remote_workers,
        "minors": profile.minors,
        "tipped_employees": profile.tipped_employees,
        "union_employees": profile.union_employees,
        "federal_contracts": profile.federal_contracts,
        "group_health_insurance": profile.group_health_insurance,
        "background_checks": profile.background_checks,
        "hourly_employees": profile.hourly_employees,
        "salaried_employees": profile.salaried_employees,
        "commissioned_employees": profile.commissioned_employees,
        "tip_pooling": profile.tip_pooling,
    }
def _normalize_city_token(value: Optional[str]) -> str:
    if not value:
        return ""
    token = re.sub(r"[^a-z0-9]+", " ", value.strip().lower())
    token = re.sub(r"\s+", " ", token).strip()
    return token
def _city_matches_scope(requirement_city: str, scoped_cities: set[str]) -> bool:
    req = _normalize_city_token(requirement_city)
    if not req or not scoped_cities:
        return False
    req_tokens = set(req.split())
    for scoped in scoped_cities:
        if req == scoped or req.startswith(f"{scoped} ") or scoped.startswith(f"{req} "):
            return True
        scoped_tokens = set(scoped.split())
        if req_tokens and scoped_tokens and (
            req_tokens.issubset(scoped_tokens) or scoped_tokens.issubset(req_tokens)
        ):
            return True
    return False
def _collect_state_city_scope(
    scopes: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[str]], dict[str, set[str]]]:
    states = sorted({(scope.get("state") or "").strip().upper() for scope in scopes if scope.get("state")})
    city_labels: dict[str, list[str]] = {}
    city_tokens: dict[str, set[str]] = {}
    for scope in scopes:
        state = (scope.get("state") or "").strip().upper()
        city = (scope.get("city") or "").strip()
        if not state or not city:
            continue
        city_labels.setdefault(state, [])
        if city not in city_labels[state]:
            city_labels[state].append(city)
        city_tokens.setdefault(state, set()).add(_normalize_city_token(city))
    return states, city_labels, city_tokens
def _build_core_sections(profile: dict[str, Any], mode: str, states: list[str]) -> list[dict[str, Any]]:
    legal_name = profile["legal_name"]
    dba = profile.get("dba")
    ceo = profile["ceo_or_president"]
    scope_desc = ", ".join([STATE_NAMES.get(s, s) for s in states]) if states else "applicable jurisdictions"
    company_ref = f"{legal_name} (DBA {dba})" if dba else legal_name
    employment_mix = []
    if profile.get("hourly_employees"):
        employment_mix.append("hourly")
    if profile.get("salaried_employees"):
        employment_mix.append("salaried")
    if profile.get("commissioned_employees"):
        employment_mix.append("commissioned")
    mix_text = ", ".join(employment_mix) if employment_mix else "varied"

    remote_clause = (
        "Remote and hybrid work arrangements are permitted for eligible roles and remain subject to business need."
        if profile.get("remote_workers")
        else "The company primarily operates in-person roles; remote arrangements require prior written approval."
    )
    minors_clause = (
        "Because the company employs minors, scheduling and duties will comply with all youth-employment limits."
        if profile.get("minors")
        else "This handbook assumes no minor employment arrangements unless policy updates are issued."
    )
    tipped_clause = (
        "Tipped positions must follow cash wage, tip-credit, and tip retention rules for each covered jurisdiction."
        if profile.get("tipped_employees")
        else "No tipped-employee programs are active unless communicated in writing."
    )
    union_clause = (
        "Where a collective bargaining agreement applies, the CBA controls in case of conflict with this handbook."
        if profile.get("union_employees")
        else "No union-specific terms apply unless a collective bargaining relationship is established."
    )
    federal_contract_clause = (
        "Federal-contract obligations may add or supersede handbook requirements for covered teams."
        if profile.get("federal_contracts")
        else "No federal-contract specific labor clauses are incorporated at this time."
    )
    coverage_clause = (
        "Group health coverage is offered to eligible employees under current plan terms."
        if profile.get("group_health_insurance")
        else "Group health coverage is not currently offered through company-sponsored plans."
    )
    background_clause = (
        "Background checks may be conducted for eligible roles in accordance with applicable law."
        if profile.get("background_checks")
        else "Background checks are not part of standard hiring or retention practices unless required by law or contract."
    )
    minors_restriction_line = (
        "Managers must follow all youth-employment hour and duty restrictions before scheduling minors."
        if profile.get("minors")
        else "If minor employees are hired in the future, youth-employment restrictions must be applied before scheduling."
    )

    sections: list[dict[str, Any]] = [
        {
            "section_key": "welcome",
            "title": "Welcome and Scope",
            "section_order": 10,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                f"This Employee Handbook is adopted by {company_ref} and applies to employees working in {scope_desc}. "
                f"{ceo} is the executive sponsor of this handbook program. "
                "This handbook states enforceable workplace rules, reporting procedures, and compliance controls. "
                "It is intended to be read with offer letters, arbitration agreements, and written policy addenda."
            ),
        },
        {
            "section_key": "employment_relationship",
            "title": "Employment Relationship",
            "section_order": 20,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employment with the company is at-will unless a written agreement signed by the Chief Executive Officer states otherwise. "
                "At-will employment means either the employee or the company may end employment at any time, with or without cause or notice, subject to applicable law. "
                f"Employment classifications currently include {mix_text} roles. "
                "No manager or supervisor may make an oral promise that changes at-will status. "
                "This handbook is not a contract of employment and does not create a guaranteed term of employment."
            ),
        },
        {
            "section_key": "equal_opportunity",
            "title": "Equal Employment Opportunity and Anti-Harassment",
            "section_order": 30,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "The company provides equal employment opportunity and prohibits discrimination, harassment, and retaliation. "
                "Employees may report concerns to any manager, Human Resources, or directly to designated reporting channels. "
                f"Primary reporting channels: email {LEGAL_OPERATIONAL_HOOKS['harassment_email']} and hotline {LEGAL_OPERATIONAL_HOOKS['harassment_hotline']}. "
                "Reports may be made by employees, applicants, contractors, or witnesses. "
                "The company will investigate promptly, maintain confidentiality to the extent possible, and prohibit retaliation for good-faith reporting or participation."
            ),
        },
        {
            "section_key": "hours_and_pay",
            "title": "Hours, Pay, and Timekeeping",
            "section_order": 40,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees must accurately record all time worked and all required meal/rest periods in the approved timekeeping system. "
                "Off-the-clock work is prohibited. Time records must be corrected in the same pay period when errors are discovered. "
                f"The standard payroll workweek runs from {LEGAL_OPERATIONAL_HOOKS['workweek_start_day']} at {LEGAL_OPERATIONAL_HOOKS['workweek_start_time']} ({LEGAL_OPERATIONAL_HOOKS['workweek_timezone']}). "
                f"Paydays follow {LEGAL_OPERATIONAL_HOOKS['payday_frequency']} with payroll cutoff anchored to {LEGAL_OPERATIONAL_HOOKS['payday_anchor']}. "
                "Overtime must be paid when worked, even if not pre-approved; unauthorized overtime may result in corrective action. "
                f"{tipped_clause} "
                f"{federal_contract_clause}"
            ),
        },
        {
            "section_key": "attendance_and_remote",
            "title": "Attendance, Work Location, and Scheduling",
            "section_order": 50,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Regular attendance and punctuality are essential job duties unless approved leave or accommodation applies. "
                "Employees must provide at least 24 hours' notice for foreseeable absences and notify their manager before shift start for unforeseeable absences. "
                "Excused absences include approved protected leave, legally protected sick leave, jury/witness duty, military leave, and approved accommodation-related absences. "
                "Unexcused absences include no-call/no-show events and absences without required notice when no legal protection applies. "
                f"{remote_clause} "
                f"{minors_clause} "
                f"{minors_restriction_line}"
            ),
        },
        {
            "section_key": "benefits_and_leave",
            "title": "Benefits and Leave",
            "section_order": 60,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Benefit eligibility and leave rights follow plan documents and applicable federal, state, and local law. "
                f"{coverage_clause} "
                f"Questions about leave eligibility, protected leave, and reasonable accommodation should be directed to {LEGAL_OPERATIONAL_HOOKS['leave_admin_email']}. "
                "No handbook provision may be interpreted to reduce statutory leave rights, paid sick leave rights, or accommodation rights."
            ),
        },
        {
            "section_key": "workplace_standards",
            "title": "Workplace Conduct and Safety",
            "section_order": 70,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees are expected to maintain professional conduct, protect confidential information, "
                "and follow all safety rules for their role and work location. "
                "Employees must report hazards, workplace violence concerns, and policy violations immediately."
            ),
        },
        {
            "section_key": "investigations",
            "title": "Investigations, Background Checks, and Corrective Action",
            "section_order": 80,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "The company may investigate policy violations and implement corrective action when needed. "
                f"{background_clause} "
                "Corrective action may include coaching, written warning, suspension, or termination, based on severity and recurrence. "
                f"{union_clause}"
            ),
        },
        {
            "section_key": "acknowledgement",
            "title": "Employee Acknowledgement",
            "section_order": 90,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "Employees must acknowledge receipt of this handbook and agree to comply with these policies. "
                "By acknowledging this handbook, employees confirm they understand reporting procedures, anti-retaliation protections, and timekeeping duties. "
                "Future updates may require renewed acknowledgement. "
                "Safe-harbor statement: if any handbook provision conflicts with applicable law, the law controls and the remaining provisions remain enforceable."
            ),
        },
    ]

    return sections
def _normalize_text_snippet(value: Optional[str], max_len: int = 220) -> str:
    if not value:
        return ""
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[:max_len].rstrip('. ')}..."
def _format_requirement_line(req: dict[str, Any], include_source: bool = False) -> str:
    title = _normalize_text_snippet(req.get("title"), max_len=140) or "Requirement"
    jurisdiction = _normalize_text_snippet(req.get("jurisdiction_name"), max_len=80)
    level = (req.get("jurisdiction_level") or "").strip().lower()
    level_suffix = f" [{level}]" if level else ""
    value = _normalize_text_snippet(req.get("current_value"), max_len=120)
    if not value:
        value = _normalize_text_snippet(req.get("description"), max_len=120) or "Refer to statutory text"
    effective = req.get("effective_date")
    effective_label = ""
    if isinstance(effective, date):
        effective_label = f"; effective {effective.isoformat()}"
    elif effective:
        effective_label = f"; effective {_normalize_text_snippet(str(effective), max_len=20)}"
    src = ""
    if include_source:
        src_url = _normalize_text_snippet(req.get("source_url"), max_len=140)
        src_name = _normalize_text_snippet(req.get("source_name"), max_len=80)
        if src_url:
            src = f"; source {src_url}"
        elif src_name:
            src = f"; source {src_name}"
    jurisdiction_label = f" ({jurisdiction}{level_suffix})" if jurisdiction else ""
    return f"- {title}{jurisdiction_label}: {value}{effective_label}{src}."
def _requirement_to_prose(req: dict[str, Any]) -> str:
    """Convert a single requirement dict into a clean, employee-facing policy sentence."""
    value = _normalize_text_snippet(req.get("current_value"), max_len=200)
    if not value:
        value = _normalize_text_snippet(req.get("description"), max_len=200)
    if not value:
        return ""
    # Ensure the sentence ends with a period.
    value = value.rstrip(". ")
    if not value:
        return ""
    return f"{value}."
def _apply_most_generous_per_category(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each (category, rate_type) group with entries at multiple jurisdiction levels,
    keep only the most employee-friendly level. Preserves all entries at the winning level
    (e.g. multiple city requirements for different selected cities)."""
    from collections import defaultdict

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    ungrouped: list[dict[str, Any]] = []

    for req in requirements:
        category = (req.get("category") or "").strip().lower()
        rate_type = req.get("rate_type")
        if not category:
            ungrouped.append(req)
            continue
        groups[(category, rate_type)].append(req)

    result: list[dict[str, Any]] = list(ungrouped)
    for (category, _rate_type), reqs in groups.items():
        # Check how many distinct jurisdiction levels exist
        levels = {(r.get("jurisdiction_level") or "").lower() for r in reqs}
        if len(levels) <= 1:
            # All at the same level (e.g. multiple cities) — keep all
            result.extend(reqs)
            continue

        if category in _NUMERIC_GENEROUS_CATEGORIES:
            # Pick the entry with the highest numeric_value, then keep all at that level
            best = max(
                reqs,
                key=lambda r: (r.get("numeric_value") or 0, _LEVEL_PRIORITY.get((r.get("jurisdiction_level") or "").lower(), 0)),
            )
            best_level = (best.get("jurisdiction_level") or "").lower()
            result.extend(r for r in reqs if (r.get("jurisdiction_level") or "").lower() == best_level)
        else:
            # Pick the most local jurisdiction level, keep all at that level
            best_priority = max(
                _LEVEL_PRIORITY.get((r.get("jurisdiction_level") or "").lower(), 0) for r in reqs
            )
            result.extend(
                r for r in reqs
                if _LEVEL_PRIORITY.get((r.get("jurisdiction_level") or "").lower(), 0) == best_priority
            )

    return result
def _select_representative_requirements(requirements: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for req in requirements:
        dedupe_key = (
            req.get("category"),
            req.get("rate_type"),
            req.get("jurisdiction_level"),
            req.get("jurisdiction_name"),
            req.get("title"),
            req.get("current_value"),
            req.get("effective_date"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        selected.append(req)
        if len(selected) >= limit:
            break
    return selected
def _build_state_addendum_content(
    state: str,
    state_name: str,
    profile: dict[str, Any],
    requirements: list[dict[str, Any]],
    selected_cities: Optional[list[str]] = None,
) -> str:
    def _category_rows(category: str) -> list[dict[str, Any]]:
        rows = [req for req in requirements if (req.get("category") or "").strip().lower() == category]
        return _select_representative_requirements(rows)

    def _other_rights_rows() -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for req in requirements:
            title = (req.get("title") or "").lower()
            description = (req.get("description") or "").lower()
            category = (req.get("category") or "").strip().lower()
            if category in ADDENDUM_CORE_CATEGORIES:
                continue
            if not any(
                marker in title or marker in description
                for marker in (
                    "lactation",
                    "pregnan",
                    "accommodation",
                    "disability",
                    "family leave",
                    "safe leave",
                    "domestic violence",
                )
            ):
                continue
            dedupe_key = (
                req.get("jurisdiction_level"),
                req.get("jurisdiction_name"),
                req.get("title"),
                req.get("current_value"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            selected.append(req)
            if len(selected) >= 4:
                break
        return selected

    def _prose_from_rows(rows: list[dict[str, Any]]) -> str:
        """Join requirement prose sentences into a single paragraph."""
        sentences = [s for s in (_requirement_to_prose(r) for r in rows) if s]
        return " ".join(sentences)

    # ── gather data ──────────────────────────────────────────────────
    min_wage_rows = _category_rows("minimum_wage")
    overtime_rows = _category_rows("overtime")
    pay_frequency_rows = _category_rows("pay_frequency")
    sick_leave_rows = _category_rows("sick_leave")
    meal_break_rows = _category_rows("meal_breaks")
    other_rights_rows = _other_rights_rows()
    final_pay_rows = _category_rows("final_pay")
    minor_work_rows = _category_rows("minor_work_permit")
    scheduling_rows = _category_rows("scheduling_reporting")

    source_refs: list[str] = []
    for req in requirements:
        source = _normalize_text_snippet(req.get("source_url"), max_len=180) or _normalize_text_snippet(
            req.get("source_name"),
            max_len=120,
        )
        if source and source not in source_refs:
            source_refs.append(source)
        if len(source_refs) >= 4:
            break

    # ── intro ────────────────────────────────────────────────────────
    paragraphs: list[str] = [
        f"This addendum applies to employees working in {state_name}. "
        "Where state and local rules differ, this addendum reflects the provision most beneficial to the employee.",
    ]

    if selected_cities:
        paragraphs.append(
            f"Covered city/local scopes in this state: {', '.join(selected_cities)}."
        )

    paragraphs.append(
        f"For questions about any provision in this addendum, contact Human Resources at "
        f"{LEGAL_OPERATIONAL_HOOKS['hr_contact_email']}, Leave Administration at "
        f"{LEGAL_OPERATIONAL_HOOKS['leave_admin_email']}, or the Harassment Reporting Hotline "
        f"at {LEGAL_OPERATIONAL_HOOKS['harassment_hotline']}."
    )

    # ── wages, overtime, and pay frequency ───────────────────────────
    wage_rows = _select_representative_requirements(
        min_wage_rows + overtime_rows + pay_frequency_rows, limit=7,
    )
    if wage_rows:
        wage_prose = _prose_from_rows(wage_rows)
        paragraphs.append(
            f"The company pays at or above the applicable minimum wage for every covered work "
            f"location and complies with all overtime and pay frequency requirements. {wage_prose}"
        )
    else:
        paragraphs.append(
            "The company pays at or above the applicable minimum wage for every covered work "
            "location and complies with all overtime and pay frequency requirements under "
            "applicable state and local law."
        )

    # ── paid sick leave ──────────────────────────────────────────────
    if sick_leave_rows:
        sick_prose = _prose_from_rows(sick_leave_rows)
        paragraphs.append(
            f"Eligible employees accrue and may use paid sick leave in accordance with "
            f"applicable law. {sick_prose} Management may not interfere with or retaliate "
            f"against the lawful use of sick leave."
        )
    else:
        paragraphs.append(
            "Eligible employees accrue and may use paid sick leave in accordance with "
            "applicable state and local law. Management may not interfere with or retaliate "
            "against the lawful use of sick leave."
        )

    # ── meal and rest breaks ─────────────────────────────────────────
    if meal_break_rows:
        meal_prose = _prose_from_rows(meal_break_rows)
        paragraphs.append(
            f"Employees are provided meal and rest break opportunities as required by law. "
            f"{meal_prose} If a required meal period or rest break is missed, the affected "
            f"employee should notify their manager or Human Resources promptly."
        )
    else:
        paragraphs.append(
            "Employees are provided meal and rest break opportunities as required by "
            "applicable state and local law. If a required meal period or rest break is "
            "missed, the affected employee should notify their manager or Human Resources "
            "promptly."
        )

    # ── accommodation and additional protected rights ────────────────
    accommodation_intro = (
        "The company provides reasonable accommodation for disability, pregnancy, and "
        "related conditions, including lactation accommodation where required by law. "
        f"Requests should be directed to {LEGAL_OPERATIONAL_HOOKS['leave_admin_email']}."
    )
    if other_rights_rows:
        rights_prose = _prose_from_rows(other_rights_rows)
        # Include each requirement's title so the coverage scorer can
        # detect topic keywords (e.g. "Lactation Accommodation").
        title_mentions = [
            _normalize_text_snippet(r.get("title"), max_len=140)
            for r in other_rights_rows
            if r.get("title")
        ]
        title_clause = ""
        if title_mentions:
            title_clause = (
                " Additional protections applicable in this jurisdiction include "
                + ", ".join(title_mentions) + "."
            )
        paragraphs.append(f"{accommodation_intro} {rights_prose}{title_clause}")
    else:
        paragraphs.append(accommodation_intro)

    # ── final pay and separation ─────────────────────────────────────
    paragraphs.append(
        "Final wages will be issued in accordance with applicable state and local "
        "final pay laws, including any accrued and unused benefits owed at separation."
    )

    # ── youth employment ─────────────────────────────────────────────
    if minor_work_rows:
        minor_prose = _prose_from_rows(minor_work_rows)
        paragraphs.append(
            f"Where minors are employed, the company complies with all youth employment "
            f"hour limits, duty restrictions, and minor work permit requirements. {minor_prose}"
        )
    else:
        paragraphs.append(
            "Where minors are employed, the company complies with all youth employment "
            "hour limits, duty restrictions, and work permit requirements under applicable "
            "state and local law."
        )

    # ── scheduling and reporting time ────────────────────────────────
    if scheduling_rows:
        sched_prose = _prose_from_rows(scheduling_rows)
        paragraphs.append(
            f"Where predictive scheduling or reporting time pay laws apply, the company "
            f"provides advance notice of schedules and compensates employees for "
            f"last-minute changes as required. {sched_prose}"
        )
    else:
        paragraphs.append(
            "Where predictive scheduling or reporting time pay laws apply, the company "
            "provides advance notice of schedules and compensates employees for "
            "last-minute changes as required by law."
        )

    # ── tip pooling ──────────────────────────────────────────────────
    if profile.get("tip_pooling"):
        paragraphs.append(
            "The company operates a tip pool that complies with all applicable state and "
            "local eligibility, notice, and distribution requirements."
        )

    # ── safe harbor ──────────────────────────────────────────────────
    paragraphs.append(
        "Nothing in this addendum is intended to reduce any right provided by "
        "federal, state, or local law. If any provision conflicts with applicable law "
        "or a collective bargaining agreement, the governing law or agreement controls "
        "and the remaining provisions continue in full effect."
    )

    # ── authoritative sources ────────────────────────────────────────
    if source_refs:
        paragraphs.append(
            "Authoritative Sources Referenced\n" + "\n".join(f"- {src}" for src in source_refs)
        )

    return "\n\n".join(paragraphs)
def _build_state_sections(
    states: list[str],
    profile: dict[str, Any],
    state_requirement_map: Optional[dict[str, list[dict[str, Any]]]] = None,
    selected_cities_by_state: Optional[dict[str, list[str]]] = None,
) -> list[dict[str, Any]]:
    state_sections: list[dict[str, Any]] = []
    for i, state in enumerate(states):
        state_name = STATE_NAMES.get(state, state)
        requirements = state_requirement_map.get(state, []) if state_requirement_map else []
        selected_cities = selected_cities_by_state.get(state, []) if selected_cities_by_state else []
        state_sections.append(
            {
                "section_key": f"state_addendum_{state.lower()}",
                "title": f"{state_name} State Addendum",
                "section_order": 200 + i,
                "section_type": "state",
                "jurisdiction_scope": {"states": [state]},
                "content": _build_state_addendum_content(
                    state,
                    state_name,
                    profile,
                    requirements,
                    selected_cities=selected_cities,
                ),
            }
        )
    return state_sections
def _slugify_key(value: str, max_len: int = 100) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or ""))
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return cleaned[:max_len]
def _normalize_custom_sections(custom_sections: list[HandbookSectionInput]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for index, section in enumerate(custom_sections):
        base_candidate = section.section_key or section.title or f"custom_{index + 1}"
        base_key = _slugify_key(base_candidate, max_len=110)
        if not base_key:
            base_key = f"custom_{index + 1}"

        key = base_key
        suffix = 2
        while key in used_keys:
            suffix_token = f"_{suffix}"
            key = f"{base_key[: max(1, 120 - len(suffix_token))]}{suffix_token}"
            suffix += 1
        used_keys.add(key)

        normalized.append(
            {
                "section_key": key,
                "title": section.title.strip(),
                "section_order": section.section_order,
                "section_type": "custom",
                "jurisdiction_scope": section.jurisdiction_scope or {},
                "content": section.content,
            }
        )
    return normalized
def _coerce_jurisdiction_scope(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}
def _sanitize_wizard_draft_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Wizard draft state must be an object")
    try:
        encoded = json.dumps(value)
    except TypeError as exc:
        raise ValueError("Wizard draft state contains unsupported values") from exc
    if len(encoded) > 500_000:
        raise ValueError("Wizard draft state exceeds max size")
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ValueError("Wizard draft state must decode to an object")
    return decoded
def _translate_handbook_db_error(exc: Exception) -> Optional[str]:
    message = str(exc).lower()
    if "handbook_sections_handbook_version_id_section_key_key" in message:
        return "Duplicate handbook section keys were detected. Update section titles and try again."
    if "value too long for type character varying" in message:
        return "One or more handbook fields are too long. Shorten the text and try again."
    if "invalid input for query argument" in message and "expected str, got dict" in message:
        return "Failed to encode handbook section metadata. Please retry."
    if 'relation "company_handbook_profiles"' in message:
        return "Handbook tables are out of date. Restart the API to apply schema updates."
    if (
        "column" in message
        and "does not exist" in message
        and (
            "company_handbook_profiles" in message
            or "handbooks" in message
            or "handbook_" in message
        )
    ):
        return "Handbook tables are out of date. Restart the API to apply schema updates."
    if 'relation "handbooks"' in message or 'relation "handbook_' in message or 'relation "handbook_wizard_drafts"' in message:
        return "Handbook tables are not available yet. Run migrations and restart the API."
    return None
async def derive_handbook_scopes_from_employees(conn, company_id: str) -> list[dict]:
    """Derive handbook scopes from active employee work locations."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT
            COALESCE(bl.state, e.work_state) AS state,
            bl.city AS city,
            e.work_location_id AS location_id
        FROM employees e
        LEFT JOIN business_locations bl ON bl.id = e.work_location_id
        WHERE e.org_id = $1
          AND e.termination_date IS NULL
          AND COALESCE(bl.state, e.work_state) IS NOT NULL
        ORDER BY state, city NULLS LAST
        """,
        company_id,
    )
    scopes: list[dict] = []
    seen: set[tuple] = set()
    for row in rows:
        state = (row["state"] or "").strip().upper()
        city = (row["city"] or "").strip() if row["city"] else None
        key = (state, city)
        if not state or key in seen:
            continue
        seen.add(key)
        scopes.append({
            "state": state,
            "city": city,
            "zipcode": None,
            "location_id": row["location_id"],
        })
    return scopes
async def _fetch_state_requirements(
    conn,
    scopes: list[dict[str, Any]],
    written_policy_only: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    normalized_states, _, selected_city_tokens_by_state = _collect_state_city_scope(scopes)
    if not normalized_states:
        return {}

    include_written_policy_filter = False
    if written_policy_only:
        try:
            include_written_policy_filter = bool(
                await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'jurisdiction_requirements'
                          AND column_name = 'requires_written_policy'
                    )
                    """
                )
            )
        except Exception as exc:
            logger.warning(
                "Unable to verify jurisdiction_requirements.requires_written_policy column; "
                "falling back to handbook coverage query without the written-policy filter: %s",
                exc,
            )
            include_written_policy_filter = False

    written_policy_clause = (
        "\n              AND ($4::boolean IS FALSE OR jr.requires_written_policy IS NOT false OR jr.category = ANY($2::varchar[]))"
        if include_written_policy_filter
        else ""
    )

    query = f"""
            SELECT
                j.state,
                jr.category,
                jr.jurisdiction_level,
                jr.jurisdiction_name,
                jr.title,
                jr.description,
                jr.current_value,
                jr.effective_date,
                jr.source_url,
                jr.source_name,
                jr.rate_type,
                jr.numeric_value,
                jr.updated_at
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = ANY($1::varchar[])
              AND jr.status = 'active'
              AND (
                jr.category = ANY($2::varchar[])
                OR jr.title ILIKE ANY($3::text[])
                OR COALESCE(jr.description, '') ILIKE ANY($3::text[])
              )
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
              {written_policy_clause}
            ORDER BY
                j.state,
                CASE jr.jurisdiction_level
                    WHEN 'state' THEN 1
                    WHEN 'county' THEN 2
                    WHEN 'city' THEN 3
                    ELSE 4
                END,
                COALESCE(jr.effective_date, CURRENT_DATE) DESC,
                COALESCE(jr.updated_at, jr.created_at) DESC
            """
    query_args: list[Any] = [
        normalized_states,
        list(ADDENDUM_CORE_CATEGORIES),
        list(ADDENDUM_KEYWORD_PATTERNS),
    ]
    if include_written_policy_filter:
        query_args.append(written_policy_only)

    try:
        rows = await conn.fetch(query, *query_args)
    except Exception as exc:
        logger.warning("Failed to fetch handbook state requirements: %s", exc)
        return {}

    by_state: dict[str, list[dict[str, Any]]] = {state: [] for state in normalized_states}
    seen_by_state: dict[str, set[tuple[Any, ...]]] = {state: set() for state in normalized_states}

    for raw_row in rows:
        row = dict(raw_row)
        state = (row.get("state") or "").strip().upper()
        if not state:
            continue
        level = (row.get("jurisdiction_level") or "").strip().lower()
        if level == "city":
            selected_city_tokens = selected_city_tokens_by_state.get(state, set())
            # Only include city-level requirements for explicitly scoped cities.
            if not selected_city_tokens:
                continue
            if not _city_matches_scope(row.get("jurisdiction_name") or "", selected_city_tokens):
                continue
        if len(by_state.setdefault(state, [])) >= 36:
            # Still collect rows whose category matches a mandatory topic so
            # the hospitality-industry validator can see all 8 required topics.
            cat = (row.get("category") or "").strip().lower()
            if cat not in MANDATORY_STATE_TOPIC_RULES:
                continue

        dedupe_key = (
            row.get("category"),
            row.get("rate_type"),
            row.get("jurisdiction_level"),
            row.get("jurisdiction_name"),
            row.get("title"),
            row.get("current_value"),
            row.get("effective_date"),
        )
        if dedupe_key in seen_by_state.setdefault(state, set()):
            continue
        seen_by_state[state].add(dedupe_key)

        by_state[state].append(row)

    for state in by_state:
        by_state[state] = _apply_most_generous_per_category(by_state[state])

    return by_state
def _requirements_cover_topic(requirements: list[dict[str, Any]], topic: str) -> bool:
    patterns = MANDATORY_STATE_TOPIC_RULES.get(topic, ())
    for req in requirements:
        haystack = " ".join(
            [
                str(req.get("category") or "").lower(),
                str(req.get("title") or "").lower(),
                str(req.get("description") or "").lower(),
            ]
        )
        if any(pattern in haystack for pattern in patterns):
            return True
    return False
def _stringify_temporal(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
def _build_requirements_fingerprint(
    state_requirement_map: dict[str, list[dict[str, Any]]],
) -> tuple[str, Optional[datetime], int]:
    records: list[dict[str, Optional[str]]] = []
    latest_updated_at: Optional[datetime] = None

    for state in sorted(state_requirement_map.keys()):
        for row in state_requirement_map.get(state, []):
            updated_at = row.get("updated_at")
            if isinstance(updated_at, datetime):
                if latest_updated_at is None or updated_at > latest_updated_at:
                    latest_updated_at = updated_at

            records.append(
                {
                    "state": state,
                    "category": _stringify_temporal(row.get("category")),
                    "jurisdiction_level": _stringify_temporal(row.get("jurisdiction_level")),
                    "jurisdiction_name": _stringify_temporal(row.get("jurisdiction_name")),
                    "title": _stringify_temporal(row.get("title")),
                    "current_value": _stringify_temporal(row.get("current_value")),
                    "effective_date": _stringify_temporal(row.get("effective_date")),
                    "source_url": _stringify_temporal(row.get("source_url")),
                    "source_name": _stringify_temporal(row.get("source_name")),
                    "updated_at": _stringify_temporal(updated_at),
                }
            )

    records.sort(
        key=lambda item: (
            item.get("state") or "",
            item.get("category") or "",
            item.get("jurisdiction_level") or "",
            item.get("jurisdiction_name") or "",
            item.get("title") or "",
            item.get("current_value") or "",
            item.get("effective_date") or "",
            item.get("updated_at") or "",
        )
    )
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest(), latest_updated_at, len(records)
def _state_section_key(state: str) -> str:
    return f"state_addendum_{state.lower()}"
def _normalize_section_content(value: Optional[str]) -> str:
    return (value or "").strip()
def _select_finding_source_url(requirements: list[dict[str, Any]]) -> Optional[str]:
    for req in requirements:
        source_url = _normalize_text_snippet(req.get("source_url"), max_len=1000)
        if source_url:
            return source_url
    return None
def _select_latest_effective_date(requirements: list[dict[str, Any]]) -> Optional[date]:
    latest_effective: Optional[date] = None
    for req in requirements:
        raw = req.get("effective_date")
        candidate: Optional[date] = None
        if isinstance(raw, datetime):
            candidate = raw.date()
        elif isinstance(raw, date):
            candidate = raw
        elif isinstance(raw, str):
            try:
                candidate = date.fromisoformat(raw[:10])
            except ValueError:
                candidate = None
        if candidate and (latest_effective is None or candidate > latest_effective):
            latest_effective = candidate
    return latest_effective
def _find_missing_state_topics(
    industry_key: str,
    states: list[str],
    state_requirement_map: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    """Return {state_code: [missing_category, ...]} for mandatory hospitality topics."""
    if industry_key not in STRICT_TEMPLATE_INDUSTRIES:
        return {}
    missing: dict[str, list[str]] = {}
    for state in states:
        requirements = state_requirement_map.get(state, [])
        state_missing = [
            topic for topic in MANDATORY_STATE_TOPIC_RULES
            if not _requirements_cover_topic(requirements, topic)
        ]
        if state_missing:
            missing[state] = state_missing
    return missing
def _validate_required_state_coverage(
    industry_key: str,
    states: list[str],
    state_requirement_map: dict[str, list[dict[str, Any]]],
    *,
    allow_fallback: bool = False,
) -> None:
    missing = _find_missing_state_topics(industry_key, states, state_requirement_map)
    if not missing:
        return

    parts = [
        f"{STATE_NAMES.get(st, st)} ({', '.join(MANDATORY_STATE_TOPIC_LABELS[t] for t in topics)})"
        for st, topics in missing.items()
    ]
    if allow_fallback:
        logger.warning("Handbook proceeding with fallback for: %s", "; ".join(parts))
        return

    raise ValueError(
        "Missing required state boilerplate coverage for hospitality handbook generation: "
        f"{'; '.join(parts)}. "
        "Run compliance refresh for the selected jurisdictions and complete legal review before creating this handbook."
    )
async def _auto_research_missing_handbook_topics(
    missing_by_state: dict[str, list[str]],
    company_id: Optional[UUID] = None,
) -> None:
    """Use Gemini + Google Search grounding to fill jurisdiction_requirements gaps.

    Only fills gaps for jurisdictions that already have data (partial coverage).
    Jurisdictions with no existing data are skipped — they require a full
    admin-initiated compliance refresh.

    If company_id is provided, also syncs the newly researched requirements
    to the company's business locations in that jurisdiction.
    """
    from app.core.services.compliance_service import (
        _refresh_repository_missing_categories,
        _load_jurisdiction_requirements,
        _jurisdiction_row_to_dict,
        _sync_requirements_to_location,
    )
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    service = get_gemini_compliance_service()

    for state, missing_topics in missing_by_state.items():
        async with get_connection() as conn:
            j_row = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = '' AND state = $1", state,
            )
            if not j_row:
                logger.info(
                    "Skipping auto-research for %s: no state-level jurisdiction exists (requires full refresh)",
                    state,
                )
                continue
            jurisdiction_id = j_row["id"]

            existing_rows = await _load_jurisdiction_requirements(conn, jurisdiction_id)
            if not existing_rows:
                logger.info(
                    "Skipping auto-research for %s: jurisdiction has no existing data (requires full refresh)",
                    state,
                )
                continue
            current_requirements = [_jurisdiction_row_to_dict(r) for r in existing_rows]

            logger.info(
                "Auto-researching %d missing handbook topics for %s: %s",
                len(missing_topics), state, ", ".join(missing_topics),
            )
            try:
                merged = await asyncio.wait_for(
                    _refresh_repository_missing_categories(
                        conn, service,
                        jurisdiction_id=jurisdiction_id,
                        city="", state=state, county=None,
                        has_local_ordinance=None,
                        current_requirements=current_requirements,
                        missing_categories=missing_topics,
                    ),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Auto-research timed out for %s", state)
                continue
            except Exception as exc:
                logger.warning("Auto-research failed for %s: %s", state, exc, exc_info=True)
                continue

            # Sync newly researched requirements to the company's locations
            if company_id and merged:
                try:
                    locations = await conn.fetch(
                        """
                        SELECT bl.id
                        FROM business_locations bl
                        JOIN jurisdictions j ON bl.jurisdiction_id = j.id
                        WHERE bl.company_id = $1
                          AND j.state = $2
                          AND bl.is_active = true
                        """,
                        company_id, state,
                    )
                    for loc in locations:
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], company_id, merged,
                            create_alerts=False,
                        )
                        logger.info(
                            "Synced auto-researched requirements to location %s: %s",
                            loc["id"], sync_result,
                        )
                except Exception as sync_exc:
                    logger.warning(
                        "Failed to sync auto-researched data to company locations for %s: %s",
                        state, sync_exc, exc_info=True,
                    )
def _build_template_sections(
    mode: str,
    scopes: list[dict[str, Any]],
    profile: dict[str, Any],
    custom_sections: list[HandbookSectionInput],
    industry_key: str = "general",
    state_requirement_map: Optional[dict[str, list[dict[str, Any]]]] = None,
    guided_answers: Optional[dict[str, str]] = None,
    allow_fallback: bool = False,
) -> list[dict[str, Any]]:
    unique_states, selected_cities_by_state, _ = _collect_state_city_scope(scopes)
    _validate_required_state_coverage(industry_key, unique_states, state_requirement_map or {}, allow_fallback=allow_fallback)
    base_sections = _build_core_sections(profile, mode, unique_states)
    state_sections = _build_state_sections(
        unique_states,
        profile,
        state_requirement_map,
        selected_cities_by_state=selected_cities_by_state,
    )
    custom = _normalize_custom_sections(custom_sections)
    sections = sorted(base_sections + state_sections + custom, key=lambda item: item["section_order"])
    hook_values = _build_operational_hook_values(profile, guided_answers or {})
    return _apply_operational_hooks_to_sections(sections, hook_values)
def _handbook_filename(title: str, version_number: int) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    sanitized = sanitized or "handbook"
    return f"{sanitized}-v{version_number}.pdf"
async def _get_employee_document_columns(conn) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employee_documents'
        """
    )
    return {row["column_name"] for row in rows}
def _validate_handbook_file_reference(file_url: Optional[str]) -> None:
    if not file_url:
        return
    storage = get_storage()
    if not storage.is_supported_storage_path(file_url):
        raise ValueError("Invalid handbook file reference")
def _normalize_industry(raw_industry: Optional[str], company_industry: Optional[str]) -> str:
    candidate = (raw_industry or company_industry or "general").strip().lower()
    candidate = re.sub(r"[\s\-_]+", " ", candidate)
    if not candidate:
        return "general"

    if candidate in GUIDED_INDUSTRY_PLAYBOOK:
        return candidate

    for token, normalized in GUIDED_INDUSTRY_ALIASES.items():
        if token in candidate:
            return normalized

    return "general"
def _sanitize_answer_map(raw_answers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in (raw_answers or {}).items():
        clean_key = re.sub(r"[^a-z0-9_]", "_", (key or "").strip().lower())
        clean_key = re.sub(r"_+", "_", clean_key).strip("_")
        if not clean_key:
            continue
        clean_value = (value or "").strip()
        if clean_value:
            sanitized[clean_key] = clean_value[:500]
    return sanitized
def _normalize_hook_text(value: Optional[str], max_len: int = 160) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\[[A-Z0-9_]+\]", cleaned):
        return None
    return cleaned[:max_len]
def _extract_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = EMAIL_PATTERN.search(value)
    if not match:
        return None
    return match.group(0)
def _normalize_workweek_day(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    token = re.sub(r"[^a-z]", "", value.strip().lower())
    if not token:
        return None
    return WORKWEEK_DAY_ALIASES.get(token)
def _parse_workweek_definition(value: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    cleaned = _normalize_hook_text(value, max_len=120)
    if not cleaned:
        return None, None, None

    day_match = re.search(
        r"\b(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
        cleaned,
        re.IGNORECASE,
    )
    day = _normalize_workweek_day(day_match.group(0) if day_match else None)

    time_match = WORKWEEK_TIME_PATTERN.search(cleaned)
    time_value = _normalize_hook_text(time_match.group(1) if time_match else None, max_len=30)

    timezone_match = WORKWEEK_TIMEZONE_PATTERN.search(cleaned)
    timezone_value = _normalize_hook_text(timezone_match.group(1).upper() if timezone_match else None, max_len=20)

    return day, time_value, timezone_value
def _build_operational_hook_values(
    profile: dict[str, Any],
    answers: dict[str, str],
) -> dict[str, str]:
    safe_answers = _sanitize_answer_map(answers)

    hr_answer = safe_answers.get("hr_contact_email")
    leave_answer = safe_answers.get("leave_admin_email")
    hotline_answer = safe_answers.get("harassment_hotline")
    harassment_email_answer = (
        safe_answers.get("harassment_email")
        or safe_answers.get("harassment_reporting_email")
    )

    workweek_definition_answer = safe_answers.get("workweek_definition")
    parsed_day, parsed_time, parsed_timezone = _parse_workweek_definition(workweek_definition_answer)
    workweek_start_day = _normalize_workweek_day(safe_answers.get("workweek_start_day")) or parsed_day
    workweek_start_time = _normalize_hook_text(safe_answers.get("workweek_start_time"), max_len=30) or parsed_time
    workweek_timezone = (
        _normalize_hook_text(safe_answers.get("workweek_timezone"), max_len=20)
        or parsed_timezone
    )

    payday_frequency_answer = (
        safe_answers.get("payday_frequency")
        or safe_answers.get("pay_frequency")
        or safe_answers.get("payroll_frequency")
    )
    payday_anchor_answer = (
        safe_answers.get("payday_anchor")
        or safe_answers.get("payday_anchor_day")
        or safe_answers.get("payday_day")
    )
    attendance_notice_answer = safe_answers.get("attendance_notice_window")
    legal_owner_answer = safe_answers.get("legal_owner") or safe_answers.get("legal_review_owner")

    hr_contact_email = _extract_email(hr_answer) or _normalize_hook_text(hr_answer, max_len=120)
    leave_admin_email = _extract_email(leave_answer) or _normalize_hook_text(leave_answer, max_len=120)
    harassment_hotline = _normalize_hook_text(hotline_answer, max_len=120)
    harassment_email = (
        _extract_email(harassment_email_answer)
        or _extract_email(hotline_answer)
        or _extract_email(hr_answer)
        or _normalize_hook_text(harassment_email_answer, max_len=120)
        or _normalize_hook_text(hr_answer, max_len=120)
    )
    payday_frequency = _normalize_hook_text(payday_frequency_answer, max_len=80)
    payday_anchor = _normalize_hook_text(payday_anchor_answer, max_len=80)
    attendance_notice_window = _normalize_hook_text(attendance_notice_answer, max_len=120)
    legal_owner = (
        _normalize_hook_text(legal_owner_answer, max_len=120)
        or _normalize_hook_text(profile.get("ceo_or_president"), max_len=120)
        or _normalize_hook_text(profile.get("legal_name"), max_len=120)
    )

    fallback_values = {
        LEGAL_OPERATIONAL_HOOKS["hr_contact_email"]: "the designated HR contact channel",
        LEGAL_OPERATIONAL_HOOKS["leave_admin_email"]: "the designated leave and accommodation contact channel",
        LEGAL_OPERATIONAL_HOOKS["harassment_hotline"]: "the designated harassment reporting channel",
        LEGAL_OPERATIONAL_HOOKS["harassment_email"]: "the designated harassment reporting email channel",
        LEGAL_OPERATIONAL_HOOKS["workweek_start_day"]: "the designated workweek start day",
        LEGAL_OPERATIONAL_HOOKS["workweek_start_time"]: "the designated workweek start time",
        LEGAL_OPERATIONAL_HOOKS["workweek_timezone"]: "local time",
        LEGAL_OPERATIONAL_HOOKS["payday_frequency"]: "the company's standard payroll cadence",
        LEGAL_OPERATIONAL_HOOKS["payday_anchor"]: "the designated payroll anchor day",
        LEGAL_OPERATIONAL_HOOKS["legal_owner"]: "designated company leadership",
        ATTENDANCE_NOTICE_WINDOW_HOOK: "as much advance notice as practicable",
    }

    resolved_values = {
        LEGAL_OPERATIONAL_HOOKS["hr_contact_email"]: hr_contact_email,
        LEGAL_OPERATIONAL_HOOKS["leave_admin_email"]: leave_admin_email,
        LEGAL_OPERATIONAL_HOOKS["harassment_hotline"]: harassment_hotline,
        LEGAL_OPERATIONAL_HOOKS["harassment_email"]: harassment_email,
        LEGAL_OPERATIONAL_HOOKS["workweek_start_day"]: workweek_start_day,
        LEGAL_OPERATIONAL_HOOKS["workweek_start_time"]: workweek_start_time,
        LEGAL_OPERATIONAL_HOOKS["workweek_timezone"]: workweek_timezone,
        LEGAL_OPERATIONAL_HOOKS["payday_frequency"]: payday_frequency,
        LEGAL_OPERATIONAL_HOOKS["payday_anchor"]: payday_anchor,
        LEGAL_OPERATIONAL_HOOKS["legal_owner"]: legal_owner,
        ATTENDANCE_NOTICE_WINDOW_HOOK: attendance_notice_window,
    }

    return {
        token: (resolved_values.get(token) or fallback)
        for token, fallback in fallback_values.items()
    }
def _apply_operational_hooks_to_sections(
    sections: list[dict[str, Any]],
    hook_values: dict[str, str],
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for section in sections:
        content = section.get("content")
        if not isinstance(content, str) or not content:
            hydrated.append(section)
            continue

        resolved_content = content
        for token, replacement in hook_values.items():
            if token in resolved_content:
                resolved_content = resolved_content.replace(token, replacement)
        hydrated.append({**section, "content": resolved_content})
    return hydrated
def _extract_hooks_from_existing_content(
    template_content: str,
    existing_content: str,
    hook_tokens: list[str],
) -> dict[str, str]:
    extracted = {}
    for token in hook_tokens:
        idx = template_content.find(token)
        if idx < 0:
            continue
        ctx_before = template_content[max(0, idx - 60):idx]
        ctx_after = template_content[idx + len(token):idx + len(token) + 60]
        before_snippet = ctx_before[-25:] if len(ctx_before) >= 25 else ctx_before
        after_snippet = ctx_after[:25] if len(ctx_after) >= 25 else ctx_after
        if not before_snippet or not after_snippet:
            continue
        before_pos = existing_content.find(before_snippet)
        if before_pos < 0:
            continue
        value_start = before_pos + len(before_snippet)
        after_pos = existing_content.find(after_snippet, value_start)
        if after_pos <= value_start:
            continue
        value = existing_content[value_start:after_pos].strip()
        if value and value != token:
            extracted[token] = value
    return extracted
def _apply_hooks_to_content(content: str, hook_values: dict[str, str]) -> str:
    """Replace operational hook placeholders in a single content string."""
    for token, replacement in hook_values.items():
        if token in content:
            content = content.replace(token, replacement)
    return content
def _parse_bool_like(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None
def _build_guided_question_list(industry_key: str) -> list[dict[str, Any]]:
    playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, GUIDED_INDUSTRY_PLAYBOOK["general"])
    questions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for question in [*GUIDED_COMMON_QUESTIONS, *playbook.get("questions", [])]:
        question_id = (question.get("id") or "").strip().lower()
        if not question_id or question_id in seen_ids:
            continue
        seen_ids.add(question_id)
        questions.append(
            {
                "id": question_id,
                "question": (question.get("question") or "").strip(),
                "placeholder": (question.get("placeholder") or "").strip() or None,
                "required": bool(question.get("required", True)),
            }
        )
    return questions
def _filter_unanswered_questions(
    questions: list[dict[str, Any]],
    answers: dict[str, str],
) -> list[dict[str, Any]]:
    unanswered: list[dict[str, Any]] = []
    for question in questions:
        question_id = question.get("id")
        if not question_id:
            continue
        if question_id not in answers or not answers[question_id].strip():
            unanswered.append(question)
    return unanswered
def _sanitize_guided_questions(raw_questions: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, question in enumerate(raw_questions or []):
        if not isinstance(question, dict):
            continue
        raw_id = str(question.get("id") or f"follow_up_{idx + 1}").strip().lower()
        clean_id = re.sub(r"[^a-z0-9_]", "_", raw_id)
        clean_id = re.sub(r"_+", "_", clean_id).strip("_")
        if not clean_id or clean_id in seen_ids:
            continue
        text = str(question.get("question") or "").strip()
        if len(text) < 4:
            continue
        placeholder = str(question.get("placeholder") or "").strip() or None
        required = _parse_bool_like(question.get("required"))
        sanitized.append(
            {
                "id": clean_id[:80],
                "question": text[:500],
                "placeholder": placeholder[:255] if placeholder else None,
                "required": required if required is not None else True,
            }
        )
        seen_ids.add(clean_id)
    return sanitized
def _default_profile_updates_for_industry(
    industry_key: str,
    normalized_profile: dict[str, Any],
) -> dict[str, Any]:
    playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, GUIDED_INDUSTRY_PLAYBOOK["general"])
    defaults = playbook.get("profile_defaults", {})
    updates: dict[str, Any] = {}
    for key, value in defaults.items():
        if key in GUIDED_PROFILE_BOOL_KEYS and bool(normalized_profile.get(key)) != bool(value):
            updates[key] = bool(value)
    return updates
def _build_default_section_suggestions(industry_key: str) -> list[dict[str, Any]]:
    playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, GUIDED_INDUSTRY_PLAYBOOK["general"])
    sections = playbook.get("sections", [])
    suggested: list[dict[str, Any]] = []
    for idx, section in enumerate(sections):
        title = (section.get("title") or "").strip()
        content = (section.get("content") or "").strip()
        if not title or not content:
            continue
        suggested.append(
            {
                "section_key": _slugify_key(f"guided_{industry_key}_{title}", max_len=120) or f"guided_{industry_key}_{idx + 1}",
                "title": title[:255],
                "content": content,
                "section_order": 300 + idx,
                "section_type": "custom",
                "jurisdiction_scope": {},
            }
        )
    return suggested
def _normalize_existing_section_titles(sections: list[Any]) -> set[str]:
    normalized: set[str] = set()
    for section in sections or []:
        title = ""
        if isinstance(section, dict):
            title = str(section.get("title") or "")
        else:
            title = str(getattr(section, "title", "") or "")
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if key:
            normalized.add(key)
    return normalized
def _sanitize_guided_profile_updates(
    updates: dict[str, Any],
    normalized_profile: dict[str, Any],
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (updates or {}).items():
        if key in GUIDED_PROFILE_BOOL_KEYS:
            parsed_bool = _parse_bool_like(value)
            if parsed_bool is not None:
                sanitized[key] = parsed_bool
            continue
        if key in GUIDED_PROFILE_NUMERIC_KEYS:
            try:
                numeric = int(value)
                if numeric >= 0 and numeric != normalized_profile.get(key):
                    sanitized[key] = numeric
            except (TypeError, ValueError):
                continue
    return sanitized
def _sanitize_guided_sections(raw_sections: list[Any], start_order: int = 320) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for idx, section in enumerate(raw_sections or []):
        if not isinstance(section, dict):
            continue
        title = (section.get("title") or "").strip()
        content = (section.get("content") or "").strip()
        if not title or not content:
            continue
        provided_key = (section.get("section_key") or "").strip()
        safe_key = _slugify_key(provided_key or f"guided_custom_{title}", max_len=120) or f"guided_custom_{idx + 1}"
        order_value = section.get("section_order")
        try:
            order = int(order_value)
        except (TypeError, ValueError):
            order = start_order + idx
        sanitized.append(
            {
                "section_key": safe_key,
                "title": title[:255],
                "content": content,
                "section_order": max(start_order, order),
                "section_type": "custom",
                "jurisdiction_scope": {},
            }
        )
    return sanitized
def _merge_guided_sections(
    existing_custom_sections: list[Any],
    baseline_sections: list[dict[str, Any]],
    ai_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen_titles = _normalize_existing_section_titles(existing_custom_sections)
    merged: list[dict[str, Any]] = []
    for section in [*baseline_sections, *ai_sections]:
        title_key = re.sub(r"[^a-z0-9]+", " ", (section.get("title") or "").lower()).strip()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        merged.append(section)
    return merged
def _extract_json_payload(raw_text: str) -> Optional[dict[str, Any]]:
    if not raw_text:
        return None
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None
