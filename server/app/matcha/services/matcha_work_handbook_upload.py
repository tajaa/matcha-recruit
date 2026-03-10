from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ...core.models.handbook import (
    CompanyHandbookProfileResponse,
    HandbookDetailResponse,
    HandbookScopeResponse,
    HandbookSectionResponse,
)
from ...core.services.handbook_service import (
    HandbookService,
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


def _build_pseudo_handbook(
    *,
    thread_id: UUID,
    company_id: UUID,
    company_name: str,
    company_industry: Optional[str],
    handbook_title: str,
    uploaded_file_url: str,
    uploaded_filename: str,
    locations: list[AuditedLocation],
    parsed_sections: list[ParsedHandbookSection],
) -> HandbookDetailResponse:
    now = datetime.now(timezone.utc)
    states = sorted({loc.state for loc in locations})

    section_rows: list[HandbookSectionResponse] = []
    for idx, section in enumerate(parsed_sections[:MAX_SECTION_PREVIEWS], start=1):
        section_rows.append(
            HandbookSectionResponse(
                id=uuid5(NAMESPACE_URL, f"{thread_id}:uploaded:{section.section_key}:{idx}"),
                section_key=section.section_key,
                title=section.title,
                content=section.content,
                section_order=idx * 10,
                section_type=section.section_type,  # type: ignore[arg-type]
                jurisdiction_scope={},
                last_reviewed_at=None,
            )
        )

    next_order = (len(section_rows) + 1) * 10
    for state in states:
        state_content = _state_specific_content(parsed_sections, state, states)
        section_rows.append(
            HandbookSectionResponse(
                id=uuid5(NAMESPACE_URL, f"{thread_id}:state:{state}"),
                section_key=f"state_addendum_{state.lower()}_uploaded",
                title=f"{STATE_NAMES.get(state, state)} Jurisdiction Review",
                content=state_content,
                section_order=next_order,
                section_type="state",
                jurisdiction_scope={"state": state},
                last_reviewed_at=None,
            )
        )
        next_order += 10

    return HandbookDetailResponse(
        id=thread_id,
        company_id=company_id,
        title=handbook_title,
        status="draft",
        mode="single_state" if len(states) <= 1 else "multi_state",
        source_type="template",
        active_version=1,
        file_url=uploaded_file_url,
        file_name=uploaded_filename,
        scopes=[
            HandbookScopeResponse(
                id=uuid5(NAMESPACE_URL, f"{thread_id}:scope:{loc.id}"),
                state=loc.state,
                city=loc.city,
                zipcode=None,
                location_id=loc.id,
            )
            for loc in locations
        ],
        profile=CompanyHandbookProfileResponse(
            company_id=company_id,
            legal_name=company_name or "Company",
            dba=None,
            ceo_or_president=company_name or "Company",
            headcount=None,
            remote_workers=False,
            minors=False,
            tipped_employees=False,
            union_employees=False,
            federal_contracts=False,
            group_health_insurance=False,
            background_checks=False,
            hourly_employees=True,
            salaried_employees=False,
            commissioned_employees=False,
            tip_pooling=False,
            updated_by=None,
            updated_at=now,
        ),
        sections=section_rows,
        created_at=now,
        updated_at=now,
        published_at=None,
        created_by=None,
    )


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
    pseudo_handbook = _build_pseudo_handbook(
        thread_id=thread_id,
        company_id=company_id,
        company_name=company_name,
        company_industry=company_industry,
        handbook_title=handbook_title,
        uploaded_file_url=uploaded_file_url,
        uploaded_filename=uploaded_filename,
        locations=locations,
        parsed_sections=parsed_sections,
    )
    coverage = HandbookService.compute_coverage(pseudo_handbook, company_industry)

    red_flags: list[dict[str, str]] = []
    seen_flag_keys: set[str] = set()

    for location in locations:
        state_text = _state_specific_content(parsed_sections, location.state, sorted({loc.state for loc in locations}))
        city_text = _city_specific_content(parsed_sections, location.city)
        location_text = city_text or state_text or ("\n\n".join(section.content for section in parsed_sections) if len(locations) == 1 else "")
        lowered_text = location_text.lower()

        categories = {}
        for requirement in location.requirements:
            category = str(getattr(requirement, "category", "") or "").strip().lower()
            if not category:
                continue
            categories.setdefault(category, []).append(requirement)

        for category, requirements in categories.items():
            requirement_title = str(getattr(requirements[0], "title", "") or "")
            keywords = _keyword_list(category, requirement_title)
            if keywords and any(keyword in lowered_text for keyword in keywords):
                continue

            label = _category_label(category)
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
            flag_key = f"{location.label}:{category}"
            if flag_key in seen_flag_keys:
                continue
            seen_flag_keys.add(flag_key)
            red_flags.append(
                {
                    "id": _slugify(flag_key, fallback=str(uuid4())),
                    "severity": "high",
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

    for missing in coverage.missing_sections:
        flag_key = f"{missing.section_key}:{missing.title}"
        if flag_key in seen_flag_keys:
            continue
        seen_flag_keys.add(flag_key)
        severity = "high" if missing.priority == "required" else "medium"
        red_flags.append(
            {
                "id": _slugify(flag_key, fallback=str(uuid4())),
                "severity": severity,
                "jurisdiction": "All covered locations",
                "section_title": missing.title,
                "summary": missing.reason,
                "why_it_matters": "The uploaded handbook does not appear to include this expected coverage based on the current company profile and jurisdiction set.",
                "recommended_action": f"Add or strengthen handbook language covering {missing.title.lower()} before relying on this handbook for those locations.",
            }
        )

    red_flags.sort(key=lambda item: (_severity_rank(item["severity"]), item["jurisdiction"], item["section_title"]))
    red_flags = red_flags[:MAX_RED_FLAGS]

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
        "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
        "handbook_strength_score": coverage.strength_score,
        "handbook_strength_label": coverage.strength_label,
    }
