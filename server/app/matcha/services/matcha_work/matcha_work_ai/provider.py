"""The AI provider -- the abstract MatchaWorkAIProvider interface and the
GeminiProvider implementation (context caching, generate, the Gemini call,
prompt+contents assembly, usage extraction), plus the get_ai_provider getter.

Owns the package's module-level mutable state: the TTL+LRU context-cache
registry, the set of models known not to support caching, and the provider
singleton. They live here rather than in __init__ so the objects that mutate
them and the objects themselves are in one file.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Any
from google import genai
from app.core.services.genai_client import get_genai_client
from google.genai import types
from app.config import get_settings

from ._fields import BLOG_FIELDS, HANDBOOK_FIELDS, HR_PILOT_FIELDS, OFFER_LETTER_FIELDS, ONBOARDING_FIELDS, POLICY_FIELDS, PRESENTATION_FIELDS, PROJECT_FIELDS, REVIEW_FIELDS, SUPPORTED_AI_MODES, SUPPORTED_AI_OPERATIONS, SUPPORTED_AI_SKILLS, WORKBOOK_FIELDS
from ._models import FLASH_LITE, _get_model, classify_thinking_level, resolve_turn_model
from ._prompts import MATCHA_WORK_BLOG_DYNAMIC_PROMPT, MATCHA_WORK_BLOG_STATIC_PROMPT, MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE, MATCHA_WORK_STATIC_PROMPT_TEMPLATE
from ._text import _clean_json_text, _extract_reply_field, _infer_skill_from_state
from cachetools import TTLCache

logger = logging.getLogger(__name__)


# Google Search grounding tool — used only for payer mode (real-world coverage data).
# NOT used in general chat: grounding adds 5-15s latency per query.
_GOOGLE_SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())


GEMINI_CALL_TIMEOUT = 120


_CACHE_TTL_SECONDS = 3600  # 1 hour — must match Gemini's cache TTL


_CACHE_REGISTRY_MAX = 2000


_cache_registry: TTLCache = TTLCache(maxsize=_CACHE_REGISTRY_MAX, ttl=_CACHE_TTL_SECONDS)


# Serializes cache creation — runs inside asyncio.to_thread, so a threading
# lock (not asyncio) is correct. Without it, concurrent first-messages for one
# company each create a Gemini cache; the losers leak until TTL.
_cache_creation_lock = threading.Lock()


_cache_unsupported_models: set[str] = set()  # models that don't support caching — skip silently


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
    compliance_reasoning: list[dict] | None = field(default=None)
    referenced_categories: list[str] | None = field(default=None)
    referenced_locations: list[str] | None = field(default=None)
    attachments: list[dict] | None = field(default=None)


class MatchaWorkAIProvider:
    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        context_summary: Optional[str] = None,
        payer_mode_prompt: Optional[str] = None,
        model_override: Optional[str] = None,
        company_id: str = "",
        user_id: str = "",
        compliance_mode: bool = False,
        payer_mode: bool = False,
        node_mode: bool = False,
        grounded_mode: bool = False,
        blog_mode_state: Optional[str] = None,
        thread_id: Optional[str] = None,
        dynamic_context: str = "",
        hr_pilot_mode: bool = False,
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
            self._client = get_genai_client(api_key=api_key or self.settings.gemini_api_key)
        return self._client

    def _get_or_create_cache(self, model: str, static_prompt: str, company_id: str = "") -> Optional[str]:
        """Get or create a Gemini cached content for the static system prompt.

        Returns cache name if successful, None if caching isn't supported or fails.
        Works with any model — silently skips models that don't support caching.
        TTLCache handles expiry + LRU eviction automatically.
        """
        if model in _cache_unsupported_models:
            return None

        prompt_hash = hashlib.md5(static_prompt.encode()).hexdigest()[:12]
        key = f"{company_id}:{prompt_hash}:{model}"

        cached = _cache_registry.get(key)
        if cached is not None:
            name, cached_model = cached
            if cached_model == model:
                return name

        with _cache_creation_lock:
            # Double-check under the lock — another thread may have created it.
            cached = _cache_registry.get(key)
            if cached is not None:
                name, cached_model = cached
                if cached_model == model:
                    return name
            return self._create_cache_locked(key, model, static_prompt, company_id)

    def _create_cache_locked(self, key: str, model: str, static_prompt: str, company_id: str) -> Optional[str]:
        try:
            new_cache = self.client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    system_instruction=static_prompt,
                    ttl=f"{_CACHE_TTL_SECONDS}s",
                ),
            )
            _cache_registry[key] = (new_cache.name, model)
            logger.info("[cache] Created Gemini cache %s for company=%s model=%s", new_cache.name, company_id, model)
            return new_cache.name
        except Exception as e:
            err_str = str(e).lower()
            if "not supported" in err_str or "not available" in err_str or "minimum" in err_str or "caching" in err_str:
                _cache_unsupported_models.add(model)
                logger.info("[cache] Model %s does not support caching, skipping future attempts", model)
            else:
                logger.warning("[cache] Failed to create Gemini cache: %s", e)
            return None

    async def generate(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        context_summary: Optional[str] = None,
        payer_mode_prompt: Optional[str] = None,
        model_override: Optional[str] = None,
        company_id: str = "",
        user_id: str = "",
        compliance_mode: bool = False,
        payer_mode: bool = False,
        node_mode: bool = False,
        grounded_mode: bool = False,
        blog_mode_state: Optional[str] = None,
        thread_id: Optional[str] = None,
        dynamic_context: str = "",
        hr_pilot_mode: bool = False,
    ) -> AIResponse:
        latest_user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        # Check if the user is requesting image/diagram generation
        is_image_request = False
        latest_user_msg_lower = latest_user_msg.lower()
        image_pattern = r"\b(generate|create|draw|make|sketch|illustrate|render)\b.*\b(image|picture|photo|illustration|sketch|diagram|flowchart|drawing)\b"
        if re.search(image_pattern, latest_user_msg_lower) or "image generation" in latest_user_msg_lower:
            is_image_request = True

        if is_image_request and not payer_mode_prompt:
            import os
            import secrets
            from uuid import UUID
            from google.genai import types as _genai_types
            from app.core.services.storage import get_storage
            from app.matcha.services.matcha_work.matcha_work_document import build_matcha_work_thread_storage_prefix

            # GA name — Google shut the preview model down 2026-06-25. Matches
            # core.services.image_gen.IMAGE_MODEL and matcha_work_document's
            # inline model= arg.
            _IMAGE_MODEL = "gemini-3.1-flash-image"

            def _call_imagen() -> Optional[tuple[bytes, str, str, Optional[dict]]]:
                try:
                    response = self.client.models.generate_content(
                        model=_IMAGE_MODEL,
                        contents=latest_user_msg,
                        config=_genai_types.GenerateContentConfig(
                            response_modalities=["IMAGE", "TEXT"],
                            image_config=_genai_types.ImageConfig(aspect_ratio="16:9"),
                        ),
                    )

                    image_data = None
                    mime = "image/png"
                    reply_text = ""

                    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if part.text:
                                reply_text += part.text
                            elif part.inline_data and part.inline_data.data:
                                image_data = part.inline_data.data
                                mime = part.inline_data.mime_type or "image/png"

                    if image_data:
                        usage = self._extract_usage_metadata(response, _IMAGE_MODEL)
                        return image_data, mime, reply_text, usage
                except Exception as e:
                    logger.warning("Gemini image generation call failed: %s", e)
                return None

            result = await asyncio.to_thread(_call_imagen)
            if result:
                image_bytes, mime_type, reply_text, image_usage = result
                ext = "png" if "png" in mime_type else "jpg"
                filename = f"image_{secrets.token_hex(8)}.{ext}"
                
                co_uuid = None
                th_uuid = None
                if company_id:
                    try:
                        co_uuid = UUID(company_id)
                    except Exception:
                        pass
                if thread_id:
                    try:
                        th_uuid = UUID(thread_id)
                    except Exception:
                        pass
                
                if co_uuid and th_uuid:
                    prefix = build_matcha_work_thread_storage_prefix(co_uuid, th_uuid, "images")
                else:
                    prefix = "matcha-work/temp-images"

                try:
                    url = await get_storage().upload_file(
                        image_bytes,
                        filename,
                        prefix=prefix,
                        content_type=mime_type,
                    )
                    if not reply_text:
                        reply_text = f"Here is the generated image for your request: \"{latest_user_msg}\""

                    attachments = [{
                        "url": url,
                        "kind": "image",
                        "filename": filename
                    }]
                    
                    # Real usage from the API when available; the hand-rolled
                    # estimate only backstops a missing usage_metadata.
                    token_usage = image_usage or {
                        "prompt_tokens": len(latest_user_msg.split()) * 2,
                        "completion_tokens": 1024,
                        "total_tokens": 1024 + len(latest_user_msg.split()) * 2,
                        "model": _IMAGE_MODEL,
                        "estimated": True,
                    }

                    return AIResponse(
                        assistant_reply=reply_text,
                        structured_update=None,
                        attachments=attachments,
                        token_usage=token_usage,
                    )
                except Exception as e:
                    logger.exception("Failed to upload generated image: %s", e)

        if payer_mode_prompt:
            # Payer mode: dedicated medical policy prompt, plain text response (no JSON)
            window_size = 15 if context_summary else 20
            windowed = messages[-window_size:]
            payer_contents = [
                types.Content(
                    role="model" if m["role"] == "assistant" else "user",
                    parts=[types.Part.from_text(text=m["content"])],
                )
                for m in windowed
                if m.get("content")
            ]
            full_prompt = payer_mode_prompt
            if context_summary:
                full_prompt += f"\n\nPrior conversation summary:\n{context_summary}"

            model = await _get_model(self.settings, model_override, company_id=company_id, user_id=user_id)
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.client.models.generate_content(
                            model=model,
                            contents=payer_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=full_prompt,
                                temperature=0.2,
                                tools=[_GOOGLE_SEARCH_TOOL],
                                # Payer coverage answers are the hardest turns
                                # in the system — clinical criteria + grounding.
                                thinking_config=types.ThinkingConfig(thinking_level="high"),
                            ),
                        )
                    ),
                    timeout=GEMINI_CALL_TIMEOUT,
                )
                reply = response.text or "I couldn't generate a response."
                # Real usage with the ACTUAL model — payer turns are Pro +
                # search grounding, the priciest combo; billing them from the
                # input-only flash estimate leaked ~all of their cost.
                return AIResponse(
                    assistant_reply=reply,
                    structured_update=None,
                    token_usage=self._extract_usage_metadata(response, model),
                )
            except Exception as e:
                logger.error("Payer mode Gemini call failed: %s", e, exc_info=True)
                return AIResponse(
                    assistant_reply="I encountered an error looking up payer policy data. Please try again.",
                    structured_update=None,
                )

        static_prompt, dynamic_prompt, contents, valid_fields, inferred_skill = self._build_prompt_and_contents(
            messages, current_state, company_context=company_context, slide_index=slide_index,
            context_summary=context_summary, blog_mode_state=blog_mode_state,
            dynamic_context=dynamic_context, hr_pilot_mode=hr_pilot_mode,
        )
        model = await _get_model(self.settings, model_override, company_id=company_id, user_id=user_id)

        # Auto-pick thinking level based on the latest user message + thread mode.
        latest_user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        thinking_level = classify_thinking_level(
            latest_user_msg,
            inferred_skill,
            compliance_mode=compliance_mode,
            payer_mode=payer_mode,
            node_mode=node_mode,
            grounded_mode=grounded_mode,
        )
        # Downgrade to flash-lite only for skill-less trivial turns — see
        # resolve_turn_model's docstring for why the skill check is required.
        model = resolve_turn_model(thinking_level, inferred_skill, model)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_gemini,
                    static_prompt,
                    dynamic_prompt,
                    contents,
                    valid_fields,
                    model,
                    inferred_skill,
                    company_id,
                    thinking_level,
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
        static_prompt: str,
        dynamic_prompt: str,
        contents: list,
        valid_fields: list[str],
        model: str,
        inferred_skill: str,
        company_id: str = "",
        thinking_level: str = "low",
    ) -> AIResponse:
        import time as _time
        # Try to cache the static prompt (instructions + company context)
        _tc0 = _time.monotonic()
        cache_name = self._get_or_create_cache(model, static_prompt, company_id)
        logger.info("[TIMING] cache lookup/create %.2fs (cache_name=%s)", _time.monotonic() - _tc0, cache_name)

        # Build thinking_config — "none" → budget=0 (disabled, fastest path)
        # on flash/pro; the 3.x generation dropped thinking_budget entirely
        # and 0 is a hard 400 INVALID_ARGUMENT on flash-lite, so a "none"
        # turn resolved to FLASH_LITE (see resolve_turn_model) uses the
        # thinking-off LEVEL instead. "low"/"high" always use a named level
        # so the model picks an appropriate budget.
        if thinking_level == "none":
            thinking_cfg = (
                types.ThinkingConfig(thinking_level="minimal") if model == FLASH_LITE
                else types.ThinkingConfig(thinking_budget=0)
            )
        else:
            thinking_cfg = types.ThinkingConfig(thinking_level=thinking_level)
        logger.info("[TIMING] thinking_level=%s skill=%s", thinking_level, inferred_skill)

        _tg0 = _time.monotonic()
        if cache_name:
            # Cached: static prompt is in the cache. Dynamic context goes as a
            # content prefix because Gemini doesn't allow system_instruction + cached_content together.
            cached_contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=f"[SYSTEM CONTEXT]\n{dynamic_prompt}")]),
                types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]),
                *contents,
            ]
            response = self.client.models.generate_content(
                model=model,
                contents=cached_contents,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2,
                    response_mime_type="application/json",
                    thinking_config=thinking_cfg,
                ),
            )
        else:
            # Fallback: send everything uncached via system_instruction
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=static_prompt + "\n\n" + dynamic_prompt,
                    temperature=0.2,
                    response_mime_type="application/json",
                    thinking_config=thinking_cfg,
                ),
            )
        logger.info("[TIMING] generate_content %.2fs", _time.monotonic() - _tg0)
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
            # Salvage: try to extract the `reply` field via regex so the user
            # at least sees the AI's text instead of the raw JSON envelope.
            salvaged_reply = _extract_reply_field(raw_text) or "I processed your request."
            return AIResponse(
                assistant_reply=salvaged_reply,
                structured_update=None,
                mode="general",
                skill="none",
                operation="none",
                token_usage=self._extract_usage_metadata(response, model),
            )

        # Gemini sometimes returns a list-wrapped response (e.g. [{...}]) even
        # though the prompt asks for an object. Try to unwrap or salvage.
        if isinstance(parsed, list):
            # Case 1: single-item list containing the expected response object
            if len(parsed) == 1 and isinstance(parsed[0], dict) and (
                "mode" in parsed[0] or "skill" in parsed[0] or "reply" in parsed[0]
            ):
                parsed = parsed[0]
            # Case 2: bare list of section-shaped dicts — treat as project_sections
            elif (
                inferred_skill == "project"
                and all(isinstance(item, dict) and ("title" in item or "content" in item) for item in parsed)
            ):
                logger.info("Salvaging bare section list as project_sections update")
                parsed = {
                    "mode": "skill",
                    "skill": "project",
                    "operation": "update",
                    "confidence": 0.8,
                    "updates": {"project_sections": parsed},
                    "reply": "I've drafted the posting sections. Review them in the panel on the right.",
                }
            else:
                logger.warning(
                    "Gemini returned list response, cannot unwrap: %s",
                    raw_text[:300],
                )
                return AIResponse(
                    assistant_reply="I processed your request.",
                    structured_update=None,
                    mode="general",
                    skill="none",
                    operation="none",
                    token_usage=self._extract_usage_metadata(response, model),
                )

        if not isinstance(parsed, dict):
            logger.warning(
                "Gemini returned non-dict response (%s): %s",
                type(parsed).__name__,
                raw_text[:300],
            )
            return AIResponse(
                assistant_reply="I processed your request.",
                structured_update=None,
                mode="general",
                skill="none",
                operation="none",
                token_usage=self._extract_usage_metadata(response, model),
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

        raw_compliance_reasoning = parsed.get("compliance_reasoning")
        compliance_reasoning = None
        if isinstance(raw_compliance_reasoning, list) and raw_compliance_reasoning:
            compliance_reasoning = raw_compliance_reasoning

        raw_referenced_categories = parsed.get("referenced_categories")
        referenced_categories = None
        if isinstance(raw_referenced_categories, list) and raw_referenced_categories:
            referenced_categories = [str(c).strip() for c in raw_referenced_categories if str(c).strip()]
            if not referenced_categories:
                referenced_categories = None

        raw_referenced_locations = parsed.get("referenced_locations")
        referenced_locations = None
        if isinstance(raw_referenced_locations, list) and raw_referenced_locations:
            referenced_locations = [str(loc).strip() for loc in raw_referenced_locations if str(loc).strip()]
            if not referenced_locations:
                referenced_locations = None

        return AIResponse(
            assistant_reply=reply,
            structured_update=updates if updates else None,
            mode=mode,
            skill=skill,
            operation=operation,
            confidence=confidence,
            missing_fields=missing_fields,
            token_usage=self._extract_usage_metadata(response, model),
            compliance_reasoning=compliance_reasoning,
            referenced_categories=referenced_categories,
            referenced_locations=referenced_locations,
        )

    async def estimate_usage(
        self,
        messages: list[dict],
        current_state: dict,
        company_context: str = "",
        slide_index: Optional[int] = None,
        dynamic_context: str = "",
        model_override: Optional[str] = None,
        company_id: str = "",
        user_id: str = "",
    ) -> dict:
        static_prompt, dynamic_prompt, _, _, _ = self._build_prompt_and_contents(
            messages, current_state, company_context=company_context,
            slide_index=slide_index, dynamic_context=dynamic_context,
        )
        # Resolve the SAME model the actual turn will use — estimating against
        # the default flash model billed Pro-tier fallback turns at flash prices.
        model = await _get_model(
            self.settings, model_override,
            company_id=company_id or None, user_id=user_id or None,
        )
        windowed = messages[-20:]
        char_count = len(static_prompt) + len(dynamic_prompt) + sum(len(str(msg.get("content", ""))) for msg in windowed)
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
        company_context: str = "",
        slide_index: Optional[int] = None,
        context_summary: Optional[str] = None,
        blog_mode_state: Optional[str] = None,
        dynamic_context: str = "",
        hr_pilot_mode: bool = False,
    ) -> tuple[str, str, list, list[str], str]:
        """Returns (static_prompt, dynamic_prompt, contents, valid_fields, skill).

        static_prompt: instructions + company context (cacheable, changes slowly)
        dynamic_prompt: current_state + summary + slide lock (changes per message)
        dynamic_context: per-turn context blocks (node/compliance/payer/RAG) —
            these vary with every message, so routing them here instead of into
            company_context keeps the static-prompt cache key stable (routing
            them into the static prompt made the Gemini cache miss every turn
            and CREATE a new cache per message).

        When blog_mode_state is provided (set by the route for project_type='blog'),
        a dedicated blog-only system prompt is used instead of the generic
        multi-skill prompt. This removes every non-blog skill from the AI's
        vocabulary so it cannot hallucinate creating a project document.
        """
        window_size = 15 if context_summary else 20
        windowed = messages[-window_size:]

        # Dedicated blog mode — swap the entire prompt. Bypasses the generic
        # multi-skill prompt so the AI can't hallucinate using project /
        # workbook / other skills on a blog chat. Split into static (cacheable)
        # + dynamic (blog state, per message) so Gemini context caching hits.
        if blog_mode_state is not None:
            static_prompt = MATCHA_WORK_BLOG_STATIC_PROMPT.format(
                today=date.today().isoformat(),
                company_context=company_context,
            )
            dynamic_prompt = MATCHA_WORK_BLOG_DYNAMIC_PROMPT.format(blog_state=blog_mode_state)
            if context_summary:
                dynamic_prompt += (
                    f"\n\n## Conversation Context Summary\n"
                    f"(Earlier messages were summarized to preserve context)\n"
                    f"{context_summary}\n"
                )
            if dynamic_context:
                dynamic_prompt += "\n\n" + dynamic_context
            blog_contents: list = []
            for msg in windowed:
                role = "user" if msg["role"] == "user" else "model"
                parts: list = []
                if role == "user":
                    for image_bytes, mime in (msg.get("image_parts") or []):
                        if image_bytes:
                            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
                text_content = msg.get("content") or ""
                if text_content or not parts:
                    parts.append(types.Part(text=text_content))
                blog_contents.append(types.Content(role=role, parts=parts))
            return static_prompt, dynamic_prompt, blog_contents, list(BLOG_FIELDS), "blog"

        current_skill = _infer_skill_from_state(current_state)
        if current_skill == "offer_letter":
            valid_fields = OFFER_LETTER_FIELDS
        elif current_skill == "review":
            valid_fields = REVIEW_FIELDS
        elif current_skill == "workbook":
            valid_fields = WORKBOOK_FIELDS
        elif current_skill == "onboarding":
            valid_fields = ONBOARDING_FIELDS
        elif current_skill == "presentation":
            valid_fields = PRESENTATION_FIELDS
        elif current_skill == "handbook":
            valid_fields = HANDBOOK_FIELDS
        elif current_skill == "policy":
            valid_fields = POLICY_FIELDS
        elif current_skill == "project":
            valid_fields = PROJECT_FIELDS
        elif current_skill == "blog":
            valid_fields = BLOG_FIELDS
        elif current_skill == "hr_pilot":
            valid_fields = HR_PILOT_FIELDS
        else:
            valid_fields = OFFER_LETTER_FIELDS + REVIEW_FIELDS + WORKBOOK_FIELDS + ONBOARDING_FIELDS + PRESENTATION_FIELDS + HANDBOOK_FIELDS + POLICY_FIELDS + PROJECT_FIELDS + BLOG_FIELDS
            # HR Pilot's action vocabulary is offered only in HR Pilot threads —
            # otherwise a normal chat could stage an `hr_action` the executor
            # would then refuse anyway.
            if hr_pilot_mode:
                valid_fields = valid_fields + HR_PILOT_FIELDS

        # Static part — instructions + company context (cached at Gemini API level)
        static_prompt = MATCHA_WORK_STATIC_PROMPT_TEMPLATE.format(
            today=date.today().isoformat(),
            company_context=company_context,
        )

        # Dynamic part — per-message state (never cached)
        dynamic_prompt = MATCHA_WORK_DYNAMIC_PROMPT_TEMPLATE.format(
            current_skill=current_skill,
            current_state=json.dumps(current_state, default=str, separators=(",", ":")),
            valid_fields=", ".join(valid_fields),
        )

        # Per-turn context (node/compliance/payer/RAG blocks) — must stay out
        # of the static prompt or the cache key changes every message.
        if dynamic_context:
            dynamic_prompt += "\n\n" + dynamic_context

        # HR Pilot action vocabulary — injected only for HR Pilot threads, so the
        # `hr_pilot` skill is invisible everywhere else (execution is gated again
        # server-side regardless).
        if hr_pilot_mode:
            dynamic_prompt += """

