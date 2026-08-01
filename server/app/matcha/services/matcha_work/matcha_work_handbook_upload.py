from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from google.genai import types

from app.matcha.services.matcha_work.message_shapes import _sse_data

logger = logging.getLogger(__name__)

from ....core.services.compliance_service import get_location_requirements, get_locations
from ....core.services.handbook_service import (
    MANDATORY_STATE_TOPIC_LABELS,
    MANDATORY_STATE_TOPIC_RULES,
    STATE_NAMES,
)
from ....core.services.model_catalog import GEMINI_FLASH
from ....core.services.storage import get_storage
from ..er.er_document_parser import ERDocumentParser
from . import matcha_work_document as doc_svc
from .matcha_work_ai import _infer_skill_from_state, get_ai_provider

# _sse_data and _build_thread_detail_response stay in routes/matcha_work/
# _shared.py — half a dozen other route submodules import them, and they are
# genuinely HTTP-layer (SSE wire framing, response-model assembly). Imported
# lazily inside run_handbook_upload rather than at module scope: threads.py
# imports THIS module at import time, so a top-level reach back into the same
# route package would be a live cycle.

CORE_SECTION_KEYS = {
    "welcome",
    "employment_relationship",
    "equal_opportunity",
    "hours_and_pay",
    "attendance_and_remote",
    "benefits_and_leave",
    "workplace_standards",
    "investigations",
    "acknowledgement",
}
MAX_SECTION_PREVIEWS = 12
MAX_RED_FLAGS = 50

# Relevance detection: if a document matches fewer than MIN_HANDBOOK_SIGNALS
# of these phrases it almost certainly isn't an employee handbook.
HANDBOOK_SIGNAL_PHRASES: tuple[str, ...] = (
    "employee handbook",
    "company handbook",
    "staff handbook",
    "employment",
    "employer",
    "at-will",
    "at will",
    "equal opportunity",
    "equal employment",
    "anti-harassment",
    "harassment",
    "discrimination",
    "workplace",
    "human resources",
    "company policy",
    "company policies",
    "code of conduct",
    "termination",
    "disciplinary",
    "compensation",
    "benefits",
    "paid time off",
    "paid leave",
    "sick leave",
    "vacation",
    "overtime",
    "minimum wage",
    "onboarding",
    "probationary",
    "confidentiality",
    "non-disclosure",
    "workers' compensation",
    "workers compensation",
    "safety",
    "osha",
    "fmla",
    "ada",
    "eeoc",
    "flsa",
)
MIN_HANDBOOK_SIGNALS = 3
KEYWORD_FAST_PATH_THRESHOLD = 10
RELEVANCE_MODEL = GEMINI_FLASH
RELEVANCE_TIMEOUT = 15  # seconds
RELEVANCE_SAMPLE_CHARS = 3000

