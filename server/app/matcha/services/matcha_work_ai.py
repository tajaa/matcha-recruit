import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Any

from google import genai
from google.genai import types

from ...config import get_settings
from ..models.matcha_work import OfferLetterDocument, ReviewDocument

logger = logging.getLogger(__name__)

GEMINI_CALL_TIMEOUT = 60

OFFER_LETTER_FIELDS = list(OfferLetterDocument.model_fields.keys())
REVIEW_FIELDS = list(ReviewDocument.model_fields.keys())

OFFER_LETTER_SYSTEM_PROMPT_TEMPLATE = """You are an offer letter assistant. Help the user create and refine a professional job offer letter.

Current document state (JSON):
{current_state}

Your job:
1. Understand what the user wants to add, change, or clarify about the offer letter.
2. Extract any structured field updates from the user's message.
3. Reply conversationally, confirming changes and asking for any missing required information.

Respond ONLY with valid JSON in this exact format:
{{
  "reply": "Your conversational response to the user",
  "updates": {{
    "field_name": "value"
  }}
}}

Rules:
- Only include fields in "updates" that should actually be changed based on the user's message
- If no fields should be updated, use an empty object: "updates": {{}}
- Always include both "reply" and "updates" keys
- Valid field names: {valid_fields}
- For dates, use ISO format (YYYY-MM-DD) or a human-readable format like "March 1, 2026"
- For salary, use a descriptive string like "$180,000/year" or "$90/hour"
- Return only the JSON object — no markdown fences, no extra text
"""

REVIEW_SYSTEM_PROMPT_TEMPLATE = """You are an anonymized performance review assistant. Help the user draft a one-off anonymous review.

Current review state (JSON):
{current_state}

Your job:
1. Understand what the user wants to add, change, or clarify in the anonymous review.
2. Extract structured review updates from the user's message.
3. Reply conversationally, confirming changes and suggesting any missing details.

Respond ONLY with valid JSON in this exact format:
{{
  "reply": "Your conversational response to the user",
  "updates": {{
    "field_name": "value"
  }}
}}

Rules:
- Only include fields in "updates" that should actually be changed
- If no fields should be updated, use an empty object: "updates": {{}}
- Always include both "reply" and "updates" keys
- Valid field names: {valid_fields}
- Keep all output professional and anonymized by default
- For overall_rating use an integer from 1-5
- If recipient_emails is empty or missing, ask the user to provide the email addresses to request feedback from
- When the user provides one or more emails, set recipient_emails as a JSON array of normalized email strings
- Do not invent or infer recipient emails that the user did not provide
- Return only the JSON object — no markdown fences, no extra text
"""


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences from model output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


@dataclass
class AIResponse:
    assistant_reply: str
    structured_update: dict | None = field(default=None)
    token_usage: dict | None = field(default=None)


class MatchaWorkAIProvider:
    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        task_type: str = "offer_letter",
    ) -> AIResponse:
        raise NotImplementedError


class GeminiProvider(MatchaWorkAIProvider):
    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
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

    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        task_type: str = "offer_letter",
    ) -> AIResponse:
        system_prompt, contents, valid_fields = self._build_prompt_and_contents(
            messages, current_state, task_type=task_type
        )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._call_gemini, system_prompt, contents, valid_fields),
                timeout=GEMINI_CALL_TIMEOUT,
            )
            return response
        except asyncio.TimeoutError:
            logger.error("Gemini call timed out after %s seconds", GEMINI_CALL_TIMEOUT)
            return AIResponse(
                assistant_reply="I'm taking too long to respond. Please try again.",
                structured_update=None,
            )
        except Exception as e:
            logger.error("Gemini call failed: %s", e, exc_info=True)
            return AIResponse(
                assistant_reply="I encountered an error processing your request. Please try again.",
                structured_update=None,
            )

    def _call_gemini(self, system_prompt: str, contents: list, valid_fields: list[str]) -> AIResponse:
        model = self.settings.analysis_model
        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        raw_text = response.text or ""
        raw_text = _clean_json_text(raw_text)

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse Gemini JSON response: %s | Raw: %s",
                e,
                raw_text[:300],
            )
            return AIResponse(
                assistant_reply=raw_text or "I processed your request.",
                structured_update=None,
            )

        reply = parsed.get("reply", "Done.")
        updates = parsed.get("updates", {})

        if isinstance(updates, dict):
            allowed = set(valid_fields)
            updates = {k: v for k, v in updates.items() if k in allowed}
        else:
            updates = {}

        return AIResponse(
            assistant_reply=reply,
            structured_update=updates if updates else None,
            token_usage=self._extract_usage_metadata(response, model),
        )

    def estimate_usage(
        self,
        messages: list[dict],
        current_state: dict,
        task_type: str = "offer_letter",
    ) -> dict:
        system_prompt, _, _ = self._build_prompt_and_contents(
            messages, current_state, task_type=task_type
        )
        windowed = messages[-20:]
        char_count = len(system_prompt) + sum(len(str(msg.get("content", ""))) for msg in windowed)
        prompt_tokens = max(1, char_count // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": None,
            "total_tokens": prompt_tokens,
            "estimated": True,
            "model": self.settings.analysis_model,
        }

    def _build_prompt_and_contents(
        self,
        messages: list[dict],
        current_state: dict,
        task_type: str = "offer_letter",
    ) -> tuple[str, list, list[str]]:
        windowed = messages[-20:]
        normalized_task_type = "review" if task_type == "review" else "offer_letter"
        if normalized_task_type == "review":
            valid_fields = REVIEW_FIELDS
            system_prompt = REVIEW_SYSTEM_PROMPT_TEMPLATE.format(
                current_state=json.dumps(current_state, indent=2, default=str),
                valid_fields=", ".join(valid_fields),
            )
        else:
            valid_fields = OFFER_LETTER_FIELDS
            system_prompt = OFFER_LETTER_SYSTEM_PROMPT_TEMPLATE.format(
                current_state=json.dumps(current_state, indent=2, default=str),
                valid_fields=", ".join(valid_fields),
            )

        contents = []
        for msg in windowed:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])],
                )
            )
        return system_prompt, contents, valid_fields

    def _extract_usage_metadata(self, response: Any, model: str) -> Optional[dict]:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None

        def _get(*keys: str) -> Optional[Any]:
            for key in keys:
                value = getattr(usage, key, None)
                if value is None and isinstance(usage, dict):
                    value = usage.get(key)
                if value is not None:
                    return value
            return None

        def _to_int(value: Any) -> Optional[int]:
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        prompt_tokens = _to_int(_get("prompt_token_count", "input_token_count", "promptTokenCount"))
        completion_tokens = _to_int(
            _get("candidates_token_count", "output_token_count", "candidatesTokenCount")
        )
        total_tokens = _to_int(_get("total_token_count", "totalTokenCount"))
        if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated": False,
            "model": model,
        }


_provider: Optional[GeminiProvider] = None


def get_ai_provider() -> GeminiProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider
