"""Espresso Tasks, from chat: start background work, and talk about what it found.

A task (`agent_tasks/`) is work that takes minutes: finding and comparing many
options (an apartment hunt, a product across stores, places that fit). Here
the assistant starts one (`start_task`), asks for what is missing with a form
(`ask_form`, runner-owned: `agent_tasks.intake`), reads tasks and their
findings, and sends follow-ups (refine, search more, a document).

Starting costs units from the monthly allowance; refine and documents are
free. Nothing here buys, books or contacts anyone.

The `task` block is rebuilt from what this run read or started, by id: the
findings shown are the task's own rows, never the model's restatement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid5

from fastapi import HTTPException
from pydantic import ValidationError

from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, ToolOutput

KEY = "tasks"
ALLOWANCE = "agent_tasks"
PAGE = 20
MAX_BLOCK_ITEMS = 5


@dataclass
class TasksSession:
    tasks: dict[str, dict] = field(default_factory=dict)  # task id -> its compact view
    items: dict[str, dict] = field(default_factory=dict)  # item id -> its summary (with task_id)


def session_of(state: RunState) -> TasksSession:
    return state.sessions[KEY]


def _uuid(value: Any, what: str = "a task") -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Use the id of {what} you listed or read.") from exc


def _user(ctx: RunContext) -> SimpleNamespace:
    return SimpleNamespace(id=ctx.user_id, role=ctx.role)


def _compact_task(task: dict) -> dict:
    keep = ("id", "playbook", "title", "status", "phase", "item_count", "shown_count", "current_round",
            "created_at", "error")
    return {**{k: task.get(k) for k in keep}, "note": (task.get("progress") or {}).get("note")}


def _compact_item(item: dict) -> dict:
    return {
        "id": item["id"], "rank": item.get("rank"), "title": item.get("title"), "subtitle": item.get("subtitle"),
        "url": item.get("url"), "user_state": item.get("user_state"), "flags": item.get("flags") or [],
        "facts": {k: (v.get("display") if v.get("status") == "verified" else f"{v.get('display')} (unconfirmed)")
                  for k, v in (item.get("fields") or {}).items()},
    }


def _remember(state: RunState, task: dict, items: list[dict] = ()) -> None:
    session = session_of(state)
    session.tasks[task["id"]] = task
    for item in items:
        session.items[item["id"]] = {**item, "task_id": task["id"]}


def _known_task(state: RunState, task_id: Any) -> str:
    key = str(task_id or "")
    if key not in session_of(state).tasks:
        raise ValueError("List or read this task first.")
    return key


def _reason(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("code") or "That didn't work.")
    return str(detail or "That didn't work.")


async def _list(ctx: RunContext, state: RunState, _args: dict) -> ToolOutput:
    from app.matcha.services.matcha_work.agent_tasks import allowance, service

    tasks = await service.list_tasks(ctx.user_id, ctx.company_id)
    for task in tasks:
        session_of(state).tasks[task["id"]] = task
    usage = await allowance.task_usage(ctx.user_id)
    return ToolOutput(payload={"tasks": [_compact_task(t) for t in tasks], "units": usage})


async def _read(ctx: RunContext, state: RunState, args: dict) -> ToolOutput:
    from app.matcha.services.matcha_work.agent_tasks import service

    view = await service.get_task(_uuid(args.get("task_id")), ctx.user_id, mark_seen=False)
    offset = max(0, int(args.get("offset") or 0))
    items = view["items"][offset: offset + PAGE]
    _remember(state, view, items)
    latest = view["rounds"][-1] if view["rounds"] else {}
    return ToolOutput(
        payload={
            "task": {**_compact_task(view), "directive": view["directive"]},
            "looking_for": [c["label"] for c in view["plan"].get("constraints") or []],
            "latest": {"kind": latest.get("kind"), "status": latest.get("status"),
                       "headline": (latest.get("summary") or {}).get("headline"),
                       "summary": (latest.get("summary") or {}).get("summary")},
            "findings": [_compact_item(i) for i in items],
            "next_offset": offset + len(items) if offset + len(items) < len(view["items"]) else None,
        },
        # The task's own runs verified these pages: an answer may link them.
        provenance=frozenset(i["url"] for i in items if i.get("url")),
    )


async def _start(ctx: RunContext, state: RunState, args: dict) -> ToolOutput:
    from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate
    from app.matcha.services.matcha_work.agent_tasks import enqueue, intake, playbooks

    playbook = playbooks.get(str(args.get("playbook") or ""))
    if not playbooks.startable(playbook):
        raise ValueError("Use one of the playbooks listed.")
    directive = " ".join(str(args.get("directive") or "").split())
    brief_raw = args.get("brief") if isinstance(args.get("brief"), dict) else {}
    values, errors = intake.clean_values(playbook, brief_raw)
    missing = [f.key for f in playbook.intake
               if f.required and f.type not in ("file", "consent") and f.key not in values]
    if errors or missing:
        return ToolOutput(payload={
            "started": False, "missing": missing, "invalid": errors,
            "next": "Call ask_form with these field keys as missing, and what they told you as known.",
        }, status="error")
    body = AgentTaskCreate(
        request_id=uuid5(ctx.run_id, f"start|{playbook.key}|{directive}"), playbook=playbook.key,
        directive=directive, title=str(args.get("title") or "")[:120], brief=values,
        input_ids=[_uuid(i, "a file") for i in (args.get("input_ids") or [])][:5],
    )
    task = await enqueue.create_task(_user(ctx), ctx.company_id, body, origin=(ctx.channel_id, None))
    _remember(state, task)
    return ToolOutput(payload={"started": True, "task": _compact_task(task)})


async def _follow_up(ctx: RunContext, state: RunState, args: dict) -> ToolOutput:
    from app.matcha.models.matcha_work.agent_tasks import RoundCreate
    from app.matcha.services.matcha_work.agent_tasks import enqueue

    task_id = _known_task(state, args.get("task_id"))
    kind = args.get("kind")
    directive = " ".join(str(args.get("directive") or "").split())[:2000]
    item_ids = [_uuid(i, "a finding") for i in (args.get("item_ids") or [])][:20]
    body = RoundCreate(request_id=uuid5(ctx.run_id, f"round|{task_id}|{kind}|{directive}"), kind=kind,
                       directive=directive, item_ids=item_ids)
    view = await enqueue.start_round(_user(ctx), UUID(task_id), body)
    _remember(state, view)
    latest = view["rounds"][-1] if view.get("rounds") else {}
    return ToolOutput(payload={"task": _compact_task(view), "round": {
        "kind": latest.get("kind"), "status": latest.get("status"), "document": latest.get("document"),
    }})


async def _cancel(ctx: RunContext, state: RunState, args: dict) -> ToolOutput:
    from app.matcha.services.matcha_work.agent_tasks import service

    task_id = _known_task(state, args.get("task_id"))
    view = await service.cancel_task(UUID(task_id), ctx.user_id)
    _remember(state, view)
    return ToolOutput(payload={"task": _compact_task(view)})


async def _update_item(ctx: RunContext, state: RunState, args: dict) -> ToolOutput:
    from app.matcha.services.matcha_work.agent_tasks import service

    item_id = str(args.get("item_id") or "")
    known = session_of(state).items.get(item_id)
    if known is None:
        raise ValueError("Read this finding before changing it.")
    item = await service.patch_item(UUID(known["task_id"]), UUID(item_id), ctx.user_id,
                                    user_state=args.get("status"), notes=args.get("notes"))
    session_of(state).items[item_id] = {**item, "task_id": known["task_id"]}
    return ToolOutput(payload={"finding": _compact_item(item), "saved": True})


def _tool(name: str, effect: str, description: str, parameters: dict, fn, *, untrusted: bool = False) -> AgentTool:
    async def handler(ctx: RunContext, state: RunState, args: dict, _left: float) -> ToolOutput:
        from app.matcha.services.matcha_work.agent_tasks.service import AgentTaskError

        try:
            out = await fn(ctx, state, args)
        except AgentTaskError as exc:
            return ToolOutput(payload={"error": str(exc)}, status="error")
        except HTTPException as exc:
            return ToolOutput(payload={"error": _reason(exc)[:300]}, status="error")
        except (ValueError, ValidationError) as exc:
            return ToolOutput(payload={"error": str(exc)[:300]}, status="error")
        return ToolOutput(payload=out.payload, provenance=out.provenance, status=out.status,
                          audit={"tool": name, "task_id": args.get("task_id"), "playbook": args.get("playbook")})

    return AgentTool(
        name=name, effect=effect, description=description,
        parameters={"type": "object", "properties": parameters.get("properties", {}),
                    "required": parameters.get("required", []), "additionalProperties": False},
        step_kind="draft" if effect == "draft" else "read",
        handler=handler, max_calls=10, untrusted_output=untrusted,
        describe=lambda args, _n=name: _n.replace("_", " ").capitalize(),
    )


_ID = {"type": "string"}
_IDS = {"type": "array", "items": {"type": "string"}}


def _prompt(_ctx: RunContext) -> str:
    from app.matcha.services.matcha_work.agent_tasks import allowance, playbooks

    def field(f) -> str:
        # A choice field names its choices, so a value is one of them (a list
        # of them for a multi-choice field: "north or south" is both).
        choices = (f": a list of any of {' | '.join(f.options)}" if f.type == "multi_select"
                   else f": one of {' | '.join(f.options)}") if f.options else ""
        return f"{f.key} ({f.label}{choices}{', required' if f.required else ''})"

    books = "\n".join(
        f"  - {p.key} ({allowance.WEIGHTS[p.key]} units): {p.description} Fields: "
        + ", ".join(field(f) for f in p.intake if f.type != "consent")
        for p in playbooks.PLAYBOOKS.values() if playbooks.startable(p)
    )
    return f"""Tasks (background work):