RELEVANCE_SYSTEM_PROMPT = """\
You classify whether a document is a US employee or company handbook.

A handbook is a comprehensive document given to employees covering MULTIPLE
areas of employment: workplace policies, benefits, code of conduct, leave,
pay practices, anti-harassment, disciplinary procedures, separation, etc.
It may be called "employee handbook", "staff handbook", "policy manual",
"employee manual", "team member guide", or "associate handbook".

A handbook is NOT a single standalone policy, an employment contract for one
person, a benefits enrollment packet, a training manual, or any other
narrowly-scoped HR document — even if it uses employment terminology.

## Examples

INPUT: "EMPLOYEE HANDBOOK — Welcome to our team. This handbook is intended to \
provide you with a general understanding of our personnel policies. Employment \
with the Company is at-will. SECTION 3 COMPENSATION: Employees are paid on a \
bi-weekly basis via direct deposit. Non-exempt employees will receive overtime \
pay in accordance with applicable federal and state law. All overtime must be \
approved by your supervisor in advance. SECTION 4 TIME OFF: Full-time employees \
are eligible for paid time off and sick leave as outlined below. SECTION 5 \
CONDUCT: The Company is committed to providing a workplace free from \
discrimination and harassment..."
OUTPUT: {"is_handbook": true, "document_type": "employee handbook", "reason": "Multi-section employee handbook covering compensation, overtime, time off, sick leave, and workplace conduct policies"}

INPUT: "TEAM MEMBER GUIDE — All crew members should review this guide during \
orientation. Our Culture and Values. Employment At Will. Equal Opportunity \
Employer. Scheduling and Attendance: Your manager will post schedules at least \
one week in advance. Meal and rest breaks are provided in accordance with \
state law. Pay Practices: You will be paid every other Friday. Tips and \
gratuities belong to you. Paid Sick Leave: You will accrue sick time based on \
hours worked. Workplace Safety: Report any hazard immediately to your \
manager. Separation: Upon leaving, your final paycheck will be issued as \
required by state law..."
OUTPUT: {"is_handbook": true, "document_type": "employee handbook", "reason": "Hospitality team member guide covering scheduling, breaks, pay, sick leave, safety, and separation — standard handbook topics in employee-facing language"}

INPUT: "TABLE OF CONTENTS 1 Welcome Letter 2 About the Company 3 Employment \
Relationship 4 Equal Opportunity and Anti-Harassment 5 Hours of Work and \
Attendance 6 Compensation and Pay Periods 7 Benefits Overview 8 Leaves of \
Absence 9 Workplace Standards and Conduct 10 Health and Safety \
11 Acknowledgement of Receipt..."
OUTPUT: {"is_handbook": true, "document_type": "employee handbook", "reason": "Handbook table of contents spanning employment, compensation, benefits, leave, conduct, and safety with acknowledgement page"}

INPUT: "EMPLOYMENT AGREEMENT — This agreement is entered into between Jane Doe \
('Employee') and Acme Corp ('Employer'). Position: Senior Manager. Start Date: \
March 1, 2024. Base Salary: $95,000/year paid semi-monthly. Benefits: Medical, \
dental, vision eligible after 30 days. At-Will Employment. Governing Law: \
State of California. Non-compete: 12 months post-termination. Severance: 4 \
weeks base salary upon involuntary termination without cause..."
OUTPUT: {"is_handbook": false, "document_type": "employment contract", "reason": "Individual employment agreement for one person with specific salary, start date, and severance terms — not a company-wide policy handbook"}

INPUT: "Paid Sick Leave Policy — Effective July 1, 2024. Purpose: To establish \
guidelines for the accrual and use of paid sick leave. Eligibility: All \
employees who work 30 or more days within a year. Accrual: Employees accrue \
one hour of sick leave for every 30 hours worked, up to a maximum of 80 hours. \
Permitted Uses: Employee's own illness, caring for a family member, domestic \
violence. Requesting Time: Notify your supervisor as soon as practicable..."
OUTPUT: {"is_handbook": false, "document_type": "standalone policy", "reason": "Single-topic policy document covering only sick leave accrual and usage — not a comprehensive handbook even though it applies company-wide"}

INPUT: "2024 Benefits Enrollment Guide — Open Enrollment: November 1-15. \
Medical Plans: PPO ($250/mo employee-only), HMO ($180/mo). Dental: Delta \
Dental ($22/mo). Vision: VSP ($8/mo). HSA contribution limits: $4,150 \
individual. Life Insurance: 1x annual salary at no cost. 401(k): Company \
matches 4% after one year. COBRA continuation: 18 months. To enroll or make \
changes visit benefits.company.com..."
OUTPUT: {"is_handbook": false, "document_type": "benefits enrollment guide", "reason": "Benefits enrollment packet listing insurance plan options, pricing, and enrollment instructions — not employment policies"}

INPUT: "Food Safety Training Manual — Required for all kitchen and service \
staff. Chapter 1: Personal Hygiene. Chapter 2: Temperature Control and HACCP. \
Chapter 3: Cross-Contamination Prevention. Chapter 4: Cleaning and Sanitizing \
Procedures. Chapter 5: Allergen Management. All team members must complete \
this training within 30 days of hire. Certification is valid for two years..."
OUTPUT: {"is_handbook": false, "document_type": "training manual", "reason": "Operational food safety training manual — covers hygiene and HACCP procedures, not employment policies or workplace conduct"}

INPUT: "COLLECTIVE BARGAINING AGREEMENT between UNITE HERE Local 11 and Pacific \
Hotels Group, Inc. Effective July 1, 2023 through June 30, 2026. Article 1: \
Recognition. Article 3: Wages and Job Classifications. Article 4: Hours of \
Work and Overtime. Article 5: Holidays and Vacation. Article 6: Health and \
Welfare Fund. Article 8: Grievance and Arbitration Procedure. Article 10: \
No Strike / No Lockout..."
OUTPUT: {"is_handbook": false, "document_type": "collective bargaining agreement", "reason": "Union CBA governing wages and working conditions through negotiated articles — not a company-issued employee handbook"}

Respond with ONLY a JSON object: {"is_handbook": boolean, "document_type": "short label", "reason": "one sentence"}
"""


