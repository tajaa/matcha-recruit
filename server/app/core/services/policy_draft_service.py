import json
import logging
import os
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

from google import genai
from google.genai import types

from ...config import get_settings
from ...database import get_connection
from ..compliance_registry import CATEGORY_KEYS


@dataclass
class PolicyDraftRequest:
    policy_type: str
    location_ids: Optional[List[str]] = None
    additional_context: Optional[str] = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic policy types — always shown regardless of company industry
# ---------------------------------------------------------------------------
_GENERIC_POLICY_TYPES: List[dict] = [
    {"value": "pto_sick_leave", "label": "PTO and Sick Leave", "categories": ["sick_leave"]},
    {"value": "meal_rest_breaks", "label": "Meal and Rest Break", "categories": ["meal_breaks"]},
    {"value": "overtime", "label": "Overtime and Hours Worked", "categories": ["overtime"]},
    {"value": "pay_practices", "label": "Pay Practices and Payday", "categories": ["pay_frequency", "final_pay", "minimum_wage"]},
    {"value": "scheduling", "label": "Scheduling and Reporting Time", "categories": ["scheduling_reporting"]},
    {"value": "youth_employment", "label": "Youth Employment / Minor Work", "categories": ["minor_work_permit"]},
    {"value": "anti_harassment", "label": "Anti-Harassment and Anti-Discrimination", "categories": ["anti_discrimination"]},
    {"value": "workplace_safety", "label": "Workplace Health and Safety", "categories": ["workplace_safety"]},
    {"value": "remote_work", "label": "Remote Work / Telecommuting", "categories": [],
     "scope_guidance": "Focus on eligibility criteria, equipment and workspace requirements, data security and VPN policies, expense reimbursement, communication expectations, and performance monitoring. DO NOT include meal breaks, minimum wage, overtime, or scheduling regulations."},
    {"value": "drug_alcohol", "label": "Drug and Alcohol", "categories": [],
     "scope_guidance": "Focus on prohibited substances, drug and alcohol testing procedures, employee assistance programs (EAP), marijuana law considerations by jurisdiction, safety-sensitive positions, and consequences of violations. DO NOT include meal breaks, minimum wage, overtime, or scheduling regulations."},
    {"value": "attendance", "label": "Attendance and Punctuality", "categories": [],
     "scope_guidance": "Focus on reporting procedures, tardiness policies, no-call/no-show rules, progressive discipline for attendance violations, and excused vs. unexcused absences. DO NOT include meal breaks, minimum wage, overtime, or scheduling regulations."},
    {"value": "code_of_conduct", "label": "Code of Conduct", "categories": [],
     "scope_guidance": "Focus on professional ethics, integrity, conflicts of interest, confidentiality, workplace respect, anti-bribery/corruption, use of company resources, social media conduct, and the disciplinary process. DO NOT include leave laws (FMLA, state family/medical leave, disability leave), meal breaks, minimum wage, overtime, scheduling, PTO accrual rules, or other labor law compliance topics — those belong in separate dedicated policies."},
    {"value": "whistleblower", "label": "Whistleblower Protection", "categories": [],
     "scope_guidance": "Focus on protected activities, internal and external reporting channels, anti-retaliation protections, investigation procedures, and confidentiality of whistleblower identity. DO NOT include meal breaks, minimum wage, overtime, or scheduling regulations."},
]

