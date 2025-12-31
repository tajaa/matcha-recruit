import json
from typing import Optional, Any

from google import genai


CULTURE_EXTRACTION_PROMPT = """Analyze this interview transcript where an AI interviewer asked an HR representative about their company culture.

Extract structured culture data from the conversation. Return ONLY a JSON object with these fields:

{{
    "collaboration_style": "highly_collaborative" | "independent" | "mixed",
    "communication": "async_first" | "sync_heavy" | "balanced",
    "pace": "fast_startup" | "steady" | "slow_methodical",
    "hierarchy": "flat" | "moderate" | "hierarchical",
    "values": ["list", "of", "core", "values"],
    "work_life_balance": "flexible" | "structured" | "demanding",
    "growth_focus": "promotion_track" | "skill_development" | "both",
    "decision_making": "consensus" | "top_down" | "autonomous",
    "remote_policy": "fully_remote" | "hybrid" | "in_office",
    "team_size": "small" | "medium" | "large",
    "key_traits": ["specific traits that make someone successful here"],
    "red_flags_for_candidates": ["traits that would not fit this culture"],
    "culture_summary": "2-3 sentence summary of the overall culture"
}}

TRANSCRIPT:
{transcript}

Return ONLY the JSON object, no other text."""


CULTURE_AGGREGATION_PROMPT = """You have culture data extracted from multiple interviews at the same company.
Aggregate these into a single unified culture profile.

For enum fields (collaboration_style, communication, etc.), choose the most common value or the one that best represents consensus.
For list fields (values, key_traits, red_flags_for_candidates), combine and deduplicate, keeping the most mentioned items.
Create a new culture_summary that synthesizes all the input.

INPUT DATA:
{culture_data_list}

Return ONLY a JSON object with the same structure as the inputs, representing the aggregated culture profile."""


class CultureAnalyzer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-3-flash-preview",
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

    async def extract_culture_from_transcript(self, transcript: str) -> dict[str, Any]:
        """Extract structured culture data from an interview transcript."""
        prompt = CULTURE_EXTRACTION_PROMPT.format(transcript=transcript)

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        # Parse JSON from response
        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[CultureAnalyzer] Failed to parse JSON: {e}")
            print(f"[CultureAnalyzer] Raw response: {text}")
            # Return a minimal structure
            return {
                "culture_summary": text[:500] if text else "Unable to extract culture data",
                "raw_response": text,
            }

    async def aggregate_culture_profiles(self, culture_data_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate multiple culture profiles into one."""
        if len(culture_data_list) == 1:
            return culture_data_list[0]

        prompt = CULTURE_AGGREGATION_PROMPT.format(
            culture_data_list=json.dumps(culture_data_list, indent=2)
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[CultureAnalyzer] Failed to parse aggregated JSON: {e}")
            # Return the first profile as fallback
            return culture_data_list[0]
