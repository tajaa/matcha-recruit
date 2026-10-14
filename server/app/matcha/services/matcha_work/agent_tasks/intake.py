"""Asking for what a task needs: a short form, built from the playbook alone.

In chat, Espresso works out which playbook fits and what the person already
said. When something that matters is missing it calls `ask_form`, naming only
playbook and field keys; the form itself (labels, types, options, file rules,
the consent text) comes from the playbook's `intake`, so the model can never
invent a field or reword a disclosure.

The form is an ordinary assistant question (`mw_agent_card_prompts`, kind
`ask_form`). Two ways to answer it:

  submit    `answer_form`: the values are checked against the same fields,
            the files against the file fields, and the task starts. No model
            run, so no daily request. The prompt's id is the task's request
            id: a retried submit gets the same task.
  typed     any reply in the conversation answers it the way it answers
            `ask_user` (`chat_entry`), and the next run takes it from there.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.database import connection_or_direct, decode_jsonb

from . import allowance, chat, enqueue, playbooks, service
from .playbook import IntakeField, Playbook

KIND = "ask_form"
MAX_OPTIONAL = 3
MAX_TEXT = 200
MAX_LIST = 10
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_YES = {"yes", "true", "y", "1"}
_NO = {"no", "false", "n", "0"}
ANSWERED = "form"


# ── values ───────────────────────────────────────────────────────────────────

def clean_value(spec: IntakeField, raw: Any) -> Any:
    """The value as the task keeps it; None for "not given". Raises
    ValueError with what is wrong, in the person's terms."""
    if raw is None or raw == "" or raw == []:
        return None
    kind = spec.type
    if kind in ("file", "consent"):
        raise ValueError("isn't a value")
    if kind in ("text", "location"):
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            raise ValueError("should be text")
        return " ".join(str(raw).split())[:MAX_TEXT] or None
    if kind in ("number", "money"):
        if isinstance(raw, bool):
            raise ValueError("should be a number")
        try:
            value = float(str(raw).replace(",", "").replace("$", "").strip())
        except ValueError as exc:
            raise ValueError("should be a number") from exc
        if not (0 <= value < 1e9):
            raise ValueError("is out of range")
        return value
    if kind == "date":
        try:
            return date.fromisoformat(str(raw)[:10]).isoformat()
        except ValueError as exc:
            raise ValueError("should be a date (YYYY-MM-DD)") from exc
    if kind == "time":
        match = _TIME.match(str(raw).strip())
        if not match:
            raise ValueError("should be a time (HH:MM)")
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    if kind == "select":
        if raw not in spec.options:
            raise ValueError("isn't one of the choices")
        return raw
    if kind == "multi_select":
        values = raw if isinstance(raw, list) else [raw]
        if any(v not in spec.options for v in values):
            raise ValueError("has a choice that isn't offered")
        return list(dict.fromkeys(values))
    if kind == "boolean":
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _YES or text in _NO:
            return text in _YES
        raise ValueError("should be yes or no")
    if kind == "list":
        values = raw if isinstance(raw, list) else str(raw).split(",")
        out = []
        for value in values:
            text = " ".join(str(value).split())[:120]
            if text and text.casefold() not in {o.casefold() for o in out}:
                out.append(text)
        return out[:MAX_LIST] or None
    raise ValueError("isn't a field it can take")


def clean_values(playbook: Playbook, raw: dict) -> tuple[dict, dict[str, str]]:
    """(the values it could read, field key -> what is wrong)."""
    fields = {f.key: f for f in playbook.intake}
    clean, errors = {}, {}
    for key, value in (raw or {}).items():
        spec = fields.get(key)
        if spec is None or spec.type in ("file", "consent"):
            continue
        try:
            made = clean_value(spec, value)
        except ValueError as exc:
            errors[key] = f"{spec.label} {exc}."
            continue
        if made is not None:
            clean[key] = made
    return clean, errors


# ── the form ─────────────────────────────────────────────────────────────────

