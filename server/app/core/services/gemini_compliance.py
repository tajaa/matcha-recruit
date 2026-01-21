import json
import os
from typing import List, Optional, Dict
from datetime import datetime, date

from google import genai
from google.genai import types

from ...config import get_settings
from ..models.compliance import ComplianceCategory, JurisdictionLevel

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
1. Minimum Wage (State and Local if applicable)
2. Paid Time Off / Sick Leave
3. Meal and Rest Break Requirements
4. Child Labor Laws (Minor Laws)
5. Pay Frequency Requirements

For EACH category, I need you to find:
- The specific requirement/rule
- The current value (e.g., "$16.00/hr")
- The effective date of this rule
- The source of this information (government website URL preferred)
- The jurisdiction level (State, County, or City)

Use Google Search to find the most up-to-date information for 2025/2026.

Respond with a JSON object containing a list of requirements under the key "requirements".
Each requirement object should have:
- "category": One of ["minimum_wage", "sick_leave", "meal_breaks", "child_labor", "pay_frequency"]
- "jurisdiction_level": One of ["state", "county", "city"]
- "jurisdiction_name": Name of the jurisdiction (e.g., "California" or "San Francisco")
- "title": Short title (e.g., "California Minimum Wage")
- "description": Detailed explanation of the rule
- "current_value": The specific value (e.g., "$16.00")
- "numeric_value": Float value if applicable (e.g., 16.00), else null
- "effective_date": "YYYY-MM-DD" if known, else null
- "source_url": URL to the official source
- "source_name": Name of the source (e.g., "CA Dept of Industrial Relations")

Example JSON structure:
{{
  "requirements": [
    {{
      "category": "minimum_wage",
      "jurisdiction_level": "state",
      "jurisdiction_name": "California",
      "title": "California Minimum Wage",
      "description": "The minimum wage for all employers in California is $16.00 per hour.",
      "current_value": "$16.00",
      "numeric_value": 16.00,
      "effective_date": "2024-01-01",
      "source_url": "https://www.dir.ca.gov/dlse/faq_minimumwage.htm",
      "source_name": "CA DIR"
    }}
  ]
}}

Ensure all data is accurate and recent. If a local (city/county) law overrides a state law (e.g., higher minimum wage), include BOTH.
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

            response = await self.client.aio.models.generate_content(
                model=self.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    tools=tools,
                    response_modalities=["TEXT"],
                ),
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
        except Exception as e:
            error_msg = str(e)
            if "API_KEY" in error_msg.upper() or "PERMISSION" in error_msg.upper():
                print(f"[Gemini Compliance] API Key/Permission error: {e}")
            elif "QUOTA" in error_msg.upper() or "RATE" in error_msg.upper():
                print(f"[Gemini Compliance] Rate limit/quota error: {e}")
            else:
                print(f"[Gemini Compliance] Error researching requirements: {e}")
            return []

# Singleton instance
_gemini_compliance: Optional[GeminiComplianceService] = None

def get_gemini_compliance_service() -> GeminiComplianceService:
    global _gemini_compliance
    if _gemini_compliance is None:
        _gemini_compliance = GeminiComplianceService()
    return _gemini_compliance
