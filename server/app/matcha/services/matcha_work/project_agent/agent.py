"""Bounded read-only agent that answers one project-chat repository question."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from google.genai import types

from app.core.services.genai_client import get_genai_client
from app.core.services.model_catalog import GEMINI_FLASH
from app.core.services.rate_limiter import GeminiRateLimiter

from . import chat, store
from .prompt import build_system_prompt
from .tools import declarations

logger = logging.getLogger(__name__)

_MAX_MODEL_CALLS = 18
_WALL_SECONDS = 240.0
_STEP_AUDIT_CAP = 4_000
_MAX_ANSWER_CHARS = 3_500


def _safe_for_audit(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except Exception:
        return {"note": "unserializable"}
    if len(encoded) <= _STEP_AUDIT_CAP:
        return value
    return {"truncated": True, "preview": encoded[:_STEP_AUDIT_CAP]}


def _fold_usage(total: dict[str, Any], response: Any) -> None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    fields = {
        "prompt_tokens": "prompt_token_count",
        "completion_tokens": "candidates_token_count",
        "thought_tokens": "thoughts_token_count",
        "total_tokens": "total_token_count",
    }
    for target, source in fields.items():
        value = getattr(usage, source, None)
        if value is not None:
            total[target] = total.get(target, 0) + int(value)


def _text_parts(parts: list[Any]) -> str:
    return "\n".join(
        str(part.text).strip()
        for part in parts
        if getattr(part, "text", None) and str(part.text).strip()
    ).strip()


def _has_source_citation(answer: str, files_read: set[str]) -> bool:
    return any(
        re.search(rf"{re.escape(path)}:\d", answer)
        for path in files_read
    )


async def run_repo_question(
    *,
    run_id: UUID,
    company_id: UUID,
    project_id: UUID,
    channel_id: UUID,
    question: str,
    project_title: str,
    repo: str,
    base_branch: str,
) -> dict:
    """Answer one question with bounded repo reads and no mutation tools."""
    started = time.monotonic()
    limiter = GeminiRateLimiter()
    tree: list[dict] | None = None
    files_read: set[str] = set()
    model_calls = 0
    seq = 0
    answer: str | None = None
    usage: dict[str, Any] = {"model": GEMINI_FLASH}

    async def step(
        name: str,
        kind: str,
        label: str,
        args: dict,
        result: dict,
        status: str = "ok",
    ) -> dict:
        nonlocal seq
        seq += 1
        await store.record_step(
            run_id,
            seq,
            name,
            kind,
            label,
            _safe_for_audit(args),
            _safe_for_audit(result),
            status,
        )
        return result

    async def call_tool(name: str, args: dict) -> tuple[dict, str]:
        nonlocal tree, answer
        try:
            if name == "list_files":
                if tree is None:
                    tree = await store.repo_tree(repo, base_branch)
                prefix = str(args.get("prefix") or "").strip().lstrip("/")
                paths = [
                    item["path"] for item in tree
                    if not prefix or item.get("path", "").startswith(prefix)
                ][:800]
                result = {"files": paths, "truncated": len(paths) == 800}
                return await step(name, "read", "Listed repository files", args, result), "ok"

            if name == "search_repo":
                query = str(args.get("query") or "").strip()
                if not query:
                    result = {"error": "Provide a focused search term."}
                    return await step(name, "read", "Search refused", args, result, "error"), "error"
                if tree is None:
                    tree = await store.repo_tree(repo, base_branch)
                result = {
                    "matches": await store.search_snapshot(project_id, query),
                    "path_matches": [
                        item["path"] for item in tree
                        if query.lower() in item.get("path", "").lower()
                    ][:40],
                }
                return await step(name, "read", f"Searched for {query[:80]}", args, result), "ok"

            if name == "read_file":
                path = str(args.get("path") or "").strip().lstrip("/")
                result = await store.read_repo_file(
                    repo,
                    base_branch,
                    path,
                    start_line=int(args.get("start_line") or 1),
                    end_line=int(args["end_line"]) if args.get("end_line") is not None else None,
                )
                files_read.add(path)
                return await step(name, "read", f"Read {path}", args, result), "ok"

            if name == "answer_question":
                candidate = str(args.get("answer") or "").strip()
                if not files_read:
                    result = {"error": "Read at least one relevant repository file before answering."}
                    return await step(name, "finish", "Answer refused", args, result, "error"), "error"
                if not candidate:
                    result = {"error": "The answer cannot be empty."}
                    return await step(name, "finish", "Answer refused", args, result, "error"), "error"
                if len(candidate) > _MAX_ANSWER_CHARS:
                    result = {"error": f"Shorten the answer to at most {_MAX_ANSWER_CHARS} characters."}
                    return await step(name, "finish", "Answer too long", args, result, "error"), "error"
                if not _has_source_citation(candidate, files_read):
                    result = {"error": "Cite at least one file you read using path:line."}
                    return await step(name, "finish", "Answer lacks a source citation", args, result, "error"), "error"
                answer = candidate
                result = {"accepted": True, "characters": len(candidate)}
                return await step(name, "finish", "Prepared grounded answer", args, result), "ok"

            result = {"error": f"Unknown tool: {name}"}
            return await step(name, "read", "Unknown tool", args, result, "error"), "error"
        except Exception as exc:
            logger.warning("project agent tool failed: %s", name, exc_info=True)
            result = {"error": str(exc)[:1000]}
            kind = "finish" if name == "answer_question" else "read"
            return await step(name, kind, f"{name} failed", args, result, "error"), "error"

    user_turn = (
        "Untrusted project metadata (labels only):\n"
        f"- project: {project_title!r}\n"
        f"- repository: {repo!r}\n"
        f"- base branch: {base_branch!r}\n\n"
        f"Question:\n{question}"
    )
    contents = [types.Content(role="user", parts=[types.Part(text=user_turn)])]
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=[types.Tool(function_declarations=declarations())],
    )

    while (
        answer is None
        and model_calls < _MAX_MODEL_CALLS
        and time.monotonic() - started < _WALL_SECONDS
    ):
        await limiter.check_limit("project_agent", "repo_question")
        model_calls += 1
        try:
            response = await asyncio.wait_for(
                get_genai_client().aio.models.generate_content(
                    model=GEMINI_FLASH,
                    contents=contents,
                    config=config,
                ),
                timeout=max(1, _WALL_SECONDS - (time.monotonic() - started)),
            )
        finally:
            await limiter.record_call("project_agent", "repo_question")

        _fold_usage(usage, response)
        parts = [
            part
            for candidate in (response.candidates or [])
            for part in ((candidate.content.parts if candidate.content else []) or [])
        ]
        calls = [part.function_call for part in parts if getattr(part, "function_call", None)]
        if not calls:
            # Gemini occasionally returns its final prose directly despite the
            # explicit finish tool. Accept it only after a repository read; the
            # same size and grounding preconditions still apply.
            direct = _text_parts(parts)
            if (
                files_read
                and direct
                and len(direct) <= _MAX_ANSWER_CHARS
                and _has_source_citation(direct, files_read)
            ):
                answer = direct
                await step(
                    "answer_question",
                    "finish",
                    "Prepared grounded answer",
                    {"answer": direct},
                    {"accepted": True, "characters": len(direct), "direct": True},
                )
            break

        contents.append(types.Content(role="model", parts=parts))
        tool_responses: list[types.Part] = []
        for call in calls:
            result, _status = await call_tool(call.name, dict(call.args or {}))
            tool_responses.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=tool_responses))

    if answer is None:
        raise RuntimeError("I couldn't produce a grounded answer within this run's limits.")

    await chat.post_as_espresso(company_id, channel_id, answer)
    await store.mark_run(
        run_id,
        status="done",
        result={"answer": answer},
        model_calls=model_calls,
        files_read=len(files_read),
        token_usage=usage,
    )
    return {
        "answer": answer,
        "model_calls": model_calls,
        "files_read": len(files_read),
        "token_usage": usage,
    }
