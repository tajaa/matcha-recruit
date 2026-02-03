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

# Timeout for individual Gemini API calls (seconds)
GEMINI_CALL_TIMEOUT = 45

VALID_CATEGORIES = {"minimum_wage", "overtime", "sick_leave", "meal_breaks", "pay_frequency"}
VALID_JURISDICTION_LEVELS = {"state", "county", "city", "federal"}

# Errors that should not be retried (API config / quota issues)
_NON_RETRYABLE_KEYWORDS = {"API_KEY", "PERMISSION", "QUOTA", "RATE"}

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


def _build_correction_feedback(error_type: str, **kwargs) -> str:
    """Build structured correction feedback for retry prompts."""
    template = CORRECTION_HINTS.get(error_type, "Previous attempt failed: {detail}")
    try:
        message = template.format(**kwargs)
    except KeyError:
        # Fallback if kwargs don't match template
        message = template
    return "\n\nPREVIOUS ATTEMPT FAILED: " + message


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

                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.settings.analysis_model,
                        contents=current_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            tools=tools,
                            response_modalities=["TEXT"],
                        ),
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
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
                last_error = str(e)
                current_prompt = prompt + f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}"

        raise GeminiExhaustedError(
            f"{label}: Exhausted {1 + max_retries} attempts. Last error: {last_error}",
            last_raw=last_raw,
        )

    async def research_location_compliance(
        self,
        city: str,
        state: str,
        county: Optional[str] = None,
        source_context: str = "",
        on_retry: Optional[Callable[[int, str], Any]] = None,
    ) -> List[Dict]:
        """
        Research compliance requirements for a specific location.
        Returns a list of dictionaries matching the ComplianceRequirement structure.

        Args:
            city: City name
            state: State code (e.g., "CA")
            county: Optional county name
            source_context: Optional context about known authoritative sources
            on_retry: Optional callback for retry events
        """

        location_str = f"{city}, {state}"
        if county:
            location_str += f" ({county})"

        prompt = f"""You are a compliance research expert. Research current labor laws and compliance requirements for a business operating in {location_str}.
{source_context}

Focus on these specific categories:
1. Minimum Wage — general/default rate ONLY (not industry-specific, tipped, fast-food, healthcare, hotel, etc.)
2. Overtime rules
3. Paid Sick Leave
4. Meal and Rest Break Requirements
5. Pay Frequency Requirements

IMPORTANT RULES:
- For each category, return ONLY the single most local jurisdiction that applies (city > county > state). Do NOT include overlapping jurisdictions for the same category. For example, if {location_str} has a city minimum wage, return ONLY the city rate, not the state rate.
- For minimum wage, return ONLY the general/default rate. Do NOT include industry-specific rates (fast food, healthcare, hotel, tipped, etc.).
- Accuracy is critical. Double-check numeric values against official government sources.

For EACH requirement, provide:
- The specific requirement/rule
- The current value (e.g., "$16.00/hr")
- The effective date of this rule
- The source URL (official government website preferred)
- The jurisdiction level (state, county, or city)

Today's date is {date.today().isoformat()}. Return ONLY the rates/values that are currently in effect as of today. Do not return upcoming or past rates.

Respond with a JSON object containing a list of requirements under the key "requirements".
Each requirement object should have:
- "category": One of ["minimum_wage", "overtime", "sick_leave", "meal_breaks", "pay_frequency"]
- "jurisdiction_level": One of ["state", "county", "city"]
- "jurisdiction_name": Name of the jurisdiction (e.g., "California" or "San Francisco")
- "title": Short title (e.g., "California Minimum Wage")
- "description": Detailed explanation of the rule
- "current_value": The specific value (e.g., "$16.00/hr")
- "numeric_value": Float value if applicable (e.g., 16.00), else null
- "effective_date": "YYYY-MM-DD" if known, else null
- "source_url": URL to the official source
- "source_name": Name of the source (e.g., "CA Dept of Industrial Relations")

Example JSON structure:
{{
  "requirements": [
    {{
      "category": "minimum_wage",
      "jurisdiction_level": "city",
      "jurisdiction_name": "San Francisco",
      "title": "San Francisco Minimum Wage",
      "description": "The minimum wage in San Francisco is $18.67 per hour.",
      "current_value": "$18.67/hr",
      "numeric_value": 18.67,
      "effective_date": "2024-07-01",
      "source_url": "https://sfgov.org/olse/minimum-wage-ordinance",
      "source_name": "SF OLSE"
    }}
  ]
}}

Return at most one requirement per category. Ensure all data is accurate and sourced.
"""

        try:
            if not self._has_api_key():
                print(f"[Gemini Compliance] ERROR: No GEMINI_API_KEY configured")
                return []

            print(f"[Gemini Compliance] Researching compliance for {location_str}...")

            def _validate_research(data: dict) -> Optional[str]:
                reqs = data.get("requirements")
                if not isinstance(reqs, list) or len(reqs) == 0:
                    return "requirements list is empty"
                return None

            requirements = await self._call_with_retry(
                prompt,
                "requirements",
                max_retries=1,
                validate_fn=_validate_research,
                label=f"Research {location_str}",
                on_retry=on_retry,
            )

            # Filter out invalid items
            valid = []
            for req in requirements:
                error = _validate_requirement(req)
                if error:
                    print(f"[Gemini Compliance] Dropping invalid requirement: {error} — {req.get('title', '?')}")
                else:
                    valid.append(req)

            print(f"[Gemini Compliance] Found {len(valid)} requirements for {location_str}")
            return valid

        except GeminiExhaustedError as e:
            print(f"[Gemini Compliance] {e}")
            # Attempt to salvage valid requirements from the last raw response
            if e.last_raw:
                try:
                    cleaned = _clean_json_text(e.last_raw)
                    data = json.loads(cleaned)
                    raw_reqs = data.get("requirements", [])
                    salvaged = [r for r in raw_reqs if _validate_requirement(r) is None]
                    if salvaged:
                        print(f"[Gemini Compliance] Salvaged {len(salvaged)} valid requirements from partial response")
                        return salvaged
                except Exception:
                    pass
            return []
        except Exception as e:
            error_msg = str(e)
            if "API_KEY" in error_msg.upper() or "PERMISSION" in error_msg.upper():
                print(f"[Gemini Compliance] API Key/Permission error: {e}")
            elif "QUOTA" in error_msg.upper() or "RATE" in error_msg.upper():
                print(f"[Gemini Compliance] Rate limit/quota error: {e}")
            else:
                print(f"[Gemini Compliance] Error researching requirements: {e}")
            return []

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
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.settings.analysis_model,
                    contents=refined_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=tools,
                        response_modalities=["TEXT"],
                    ),
                ),
                timeout=GEMINI_CALL_TIMEOUT,
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

For each upcoming change, search for:
- Bills in the current legislative session
- Ballot measures
- Regulatory changes
- Scheduled effective dates of already-passed laws

Respond with a JSON object:
{{
  "upcoming": [
    {{
      "category": "minimum_wage" | "overtime" | "sick_leave" | "meal_breaks" | "pay_frequency" | "other",
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