# ---------------------------------------------------------------------------
# Industry-specific policy types — shown only when company industry matches
# ---------------------------------------------------------------------------
_INDUSTRY_POLICY_TYPES: List[dict] = [
    # Healthcare-specific policy types
    {"value": "hipaa_privacy", "label": "HIPAA Privacy and Security", "categories": ["hipaa_privacy"], "industries": ["healthcare"]},
    {"value": "bloodborne_pathogens", "label": "Bloodborne Pathogens Exposure Control", "categories": ["clinical_safety"], "industries": ["healthcare"]},
    {"value": "credentialing", "label": "Credentialing and Licensure Verification", "categories": ["healthcare_workforce"], "industries": ["healthcare"]},
    {"value": "patient_safety", "label": "Patient Safety and Incident Reporting", "categories": ["clinical_safety"], "industries": ["healthcare"]},
    {"value": "infection_control", "label": "Infection Control and PPE", "categories": ["clinical_safety"], "industries": ["healthcare"]},
    # Oncology-specific policy types
    {"value": "radiation_safety", "label": "Radiation Safety Program", "categories": ["radiation_safety"], "industries": ["healthcare:oncology"]},
    {"value": "chemotherapy_handling", "label": "Chemotherapy and Hazardous Drug Handling", "categories": ["chemotherapy_handling"], "industries": ["healthcare:oncology"]},
    {"value": "tumor_registry", "label": "Tumor Registry Reporting", "categories": ["tumor_registry"], "industries": ["healthcare:oncology"]},
    {"value": "oncology_clinical_trials", "label": "Clinical Trials Compliance", "categories": ["oncology_clinical_trials"], "industries": ["healthcare:oncology"]},
    {"value": "oncology_patient_rights", "label": "Oncology Patient Rights", "categories": ["oncology_patient_rights"], "industries": ["healthcare:oncology"]},
    # Medical compliance policy types
    {"value": "health_it_compliance", "label": "Health IT & Interoperability", "categories": ["health_it"], "industries": ["healthcare"]},
    {"value": "quality_reporting_compliance", "label": "Quality Reporting & Value-Based Care", "categories": ["quality_reporting"], "industries": ["healthcare"]},
    {"value": "cybersecurity_compliance", "label": "Healthcare Cybersecurity", "categories": ["cybersecurity"], "industries": ["healthcare"]},
    {"value": "environmental_safety_compliance", "label": "Environmental & Facility Safety", "categories": ["environmental_safety"], "industries": ["healthcare"]},
    {"value": "pharmacy_compliance", "label": "Pharmacy & Controlled Substances", "categories": ["pharmacy_drugs"], "industries": ["healthcare:pharmacy"]},
    {"value": "payer_relations_compliance", "label": "Payer Relations & Managed Care", "categories": ["payer_relations"], "industries": ["healthcare:managed_care"]},
    {"value": "reproductive_behavioral_compliance", "label": "Reproductive & Behavioral Health", "categories": ["reproductive_behavioral"], "industries": ["healthcare:behavioral_health"]},
    {"value": "pediatric_vulnerable_compliance", "label": "Pediatric & Vulnerable Populations", "categories": ["pediatric_vulnerable"], "industries": ["healthcare:pediatric"]},
    {"value": "telehealth_compliance", "label": "Telehealth & Digital Health", "categories": ["telehealth"], "industries": ["healthcare:telehealth"]},
    {"value": "medical_device_safety", "label": "Medical Device Safety", "categories": ["medical_devices"], "industries": ["healthcare:devices"]},
    {"value": "transplant_compliance", "label": "Transplant & Organ Procurement", "categories": ["transplant_organ"], "industries": ["healthcare:transplant"]},
    {"value": "antitrust_compliance", "label": "Healthcare Antitrust & Competition", "categories": ["antitrust"], "industries": ["healthcare"]},
    {"value": "tax_exempt_compliance", "label": "Tax-Exempt Organization Compliance", "categories": ["tax_exempt"], "industries": ["healthcare:nonprofit"]},
    {"value": "language_access_compliance", "label": "Language Access & Civil Rights", "categories": ["language_access"], "industries": ["healthcare"]},
    {"value": "records_retention_compliance", "label": "Medical Records Retention", "categories": ["records_retention"], "industries": ["healthcare"]},
    {"value": "marketing_comms_compliance", "label": "Healthcare Marketing & Communications", "categories": ["marketing_comms"], "industries": ["healthcare"]},
    {"value": "emerging_regulatory_compliance", "label": "Emerging Regulatory Compliance", "categories": ["emerging_regulatory"], "industries": ["healthcare"]},
]

POLICY_TYPES = _GENERIC_POLICY_TYPES + _INDUSTRY_POLICY_TYPES

