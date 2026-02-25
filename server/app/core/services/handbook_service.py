import asyncio
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import html
import re
from typing import Any, Optional
from uuid import UUID

import asyncpg

from ...config import get_settings
from ...database import get_connection
from .storage import get_storage
from ..models.handbook import (
    CompanyHandbookProfileInput,
    CompanyHandbookProfileResponse,
    HandbookAcknowledgementSummary,
    HandbookChangeRequestResponse,
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
    HandbookPublishResponse,
    HandbookScopeInput,
    HandbookScopeResponse,
    HandbookSectionInput,
    HandbookSectionResponse,
    HandbookUpdateRequest,
    HandbookWizardDraftResponse,
)


STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

ADDENDUM_CORE_CATEGORIES = (
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
)

ADDENDUM_FALLBACK_REVIEW_LINE = (
    "No verified statutory entries were found in the compliance repository for this topic. "
    "Run a compliance refresh and complete legal review before publishing."
)

ADDENDUM_KEYWORD_PATTERNS = (
    "%lactation%",
    "%pregnan%",
    "%disability benefit%",
    "%disability insurance%",
    "%family leave%",
    "%paid family%",
    "%reasonable accommodation%",
    "%anti-retaliation%",
    "%domestic violence%",
)

STRICT_TEMPLATE_INDUSTRIES = {"hospitality"}

MANDATORY_STATE_TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "minimum_wage": ("minimum_wage", "minimum wage", "wage floor"),
    "overtime": ("overtime", "ot", "time and a half"),
    "pay_frequency": ("pay_frequency", "pay frequency", "payday", "pay period"),
    "sick_leave": ("sick_leave", "paid sick", "sick leave"),
    "meal_breaks": ("meal_break", "meal period", "rest break", "meal and rest"),
}

MANDATORY_STATE_TOPIC_LABELS: dict[str, str] = {
    "minimum_wage": "minimum wage",
    "overtime": "overtime",
    "pay_frequency": "pay frequency",
    "sick_leave": "paid sick leave",
    "meal_breaks": "meal/rest breaks",
}

LEGAL_OPERATIONAL_HOOKS = {
    "hr_contact_email": "[HR_CONTACT_EMAIL]",
    "leave_admin_email": "[LEAVE_ADMIN_EMAIL]",
    "harassment_hotline": "[HARASSMENT_REPORTING_HOTLINE]",
    "harassment_email": "[HARASSMENT_REPORTING_EMAIL]",
    "workweek_start_day": "[WORKWEEK_START_DAY]",
    "workweek_start_time": "[WORKWEEK_START_TIME]",
    "workweek_timezone": "[WORKWEEK_TIMEZONE]",
    "payday_frequency": "[PAYDAY_FREQUENCY]",
    "payday_anchor": "[PAYDAY_ANCHOR_DAY]",
    "legal_owner": "[LEGAL_REVIEW_OWNER]",
}

ATTENDANCE_NOTICE_WINDOW_HOOK = "[ATTENDANCE_NOTICE_WINDOW]"

WORKWEEK_DAY_ALIASES = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "weds": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
}

WORKWEEK_TIME_PATTERN = re.compile(
    r"\b((?:[01]?\d|2[0-3])(?::[0-5]\d)?\s?(?:AM|PM)?)\b",
    re.IGNORECASE,
)
WORKWEEK_TIMEZONE_PATTERN = re.compile(
    r"\b(PT|PST|PDT|MT|MST|MDT|CT|CST|CDT|ET|EST|EDT|UTC(?:[+-]\d{1,2})?|GMT(?:[+-]\d{1,2})?)\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

GUIDED_PROFILE_BOOL_KEYS = {
    "remote_workers",
    "minors",
    "tipped_employees",
    "union_employees",
    "federal_contracts",
    "group_health_insurance",
    "background_checks",
    "hourly_employees",
    "salaried_employees",
    "commissioned_employees",
    "tip_pooling",
}

GUIDED_PROFILE_NUMERIC_KEYS = {"headcount"}

GUIDED_COMMON_QUESTIONS = [
    {
        "id": "hr_contact_email",
        "question": "What email should employees use for HR policy questions?",
        "placeholder": "hr@company.com",
        "required": True,
    },
    {
        "id": "leave_admin_email",
        "question": "What email should employees use for leave and accommodation requests?",
        "placeholder": "leave@company.com",
        "required": True,
    },
    {
        "id": "harassment_hotline",
        "question": "What hotline number or reporting channel should be listed for harassment complaints?",
        "placeholder": "24/7 hotline number or internal reporting channel",
        "required": True,
    },
    {
        "id": "harassment_email",
        "question": "What email should be listed as a harassment reporting channel?",
        "placeholder": "hr-reports@company.com",
        "required": True,
    },
    {
        "id": "workweek_definition",
        "question": "When does your payroll workweek start (day, time, and timezone)?",
        "placeholder": "Sunday 12:00 AM PT",
        "required": True,
    },
    {
        "id": "payday_frequency",
        "question": "What payroll cadence applies for regular paydays?",
        "placeholder": "e.g., weekly or biweekly",
        "required": True,
    },
    {
        "id": "payday_anchor",
        "question": "What day should be used as the payroll anchor/cutoff reference?",
        "placeholder": "e.g., Friday",
        "required": True,
    },
    {
        "id": "attendance_notice_window",
        "question": "What call-out notice window should apply for foreseeable absences?",
        "placeholder": "24 hours advance notice",
        "required": True,
    },
]

GUIDED_INDUSTRY_PLAYBOOK = {
    "general": {
        "label": "General Employer",
        "summary": "General employment baseline with enforceable reporting, wage/hour, leave, and anti-retaliation controls.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "discipline_escalation_matrix",
                "question": "How should corrective action escalate (coaching, written warning, suspension, termination)?",
                "placeholder": "Define standard escalation path",
                "required": False,
            },
            {
                "id": "manager_training_frequency",
                "question": "How often should managers complete policy and anti-retaliation training?",
                "placeholder": "e.g., annually",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Reporting and Escalation Protocol",
                "content": (
                    "Employees may report policy concerns to supervisors, Human Resources at [HR_CONTACT_EMAIL], "
                    "or through [HARASSMENT_REPORTING_HOTLINE]. Reports may be made without fear of retaliation. "
                    "All managers must escalate complaints to HR within one business day."
                ),
            },
            {
                "title": "Attendance and Absence Control Matrix",
                "content": (
                    "Foreseeable absences require at least [ATTENDANCE_NOTICE_WINDOW] notice unless a protected leave law applies. "
                    "Unforeseeable absences must be reported before shift start. "
                    "Excused and unexcused absences are evaluated under company policy and applicable sick leave law."
                ),
            },
        ],
    },
    "hospitality": {
        "label": "Hospitality / Restaurants",
        "summary": "Adds tipped-employee controls, service-shift scheduling, and tip-pool governance expectations.",
        "profile_defaults": {
            "hourly_employees": True,
            "tipped_employees": True,
            "tip_pooling": True,
        },
        "questions": [
            {
                "id": "tip_credit_policy",
                "question": "Do you use tip credit by location, and if so, where?",
                "placeholder": "State/local rules where tip credit is used",
                "required": True,
            },
            {
                "id": "tip_pool_roles",
                "question": "Which job roles are included/excluded from tip pooling?",
                "placeholder": "Servers, bartenders, bussers included; managers excluded",
                "required": True,
            },
            {
                "id": "service_cutoff_reporting",
                "question": "What same-day escalation process applies to guest incidents and workplace complaints?",
                "placeholder": "Who must be notified and within what timeframe",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Tipped Employee and Tip Pool Compliance",
                "content": (
                    "Tip ownership remains with employees unless a lawful tip pool applies. "
                    "Managers and supervisors may not retain employee tips. "
                    "Tip pool eligibility and distribution must match state/local law and the approved role matrix."
                ),
            },
            {
                "title": "Shift Scheduling and Rest Period Controls",
                "content": (
                    "Scheduling managers must provide compliant meal/rest opportunities and avoid off-the-clock prep or close-out work. "
                    "Shift swaps require manager approval and documented coverage confirmation."
                ),
            },
        ],
    },
    "healthcare": {
        "label": "Healthcare",
        "summary": "Adds patient-facing conduct controls, credentialing checks, and accommodation/escalation expectations.",
        "profile_defaults": {
            "hourly_employees": True,
            "background_checks": True,
            "group_health_insurance": True,
        },
        "questions": [
            {
                "id": "credentialing_review_owner",
                "question": "Who owns credential/licensure verification and escalation for lapses?",
                "placeholder": "Department + role",
                "required": True,
            },
            {
                "id": "patient_safety_reporting_window",
                "question": "What is the required reporting window for patient safety or workplace safety incidents?",
                "placeholder": "e.g., immediate verbal report + written report within 24h",
                "required": True,
            },
        ],
        "sections": [
            {
                "title": "Credentialing and Scope-of-Practice Compliance",
                "content": (
                    "Employees must perform duties within their active licensure and scope-of-practice limits. "
                    "Managers must verify active credentials before assignment changes and escalate lapses immediately."
                ),
            },
            {
                "title": "Patient Safety and Non-Retaliation Reporting",
                "content": (
                    "Employees must report patient safety and workplace safety concerns immediately through established channels. "
                    "Good-faith safety reporting is protected from retaliation."
                ),
            },
        ],
    },
    "retail": {
        "label": "Retail",
        "summary": "Adds shift scheduling, timekeeping integrity, and customer-floor conduct controls for retail operations.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "opening_closing_checklist",
                "question": "What opening/closing checklist controls should be mandatory for timekeeping and safety?",
                "placeholder": "Clock-in/out, cash count, alarm check, safety walkthrough",
                "required": False,
            },
            {
                "id": "loss_prevention_escalation",
                "question": "How should suspected theft, violence, or safety incidents be escalated?",
                "placeholder": "Escalation owner and response timeline",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Store Shift Compliance Controls",
                "content": (
                    "Opening and closing activities must be completed on the clock. "
                    "Managers must verify break compliance, time edits, and end-of-shift handoff records each day."
                ),
            },
            {
                "title": "Customer-Facing Conduct and Incident Escalation",
                "content": (
                    "Employees must de-escalate customer conflicts and immediately report threats, violence, or discriminatory behavior. "
                    "Serious incidents must be escalated to leadership and HR without delay."
                ),
            },
        ],
    },
    "manufacturing": {
        "label": "Manufacturing / Warehouse",
        "summary": "Adds safety-critical controls, shift handoff requirements, and incident escalation for operational sites.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "safety_shutdown_authority",
                "question": "Who can stop production for safety and how is restart approval handled?",
                "placeholder": "Role/title + restart authority",
                "required": True,
            },
            {
                "id": "ppe_enforcement_protocol",
                "question": "What PPE enforcement and corrective action protocol should apply?",
                "placeholder": "Required PPE and escalation sequence",
                "required": True,
            },
        ],
        "sections": [
            {
                "title": "Safety-Critical Work and Stop-Work Authority",
                "content": (
                    "Any employee may stop work when an imminent safety hazard exists. "
                    "Operations may resume only after hazard review and documented management authorization."
                ),
            },
            {
                "title": "Shift Handoff, Lockout/Tagout, and Incident Reporting",
                "content": (
                    "Shift transitions must include documented equipment status, outstanding hazards, and lockout/tagout controls where applicable. "
                    "Injuries, near misses, and safety concerns must be reported immediately."
                ),
            },
        ],
    },
    "technology": {
        "label": "Technology / Professional Services",
        "summary": "Adds remote-work governance, data security expectations, and responsive investigation channels.",
        "profile_defaults": {
            "remote_workers": True,
            "salaried_employees": True,
        },
        "questions": [
            {
                "id": "remote_work_jurisdiction_tracking",
                "question": "How should employees report work-location changes for tax and compliance tracking?",
                "placeholder": "Notice window + approval workflow",
                "required": True,
            },
            {
                "id": "security_incident_reporting_window",
                "question": "What is the response window for suspected data/privacy incidents?",
                "placeholder": "e.g., immediate to security@company.com",
                "required": True,
            },
        ],
        "sections": [
            {
                "title": "Remote Work Location and Payroll Compliance",
                "content": (
                    "Employees must obtain approval before changing primary work location across state lines. "
                    "Location changes must be reported promptly to maintain wage/hour, tax, and leave-law compliance."
                ),
            },
            {
                "title": "Data Security, Privacy, and Investigations",
                "content": (
                    "Employees must protect confidential and personal data under company security policies. "
                    "Suspected privacy or security incidents must be reported immediately through approved channels."
                ),
            },
        ],
    },
}

GUIDED_INDUSTRY_ALIASES = {
    "restaurant": "hospitality",
    "hospitality": "hospitality",
    "food": "hospitality",
    "hotel": "hospitality",
    "health": "healthcare",
    "medical": "healthcare",
    "clinic": "healthcare",
    "retail": "retail",
    "store": "retail",
    "shop": "retail",
    "warehouse": "manufacturing",
    "manufacturing": "manufacturing",
    "industrial": "manufacturing",
    "technology": "technology",
    "software": "technology",
    "saas": "technology",
    "professional services": "technology",
    "consulting": "technology",
}


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
            "section_key": "custom_policy_responsibility",
            "title": "Employer-Custom Policy Responsibility",
            "section_order": 85,
            "section_type": "core",
            "jurisdiction_scope": {"mode": mode, "states": states},
            "content": (
                "State and city addenda in this handbook are generated from verified jurisdiction requirements and are limited to baseline statutory controls. "
                "Any employer-authored custom sections, culture language, operating standards, or benefit promises are drafted at employer direction and remain the employer's legal responsibility. "
                "The employer must obtain legal review before publishing or enforcing custom handbook language."
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

    min_wage_rows = _category_rows("minimum_wage")
    overtime_rows = _category_rows("overtime")
    pay_frequency_rows = _category_rows("pay_frequency")
    sick_leave_rows = _category_rows("sick_leave")
    meal_break_rows = _category_rows("meal_breaks")
    other_rights_rows = _other_rights_rows()

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

    city_rows = [
        req for req in requirements if (req.get("jurisdiction_level") or "").strip().lower() == "city"
    ]

    lines: list[str] = [
        f"This addendum applies to employees working in {state_name}.",
        "Where state and local rules differ, the rule that provides greater employee protection controls.",
        (
            f"Operational contacts: Human Resources {LEGAL_OPERATIONAL_HOOKS['hr_contact_email']}; "
            f"Leave Administration {LEGAL_OPERATIONAL_HOOKS['leave_admin_email']}; "
            f"Harassment Reporting Hotline {LEGAL_OPERATIONAL_HOOKS['harassment_hotline']}."
        ),
        "",
    ]

    if selected_cities:
        lines.append(f"Covered city/local scopes in this state: {', '.join(selected_cities)}.")
        if not city_rows:
            lines.append(
                "No city-specific statutory entries were found in the compliance repository for the selected city scopes. "
                "Run a compliance refresh and complete legal review for local ordinance coverage before publication."
            )
    else:
        lines.append(
            "No city-specific scope is configured for this state in this handbook draft. "
            "If local ordinances apply, add city-level addenda before publication."
        )

    lines.extend(
        [
        "1) Wage, Overtime, and Pay Frequency Controls",
        "Payroll must apply current minimum wage, overtime, and pay-frequency requirements for each covered work location.",
    ])

    wage_rows = _select_representative_requirements(min_wage_rows + overtime_rows + pay_frequency_rows, limit=7)
    if wage_rows:
        lines.extend(_format_requirement_line(req) for req in wage_rows)
    else:
        lines.append(f"- {ADDENDUM_FALLBACK_REVIEW_LINE}")

    lines.extend([
        "",
        "2) Paid Sick Leave",
        (
            "Eligible employees accrue and use paid sick leave under controlling state/local law. "
            "Managers may not interfere with or retaliate against lawful sick leave use."
        ),
    ])
    if sick_leave_rows:
        lines.extend(_format_requirement_line(req) for req in sick_leave_rows)
    else:
        lines.append(f"- {ADDENDUM_FALLBACK_REVIEW_LINE}")

    lines.extend([
        "",
        "3) Meal and Rest Break Requirements",
        "Scheduling managers must provide meal/rest opportunities and premium-pay remedies where required by law.",
    ])
    if meal_break_rows:
        lines.extend(_format_requirement_line(req) for req in meal_break_rows)
    else:
        lines.append(f"- {ADDENDUM_FALLBACK_REVIEW_LINE}")

    lines.extend([
        "",
        "4) Accommodation and Additional Protected Rights",
        (
            "The company provides reasonable accommodation for disability, pregnancy, and related conditions, "
            "including lactation accommodation where required by law. "
            f"Requests should be sent to {LEGAL_OPERATIONAL_HOOKS['leave_admin_email']}."
        ),
    ])
    if other_rights_rows:
        lines.extend(_format_requirement_line(req) for req in other_rights_rows)
    else:
        lines.append(
            "- Lactation, disability-benefit, and other state-specific rights must be reviewed against current statutory guidance before final publication."
        )

    tip_pooling_clause = (
        "Tip pooling is used and must follow state/local eligibility, notice, and distribution restrictions."
        if profile.get("tip_pooling")
        else "Tip pooling is not currently configured; any future tip-pool program must be implemented by written policy addendum."
    )

    lines.extend([
        "",
        "5) Safe Harbor and Legal Control",
        "This addendum is intended as a compliance control and does not reduce rights provided by federal, state, or local law.",
        "If any provision conflicts with applicable law or a collective bargaining agreement, governing law/CBA controls and remaining provisions stay in effect.",
        tip_pooling_clause,
    ])

    if source_refs:
        lines.extend(["", "Authoritative Sources Referenced"])
        lines.extend(f"- {src}" for src in source_refs)
    else:
        lines.extend(
            [
                "",
                "Authoritative Sources Referenced",
                "- Source links were not present in the repository snapshot; run compliance refresh and legal review before publication.",
            ]
        )

    lines.extend([
        "",
        (
            f"Final legal review owner: {LEGAL_OPERATIONAL_HOOKS['legal_owner']}. "
            "Do not publish this addendum without legal sign-off."
        ),
    ])
    return "\n".join(lines)


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


async def _fetch_state_requirements(
    conn,
    scopes: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    normalized_states, _, selected_city_tokens_by_state = _collect_state_city_scope(scopes)
    if not normalized_states:
        return {}

    try:
        rows = await conn.fetch(
            """
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
                jr.updated_at
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = ANY($1::varchar[])
              AND (
                jr.category = ANY($2::varchar[])
                OR jr.title ILIKE ANY($3::text[])
                OR COALESCE(jr.description, '') ILIKE ANY($3::text[])
              )
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
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
            """,
            normalized_states,
            list(ADDENDUM_CORE_CATEGORIES),
            list(ADDENDUM_KEYWORD_PATTERNS),
        )
    except Exception:
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


def _validate_required_state_coverage(
    industry_key: str,
    states: list[str],
    state_requirement_map: dict[str, list[dict[str, Any]]],
) -> None:
    if industry_key not in STRICT_TEMPLATE_INDUSTRIES:
        return

    missing_by_state: list[str] = []
    for state in states:
        requirements = state_requirement_map.get(state, [])
        missing_topics = [
            MANDATORY_STATE_TOPIC_LABELS[topic]
            for topic in MANDATORY_STATE_TOPIC_RULES.keys()
            if not _requirements_cover_topic(requirements, topic)
        ]
        if missing_topics:
            missing_by_state.append(
                f"{STATE_NAMES.get(state, state)} ({', '.join(missing_topics)})"
            )

    if missing_by_state:
        raise ValueError(
            "Missing required state boilerplate coverage for hospitality handbook generation: "
            f"{'; '.join(missing_by_state)}. "
            "Run compliance refresh for the selected jurisdictions and complete legal review before creating this handbook."
        )


def _build_template_sections(
    mode: str,
    scopes: list[dict[str, Any]],
    profile: dict[str, Any],
    custom_sections: list[HandbookSectionInput],
    industry_key: str = "general",
    state_requirement_map: Optional[dict[str, list[dict[str, Any]]]] = None,
    guided_answers: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    unique_states, selected_cities_by_state, _ = _collect_state_city_scope(scopes)
    _validate_required_state_coverage(industry_key, unique_states, state_requirement_map or {})
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


class HandbookService:
    @staticmethod
    def _is_missing_freshness_table_error(exc: BaseException) -> bool:
        if not isinstance(exc, asyncpg.UndefinedTableError):
            return False
        msg = str(exc).lower()
        return (
            "handbook_freshness_checks" in msg
            or "handbook_freshness_findings" in msg
        )

    @staticmethod
    async def _ensure_freshness_tables(conn) -> None:
        checks_exists = await conn.fetchval(
            "SELECT to_regclass('public.handbook_freshness_checks') IS NOT NULL"
        )
        findings_exists = await conn.fetchval(
            "SELECT to_regclass('public.handbook_freshness_findings') IS NOT NULL"
        )
        if checks_exists and findings_exists:
            return

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handbook_freshness_checks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                triggered_by UUID REFERENCES users(id),
                check_type VARCHAR(20) NOT NULL DEFAULT 'manual'
                    CHECK (check_type IN ('manual', 'scheduled')),
                status VARCHAR(20) NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
                is_outdated BOOLEAN NOT NULL DEFAULT false,
                impacted_sections INTEGER NOT NULL DEFAULT 0,
                changes_created INTEGER NOT NULL DEFAULT 0,
                requirements_fingerprint VARCHAR(128),
                previous_fingerprint VARCHAR(128),
                requirements_last_updated_at TIMESTAMPTZ,
                data_staleness_days INTEGER,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_handbook_created
            ON handbook_freshness_checks(handbook_id, created_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_checks_company_created
            ON handbook_freshness_checks(company_id, created_at DESC)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handbook_freshness_findings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                freshness_check_id UUID NOT NULL REFERENCES handbook_freshness_checks(id) ON DELETE CASCADE,
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                section_key VARCHAR(120),
                finding_type VARCHAR(40) NOT NULL,
                summary TEXT NOT NULL,
                old_content TEXT,
                proposed_content TEXT,
                source_url VARCHAR(1000),
                effective_date DATE,
                change_request_id UUID REFERENCES handbook_change_requests(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_check
            ON handbook_freshness_findings(freshness_check_id)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_handbook_freshness_findings_handbook
            ON handbook_freshness_findings(handbook_id)
            """
        )

    @staticmethod
    async def _upsert_profile_with_conn(
        conn,
        company_id: str,
        profile: CompanyHandbookProfileInput,
        updated_by: Optional[str] = None,
    ) -> CompanyHandbookProfileResponse:
        data = _normalize_profile(profile)
        await conn.execute(
            """
            INSERT INTO company_handbook_profiles (
                company_id, legal_name, dba, ceo_or_president, headcount,
                remote_workers, minors, tipped_employees, union_employees, federal_contracts,
                group_health_insurance, background_checks, hourly_employees,
                salaried_employees, commissioned_employees, tip_pooling, updated_by, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15, $16, $17, NOW()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                legal_name = EXCLUDED.legal_name,
                dba = EXCLUDED.dba,
                ceo_or_president = EXCLUDED.ceo_or_president,
                headcount = EXCLUDED.headcount,
                remote_workers = EXCLUDED.remote_workers,
                minors = EXCLUDED.minors,
                tipped_employees = EXCLUDED.tipped_employees,
                union_employees = EXCLUDED.union_employees,
                federal_contracts = EXCLUDED.federal_contracts,
                group_health_insurance = EXCLUDED.group_health_insurance,
                background_checks = EXCLUDED.background_checks,
                hourly_employees = EXCLUDED.hourly_employees,
                salaried_employees = EXCLUDED.salaried_employees,
                commissioned_employees = EXCLUDED.commissioned_employees,
                tip_pooling = EXCLUDED.tip_pooling,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """,
            company_id,
            data["legal_name"],
            data["dba"],
            data["ceo_or_president"],
            data["headcount"],
            data["remote_workers"],
            data["minors"],
            data["tipped_employees"],
            data["union_employees"],
            data["federal_contracts"],
            data["group_health_insurance"],
            data["background_checks"],
            data["hourly_employees"],
            data["salaried_employees"],
            data["commissioned_employees"],
            data["tip_pooling"],
            updated_by,
        )
        row = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1",
            company_id,
        )
        return CompanyHandbookProfileResponse(**dict(row))

    @staticmethod
    async def get_or_default_profile(company_id: str) -> CompanyHandbookProfileResponse:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM company_handbook_profiles
                WHERE company_id = $1
                """,
                company_id,
            )
            if row:
                return CompanyHandbookProfileResponse(**dict(row))

            company_name = await conn.fetchval(
                "SELECT name FROM companies WHERE id = $1",
                company_id,
            ) or "Company"
            headcount = await conn.fetchval(
                "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
                company_id,
            )
            fallback = {
                "company_id": UUID(company_id),
                "legal_name": company_name,
                "dba": None,
                "ceo_or_president": "Company Leadership",
                "headcount": int(headcount or 0),
                "remote_workers": False,
                "minors": False,
                "tipped_employees": False,
                "union_employees": False,
                "federal_contracts": False,
                "group_health_insurance": False,
                "background_checks": False,
                "hourly_employees": True,
                "salaried_employees": False,
                "commissioned_employees": False,
                "tip_pooling": False,
                "updated_by": None,
                "updated_at": datetime.utcnow(),
            }
            return CompanyHandbookProfileResponse(**fallback)

    @staticmethod
    async def upsert_profile(
        company_id: str,
        profile: CompanyHandbookProfileInput,
        updated_by: Optional[str] = None,
    ) -> CompanyHandbookProfileResponse:
        async with get_connection() as conn:
            return await HandbookService._upsert_profile_with_conn(
                conn,
                company_id,
                profile,
                updated_by,
            )

    @staticmethod
    async def get_wizard_draft(
        company_id: str,
        user_id: str,
    ) -> Optional[HandbookWizardDraftResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, company_id, user_id, draft_state, created_at, updated_at
                FROM handbook_wizard_drafts
                WHERE company_id = $1 AND user_id = $2
                """,
                company_id,
                user_id,
            )
            if not row:
                return None
            payload = dict(row)
            raw = payload.pop("draft_state", {}) or {}
            payload["state"] = json.loads(raw) if isinstance(raw, str) else raw
            return HandbookWizardDraftResponse(**payload)

    @staticmethod
    async def upsert_wizard_draft(
        company_id: str,
        user_id: str,
        state: dict[str, Any],
    ) -> HandbookWizardDraftResponse:
        normalized_state = _sanitize_wizard_draft_state(state)
        try:
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO handbook_wizard_drafts (
                        company_id, user_id, draft_state, created_at, updated_at
                    )
                    VALUES ($1, $2, $3::jsonb, NOW(), NOW())
                    ON CONFLICT (company_id, user_id)
                    DO UPDATE SET
                        draft_state = EXCLUDED.draft_state,
                        updated_at = NOW()
                    RETURNING id, company_id, user_id, draft_state, created_at, updated_at
                    """,
                    company_id,
                    user_id,
                    json.dumps(normalized_state),
                )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        payload = dict(row)
        raw = payload.pop("draft_state", {}) or {}
        payload["state"] = json.loads(raw) if isinstance(raw, str) else raw
        return HandbookWizardDraftResponse(**payload)

    @staticmethod
    async def delete_wizard_draft(
        company_id: str,
        user_id: str,
    ) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM handbook_wizard_drafts
                WHERE company_id = $1 AND user_id = $2
                """,
                company_id,
                user_id,
            )
            return result == "DELETE 1"

    @staticmethod
    async def _generate_guided_draft_ai_payload(
        *,
        company_name: str,
        industry_key: str,
        industry_label: str,
        title: str,
        mode: str,
        scopes: list[dict[str, Any]],
        normalized_profile: dict[str, Any],
        answers: dict[str, str],
        baseline_questions: list[dict[str, Any]],
        baseline_sections: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        try:
            settings = get_settings()
        except Exception:
            return None

        if not settings.use_vertex and not settings.gemini_api_key:
            return None

        try:
            from google import genai
        except Exception:
            return None

        try:
            from .rate_limiter import RateLimitExceeded, get_rate_limiter

            await get_rate_limiter().check_limit("handbook_guided_draft", industry_key)
        except RateLimitExceeded as exc:
            raise GuidedDraftRateLimitError(
                "Guided draft rate limit exceeded. Please retry later."
            ) from exc
        except Exception:
            pass

        states = sorted({(scope.get("state") or "").upper() for scope in scopes if scope.get("state")})
        states_text = ", ".join(states) if states else "No states selected"

        prompt = (
            "You are an HR policy drafting assistant. "
            "Generate practical handbook setup guidance for an HR manager.\n\n"
            f"Company: {company_name}\n"
            f"Handbook title: {title}\n"
            f"Industry: {industry_label}\n"
            f"Mode: {mode}\n"
            f"States: {states_text}\n"
            f"Current profile flags: {json.dumps(normalized_profile)}\n"
            f"Known answers from HR manager: {json.dumps(answers)}\n"
            f"Baseline follow-up questions: {json.dumps(baseline_questions)}\n"
            f"Baseline suggested sections: {json.dumps(baseline_sections)}\n\n"
            "Return ONLY JSON with this shape:\n"
            "{\n"
            '  "summary": "one short paragraph",\n'
            '  "questions": [\n'
            '    {"id":"snake_case","question":"text","placeholder":"optional","required":true}\n'
            "  ],\n"
            '  "profile_updates": {\n'
            '    "remote_workers": false,\n'
            '    "tipped_employees": false,\n'
            '    "union_employees": false,\n'
            '    "federal_contracts": false,\n'
            '    "group_health_insurance": false,\n'
            '    "background_checks": false,\n'
            '    "hourly_employees": true,\n'
            '    "salaried_employees": false,\n'
            '    "commissioned_employees": false,\n'
            '    "tip_pooling": false\n'
            "  },\n"
            '  "suggested_sections": [\n'
            '    {"section_key":"snake_case","title":"text","content":"enforceable policy text","section_order":320}\n'
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Provide at most 6 questions and at most 6 suggested sections.\n"
            "- Questions should help complete missing operational/legal hooks.\n"
            "- Suggested sections must be enforceable policy language, not summaries.\n"
            "- Use placeholders like [HR_CONTACT_EMAIL], [HARASSMENT_REPORTING_HOTLINE], [WORKWEEK_START_DAY] when details are unknown.\n"
            "- Keep content neutral, non-retaliatory, and suitable for legal review.\n"
        )

        try:
            if settings.use_vertex:
                client = genai.Client(
                    vertexai=True,
                    project=settings.vertex_project,
                    location=settings.vertex_location or "us-central1",
                )
            else:
                client = genai.Client(api_key=settings.gemini_api_key)
        except Exception:
            return None

        model_name = settings.analysis_model or "gemini-3-flash-preview"
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                ),
                timeout=45,
            )
            raw_text = (getattr(response, "text", None) or "").strip()
            parsed = _extract_json_payload(raw_text)
            if not parsed:
                return None
            try:
                from .rate_limiter import get_rate_limiter

                await get_rate_limiter().record_call("handbook_guided_draft", industry_key)
            except Exception:
                pass
            return parsed
        except Exception:
            return None

    @staticmethod
    async def generate_guided_draft(
        company_id: str,
        data: HandbookGuidedDraftRequest,
    ) -> HandbookGuidedDraftResponse:
        normalized_scopes = [_normalize_scope(scope) for scope in data.scopes]
        normalized_profile = _normalize_profile(data.profile)
        answers = _sanitize_answer_map(data.answers)

        company_name = normalized_profile.get("legal_name") or "Company"
        company_industry = None
        async with get_connection() as conn:
            company_row = await conn.fetchrow(
                "SELECT name, industry FROM companies WHERE id = $1",
                company_id,
            )
            if company_row:
                company_name = company_row.get("name") or company_name
                company_industry = company_row.get("industry")

        industry_key = _normalize_industry(data.industry, company_industry)
        playbook = GUIDED_INDUSTRY_PLAYBOOK.get(industry_key, GUIDED_INDUSTRY_PLAYBOOK["general"])
        industry_label = playbook.get("label", "General Employer")
        baseline_summary = playbook.get("summary", GUIDED_INDUSTRY_PLAYBOOK["general"]["summary"])

        baseline_questions = _build_guided_question_list(industry_key)
        unanswered_baseline_questions = _filter_unanswered_questions(baseline_questions, answers)
        baseline_profile_updates = _default_profile_updates_for_industry(industry_key, normalized_profile)
        baseline_sections = _build_default_section_suggestions(industry_key)

        ai_payload = await HandbookService._generate_guided_draft_ai_payload(
            company_name=company_name,
            industry_key=industry_key,
            industry_label=industry_label,
            title=(data.title or "").strip() or "Employee Handbook",
            mode=data.mode,
            scopes=normalized_scopes,
            normalized_profile=normalized_profile,
            answers=answers,
            baseline_questions=baseline_questions,
            baseline_sections=baseline_sections,
        )

        ai_summary = None
        ai_questions: list[dict[str, Any]] = []
        ai_profile_updates: dict[str, Any] = {}
        ai_sections: list[dict[str, Any]] = []

        if ai_payload:
            if isinstance(ai_payload.get("summary"), str):
                ai_summary = ai_payload["summary"].strip()
            ai_questions = _sanitize_guided_questions(ai_payload.get("questions") or [])
            ai_profile_updates = _sanitize_guided_profile_updates(
                ai_payload.get("profile_updates") or {},
                normalized_profile,
            )
            ai_sections = _sanitize_guided_sections(ai_payload.get("suggested_sections") or [])

        combined_profile_updates = {**baseline_profile_updates, **ai_profile_updates}

        combined_questions = _sanitize_guided_questions([*unanswered_baseline_questions, *ai_questions])
        unanswered_questions = _filter_unanswered_questions(combined_questions, answers)

        merged_sections = _merge_guided_sections(
            data.existing_custom_sections,
            baseline_sections=baseline_sections,
            ai_sections=ai_sections,
        )

        summary = ai_summary or baseline_summary
        if unanswered_questions:
            summary = (
                f"{summary} Answer the follow-up questions to finalize policy hooks before publishing."
            )

        return HandbookGuidedDraftResponse(
            industry=industry_key,
            summary=summary,
            clarification_needed=bool(unanswered_questions),
            questions=[HandbookGuidedQuestion(**question) for question in unanswered_questions],
            profile_updates=combined_profile_updates,
            suggested_sections=[HandbookGuidedSectionSuggestion(**section) for section in merged_sections],
        )

    @staticmethod
    async def list_handbooks(company_id: str) -> list[HandbookListItemResponse]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    h.*,
                    COALESCE(
                        ARRAY_AGG(DISTINCT hs.state) FILTER (WHERE hs.state IS NOT NULL),
                        '{}'::varchar[]
                    ) AS scope_states,
                    COALESCE(
                        COUNT(DISTINCT hcr.id) FILTER (WHERE hcr.status = 'pending'),
                        0
                    ) AS pending_changes_count
                FROM handbooks h
                LEFT JOIN handbook_scopes hs ON hs.handbook_id = h.id
                LEFT JOIN handbook_change_requests hcr ON hcr.handbook_id = h.id
                WHERE h.company_id = $1
                GROUP BY h.id
                ORDER BY h.updated_at DESC
                """,
                company_id,
            )
            return [HandbookListItemResponse(**dict(row)) for row in rows]

    @staticmethod
    async def create_handbook(
        company_id: str,
        data: HandbookCreateRequest,
        created_by: Optional[str] = None,
    ) -> HandbookDetailResponse:
        normalized_scopes = [_normalize_scope(scope) for scope in data.scopes]
        profile = _normalize_profile(data.profile)
        guided_answers = _sanitize_answer_map(data.guided_answers)
        profile_row: Optional[CompanyHandbookProfileResponse] = None
        _validate_handbook_file_reference(data.file_url)

        try:
            async with get_connection() as conn:
                async with conn.transaction():
                    company_industry = await conn.fetchval(
                        "SELECT industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    industry_key = _normalize_industry(data.industry, company_industry)

                    profile_row = await HandbookService._upsert_profile_with_conn(
                        conn,
                        company_id,
                        data.profile,
                        created_by,
                    )
                    handbook_id = await conn.fetchval(
                        """
                        INSERT INTO handbooks (
                            company_id, title, status, mode, source_type, active_version,
                            file_url, file_name, created_by, created_at, updated_at
                        )
                        VALUES ($1, $2, 'draft', $3, $4, 1, $5, $6, $7, NOW(), NOW())
                        RETURNING id
                        """,
                        company_id,
                        data.title,
                        data.mode,
                        data.source_type,
                        data.file_url,
                        data.file_name,
                        created_by,
                    )

                    for scope in normalized_scopes:
                        await conn.execute(
                            """
                            INSERT INTO handbook_scopes (handbook_id, state, city, zipcode, location_id, created_at)
                            VALUES ($1, $2, $3, $4, $5, NOW())
                            """,
                            handbook_id,
                            scope["state"],
                            scope["city"],
                            scope["zipcode"],
                            scope["location_id"],
                        )

                    version_id = await conn.fetchval(
                        """
                        INSERT INTO handbook_versions (
                            handbook_id, version_number, summary, is_published, created_by, created_at
                        )
                        VALUES ($1, 1, $2, false, $3, NOW())
                        RETURNING id
                        """,
                        handbook_id,
                        "Initial handbook draft",
                        created_by,
                    )

                    if data.source_type == "template":
                        state_requirement_map = await _fetch_state_requirements(
                            conn,
                            normalized_scopes,
                        )
                        sections = _build_template_sections(
                            data.mode,
                            normalized_scopes,
                            profile,
                            data.custom_sections,
                            industry_key=industry_key,
                            state_requirement_map=state_requirement_map,
                            guided_answers=guided_answers,
                        )
                    else:
                        sections = [
                            {
                                "section_key": "uploaded_handbook",
                                "title": "Uploaded Employee Handbook",
                                "section_order": 10,
                                "section_type": "uploaded",
                                "jurisdiction_scope": {},
                                "content": (
                                    "This handbook was uploaded as a company-authored document. "
                                    "Use the file attachment for the canonical text."
                                ),
                            }
                        ]

                    for section in sections:
                        await conn.execute(
                            """
                            INSERT INTO handbook_sections (
                                handbook_version_id, section_key, title, section_order,
                                section_type, jurisdiction_scope, content, created_at, updated_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, NOW(), NOW())
                            """,
                            version_id,
                            section["section_key"],
                            section["title"],
                            section["section_order"],
                            section["section_type"],
                            json.dumps(section["jurisdiction_scope"] or {}),
                            section["content"],
                        )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        handbook = await HandbookService.get_handbook_by_id(str(handbook_id), company_id)
        if handbook is None:
            raise ValueError("Failed to create handbook")
        if profile_row is not None:
            handbook.profile = profile_row
        return handbook

    @staticmethod
    async def _get_active_version_id(conn, handbook_id: str, active_version: int) -> Optional[UUID]:
        return await conn.fetchval(
            """
            SELECT id
            FROM handbook_versions
            WHERE handbook_id = $1 AND version_number = $2
            """,
            handbook_id,
            active_version,
        )

    @staticmethod
    async def get_handbook_by_id(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookDetailResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM handbooks
                WHERE id = $1 AND company_id = $2
                """,
                handbook_id,
                company_id,
            )
            if not row:
                return None

            active_version_id = await HandbookService._get_active_version_id(
                conn,
                str(row["id"]),
                row["active_version"],
            )
            if active_version_id is None:
                active_version_id = await conn.fetchval(
                    """
                    SELECT id
                    FROM handbook_versions
                    WHERE handbook_id = $1
                    ORDER BY version_number DESC
                    LIMIT 1
                    """,
                    row["id"],
                )

            scope_rows = await conn.fetch(
                """
                SELECT id, state, city, zipcode, location_id
                FROM handbook_scopes
                WHERE handbook_id = $1
                ORDER BY state, city NULLS LAST, zipcode NULLS LAST
                """,
                row["id"],
            )
            section_rows = await conn.fetch(
                """
                SELECT id, section_key, title, content, section_order, section_type, jurisdiction_scope
                FROM handbook_sections
                WHERE handbook_version_id = $1
                ORDER BY section_order ASC, created_at ASC
                """,
                active_version_id,
            )

            profile = await HandbookService.get_or_default_profile(company_id)

            section_models: list[HandbookSectionResponse] = []
            for section in section_rows:
                section_dict = dict(section)
                section_dict["jurisdiction_scope"] = _coerce_jurisdiction_scope(
                    section_dict.get("jurisdiction_scope")
                )
                section_models.append(HandbookSectionResponse(**section_dict))

            return HandbookDetailResponse(
                id=row["id"],
                company_id=row["company_id"],
                title=row["title"],
                status=row["status"],
                mode=row["mode"],
                source_type=row["source_type"],
                active_version=row["active_version"],
                file_url=row["file_url"],
                file_name=row["file_name"],
                scopes=[HandbookScopeResponse(**dict(scope)) for scope in scope_rows],
                profile=profile,
                sections=section_models,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                published_at=row["published_at"],
                created_by=row["created_by"],
            )

    @staticmethod
    async def update_handbook(
        handbook_id: str,
        company_id: str,
        data: HandbookUpdateRequest,
        updated_by: Optional[str] = None,
    ) -> Optional[HandbookDetailResponse]:
        try:
            async with get_connection() as conn:
                async with conn.transaction():
                    current = await conn.fetchrow(
                        """
                        SELECT *
                        FROM handbooks
                        WHERE id = $1 AND company_id = $2
                        """,
                        handbook_id,
                        company_id,
                    )
                    if not current:
                        return None

                    if data.mode is not None or data.scopes is not None:
                        next_mode = data.mode or current["mode"]
                        if data.scopes is None:
                            scope_count = await conn.fetchval(
                                "SELECT COUNT(*) FROM handbook_scopes WHERE handbook_id = $1",
                                handbook_id,
                            )
                            scope_count = int(scope_count or 0)
                        else:
                            scope_count = len(data.scopes)
                        if next_mode == "single_state" and scope_count != 1:
                            raise ValueError("Single-state handbooks must have exactly one scope")
                        if next_mode == "multi_state" and scope_count < 2:
                            raise ValueError("Multi-state handbooks must include at least two scopes")

                    _validate_handbook_file_reference(data.file_url)
                    should_invalidate_cached_file = (
                        current["source_type"] == "template"
                        and any(
                            value is not None
                            for value in (data.title, data.mode, data.scopes, data.sections, data.profile)
                        )
                        and data.file_url is None
                        and data.file_name is None
                    )

                    updates: list[str] = []
                    params: list[Any] = []
                    idx = 3

                    if data.title is not None:
                        updates.append(f"title = ${idx}")
                        params.append(data.title)
                        idx += 1
                    if data.mode is not None:
                        updates.append(f"mode = ${idx}")
                        params.append(data.mode)
                        idx += 1
                    if data.file_url is not None:
                        updates.append(f"file_url = ${idx}")
                        params.append(data.file_url)
                        idx += 1
                    if data.file_name is not None:
                        updates.append(f"file_name = ${idx}")
                        params.append(data.file_name)
                        idx += 1
                    if should_invalidate_cached_file:
                        updates.append("file_url = NULL")
                        updates.append("file_name = NULL")

                    if updates:
                        updates.append("updated_at = NOW()")
                        query = f"UPDATE handbooks SET {', '.join(updates)} WHERE id = $1 AND company_id = $2"
                        await conn.execute(query, handbook_id, company_id, *params)
                    else:
                        await conn.execute(
                            "UPDATE handbooks SET updated_at = NOW() WHERE id = $1 AND company_id = $2",
                            handbook_id,
                            company_id,
                        )

                    if data.scopes is not None:
                        await conn.execute("DELETE FROM handbook_scopes WHERE handbook_id = $1", handbook_id)
                        for scope in data.scopes:
                            normalized = _normalize_scope(scope)
                            await conn.execute(
                                """
                                INSERT INTO handbook_scopes (handbook_id, state, city, zipcode, location_id, created_at)
                                VALUES ($1, $2, $3, $4, $5, NOW())
                                """,
                                handbook_id,
                                normalized["state"],
                                normalized["city"],
                                normalized["zipcode"],
                                normalized["location_id"],
                            )

                    if data.sections is not None:
                        seen_keys: set[str] = set()
                        for section in data.sections:
                            key = section.section_key.strip()
                            if key in seen_keys:
                                raise ValueError(f"Duplicate section key '{key}' in handbook update")
                            seen_keys.add(key)

                        version_id = await HandbookService._get_active_version_id(
                            conn,
                            handbook_id,
                            current["active_version"],
                        )
                        if version_id:
                            await conn.execute(
                                "DELETE FROM handbook_sections WHERE handbook_version_id = $1",
                                version_id,
                            )
                            for section in data.sections:
                                await conn.execute(
                                    """
                                    INSERT INTO handbook_sections (
                                        handbook_version_id, section_key, title, content, section_order,
                                        section_type, jurisdiction_scope, created_at, updated_at
                                    )
                                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW(), NOW())
                                    """,
                                    version_id,
                                    section.section_key,
                                    section.title,
                                    section.content,
                                    section.section_order,
                                    section.section_type,
                                    json.dumps(section.jurisdiction_scope or {}),
                                )

                    if data.profile is not None:
                        await HandbookService._upsert_profile_with_conn(
                            conn,
                            company_id,
                            data.profile,
                            updated_by,
                        )
        except Exception as exc:
            translated = _translate_handbook_db_error(exc)
            if translated:
                raise ValueError(translated) from exc
            raise

        return await HandbookService.get_handbook_by_id(handbook_id, company_id)

    @staticmethod
    async def publish_handbook(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookPublishResponse]:
        async with get_connection() as conn:
            async with conn.transaction():
                target = await conn.fetchrow(
                    """
                    SELECT id, active_version
                    FROM handbooks
                    WHERE id = $1 AND company_id = $2
                    """,
                    handbook_id,
                    company_id,
                )
                if not target:
                    return None

                await conn.execute(
                    """
                    UPDATE handbooks
                    SET status = 'archived', updated_at = NOW()
                    WHERE company_id = $1
                      AND status = 'active'
                      AND id <> $2
                    """,
                    company_id,
                    handbook_id,
                )
                await conn.execute(
                    """
                    UPDATE handbooks
                    SET status = 'active',
                        published_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1 AND company_id = $2
                    """,
                    handbook_id,
                    company_id,
                )
                await conn.execute(
                    """
                    UPDATE handbook_versions
                    SET is_published = (version_number = $2)
                    WHERE handbook_id = $1
                    """,
                    handbook_id,
                    target["active_version"],
                )

                row = await conn.fetchrow(
                    """
                    SELECT id, status, active_version, published_at
                    FROM handbooks
                    WHERE id = $1
                    """,
                    handbook_id,
                )
                return HandbookPublishResponse(**dict(row))

    @staticmethod
    async def archive_handbook(handbook_id: str, company_id: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                """
                UPDATE handbooks
                SET status = 'archived', updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                """,
                handbook_id,
                company_id,
            )
            return result == "UPDATE 1"

    @staticmethod
    async def list_change_requests(
        handbook_id: str,
        company_id: str,
    ) -> list[HandbookChangeRequestResponse]:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not exists:
                return []

            rows = await conn.fetch(
                """
                SELECT *
                FROM handbook_change_requests
                WHERE handbook_id = $1
                ORDER BY
                    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                    created_at DESC
                """,
                handbook_id,
            )
            return [HandbookChangeRequestResponse(**dict(row)) for row in rows]

    @staticmethod
    async def resolve_change_request(
        handbook_id: str,
        company_id: str,
        change_id: str,
        new_status: str,
        resolved_by: Optional[str] = None,
    ) -> Optional[HandbookChangeRequestResponse]:
        if new_status not in {"accepted", "rejected"}:
            return None

        async with get_connection() as conn:
            async with conn.transaction():
                handbook = await conn.fetchrow(
                    "SELECT id, active_version FROM handbooks WHERE id = $1 AND company_id = $2",
                    handbook_id,
                    company_id,
                )
                if not handbook:
                    return None

                change = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_change_requests
                    WHERE id = $1 AND handbook_id = $2
                    """,
                    change_id,
                    handbook_id,
                )
                if not change:
                    return None

                accepted_content_change = False
                if new_status == "accepted" and change["section_key"]:
                    version_id = await HandbookService._get_active_version_id(
                        conn,
                        handbook_id,
                        handbook["active_version"],
                    )
                    if version_id:
                        await conn.execute(
                            """
                            UPDATE handbook_sections
                            SET content = $1, updated_at = NOW()
                            WHERE handbook_version_id = $2 AND section_key = $3
                            """,
                            change["proposed_content"],
                            version_id,
                            change["section_key"],
                        )
                        accepted_content_change = True

                updated = await conn.fetchrow(
                    """
                    UPDATE handbook_change_requests
                    SET status = $1, resolved_by = $2, resolved_at = NOW()
                    WHERE id = $3
                    RETURNING *
                    """,
                    new_status,
                    resolved_by,
                    change_id,
                )
                if accepted_content_change:
                    await conn.execute(
                        "UPDATE handbooks SET updated_at = NOW(), file_url = NULL, file_name = NULL WHERE id = $1",
                        handbook_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE handbooks SET updated_at = NOW() WHERE id = $1",
                        handbook_id,
                    )

        return HandbookChangeRequestResponse(**dict(updated)) if updated else None

    @staticmethod
    def _build_freshness_response(
        check_row: dict[str, Any],
        findings_rows: list[dict[str, Any]],
    ) -> HandbookFreshnessCheckResponse:
        findings = [
            HandbookFreshnessFindingResponse(
                section_key=row.get("section_key"),
                finding_type=row.get("finding_type") or "info",
                summary=row.get("summary") or "",
                change_request_id=row.get("change_request_id"),
                source_url=row.get("source_url"),
                effective_date=row.get("effective_date"),
            )
            for row in findings_rows
        ]

        checked_at = check_row.get("completed_at") or check_row.get("created_at") or datetime.utcnow()
        return HandbookFreshnessCheckResponse(
            check_id=check_row["id"],
            handbook_id=check_row["handbook_id"],
            check_type=check_row["check_type"],
            status=check_row["status"],
            is_outdated=bool(check_row.get("is_outdated")),
            impacted_sections=int(check_row.get("impacted_sections") or 0),
            new_change_requests_count=int(check_row.get("changes_created") or 0),
            requirements_last_updated_at=check_row.get("requirements_last_updated_at"),
            data_staleness_days=check_row.get("data_staleness_days"),
            current_fingerprint=check_row.get("requirements_fingerprint"),
            previous_fingerprint=check_row.get("previous_fingerprint"),
            checked_at=checked_at,
            findings=findings,
        )

    @staticmethod
    async def get_latest_freshness_check(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookFreshnessCheckResponse]:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not exists:
                return None

            await HandbookService._ensure_freshness_tables(conn)

            try:
                check_row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_freshness_checks
                    WHERE handbook_id = $1 AND company_id = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    handbook_id,
                    company_id,
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                check_row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM handbook_freshness_checks
                    WHERE handbook_id = $1 AND company_id = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    handbook_id,
                    company_id,
                )
            if not check_row:
                return None

            try:
                finding_rows = await conn.fetch(
                    """
                    SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date
                    FROM handbook_freshness_findings
                    WHERE freshness_check_id = $1
                    ORDER BY created_at ASC
                    """,
                    check_row["id"],
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                finding_rows = await conn.fetch(
                    """
                    SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date
                    FROM handbook_freshness_findings
                    WHERE freshness_check_id = $1
                    ORDER BY created_at ASC
                    """,
                    check_row["id"],
                )
            return HandbookService._build_freshness_response(
                dict(check_row),
                [dict(row) for row in finding_rows],
            )

    @staticmethod
    async def run_freshness_check(
        handbook_id: str,
        company_id: str,
        triggered_by: Optional[str] = None,
        check_type: str = "manual",
    ) -> Optional[HandbookFreshnessCheckResponse]:
        if check_type not in {"manual", "scheduled"}:
            raise ValueError("Invalid freshness check type")

        async with get_connection() as conn:
            handbook_exists = await conn.fetchval(
                "SELECT 1 FROM handbooks WHERE id = $1 AND company_id = $2",
                handbook_id,
                company_id,
            )
            if not handbook_exists:
                return None

            await HandbookService._ensure_freshness_tables(conn)

            try:
                check_id = await conn.fetchval(
                    """
                    INSERT INTO handbook_freshness_checks (
                        handbook_id,
                        company_id,
                        triggered_by,
                        check_type,
                        status,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, 'running', NOW())
                    RETURNING id
                    """,
                    handbook_id,
                    company_id,
                    triggered_by,
                    check_type,
                )
            except asyncpg.UndefinedTableError as exc:
                if not HandbookService._is_missing_freshness_table_error(exc):
                    raise
                await HandbookService._ensure_freshness_tables(conn)
                check_id = await conn.fetchval(
                    """
                    INSERT INTO handbook_freshness_checks (
                        handbook_id,
                        company_id,
                        triggered_by,
                        check_type,
                        status,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, 'running', NOW())
                    RETURNING id
                    """,
                    handbook_id,
                    company_id,
                    triggered_by,
                    check_type,
                )

            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1))",
                        f"handbook-freshness:{company_id}:{handbook_id}",
                    )

                    handbook_row = await conn.fetchrow(
                        "SELECT id, active_version FROM handbooks WHERE id = $1 AND company_id = $2",
                        handbook_id,
                        company_id,
                    )
                    if not handbook_row:
                        raise ValueError("Handbook not found")

                    version_id = await HandbookService._get_active_version_id(
                        conn,
                        handbook_id,
                        handbook_row["active_version"],
                    )
                    if version_id is None:
                        raise ValueError("Active handbook version not found")

                    scope_rows = await conn.fetch(
                        """
                        SELECT state, city, zipcode, location_id
                        FROM handbook_scopes
                        WHERE handbook_id = $1
                        ORDER BY state, city NULLS LAST, zipcode NULLS LAST
                        """,
                        handbook_id,
                    )
                    scopes = [dict(row) for row in scope_rows]

                    profile = await HandbookService.get_or_default_profile(company_id)
                    profile_data = profile.model_dump(
                        exclude={"company_id", "updated_by", "updated_at"},
                    )
                    normalized_profile = _normalize_profile(CompanyHandbookProfileInput(**profile_data))

                    requirement_map = await _fetch_state_requirements(conn, scopes)
                    current_fingerprint, latest_requirement_update, _ = _build_requirements_fingerprint(
                        requirement_map
                    )
                    previous_fingerprint = await conn.fetchval(
                        """
                        SELECT requirements_fingerprint
                        FROM handbook_freshness_checks
                        WHERE handbook_id = $1
                          AND company_id = $2
                          AND status = 'completed'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        handbook_id,
                        company_id,
                    )

                    section_rows = await conn.fetch(
                        """
                        SELECT section_key, content
                        FROM handbook_sections
                        WHERE handbook_version_id = $1
                        """,
                        version_id,
                    )
                    sections_by_key = {row["section_key"]: row["content"] for row in section_rows}

                    states, selected_cities_by_state, _ = _collect_state_city_scope(scopes)
                    impacted_sections = 0
                    changes_created = 0

                    for state in states:
                        section_key = _state_section_key(state)
                        if section_key not in sections_by_key:
                            continue

                        requirements = requirement_map.get(state, [])
                        proposed_content = _build_state_addendum_content(
                            state=state,
                            state_name=STATE_NAMES.get(state, state),
                            profile=normalized_profile,
                            requirements=requirements,
                            selected_cities=selected_cities_by_state.get(state),
                        )
                        old_content = sections_by_key.get(section_key) or ""
                        if _normalize_section_content(old_content) == _normalize_section_content(proposed_content):
                            continue

                        impacted_sections += 1
                        source_url = _select_finding_source_url(requirements)
                        effective_date = _select_latest_effective_date(requirements)

                        existing_pending_change_id = await conn.fetchval(
                            """
                            SELECT id
                            FROM handbook_change_requests
                            WHERE handbook_id = $1
                              AND handbook_version_id = $2
                              AND section_key = $3
                              AND status = 'pending'
                              AND proposed_content = $4
                            LIMIT 1
                            """,
                            handbook_id,
                            version_id,
                            section_key,
                            proposed_content,
                        )

                        change_request_id = existing_pending_change_id
                        finding_type = "already_pending" if existing_pending_change_id else "change_request_created"
                        summary = (
                            f"{STATE_NAMES.get(state, state)} addendum appears outdated based on current jurisdiction requirements."
                        )

                        if not existing_pending_change_id:
                            change_request_id = await conn.fetchval(
                                """
                                INSERT INTO handbook_change_requests (
                                    handbook_id,
                                    handbook_version_id,
                                    section_key,
                                    old_content,
                                    proposed_content,
                                    rationale,
                                    source_url,
                                    effective_date,
                                    status,
                                    created_at
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', NOW())
                                RETURNING id
                                """,
                                handbook_id,
                                version_id,
                                section_key,
                                old_content,
                                proposed_content,
                                "Automated handbook freshness check detected newer statutory baseline language.",
                                source_url,
                                effective_date,
                            )
                            changes_created += 1

                        await conn.execute(
                            """
                            INSERT INTO handbook_freshness_findings (
                                freshness_check_id,
                                handbook_id,
                                section_key,
                                finding_type,
                                summary,
                                old_content,
                                proposed_content,
                                source_url,
                                effective_date,
                                change_request_id,
                                created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                            """,
                            check_id,
                            handbook_id,
                            section_key,
                            finding_type,
                            summary,
                            old_content,
                            proposed_content,
                            source_url,
                            effective_date,
                            change_request_id,
                        )

                    is_outdated = bool(
                        impacted_sections > 0
                        or (
                            previous_fingerprint
                            and current_fingerprint
                            and previous_fingerprint != current_fingerprint
                        )
                    )
                    data_staleness_days = (
                        (datetime.utcnow().date() - latest_requirement_update.date()).days
                        if latest_requirement_update
                        else None
                    )

                    await conn.execute(
                        """
                        UPDATE handbook_freshness_checks
                        SET
                            status = 'completed',
                            is_outdated = $1,
                            impacted_sections = $2,
                            changes_created = $3,
                            requirements_fingerprint = $4,
                            previous_fingerprint = $5,
                            requirements_last_updated_at = $6,
                            data_staleness_days = $7,
                            completed_at = NOW()
                        WHERE id = $8
                        """,
                        is_outdated,
                        impacted_sections,
                        changes_created,
                        current_fingerprint,
                        previous_fingerprint,
                        latest_requirement_update,
                        data_staleness_days,
                        check_id,
                    )

                    if changes_created > 0:
                        await conn.execute(
                            """
                            UPDATE handbooks
                            SET updated_at = NOW(), file_url = NULL, file_name = NULL
                            WHERE id = $1
                            """,
                            handbook_id,
                        )

                    check_row = await conn.fetchrow(
                        "SELECT * FROM handbook_freshness_checks WHERE id = $1",
                        check_id,
                    )
                    finding_rows = await conn.fetch(
                        """
                        SELECT section_key, finding_type, summary, change_request_id, source_url, effective_date
                        FROM handbook_freshness_findings
                        WHERE freshness_check_id = $1
                        ORDER BY created_at ASC
                        """,
                        check_id,
                    )

                return HandbookService._build_freshness_response(
                    dict(check_row),
                    [dict(row) for row in finding_rows],
                )
            except Exception as exc:
                await conn.execute(
                    """
                    UPDATE handbook_freshness_checks
                    SET status = 'failed', error_message = $1, completed_at = NOW()
                    WHERE id = $2
                    """,
                    str(exc),
                    check_id,
                )
                raise

    @staticmethod
    async def _ensure_handbook_pdf(
        handbook_id: str,
        company_id: str,
    ) -> tuple[str, str, int]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            raise ValueError("Handbook not found")

        if handbook.file_url:
            _validate_handbook_file_reference(handbook.file_url)
            return handbook.file_url, (handbook.file_name or ""), handbook.active_version

        pdf_bytes, filename = await HandbookService.generate_handbook_pdf_bytes(handbook_id, company_id)
        storage = get_storage()
        file_url = await storage.upload_file(
            pdf_bytes,
            filename,
            prefix="handbooks",
            content_type="application/pdf",
        )

        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE handbooks
                SET file_url = $1, file_name = $2, updated_at = NOW()
                WHERE id = $3 AND company_id = $4
                """,
                file_url,
                filename,
                handbook_id,
                company_id,
            )
        return file_url, filename, handbook.active_version

    @staticmethod
    async def distribute_to_employees(
        handbook_id: str,
        company_id: str,
        distributed_by: Optional[str] = None,
        employee_ids: Optional[list[str]] = None,
    ) -> Optional[HandbookDistributionResponse]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None
        if handbook.status != "active":
            raise ValueError("Only active handbooks can be distributed for acknowledgement")

        file_url, _, version_number = await HandbookService._ensure_handbook_pdf(handbook_id, company_id)
        doc_type = f"handbook:{handbook_id}:{version_number}"

        async with get_connection() as conn:
            async with conn.transaction():
                selected_employee_ids: list[UUID] = []
                if employee_ids is not None:
                    dedup: set[UUID] = set()
                    for raw_id in employee_ids:
                        parsed_id = UUID(str(raw_id))
                        if parsed_id in dedup:
                            continue
                        dedup.add(parsed_id)
                        selected_employee_ids.append(parsed_id)
                    if not selected_employee_ids:
                        raise ValueError("Select at least one employee to send this handbook.")

                if selected_employee_ids:
                    employee_rows = await conn.fetch(
                        """
                        SELECT id
                        FROM employees
                        WHERE org_id = $1
                          AND termination_date IS NULL
                          AND email IS NOT NULL
                          AND id = ANY($2::uuid[])
                        ORDER BY created_at ASC
                        """,
                        company_id,
                        selected_employee_ids,
                    )
                    found_ids = {row["id"] for row in employee_rows}
                    missing_ids = [employee_id for employee_id in selected_employee_ids if employee_id not in found_ids]
                    if missing_ids:
                        raise ValueError("Some selected employees are no longer active for this company.")
                else:
                    employee_rows = await conn.fetch(
                        """
                        SELECT id
                        FROM employees
                        WHERE org_id = $1
                          AND termination_date IS NULL
                          AND email IS NOT NULL
                        ORDER BY created_at ASC
                        """,
                        company_id,
                    )

                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    f"handbook-distribute:{company_id}:{doc_type}",
                )

                columns = await _get_employee_document_columns(conn)
                existing_employee_rows = await conn.fetch(
                    """
                    SELECT employee_id
                    FROM employee_documents
                    WHERE org_id = $1 AND doc_type = $2
                      AND status IN ('pending_signature', 'signed')
                    """,
                    company_id,
                    doc_type,
                )
                existing_employee_ids = {row["employee_id"] for row in existing_employee_rows}
                insertable = {
                    "org_id": UUID(company_id),
                    "doc_type": doc_type,
                    "title": f"{handbook.title} (v{version_number})",
                    "description": f"Employee handbook acknowledgement for {handbook.title}",
                    "storage_path": file_url,
                    "status": "pending_signature",
                    "expires_at": date.today() + timedelta(days=365),
                    "assigned_by": UUID(distributed_by) if distributed_by else None,
                    "updated_at": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                }

                assigned = 0
                skipped = 0
                for employee in employee_rows:
                    if employee["id"] in existing_employee_ids:
                        skipped += 1
                        continue

                    record = {"employee_id": employee["id"]}
                    record.update(insertable)
                    cols = [col for col in record.keys() if col in columns]
                    values = [record[col] for col in cols]
                    placeholders = ", ".join(f"${idx}" for idx in range(1, len(cols) + 1))
                    col_sql = ", ".join(cols)
                    result = await conn.execute(
                        (
                            f"INSERT INTO employee_documents ({col_sql}) VALUES ({placeholders}) "
                            "ON CONFLICT (employee_id, doc_type) "
                            "WHERE status IN ('pending_signature', 'signed') DO NOTHING"
                        ),
                        *values,
                    )
                    if result == "INSERT 0 1":
                        assigned += 1
                    else:
                        skipped += 1

                await conn.execute(
                    """
                    INSERT INTO handbook_distribution_runs (
                        handbook_id, handbook_version_id, distributed_by, distributed_at, employee_count
                    )
                    VALUES (
                        $1,
                        (
                            SELECT id FROM handbook_versions
                            WHERE handbook_id = $1 AND version_number = $2
                            LIMIT 1
                        ),
                        $3,
                        NOW(),
                        $4
                    )
                    """,
                    handbook_id,
                    version_number,
                    distributed_by,
                    assigned,
                )

        return HandbookDistributionResponse(
            handbook_id=UUID(handbook_id),
            handbook_version=version_number,
            assigned_count=assigned,
            skipped_existing_count=skipped,
            distributed_at=datetime.utcnow(),
        )

    @staticmethod
    async def list_distribution_recipients(
        handbook_id: str,
        company_id: str,
    ) -> Optional[list[HandbookDistributionRecipientResponse]]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None
        if handbook.status != "active":
            raise ValueError("Only active handbooks can be distributed for acknowledgement")

        doc_type = f"handbook:{handbook_id}:{handbook.active_version}"
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.id AS employee_id,
                    COALESCE(NULLIF(TRIM(e.first_name || ' ' || e.last_name), ''), e.email) AS name,
                    e.email,
                    (
                        SELECT status
                        FROM employee_invitations
                        WHERE employee_id = e.id
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) AS invitation_status,
                    EXISTS (
                        SELECT 1
                        FROM employee_documents ed
                        WHERE ed.org_id = $1
                          AND ed.employee_id = e.id
                          AND ed.doc_type = $2
                          AND ed.status IN ('pending_signature', 'signed')
                    ) AS already_assigned
                FROM employees e
                WHERE e.org_id = $1
                  AND e.termination_date IS NULL
                  AND e.email IS NOT NULL
                ORDER BY e.created_at ASC
                """,
                company_id,
                doc_type,
            )

        return [
            HandbookDistributionRecipientResponse(
                employee_id=row["employee_id"],
                name=row["name"],
                email=row["email"],
                invitation_status=row["invitation_status"],
                already_assigned=bool(row["already_assigned"]),
            )
            for row in rows
        ]

    @staticmethod
    async def get_acknowledgement_summary(
        handbook_id: str,
        company_id: str,
    ) -> Optional[HandbookAcknowledgementSummary]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            return None

        doc_type = f"handbook:{handbook_id}:{handbook.active_version}"
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int AS assigned_count,
                    COUNT(*) FILTER (WHERE status = 'signed')::int AS signed_count,
                    COUNT(*) FILTER (WHERE status = 'pending_signature')::int AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'expired')::int AS expired_count
                FROM employee_documents
                WHERE org_id = $1 AND doc_type = $2
                """,
                company_id,
                doc_type,
            )

        return HandbookAcknowledgementSummary(
            handbook_id=UUID(handbook_id),
            handbook_version=handbook.active_version,
            assigned_count=row["assigned_count"] if row else 0,
            signed_count=row["signed_count"] if row else 0,
            pending_count=row["pending_count"] if row else 0,
            expired_count=row["expired_count"] if row else 0,
        )

    @staticmethod
    async def generate_handbook_pdf_bytes(
        handbook_id: str,
        company_id: str,
    ) -> tuple[bytes, str]:
        handbook = await HandbookService.get_handbook_by_id(handbook_id, company_id)
        if handbook is None:
            raise ValueError("Handbook not found")

        scope_label = ", ".join(sorted({scope.state for scope in handbook.scopes})) or "N/A"
        section_html = "".join(
            f"""
            <section class="section">
                <h2>{html.escape(section.title)}</h2>
                <div class="content">{html.escape(section.content).replace("\n", "<br/>")}</div>
            </section>
            """
            for section in handbook.sections
        )

        html_content = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    color: #111827;
                    margin: 40px;
                    line-height: 1.45;
                }}
                h1 {{
                    margin: 0 0 6px 0;
                    font-size: 26px;
                }}
                .meta {{
                    color: #4b5563;
                    font-size: 12px;
                    margin-bottom: 20px;
                }}
                .profile {{
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin-bottom: 16px;
                    font-size: 12px;
                }}
                .section {{
                    margin-top: 18px;
                    page-break-inside: avoid;
                }}
                .section h2 {{
                    font-size: 16px;
                    margin-bottom: 6px;
                    border-bottom: 1px solid #e5e7eb;
                    padding-bottom: 4px;
                }}
                .content {{
                    font-size: 12px;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <h1>{html.escape(handbook.title)}</h1>
            <div class="meta">Version {handbook.active_version} • Scope: {html.escape(scope_label)} • Status: {html.escape(handbook.status)}</div>
            <div class="profile">
                <div><strong>Legal Name:</strong> {html.escape(handbook.profile.legal_name)}</div>
                <div><strong>DBA:</strong> {html.escape(handbook.profile.dba or "N/A")}</div>
                <div><strong>CEO/President:</strong> {html.escape(handbook.profile.ceo_or_president)}</div>
                <div><strong>Headcount:</strong> {html.escape(str(handbook.profile.headcount) if handbook.profile.headcount is not None else "N/A")}</div>
            </div>
            {section_html}
        </body>
        </html>
        """

        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError("PDF generation is not available because WeasyPrint is not installed") from exc

        pdf_bytes = HTML(string=html_content).write_pdf()
        filename = _handbook_filename(handbook.title, handbook.active_version)
        return pdf_bytes, filename
