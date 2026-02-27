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
from ...core.services.platform_settings import get_matcha_work_model_mode
from ..models.matcha_work import OfferLetterDocument, OnboardingDocument, ReviewDocument, WorkbookDocument

logger = logging.getLogger(__name__)

GEMINI_CALL_TIMEOUT = 120

OFFER_LETTER_FIELDS = list(OfferLetterDocument.model_fields.keys())
REVIEW_FIELDS = list(ReviewDocument.model_fields.keys())
WORKBOOK_FIELDS = list(WorkbookDocument.model_fields.keys())
ONBOARDING_FIELDS = list(OnboardingDocument.model_fields.keys())

SUPPORTED_AI_MODES = {"skill", "general", "clarify", "refuse"}
SUPPORTED_AI_SKILLS = {"chat", "offer_letter", "review", "workbook", "onboarding", "none"}
SUPPORTED_AI_OPERATIONS = {
    "create",
    "update",
    "save_draft",
    "send_draft",
    "finalize",
    "send_requests",
    "track",
    "create_employees",
    "generate_presentation",
    "none",
}

MATCHA_WORK_SYSTEM_PROMPT_TEMPLATE = """You are Matcha Work, an HR copilot for US employers.

Mission:
1) Provide high-quality general HR guidance for US teams.
2) Detect and execute supported Matcha Work skills from natural language.
3) Ask concise clarifying questions when required inputs are missing.
4) Never block normal Q&A just because no skill is invoked.

Current thread context:
- current_skill (inferred from state): {current_skill}
- current_state (JSON): {current_state}
- valid_update_fields: {valid_fields}

Supported skills:
- offer_letter: create/update offer letter content, save_draft, send_draft, finalize
- review: create/update anonymized review content, collect recipient_emails, send review requests, track responses
- workbook: create/update HR workbook documents and section content, generate_presentation
- onboarding: collect employee details and create employee records with automatic provisioning.
  Required per employee: first_name, last_name, work_email.
  Optional per employee: personal_email, work_state, employment_type, start_date, address.
  The "employees" field is a JSON array of employee objects.
  Set batch_status to "collecting" while gathering info, "ready" when user confirms the list.
  Use create_employees operation ONLY when user explicitly confirms the employee list is ready.
  Always collect ALL employees before creating. Do not create one at a time unless asked.

Mode selection:
- mode=skill when user clearly asks for a supported action.
- mode=general for informational/advisory HR questions.
- mode=clarify when action is requested but required details are missing.
- mode=refuse only for unsafe/disallowed or unsupported actions.

US HR policy:
- Default to US federal baseline.
- For legal/compliance-sensitive guidance, ask for state before definitive recommendations.
- For high-risk topics (termination, discrimination, wage-hour classification, leave, investigations):
  - surface uncertainty if facts are missing
  - provide practical next steps
  - include a short "not legal advice" caution
- Do not fabricate statutes, agencies, case law, or deadlines.

Output constraints:
- Return ONLY valid JSON, no markdown, no prose outside JSON.
- JSON format:
{{
  "mode": "skill|general|clarify|refuse",
  "skill": "offer_letter|review|workbook|onboarding|none",
  "operation": "create|update|save_draft|send_draft|finalize|send_requests|track|create_employees|generate_presentation|none",
  "confidence": 0.0,
  "updates": {{}},
  "missing_fields": [],
  "reply": ""
}}
- "updates" may include only keys from valid_update_fields.
- If no state changes are needed, set "updates": {{}}.
- If mode != skill, use "operation": "none" unless a clarify step for skill action is needed.
- recipient_emails must be lowercase email strings in an array.
- For offer_letter send_draft, include recipient_emails (or candidate_email) when the target email is provided.
- overall_rating must be an integer 1-5.
- For workbook "sections", ALWAYS return the full sections list (not a partial patch).
- start_date and expiration_date must be ISO 8601 strings (YYYY-MM-DD). Always capture dates mentioned by the user.
- company_logo_url must NOT be set by AI — it is managed via file upload only.
"""


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences from model output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _infer_skill_from_state(current_state: dict) -> str:
    """Infer the active skill from current_state contents."""
    if not current_state:
        return "chat"
    if any(k in current_state for k in ("candidate_name", "position_title", "salary", "salary_range_min")):
        return "offer_letter"
    if any(k in current_state for k in ("overall_rating", "review_title", "review_request_statuses", "review_expected_responses")):
        return "review"
    if "sections" in current_state or "workbook_title" in current_state:
        return "workbook"
    if any(k in current_state for k in ("employees", "batch_status")):
        return "onboarding"
    return "chat"


