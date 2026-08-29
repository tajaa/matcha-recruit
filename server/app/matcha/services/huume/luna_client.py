"""OpenAI Responses adapter for Huume's existing bounded tool loop.

Huume's loop deliberately keeps its Gemini-shaped in-memory tool contract so
the server-side safety envelope and its extensive loop tests do not change.
This adapter is the only provider boundary: it translates those transient
objects to Responses API inputs and translates Luna function calls back.
"""

from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace
from typing import Any

import httpx
from google.genai import types

from app.config import get_settings
from app.core.services.ai_usage import record_openai_response


_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _schema(schema: Any) -> dict[str, Any]:
    """Convert Google function-schema objects into JSON Schema for Responses."""
    result: dict[str, Any] = {}
    schema_type = getattr(schema, "type", None)
    if schema_type:
        value = getattr(schema_type, "value", schema_type)
        result["type"] = str(value).lower()
    description = getattr(schema, "description", None)
    if description:
        result["description"] = description
    enum = getattr(schema, "enum", None)
    if enum:
        result["enum"] = list(enum)
    properties = getattr(schema, "properties", None)
    if properties:
        result["properties"] = {name: _schema(child) for name, child in properties.items()}
    required = getattr(schema, "required", None)
    if required:
        result["required"] = list(required)
    items = getattr(schema, "items", None)
    if items:
        result["items"] = _schema(items)
    return result


def _tools(config: Any) -> list[dict[str, Any]]:
    declarations = []
    for tool in getattr(config, "tools", None) or []:
        declarations.extend(getattr(tool, "function_declarations", None) or [])
    return [
        {
            "type": "function",
            "name": declaration.name,
            "description": declaration.description,
            "parameters": _schema(declaration.parameters),
        }
        for declaration in declarations
    ]


def _messages(contents: list[Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for content in contents:
        role = "assistant" if getattr(content, "role", None) == "model" else "user"
        text_type = "output_text" if role == "assistant" else "input_text"
        parts: list[dict[str, Any]] = []
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text is not None:
                # Responses input items use a different content-part type for
                # prior assistant messages.  Sending assistant history as
                # ``input_text`` is rejected with HTTP 400; it made a fresh
                # Huume thread work once and every later turn fail before the
                # model ran (schedule threads always have history).
                parts.append({
                    "type": text_type,
                    "text": text,
                })
            inline = getattr(part, "inline_data", None)
            # Historical assistant images are not valid Responses input
            # content. Huume only attaches images to the current user turn.
            if role == "user" and inline is not None and getattr(inline, "data", None):
                encoded = base64.b64encode(inline.data).decode("ascii")
                mime = getattr(inline, "mime_type", None) or "application/octet-stream"
                parts.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
        if parts:
            messages.append({"role": role, "content": parts})
    return messages or [{"role": "user", "content": [{"type": "input_text", "text": "Hello."}]}]


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    return "\n".join(
        content["text"]
        for output in payload.get("output", [])
        if isinstance(output, dict) and output.get("type") == "message"
        for content in output.get("content", [])
        if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str)
    ).strip()


def _http_error_detail(exc: httpx.HTTPError) -> str:
    """Return the provider's bounded error detail for logs and usage audit."""
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            message = error.get("message")
            detail = ": ".join(str(value) for value in (code, message) if value)
            if detail:
                return detail[:1000]
    except (TypeError, ValueError):
        pass
    return f"HTTP {response.status_code}: {response.text[:1000]}"


class _LunaModels:
    def __init__(self) -> None:
        self._previous_response_id: str | None = None
        self._pending_call_ids: list[tuple[str, str]] = []

    def _tool_outputs(self, contents: list[Any]) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for part in getattr(contents[-1], "parts", None) or []:
            response = getattr(part, "function_response", None)
            if response is None:
                continue
            name = response.name
            index = next((i for i, call in enumerate(self._pending_call_ids) if call[0] == name), None)
            if index is None:
                raise ValueError(f"Luna tool response has no pending call: {name}")
            _name, call_id = self._pending_call_ids.pop(index)
            outputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(response.response or {}, default=str, separators=(",", ":")),
            })
        return outputs

    async def generate_content(self, *, model: str, contents: list[Any], config: Any):
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for Huume Luna")
        follow_up = self._previous_response_id is not None
        payload: dict[str, Any] = {
            "model": model,
            "input": self._tool_outputs(contents) if follow_up else _messages(contents),
            # Responses does not carry request-level instructions forward
            # automatically with previous_response_id, so repeat the stable
            # Huume safety prompt and tool catalog on every tool follow-up.
            "instructions": str(getattr(config, "system_instruction", "") or ""),
            "tools": _tools(config),
            "parallel_tool_calls": True,
            "reasoning": {"effort": "high"},
        }
        if follow_up:
            payload["previous_response_id"] = self._previous_response_id

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    _RESPONSES_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            error_detail = _http_error_detail(exc)
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=error_detail,
                status="timeout" if isinstance(exc, httpx.TimeoutException) else "error",
            )
            raise RuntimeError(f"OpenAI Responses request failed: {error_detail}") from exc
        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"Invalid Responses JSON: {exc}",
                status="error",
            )
            raise RuntimeError("OpenAI Responses returned invalid JSON") from exc
        if not isinstance(data, dict):
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                error="OpenAI Responses payload must be an object",
                status="error",
            )
            raise RuntimeError("OpenAI Responses payload must be an object")
        self._previous_response_id = data.get("id") or self._previous_response_id
        calls = [output for output in data.get("output", []) if isinstance(output, dict) and output.get("type") == "function_call"]
        self._pending_call_ids = [
            (str(call.get("name") or ""), str(call.get("call_id") or ""))
            for call in calls if call.get("name") and call.get("call_id")
        ]
        parts: list[types.Part] = []
        text = _response_text(data)
        if text:
            parts.append(types.Part(text=text))
        for call in calls:
            try:
                args = json.loads(call.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError):
                args = {}
            parts.append(types.Part(function_call=types.FunctionCall(name=call.get("name"), args=args)))
        usage = data.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        usage_metadata = SimpleNamespace(
            prompt_token_count=usage.get("input_tokens", 0),
            candidates_token_count=usage.get("output_tokens", 0),
            total_token_count=usage.get("total_tokens", 0),
            thoughts_token_count=output_details.get("reasoning_tokens", 0),
            cached_content_token_count=input_details.get("cached_tokens", 0),
        )
        await record_openai_response(
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            response=data,
        )
        return SimpleNamespace(
            usage_metadata=usage_metadata,
            text=text,
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
        )


class LunaClient:
    def __init__(self) -> None:
        self.aio = SimpleNamespace(models=_LunaModels())


def get_luna_client() -> LunaClient:
    return LunaClient()
