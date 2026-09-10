"""Bounded read-only agent that answers one project-chat repository question."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID


from app.core.services.ai_usage import feature_scope
from app.matcha.services.huume.luna_client import get_luna_client, text_item, tool_output_item
from app.matcha.services.huume.routing import LUNA

from . import chat, store
from .prompt import build_system_prompt
from .tools import declarations

logger = logging.getLogger(__name__)

_MAX_MODEL_CALLS = 18
_WALL_SECONDS = 240.0
_STEP_AUDIT_CAP = 4_000
_MAX_ANSWER_CHARS = 3_500
# Under tool_config=ANY the model can no longer end the run by answering in
# prose, so a model that keeps failing the finish preconditions would otherwise
# grind through every one of _MAX_MODEL_CALLS before raising. Give up sooner.
_MAX_FINISH_REFUSALS = 3
_AI_USAGE_FEATURE = "matcha.espresso.repo_question"


def _safe_for_audit(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except Exception:
        return {"note": "unserializable"}
    if len(encoded) <= _STEP_AUDIT_CAP:
        return value
    return {"truncated": True, "preview": encoded[:_STEP_AUDIT_CAP]}


def _fold_usage(total: dict[str, Any], response: Any) -> None:
    usage = getattr(response, "usage", None) or {}
    if not usage:
        return
    details_out = usage.get("output_tokens_details") or {}
    fields = {
        "prompt_tokens": usage.get("input_tokens"),
        "completion_tokens": usage.get("output_tokens"),
        "thought_tokens": details_out.get("reasoning_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    for target, value in fields.items():
        if value is not None:
            total[target] = total.get(target, 0) + int(value)


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
    client = get_luna_client()
    tree: list[dict] | None = None
    files_read: set[str] = set()
    model_calls = 0
    pending_outputs: list[dict[str, Any]] = []
    finish_refusals = 0
    seq = 0
    answer: str | None = None
    usage: dict[str, Any] = {"model": LUNA}

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
    input_items: list[dict[str, Any]] = [text_item("user", user_turn)]
    instructions = build_system_prompt()
    tools = declarations()

    while (
        answer is None
        and model_calls < _MAX_MODEL_CALLS
        and time.monotonic() - started < _WALL_SECONDS
    ):
        model_calls += 1
        call_timeout = max(1, _WALL_SECONDS - (time.monotonic() - started))
        with feature_scope(_AI_USAGE_FEATURE):
            response = await asyncio.wait_for(
                client.create_response(
                    model=LUNA,
                    # The first call sends the question; follow-ups send only
                    # tool outputs, with previous_response_id carrying the rest.
                    input=input_items if model_calls == 1 else pending_outputs,
                    instructions=instructions,
                    tools=tools,
                    # This agent must call a tool: its answer only counts once
                    # it has actually read the repository.
                    tool_choice="required",
                    timeout_seconds=call_timeout,
                ),
                timeout=call_timeout,
            )

        _fold_usage(usage, response)
        calls = response.function_calls
        if not calls:
            # Luna occasionally returns its final prose directly despite the
            # explicit finish tool. Accept it only after a repository read; the
            # same size and grounding preconditions still apply.
            direct = (response.text or '').strip()
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

        tool_responses: list[dict[str, Any]] = []
        for call in calls:
            result, status = await call_tool(call["name"], dict(call["arguments"] or {}))
            if call["name"] == "answer_question":
                finish_refusals = finish_refusals + 1 if status == "error" else 0
            elif status == "ok":
                # A successful read is new grounding, so the next finish attempt
                # starts from a clean slate.
                finish_refusals = 0
            tool_responses.append(tool_output_item(call["call_id"], result))
        if finish_refusals >= _MAX_FINISH_REFUSALS:
            break
        pending_outputs = tool_responses

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
