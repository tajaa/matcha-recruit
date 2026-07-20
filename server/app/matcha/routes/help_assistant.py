"""Tenant-facing in-app help assistant ("Guide" for the whole app).

Read-only, per-page AI helper: the frontend sends the authored help blurb for
the page the user is on (title/summary/tips from client/src/data/pageHelp.ts)
plus a free-form question; Gemini flash-lite streams back a grounded answer.
Modeled on the admin Compliance Studio guide (core/routes/admin.py
studio_assistant) — NO tool calls, NO mutations, narration only.
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..dependencies import require_admin_or_client

logger = logging.getLogger(__name__)

router = APIRouter()

# page_context is client-controlled input that lands in a prompt — whitelist
# the keys the FE registry actually sends and cap sizes so a tampered payload
# can't smuggle a novel-length prompt in.
_ALLOWED_CONTEXT_KEYS = ("title", "summary", "tips")
_MAX_CONTEXT_CHARS = 2000
_MAX_QUESTION_CHARS = 500


class HelpAssistantRequest(BaseModel):
    question: str
    page_context: Optional[Dict[str, Any]] = None


def sanitize_page_context(ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Whitelist title/summary/tips, coerce to strings, cap combined size."""
    if not isinstance(ctx, dict):
        return {}
    out: Dict[str, Any] = {}
    budget = _MAX_CONTEXT_CHARS
    for key in _ALLOWED_CONTEXT_KEYS:
        value = ctx.get(key)
        if value is None:
            continue
        if key == "tips" and isinstance(value, list):
            tips = []
            for tip in value:
                text = str(tip)[:budget]
                budget -= len(text)
                if text:
                    tips.append(text)
                if budget <= 0:
                    break
            if tips:
                out[key] = tips
        else:
            text = str(value)[:budget]
            budget -= len(text)
            if text:
                out[key] = text
        if budget <= 0:
            break
    return out


@router.post("/help", dependencies=[Depends(require_admin_or_client)])
async def help_assistant(body: HelpAssistantRequest):
    """Stream a grounded how-to answer for the page the user is viewing."""
    import os

    from google import genai
    from app.core.services.genai_client import get_genai_client
    from google.genai import types as genai_types

    from app.config import get_settings
    from app.core.services.gemini_compliance import DEFAULT_LITE_MODEL
    from app.core.services.rate_limiter import RateLimitExceeded, get_rate_limiter

    limiter = get_rate_limiter()
    try:
        await limiter.check_limit("help_assistant")
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    question = body.question.strip()[:_MAX_QUESTION_CHARS]
    if not question:
        raise HTTPException(status_code=422, detail="Question is required")

    context = sanitize_page_context(body.page_context)

    system_prompt = (
        "You are a read-only in-app help guide inside Matcha, an HR compliance "
        "platform for small businesses. The user is viewing one specific page "
        "of the app; you are given that page's help card as JSON (title, "
        "summary, tips). Answer the user's question about how to use THIS page "
        "using ONLY that context — never invent buttons, features, or data "
        "that are not described there, and never claim you performed an "
        "action (you cannot perform any). If the question is about something "
        "outside this page, say so briefly and suggest where in the app it "
        "might live only if the context makes that obvious. Be concise, plain "
        "English, 2-4 sentences unless asked to elaborate."
    )
    prompt = (
        f"{system_prompt}\n\nCurrent page help card:\n{json.dumps(context)}"
        f"\n\nUser question: {question}"
    )

    async def event_stream():
        try:
            api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Assistant not configured'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            client = get_genai_client(api_key=api_key)
            await limiter.record_call("help_assistant")
            # Low-stakes narration — always flash-lite, like the studio guide.
            response = await client.aio.models.generate_content_stream(
                model=DEFAULT_LITE_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=600),
            )
            async for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk.text})}\n\n"
        except Exception as exc:  # noqa: BLE001 — stream errors as SSE, never 500 mid-stream
            logger.warning("help assistant stream failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Assistant unavailable right now'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
