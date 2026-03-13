"""Investigation interview question generation service.

Generates role-specific questions for IR investigation interviews using Gemini AI.
"""

import json
import logging
from typing import Optional, Any

from google import genai

logger = logging.getLogger(__name__)

FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")


QUESTION_GENERATION_PROMPT = """You are an expert workplace investigator. Generate questions for an investigation interview.

INCIDENT SUMMARY:
{incident_summary}

INTERVIEWEE: {interviewee_name}
ROLE IN INVESTIGATION: {interviewee_role}

{prior_context}

Generate 8-12 targeted investigation questions. Each question should have:
- question: The actual question to ask
- category: One of "foundational", "temporal", "observational", "behavioral", "follow_up"
- rationale: Why this question matters for the investigation

ROLE-SPECIFIC GUIDANCE:
- complainant: Focus on their direct experience, timeline of events, impact, any witnesses, prior reporting attempts
- respondent: Focus on their version of events, context, relationship with complainant, awareness of policies
- witness: Focus on what they directly observed, when, environmental details, any other witnesses

RULES:
- Questions must be open-ended and non-leading
- Do not suggest answers within questions
- Do not reference other witness statements
- Include timeline-establishing questions
- Include questions about documentary evidence (emails, messages, etc.)
- Progress from general to specific

Return ONLY a JSON array:
[
    {{
        "question": "...",
        "category": "foundational|temporal|observational|behavioral|follow_up",
        "rationale": "..."
    }}
]
"""


async def generate_investigation_questions(
    incident: dict[str, Any],
    interviewee_name: str,
    interviewee_role: str,
    prior_transcripts: Optional[list[str]] = None,
    api_key: Optional[str] = None,
    vertex_project: Optional[str] = None,
    vertex_location: str = "us-central1",
    model: str = "gemini-2.5-flash",
) -> list[dict[str, Any]]:
    """Generate investigation questions for an interviewee.

    Args:
        incident: Dict with incident data (title, description, incident_type, etc.)
        interviewee_name: Name of the person being interviewed
        interviewee_role: Role in investigation (complainant, respondent, witness)
        prior_transcripts: Optional list of transcript texts from prior interviews
        api_key: Gemini API key
        vertex_project: Vertex AI project ID
        vertex_location: Vertex AI location
        model: Gemini model to use

    Returns:
        List of question dicts with question, category, rationale
    """
    # Prefer GEMINI_API_KEY (direct API) over Vertex AI — matches compliance service pattern
    import os
    direct_api_key = os.getenv("GEMINI_API_KEY")
    if direct_api_key:
        client = genai.Client(api_key=direct_api_key)
    elif api_key:
        client = genai.Client(api_key=api_key)
    elif vertex_project:
        client = genai.Client(
            vertexai=True,
            project=vertex_project,
            location=vertex_location,
        )
    else:
        raise ValueError("Either api_key or vertex_project must be provided")

    incident_summary = (
        f"Title: {incident.get('title', 'N/A')}\n"
        f"Type: {incident.get('incident_type', 'N/A')}\n"
        f"Severity: {incident.get('severity', 'N/A')}\n"
        f"Description: {incident.get('description', 'N/A')}\n"
        f"Location: {incident.get('location', 'N/A')}\n"
        f"Occurred at: {incident.get('occurred_at', 'N/A')}"
    )

    prior_context = ""
    if prior_transcripts:
        prior_context = (
            "PRIOR INTERVIEW TRANSCRIPTS (avoid re-asking answered questions, probe gaps):\n"
            + "\n---\n".join(prior_transcripts[:3])  # Limit to 3 transcripts
        )

    prompt = QUESTION_GENERATION_PROMPT.format(
        incident_summary=incident_summary,
        interviewee_name=interviewee_name,
        interviewee_role=interviewee_role,
        prior_context=prior_context,
    )

    candidates = [model] + [m for m in FALLBACK_MODELS if m != model]
    response = None
    for candidate in candidates:
        try:
            response = await client.aio.models.generate_content(
                model=candidate,
                contents=prompt,
            )
            break
        except Exception as exc:
            if "404" in str(exc) or "NOT_FOUND" in str(exc):
                logger.warning("Model %s unavailable, trying next: %s", candidate, exc)
                continue
            raise
    if response is None:
        raise RuntimeError(f"All models unavailable: {candidates}")

    text = response.text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        questions = json.loads(text)
        if isinstance(questions, list):
            return questions
        return []
    except json.JSONDecodeError:
        print(f"[IRQuestions] Failed to parse questions JSON: {text[:200]}")
        return []