def _keyword_relevance_check(text: str) -> tuple[Optional[bool], Optional[str]]:
    """Keyword-based relevance check. Returns (True/False/None, reason).

    None means ambiguous — the caller should escalate to LLM classification.
    """
    lowered = (text or "").lower()
    if not lowered:
        return False, "The uploaded file contains no readable text."

    matched = sum(1 for phrase in HANDBOOK_SIGNAL_PHRASES if phrase in lowered)

    # Fast-path: obviously a handbook
    if matched >= KEYWORD_FAST_PATH_THRESHOLD:
        return True, None

    # Obviously not a handbook
    if matched < MIN_HANDBOOK_SIGNALS:
        # Try to give a specific hint about what the document actually is.
        wrong_doc_hints = [
            (("menu", "appetizer", "entrée", "entree", "dessert", "beverage"), "a restaurant menu"),
            (("invoice", "bill to", "amount due", "payment terms", "remit to"), "an invoice"),
            (("lease", "landlord", "tenant", "rent", "premises"), "a lease agreement"),
            (("resume", "curriculum vitae", "work experience", "objective", "references"), "a resume or CV"),
            (("proposal", "scope of work", "deliverables", "timeline", "milestones"), "a project proposal"),
            (("marketing", "campaign", "brand", "target audience", "social media"), "marketing material"),
            (("recipe", "ingredients", "tablespoon", "preheat", "serving"), "a recipe document"),
        ]
        for keywords, label in wrong_doc_hints:
            if sum(1 for kw in keywords if kw in lowered) >= 2:
                return False, (
                    f"This document appears to be {label}, not an employee handbook. "
                    "Please upload your company's employee handbook (PDF or DOCX) and try again."
                )

        return False, (
            "This document does not appear to be an employee handbook — it lacks standard "
            "handbook language (employment policies, benefits, workplace conduct, etc.). "
            "Please upload your company's employee handbook and try again."
        )

    # Ambiguous zone (MIN_HANDBOOK_SIGNALS <= matched < KEYWORD_FAST_PATH_THRESHOLD)
    return None, None