HR PILOT ACTIONS:
Besides answering questions, you may PROPOSE two documented actions, and you may
CONFIRM any action already staged in current_state. All actions are strictly
two-step and confirm-first — never propose and execute in the same message.

PROPOSE (mode="skill", skill="hr_pilot", operation="none", with the hr_action in updates):
- Discipline write-up — when a supervisor asks to write someone up / document an
  attendance, performance, or policy issue:
  updates={"hr_action": {"type":"discipline_draft", "employee_name": str,
  "infraction_type": "attendance|performance|policy_violation",
  "severity": "minor|moderate|severe", "occurrence_dates": ["YYYY-MM-DD", ...],
  "description": str, "expected_improvement": str, "status": "proposed"}}
- Time-off request on an employee's behalf — VACATION or PERSONAL only:
  updates={"hr_action": {"type":"pto_request", "employee_name": str,
  "request_type": "vacation|personal", "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD", "hours": number, "reason": str, "status": "proposed"}}
In "reply", summarize what you drafted and ask the supervisor to confirm.

CONFIRM (mode="skill", skill="hr_pilot", operation="execute_hr_action", updates={}):
- When current_state.hr_action has status "proposed" (ANY type — including a
  safety/incident or HR-case report the SYSTEM staged for the supervisor after a
  hard-stop) and the user confirms (e.g. "yes", "confirm", "file it"), emit the
  execute operation with an EMPTY updates object. NEVER restate hr_action.

