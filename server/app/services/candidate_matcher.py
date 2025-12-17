import json
from typing import Optional, Any

from google import genai


MATCHING_PROMPT = """You are evaluating how well a candidate would fit a company's culture.

COMPANY CULTURE PROFILE:
{culture_profile}

CANDIDATE PROFILE:
{candidate_profile}

Analyze the match between this candidate and the company culture. Consider:
1. Work style alignment (pace, collaboration, communication preferences)
2. Values alignment
3. Growth expectations match
4. Potential red flags or concerns
5. Strengths that would make them thrive

Return ONLY a JSON object with:

{{
    "match_score": 0-100 (integer, where 100 is perfect fit),
    "match_reasoning": "2-3 paragraph explanation of why this score",
    "culture_fit_breakdown": {{
        "collaboration_fit": {{
            "score": 0-100,
            "reasoning": "brief explanation"
        }},
        "pace_fit": {{
            "score": 0-100,
            "reasoning": "brief explanation"
        }},
        "values_alignment": {{
            "score": 0-100,
            "reasoning": "brief explanation"
        }},
        "growth_fit": {{
            "score": 0-100,
            "reasoning": "brief explanation"
        }},
        "work_style_fit": {{
            "score": 0-100,
            "reasoning": "brief explanation"
        }}
    }},
    "strengths": ["list of candidate strengths for this role/culture"],
    "concerns": ["list of potential concerns or misalignments"],
    "interview_suggestions": ["questions to explore in follow-up interviews"]
}}

Return ONLY the JSON object, no other text."""


class CandidateMatcher:
    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.5-flash-lite",
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

    async def match_candidate(
        self,
        culture_profile: dict[str, Any],
        candidate_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Match a candidate against a company's culture profile."""
        prompt = MATCHING_PROMPT.format(
            culture_profile=json.dumps(culture_profile, indent=2),
            candidate_profile=json.dumps(candidate_profile, indent=2),
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
        )

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
            print(f"[CandidateMatcher] Failed to parse JSON: {e}")
            return {
                "match_score": 50,
                "match_reasoning": "Unable to fully analyze match",
                "raw_response": text,
            }
