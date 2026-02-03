"""IR Analyzer Service for Incident Reports.

AI-powered analysis for incident reporting:
- Auto-categorization (incident type detection)
- Severity assessment
- Root cause analysis
- Corrective action recommendations
- Similar incident detection
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Any, Callable

from google import genai

from ...core.services.rate_limiter import get_rate_limiter, RateLimitExceeded


# ===========================================
# Constants and Exceptions
# ===========================================

GEMINI_CALL_TIMEOUT = 45  # seconds


class IRAnalysisError(Exception):
    """Raised when IR analysis fails after all retries."""
    pass


# ===========================================
# Validation Functions
# ===========================================

VALID_INCIDENT_TYPES = {"safety", "behavioral", "property", "near_miss", "other"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def _validate_categorization(result: dict) -> Optional[str]:
    """Validate categorization response. Returns error message or None."""
    if result.get("suggested_type") not in VALID_INCIDENT_TYPES:
        return f"Invalid suggested_type: {result.get('suggested_type')}. Must be one of: {VALID_INCIDENT_TYPES}"

    confidence = result.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return f"Invalid confidence: {confidence} (must be number between 0.0 and 1.0)"

    if not result.get("reasoning"):
        return "Missing required field: reasoning"

    return None


def _validate_severity(result: dict) -> Optional[str]:
    """Validate severity response. Returns error message or None."""
    if result.get("suggested_severity") not in VALID_SEVERITIES:
        return f"Invalid suggested_severity: {result.get('suggested_severity')}. Must be one of: {VALID_SEVERITIES}"

    if not isinstance(result.get("factors"), list):
        return "Invalid factors: must be a list"

    if not result.get("reasoning"):
        return "Missing required field: reasoning"

    return None


def _validate_root_cause(result: dict) -> Optional[str]:
    """Validate root cause analysis response. Returns error message or None."""
    if not result.get("primary_cause"):
        return "Missing required field: primary_cause"

    if not isinstance(result.get("contributing_factors"), list):
        return "Invalid contributing_factors: must be a list"

    if not isinstance(result.get("prevention_suggestions"), list):
        return "Invalid prevention_suggestions: must be a list"

    if not result.get("reasoning"):
        return "Missing required field: reasoning"

    return None


def _validate_recommendations(result: dict) -> Optional[str]:
    """Validate recommendations response. Returns error message or None."""
    if not isinstance(result.get("recommendations"), list):
        return "Invalid recommendations: must be a list"

    if len(result.get("recommendations", [])) == 0:
        return "recommendations list cannot be empty"

    valid_priorities = {"immediate", "short_term", "long_term"}
    for i, rec in enumerate(result.get("recommendations", [])):
        if not isinstance(rec, dict):
            return f"recommendations[{i}] must be an object"
        if not rec.get("action"):
            return f"recommendations[{i}] missing required field: action"
        if rec.get("priority") not in valid_priorities:
            return f"recommendations[{i}] invalid priority: {rec.get('priority')}. Must be one of: {valid_priorities}"

    if not result.get("summary"):
        return "Missing required field: summary"

    return None


def _validate_similar_incidents(result: dict) -> Optional[str]:
    """Validate similar incidents response. Returns error message or None."""
    if not isinstance(result.get("similar_incidents"), list):
        return "Invalid similar_incidents: must be a list"

    for i, inc in enumerate(result.get("similar_incidents", [])):
        if not isinstance(inc, dict):
            return f"similar_incidents[{i}] must be an object"
        if not inc.get("incident_id"):
            return f"similar_incidents[{i}] missing required field: incident_id"
        if not inc.get("incident_number"):
            return f"similar_incidents[{i}] missing required field: incident_number"
        score = inc.get("similarity_score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            return f"similar_incidents[{i}] invalid similarity_score: {score}"

    return None


# ===========================================
# Prompts
# ===========================================

CATEGORIZATION_PROMPT = """You are an HR incident analysis assistant. Analyze this incident report and determine the most appropriate category.

INCIDENT REPORT:
Title: {title}
Description: {description}
Location: {location}
Reported By: {reported_by}

AVAILABLE CATEGORIES:
- safety: Physical injuries, accidents, unsafe conditions, OSHA-recordable events
- behavioral: HR issues, policy violations, harassment, discrimination, workplace conflicts
- property: Damage to equipment, facilities, company assets
- near_miss: Close calls, hazards identified, incidents that could have caused harm but didn't
- other: Incidents that don't clearly fit other categories

Your task:
1. Analyze the incident description carefully
2. Identify keywords and context clues
3. Determine the most likely category
4. Provide confidence level and reasoning

Return ONLY a JSON object with this structure:
{{
    "suggested_type": "safety",
    "confidence": 0.85,
    "reasoning": "The incident mentions a slip on wet floor resulting in minor injury, which is clearly a safety/injury incident. Keywords: 'fell', 'injured', 'wet floor'.",
    "alternative_types": [
        {{
            "type": "near_miss",
            "confidence": 0.10,
            "reason": "If no injury occurred, this could be a near miss"
        }}
    ]
}}

Confidence should be between 0.0 and 1.0."""


SEVERITY_ASSESSMENT_PROMPT = """You are an HR incident analysis assistant. Assess the severity of this incident.

INCIDENT REPORT:
Title: {title}
Description: {description}
Type: {incident_type}
Location: {location}
Category-Specific Data: {category_data}

SEVERITY LEVELS:
- critical: Life-threatening, major regulatory violation, significant business impact, requires immediate executive attention
- high: Serious injury requiring medical attention, major policy violation, significant property damage, potential legal exposure
- medium: Minor injury requiring first aid, policy violation, moderate property damage, needs follow-up action
- low: No injury, minor incident, near miss, learning opportunity, no immediate action required

Your task:
1. Evaluate injury severity (if safety incident)
2. Consider regulatory implications (OSHA, legal)
3. Assess business/operational impact
4. Consider repeat/pattern potential
5. Determine appropriate severity level

Return ONLY a JSON object with this structure:
{{
    "suggested_severity": "medium",
    "factors": [
        "Minor injury requiring first aid only",
        "No OSHA recordable event",
        "Equipment still operational",
        "First occurrence at this location"
    ],
    "reasoning": "While the incident resulted in an injury, it was minor and required only first aid. No days lost and no medical treatment needed. However, the wet floor condition should be addressed to prevent recurrence.",
    "escalation_recommended": false,
    "escalation_reason": null
}}"""


ROOT_CAUSE_PROMPT = """You are an HR incident analysis assistant specializing in root cause analysis. Analyze this incident to identify root causes and contributing factors.

INCIDENT REPORT:
Title: {title}
Description: {description}
Type: {incident_type}
Severity: {severity}
Location: {location}
Category-Specific Data: {category_data}
Witnesses: {witnesses}

Use the "5 Whys" methodology and consider these common root cause categories:
- Human factors (training, fatigue, inattention, communication)
- Process/Procedure (inadequate SOPs, unclear instructions)
- Equipment/Tools (malfunction, improper maintenance, design flaw)
- Environment (lighting, weather, workspace layout, hazards)
- Management/Organizational (staffing, supervision, culture, resources)

Your task:
1. Identify the primary root cause
2. List contributing factors
3. Suggest preventive measures
4. Consider systemic issues

Return ONLY a JSON object with this structure:
{{
    "primary_cause": "Inadequate floor maintenance protocol during high-traffic periods",
    "cause_category": "Process/Procedure",
    "contributing_factors": [
        "No wet floor signage deployed",
        "Cleaning occurred during peak hours",
        "Employee rushing to meeting"
    ],
    "five_whys": [
        {{
            "why": "Why did the employee fall?",
            "answer": "The floor was wet and slippery"
        }},
        {{
            "why": "Why was the floor wet?",
            "answer": "It had just been mopped"
        }},
        {{
            "why": "Why wasn't there warning signage?",
            "answer": "The janitor didn't have signs available"
        }},
        {{
            "why": "Why weren't signs available?",
            "answer": "Signs weren't restocked after last cleaning"
        }},
        {{
            "why": "Why weren't they restocked?",
            "answer": "No inventory check process exists for safety equipment"
        }}
    ],
    "prevention_suggestions": [
        "Implement wet floor signage checklist for all cleaning staff",
        "Schedule high-traffic area cleaning during off-peak hours",
        "Add safety equipment to regular inventory checks"
    ],
    "reasoning": "This incident could have been prevented with proper warning signage. The root cause traces back to a process gap in safety equipment management."
}}"""


RECOMMENDATIONS_PROMPT = """You are an HR incident analysis assistant. Generate corrective action recommendations for this incident.

INCIDENT REPORT:
Title: {title}
Description: {description}
Type: {incident_type}
Severity: {severity}
Root Cause Analysis: {root_cause}

COMPANY CONTEXT:
Company: {company_name}
Industry: {industry}
Company Size: {company_size}
Location: {city}, {state}

COMPANY-SPECIFIC GUIDANCE:
{ir_guidance_blurb}

Generate practical, actionable recommendations for:
1. Immediate actions (within 24-48 hours)
2. Short-term improvements (within 1-2 weeks)
3. Long-term systemic changes (within 1-3 months)

Consider:
- Industry-specific regulations and best practices for {industry}
- State/local requirements for {state}
- Company size constraints ({company_size})
- The company's specific guidance above (if provided)
- Regulatory compliance requirements
- Resource constraints (time, budget, personnel)
- Effectiveness and measurability
- Impact on operations

Return ONLY a JSON object with this structure:
{{
    "recommendations": [
        {{
            "action": "Deploy wet floor signage immediately in affected area",
            "priority": "immediate",
            "responsible_party": "Facilities Manager",
            "estimated_effort": "1 hour",
            "rationale": "Prevent additional incidents while root cause is addressed"
        }},
        {{
            "action": "Conduct safety briefing with all cleaning staff on proper signage protocols",
            "priority": "short_term",
            "responsible_party": "Facilities Manager",
            "estimated_effort": "2 hours + staff time",
            "rationale": "Ensure all staff understand and follow safety protocols"
        }},
        {{
            "action": "Implement safety equipment inventory management system",
            "priority": "long_term",
            "responsible_party": "Operations Manager",
            "estimated_effort": "1-2 weeks for setup",
            "rationale": "Address systemic gap in equipment availability"
        }}
    ],
    "training_recommended": true,
    "training_topics": ["Wet floor safety", "Signage protocols", "Incident reporting"],
    "policy_review_recommended": true,
    "policies_to_review": ["Cleaning schedules", "Safety equipment protocols"],
    "summary": "Three-tier response addressing immediate hazard, staff awareness, and systemic process improvement."
}}"""


SIMILAR_INCIDENTS_PROMPT = """You are an HR incident analysis assistant. Analyze this incident against historical data to identify patterns and similar incidents.

CURRENT INCIDENT:
Title: {title}
Description: {description}
Type: {incident_type}
Location: {location}
Occurred: {occurred_at}

HISTORICAL INCIDENTS (last 12 months):
{historical_incidents}

Your task:
1. Identify similar incidents by type, location, or cause
2. Detect patterns (recurring issues, hotspots, timing)
3. Assess if this is part of a larger trend
4. Flag any concerning patterns

Return ONLY a JSON object with this structure:
{{
    "similar_incidents": [
        {{
            "incident_id": "uuid-here",
            "incident_number": "IR-2024-01-ABC1",
            "title": "Slip and fall in kitchen",
            "similarity_score": 0.85,
            "common_factors": ["Same location", "Wet floor involved", "Similar time of day"]
        }}
    ],
    "pattern_detected": true,
    "pattern_summary": "This is the third wet floor incident in the cafeteria area in 6 months, suggesting a systemic issue with floor maintenance in this location.",
    "trend_analysis": {{
        "location_hotspot": true,
        "recurring_cause": true,
        "seasonal_pattern": false,
        "escalating_severity": false
    }},
    "recommendations": [
        "Prioritize floor safety assessment in cafeteria area",
        "Review cleaning protocols specifically for this location"
    ]
}}

If no similar incidents exist, return an empty similar_incidents array and pattern_detected: false."""


class IRAnalyzer:
    """AI-powered analysis for incident reports."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash",
    ):
        """
        Initialize the IR analyzer.

        Args:
            api_key: Gemini API key.
            vertex_project: GCP project ID for Vertex AI.
            vertex_location: Vertex AI location.
            model: Model to use for analysis.
        """
        self.model = model

        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    async def _call_with_retry(
        self,
        build_prompt_fn: Callable[[Optional[str]], str],
        validate_fn: Callable[[dict], Optional[str]],
        *,
        max_retries: int = 1,
        label: str = "ir_analysis",
    ) -> dict[str, Any]:
        """
        Call Gemini with retry logic and feedback on failure.

        Args:
            build_prompt_fn: Function that takes feedback (or None) and returns prompt.
            validate_fn: Function that validates result, returns error string or None.
            max_retries: Number of retries after initial attempt.
            label: Label for rate limiting tracking.

        Returns:
            Validated result dictionary.

        Raises:
            IRAnalysisError: If all attempts fail.
            RateLimitExceeded: If rate limit is hit.
        """
        rate_limiter = get_rate_limiter()

        # Check rate limit before starting (fail fast if already at limit)
        await rate_limiter.check_limit("ir_analysis", label)

        last_error = None

        for attempt in range(1 + max_retries):
            # Check limit again before each retry attempt
            if attempt > 0:
                await rate_limiter.check_limit("ir_analysis", label)

            prompt = build_prompt_fn(feedback=last_error if attempt > 0 else None)

            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt,
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
                )

                # Record the actual API call
                await rate_limiter.record_call("ir_analysis", label)

                result = self._parse_json_response(response.text)

                # Validate the result
                validation_error = validate_fn(result)
                if validation_error:
                    last_error = f"PREVIOUS ATTEMPT FAILED VALIDATION: {validation_error}. Please fix and return valid JSON."
                    continue

                return result

            except asyncio.TimeoutError:
                last_error = f"PREVIOUS ATTEMPT TIMED OUT after {GEMINI_CALL_TIMEOUT}s. Please respond more concisely."
            except json.JSONDecodeError as e:
                last_error = f"PREVIOUS ATTEMPT FAILED JSON PARSE: {e}. Return ONLY valid JSON, no markdown."
            except Exception as e:
                last_error = f"PREVIOUS ATTEMPT FAILED: {e}"

        raise IRAnalysisError(f"Analysis failed after {max_retries + 1} attempts: {last_error}")

    async def categorize_incident(
        self,
        title: str,
        description: str,
        location: Optional[str] = None,
        reported_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Auto-categorize an incident based on its description.

        Args:
            title: Incident title.
            description: Incident description.
            location: Where the incident occurred.
            reported_by: Who reported it.

        Returns:
            Categorization analysis with suggested type and confidence.
        """
        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = CATEGORIZATION_PROMPT.format(
                title=title,
                description=description or "No description provided",
                location=location or "Not specified",
                reported_by=reported_by or "Not specified",
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_categorization, label="categorize")
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def assess_severity(
        self,
        title: str,
        description: str,
        incident_type: str,
        location: Optional[str] = None,
        category_data: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Assess the severity of an incident.

        Args:
            title: Incident title.
            description: Incident description.
            incident_type: Type of incident.
            location: Where it occurred.
            category_data: Type-specific data.

        Returns:
            Severity assessment with suggested level and factors.
        """
        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = SEVERITY_ASSESSMENT_PROMPT.format(
                title=title,
                description=description or "No description provided",
                incident_type=incident_type,
                location=location or "Not specified",
                category_data=json.dumps(category_data) if category_data else "None",
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_severity, label="severity")
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def analyze_root_cause(
        self,
        title: str,
        description: str,
        incident_type: str,
        severity: str,
        location: Optional[str] = None,
        category_data: Optional[dict] = None,
        witnesses: Optional[list] = None,
    ) -> dict[str, Any]:
        """
        Perform root cause analysis on an incident.

        Args:
            title: Incident title.
            description: Incident description.
            incident_type: Type of incident.
            severity: Incident severity.
            location: Where it occurred.
            category_data: Type-specific data.
            witnesses: Witness statements.

        Returns:
            Root cause analysis with primary cause, contributing factors, and prevention suggestions.
        """
        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = ROOT_CAUSE_PROMPT.format(
                title=title,
                description=description or "No description provided",
                incident_type=incident_type,
                severity=severity,
                location=location or "Not specified",
                category_data=json.dumps(category_data) if category_data else "None",
                witnesses=json.dumps(witnesses) if witnesses else "No witness statements",
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_root_cause, label="root_cause")
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def generate_recommendations(
        self,
        title: str,
        description: str,
        incident_type: str,
        severity: str,
        root_cause: Optional[str] = None,
        # Company/location context parameters
        company_name: Optional[str] = None,
        industry: Optional[str] = None,
        company_size: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        ir_guidance_blurb: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Generate corrective action recommendations.

        Args:
            title: Incident title.
            description: Incident description.
            incident_type: Type of incident.
            severity: Incident severity.
            root_cause: Root cause analysis results.
            company_name: Name of the company.
            industry: Company industry.
            company_size: Company size (startup, mid, enterprise).
            city: Location city.
            state: Location state.
            ir_guidance_blurb: Company-specific IR guidance.

        Returns:
            Recommendations with prioritized actions.
        """
        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = RECOMMENDATIONS_PROMPT.format(
                title=title,
                description=description or "No description provided",
                incident_type=incident_type,
                severity=severity,
                root_cause=root_cause or "Not yet analyzed",
                company_name=company_name or "Not specified",
                industry=industry or "Not specified",
                company_size=company_size or "Not specified",
                city=city or "Not specified",
                state=state or "Not specified",
                ir_guidance_blurb=ir_guidance_blurb or "No specific guidance provided",
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_recommendations, label="recommendations")
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def find_similar_incidents(
        self,
        title: str,
        description: str,
        incident_type: str,
        location: Optional[str],
        occurred_at: datetime,
        historical_incidents: list[dict],
    ) -> dict[str, Any]:
        """
        Find similar historical incidents and detect patterns.

        Args:
            title: Current incident title.
            description: Current incident description.
            incident_type: Type of incident.
            location: Where it occurred.
            occurred_at: When it occurred.
            historical_incidents: List of past incidents with id, incident_number, title, description, incident_type, location.

        Returns:
            Similar incidents analysis with pattern detection.
        """
        # Format historical incidents
        historical_text = "\n".join([
            f"- {inc['incident_number']}: {inc['title']} (Type: {inc['incident_type']}, Location: {inc.get('location', 'N/A')}, Date: {inc.get('occurred_at', 'N/A')})"
            for inc in historical_incidents
        ]) if historical_incidents else "No historical incidents available."

        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = SIMILAR_INCIDENTS_PROMPT.format(
                title=title,
                description=description or "No description provided",
                incident_type=incident_type,
                location=location or "Not specified",
                occurred_at=occurred_at.isoformat() if occurred_at else "Not specified",
                historical_incidents=historical_text,
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_similar_incidents, label="similar_incidents")
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result


def get_ir_analyzer() -> IRAnalyzer:
    """Factory function to create IR analyzer with settings."""
    from ...config import get_settings

    settings = get_settings()

    if settings.use_vertex:
        return IRAnalyzer(
            vertex_project=settings.gcp_project,
            vertex_location="us-central1",
        )
    else:
        return IRAnalyzer(api_key=settings.gemini_api_key)
