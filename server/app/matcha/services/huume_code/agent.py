"""Bounded Gemini function-calling loop that turns one chat mention into a draft PR."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from uuid import UUID

from google.genai import types

from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from app.database import connection_or_direct
from app.matcha.services.matcha_work import github_write
from . import chat, store
from .guards import WorkingSet, branch_name
from .identity import ensure_huume_bot_user
from .prompt import build_prompt
from .tools import declarations

logger = logging.getLogger(__name__)
_MAX_CALLS = 30
_WALL_SECONDS = 420.0
_STEP_CAP = 4_000


def _safe(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except Exception:
        return {"note": "unserializable"}
    return value if len(encoded) <= _STEP_CAP else {"truncated": True, "preview": encoded[:_STEP_CAP]}


async def run_huume_code(*, run_id: UUID, company_id: UUID, project_id: UUID, channel_id: UUID, request: str, repo: str, base_branch: str) -> dict:
    """Run one agent turn. Exceptions are handled by the Celery wrapper.

    All writes remain in ``WorkingSet`` until ``open_pr``; the only GitHub
    mutation is its single, non-force commit and draft PR.
    """
    started = time.monotonic()
    limiter = GeminiRateLimiter()
    working = WorkingSet()
    tree: list[dict] | None = None
    ticket: dict | None = None
    branch: str | None = None
    model_calls = 0
    posted_updates = 0
    seq = 0
    opened_pr: dict | None = None
    completed = False
    bot_id: UUID
    async with connection_or_direct() as conn:
        bot_id = await ensure_huume_bot_user(conn, company_id)

    async def step(name: str, kind: str, label: str, args: dict, result: dict, status: str = "ok") -> dict:
        nonlocal seq
        seq += 1
        await store.record_step(run_id, seq, name, kind, label, _safe(args), _safe(result), status)
        return result

    async def call_tool(name: str, args: dict) -> tuple[dict, str]:
        nonlocal tree, ticket, branch, posted_updates, opened_pr
        try:
            if name == "list_tickets":
                result = {"tickets": await store.list_tickets(project_id)}
                return await step(name, "read", "Listed open tickets", args, result), "ok"
            if name == "read_ticket":
                candidate = await store.read_ticket(project_id, UUID(str(args.get("task_id"))))
                if not candidate:
                    return await step(name, "read", "Ticket not found", args, {"error": "Ticket is not in this project."}, "error"), "error"
                ticket = candidate
                branch = branch_name(ticket["id"], ticket["title"])
                context = await store.grounding(project_id, ticket.get("element_id"))
                await store.mark_run(run_id, status="running", task_id=UUID(ticket["id"]), branch=branch)
                await store.move_ticket_silently(project_id, UUID(ticket["id"]), "in_progress", bot_id)
                if posted_updates < 1:
                    await chat.post_as_huume(company_id, channel_id, f'Picked **{ticket["title"]}** and moved it to **In progress** — reading the relevant code and preparing a draft PR.')
                    posted_updates += 1
                result = {"ticket": candidate, "branch": branch, "grounding": context}
                return await step(name, "read", f'Read ticket: {ticket["title"]}', args, result), "ok"
            if name == "list_files":
                if tree is None:
                    tree = await store.repo_tree(repo, base_branch)
                prefix = str(args.get("prefix") or "").lstrip("/")
                files = [item["path"] for item in tree if item.get("path", "").startswith(prefix)][:600]
                return await step(name, "read", "Listed repository files", args, {"files": files}), "ok"
            if name == "read_file":
                path = str(args.get("path") or "").lstrip("/")
                value = working.read(path, await store.repo_file(repo, base_branch, path))
                result = {"path": path, "content": value} if value is not None else {"error": f"File not found: {path}"}
                return await step(name, "read", f"Read {path}", args, result, "ok" if value is not None else "error"), "ok" if value is not None else "error"
            if name == "search_repo":
                query = str(args.get("query") or "")
                result = {"matches": await store.search_snapshot(project_id, query)}
                if tree is None:
                    tree = await store.repo_tree(repo, base_branch)
                result["path_matches"] = [item["path"] for item in tree if query.lower() in item.get("path", "").lower()][:30]
                return await step(name, "read", "Searched repository snapshot", args, result), "ok"
            if name == "write_file":
                working.write(str(args.get("path") or ""), str(args.get("content") or ""))
                return await step(name, "write", f"Staged {args.get('path')}", args, {"staged_files": len(working.files), "deleted_files": len(working.deletes)}), "ok"
            if name == "delete_file":
                working.delete(str(args.get("path") or ""))
                return await step(name, "write", f"Staged deletion of {args.get('path')}", args, {"staged_files": len(working.files), "deleted_files": len(working.deletes)}), "ok"
            if name == "post_update":
                if posted_updates >= 2:
                    result = {"status": "skipped", "message": "Chat message budget reached."}
                    return await step(name, "write", "Skipped extra chat update", args, result, "skipped"), "skipped"
                await chat.post_as_huume(company_id, channel_id, str(args.get("message") or "")[:1200])
                posted_updates += 1
                return await step(name, "write", "Posted chat update", args, {"status": "posted"}), "ok"
            if name == "open_pr":
                if not ticket:
                    raise ValueError("Choose and read a ticket before opening a PR.")
                if not working.files and not working.deletes:
                    raise ValueError("Stage at least one file before opening a PR.")
                assert branch is not None
                base_sha = await github_write.ensure_branch(repo, base_branch, branch)
                await github_write.commit_files(repo, branch, base_sha, working.files, working.deletes, f"Huume: {ticket['title']}")
                opened_pr = await github_write.open_draft_pr(repo, branch, base_branch, str(args.get("title") or ticket["title"]), str(args.get("body") or ""))
                await store.move_ticket_silently(project_id, UUID(ticket["id"]), "review", bot_id)
                await store.mark_run(run_id, status="running", pr_url=opened_pr.get("html_url"), files_changed=len(working.files) + len(working.deletes))
                if posted_updates < 3:
                    await chat.post_as_huume(company_id, channel_id, f"Draft PR ready: [{opened_pr.get('html_url')}]({opened_pr.get('html_url')}) — moved the ticket to **Review**.")
                    posted_updates += 1
                return await step(name, "write", "Opened draft pull request", args, {"url": opened_pr.get("html_url"), "number": opened_pr.get("number")}), "ok"
            if name == "finish":
                return await step(name, "finish", "Finished", args, {"message": str(args.get("message") or "")}), "ok"
            return await step(name, "read", f"Unknown tool: {name}", args, {"error": "unknown tool"}, "error"), "error"
        except Exception as exc:  # tool errors must feed the model, not kill audit
            logger.warning("huume_code tool failed: %s", name, exc_info=True)
            return await step(name, "write", f"{name} refused", args, {"error": str(exc)}, "error"), "error"

    initial = build_prompt(request=request, repo=repo, branch=base_branch)
    contents = [types.Content(role="user", parts=[types.Part(text=initial)])]
    config = types.GenerateContentConfig(tools=[types.Tool(function_declarations=declarations())])
    try:
        while model_calls < _MAX_CALLS and time.monotonic() - started < _WALL_SECONDS:
            await limiter.check_limit("huume_code", "agent")
            model_calls += 1
            try:
                response = await asyncio.wait_for(get_genai_client().aio.models.generate_content(
                    model="gemini-3.6-flash", contents=contents, config=config,
                ), timeout=max(1, _WALL_SECONDS - (time.monotonic() - started)))
            finally:
                await limiter.record_call("huume_code", "agent")
            parts = [part for candidate in (response.candidates or []) for part in ((candidate.content.parts if candidate.content else []) or [])]
            calls = [part.function_call for part in parts if getattr(part, "function_call", None)]
            if not calls:
                break
            contents.append(types.Content(role="model", parts=parts))
            responses: list[types.Part] = []
            should_finish = False
            for call in calls:
                result, _status = await call_tool(call.name, dict(call.args or {}))
                responses.append(types.Part.from_function_response(name=call.name, response=result))
                should_finish = should_finish or call.name == "finish"
            contents.append(types.Content(role="user", parts=responses))
            if should_finish:
                break
        # A bound is not permission to discard useful staged work. The only
        # externally visible partial result is still a reviewable draft PR.
        if (
            (model_calls >= _MAX_CALLS or time.monotonic() - started >= _WALL_SECONDS)
            and ticket and (working.files or working.deletes) and not opened_pr
        ):
            await call_tool("open_pr", {
                "title": f"[partial] {ticket['title']}",
                "body": "Huume reached its run bound before completing this draft. Please review carefully.",
            })
        completed = True
    except RateLimitExceeded:
        raise
    finally:
        if completed:
            await store.mark_run(
                run_id, status="done", model_calls=model_calls,
                files_changed=len(working.files) + len(working.deletes),
                pr_url=opened_pr.get("html_url") if opened_pr else None,
            )
    return {"model_calls": model_calls, "pr_url": opened_pr.get("html_url") if opened_pr else None}
