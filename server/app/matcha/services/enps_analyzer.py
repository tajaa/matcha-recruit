"""
eNPS Survey Theme Analyzer

Real-time AI theme extraction for eNPS survey responses.
"""
import json
from typing import Optional
from google import genai


class ENPSAnalyzer:
    """Real-time theme extraction for eNPS responses using Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.0-flash-exp",
    ):
        """
        Initialize the ENPSAnalyzer.

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

    async def extract_themes_from_reason(
        self, reason: str, score: int, category: str
    ) -> Optional[dict]:
        """
        Extract themes from a single eNPS response reason.

        Args:
            reason: Employee's explanation for their NPS score
            score: NPS score (0-10)
            category: NPS category (detractor, passive, promoter)

        Returns:
            dict with keys:
            - themes: list of 1-3 main themes
            - sentiment_score: float from -1.0 to 1.0
            - key_phrases: list of important quotes
        """
        if not reason or len(reason.strip()) < 10:
            return None

        prompt = f"""Extract key themes from this employee feedback.

Score: {score}/10 (Category: {category})
Reason: "{reason}"

Return ONLY a JSON object:
{{
    "themes": [<1-3 main themes like "compensation", "work-life balance", "career growth", "management", "culture">],
    "sentiment_score": <-1.0 to 1.0>,
    "key_phrases": [<1-2 most important quotes from the reason>]
}}

Focus on:
- What specific aspects they mention (themes)
- Overall tone (sentiment_score)
- Most revealing statements (key_phrases)

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
            if not all(k in result for k in ["themes", "sentiment_score", "key_phrases"]):
                print(f"[ENPSAnalyzer] Missing required keys in response: {result}")
                return None

            # Clamp sentiment_score to [-1.0, 1.0]
            result["sentiment_score"] = max(-1.0, min(1.0, float(result["sentiment_score"])))

            return result

        except json.JSONDecodeError as e:
            print(f"[ENPSAnalyzer] Failed to parse JSON: {e}")
            print(f"[ENPSAnalyzer] Raw response: {text}")
            return None
        except Exception as e:
            print(f"[ENPSAnalyzer] Error extracting themes: {e}")
            return None
