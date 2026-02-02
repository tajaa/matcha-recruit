import asyncio
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from google import genai
from google.genai import types

from ...config import get_settings
from ..models.compliance import ComplianceCategory, JurisdictionLevel, VerificationResult

# Timeout for individual Gemini API calls (seconds)
GEMINI_CALL_TIMEOUT = 45

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

    async def research_location_compliance(
        self,
        city: str,
        state: str,
        county: Optional[str] = None
    ) -> List[Dict]:
        """
        Research compliance requirements for a specific location.
        Returns a list of dictionaries matching the ComplianceRequirement structure.
        """
        
        location_str = f"{city}, {state}"
        if county:
            location_str += f" ({county})"

        prompt = f"""You are a compliance research expert. Research current labor laws and compliance requirements for a business operating in {location_str}.

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
            # Check for API key
            api_key = os.getenv("GEMINI_API_KEY") or self.settings.gemini_api_key
            if not api_key and not self.settings.use_vertex:
                print(f"[Gemini Compliance] ERROR: No GEMINI_API_KEY configured")
                return []

            print(f"[Gemini Compliance] Researching compliance for {location_str}...")

            # Use Google Search tool
            tools = [types.Tool(google_search=types.GoogleSearch())]

            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.settings.analysis_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=tools,
                        response_modalities=["TEXT"],
                    ),
                ),
                timeout=GEMINI_CALL_TIMEOUT,
            )

            # Parse JSON from response
            text = response.text

            # Clean up markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())
            requirements = data.get("requirements", [])
            print(f"[Gemini Compliance] Found {len(requirements)} requirements for {location_str}")
            return requirements

        except json.JSONDecodeError as e:
            print(f"[Gemini Compliance] Error parsing JSON response: {e}")
            print(f"[Gemini Compliance] Raw response: {response.text[:500] if response else 'No response'}...")
            return []
        except (asyncio.TimeoutError, TimeoutError):
            print(f"[Gemini Compliance] Gemini API timed out after {GEMINI_CALL_TIMEOUT}s for {location_str}")
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
            api_key = os.getenv("GEMINI_API_KEY") or self.settings.gemini_api_key
            if not api_key and not self.settings.use_vertex:
                return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="No API key configured")

            tools = [types.Tool(google_search=types.GoogleSearch())]
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.settings.analysis_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=tools,
                        response_modalities=["TEXT"],
                    ),
                ),
                timeout=GEMINI_CALL_TIMEOUT,
            )

            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())
            return VerificationResult(
                confirmed=data.get("confirmed", False),
                confidence=float(data.get("confidence", 0.0)),
                sources=data.get("sources", []),
                explanation=data.get("explanation", ""),
            )
        except (asyncio.TimeoutError, TimeoutError):
            print(f"[Gemini Compliance] Verification timed out after {GEMINI_CALL_TIMEOUT}s for {title} in {jurisdiction_name}")
            return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation=f"Verification timed out after {GEMINI_CALL_TIMEOUT}s")
        except Exception as e:
            print(f"[Gemini Compliance] Verification error: {e}")
            return VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation=f"Verification failed: {e}")

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
            api_key = os.getenv("GEMINI_API_KEY") or self.settings.gemini_api_key
            if not api_key and not self.settings.use_vertex:
                return []

            print(f"[Gemini Compliance] Scanning upcoming legislation for {location_str}...")

            tools = [types.Tool(google_search=types.GoogleSearch())]
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.settings.analysis_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=tools,
                        response_modalities=["TEXT"],
                    ),
                ),
                timeout=GEMINI_CALL_TIMEOUT,
            )

            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())
            upcoming = data.get("upcoming", [])
            print(f"[Gemini Compliance] Found {len(upcoming)} upcoming legislative items for {location_str}")
            return upcoming

        except json.JSONDecodeError as e:
            print(f"[Gemini Compliance] Error parsing legislation JSON: {e}")
            return []
        except (asyncio.TimeoutError, TimeoutError):
            print(f"[Gemini Compliance] Legislation scan timed out after {GEMINI_CALL_TIMEOUT}s for {location_str}")
            return []
        except Exception as e:
            print(f"[Gemini Compliance] Error scanning legislation: {e}")
            return []

# Singleton instance
_gemini_compliance: Optional[GeminiComplianceService] = None

def get_gemini_compliance_service() -> GeminiComplianceService:
    global _gemini_compliance
    if _gemini_compliance is None:
        _gemini_compliance = GeminiComplianceService()
    return _gemini_compliance