async def _get_model(settings) -> str:
    mode = await get_matcha_work_model_mode()
    if mode == "heavy":
        return "gemini-3.1-pro-preview"
    return settings.analysis_model


@dataclass
class AIResponse:
    assistant_reply: str
    structured_update: dict | None = field(default=None)
    mode: str = "general"
    skill: str = "none"
    operation: str = "none"
    confidence: float = 0.0
    missing_fields: list[str] = field(default_factory=list)
    token_usage: dict | None = field(default=None)


class MatchaWorkAIProvider:
    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
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
    ) -> AIResponse:
        system_prompt, contents, valid_fields, inferred_skill = self._build_prompt_and_contents(
            messages, current_state
        )
        model = await _get_model(self.settings)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_gemini,
                    system_prompt,
                    contents,
                    valid_fields,
                    model,
                    inferred_skill,
                ),
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

    def _call_gemini(
        self,
        system_prompt: str,
        contents: list,
        valid_fields: list[str],
        model: str,
        inferred_skill: str,
    ) -> AIResponse:
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
                mode="general",
                skill="none",
                operation="none",
            )

        reply = parsed.get("reply", "Done.")
        raw_updates = parsed.get("updates", {})
        if isinstance(raw_updates, dict):
            allowed = set(valid_fields)
            updates = {k: v for k, v in raw_updates.items() if k in allowed}
        else:
            updates = {}

        raw_mode = str(parsed.get("mode") or "").strip().lower()
        mode = raw_mode if raw_mode in SUPPORTED_AI_MODES else ""

        # Backward compatibility with older reply/updates-only JSON.
        if not mode:
            mode = "skill" if updates else "general"

        raw_skill = str(parsed.get("skill") or "").strip().lower()
        skill = raw_skill if raw_skill in SUPPORTED_AI_SKILLS else ""
        if not skill:
            skill = inferred_skill if mode == "skill" else "none"

        raw_operation = str(parsed.get("operation") or "").strip().lower()
        operation = raw_operation if raw_operation in SUPPORTED_AI_OPERATIONS else ""
        if not operation:
            if mode == "skill":
                operation = "update" if updates else "track"
            else:
                operation = "none"

        raw_confidence = parsed.get("confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.8 if mode == "skill" else 0.5
        confidence = max(0.0, min(1.0, confidence))

        raw_missing_fields = parsed.get("missing_fields", [])
        if isinstance(raw_missing_fields, list):
            missing_fields = [str(item).strip() for item in raw_missing_fields if str(item).strip()]
        else:
            missing_fields = []

        return AIResponse(
            assistant_reply=reply,
            structured_update=updates if updates else None,
            mode=mode,
            skill=skill,
            operation=operation,
            confidence=confidence,
            missing_fields=missing_fields,
            token_usage=self._extract_usage_metadata(response, model),
        )

    async def estimate_usage(
        self,
        messages: list[dict],
        current_state: dict,
    ) -> dict:
        system_prompt, _, _, _ = self._build_prompt_and_contents(
            messages, current_state
        )
        model = await _get_model(self.settings)
        windowed = messages[-20:]
        char_count = len(system_prompt) + sum(len(str(msg.get("content", ""))) for msg in windowed)
        prompt_tokens = max(1, char_count // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": None,
            "total_tokens": prompt_tokens,
            "estimated": True,
            "model": model,
        }

    def _build_prompt_and_contents(
        self,
        messages: list[dict],
        current_state: dict,
    ) -> tuple[str, list, list[str], str]:
        windowed = messages[-20:]
        current_skill = _infer_skill_from_state(current_state)
        if current_skill == "offer_letter":
            valid_fields = OFFER_LETTER_FIELDS
        elif current_skill == "review":
            valid_fields = REVIEW_FIELDS
        elif current_skill == "workbook":
            valid_fields = WORKBOOK_FIELDS
        elif current_skill == "onboarding":
            valid_fields = ONBOARDING_FIELDS
        else:
            valid_fields = []

        system_prompt = MATCHA_WORK_SYSTEM_PROMPT_TEMPLATE.format(
            current_skill=current_skill,
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
        return system_prompt, contents, valid_fields, current_skill

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
