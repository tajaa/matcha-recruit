import json
from typing import Optional, Any

from google import genai


POSITION_MATCHING_PROMPT = """You are evaluating how well a candidate matches a specific job position and company culture.

POSITION DETAILS:
{position_data}

CANDIDATE PROFILE:
{candidate_data}

COMPANY CULTURE PROFILE (if available):
{culture_profile}

Analyze the match comprehensively. Consider:
1. SKILLS MATCH: How well do the candidate's skills match required and preferred skills?
2. EXPERIENCE MATCH: Does their experience level and background fit the role?
3. CULTURE FIT: Would they thrive in this company's culture? (If no culture profile, score 70 as neutral)

Return ONLY a JSON object with:

{{
    "overall_score": 0-100 (weighted: 40% skills, 30% experience, 30% culture),
    "skills_match": {{
        "score": 0-100,
        "matched_required": ["skills from required list that candidate has"],
        "missing_required": ["required skills candidate lacks"],
        "matched_preferred": ["preferred skills candidate has"],
        "reasoning": "brief explanation of skills match"
    }},
    "experience_match": {{
        "score": 0-100,
        "candidate_level": "detected experience level (entry/mid/senior/lead/executive)",
        "required_level": "position requirement",
        "years_relevant": "estimated years of relevant experience",
        "reasoning": "brief explanation of experience fit"
    }},
    "culture_fit": {{
        "score": 0-100,
        "reasoning": "brief explanation of culture fit",
        "strengths": ["cultural fit strengths"],
        "concerns": ["potential cultural misalignments"]
    }},
    "overall_reasoning": "2-3 paragraph summary explaining the overall match and key considerations",
    "interview_focus_areas": ["specific areas to explore in an interview with this candidate"]
}}

Return ONLY the JSON object, no other text."""


class PositionMatcher:
    """Matches candidates to specific positions considering skills, experience, and culture."""

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

    def _prepare_position_data(self, position: dict[str, Any]) -> dict[str, Any]:
        """Prepare position data for the prompt."""
        return {
            "title": position.get("title"),
            "department": position.get("department"),
            "location": position.get("location"),
            "remote_policy": position.get("remote_policy"),
            "employment_type": position.get("employment_type"),
            "experience_level": position.get("experience_level"),
            "salary_range": f"${position.get('salary_min', 'N/A')} - ${position.get('salary_max', 'N/A')} {position.get('salary_currency', 'USD')}"
            if position.get("salary_min") or position.get("salary_max")
            else "Not specified",
            "required_skills": position.get("required_skills", []),
            "preferred_skills": position.get("preferred_skills", []),
            "requirements": position.get("requirements", []),
            "responsibilities": position.get("responsibilities", []),
            "benefits": position.get("benefits", []),
            "visa_sponsorship": position.get("visa_sponsorship", False),
        }

    def _prepare_candidate_data(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Prepare candidate data for the prompt."""
        parsed_data = candidate.get("parsed_data", {}) or {}
        return {
            "name": candidate.get("name"),
            "skills": candidate.get("skills", []) or parsed_data.get("skills", []),
            "experience_years": candidate.get("experience_years")
            or parsed_data.get("experience_years"),
            "education": candidate.get("education", [])
            or parsed_data.get("education", []),
            "work_history": parsed_data.get("work_history", []),
            "summary": parsed_data.get("summary"),
            "inferred_culture_preferences": parsed_data.get(
                "inferred_culture_preferences", {}
            ),
        }

    async def match_candidate_to_position(
        self,
        position: dict[str, Any],
        candidate: dict[str, Any],
        culture_profile: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Match a candidate to a position.

        Args:
            position: Position data from database
            candidate: Candidate data from database
            culture_profile: Optional company culture profile

        Returns:
            Match result with overall_score, skills_match, experience_match, culture_fit
        """
        position_data = self._prepare_position_data(position)
        candidate_data = self._prepare_candidate_data(candidate)

        culture_str = (
            json.dumps(culture_profile, indent=2)
            if culture_profile
            else "No culture profile available - use neutral score of 70 for culture fit"
        )

        prompt = POSITION_MATCHING_PROMPT.format(
            position_data=json.dumps(position_data, indent=2),
            candidate_data=json.dumps(candidate_data, indent=2),
            culture_profile=culture_str,
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
            result = json.loads(text)
            # Ensure all required fields exist
            return {
                "overall_score": result.get("overall_score", 50),
                "skills_match_score": result.get("skills_match", {}).get("score", 50),
                "experience_match_score": result.get("experience_match", {}).get(
                    "score", 50
                ),
                "culture_fit_score": result.get("culture_fit", {}).get("score", 70),
                "match_reasoning": result.get("overall_reasoning", ""),
                "skills_breakdown": result.get("skills_match"),
                "experience_breakdown": result.get("experience_match"),
                "culture_fit_breakdown": result.get("culture_fit"),
                "interview_focus_areas": result.get("interview_focus_areas", []),
            }
        except json.JSONDecodeError as e:
            print(f"[PositionMatcher] Failed to parse JSON: {e}")
            return {
                "overall_score": 50,
                "skills_match_score": 50,
                "experience_match_score": 50,
                "culture_fit_score": 70,
                "match_reasoning": "Unable to fully analyze match",
                "skills_breakdown": None,
                "experience_breakdown": None,
                "culture_fit_breakdown": None,
                "raw_response": text,
            }