# ---------------------------------------------------------------------------
# Validate that every policy type's categories exist in the compliance registry
# ---------------------------------------------------------------------------
for _pt in POLICY_TYPES:
    for _cat in _pt.get("categories", []):
        assert _cat in CATEGORY_KEYS, (
            f"Policy type '{_pt['value']}' references unknown category '{_cat}'. "
            f"Add it to compliance_registry.CATEGORIES or fix the policy type."
        )

# Map free-text industry values to canonical names for filtering.
_INDUSTRY_ALIASES: Dict[str, str] = {
    "health": "healthcare", "healthcare": "healthcare", "medical": "healthcare",
    "clinic": "healthcare", "hospital": "healthcare", "nursing": "healthcare",
    "pharmacy": "healthcare", "dental": "healthcare", "physician": "healthcare",
    "outpatient": "healthcare", "ambulatory": "healthcare",
    "restaurant": "hospitality", "hospitality": "hospitality", "food": "hospitality",
    "hotel": "hospitality",
    "retail": "retail", "store": "retail",
    "manufacturing": "manufacturing", "warehouse": "manufacturing",
    "construction": "manufacturing",
    "technology": "technology", "software": "technology", "saas": "technology",
}


def _resolve_industry(raw: str) -> str:
    """Resolve a free-text industry string to a canonical industry name.

    Tries exact match first, then substring match against alias keys.
    """
    raw = raw.lower().strip()
    canonical = _INDUSTRY_ALIASES.get(raw)
    if canonical:
        return canonical
    for alias_key, alias_val in _INDUSTRY_ALIASES.items():
        if alias_key in raw or raw in alias_key:
            return alias_val
    return ""

# Industry-specific prompt context appended to the policy draft prompt.
_INDUSTRY_POLICY_CONTEXT: Dict[str, str] = {
    "healthcare": (
        "\n\n## Industry Context — Healthcare\n"
        "This is a HEALTHCARE employer (hospital, clinic, medical office, nursing facility, "
        "or similar). The policy MUST reference healthcare-specific regulations including:\n"
        "- HIPAA Privacy Rule and Security Rule requirements\n"
        "- OSHA Bloodborne Pathogens Standard (29 CFR 1910.1030)\n"
        "- CMS Conditions of Participation (if applicable)\n"
        "- Joint Commission standards (if applicable)\n"
        "- State nurse practice acts and scope-of-practice rules\n"
        "- Healthcare worker safety requirements\n"
        "Use industry-appropriate terminology and reference healthcare-specific regulatory bodies."
    ),
    "healthcare:oncology": (
        "\n\n## Industry Context — Oncology\n"
        "This is an ONCOLOGY employer. The policy MUST reference oncology-specific "
        "regulations including:\n"
        "- NRC 10 CFR 35 / Agreement State radiation licensing\n"
        "- USP <800> hazardous drug handling standards\n"
        "- OSHA cytotoxic drug exposure limits\n"
        "- State tumor/cancer registry reporting requirements\n"
        "- 21 CFR 50/56 clinical trial protections (if applicable)\n"
        "Use oncology-appropriate terminology."
    ),
}


async def get_policy_types_for_company(company_id: str) -> List[dict]:
    """Return policy types filtered by the company's industry.

    Generic types (no ``industries`` key) are always included. Industry-specific
    types are included only when the company's industry tags match.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT industry, healthcare_specialties FROM companies WHERE id = $1",
            UUID(company_id),
        )
    raw_industry = (row["industry"] or "").strip() if row else ""
    canonical = _resolve_industry(raw_industry)

    # Build tag set: {"healthcare", "healthcare:oncology"} for oncology company
    company_tags = {canonical} if canonical else set()
    if canonical == "healthcare" and row and row["healthcare_specialties"]:
        for spec in row["healthcare_specialties"]:
            company_tags.add(f"healthcare:{spec}")

    result = []
    for pt in POLICY_TYPES:
        industries = pt.get("industries")
        if industries is None:
            result.append(pt)
        elif company_tags & set(industries):
            result.append(pt)
    return result

_POLICY_TYPE_MAP = {pt["value"]: pt for pt in POLICY_TYPES}

DEFAULT_MODEL = "gemini-3-flash-preview"
FALLBACK_MODEL = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    elif settings.use_vertex:
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location,
        )
    else:
        return genai.Client(api_key=settings.gemini_api_key)


def _requirement_to_context(req: dict) -> dict:
    return {
        "category": req["category"],
        "jurisdiction_level": req["jurisdiction_level"],
        "jurisdiction_name": req["jurisdiction_name"],
        "title": req["title"],
        "description": req["description"],
        "current_value": req["current_value"],
        "source_url": req["source_url"],
        "effective_date": req["effective_date"].isoformat() if req.get("effective_date") else None,
    }


async def generate_policy_draft_stream(
    company_id: str, request
) -> AsyncGenerator[dict, None]:
    """Stream a policy draft using jurisdiction data + Gemini with Google Search grounding."""

    policy_config = _POLICY_TYPE_MAP.get(request.policy_type)
    if not policy_config:
        yield {"type": "error", "message": f"Unknown policy type: {request.policy_type}"}
        return

    yield {"type": "phase", "message": "Loading company locations..."}

    async with get_connection() as conn:
        # Load company name and industry
        company_row = await conn.fetchrow(
            "SELECT name, industry FROM companies WHERE id = $1", UUID(company_id)
        )
        company_name = company_row["name"] if company_row else "the company"
        raw_industry = (company_row["industry"] or "").strip() if company_row else ""
        canonical_industry = _resolve_industry(raw_industry)
        industry_prompt_context = _INDUSTRY_POLICY_CONTEXT.get(canonical_industry, "")

        # Load locations
        if request.location_ids:
            location_ids = [UUID(lid) for lid in request.location_ids]
            locations = await conn.fetch(
                "SELECT id, city, state, county FROM business_locations WHERE company_id = $1 AND id = ANY($2)",
                UUID(company_id),
                location_ids,
            )
        else:
            locations = await conn.fetch(
                "SELECT id, city, state, county FROM business_locations WHERE company_id = $1 AND is_active = true",
                UUID(company_id),
            )

        if not locations:
            yield {"type": "error", "message": "No locations found. Add locations in Compliance first."}
            return

        yield {"type": "phase", "message": f"Found {len(locations)} location(s). Loading jurisdiction data..."}

        # Load jurisdiction requirements per location, dedup by state
        all_requirements: List[dict] = []
        seen_states: set = set()
        locations_without_data: List[str] = []
        related_categories = policy_config["categories"]

        for loc in locations:
            state = loc["state"]
            city = loc["city"]

            # Find jurisdiction for this location
            # Try city-level first, then state-level
            jurisdiction_row = None
            if city:
                jurisdiction_row = await conn.fetchrow(
                    "SELECT id FROM jurisdictions WHERE state = $1 AND city = $2",
                    state,
                    city,
                )
            if not jurisdiction_row:
                jurisdiction_row = await conn.fetchrow(
                    "SELECT id FROM jurisdictions WHERE state = $1 AND (city IS NULL OR city = '')",
                    state,
                )

            if not jurisdiction_row:
                locations_without_data.append(f"{city}, {state}" if city else state)
                continue

            jurisdiction_id = jurisdiction_row["id"]

            # Load requirements
            reqs = await conn.fetch(
                "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                jurisdiction_id,
            )

            # Filter out industry-specific requirements that don't apply
            reqs = [r for r in reqs
                    if not r.get("applicable_industries")
                    or (canonical_industry and canonical_industry in [i.lower() for i in r["applicable_industries"]])]

            if not related_categories:
                reqs = []  # No DB requirements for scope-guidance-only policy types
            else:
                reqs = [r for r in reqs if r["category"] in related_categories]

            # Dedup: for state-level, only include once per state
            for req in reqs:
                req_dict = dict(req)
                key = (req_dict["jurisdiction_level"], req_dict["jurisdiction_name"], req_dict["category"])
                if req_dict["jurisdiction_level"] == "state" and state in seen_states:
                    # Only skip state-level dupes
                    if key in {(r.get("_dedup_key")) for r in all_requirements if r.get("_dedup_key")}:
                        continue
                context = _requirement_to_context(req_dict)
                context["_dedup_key"] = key
                all_requirements.append(context)

            seen_states.add(state)

        # Clean dedup keys
        for req in all_requirements:
            req.pop("_dedup_key", None)

        if locations_without_data:
            yield {
                "type": "phase",
                "message": f"Note: No jurisdiction data for {', '.join(locations_without_data)}. Will use web search for those areas.",
            }

    # Build prompt
    policy_label = policy_config["label"]
    location_summaries = []
    for loc in locations:
        city = loc["city"]
        state = loc["state"]
        location_summaries.append(f"{city}, {state}" if city else state)

    jurisdiction_context = ""
    if all_requirements:
        jurisdiction_context = "\n\n## Structured Jurisdiction Data\nThe following legal requirements are from our compliance database. Use these as authoritative facts:\n\n"
        for req in all_requirements:
            jurisdiction_context += f"- **{req['jurisdiction_name']}** ({req['jurisdiction_level']}) — {req['category']}: "
            jurisdiction_context += f"{req['title']}"
            if req["current_value"]:
                jurisdiction_context += f" — Current value: {req['current_value']}"
            if req["description"]:
                jurisdiction_context += f"\n  Detail: {req['description']}"
            if req["source_url"]:
                jurisdiction_context += f"\n  Source: {req['source_url']}"
            if req["effective_date"]:
                jurisdiction_context += f"\n  Effective: {req['effective_date']}"
            jurisdiction_context += "\n"

    additional = ""
    if request.additional_context:
        additional = f"\n\n## Additional Company Context\n{request.additional_context}\n"

    scope_guidance_block = f"\n\n## Policy Scope Guidance\n{policy_config['scope_guidance']}\n" if policy_config.get("scope_guidance") else ""

    prompt = f"""You are an employment law attorney and HR policy writer. Draft a professional **{policy_label}** policy for **{company_name}**.

