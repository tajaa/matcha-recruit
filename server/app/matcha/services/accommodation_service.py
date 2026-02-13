"""Accommodation Analyzer Service for ADA Interactive Process.

AI-powered analysis for accommodation case management:
- Reasonable accommodation suggestions
- Undue hardship assessment
- Essential job function analysis
"""

import json
from datetime import datetime, timezone
from typing import Optional, Any

from google import genai


# ===========================================
# Prompts
# ===========================================

ACCOMMODATION_SUGGESTIONS_PROMPT = """You are an ADA accommodation specialist. Analyze this accommodation case and suggest reasonable accommodations.

CASE INFORMATION:
{case_info}

SUPPORTING DOCUMENTS:
{documents}

Your task:
1. Review the employee's disability category and requested accommodation
2. Suggest reasonable accommodations based on EEOC guidance and JAN (Job Accommodation Network) resources
3. For each suggestion, provide implementation steps, cost estimate, and effectiveness rating
4. Include relevant legal references

Return ONLY a JSON object with this structure:
{{
    "suggestions": [
        {{
            "accommodation": "Description of the accommodation",
            "rationale": "Why this accommodation is appropriate",
            "implementation_steps": ["Step 1", "Step 2"],
            "cost_estimate": "low",
            "effectiveness_rating": "high"
        }}
    ],
    "references": ["EEOC guidance on...", "JAN: ..."],
    "summary": "2-3 sentence overview of recommended accommodations"
}}

Cost estimates should be "low", "medium", or "high".
Effectiveness ratings should be "high", "medium", or "low".
Be thorough but practical. Focus on accommodations that are likely to be effective and reasonable."""


UNDUE_HARDSHIP_PROMPT = """You are an ADA compliance analyst. Assess whether the requested accommodation would constitute an undue hardship for the employer.

CASE INFORMATION:
{case_info}

SUPPORTING DOCUMENTS:
{documents}

Your task:
1. Analyze the accommodation request against the four statutory undue hardship factors
2. For each factor, provide an assessment and severity rating
3. Consider alternative accommodations if the primary request poses hardship
4. Provide overall reasoning

The four ADA undue hardship factors:
- Cost: Nature and net cost of the accommodation
- Financial resources: Overall financial resources of the facility and employer
- Operations: Impact on the operation of the facility
- Structure: Type of operation, including workforce composition and structure

Return ONLY a JSON object with this structure:
{{
    "hardship_likely": false,
    "factors": [
        {{
            "factor": "cost",
            "assessment": "Description of the cost impact",
            "severity": "low"
        }},
        {{
            "factor": "financial_resources",
            "assessment": "Description of financial impact",
            "severity": "low"
        }},
        {{
            "factor": "operations",
            "assessment": "Description of operational impact",
            "severity": "low"
        }},
        {{
            "factor": "structure",
            "assessment": "Description of structural impact",
            "severity": "low"
        }}
    ],
    "reasoning": "Overall analysis of whether undue hardship exists",
    "alternatives": ["Alternative accommodation 1", "Alternative accommodation 2"],
    "summary": "2-3 sentence summary of the hardship assessment"
}}

Severity should be "low", "medium", or "high".
Be objective and legally grounded. Note that the burden of proving undue hardship rests with the employer."""


JOB_FUNCTION_ANALYSIS_PROMPT = """You are an ADA compliance analyst. Analyze the essential and marginal functions of this job in context of the employee's accommodation request.

CASE INFORMATION:
{case_info}

JOB DESCRIPTION:
{job_description}

Your task:
1. Identify essential job functions (those fundamental to the position)
2. Identify marginal functions (those that are supplementary or could be reassigned)
3. Determine which functions are affected by the employee's disability
4. Suggest modifications for affected functions

Factors for determining essential functions:
- The reason the position exists
- Limited number of employees available to perform the function
- The function is highly specialized
- Time spent performing the function
- Consequences of not performing the function
- Terms of a collective bargaining agreement
- Work experience of past/current incumbents

Return ONLY a JSON object with this structure:
{{
    "essential_functions": ["Function 1", "Function 2"],
    "marginal_functions": ["Function 1", "Function 2"],
    "functions_affected_by_disability": ["Function that may be impacted"],
    "modification_options": [
        {{
            "function": "The affected function",
            "modification": "How it could be modified or reassigned",
            "feasibility": "high"
        }}
    ],
    "summary": "2-3 sentence overview of the job function analysis"
}}

Feasibility should be "high", "medium", or "low".
Be thorough and objective. Consider both the employer's needs and the employee's capabilities."""


