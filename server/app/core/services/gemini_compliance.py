import asyncio
import json
import re
import os
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, date

from google import genai
from google.genai import types

from ...config import get_settings
from ..models.compliance import ComplianceCategory, JurisdictionLevel, VerificationResult
from .rate_limiter import get_rate_limiter, RateLimitExceeded
from .search_strategy import build_search_strategy_prompt
from .platform_settings import get_jurisdiction_research_model_mode

# Timeout for individual Gemini API calls (seconds)
GEMINI_CALL_TIMEOUT = 120

DEFAULT_LIGHT_MODEL = "gemini-3-flash-preview"
DEFAULT_HEAVY_MODEL = "gemini-3.1-pro-preview"
DEFAULT_HEAVY_FALLBACK_MODEL = "gemini-2.5-pro"

VALID_CATEGORIES = {
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
    "final_pay",
    "minor_work_permit",
    "scheduling_reporting",
    "leave",
    "workplace_safety",
    "workers_comp",
    "anti_discrimination",
    "hipaa_privacy",
    "billing_integrity",
    "clinical_safety",
    "healthcare_workforce",
    "corporate_integrity",
    "research_consent",
    "state_licensing",
    "emergency_preparedness",
}
# Healthcare categories are researched via a background Celery worker, so they
# should NOT be included in the default sweep when categories=None.
_HEALTHCARE_ONLY_CATEGORIES = {
    "hipaa_privacy", "billing_integrity", "clinical_safety",
    "healthcare_workforce", "corporate_integrity", "research_consent",
    "state_licensing", "emergency_preparedness",
}
DEFAULT_RESEARCH_CATEGORIES = sorted(VALID_CATEGORIES - _HEALTHCARE_ONLY_CATEGORIES)

VALID_JURISDICTION_LEVELS = {"state", "county", "city", "federal"}
VALID_RATE_TYPES = {
    "general",
    "tipped",
    "exempt_salary",
    "hotel",
    "fast_food",
    "healthcare",
    "large_employer",
    "small_employer",
}

_CATEGORY_ALIASES = {
    "meal_rest_breaks": "meal_breaks",
    "meal_and_rest_breaks": "meal_breaks",
    "meal_periods": "meal_breaks",
    "rest_breaks": "meal_breaks",
    "payday_frequency": "pay_frequency",
    "pay_day_frequency": "pay_frequency",
    "final_wage": "final_pay",
    "final_wages": "final_pay",
    "final_paycheck": "final_pay",
    "final_paychecks": "final_pay",
    "minor_work_permits": "minor_work_permit",
    "work_permit": "minor_work_permit",
    "work_permits": "minor_work_permit",
    "youth_employment": "minor_work_permit",
    "youth_work_permit": "minor_work_permit",
    "scheduling_and_reporting_time": "scheduling_reporting",
    "reporting_time": "scheduling_reporting",
    "predictive_scheduling": "scheduling_reporting",
    "fair_workweek": "scheduling_reporting",
    "leave_of_absence": "leave",
    "family_leave": "leave",
    "medical_leave": "leave",
    "pfml": "leave",
    "paid_family_leave": "leave",
    "family_medical_leave": "leave",
    "osha": "workplace_safety",
    "occupational_safety": "workplace_safety",
    "safety": "workplace_safety",
    "workplace_health": "workplace_safety",
    "workers_compensation": "workers_comp",
    "worker_comp": "workers_comp",
    "workman_comp": "workers_comp",
    "workmen_comp": "workers_comp",
    "discrimination": "anti_discrimination",
    "harassment": "anti_discrimination",
    "equal_pay": "anti_discrimination",
    "pay_equity": "anti_discrimination",
    "ada": "anti_discrimination",
    "ada_accommodations": "anti_discrimination",
    # Healthcare categories
    "hipaa": "hipaa_privacy",
    "hipaa_security": "hipaa_privacy",
    "hitech": "hipaa_privacy",
    "phi": "hipaa_privacy",
    "42_cfr_part_2": "hipaa_privacy",
    "part_2": "hipaa_privacy",
    "substance_use_records": "hipaa_privacy",
    "false_claims": "billing_integrity",
    "anti_kickback": "billing_integrity",
    "stark_law": "billing_integrity",
    "medicare_billing": "billing_integrity",
    "mhpaea": "billing_integrity",
    "mental_health_parity": "billing_integrity",
    "joint_commission": "clinical_safety",
    "cms_conditions": "clinical_safety",
    "infection_control": "clinical_safety",
    "bloodborne_pathogens": "clinical_safety",
    "medical_waste": "clinical_safety",
    "epa_medical_waste": "clinical_safety",
    "credentialing": "healthcare_workforce",
    "oig_exclusion": "healthcare_workforce",
    "mandatory_reporter": "healthcare_workforce",
    "oig_compliance": "corporate_integrity",
    "qui_tam": "corporate_integrity",
    "irb": "research_consent",
    "gcp": "research_consent",
    "facility_licensure": "state_licensing",
    "telehealth": "state_licensing",
    "abortion": "state_licensing",
    "dobbs": "state_licensing",
    "ada_accessibility": "state_licensing",
    "emtala": "emergency_preparedness",
    "nfpa": "emergency_preparedness",
    "life_safety_code": "emergency_preparedness",
}

_JURISDICTION_LEVEL_ALIASES = {
    "local": "city",
    "municipal": "city",
    "citywide": "city",
    "countywide": "county",
    "statewide": "state",
    "national": "federal",
}

_RATE_TYPE_ALIASES = {
    "tip_credit": "tipped",
    "tipped_rate": "tipped",
    "cash_wage": "tipped",
    "exempt": "exempt_salary",
    "salary_threshold": "exempt_salary",
    "salary_basis": "exempt_salary",
}

# Errors that should not be retried (API config / quota issues)
_NON_RETRYABLE_KEYWORDS = {"API_KEY", "PERMISSION", "QUOTA", "RATE"}

_MODEL_UNAVAILABLE_SNIPPETS = (
    "not found for api version",
    "model not found",
    "unknown model",
    "invalid model",
    "does not support tool",
    "does not support tools",
    "unsupported model",
)

_MODEL_ACCESS_SNIPPETS = (
    "permission denied",
    "forbidden",
    "not authorized",
    "unauthorized",
    "access denied",
)

# Structured correction hints for retry prompts
CORRECTION_HINTS = {
    "json_parse": "Return ONLY valid JSON. No markdown fences, no explanation text, no trailing commas.",
    "missing_key": "Your response was missing the required '{key}' field. Include it in your JSON.",
    "empty_list": "The '{key}' list was empty. Provide at least one item.",
    "invalid_category": "You used category '{got}' which is invalid. Use only: {valid}.",
    "invalid_jurisdiction_level": "You used jurisdiction_level '{got}' which is invalid. Use only: {valid}.",
    "missing_field": "Requirement missing required field '{field}'. All requirements need: category, jurisdiction_level, jurisdiction_name, title.",
    "timeout": "Response took too long. Be more concise - return only essential data.",
    "validation": "Validation failed: {detail}. Fix this specific issue.",
}