## Locations Covered
{', '.join(location_summaries)}
{jurisdiction_context}{additional}{industry_prompt_context}{scope_guidance_block}
## Instructions
1. Write a complete, professional policy document in Markdown format.
2. Include standard sections: Purpose, Scope, Definitions (if needed), Policy Statement, Procedures, and Compliance.
3. Where laws differ by jurisdiction, create jurisdiction-specific sections clearly labeled (e.g., "### California" or "### New York City").
4. When referencing specific legal requirements from the structured data above, cite the source URL in parentheses.
5. Use [COMPANY NAME] as a placeholder where the company name should appear in formal language, and [BRACKETS] for any company-specific details the user needs to fill in (e.g., [NUMBER OF PTO DAYS], [HR CONTACT EMAIL]).
6. If any company context conflicts with legal minimums from the jurisdiction data, flag it clearly with a ⚠️ warning.
7. Keep the tone professional but readable. Avoid overly legalistic jargon where plain language works.
8. Stay within the scope described in the Policy Scope Guidance section if one is provided. Do not include topics from other policy domains.
9. Use Google Search to find the latest legal requirements for any jurisdictions or topics not covered by the structured data above."""

    yield {"type": "phase", "message": "Generating policy draft with AI..."}

    # Stream from Gemini
    client = _get_client()
    models_to_try = [DEFAULT_MODEL, FALLBACK_MODEL]

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                ),
            )

            async for chunk in response:
                if chunk.text:
                    yield {"type": "content", "text": chunk.text}

            yield {"type": "complete", "message": "Policy draft generated successfully."}
            return

        except Exception as exc:
            error_msg = str(exc).lower()
            is_model_error = any(
                s in error_msg
                for s in ("not found", "unknown model", "invalid model", "unsupported")
            )
            if is_model_error and model_name != models_to_try[-1]:
                logger.warning("Model %s unavailable, falling back: %s", model_name, exc)
                continue
            logger.error("Policy draft generation failed: %s", exc)
            yield {"type": "error", "message": f"AI generation failed: {str(exc)}"}
            return

    yield {"type": "error", "message": "All AI models unavailable. Please try again later."}


# ---------------------------------------------------------------------------
# Topic-based policy drafting (freeform topic + jurisdiction)
# ---------------------------------------------------------------------------


def _match_topic_to_categories(topic: str) -> List[str]:
    """Match a freeform topic string to known policy type categories.

    Checks each policy type's label and value for a substring match
    against the topic. Returns the union of matched categories, or an
    empty list if no policy type matches (meaning we fall back to text
    search).
    """
    topic_lower = topic.lower().strip()
    matched_categories: List[str] = []
    for pt in POLICY_TYPES:
        label_lower = pt["label"].lower()
        value_lower = pt["value"].lower()
        # Check if the topic is a substring of the label/value or vice-versa
        if (
            topic_lower in label_lower
            or label_lower in topic_lower
            or topic_lower in value_lower
            or value_lower in topic_lower
        ):
            matched_categories.extend(pt["categories"])
    return list(set(matched_categories))


async def _fetch_requirements_for_topic(
    jurisdiction: str,
    topic: str,
    location_id: Optional[str] = None,
) -> List[dict]:
    """Fetch jurisdiction_requirements rows relevant to a topic + jurisdiction.

    Strategy:
    1. Find jurisdiction rows matching the jurisdiction name (state match).
    2. If the topic maps to known policy-type categories, filter by those.
    3. Otherwise, do ILIKE text search on title/description against the topic.
    4. Also include federal-level requirements from the same categories.
    """
    matched_categories = _match_topic_to_categories(topic)

    async with get_connection() as conn:
        # Resolve jurisdiction_ids for the given jurisdiction name.
        # We match state abbreviation OR full jurisdiction_name in the
        # jurisdiction_requirements table directly (it stores jurisdiction_name).
        # Also look up via the jurisdictions table for state-level matches.
        jurisdiction_ids: List = []
        state_abbr = jurisdiction.strip().upper() if len(jurisdiction.strip()) == 2 else None

        # Try matching via the jurisdictions table
        if state_abbr:
            jur_rows = await conn.fetch(
                "SELECT id FROM jurisdictions WHERE state = $1",
                state_abbr,
            )
        else:
            # Full state name: look up jurisdiction_requirements by jurisdiction_name
            # to find the matching jurisdiction_ids, since jurisdictions.state stores
            # 2-char abbreviations only.
            jur_name_pattern = f"%{jurisdiction.strip()}%"
            jur_rows = await conn.fetch(
                """SELECT DISTINCT jurisdiction_id AS id
                   FROM jurisdiction_requirements
                   WHERE jurisdiction_name ILIKE $1
                   LIMIT 50""",
                jur_name_pattern,
            )

        jurisdiction_ids = [r["id"] for r in jur_rows]

        # If a location_id was given, also include that location's jurisdiction
        if location_id:
            loc_jur = await conn.fetch(
                """SELECT j.id FROM jurisdictions j
                   JOIN business_locations bl ON (
                       (bl.state = j.state AND (j.city IS NULL OR j.city = ''))
                       OR (bl.state = j.state AND LOWER(bl.city) = LOWER(j.city))
                   )
                   WHERE bl.id = $1""",
                UUID(location_id),
            )
            for r in loc_jur:
                if r["id"] not in jurisdiction_ids:
                    jurisdiction_ids.append(r["id"])

        if not jurisdiction_ids:
            # Fall back: search jurisdiction_requirements by jurisdiction_name directly
            pattern = f"%{jurisdiction.strip()}%"
            if matched_categories:
                rows = await conn.fetch(
                    """SELECT * FROM jurisdiction_requirements
                       WHERE jurisdiction_name ILIKE $1
                         AND category = ANY($2::text[])
                       ORDER BY category, jurisdiction_level
                       LIMIT 100""",
                    pattern,
                    matched_categories,
                )
            else:
                topic_pattern = f"%{topic.strip()}%"
                rows = await conn.fetch(
                    """SELECT * FROM jurisdiction_requirements
                       WHERE jurisdiction_name ILIKE $1
                         AND (title ILIKE $2 OR description ILIKE $2 OR category ILIKE $2)
                       ORDER BY category, jurisdiction_level
                       LIMIT 100""",
                    pattern,
                    topic_pattern,
                )
            return [dict(r) for r in rows]

        # Fetch by jurisdiction_ids + category or text search
        if matched_categories:
            rows = await conn.fetch(
                """SELECT * FROM jurisdiction_requirements
                   WHERE jurisdiction_id = ANY($1::uuid[])
                     AND category = ANY($2::text[])
                   ORDER BY category, jurisdiction_level
                   LIMIT 200""",
                jurisdiction_ids,
                matched_categories,
            )
            # Also fetch federal-level requirements for the same categories
            federal_rows = await conn.fetch(
                """SELECT * FROM jurisdiction_requirements
                   WHERE jurisdiction_level = 'federal'
                     AND category = ANY($1::text[])
                   LIMIT 50""",
                matched_categories,
            )
        else:
            topic_pattern = f"%{topic.strip()}%"
            rows = await conn.fetch(
                """SELECT * FROM jurisdiction_requirements
                   WHERE jurisdiction_id = ANY($1::uuid[])
                     AND (title ILIKE $2 OR description ILIKE $2 OR category ILIKE $2)
                   ORDER BY
                     CASE WHEN title ILIKE $2 THEN 0
                          WHEN category ILIKE $2 THEN 1
                          ELSE 2
                     END,
                     category, jurisdiction_level
                   LIMIT 200""",
                jurisdiction_ids,
                topic_pattern,
            )
            federal_rows = await conn.fetch(
                """SELECT * FROM jurisdiction_requirements
                   WHERE jurisdiction_level = 'federal'
                     AND (title ILIKE $1 OR description ILIKE $1 OR category ILIKE $1)
                   LIMIT 50""",
                topic_pattern,
            )

        # Merge and deduplicate by requirement id
        seen_ids = set()
        results = []
        for r in list(rows) + list(federal_rows):
            rid = r["id"]
            if rid not in seen_ids:
                seen_ids.add(rid)
                results.append(dict(r))
        return results


def _build_requirement_context_block(requirements: List[dict]) -> str:
    """Format a list of requirement dicts into a prompt context block."""
    if not requirements:
        return ""
    block = (
        "\n\n## Regulatory Requirements from Database\n"
        "The following requirements are from our verified compliance database. "
        "Use these as authoritative source material and cite them in the policy:\n\n"
    )
    for req in requirements:
        block += f"- **{req.get('jurisdiction_name', 'Unknown')}** ({req.get('jurisdiction_level', '')}) -- {req.get('category', '')}: "
        block += f"{req.get('title', '')}"
        if req.get("current_value"):
            block += f" -- Current value: {req['current_value']}"
        if req.get("description"):
            block += f"\n  Detail: {req['description']}"
        if req.get("source_url"):
            block += f"\n  Source: {req['source_url']}"
        eff = req.get("effective_date")
        if eff:
            block += f"\n  Effective: {eff.isoformat() if hasattr(eff, 'isoformat') else eff}"
        block += "\n"
    return block


async def draft_policy_from_topic(
    topic: str,
    jurisdiction: str,
    requirements: List[dict],
    industry: Optional[str] = None,
) -> dict:
    """Generate a policy draft for a freeform topic and jurisdiction.

    Args:
        topic: The policy topic (e.g., "Bloodborne Pathogen Exposure Control").
        jurisdiction: Target jurisdiction (e.g., "California", "CA").
        requirements: Pre-fetched requirement dicts from the database.
        industry: Optional industry context string.

    Returns:
        dict with keys: title, content, citations, applicable_jurisdictions, category.
    """
    # Determine industry context
    canonical_industry = _resolve_industry(industry) if industry else ""
    industry_prompt_context = _INDUSTRY_POLICY_CONTEXT.get(canonical_industry, "")

    # Build the requirements context block
    requirements_context = _build_requirement_context_block(requirements)

    # Build citations reference for the prompt — only requirements with source_url
    citable_requirements = [
        r for r in requirements if r.get("source_url")
    ]

    # Collect unique jurisdictions from requirements
    applicable_jurisdictions = sorted(set(
        r.get("jurisdiction_name", "") for r in requirements if r.get("jurisdiction_name")
    ))
    if jurisdiction not in applicable_jurisdictions:
        applicable_jurisdictions.insert(0, jurisdiction)

    # Infer category from the matched requirements
    category_counts: Dict[str, int] = {}
    for r in requirements:
        cat = r.get("category", "")
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1
    primary_category = max(category_counts, key=category_counts.get) if category_counts else "general"

    industry_block = ""
    if industry:
        industry_block = f"\n\n## Industry Context\nThis policy is for a **{industry}** organization.\n"
    industry_block += industry_prompt_context

    citations_instruction = ""
    if citable_requirements:
        citations_instruction = (
            "\n\nWhen you cite a requirement, use this exact format in the text: "
            "[Citation: requirement_key] where requirement_key matches one of the keys below.\n"
            "Available citation keys:\n"
        )
        for r in citable_requirements:
            citations_instruction += f"  - key=\"{r.get('requirement_key', r.get('title', ''))}\" title=\"{r.get('title', '')}\" source=\"{r.get('source_url', '')}\"\n"

    prompt = f"""You are an employment law attorney and HR policy writer. Draft a complete, professional policy document for the following topic.