Rules:
- NEVER claim anything was filed unless you used operation="execute_hr_action".
- If you're missing the employee, dates, hours, or what happened, ask
  (mode="clarify") — never invent a name, date, or number for a real record.
- Do NOT PROPOSE a discipline write-up or PTO request for anything involving
  safety, injury, harassment, discrimination, sick/medical leave, or termination
  — those go to corporate HR (and are refused here). This restriction is about
  PROPOSING; it does NOT stop you from helping the supervisor CONFIRM a
  system-staged report about such a topic.
- Never give guidance about the CONTENT of a staged safety/harassment report —
  only help the supervisor confirm it or cancel it."""

        # Recruiting project context — add specific instructions
        # (The route-level _inject_recruiting_project_context provides the primary
        #  context via company_context; this adds post-finalization details from thread state)
        if current_skill == "project" and current_state.get("posting"):
            posting = current_state.get("posting", {})
            candidates_count = len(current_state.get("candidates", []))
            is_finalized = bool(posting.get("finalized"))
            dynamic_prompt += f"""
RECRUITING PROJECT UPDATE:
- Posting finalized: {is_finalized}
- Candidates: {candidates_count}
"""

        if context_summary:
            dynamic_prompt += (
                f"\n\n## Conversation Context Summary\n"
                f"(Earlier messages were summarized to preserve context)\n"
                f"{context_summary}\n"
            )

        if slide_index is not None and current_skill in ("presentation", "workbook"):
            slides = current_state.get("slides") or []
            if not slides:
                pres = current_state.get("presentation")
                if isinstance(pres, dict):
                    slides = pres.get("slides") or []
            slide_title = ""
            if 0 <= slide_index < len(slides):
                slide_title = slides[slide_index].get("title", "") if isinstance(slides[slide_index], dict) else ""
            label = f' "{slide_title}"' if slide_title else ""
            total = len(slides)
            dynamic_prompt += (
                f"\n\n--- SLIDE LOCK ACTIVE ---\n"
                f"The user has selected Slide {slide_index + 1}/{total}{label} (0-based index {slide_index}). "
                f"You MUST only modify this slide. In your updates JSON:\n"
                f"- The 'slides' array must be identical to current_state except at index {slide_index}\n"
                f"- Do NOT change any other slide's title, bullets, or speaker_notes\n"
                f"- Do NOT include presentation_title, subtitle, theme, or cover_image_url in updates\n"
                f"- Only include 'slides' in your updates object\n"
                f"- CRITICAL: The user is requesting a CHANGE to the current slide. You must produce "
                f"updated content that differs from current_state. If the user asks to add, remove, or "
                f"modify something, the slide in your response MUST reflect that change. Never return "
                f"the slide unchanged when the user has requested a modification.\n"
                f"--- END SLIDE LOCK ---"
            )

        contents = []
        for msg in windowed:
            role = "user" if msg["role"] == "user" else "model"
            parts: list = []
            # Multimodal: attach any pre-fetched image bytes. The route layer
            # populates image_parts via fetch_image_parts_for_messages() so
            # this pure builder never does blocking I/O.
            if role == "user":
                for image_bytes, mime in (msg.get("image_parts") or []):
                    if image_bytes:
                        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
            text_content = msg.get("content") or ""
            if text_content or not parts:
                parts.append(types.Part(text=text_content))
            contents.append(types.Content(role=role, parts=parts))
        return static_prompt, dynamic_prompt, contents, valid_fields, current_skill

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
        cached_tokens = _to_int(_get("cached_content_token_count")) or 0
        total_tokens = _to_int(_get("total_token_count", "totalTokenCount"))

        # Gemini's prompt_token_count includes cached tokens. Subtract them
        # so users aren't charged for cached content.
        if cached_tokens > 0 and prompt_tokens is not None:
            prompt_tokens = max(0, prompt_tokens - cached_tokens)

        # Recompute total from the adjusted prompt + completion
        if prompt_tokens is not None or completion_tokens is not None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "estimated": False,
            "model": model,
        }


_provider: Optional[GeminiProvider] = None


def get_ai_provider() -> GeminiProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider
