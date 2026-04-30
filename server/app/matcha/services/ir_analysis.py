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


VALID_RELEVANCES = {"violated", "bent", "related"}


def _validate_policy_mapping(result: dict) -> Optional[str]:
    """Validate policy mapping response. Returns error message or None."""
    if not isinstance(result.get("matches"), list):
        return "Invalid matches: must be a list"

    for i, match in enumerate(result.get("matches", [])):
        if not isinstance(match, dict):
            return f"matches[{i}] must be an object"
        if not match.get("policy_id"):
            return f"matches[{i}] missing required field: policy_id"
        if not match.get("policy_title"):
            return f"matches[{i}] missing required field: policy_title"
        if match.get("relevance") not in VALID_RELEVANCES:
            return f"matches[{i}] invalid relevance: {match.get('relevance')}. Must be one of: {VALID_RELEVANCES}"
        confidence = match.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            return f"matches[{i}] invalid confidence: {confidence} (must be number between 0.0 and 1.0)"
        if not match.get("reasoning"):
            return f"matches[{i}] missing required field: reasoning"

    if not result.get("summary"):
        return "Missing required field: summary"

    return None


def _validate_risk_themes(result: dict) -> Optional[str]:
    """Validate risk-themes response. Returns error message or None."""
    themes = result.get("themes")
    if not isinstance(themes, list):
        return "Invalid themes: must be a list"

    for i, theme in enumerate(themes):
        if not isinstance(theme, dict):
            return f"themes[{i}] must be an object"
        if not theme.get("label"):
            return f"themes[{i}] missing required field: label"
        if theme.get("severity") not in VALID_SEVERITIES:
            return f"themes[{i}] invalid severity: {theme.get('severity')}. Must be one of: {VALID_SEVERITIES}"
        if not isinstance(theme.get("incident_count"), int) or theme["incident_count"] < 1:
            return f"themes[{i}] incident_count must be a positive integer"
        evidence = theme.get("evidence_incident_ids")
        if not isinstance(evidence, list) or len(evidence) == 0:
            return f"themes[{i}] evidence_incident_ids must be a non-empty list"
        if not theme.get("insight"):
            return f"themes[{i}] missing required field: insight"
        if not theme.get("recommendation"):
            return f"themes[{i}] missing required field: recommendation"

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


POLICY_MAPPING_PROMPT = """You are an HR policy compliance analyst. Given an incident report and a company's active policies, identify which policies were violated, bent, or are contextually related.

INCIDENT REPORT:
Title: {title}
Description: {description}
Type: {incident_type}
Severity: {severity}
Category-Specific Data: {category_data}

COMPANY ACTIVE POLICIES:
{policies_list}

Your task:
1. Analyze the incident against each policy
2. Identify policies that were clearly violated, arguably bent, or contextually related
3. For each match, explain the connection and quote a relevant excerpt from the policy if possible
4. Sort matches by confidence (highest first), return at most 5

Relevance tiers:
- violated: The incident clearly broke this policy
- bent: The policy was stretched or arguably not followed; debatable
- related: The policy is contextually relevant but not necessarily broken

Return ONLY a JSON object with this structure:
{{
    "matches": [
        {{
            "policy_id": "uuid-of-policy",
            "policy_title": "Anti-Harassment Policy",
            "relevance": "violated",
            "confidence": 0.92,
            "reasoning": "The reported behavior constitutes harassment as defined in Section 2 of the policy.",
            "relevant_excerpt": "All employees are expected to maintain a respectful workplace free from intimidation..."
        }}
    ],
    "summary": "This incident primarily violates the Anti-Harassment Policy and is related to the Code of Conduct.",
    "no_matching_policies": false
}}

If no policies match the incident, return matches as an empty array and no_matching_policies as true."""


