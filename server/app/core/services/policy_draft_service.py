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


@dataclass
class PolicyDraftRequest:
    policy_type: str
    location_ids: Optional[List[str]] = None
    additional_context: Optional[str] = None

logger = logging.getLogger(__name__)

POLICY_TYPES = [
    {"value": "pto_sick_leave", "label": "PTO and Sick Leave", "categories": ["sick_leave"]},
    {"value": "meal_rest_breaks", "label": "Meal and Rest Break", "categories": ["meal_breaks"]},
    {"value": "overtime", "label": "Overtime and Hours Worked", "categories": ["overtime"]},
    {"value": "pay_practices", "label": "Pay Practices and Payday", "categories": ["pay_frequency", "final_pay", "minimum_wage"]},
    {"value": "scheduling", "label": "Scheduling and Reporting Time", "categories": ["scheduling_reporting"]},
    {"value": "youth_employment", "label": "Youth Employment / Minor Work", "categories": ["minor_work_permit"]},
    {"value": "anti_harassment", "label": "Anti-Harassment and Anti-Discrimination", "categories": ["anti_discrimination"]},
    {"value": "workplace_safety", "label": "Workplace Health and Safety", "categories": ["workplace_safety"]},
    {"value": "remote_work", "label": "Remote Work / Telecommuting", "categories": []},
    {"value": "drug_alcohol", "label": "Drug and Alcohol", "categories": []},
    {"value": "attendance", "label": "Attendance and Punctuality", "categories": []},
    {"value": "code_of_conduct", "label": "Code of Conduct", "categories": []},
    {"value": "whistleblower", "label": "Whistleblower Protection", "categories": []},
    # Healthcare-specific policy types
    {"value": "hipaa_privacy", "label": "HIPAA Privacy and Security", "categories": ["hipaa_privacy"], "industries": ["healthcare"]},
    {"value": "bloodborne_pathogens", "label": "Bloodborne Pathogens Exposure Control", "categories": ["clinical_safety"], "industries": ["healthcare"]},
    {"value": "credentialing", "label": "Credentialing and Licensure Verification", "categories": ["healthcare_workforce"], "industries": ["healthcare"]},
    {"value": "patient_safety", "label": "Patient Safety and Incident Reporting", "categories": ["clinical_safety"], "industries": ["healthcare"]},
    {"value": "infection_control", "label": "Infection Control and PPE", "categories": ["clinical_safety"], "industries": ["healthcare"]},
]

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
}


async def get_policy_types_for_company(company_id: str) -> List[dict]:
    """Return policy types filtered by the company's industry.

    Generic types (no ``industries`` key) are always included. Industry-specific
    types are included only when the company's industry matches.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT industry FROM companies WHERE id = $1", UUID(company_id)
        )
    raw_industry = (row["industry"] or "").strip() if row else ""
    canonical = _resolve_industry(raw_industry)

    result = []
    for pt in POLICY_TYPES:
        industries = pt.get("industries")
        if industries is None:
            result.append(pt)
        elif canonical and canonical in industries:
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

            if related_categories:
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

    prompt = f"""You are an employment law attorney and HR policy writer. Draft a professional **{policy_label}** policy for **{company_name}**.

## Locations Covered
{', '.join(location_summaries)}
{jurisdiction_context}{additional}{industry_prompt_context if policy_config.get("industries") else ""}
## Instructions
1. Write a complete, professional policy document in Markdown format.
2. Include standard sections: Purpose, Scope, Definitions (if needed), Policy Statement, Procedures, and Compliance.
3. Where laws differ by jurisdiction, create jurisdiction-specific sections clearly labeled (e.g., "### California" or "### New York City").
4. When referencing specific legal requirements from the structured data above, cite the source URL in parentheses.
5. Use [COMPANY NAME] as a placeholder where the company name should appear in formal language, and [BRACKETS] for any company-specific details the user needs to fill in (e.g., [NUMBER OF PTO DAYS], [HR CONTACT EMAIL]).
6. If any company context conflicts with legal minimums from the jurisdiction data, flag it clearly with a ⚠️ warning.
7. Keep the tone professional but readable. Avoid overly legalistic jargon where plain language works.
8. Use Google Search to find the latest legal requirements for any jurisdictions or topics not covered by the structured data above."""

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
