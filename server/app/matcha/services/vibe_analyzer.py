"""
Vibe Check Sentiment Analyzer

Real-time AI sentiment analysis for employee vibe check submissions.
"""
import json
from typing import Optional
from google import genai


class VibeAnalyzer:
    """Real-time sentiment analysis for vibe checks using Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-2.0-flash-exp",
    ):
        """
        Initialize the VibeAnalyzer.

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

    async def analyze_sentiment(self, comment: str) -> Optional[dict]:
        """
        Analyze sentiment in real-time using Gemini.

        Args:
            comment: Employee's vibe check comment

        Returns:
            dict with keys:
            - sentiment_score: float from -1.0 (very negative) to 1.0 (very positive)
            - themes: list of 1-3 main themes (e.g., "workload", "team dynamics")
            - key_phrases: list of 1-2 most important phrases from the comment
        """
        if not comment or len(comment.strip()) < 5:
            return None

        prompt = f"""Analyze this employee vibe check comment for sentiment.

Comment: "{comment}"

Return ONLY a JSON object with this exact structure:
{{
    "sentiment_score": <number from -1.0 (very negative) to 1.0 (very positive)>,
    "themes": [<list of 1-3 main themes, e.g. "workload", "team dynamics", "recognition">],
    "key_phrases": [<1-2 most important phrases from the comment>]
}}

Focus on:
- Overall emotional tone (sentiment_score)
- Main topics/concerns mentioned (themes)
- Most significant statements (key_phrases)

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
            if not all(k in result for k in ["sentiment_score", "themes", "key_phrases"]):
                print(f"[VibeAnalyzer] Missing required keys in response: {result}")
                return None

            # Clamp sentiment_score to [-1.0, 1.0]
            result["sentiment_score"] = max(-1.0, min(1.0, float(result["sentiment_score"])))

            return result

        except json.JSONDecodeError as e:
            print(f"[VibeAnalyzer] Failed to parse JSON: {e}")
            print(f"[VibeAnalyzer] Raw response: {text}")
            return None
        except Exception as e:
            print(f"[VibeAnalyzer] Error analyzing sentiment: {e}")
            return None