class AccommodationAnalyzer:
    """AI-powered analysis for ADA accommodation cases."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash",
    ):
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

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    def _format_case_info(self, case_info: dict) -> str:
        """Format case info for inclusion in prompt."""
        parts = [
            f"Case Number: {case_info.get('case_number', 'N/A')}",
            f"Title: {case_info.get('title', 'N/A')}",
            f"Description: {case_info.get('description', 'N/A')}",
            f"Disability Category: {case_info.get('disability_category', 'N/A')}",
            f"Status: {case_info.get('status', 'N/A')}",
            f"Requested Accommodation: {case_info.get('requested_accommodation', 'N/A')}",
        ]
        return "\n".join(parts)

    def _format_documents(self, documents: list[dict]) -> str:
        """Format document list for inclusion in prompt."""
        if not documents:
            return "No supporting documents provided."
        parts = []
        for doc in documents:
            parts.append(f"--- Document: {doc.get('filename', 'Unknown')} (Type: {doc.get('document_type', 'other')}) ---")
            if doc.get("text"):
                parts.append(doc["text"])
            parts.append("")
        return "\n".join(parts)

    async def suggest_accommodations(
        self,
        case_info: dict,
        documents: list[dict] = None,
    ) -> dict[str, Any]:
        """Suggest reasonable accommodations based on case details."""
        prompt = ACCOMMODATION_SUGGESTIONS_PROMPT.format(
            case_info=self._format_case_info(case_info),
            documents=self._format_documents(documents or []),
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def assess_undue_hardship(
        self,
        case_info: dict,
        documents: list[dict] = None,
    ) -> dict[str, Any]:
        """Assess whether accommodation constitutes undue hardship."""
        prompt = UNDUE_HARDSHIP_PROMPT.format(
            case_info=self._format_case_info(case_info),
            documents=self._format_documents(documents or []),
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def analyze_job_functions(
        self,
        case_info: dict,
        job_description: str = "",
    ) -> dict[str, Any]:
        """Analyze essential vs marginal job functions."""
        prompt = JOB_FUNCTION_ANALYSIS_PROMPT.format(
            case_info=self._format_case_info(case_info),
            job_description=job_description or "No job description provided.",
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    # Synchronous versions for Celery tasks

    def suggest_accommodations_sync(
        self,
        case_info: dict,
        documents: list[dict] = None,
    ) -> dict[str, Any]:
        """Synchronous version of suggest_accommodations."""
        prompt = ACCOMMODATION_SUGGESTIONS_PROMPT.format(
            case_info=self._format_case_info(case_info),
            documents=self._format_documents(documents or []),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def assess_undue_hardship_sync(
        self,
        case_info: dict,
        documents: list[dict] = None,
    ) -> dict[str, Any]:
        """Synchronous version of assess_undue_hardship."""
        prompt = UNDUE_HARDSHIP_PROMPT.format(
            case_info=self._format_case_info(case_info),
            documents=self._format_documents(documents or []),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def analyze_job_functions_sync(
        self,
        case_info: dict,
        job_description: str = "",
    ) -> dict[str, Any]:
        """Synchronous version of analyze_job_functions."""
        prompt = JOB_FUNCTION_ANALYSIS_PROMPT.format(
            case_info=self._format_case_info(case_info),
            job_description=job_description or "No job description provided.",
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        result = self._parse_json_response(response.text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result