def build_form(playbook: Playbook, *, directive: str, title: str, known: dict, missing: list,
               note: str, consent_needed: bool) -> dict:
    """The question payload: what to ask, from the playbook's fields only.

    Asked: required fields not yet known, fields the model named as missing,
    and `ask="always"` ones. Then up to MAX_OPTIONAL `if_missing` fields the
    person may fill or leave. `never` fields are asked only when named."""
    known_clean, _ = clean_values(playbook, known or {})
    named = {k for k in (missing or []) if isinstance(k, str)}
    asked, optional = [], []
    for spec in playbook.intake:
        if spec.type == "consent":
            continue
        if spec.ask == "never" and spec.key not in named:
            continue
        if spec.key in known_clean and spec.ask != "always":
            continue
        if spec.required or spec.key in named or spec.ask == "always":
            asked.append(spec.key)
    for spec in playbook.intake:
        if len(optional) >= MAX_OPTIONAL:
            break
        if spec.key not in asked and spec.key not in known_clean and spec.ask == "if_missing":
            optional.append(spec.key)
    if not asked and not optional and not consent_needed:
        raise ValueError("Nothing is missing: start the task with start_task.")
    return {
        "kind": KIND,
        "question": " ".join(str(note or "").split())[:300] or f"A few details for this {playbook.label.lower()} task",
        "playbook": playbook.key,
        "directive": " ".join(directive.split())[:4000],
        "title": " ".join(str(title or "").split())[:120],
        "known": known_clean,
        "fields": asked,
        "optional": optional,
        "consent": playbook.consent if consent_needed else None,
    }