async def check_handbook_relevance(text: str, client: Any = None) -> tuple[bool, Optional[str]]:
    """Classify whether a document is an employee handbook.

    Uses a two-tier approach:
    1. Keyword fast-path: if 10+ handbook signals match, return True immediately.
    2. LLM classification via Gemini Flash for ambiguous documents.
    3. Falls back to keyword logic on any LLM failure.

    Returns (is_relevant, rejection_reason). If is_relevant is True the second
    element is None.
    """
    # Tier 1: keyword check
    keyword_result, keyword_reason = _keyword_relevance_check(text)
    if keyword_result is not None:
        return keyword_result, keyword_reason

    # Tier 2: LLM classification for ambiguous documents
    if client is not None:
        try:
            sample = text[:RELEVANCE_SAMPLE_CHARS]
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=RELEVANCE_MODEL,
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part(text=sample)],
                    )],
                    config=types.GenerateContentConfig(
                        system_instruction=RELEVANCE_SYSTEM_PROMPT,
                        temperature=0.0,
                    ),
                ),
                timeout=RELEVANCE_TIMEOUT,
            )
            raw = (response.text or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
                raw = raw.strip()
            parsed = json.loads(raw)

            if parsed.get("is_handbook"):
                return True, None

            doc_type = parsed.get("document_type", "non-handbook document")
            reason = parsed.get("reason", "")
            return False, (
                f"This document appears to be a {doc_type}, not an employee handbook. "
                f"{reason} "
                "Please upload your company's employee handbook (PDF or DOCX) and try again."
            )
        except Exception:
            logger.warning("LLM handbook relevance check failed, falling back to keyword logic", exc_info=True)

    # Fallback: use keyword logic for the ambiguous zone.
    # In the ambiguous zone (3-9 matches) we default to allowing the upload
    # so we don't block legitimate handbooks with unusual phrasing.
    return True, None


@dataclass
class ParsedHandbookSection:
    title: str
    content: str
    section_key: str
    section_type: str


@dataclass
class AuditedLocation:
    id: UUID
    label: str
    state: str
    city: Optional[str]
    requirements: list[Any]


def derive_handbook_title(filename: str) -> str:
    raw_name = (filename or "").strip()
    if not raw_name:
        return "Uploaded Employee Handbook"
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", raw_name)
    cleaned = re.sub(r"[_\-]+", " ", stem).strip()
    return cleaned.title() if cleaned else "Uploaded Employee Handbook"


def _slugify(value: str, fallback: str = "uploaded_handbook") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or fallback


def _clean_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _looks_like_heading(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or len(stripped) > 90:
        return False
    if re.fullmatch(r"(page|pg)\s+\d+", stripped, flags=re.IGNORECASE):
        return False
    if re.match(r"^\d+(\.\d+)*[\s:-]", stripped):
        return True
    if stripped.endswith(":"):
        return True
    letters = re.sub(r"[^A-Za-z]", "", stripped)
    if letters and stripped.isupper():
        return True
    words = stripped.split()
    if 1 <= len(words) <= 8 and stripped == stripped.title():
        return True
    return False


def parse_handbook_sections(text: str) -> list[ParsedHandbookSection]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    blocks = [block.strip() for block in re.split(r"\n\s*\n+", cleaned) if block.strip()]
    sections: list[ParsedHandbookSection] = []
    current_title = "Uploaded Handbook"
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_parts
        content = "\n\n".join(part for part in current_parts if part.strip()).strip()
        if not content:
            return
        section_key = _slugify(current_title)
        section_type = "core" if section_key in CORE_SECTION_KEYS else "uploaded"
        sections.append(
            ParsedHandbookSection(
                title=current_title,
                content=content,
                section_key=section_key,
                section_type=section_type,
            )
        )

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        heading = lines[0] if _looks_like_heading(lines[0]) else None
        if heading:
            flush()
            current_title = re.sub(r"^\d+(\.\d+)*[\s:-]*", "", heading).strip(" :.-") or "Section"
            current_parts = ["\n".join(lines[1:]).strip()] if len(lines) > 1 else []
        else:
            current_parts.append("\n".join(lines))

    flush()

    if sections:
        return sections

    chunks = [chunk.strip() for chunk in re.split(r"(?<=\.)\s{2,}", cleaned) if chunk.strip()]
    fallback_sections: list[ParsedHandbookSection] = []
    for idx, chunk in enumerate(chunks[:MAX_SECTION_PREVIEWS], start=1):
        fallback_sections.append(
            ParsedHandbookSection(
                title=f"Section {idx}",
                content=chunk,
                section_key=f"section_{idx}",
                section_type="uploaded",
            )
        )
    return fallback_sections


def _state_specific_content(sections: Iterable[ParsedHandbookSection], state: str, all_states: list[str]) -> str:
    sections = list(sections)
    state_code = (state or "").upper()
    state_name = STATE_NAMES.get(state_code, state_code).lower()
    abbrev_re = re.compile(r"\b" + re.escape(state_code) + r"\b") if len(state_code) == 2 else None

    matched: list[str] = []
    for section in sections:
        haystack = f"{section.title}\n{section.content}"
        haystack_lower = haystack.lower()
        if state_name and state_name in haystack_lower:
            matched.append(section.content)
        elif abbrev_re and abbrev_re.search(haystack):
            matched.append(section.content)

    if matched:
        return "\n\n".join(matched)
    # Fall back to full handbook text so multi-state handbooks with generic
    # language are checked per-category rather than flagging everything red.
    return "\n\n".join(section.content for section in sections)


def _city_specific_content(sections: Iterable[ParsedHandbookSection], city: Optional[str]) -> str:
    city_name = (city or "").strip().lower()
    if not city_name:
        return ""
    matched = []
    for section in sections:
        haystack = f"{section.title}\n{section.content}".lower()
        if city_name in haystack:
            matched.append(section.content)
    return "\n\n".join(matched)


def _keyword_list(category: str, requirement_title: str) -> list[str]:
    normalized_category = (category or "").strip().lower()
    if normalized_category in MANDATORY_STATE_TOPIC_RULES:
        return list(MANDATORY_STATE_TOPIC_RULES[normalized_category])

    words = [
        word
        for word in re.split(r"[^a-z0-9]+", f"{normalized_category} {requirement_title.lower()}")
        if len(word) >= 5
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        deduped.append(word)
    return deduped[:6]


def _category_label(category: str) -> str:
    normalized_category = (category or "").strip().lower()
    return MANDATORY_STATE_TOPIC_LABELS.get(
        normalized_category,
        normalized_category.replace("_", " ").title() or "Jurisdiction requirement",
    )


def _severity_rank(value: str) -> int:
    order = {"high": 0, "medium": 1, "low": 2}
    return order.get(value, 99)


HIGH_SEVERITY_CATEGORIES = {
    "minimum_wage", "overtime", "pay_frequency",
    "final_pay", "sick_leave", "meal_breaks",
}
MEDIUM_SEVERITY_CATEGORIES = {
    "minor_work_permit", "scheduling_reporting",
    "harassment", "workers_compensation",
}


def _assign_severity(category: str) -> str:
    cat = (category or "").strip().lower()
    if cat in HIGH_SEVERITY_CATEGORIES:
        return "high"
    if cat in MEDIUM_SEVERITY_CATEGORIES:
        return "medium"
    return "low"


_MIN_CONTENT_CHARS = 50


def _keyword_match_with_depth(lowered_text: str, keywords: list[str], category: str) -> bool:
    """Check if any keyword appears in text with sufficient surrounding content.

    For HIGH/MEDIUM severity categories (mandatory), the keyword must appear
    in a paragraph of at least _MIN_CONTENT_CHARS characters so that a bare
    table-of-contents line like "4. Minimum Wage" doesn't count as coverage.
    For low-severity (fallback) categories, any match suffices.
    """
    if not keywords:
        return False
    cat = (category or "").strip().lower()
    needs_depth = cat in HIGH_SEVERITY_CATEGORIES or cat in MEDIUM_SEVERITY_CATEGORIES
    for keyword in keywords:
        if keyword not in lowered_text:
            continue
        if not needs_depth:
            return True
        for para in lowered_text.split("\n\n"):
            if keyword in para and len(para) >= _MIN_CONTENT_CHARS:
                return True
    return False


def _audit_location_group(
    *,
    parsed_sections: list[ParsedHandbookSection],
    locations_subset: list[AuditedLocation],
    all_states: list[str],
    total_location_count: int,
    seen_flag_keys: set[str],
) -> tuple[list[dict], list[dict], dict[str, dict[str, set[str]]]]:
    """Audit a subset of locations against parsed handbook sections.

    Returns (red_flags, green_flags, location_coverage).
    ``seen_flag_keys`` is mutated in-place so successive calls share dedup state.
    """
    red_flags: list[dict] = []
    green_flags: list[dict] = []
    location_coverage: dict[str, dict[str, set[str]]] = {}

    for location in locations_subset:
        state_text = _state_specific_content(parsed_sections, location.state, all_states)
        city_text = _city_specific_content(parsed_sections, location.city)
        location_text = city_text or state_text or (
            "\n\n".join(section.content for section in parsed_sections)
            if total_location_count == 1 else ""
        )
        lowered_text = location_text.lower()

        categories: dict[str, list[Any]] = {}
        for requirement in location.requirements:
            category = str(getattr(requirement, "category", "") or "").strip().lower()
            if not category:
                continue
            categories.setdefault(category, []).append(requirement)

        loc_key = location.label
        if loc_key not in location_coverage:
            location_coverage[loc_key] = {"covered": set(), "total": set(), "state": {location.state}, "city": {location.city}}
        else:
            location_coverage[loc_key]["state"].add(location.state)
            location_coverage[loc_key]["city"].add(location.city)

        for category, requirements in categories.items():
            location_coverage[loc_key]["total"].add(category)
            requirement_title = str(getattr(requirements[0], "title", "") or "")
            keywords = _keyword_list(category, requirement_title)
            label = _category_label(category)
            flag_key = f"{location.label}:{category}"

            if keywords and _keyword_match_with_depth(lowered_text, keywords, category):
                location_coverage[loc_key]["covered"].add(category)
                if flag_key not in seen_flag_keys:
                    seen_flag_keys.add(flag_key)
                    green_flags.append(
                        {
                            "id": _slugify(flag_key, fallback=str(uuid4())),
                            "jurisdiction": location.label,
                            "category": category,
                            "category_label": label,
                            "summary": f"Handbook addresses {label} for {location.label}.",
                        }
                    )
                continue

            if flag_key in seen_flag_keys:
                continue
            seen_flag_keys.add(flag_key)

            evidence_bits: list[str] = []
            for requirement in requirements[:3]:
                jurisdiction_name = str(getattr(requirement, "jurisdiction_name", "") or location.label).strip()
                current_value = str(getattr(requirement, "current_value", "") or getattr(requirement, "title", "") or "").strip()
                if current_value:
                    evidence_bits.append(f"{jurisdiction_name}: {current_value}")
            why = (
                "Synced compliance data for this jurisdiction includes "
                + "; ".join(evidence_bits)
                if evidence_bits
                else f"Synced compliance data for {location.label} includes a current {label.lower()} requirement."
            )
            red_flags.append(
                {
                    "id": _slugify(flag_key, fallback=str(uuid4())),
                    "severity": _assign_severity(category),
                    "jurisdiction": location.label,
                    "section_title": "Jurisdiction coverage",
                    "summary": f"No clear handbook coverage found for {label} in {location.label}.",
                    "why_it_matters": why,
                    "recommended_action": (
                        f"Add or revise handbook language for {label.lower()} that applies to {location.label} "
                        "and verify it matches the synced /compliance requirements."
                    ),
                }
            )

    return red_flags, green_flags, location_coverage


def compute_coverage_summaries(
    location_coverage: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, Any]], int, str]:
    """Compute jurisdiction summaries and overall strength from location_coverage.

    Returns (jurisdiction_summaries, strength_score, strength_label).
    """
    jurisdiction_summaries: list[dict[str, Any]] = []
    total_covered = 0
    total_required = 0
    for loc_label, info in location_coverage.items():
        covered = info["covered"]
        total = info["total"]
        total_covered += len(covered)
        total_required += len(total)
        missing = total - covered
        states_set = info.get("state", set())
        cities_set = info.get("city", set())
        jurisdiction_summaries.append(
            {
                "location_label": loc_label,
                "state": next(iter(states_set)) if states_set else "",
                "city": next((c for c in cities_set if c), None),
                "covered_count": len(covered),
                "total_count": len(total),
                "covered_categories": sorted(covered),
                "missing_categories": sorted(missing),
            }
        )

    strength_score = round((total_covered / total_required) * 100) if total_required > 0 else 0
    if strength_score >= 80:
        strength_label = "Strong"
    elif strength_score >= 50:
        strength_label = "Moderate"
    else:
        strength_label = "Weak"

    return jurisdiction_summaries, strength_score, strength_label


def audit_uploaded_handbook(
    *,
    thread_id: UUID,
    company_id: UUID,
    company_name: str,
    company_industry: Optional[str],
    uploaded_file_url: str,
    uploaded_filename: str,
    extracted_text: str,
    locations: list[AuditedLocation],
) -> dict[str, Any]:
    parsed_sections = parse_handbook_sections(extracted_text)
    if not parsed_sections:
        raise ValueError("No readable handbook text found in the uploaded file")

    handbook_title = derive_handbook_title(uploaded_filename)
    seen_flag_keys: set[str] = set()
    all_states = sorted({loc.state for loc in locations})

    red_flags, green_flags, location_coverage = _audit_location_group(
        parsed_sections=parsed_sections,
        locations_subset=locations,
        all_states=all_states,
        total_location_count=len(locations),
        seen_flag_keys=seen_flag_keys,
    )

    red_flags.sort(key=lambda item: (_severity_rank(item["severity"]), item["jurisdiction"], item["section_title"]))
    total_red_flag_count = len(red_flags)
    red_flags = red_flags[:MAX_RED_FLAGS]

    jurisdiction_summaries, strength_score, strength_label = compute_coverage_summaries(location_coverage)

    return {
        "handbook_title": handbook_title,
        "handbook_mode": "single_state" if len({loc.state for loc in locations}) <= 1 else "multi_state",
        "handbook_states": sorted({loc.state for loc in locations}),
        "handbook_sections": [
            {
                "section_key": section.section_key,
                "title": section.title,
                "content": section.content[:500],
                "section_type": section.section_type,
            }
            for section in parsed_sections[:MAX_SECTION_PREVIEWS]
        ],
        "handbook_review_locations": [loc.label for loc in locations],
        "handbook_red_flags": red_flags,
        "handbook_green_flags": green_flags,
        "handbook_jurisdiction_summaries": jurisdiction_summaries,
        "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
        "handbook_strength_score": strength_score,
        "handbook_strength_label": strength_label,
        "handbook_total_red_flag_count": total_red_flag_count,
    }


# ---------------------------------------------------------------------------
# Upload flow (moved out of routes/matcha_work/threads.py, refactor round 2
# stage 5). The route keeps auth + the 404/400 shell; everything below --
# validation, S3 upload, text extraction, relevance gate, and the quarterly
# SSE audit generator -- is service work.
# ---------------------------------------------------------------------------

HANDBOOK_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}
HANDBOOK_UPLOAD_MAX_BYTES = 10 * 1024 * 1024