RISK_THEMES_PROMPT = """You are an HR risk analyst. Scan the provided corpus of recent incident reports for recurring patterns and emerging themes that an operator should act on.

LOOK FOR:
- **Recurring infraction patterns**: insubordination, attendance, tardiness, repeated policy violations
- **Training / competence gaps**: mistakes, guest concerns, "unsure how to", procedure not followed correctly
- **Safety hotspots**: one location dominating injury/property/near-miss incidents
- **Management or morale signals**: multiple incidents involving the same supervisor, repeat reporters, escalating severity at one site
- **Equipment / process failures**: same equipment cited, same process step failing repeatedly

COMPANY CONTEXT:
{company_context}

LOCATIONS REGISTRY:
{locations_registry}

EMPLOYEES REGISTRY (when available — names involved in incidents):
{employees_registry}

INCIDENT CORPUS (most recent first, capped):
{incident_corpus}

TASK:
1. Identify themes (recurring patterns) supported by **3 or more** incidents from the corpus. Skip noise — single occurrences are not themes.
2. For each theme, name the supporting incident_ids (1–5 representative ones drawn ONLY from the corpus above).
3. If a theme is location-specific, set location_id to that location's id from the registry; if cross-location, set location_id to null.
4. Choose severity from low / medium / high / critical based on stakes (low = informational, critical = imminent harm or compliance risk).
5. Write a short insight paragraph (1–2 sentences) explaining why this matters.
6. Write a short recommendation (1 sentence) on what to do.
7. Cap the response at 8 themes. Surface the most actionable.

Return ONLY a JSON object with this structure:
{{
    "themes": [
        {{
            "label": "Insubordination cluster at one location",
            "severity": "high",
            "location_id": "uuid-from-registry-or-null",
            "incident_count": 5,
            "evidence_incident_ids": ["uuid-1", "uuid-2", "uuid-3"],
            "insight": "Five behavioral incidents at this site involve the same shift, suggesting either a morale issue or weak supervisory follow-through.",
            "recommendation": "Review shift schedules and conduct 1:1 coaching with the involved supervisor."
        }}
    ]
}}

If no patterns reach the 3-incident threshold, return {{ "themes": [] }}."""


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

    async def map_policy_violations(
        self,
        title: str,
        description: str,
        incident_type: str,
        severity: str,
        category_data: Optional[dict] = None,
        policies: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        Map an incident to company policies to identify violations.

        Args:
            title: Incident title.
            description: Incident description.
            incident_type: Type of incident.
            severity: Incident severity.
            category_data: Type-specific data.
            policies: List of active company policies with id, title, description/content.

        Returns:
            Policy mapping analysis with matched policies.
        """
        policies_text = "\n".join([
            f"{i+1}. [{p['id']}] {p['title']}: {(p.get('description') or (p.get('content') or '')[:200]) or 'No description'}"
            for i, p in enumerate(policies or [])
        ]) if policies else "No active policies available."

        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = POLICY_MAPPING_PROMPT.format(
                title=title,
                description=description or "No description provided",
                incident_type=incident_type,
                severity=severity,
                category_data=json.dumps(category_data) if category_data else "None",
                policies_list=policies_text,
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        result = await self._call_with_retry(build_prompt, _validate_policy_mapping, label="policy_mapping")
        result["matches"] = sorted(result.get("matches", []), key=lambda m: m.get("confidence", 0), reverse=True)[:5]
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def detect_risk_themes(
        self,
        incidents: list[dict],
        location_lookup: dict,
        employee_lookup: Optional[dict] = None,
        company_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Scan a corpus of incidents for recurring patterns and themes.

        Args:
            incidents: list of dicts with at least id, occurred_at, incident_type,
                severity, location_id, description, optional root_cause,
                witnesses, involved_employee_ids, er_case_id.
            location_lookup: {location_id_str: human-readable label}
            employee_lookup: optional {employee_id_str: name}
            company_context: optional one-line description for the company.

        Returns:
            {"themes": [...], "generated_at": iso}. Themes capped at 8 by prompt.
            Filters out themes whose evidence ids are not in the supplied corpus
            (Gemini sometimes hallucinates ids).
        """
        valid_incident_ids = {str(inc["id"]) for inc in incidents}
        valid_location_ids = set(location_lookup.keys())

        locations_registry = "\n".join(
            f"- {lid}: {label}" for lid, label in sorted(location_lookup.items())
        ) or "No locations registered."

        if employee_lookup:
            employees_registry = "\n".join(
                f"- {eid}: {name}" for eid, name in sorted(employee_lookup.items())
            )
        else:
            employees_registry = "Not provided (Cap tier or employees feature disabled)."

        def _format_incident(inc: dict) -> str:
            occurred = inc.get("occurred_at")
            occurred_str = occurred.isoformat() if hasattr(occurred, "isoformat") else (occurred or "unknown")
            loc_label = location_lookup.get(str(inc.get("location_id") or ""), "Unassigned")
            involved_ids = inc.get("involved_employee_ids") or []
            involved_names = [
                (employee_lookup or {}).get(str(eid), str(eid)[:8]) for eid in involved_ids
            ] if employee_lookup else []
            witness_names = []
            witnesses = inc.get("witnesses")
            if isinstance(witnesses, list):
                witness_names = [w.get("name") for w in witnesses if isinstance(w, dict) and w.get("name")]
            er_flag = " [linked to ER case]" if inc.get("er_case_id") else ""
            return (
                f"- id={inc['id']} | type={inc.get('incident_type')} | severity={inc.get('severity')} | "
                f"location={loc_label} | occurred={occurred_str}{er_flag}\n"
                f"  description: {(inc.get('description') or '').strip()[:400]}\n"
                + (f"  involved: {', '.join(involved_names)}\n" if involved_names else "")
                + (f"  witnesses: {', '.join(witness_names)}\n" if witness_names else "")
                + (f"  root_cause: {(inc.get('root_cause') or '').strip()[:200]}\n" if inc.get("root_cause") else "")
            ).rstrip()

        incident_corpus = "\n".join(_format_incident(inc) for inc in incidents) or "No incidents in window."

        def build_prompt(feedback: Optional[str] = None) -> str:
            prompt = RISK_THEMES_PROMPT.format(
                company_context=company_context or "Not specified.",
                locations_registry=locations_registry,
                employees_registry=employees_registry,
                incident_corpus=incident_corpus,
            )
            if feedback:
                prompt += f"\n\n{feedback}"
            return prompt

        # Let IRAnalysisError propagate — caller distinguishes a legitimate
        # "no themes found" from a Gemini outage so it can skip caching the
        # empty result for 24h.
        result = await self._call_with_retry(build_prompt, _validate_risk_themes, label="risk_themes")

        cleaned: list[dict] = []
        for theme in result.get("themes", []):
            evidence = [eid for eid in theme.get("evidence_incident_ids", []) if eid in valid_incident_ids]
            if len(evidence) < 1:
                continue
            theme["evidence_incident_ids"] = evidence[:5]
            loc_id = theme.get("location_id")
            if loc_id and loc_id not in valid_location_ids:
                theme["location_id"] = None
            cleaned.append(theme)

        return {"themes": cleaned[:8], "generated_at": datetime.now(timezone.utc).isoformat()}


def get_ir_analyzer() -> IRAnalyzer:
    """Factory function to create IR analyzer with settings."""
    from ...config import get_settings

    settings = get_settings()

    if settings.use_vertex:
        return IRAnalyzer(
            vertex_project=settings.vertex_project,
            vertex_location="us-central1",
        )
    else:
        return IRAnalyzer(api_key=settings.gemini_api_key)