def _shown(spec: IntakeField, value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if spec.type == "money" and isinstance(value, (int, float)):
        return f"${value:,.0f}"
    return str(value)


def form_view(payload: dict) -> dict:
    """What both apps render: the fields to fill, what is already known, and
    the disclosure to agree to when the playbook needs one."""
    from app.matcha.services.matcha_work.agent_runtime import consent

    playbook = playbooks.get(payload.get("playbook"))
    fields = {f.key: f for f in playbook.intake} if playbook else {}
    known = payload.get("known") or {}
    optional = set(payload.get("optional") or [])
    return {
        "question": payload.get("question") or "",
        "buttons": [],
        "form": {
            "playbook": payload.get("playbook"),
            "label": playbook.label if playbook else "",
            "title": payload.get("title") or "",
            "directive": payload.get("directive") or "",
            "fields": [{**fields[k].view(), "optional": k in optional, "value": known.get(k)}
                       for k in [*(payload.get("fields") or []), *(payload.get("optional") or [])] if k in fields],
            "known": [{"key": k, "label": fields[k].label, "value": v, "shown": _shown(fields[k], v)}
                      for k, v in known.items() if k in fields],
            "consent": consent.disclosure_view(payload["consent"]) if payload.get("consent") else None,
            "units": allowance.WEIGHTS.get(payload.get("playbook") or "", 0),
            "submit_label": "Start",
        },
    }


def form_text(payload: dict) -> str:
    """The message text: what older apps show, and what a later run replays."""
    view = form_view(payload)["form"]
    lines = [payload.get("question") or ""]
    wanted = [f["label"] + ("" if not f["optional"] else " (optional)") for f in view["fields"]]
    if wanted:
        lines.append("Tell me: " + "; ".join(wanted) + ".")
    lines.append("Reply here, or fill in the form.")
    return "\n".join(line for line in lines if line)[:1500]


def _parse(ctx, state, args: dict) -> dict:
    """`ask_form`'s arguments as the run's question. Raises ValueError (told
    to the model) for a playbook or ask it can't use."""
    playbook = playbooks.get(str(args.get("playbook") or ""))
    if playbook is None or playbook.engine != "chain" or not playbook.env_ready():
        raise ValueError("Use one of the playbooks start_task accepts.")
    directive = " ".join(str(args.get("directive") or "").split())
    if len(directive) < 3:
        raise ValueError("Give the directive: what the person asked for, in their words.")
    known = args.get("known") if isinstance(args.get("known"), dict) else {}
    missing = args.get("missing") if isinstance(args.get("missing"), list) else []
    needs_consent = bool(playbook.consent) and playbook.consent not in (getattr(ctx, "grants", None) or {})
    return build_form(playbook, directive=directive, title=str(args.get("title") or ""), known=known,
                      missing=missing, note=str(args.get("note") or ""), consent_needed=needs_consent)


def ask_form_tool():
    from app.matcha.services.matcha_work.agent_runtime.registry import AgentTool

    return AgentTool(
        name="ask_form",
        effect="ask",
        description=(
            "Ask the person for a task's missing details with a short form, then stop. Name the "
            "playbook, their directive, what they already told you (`known`, by field key) and the "
            "field keys still missing. The form is built from the playbook; you only pick fields. "
            "Use this, not ask_user, for a task's details, and never ask for them in prose."
        ),
        parameters={
            "type": "object",
            "properties": {
                "playbook": {"type": "string", "enum": sorted(k for k, p in playbooks.PLAYBOOKS.items()
                                                              if p.engine == "chain")},
                "directive": {"type": "string", "description": "What they asked for, in their words"},
                "title": {"type": "string", "description": "A short name for the task"},
                "known": {"type": "object", "description": "Field key -> what they already said"},
                "missing": {"type": "array", "items": {"type": "string"}, "description": "Field keys to ask"},
                "note": {"type": "string", "description": "One short line above the form"},
            },
            "required": ["playbook", "directive", "known", "missing"],
        },
        step_kind="ask",
        parse_ask=_parse,
    )


# ── answering ────────────────────────────────────────────────────────────────

async def _check_files(conn, playbook: Playbook, user_id: UUID, input_ids: list[UUID]) -> None:
    if not input_ids:
        return
    specs = [f for f in playbook.intake if f.type == "file"]
    if not specs:
        raise HTTPException(status_code=422, detail="This form takes no files.")
    kinds = {kind for spec in specs for kind in spec.accept}
    most = sum(spec.max_count for spec in specs)
    biggest = max(spec.max_bytes for spec in specs)
    if len(set(input_ids)) > most:
        raise HTTPException(status_code=422, detail=f"At most {most} files.")
    rows = await conn.fetch(
        "SELECT id, kind, size_bytes FROM mw_agent_inputs WHERE id = ANY($1::uuid[]) AND user_id = $2",
        list(set(input_ids)), user_id,
    )
    if len(rows) != len(set(input_ids)):
        raise HTTPException(status_code=404, detail="One of those files wasn't found.")
    for row in rows:
        if row["kind"] not in kinds:
            raise HTTPException(status_code=422, detail="One of those files isn't a kind this form takes.")
        if int(row["size_bytes"] or 0) > biggest:
            raise HTTPException(status_code=422, detail="One of those files is too large.")


async def answer_form(user, prompt_id: UUID, body) -> dict:
    """Submit a form: check it, start the task, close the question. `body`:
    `FormAnswer`. Returns the task."""
    from app.matcha.models.matcha_work.agent_tasks import AgentTaskCreate
    from app.matcha.services.matcha_work.agent_runtime import prompts

    async with connection_or_direct() as conn:
        prompt = await conn.fetchrow(
            """SELECT *, (status = 'open' AND expires_at > NOW()) AS live
               FROM mw_agent_card_prompts WHERE id = $1 AND kind = 'ask_form'""",
            prompt_id,
        )
    if prompt is None or prompt["owner_user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Form not found.")
    if prompt["agent_task_id"] is not None:
        return await service.get_task(prompt["agent_task_id"], user.id, mark_seen=False)  # a retried submit
    if not prompt["live"]:
        raise HTTPException(status_code=409, detail="That form has closed. Ask Espresso again.")
    payload = decode_jsonb(prompt["payload"], {}) or {}
    playbook = playbooks.get(payload.get("playbook"))
    if playbook is None:
        raise HTTPException(status_code=409, detail="Espresso can't do that kind of task any more.")
    values, errors = clean_values(playbook, {**(payload.get("known") or {}), **(body.values or {})})
    for spec in playbook.intake:
        if spec.required and spec.type not in ("file", "consent") and spec.key not in values:
            errors.setdefault(spec.key, f"{spec.label} is needed.")
    if errors:
        raise HTTPException(status_code=422, detail={"code": "form_invalid", "errors": errors})
    async with connection_or_direct() as conn:
        await _check_files(conn, playbook, user.id, list(body.input_ids or []))
    task = await enqueue.create_task(
        user, prompt["company_id"],
        AgentTaskCreate(request_id=prompt_id, playbook=playbook.key, directive=payload.get("directive") or "",
                        title=payload.get("title") or "", brief=values, input_ids=list(body.input_ids or []),
                        consent_version=body.consent_version),
        origin=(prompt["channel_id"], prompt["message_id"]),
    )
    task_id = UUID(task["id"])
    async with connection_or_direct() as conn, conn.transaction():
        claimed = await conn.fetchval(
            """UPDATE mw_agent_card_prompts
               SET status = 'answered', answer = $2, answered_by = $3, answered_at = NOW(), agent_task_id = $4
               WHERE id = $1 AND status = 'open'
               RETURNING TRUE""",
            prompt_id, ANSWERED, user.id, task_id,
        )
        message = await chat.post_card(conn, task, company_id=prompt["company_id"], channel_id=prompt["channel_id"],
                                       event="started") if claimed else None
    if claimed:
        from app.matcha.services.matcha_work.agent_card import chat_flow
        from app.matcha.services.matcha_work.project_agent.chat import broadcast_espresso_message

        await chat_flow.broadcast_prompt_updates([prompts.update_event(dict(prompt), "answered", ANSWERED)])
        await broadcast_espresso_message(message)
    return task