def _location_label(location: dict) -> str:
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip().upper()
    return f"{city}, {state}" if city else state


def _thread_accepts_handbook_upload(thread: dict) -> bool:
    current_state = thread.get("current_state") or {}
    current_skill = _infer_skill_from_state(current_state)
    if current_skill == "chat":
        return True
    if current_skill != "handbook":
        return False
    # Reject if an analysis is already in progress.
    if current_state.get("handbook_upload_status") == "analyzing":
        return False
    source_type = current_state.get("handbook_source_type")
    # Allow upload if already in upload mode OR if source type hasn't been
    # committed yet (user started chatting about a handbook but can still
    # switch to upload mode via the paperclip button).
    if source_type in ("upload", None):
        return True
    return False


def _build_handbook_block_message(location_labels: list[str]) -> str:
    if not location_labels:
        return (
            "Handbook upload audit is blocked because no active Compliance Locations were found. "
            "Add or sync company locations in /compliance first."
        )
    if len(location_labels) == 1:
        scoped = location_labels[0]
    else:
        scoped = ", ".join(location_labels[:6])
        if len(location_labels) > 6:
            scoped += f", and {len(location_labels) - 6} more"
    return (
        "Handbook upload audit is blocked because these active Compliance Locations are not fully synced: "
        f"{scoped}. Fix /compliance coverage first, then retry the upload."
    )


