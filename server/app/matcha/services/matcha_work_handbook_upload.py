from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from google.genai import types

logger = logging.getLogger(__name__)

from ...core.services.handbook_service import (
    MANDATORY_STATE_TOPIC_LABELS,
    MANDATORY_STATE_TOPIC_RULES,
    STATE_NAMES,
)

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
MAX_RED_FLAGS = 20

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
RELEVANCE_MODEL = "gemini-2.0-flash"
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
    state_code = (state or "").upper()
    state_name = STATE_NAMES.get(state_code, state_code).lower()
    matched: list[str] = []
    for section in sections:
        haystack = f"{section.title}\n{section.content}".lower()
        if state_name and state_name in haystack:
            matched.append(section.content)
    if matched:
        return "\n\n".join(matched)
    if len(all_states) == 1:
        return "\n\n".join(section.content for section in sections)
    return ""


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
        if len(word) >= 4
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
}


def _assign_severity(category: str) -> str:
    cat = (category or "").strip().lower()
    if cat in HIGH_SEVERITY_CATEGORIES:
        return "high"
    if cat in MEDIUM_SEVERITY_CATEGORIES:
        return "medium"
    return "low"


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

    red_flags: list[dict[str, str]] = []
    green_flags: list[dict[str, str]] = []
    seen_flag_keys: set[str] = set()
    # Per-location coverage tracking: {location_label: {covered: set, total: set}}
    location_coverage: dict[str, dict[str, set[str]]] = {}

    all_states = sorted({loc.state for loc in locations})

    for location in locations:
        state_text = _state_specific_content(parsed_sections, location.state, all_states)
        city_text = _city_specific_content(parsed_sections, location.city)
        location_text = city_text or state_text or ("\n\n".join(section.content for section in parsed_sections) if len(locations) == 1 else "")
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

            if keywords and any(keyword in lowered_text for keyword in keywords):
                # Covered — green flag
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

            # Not covered — red flag
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

    red_flags.sort(key=lambda item: (_severity_rank(item["severity"]), item["jurisdiction"], item["section_title"]))
    red_flags = red_flags[:MAX_RED_FLAGS]

    # Per-jurisdiction summaries
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
    }
