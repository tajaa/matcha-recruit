"""
Performance Review AI Analyzer

AI analysis for comparing self-assessments with manager reviews.
"""
import json
from typing import Optional, Any
from google import genai


class ReviewAnalyzer:
    """AI analysis for performance reviews using Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.0-flash-exp",
    ):
        """
        Initialize the ReviewAnalyzer.

        Args:
            api_key: Google API key for Gemini
            vertex_project: Google Cloud project ID for Vertex AI
            vertex_location: Vertex AI location
            model: Gemini model to use
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

    async def analyze_review_alignment(
        self,
        self_ratings: dict[str, Any],
        manager_ratings: dict[str, Any],
        template_categories: list[dict[str, Any]],
        self_comments: Optional[str] = None,
        manager_comments: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Compare self vs manager assessment with AI insights.

        Args:
            self_ratings: Employee's self-ratings {category_name: rating}
            manager_ratings: Manager's ratings {category_name: rating}
            template_categories: Review template structure
            self_comments: Optional employee comments
            manager_comments: Optional manager comments

        Returns:
            dict with keys:
            - alignment_score: 0-1, how closely they agree
            - areas_of_agreement: categories where ratings are close
            - discrepancies: list of dicts with analysis of gaps
            - strengths: identified strengths
            - development_areas: areas for improvement
        """
        prompt = f"""Analyze alignment between employee self-assessment and manager review.

Template categories: {json.dumps(template_categories, indent=2)}

Self-ratings: {json.dumps(self_ratings, indent=2)}
Manager ratings: {json.dumps(manager_ratings, indent=2)}

{f'Self comments: "{self_comments}"' if self_comments else ''}
{f'Manager comments: "{manager_comments}"' if manager_comments else ''}

Return ONLY a JSON object:
{{
    "alignment_score": <0-1, how closely self and manager agree overall>,
    "areas_of_agreement": [<list of category names where ratings are within 0.5 points>],
    "discrepancies": [
        {{
            "category": "...",
            "self_rating": X,
            "manager_rating": Y,
            "gap": <difference>,
            "analysis": "Possible reasons for the gap..."
        }}
    ],
    "strengths": [<identified strengths from both perspectives>],
    "development_areas": [<areas for improvement>],
    "overall_insight": "2-3 sentence summary of the review alignment"
}}

Focus on:
- Calculating alignment_score based on rating differences
- Highlighting where self and manager agree (areas_of_agreement)
- Analyzing significant gaps (discrepancies with gap > 1.0)
- Extracting key strengths and development areas
- Providing actionable insights

Return ONLY the JSON, no other text."""

        try:
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

            result = json.loads(text)

            # Validate structure
            required_keys = [
                "alignment_score",
                "areas_of_agreement",
                "discrepancies",
                "strengths",
                "development_areas",
            ]
            if not all(k in result for k in required_keys):
                print(f"[ReviewAnalyzer] Missing required keys in response: {result}")
                return None

            # Clamp alignment_score to [0.0, 1.0]
            result["alignment_score"] = max(0.0, min(1.0, float(result["alignment_score"])))

            return result

        except json.JSONDecodeError as e:
            print(f"[ReviewAnalyzer] Failed to parse JSON: {e}")
            print(f"[ReviewAnalyzer] Raw response: {text}")
            return None
        except Exception as e:
            print(f"[ReviewAnalyzer] Error analyzing review alignment: {e}")
            return None