def _build_handbook_upload_summary(
    *,
    file_name: str,
    reviewed_locations: list[str],
    red_flags: list[dict],
    green_flags: list[dict] | None = None,
    jurisdiction_summaries: list[dict] | None = None,
    blocked_message: Optional[str] = None,
) -> str:
    if blocked_message:
        return blocked_message

    passing_count = len(green_flags or [])
    gap_count = len(red_flags)

    if not red_flags:
        return (
            f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
            f"{passing_count} requirement(s) covered, no jurisdiction coverage gaps detected."
        )

    counts = {"high": 0, "medium": 0, "low": 0}
    for row in red_flags:
        severity = str(row.get("severity") or "medium").lower()
        if severity in counts:
            counts[severity] += 1

    severity_bits = []
    for severity in ("high", "medium", "low"):
        count = counts[severity]
        if count:
            severity_bits.append(f"{count} {severity}")

    severity_summary = ", ".join(severity_bits) if severity_bits else f"{gap_count} issue(s)"

    # Per-jurisdiction coverage snippet
    jurisdiction_bits: list[str] = []
    for js in (jurisdiction_summaries or []):
        jurisdiction_bits.append(f"{js['location_label']} {js['covered_count']}/{js['total_count']}")
    jurisdiction_snippet = (" | ".join(jurisdiction_bits) + ".") if jurisdiction_bits else ""

    return (
        f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
        f"{passing_count} passing, {severity_summary} red flag(s). "
        + (f"Coverage: {jurisdiction_snippet} " if jurisdiction_snippet else "")
        + "Review the Preview panel for details."
    )