def _normalize_token(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    token = str(value).strip().lower()
    token = token.replace("&", " and ")
    token = re.sub(r"[\s\-/]+", "_", token)
    token = re.sub(r"[^a-z0-9_]", "", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token or None


def _normalize_category_value(value: Optional[str]) -> Optional[str]:
    token = _normalize_token(value)
    if not token:
        return None
    if token in VALID_CATEGORIES:
        return token
    return _CATEGORY_ALIASES.get(token)


def _normalize_jurisdiction_level_value(value: Optional[str]) -> Optional[str]:
    token = _normalize_token(value)
    if not token:
        return None
    if token in VALID_JURISDICTION_LEVELS:
        return token
    return _JURISDICTION_LEVEL_ALIASES.get(token)


def _normalize_rate_type_value(value: Optional[str]) -> Optional[str]:
    token = _normalize_token(value)
    if not token:
        return None
    if token in VALID_RATE_TYPES:
        return token
    return _RATE_TYPE_ALIASES.get(token)


def _coerce_requirement_shape(req: dict, requested_category: Optional[str]) -> dict:
    """Normalize requirement fields so minor model drift doesn't drop valid rows."""
    normalized = dict(req)
    expected_category = _normalize_category_value(requested_category)

    if expected_category:
        normalized["category"] = expected_category
    else:
        category = _normalize_category_value(normalized.get("category"))
        if category:
            normalized["category"] = category

    jurisdiction_level = _normalize_jurisdiction_level_value(normalized.get("jurisdiction_level"))
    if jurisdiction_level:
        normalized["jurisdiction_level"] = jurisdiction_level
    else:
        jurisdiction_name = str(normalized.get("jurisdiction_name") or "").lower()
        if "federal" in jurisdiction_name or "u.s." in jurisdiction_name or "united states" in jurisdiction_name:
            normalized["jurisdiction_level"] = "federal"
        elif "county" in jurisdiction_name:
            normalized["jurisdiction_level"] = "county"
        elif "city" in jurisdiction_name:
            normalized["jurisdiction_level"] = "city"
        elif jurisdiction_name:
            normalized["jurisdiction_level"] = "state"

    if normalized.get("category") == "minimum_wage":
        normalized["rate_type"] = _normalize_rate_type_value(normalized.get("rate_type")) or "general"
    else:
        normalized["rate_type"] = None

    if normalized.get("category") == "leave":
        meta = {}
        for src_key, dest_key in [
            ("paid", "paid"), ("max_weeks", "max_weeks"),
            ("wage_replacement_pct", "wage_pct"), ("job_protection", "job_prot"),
            ("employer_size_threshold", "emp_min"), ("employee_tenure_months", "tenure_mo"),
            ("employee_hours_threshold", "hrs_min"),
        ]:
            val = normalized.pop(src_key, None)
            if val is not None:
                meta[dest_key] = val
        if meta:
            if not normalized.get("current_value"):
                # Build a short summary for current_value (VARCHAR 100)
                parts = []
                if meta.get("max_weeks"):
                    parts.append(f"{meta['max_weeks']} weeks")
                if meta.get("wage_pct"):
                    parts.append(f"{meta['wage_pct']}% pay")
                if meta.get("job_prot"):
                    parts.append("job protected")
                if meta.get("paid"):
                    parts.append("paid")
                normalized["current_value"] = ", ".join(parts)[:100] if parts else None
            # Preserve original description — do NOT overwrite with JSON meta
        if meta.get("max_weeks"):
            normalized["numeric_value"] = meta["max_weeks"]

    # Auto-tag healthcare categories with applicable_industries
    _HEALTHCARE_CATEGORIES = {
        "hipaa_privacy", "billing_integrity", "clinical_safety",
        "healthcare_workforce", "corporate_integrity", "research_consent",
        "state_licensing", "emergency_preparedness",
    }
    if normalized.get("category") in _HEALTHCARE_CATEGORIES:
        if not normalized.get("applicable_industries"):
            normalized["applicable_industries"] = ["healthcare"]

    # Clamp numeric_value to fit DECIMAL(10,4) — max absolute value 999999.9999
    nv = normalized.get("numeric_value")
    if nv is not None:
        try:
            nv = float(nv)
            if abs(nv) >= 1_000_000:
                normalized["numeric_value"] = None
        except (TypeError, ValueError):
            normalized["numeric_value"] = None

    rwp = normalized.get("requires_written_policy")
    if isinstance(rwp, str):
        rwp = rwp.strip().lower() not in ("false", "0", "no", "")
    normalized["requires_written_policy"] = bool(rwp) if rwp is not None else None

    return normalized


def _build_correction_feedback(error_type: str, **kwargs) -> str:
    """Build structured correction feedback for retry prompts."""
    template = CORRECTION_HINTS.get(error_type, "Previous attempt failed: {detail}")
    try:
        message = template.format(**kwargs)
    except KeyError:
        # Fallback if kwargs don't match template
        message = template
    return "\n\nPREVIOUS ATTEMPT FAILED: " + message


def _is_model_unavailable_error(error_message: str) -> bool:
    text = (error_message or "").lower()
    if "models/" in text and "not found" in text:
        return True
    return any(snippet in text for snippet in _MODEL_UNAVAILABLE_SNIPPETS)


def _is_model_access_error(error_message: str) -> bool:
    text = (error_message or "").lower()
    if "model" not in text and "models/" not in text:
        return False
    return any(snippet in text for snippet in _MODEL_ACCESS_SNIPPETS)


class GeminiExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_raw: Optional[str] = None):
        super().__init__(message)
        self.last_raw = last_raw


def _clean_json_text(text: str) -> str:
    """Clean JSON text by removing markdown fences and fixing Python booleans."""
    text = text.strip()

    # Strip markdown fences (handles unclosed blocks)
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    # Find the first '{' and last '}' to extract JSON from surrounding text
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        text = text[start : end + 1]

    # Fix common LLM JSON errors (Python booleans/None)
    text = re.sub(r":\s*True\b", ": true", text)
    text = re.sub(r":\s*False\b", ": false", text)
    text = re.sub(r":\s*None\b", ": null", text)

    return text


def _validate_requirement(req: dict) -> Optional[str]:
    """Validate a single requirement dict. Returns error string or None if valid."""
    cat = req.get("category")
    if cat not in VALID_CATEGORIES:
        return f"invalid category '{cat}'"

    level = req.get("jurisdiction_level")
    if level not in VALID_JURISDICTION_LEVELS:
        return f"invalid jurisdiction_level '{level}'"

    if not req.get("title"):
        return "missing title"

    if not req.get("jurisdiction_name"):
        return "missing jurisdiction_name"

    # Validate rate_type for minimum_wage category
    if cat == "minimum_wage":
        rate_type = req.get("rate_type")
        if rate_type is not None and rate_type not in VALID_RATE_TYPES:
            return f"invalid rate_type '{rate_type}' for minimum_wage"

    return None


def _validate_verification(data: dict) -> Optional[str]:
    """Validate verification response dict. Returns error string or None if valid."""
    if "confirmed" not in data:
        return "missing 'confirmed' field"

    confidence = data.get("confidence")
    if confidence is None:
        return "missing 'confidence' field"
    try:
        c = float(confidence)
        if not (0.0 <= c <= 1.0):
            return f"confidence {c} not in [0.0, 1.0]"
    except (TypeError, ValueError):
        return f"confidence '{confidence}' is not numeric"

    return None


def _build_category_prompt(
    location_str: str,
    category: str,
    context_section: str = "",
    preemption_context: str = "",
    industry_context: str = "",
) -> str:
    """Build a focused prompt for a single compliance category."""

    category_instructions = {
        "minimum_wage": """Research MINIMUM WAGE requirements.
Always include the STATE baseline minimum wage.
If a county/city minimum wage ordinance exists (and is allowed), also include the local override.
Return SEPARATE requirements for each rate type that exists at each applicable level:
- "general" - standard minimum wage (ALWAYS include for state baseline)
- "tipped" - if tip credits allowed
- "exempt_salary" - minimum exempt salary threshold for overtime exemption (ALWAYS include; if only federal applies, explicitly say so)
- "hotel", "fast_food", "healthcare" - if special rates exist
- "large_employer" / "small_employer" - if rates differ by size
For tipped requirements, explicitly describe whether tip crediting is allowed and how it works (cash wage + tip credit structure).
Provide numeric_value for rates/salary thresholds when possible.""",

        "overtime": """Research OVERTIME requirements.
Always include the STATE baseline overtime rules.
If a county/city overtime ordinance exists (and is allowed), also include the local override.
Include daily/weekly overtime thresholds and multipliers.""",

        "sick_leave": """Research PAID SICK LEAVE requirements.
Always include the STATE baseline sick leave rules.
If a county/city sick leave ordinance exists (and is allowed), also include the local override.
Include accrual rate, cap, and usage rules.""",

        "meal_breaks": """Research MEAL AND REST BREAK requirements.
Always include the STATE baseline meal/rest break rules.
If a county/city ordinance exists (and is allowed), also include the local override.
Include timing, duration, and waiver conditions.""",

        "pay_frequency": """Research PAY FREQUENCY requirements.
Always include the STATE baseline pay frequency rules.
If a county/city ordinance exists (and is allowed), also include the local override.
Include required pay periods and final pay rules.""",

        "final_pay": """Research FINAL PAY requirements.
Always include the STATE baseline final paycheck rules.
If local (county/city) final-pay rules exist and are allowed, include local overrides.
Cover BOTH voluntary resignations and involuntary terminations, including timing and payout method requirements.
Explicitly state whether accrued vacation/PTO must be paid out, and whether accrued sick leave must be paid out at separation.""",

        "minor_work_permit": """Research MINOR WORK PERMIT / YOUTH EMPLOYMENT requirements.
Always include the STATE baseline minor-work authorization rules.
If local (county/city) rules exist and are allowed, include local overrides.
Include whether work permits are required, age thresholds, hour limits (school-day/non-school-day), prohibited occupations, and who issues permits.""",

        "scheduling_reporting": """Research SCHEDULING AND REPORTING TIME requirements.
Always include the STATE baseline rules.
If local fair-workweek/predictive-scheduling ordinances exist (and are allowed), include local overrides.
Include advance-schedule notice windows, penalties for schedule changes, reporting/show-up pay rules, on-call restrictions, and spread-of-hours pay if applicable.
If no specific scheduling/reporting-time law applies, explicitly say so.""",

        "leave": """Research LEAVE OF ABSENCE programs and entitlements.
Return EACH qualifying leave program as a SEPARATE requirement.
Common programs: state paid family/medical leave (PFML), state disability insurance (SDI/TDI),
state family leave acts, pregnancy disability leave.
Do NOT include federal FMLA (handled separately).

For EACH program, include these additional JSON fields:
- "paid": true or false
- "max_weeks": integer (maximum weeks of leave)
- "wage_replacement_pct": number or null (e.g., 60 for 60%)
- "job_protection": true or false
- "employer_size_threshold": integer or null (minimum employees)
- "employee_tenure_months": integer or null (minimum months employed)
- "employee_hours_threshold": integer or null (minimum hours worked)

Set numeric_value to max_weeks. Set current_value to a SHORT summary (under 80 chars) like "8 weeks, 60% pay, job protected".
Set description to a longer explanation of the program if needed.""",

        "workplace_safety": """Research WORKPLACE SAFETY requirements (OSHA and state equivalents).
Always include federal OSHA applicability (employers with 1+ employees).
If the state operates its own OSHA-approved State Plan, include state-specific requirements.
Cover: injury/illness recording (OSHA 300 log), reporting requirements (fatalities, hospitalizations),
mandatory safety training, hazard communication (GHS/SDS), required workplace posters,
bloodborne pathogen standards if applicable, and any industry-specific safety rules.
Include employee count thresholds where they apply (e.g., OSHA 300 log exemptions for <10 employees).
Set current_value to a SHORT summary (under 80 chars).""",

        "workers_comp": """Research WORKERS' COMPENSATION INSURANCE requirements.
Always include the STATE baseline workers' comp requirements.
Cover: whether coverage is mandatory or elective, employee count thresholds for mandatory coverage,
exempt categories (e.g., sole proprietors, independent contractors, domestic workers, agricultural),
state fund vs. private insurance options, penalty for non-compliance,
and any special industry requirements (e.g., construction must cover all workers).
Include the state agency that administers the program.
Set current_value to a SHORT summary (under 80 chars).""",

        "anti_discrimination": """Research ANTI-DISCRIMINATION AND EQUAL EMPLOYMENT requirements.
Always include the STATE baseline anti-discrimination laws.
If local (county/city) human rights ordinances add protections, include local overrides.
Cover: protected classes beyond federal Title VII (e.g., sexual orientation, gender identity, marital status),
employer size thresholds for state law applicability, harassment prevention training requirements,
pay equity/transparency laws, reasonable accommodation requirements (disability, pregnancy, religion),
mandatory anti-harassment policy requirements, and complaint filing agencies/deadlines.
Do NOT duplicate federal Title VII or ADA — focus on state and local additions.
Set current_value to a SHORT summary (under 80 chars).""",

        "hipaa_privacy": """Research HIPAA PRIVACY AND SECURITY requirements as they apply in this jurisdiction.
Cover: HIPAA Privacy Rule (45 CFR Part 164 Subpart E), HIPAA Security Rule (45 CFR Part 164 Subpart C),
HITECH Act breach notification requirements (timing, state AG notification),
42 CFR Part 2 requirements for substance use disorder records where applicable,
and any STATE health privacy laws that EXCEED federal HIPAA protections
(e.g., CA CMIA, TX HB 300, NY SHIELD Act health data provisions).
Include stricter consent, redisclosure, segregation, and patient-access rules for Part 2 records
when they go beyond standard HIPAA handling.
Include state-specific breach notification timelines if shorter than HIPAA's 60-day window.
Include penalties for non-compliance at both federal and state levels.
Set current_value to a SHORT summary (under 80 chars).""",

        "billing_integrity": """Research BILLING AND FINANCIAL INTEGRITY requirements for healthcare entities in this jurisdiction.
Cover: Federal False Claims Act (31 U.S.C. §§ 3729–3733), Anti-Kickback Statute (42 U.S.C. § 1320a-7b),
Physician Self-Referral Law (Stark Law, 42 U.S.C. § 1395nn), Medicare/Medicaid billing requirements,
Mental Health Parity and Addiction Equity Act (MHPAEA) obligations as enforced through payer coverage,
utilization management, medical necessity, and reimbursement rules,
and any STATE false claims acts, anti-kickback laws, parity laws, or fee-splitting prohibitions.
Include state-specific billing fraud statutes and qui tam provisions.
Set current_value to a SHORT summary (under 80 chars).""",

        "clinical_safety": """Research CLINICAL AND PATIENT SAFETY requirements for healthcare facilities in this jurisdiction.
Cover: CMS Conditions of Participation (42 CFR Parts 482-485), Joint Commission accreditation standards,
medication management and DEA controlled substance requirements,
OSHA Bloodborne Pathogens Standard (29 CFR 1910.1030), infection control and prevention requirements,
EPA and STATE medical waste disposal / regulated medical waste handling requirements,
and any STATE patient safety reporting requirements (e.g., adverse event reporting, sentinel events).
Include state health department inspection and survey requirements.
Set current_value to a SHORT summary (under 80 chars).""",

        "healthcare_workforce": """Research HEALTHCARE WORKFORCE compliance requirements in this jurisdiction.
Cover: provider credentialing and privileging requirements, OIG List of Excluded Individuals/Entities (LEIE) screening obligations,
mandatory reporter obligations (child abuse, elder abuse, domestic violence),
healthcare-specific labor rules (nurse staffing ratios, mandatory overtime bans for healthcare workers),
and state-specific scope-of-practice rules for nurses, PAs, and allied health.
Include frequency requirements for OIG exclusion screening and credentialing verification.
Set current_value to a SHORT summary (under 80 chars).""",

        "corporate_integrity": """Research CORPORATE INTEGRITY AND ETHICS requirements for healthcare organizations in this jurisdiction.
Cover: OIG Compliance Program Guidance for hospitals/healthcare entities,
corporate integrity agreement (CIA) common requirements, code of conduct mandates,
conflict of interest disclosure requirements, whistleblower protections and qui tam provisions
(federal False Claims Act qui tam + state equivalents),
and any STATE healthcare compliance program requirements.
Include state-specific whistleblower protections for healthcare workers.
Set current_value to a SHORT summary (under 80 chars).""",

        "research_consent": """Research RESEARCH AND INFORMED CONSENT requirements in this jurisdiction.
Cover: IRB oversight requirements (45 CFR Part 46 — Common Rule), Good Clinical Practice (ICH-GCP) standards,
FDA investigational regulations (21 CFR Parts 50, 56, 312, 812),
21 CFR Part 11 (electronic records/signatures), and any STATE-specific informed consent requirements,
research subject protections, or bioethics laws that exceed federal standards.
Include state requirements for genetic testing consent and biospecimen research.
Set current_value to a SHORT summary (under 80 chars).""",

        "state_licensing": """Research STATE LICENSING AND SCOPE OF PRACTICE requirements for healthcare in this jurisdiction.
Cover: facility licensure requirements (hospitals, clinics, ASCs, nursing facilities),
provider licensing and renewal requirements (physicians, nurses, allied health),
telehealth and cross-state practice regulations (interstate compacts like IMLC, NLC),
post-Dobbs abortion-service restrictions or protections that affect providers or facilities,
ADA physical accessibility and plant/facility standards enforced through health facility rules,
and any recent changes to scope-of-practice laws (e.g., NP independent practice authority).
Include state health department facility licensing categories and renewal timelines.
Set current_value to a SHORT summary (under 80 chars).""",

        "emergency_preparedness": """Research EMERGENCY PREPAREDNESS requirements for healthcare facilities in this jurisdiction.
Cover: EMTALA (Emergency Medical Treatment and Labor Act, 42 U.S.C. § 1395dd) — screening, stabilization, and transfer requirements;
CMS Emergency Preparedness Rule (42 CFR § 482.15) — emergency plan, communication plan, policies/procedures, training/testing;
NFPA fire and life safety code requirements adopted through CMS, accrediting bodies, or STATE health/facility regulators;
and any STATE-specific emergency preparedness requirements for healthcare facilities.
Include penalties for EMTALA violations and state emergency management mandates.
Set current_value to a SHORT summary (under 80 chars).""",
    }

    return f"""You are a compliance research expert. Research current {category.replace('_', ' ')} laws for a business operating in {location_str}.
{context_section}
{preemption_context}
{industry_context}
{category_instructions.get(category, "")}
If there is no distinct rule beyond federal/state baseline, still return one state-level requirement that explicitly says no additional jurisdiction-specific rule applies.
Do NOT return an empty requirements list.

For each requirement, determine whether the statute explicitly requires the employer to include this policy in a written employee handbook or written notice. Set "requires_written_policy" to true only if written disclosure is legally mandated. If the obligation is satisfied by a workplace poster, verbal notice, or operational compliance alone, set it to false.

Today's date is {date.today().isoformat()}. Return ONLY rates/values currently in effect.

Respond with JSON:
{{
  "requirements": [
    {{
      "category": "{category}",
      "rate_type": <for minimum_wage only: "general" | "tipped" | "exempt_salary" | "hotel" | "fast_food" | "healthcare" | "large_employer" | "small_employer"; else null>,
      "jurisdiction_level": "state" | "county" | "city",
      "jurisdiction_name": "Name",
      "title": "Short title",
      "description": "Detailed explanation",
      "current_value": "$X.XX/hr" or description,
      "numeric_value": <float or null>,
      "effective_date": "YYYY-MM-DD" or null,
      "source_url": "https://...",
      "source_name": "Source Name",
      "requires_written_policy": true | false,
      "paid": <for leave only: true|false; else omit>,
      "max_weeks": <for leave only: integer; else omit>,
      "wage_replacement_pct": <for leave only: number or null; else omit>,
      "job_protection": <for leave only: true|false; else omit>,
      "employer_size_threshold": <for leave only: integer or null; else omit>,
      "employee_tenure_months": <for leave only: integer or null; else omit>,
      "employee_hours_threshold": <for leave only: integer or null; else omit>
    }}
  ]
}}
"""


class GeminiComplianceService:
    """
    Service for researching compliance requirements using Gemini with Google Search.
    """

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            # Check for specific API key for this service first
            api_key = os.getenv("GEMINI_API_KEY")

            if api_key:
                self._client = genai.Client(api_key=api_key)
            elif self.settings.use_vertex:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.settings.vertex_project,
                    location=self.settings.vertex_location,
                )
            else:
                self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _has_api_key(self) -> bool:
        api_key = os.getenv("GEMINI_API_KEY") or self.settings.gemini_api_key
        return bool(api_key) or self.settings.use_vertex

    async def _resolve_model_candidates(self) -> List[str]:
        mode = await get_jurisdiction_research_model_mode()
        light_model = (self.settings.analysis_model or DEFAULT_LIGHT_MODEL).strip() or DEFAULT_LIGHT_MODEL

        if mode != "heavy":
            return [light_model]

        configured_heavy = (
            os.getenv("GEMINI_JURISDICTION_HEAVY_MODEL")
            or os.getenv("GEMINI_HEAVY_MODEL")
            or DEFAULT_HEAVY_MODEL
        )

        candidates: List[str] = []
        for candidate in [configured_heavy, DEFAULT_HEAVY_FALLBACK_MODEL, light_model]:
            model = str(candidate or "").strip()
            if model and model not in candidates:
                candidates.append(model)
        return candidates

    async def _generate_content_with_model_fallback(
        self,
        *,
        contents: Any,
        config: types.GenerateContentConfig,
        timeout_seconds: int = GEMINI_CALL_TIMEOUT,
    ) -> tuple[Any, str]:
        model_candidates = await self._resolve_model_candidates()
        if not model_candidates:
            raise RuntimeError("No Gemini model candidates are configured")

        last_exc: Optional[Exception] = None
        for idx, model in enumerate(model_candidates):
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )
                if idx > 0:
                    print(f"[Gemini Compliance] Fallback model engaged: {model}")
                return response, model
            except Exception as exc:
                message = str(exc)
                if (
                    (_is_model_unavailable_error(message) or _is_model_access_error(message))
                    and idx < len(model_candidates) - 1
                ):
                    next_model = model_candidates[idx + 1]
                    print(
                        f"[Gemini Compliance] Model '{model}' unavailable for this call; "
                        f"trying fallback '{next_model}'"
                    )
                    last_exc = exc
                    continue
                raise

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Gemini content generation failed before model invocation")

    async def _call_with_retry(
        self,
        prompt: str,
        response_key: Optional[str],
        *,
        max_retries: int = 1,
        validate_fn: Optional[Callable[[Any], Optional[str]]] = None,
        label: str = "Gemini call",
        on_retry: Optional[Callable[[int, str], Any]] = None,
    ) -> Any:
        """Call Gemini with retry-on-failure loop.

        On each retry, appends feedback about what went wrong to the prompt.
        Non-retryable errors (API key, permission, quota, rate) raise immediately.
        When ``response_key`` is a string, returns ``data[response_key]``.
        When ``response_key`` is ``None``, returns the full parsed dict.
        Raises ``GeminiExhaustedError`` when all attempts fail.
        """
        tools = [types.Tool(google_search=types.GoogleSearch())]
        last_raw: Optional[str] = None
        last_error: Optional[str] = None
        current_prompt = prompt
        rate_limiter = get_rate_limiter()

        # Check rate limit before starting (fail fast if already at limit)
        try:
            await rate_limiter.check_limit("gemini_compliance", label)
        except RateLimitExceeded as e:
            raise GeminiExhaustedError(f"{label}: Rate limit exceeded - {e}", last_raw=None)

        for attempt in range(1 + max_retries):
            try:
                # Check limit again before each retry attempt
                if attempt > 0:
                    await rate_limiter.check_limit("gemini_compliance", label)
                    print(f"[Gemini Compliance] {label}: Attempt {attempt + 1} (retrying: {last_error})")
                    if on_retry is not None:
                        on_retry(attempt, last_error)

                response, _model_used = await self._generate_content_with_model_fallback(
                    contents=current_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=tools,
                        response_modalities=["TEXT"],
                    ),
                    timeout_seconds=GEMINI_CALL_TIMEOUT,
                )

                # Record the actual API call
                await rate_limiter.record_call("gemini_compliance", label)

                raw_text = response.text
                last_raw = raw_text

                # Parse JSON
                cleaned = _clean_json_text(raw_text)
                data = json.loads(cleaned)

                if response_key is not None:
                    result = data.get(response_key)
                    if result is None:
                        last_error = f"missing '{response_key}' key in response"
                        current_prompt = prompt + _build_correction_feedback("missing_key", key=response_key)
                        continue
                else:
                    result = data

                # Run per-item validation if provided
                if validate_fn is not None:
                    validation_error = validate_fn(data)
                    if validation_error:
                        last_error = validation_error
                        current_prompt = prompt + _build_correction_feedback("validation", detail=last_error)
                        continue

                return result

            except json.JSONDecodeError as e:
                last_error = f"response was not valid JSON: {e}"
                current_prompt = prompt + _build_correction_feedback("json_parse")

            except (asyncio.TimeoutError, TimeoutError):
                last_error = f"timed out after {GEMINI_CALL_TIMEOUT}s"
                current_prompt = prompt + _build_correction_feedback("timeout")

            except Exception as e:
                error_msg = str(e).upper()
                if any(kw in error_msg for kw in _NON_RETRYABLE_KEYWORDS):
                    raise
                if _is_model_unavailable_error(str(e)):
                    raise
                last_error = str(e)
                current_prompt = prompt + f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}"

        raise GeminiExhaustedError(
            f"{label}: Exhausted {1 + max_retries} attempts. Last error: {last_error}",
            last_raw=last_raw,
        )

    async def research_location_compliance_parallel(
        self,
        city: str,
        state: str,
        county: Optional[str] = None,
        categories: Optional[List[str]] = None,
        source_context: str = "",
        corrections_context: str = "",
        preemption_rules: Optional[Dict[str, bool]] = None,
        has_local_ordinance: Optional[bool] = None,
        on_retry: Optional[Callable[[int, str], Any]] = None,
        industry_context: str = "",
    ) -> List[Dict]:
        """Research compliance using parallel category-specific calls.

        Args:
            preemption_rules: Optional dict mapping category -> allows_local_override.
                When provided, prompts are enhanced with preemption awareness.
            industry_context: Optional context string for industry-specific research
                (e.g., healthcare-specific wage/overtime/scheduling rules).
        """

        location_str = f"{city}, {state}"
        if county:
            location_str += f" ({county})"

        # Build context
        context_section = source_context
        if corrections_context:
            context_section += f"\n\n{corrections_context}"

        selected_categories: List[str] = []
        for category in categories or DEFAULT_RESEARCH_CATEGORIES:
            normalized = _normalize_category_value(category)
            if normalized and normalized not in selected_categories:
                selected_categories.append(normalized)
        if not selected_categories:
            selected_categories = list(DEFAULT_RESEARCH_CATEGORIES)

        search_strategy = build_search_strategy_prompt(state, selected_categories)
        if search_strategy:
            context_section += f"\n\n{search_strategy}"

        # Build per-category preemption context strings
        preemption_map = preemption_rules or {}

        def _preemption_context_for(cat: str) -> str:
            allows = preemption_map.get(cat)
            if allows is None:
                if has_local_ordinance is False:
                    return (
                        f"\nIMPORTANT: {city} does NOT have its own local "
                        f"{cat.replace('_', ' ')} ordinance. Do NOT fabricate city-level rules. "
                        f"Return ONLY state-level (and county-level if applicable) requirements."
                    )
                return ""
            state_name = state  # 2-letter code
            if allows:
                if has_local_ordinance is False:
                    return (
                        f"\nIMPORTANT: {state_name} allows local jurisdictions to set their own "
                        f"{cat.replace('_', ' ')} rules. However, {city} does NOT have its own local "
                        f"{cat.replace('_', ' ')} ordinance. Do NOT fabricate city-level rules. "
                        f"Return ONLY state-level (and county-level if applicable) requirements."
                    )
                else:
                    return (
                        f"\nIMPORTANT: {state_name} allows local jurisdictions to set their own "
                        f"{cat.replace('_', ' ')} rules. Check if {city} has its own local ordinance. "
                        f"Always include the state baseline AND any local override if one exists."
                    )
            else:
                return (
                    f"\nIMPORTANT: {state_name} PREEMPTS local {cat.replace('_', ' ')} ordinances. "
                    f"Local cities/counties cannot set their own rates. "
                    f"Return ONLY state-level {cat.replace('_', ' ')} requirements. "
                    f"Do NOT return city or county level requirements for this category."
                )

        async def research_category(category: str) -> List[Dict]:
            """Research a single category with retry."""
            prompt = _build_category_prompt(
                location_str, category, context_section,
                preemption_context=_preemption_context_for(category),
                industry_context=industry_context,
            )
            try:
                def _validate(data: dict) -> Optional[str]:
                    reqs = data.get("requirements")
                    if not isinstance(reqs, list):
                        return "requirements must be a list"
                    return None

                result = await self._call_with_retry(
                    prompt,
                    "requirements",
                    max_retries=1,
                    validate_fn=_validate,
                    label=f"Research {category} for {location_str}",
                    on_retry=on_retry,
                )
                if not isinstance(result, list):
                    return []

                normalized_rows: List[Dict] = []
                for req in result:
                    if not isinstance(req, dict):
                        continue
                    normalized_rows.append(_coerce_requirement_shape(req, requested_category=category))

                return normalized_rows
            except GeminiExhaustedError as e:
                print(f"[Gemini Compliance] {category} exhausted: {e}")
                return []
            except Exception as e:
                print(f"[Gemini Compliance] {category} error: {e}")
                return []

        # Run categories in parallel with throttled concurrency to avoid
        # overwhelming Gemini API quota (especially with 20 categories).
        mode = await get_jurisdiction_research_model_mode()
        concurrency = 4 if mode == "heavy" else min(6, len(selected_categories))
        semaphore = asyncio.Semaphore(concurrency)

        async def research_category_throttled(category: str) -> List[Dict]:
            async with semaphore:
                return await research_category(category)

        print(
            f"[Gemini Compliance] Researching {location_str} "
            f"({len(selected_categories)} categories, concurrency={concurrency})..."
        )
        results = await asyncio.gather(*[research_category_throttled(c) for c in selected_categories])

        # Flatten and validate
        all_requirements = []
        for category_results in results:
            for req in category_results:
                error = _validate_requirement(req)
                if error:
                    print(f"[Gemini Compliance] Dropping invalid: {error}")
                else:
                    all_requirements.append(req)

        print(f"[Gemini Compliance] Found {len(all_requirements)} requirements for {location_str}")
        return all_requirements

    async def research_location_compliance(
        self,
        city: str,
        state: str,
        county: Optional[str] = None,
        categories: Optional[List[str]] = None,
        source_context: str = "",
        corrections_context: str = "",
        preemption_rules: Optional[Dict[str, bool]] = None,
        has_local_ordinance: Optional[bool] = None,
        on_retry: Optional[Callable[[int, str], Any]] = None,
        industry_context: str = "",
    ) -> List[Dict]:
        """Research compliance requirements for a location (uses parallel calls)."""
        if not self._has_api_key():
            print(f"[Gemini Compliance] ERROR: No GEMINI_API_KEY configured")
            return []

        return await self.research_location_compliance_parallel(
            city, state, county, categories, source_context, corrections_context,
            preemption_rules=preemption_rules,
            has_local_ordinance=has_local_ordinance,
            on_retry=on_retry,
            industry_context=industry_context,
        )

    async def discover_jurisdiction_sources(
        self,
        city: str,
        state: str,
        county: Optional[str] = None,
    ) -> List[Dict]:
        """One-time call to discover authoritative sources for a jurisdiction.

        Used to bootstrap the jurisdiction_sources table for new jurisdictions.
        Returns a list of source dictionaries with domain, name, categories, and jurisdiction_level.
        """
        location_str = f"{city}, {state}"
        if county:
            location_str += f" ({county})"

        prompt = f"""What are the official government sources for employment/labor law in {location_str}?

List the authoritative websites for:
- Minimum wage rates
- Paid sick leave requirements
- Overtime rules
- Meal/rest break requirements
- Pay frequency requirements
- Final paycheck and payout requirements
- Minor/youth work permit rules
- Scheduling / reporting-time / fair-workweek rules

Respond with JSON:
{{
  "sources": [
    {{
      "domain": "example.gov",
      "name": "Department Name",
      "categories": ["minimum_wage", "sick_leave"],
      "jurisdiction_level": "city" | "county" | "state"
    }}
  ]
}}

Only include official .gov or government-affiliated sources. Be specific to {location_str}.
Focus on the most authoritative sources (state labor departments, city wage offices, etc.).
"""
        try:
            if not self._has_api_key():
                print(f"[Gemini Compliance] ERROR: No GEMINI_API_KEY configured for source discovery")
                return []

            print(f"[Gemini Compliance] Discovering jurisdiction sources for {location_str}...")

            sources = await self._call_with_retry(
                prompt, "sources", max_retries=0, label=f"Discover sources {location_str}"
            )

            if not isinstance(sources, list):
                return []

            print(f"[Gemini Compliance] Discovered {len(sources)} sources for {location_str}")
            return sources

        except GeminiExhaustedError as e:
            print(f"[Gemini Compliance] Source discovery exhausted: {e}")
            return []
        except Exception as e:
            print(f"[Gemini Compliance] Source discovery error: {e}")
            return []

    async def verify_compliance_change(
        self,
        category: str,
        title: str,
        jurisdiction_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
    ) -> VerificationResult:
        """
        Verify a detected compliance change against authoritative sources.
        Returns confirmation, confidence score, and source citations.
        """
        prompt = f"""You are a compliance verification expert. A compliance monitoring system detected the following change:

Category: {category}
Rule: {title}
Jurisdiction: {jurisdiction_name}
Previous value: {old_value or 'N/A'}
New value: {new_value or 'N/A'}

Your task:
1. Use Google Search to verify whether this change is accurate
2. Check official government sources (.gov domains preferred)
3. Confirm or deny the change with supporting evidence

Respond with a JSON object:
{{
  "confirmed": true/false,
  "confidence": 0.0 to 1.0,
  "sources": [
    {{
      "url": "https://...",
      "name": "Source Name",
      "type": "official" | "news" | "blog" | "other",
      "snippet": "Brief relevant excerpt"
    }}
  ],
  "explanation": "Brief explanation of your findings"
}}

Be conservative with confidence scores:
- 0.9+ only if confirmed by official .gov source
- 0.6-0.9 if confirmed by reputable news sources
- 0.3-0.6 if only found in blogs or unverified sources
- Below 0.3 if you cannot find confirmation
"""
        try:
            if not self._has_api_key():
                return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="No API key configured")

            data = await self._call_with_retry(
                prompt,
                None,
                max_retries=1,
                validate_fn=_validate_verification,
                label=f"Verify {title}",
            )

            return VerificationResult(
                confirmed=data.get("confirmed", False),
                confidence=float(data.get("confidence", 0.0)),
                sources=data.get("sources", []),
                explanation=data.get("explanation", ""),
            )

        except GeminiExhaustedError as e:
            print(f"[Gemini Compliance] {e}")
            return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation=f"Verification exhausted retries: {e}")
        except Exception as e:
            error_msg = str(e)
            if "API_KEY" in error_msg.upper() or "PERMISSION" in error_msg.upper():
                print(f"[Gemini Compliance] Verification API Key/Permission error: {e}")
            else:
                print(f"[Gemini Compliance] Verification error: {e}")
            return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation=f"Verification failed: {e}")

    async def verify_compliance_change_adaptive(
        self,
        category: str,
        title: str,
        jurisdiction_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
    ) -> VerificationResult:
        """Adaptive verification: retry with refined prompt if confidence is in the grey zone (0.3-0.6)."""
        first = await self.verify_compliance_change(
            category=category, title=title, jurisdiction_name=jurisdiction_name,
            old_value=old_value, new_value=new_value,
        )

        # Confident enough or hopeless — return as-is
        if first.confidence >= 0.6 or first.confidence < 0.3:
            return first

        # Grey zone: retry with a more targeted prompt
        print(f"[Gemini Compliance] Adaptive retry for {title}: first confidence={first.confidence:.2f}")

        refined_prompt = f"""You are a compliance verification expert performing a SECOND verification pass.

A previous verification attempt returned LOW CONFIDENCE ({first.confidence:.2f}) for the following change:

Category: {category}
Rule: {title}
Jurisdiction: {jurisdiction_name}
Previous value: {old_value or 'N/A'}
New value: {new_value or 'N/A'}

Previous explanation: {first.explanation}

Your task for this second pass:
1. Search SPECIFICALLY for official .gov sources for {jurisdiction_name}
2. Look for the exact value "{new_value}" on government websites
3. Check the official labor department or wage board for {jurisdiction_name}
4. If the category is minimum_wage, search for "{jurisdiction_name} minimum wage {new_value}"

Respond with a JSON object:
{{
  "confirmed": true/false,
  "confidence": 0.0 to 1.0,
  "sources": [
    {{
      "url": "https://...",
      "name": "Source Name",
      "type": "official" | "news" | "blog" | "other",
      "snippet": "Brief relevant excerpt"
    }}
  ],
  "explanation": "Brief explanation of your findings"
}}

Be conservative with confidence scores:
- 0.9+ only if confirmed by official .gov source
- 0.6-0.9 if confirmed by reputable news sources
- 0.3-0.6 if only found in blogs or unverified sources
- Below 0.3 if you cannot find confirmation
"""
        try:
            if not self._has_api_key():
                return first

            # Check rate limit for adaptive retry
            try:
                await get_rate_limiter().check_and_record("gemini_compliance", f"adaptive_verify_{title[:30]}")
            except RateLimitExceeded:
                print(f"[Gemini Compliance] Rate limit hit during adaptive retry, returning first result")
                return first

            tools = [types.Tool(google_search=types.GoogleSearch())]
            response, _model_used = await self._generate_content_with_model_fallback(
                contents=refined_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    tools=tools,
                    response_modalities=["TEXT"],
                ),
                timeout_seconds=GEMINI_CALL_TIMEOUT,
            )

            raw_text = response.text
            cleaned = _clean_json_text(raw_text)
            data = json.loads(cleaned)

            val_err = _validate_verification(data)
            if val_err:
                print(f"[Gemini Compliance] Adaptive retry validation failed: {val_err}")
                return first

            second = VerificationResult(
                confirmed=data.get("confirmed", False),
                confidence=float(data.get("confidence", 0.0)),
                sources=data.get("sources", []),
                explanation=data.get("explanation", ""),
            )

            # Return whichever has higher confidence
            if second.confidence > first.confidence:
                print(f"[Gemini Compliance] Adaptive retry improved confidence: {first.confidence:.2f} -> {second.confidence:.2f}")
                return second
            return first

        except Exception as e:
            print(f"[Gemini Compliance] Adaptive retry failed: {e}")
            return first

    async def verify_compliance_changes_batch(
        self,
        changes: List[Dict],
        jurisdiction_name: str,
    ) -> List[VerificationResult]:
        """
        Verify multiple compliance changes in a single API call for efficiency.
        All changes should be for the same jurisdiction to share context.

        Args:
            changes: List of dicts with keys: category, title, old_value, new_value, index
            jurisdiction_name: The jurisdiction these changes apply to

        Returns:
            List of VerificationResults in the same order as input changes
        """
        if not changes:
            return []

        if len(changes) == 1:
            # Single change - use regular verification
            c = changes[0]
            result = await self.verify_compliance_change(
                category=c.get("category", ""),
                title=c.get("title", ""),
                jurisdiction_name=jurisdiction_name,
                old_value=c.get("old_value"),
                new_value=c.get("new_value"),
            )
            return [result]

        # Build batch prompt
        changes_text = "\n".join([
            f"{i+1}. Category: {c.get('category')}\n"
            f"   Rule: {c.get('title')}\n"
            f"   Previous value: {c.get('old_value') or 'N/A'}\n"
            f"   New value: {c.get('new_value') or 'N/A'}"
            for i, c in enumerate(changes)
        ])

        prompt = f"""You are a compliance verification expert. A compliance monitoring system detected the following {len(changes)} changes for {jurisdiction_name}:

{changes_text}

Your task:
1. Use Google Search to verify whether EACH of these changes is accurate
2. Check official government sources (.gov domains preferred) for {jurisdiction_name}
3. Confirm or deny EACH change with supporting evidence

IMPORTANT: Verify each change independently but share your research context across all of them.
This is more efficient than separate searches for each change.

Respond with a JSON object containing an array of results, one for each change IN THE SAME ORDER:
{{
  "results": [
    {{
      "change_number": 1,
      "confirmed": true/false,
      "confidence": 0.0 to 1.0,
      "sources": [
        {{
          "url": "https://...",
          "name": "Source Name",
          "type": "official" | "news" | "blog" | "other",
          "snippet": "Brief relevant excerpt"
        }}
      ],
      "explanation": "Brief explanation of your findings"
    }},
    // ... one entry for each change
  ]
}}

Be conservative with confidence scores:
- 0.9+ only if confirmed by official .gov source
- 0.6-0.9 if confirmed by reputable news sources
- 0.3-0.6 if only found in blogs or unverified sources
- Below 0.3 if you cannot find confirmation

You MUST return exactly {len(changes)} results, one for each change listed above.
"""
        try:
            if not self._has_api_key():
                return [VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="No API key configured")] * len(changes)

            # Check rate limit
            try:
                await get_rate_limiter().check_and_record("gemini_compliance", f"batch_verify_{jurisdiction_name[:20]}")
            except RateLimitExceeded:
                print(f"[Gemini Compliance] Rate limit hit during batch verification")
                return [VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="Rate limit exceeded")] * len(changes)

            tools = [types.Tool(google_search=types.GoogleSearch())]
            response, _model_used = await self._generate_content_with_model_fallback(
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    tools=tools,
                    response_modalities=["TEXT"],
                ),
                timeout_seconds=GEMINI_CALL_TIMEOUT * 2,  # Double timeout for batch
            )

            raw_text = response.text
            cleaned = _clean_json_text(raw_text)
            data = json.loads(cleaned)

            results_list = data.get("results", [])
            if not isinstance(results_list, list):
                print(f"[Gemini Compliance] Batch verification returned non-list results")
                return [VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="Invalid batch response")] * len(changes)

            # Map results to VerificationResult objects
            verification_results = []
            for i, change in enumerate(changes):
                # Find matching result by change_number or use index
                result_data = None
                for r in results_list:
                    if r.get("change_number") == i + 1:
                        result_data = r
                        break
                if result_data is None and i < len(results_list):
                    result_data = results_list[i]

                if result_data:
                    verification_results.append(VerificationResult(
                        confirmed=result_data.get("confirmed", False),
                        confidence=float(result_data.get("confidence", 0.0)),
                        sources=result_data.get("sources", []),
                        explanation=result_data.get("explanation", ""),
                    ))
                else:
                    verification_results.append(VerificationResult(
                        confirmed=False, confidence=0.0, sources=[],
                        explanation=f"No result returned for change {i+1}",
                    ))

            print(f"[Gemini Compliance] Batch verified {len(changes)} changes in single call")
            return verification_results

        except Exception as e:
            print(f"[Gemini Compliance] Batch verification error: {e}")
            return [VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation=f"Batch verification failed: {e}")] * len(changes)

    async def scan_upcoming_legislation(
        self,
        city: str,
        state: str,
        county: Optional[str] = None,
        current_requirements: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Scan for upcoming or pending legislation that may affect compliance.
        Returns a list of upcoming legislative changes.
        """
        location_str = f"{city}, {state}"
        if county:
            location_str += f" ({county})"

        context_lines = ""
        if current_requirements:
            context_lines = "\n".join(
                f"- {r.get('category', 'unknown')}: {r.get('title', 'N/A')} = {r.get('current_value', 'N/A')}"
                for r in current_requirements[:10]
            )

        prompt = f"""You are a legislative monitoring expert. Search for upcoming, pending, or recently passed legislation that could affect labor law compliance for businesses in {location_str}.

{"Current requirements for context:" + chr(10) + context_lines if context_lines else ""}

Focus on:
1. Minimum wage increases (scheduled or proposed)
2. New or expanded sick leave requirements
3. Changes to overtime rules
4. New meal/rest break requirements
5. Pay transparency or frequency changes
6. Final paycheck timing/payout changes (including PTO/vacation payout rules)
7. Minor/youth work permit or hour-limit changes
8. Fair-workweek / predictive scheduling / reporting-time changes

For each upcoming change, search for:
- Bills in the current legislative session
- Ballot measures
- Regulatory changes
- Scheduled effective dates of already-passed laws

Respond with a JSON object:
{{
  "upcoming": [
    {{
      "category": "minimum_wage" | "overtime" | "sick_leave" | "meal_breaks" | "pay_frequency" | "final_pay" | "minor_work_permit" | "scheduling_reporting" | "other",
      "title": "Short descriptive title",
      "description": "Detailed description of the change",
      "current_status": "proposed" | "passed" | "signed" | "effective_soon" | "effective",
      "expected_effective_date": "YYYY-MM-DD" or null,
      "impact_summary": "How this affects businesses",
      "source_url": "URL to source",
      "source_name": "Source name",
      "confidence": 0.0 to 1.0,
      "legislation_key": "unique_identifier_for_this_bill"
    }}
  ]
}}

Only include items you can verify through search. Be conservative with confidence scores.
Return an empty array if no upcoming legislation is found.
"""
        try:
            if not self._has_api_key():
                return []

            print(f"[Gemini Compliance] Scanning upcoming legislation for {location_str}...")

            # Best-effort: max_retries=0 (not worth the latency for supplementary data)
            upcoming = await self._call_with_retry(
                prompt,
                "upcoming",
                max_retries=0,
                label=f"Legislation scan {location_str}",
            )
            if not isinstance(upcoming, list):
                upcoming = []

            print(f"[Gemini Compliance] Found {len(upcoming)} upcoming legislative items for {location_str}")
            return upcoming

        except GeminiExhaustedError as e:
            print(f"[Gemini Compliance] Legislation scan exhausted: {e}")
            return []
        except Exception as e:
            error_msg = str(e)
            if "API_KEY" in error_msg.upper() or "PERMISSION" in error_msg.upper():
                print(f"[Gemini Compliance] API Key/Permission error: {e}")
            elif "QUOTA" in error_msg.upper() or "RATE" in error_msg.upper():
                print(f"[Gemini Compliance] Rate limit/quota error: {e}")
            else:
                print(f"[Gemini Compliance] Error scanning legislation: {e}")
            return []


# Singleton instance
_gemini_compliance: Optional[GeminiComplianceService] = None

def get_gemini_compliance_service() -> GeminiComplianceService:
    global _gemini_compliance
    if _gemini_compliance is None:
        _gemini_compliance = GeminiComplianceService()
    return _gemini_compliance