## Topic
{topic}

## Jurisdiction
{jurisdiction}
{requirements_context}{industry_block}{citations_instruction}

## Required Sections
Write the policy in Markdown format with ALL of the following sections:

1. **Purpose** — Why this policy exists
2. **Scope** — Who and what it applies to
3. **Definitions** — Key terms used in the policy
4. **Policy Statement** — The core policy rules and commitments
5. **Procedures** — Step-by-step implementation procedures
6. **Responsibilities** — Who is responsible for what (management, employees, HR, etc.)
7. **Citations & Legal References** — List every regulatory requirement referenced, with source URLs
8. **Review Schedule** — When and how the policy should be reviewed/updated

## Instructions
- Write a complete, production-ready policy document.
- Include jurisdiction-specific details: reference the specific state name, statute numbers, and regulatory codes.
- When referencing requirements from the database above, cite the source URL in parentheses.
- Use [COMPANY NAME] as a placeholder for the organization name.
- Use [BRACKETS] for any company-specific values that need to be filled in.
- Keep the tone professional but readable.
- Use Google Search to supplement any gaps in the provided regulatory data.

Return ONLY the policy document in Markdown format. Do not include any JSON wrapping or meta-commentary."""

    client = _get_client()
    models_to_try = [DEFAULT_MODEL, FALLBACK_MODEL]
    generated_content = ""

    for model_name in models_to_try:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                ),
            )
            generated_content = response.text or ""
            break
        except Exception as exc:
            error_msg = str(exc).lower()
            is_model_error = any(
                s in error_msg
                for s in ("not found", "unknown model", "invalid model", "unsupported")
            )
            if is_model_error and model_name != models_to_try[-1]:
                logger.warning("Model %s unavailable, falling back: %s", model_name, exc)
                continue
            logger.error("Topic-based policy draft failed: %s", exc)
            raise

    if not generated_content:
        raise RuntimeError("All AI models failed to generate policy content")

    # Extract a title from the generated content (first H1 or H2 heading)
    title = topic
    for line in generated_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            title = stripped.lstrip("# ").strip()
            break

    # Build citations from the requirements that have source URLs
    citations = []
    for r in citable_requirements:
        citations.append({
            "requirement_key": r.get("requirement_key", ""),
            "title": r.get("title", ""),
            "source_url": r.get("source_url", ""),
        })

    return {
        "title": title,
        "content": generated_content,
        "citations": citations,
        "applicable_jurisdictions": applicable_jurisdictions,
        "category": primary_category,
    }