async def run_handbook_upload(
    *,
    thread_id: UUID,
    company_id: UUID,
    thread: dict,
    raw_filename: Optional[str],
    content: bytes,
    content_type: Optional[str],
) -> Optional[AsyncIterator[str]]:
    """Audit an uploaded handbook against the company's synced jurisdictions.

    Returns ``None`` when the upload was blocked or rejected -- the thread
    state and the explanatory messages have already been written, and the
    caller should just re-read the thread. Otherwise returns the SSE generator
    for the happy-path incremental analysis.

    Raises HTTPException for the caller to surface verbatim (bad extension,
    empty/oversized file, unreadable text).
    """
    # Lazy — see the note beside this module's imports (threads.py imports us
    # at module scope, so a top-level import of its package would cycle).
    # `_build_thread_detail_response` is genuinely routes-layer (raises
    # HTTPException, builds the response model) and threads.py imports THIS
    # module at scope, so it stays lazy. `_sse_data` is pure and now lives in
    # a services leaf — imported at module scope above.
    from app.matcha.routes.matcha_work._shared import _build_thread_detail_response

    filename = (raw_filename or "handbook.pdf").strip() or "handbook.pdf"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in HANDBOOK_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and DOC handbooks are supported")

    active_locations = [
        loc for loc in await get_locations(company_id)
        if loc.get("is_active", True)
    ]
    active_location_labels = [_location_label(loc) for loc in active_locations if _location_label(loc)]
    unsynced_labels = [
        _location_label(loc)
        for loc in active_locations
        if loc.get("data_status") != "synced" and _location_label(loc)
    ]
    if not active_locations or unsynced_labels:
        blocking_message = _build_handbook_block_message(
            unsynced_labels if unsynced_labels else active_location_labels
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": active_location_labels,
                "handbook_red_flags": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Blocked handbook upload audit",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Handbook upload attempted for {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return None

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded handbook file is empty")
    if len(content) > HANDBOOK_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Handbook file exceeds the 10 MB limit")

    try:
        extracted_text, _page_count = ERDocumentParser().extract_text_from_bytes(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to extract handbook upload text for thread %s: %s", thread_id, exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to read the uploaded handbook file") from exc

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable handbook text was found in the uploaded file")

    # Quick relevance check — reject clearly wrong documents before expensive work.
    is_handbook, rejection_reason = await check_handbook_relevance(extracted_text, get_ai_provider().client)
    if not is_handbook:
        blocking_message = rejection_reason or (
            "This document does not appear to be an employee handbook. "
            "Please upload your company's employee handbook and try again."
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": [],
                "handbook_red_flags": [],
                "handbook_green_flags": [],
                "handbook_jurisdiction_summaries": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Rejected non-handbook upload",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Uploaded file: {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return None

    # --- Happy path: upload to S3, then stream incremental analysis via SSE ---

    storage = get_storage()
    uploaded_file_url = await storage.upload_file(
        content,
        filename,
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbooks"),
        content_type=content_type,
    )
    await storage.upload_file(
        extracted_text.encode("utf-8"),
        f"{os.path.splitext(filename)[0] or 'handbook'}-extracted.txt",
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbook-analysis"),
        content_type="text/plain",
    )

    # Pre-compute handbook metadata that stays constant across quarters.
    parsed_sections = parse_handbook_sections(extracted_text)
    if not parsed_sections:
        raise HTTPException(status_code=400, detail="No readable handbook text found in the uploaded file")

    handbook_title = derive_handbook_title(filename)
    all_states = sorted({str(loc.get("state") or "").strip().upper() for loc in active_locations if loc.get("state")})
    handbook_mode = "single_state" if len(set(all_states)) <= 1 else "multi_state"
    total_location_count = len(active_locations)
    all_location_labels = [_location_label(loc) for loc in active_locations if _location_label(loc)]
    section_previews = [
        {
            "section_key": section.section_key,
            "title": section.title,
            "content": section.content[:500],
            "section_type": section.section_type,
        }
        for section in parsed_sections[:MAX_SECTION_PREVIEWS]
    ]

    # Split locations into up to 4 quarter groups for incremental analysis.
    quarter_size = math.ceil(total_location_count / 4) if total_location_count else 1
    location_quarters: list[list[dict]] = [
        active_locations[i : i + quarter_size]
        for i in range(0, total_location_count, quarter_size)
    ]

    async def event_stream():
        try:
            # Mark thread as analyzing.
            await doc_svc.apply_update(
                thread_id,
                {
                    "handbook_source_type": "upload",
                    "handbook_upload_status": "analyzing",
                    "handbook_analysis_progress": 0,
                    "handbook_title": handbook_title,
                    "handbook_uploaded_file_url": uploaded_file_url,
                    "handbook_uploaded_filename": filename,
                    "handbook_mode": handbook_mode,
                    "handbook_states": all_states,
                    "handbook_sections": section_previews,
                    "handbook_review_locations": all_location_labels,
                    "handbook_blocking_error": None,
                    "handbook_error": None,
                },
                diff_summary="Started handbook analysis",
            )
            yield _sse_data({"type": "handbook_progress", "progress": 0, "status": "analyzing"})

            seen_flag_keys: set[str] = set()
            accumulated_red_flags: list[dict] = []
            accumulated_green_flags: list[dict] = []
            accumulated_coverage: dict[str, dict[str, set[str]]] = {}
            num_quarters = len(location_quarters)

            for q_idx, quarter_locs in enumerate(location_quarters, 1):
                # Fetch requirements for this quarter's locations sequentially
                # to avoid connection pool exhaustion.
                audited_locs: list[AuditedLocation] = []
                for loc in quarter_locs:
                    if not loc.get("id"):
                        continue
                    try:
                        requirements = await get_location_requirements(UUID(str(loc["id"])), company_id)
                    except Exception:
                        logger.error(
                            "Failed to load location requirements for handbook upload audit thread %s location %s",
                            thread_id,
                            loc.get("id"),
                            exc_info=True,
                        )
                        yield _sse_data({"type": "error", "message": "Failed to load synced compliance requirements."})
                        return
                    audited_locs.append(
                        AuditedLocation(
                            id=UUID(str(loc["id"])),
                            label=_location_label(loc),
                            state=str(loc.get("state") or "").strip().upper(),
                            city=str(loc.get("city") or "").strip() or None,
                            requirements=list(requirements),
                        )
                    )

                # Audit this quarter's locations.
                q_red, q_green, q_coverage = _audit_location_group(
                    parsed_sections=parsed_sections,
                    locations_subset=audited_locs,
                    all_states=all_states,
                    total_location_count=total_location_count,
                    seen_flag_keys=seen_flag_keys,
                )

                # Accumulate results.
                accumulated_red_flags.extend(q_red)
                accumulated_green_flags.extend(q_green)
                for loc_key, info in q_coverage.items():
                    if loc_key in accumulated_coverage:
                        accumulated_coverage[loc_key]["covered"] |= info["covered"]
                        accumulated_coverage[loc_key]["total"] |= info["total"]
                        accumulated_coverage[loc_key]["state"] |= info["state"]
                        accumulated_coverage[loc_key]["city"] |= info["city"]
                    else:
                        accumulated_coverage[loc_key] = info

                # Sort and cap red flags.
                sorted_red = sorted(
                    accumulated_red_flags,
                    key=lambda item: (_severity_rank(item["severity"]), item["jurisdiction"], item["section_title"]),
                )
                total_red_count = len(accumulated_red_flags)
                sorted_red = sorted_red[:MAX_RED_FLAGS]

                # Compute running summaries.
                jurisdiction_summaries, strength_score, strength_label = compute_coverage_summaries(accumulated_coverage)
                progress = q_idx / num_quarters

                partial_state = {
                    "handbook_source_type": "upload",
                    "handbook_upload_status": "analyzing",
                    "handbook_analysis_progress": progress,
                    "handbook_title": handbook_title,
                    "handbook_mode": handbook_mode,
                    "handbook_states": all_states,
                    "handbook_uploaded_file_url": uploaded_file_url,
                    "handbook_uploaded_filename": filename,
                    "handbook_blocking_error": None,
                    "handbook_error": None,
                    "handbook_sections": section_previews,
                    "handbook_review_locations": all_location_labels,
                    "handbook_red_flags": sorted_red,
                    "handbook_green_flags": accumulated_green_flags,
                    "handbook_jurisdiction_summaries": jurisdiction_summaries,
                    "handbook_strength_score": strength_score,
                    "handbook_strength_label": strength_label,
                    "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                    "handbook_total_red_flag_count": total_red_count,
                }

                await doc_svc.apply_update(
                    thread_id,
                    partial_state,
                    diff_summary=f"Handbook analysis quarter {q_idx}/{num_quarters}",
                )
                yield _sse_data({"type": "handbook_progress", "progress": progress, "partial_state": partial_state})

            # Final: mark as reviewed and add messages.
            final_state = {
                **partial_state,
                "handbook_upload_status": "reviewed",
                "handbook_analysis_progress": 1.0,
                "handbook_status": "ready",
            }
            result = await doc_svc.apply_update(
                thread_id,
                final_state,
                diff_summary=f"Uploaded handbook audit: {filename}",
            )

            summary_message = _build_handbook_upload_summary(
                file_name=filename,
                reviewed_locations=all_location_labels,
                red_flags=sorted_red,
                green_flags=accumulated_green_flags,
                jurisdiction_summaries=jurisdiction_summaries,
            )
            await doc_svc.add_message(
                thread_id,
                "system",
                f"Uploaded handbook file: {filename}.",
                version_created=result["version"],
            )
            await doc_svc.add_message(
                thread_id,
                "assistant",
                summary_message,
                version_created=result["version"],
            )

            detail = await _build_thread_detail_response(thread_id, company_id)
            yield _sse_data({"type": "complete", "data": detail.model_dump(mode="json")})
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Handbook upload stream failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Handbook analysis failed. Please try again."})

    return event_stream()