- Start a task with start_task for work that means finding and comparing many options and takes \
minutes: a home to rent, a product across stores, places that fit, a service, jobs to apply for \
(the job_search playbook). It runs in the background, keeps what it finds with the evidence for each \
fact, and posts here when it is done. Answer quick questions yourself instead.
- Playbooks:
{books}
- Put what they told you in `brief` by field key: a list field as an array, a choice field as one of \
its choices exactly. A limit that has its own field (a price, a distance, a date) goes there, not in \
must_haves. Something they want to find out about each one ("see what concessions they're \
offering", the fees) is not a must have either: it is reported for every finding, and a must have \
would throw out each one whose page doesn't say. If something that would change the results a lot \
is missing (where, the budget, dates), call ask_form first, naming those field keys as missing and \
the rest as known. Never ask for a task's details in prose. If nothing important is missing, start it.
- Files they attached (by file id) can go in `input_ids`.
- Starting a task uses units from their monthly allowance: say so when you start one. A refine is \
free, search more costs 1 unit, a document is free.
- list_tasks and read_task show their tasks and what each found; follow_up_task refines ("only the \
Mission"), searches for more, or writes the findings into a document (not a job search: those are \
re-ranked and redrafted with the job search tools); update_task_item saves or \
dismisses a finding; cancel_task stops one. To show findings, add a `task` block with the task id and \
up to 5 finding ids you read."""


TASK_BLOCK = {
    "type": "object",
    "description": "A task you read or started, and up to 5 of its findings you read, by id.",
    "properties": {
        "task_id": {"type": "string"},
        "item_ids": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_BLOCK_ITEMS},
    },
    "required": ["task_id", "item_ids"],
}


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    from app.matcha.services.matcha_work.agent_tasks import chat

    session = state.sessions.get(KEY)
    if session is None or not isinstance(raw, dict):
        return None, ["Dropped a task block: no task was read or started"]
    task = session.tasks.get(str(raw.get("task_id") or ""))
    if task is None:
        return None, ["Dropped a task block: this run did not read that task"]
    items, warnings = [], []
    for item_id in raw.get("item_ids") or []:
        item = session.items.get(str(item_id))
        if item is None or item.get("task_id") != task["id"]:
            warnings.append("Dropped a finding this run did not read")
            continue
        items.append(item)
        if len(items) >= MAX_BLOCK_ITEMS:
            break
    return {"type": "task", "task": chat.card_view(task, top=items, limit=MAX_BLOCK_ITEMS)}, warnings


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Tasks",
        tools=(
            _tool("list_tasks", "read", "List the person's tasks and their units left this month.", {}, _list),
            _tool("read_task", "read",
                  "Read one task: what it is looking for, its latest result and its ranked findings "
                  "(20 at a time; follow next_offset).",
                  {"properties": {"task_id": _ID, "offset": {"type": "integer", "minimum": 0}},
                   "required": ["task_id"]}, _read, untrusted=True),
            _tool("start_task", "draft",
                  "Start a background task. Returns `missing` instead when a required field is not "
                  "known: then call ask_form.",
                  {"properties": {"playbook": _ID, "directive": _ID, "title": _ID,
                                  "brief": {"type": "object", "description": "Field key -> value"},
                                  "input_ids": _IDS},
                   "required": ["playbook", "directive", "brief"]}, _start),
            _tool("follow_up_task", "draft",
                  "On a finished task you read: refine it with the person's change, search for more "
                  "(optionally like some findings), or write its findings into a document.",
                  {"properties": {"task_id": _ID, "kind": {"type": "string", "enum": ["refine", "more", "document"]},
                                  "directive": _ID, "item_ids": _IDS},
                   "required": ["task_id", "kind", "directive", "item_ids"]}, _follow_up),
            _tool("cancel_task", "draft", "Stop a running task you read.",
                  {"properties": {"task_id": _ID}, "required": ["task_id"]}, _cancel),
            _tool("update_task_item", "draft",
                  "Save the person's status (saved, chosen, dismissed) or notes on a finding you read.",
                  {"properties": {"item_id": _ID,
                                  "status": {"type": ["string", "null"],
                                             "enum": ["new", "saved", "chosen", "dismissed", None]},
                                  "notes": {"type": ["string", "null"]}},
                   "required": ["item_id", "status", "notes"]}, _update_item),
        ),
        prompt_block=_prompt,
        private_only=True,
        allowance=ALLOWANCE,
        session_factory=lambda _ctx: TasksSession(),
        block_schemas={"task": TASK_BLOCK},
        gate=gate_block,
    )
