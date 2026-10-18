"""Emailing the person what a task found, once it finishes.

A task runs on the server, so the person can start one and close Espresso.
When it ends (done, or stopped), the account's email gets its headline, its
summary and its top picks, each with its key facts, the homes that fit and
its link: everything in it is read from the task's own rows, like the chat
card (`chat.py`).

- **Once a round.** `service.close_round` settles a round exactly once, and
  only a round it settled now is emailed (`orchestrator._stopped`). A job
  search is emailed once, when its pointer is completed (`job_tasks`).
- **Not while the person is there.** A round that ends within `EMAIL_AFTER`
  of being asked (a refine that only re-sorts, a document) sends none; the
  bell and the chat card still say so.
- **Best effort and pool-free.** An email that fails never fails the task,
  and reserved test domains are never sent to (the email service's guard).
"""
from __future__ import annotations

import html
import logging
from datetime import timedelta
from uuid import UUID

from app.database import decode_jsonb

from . import items as items_mod
from .chat import TOP_ITEMS, picked_from, picks

logger = logging.getLogger(__name__)

FINISHED = ("done", "failed")
EMAIL_AFTER = timedelta(seconds=60)
FACTS = 4
FROM_NAME = "Espresso"
TITLE_CHARS = 80
TEXT_CHARS = 600


def _web(url) -> str | None:
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


def homes_line(homes: dict | None) -> str | None:
    """"3 of 18 homes fit · from $2,949/mo", word for word as the app's
    `AgentTaskHomes.line` says it."""
    count = (homes or {}).get("count")
    if not count:
        return None
    fit, low = homes.get("fit"), homes.get("from")
    noun = "home" if count == 1 else "homes"
    if fit == 0:
        return f"None of {count} {noun} fit"
    line = f"{count} {noun} listed" if fit is None else f"{fit} of {count} {noun} fit"
    return f"{line} · from ${low:,.0f}/mo" if low else line


def facts(item: dict, columns: list[dict]) -> list[tuple[str, str]]:
    """Up to FACTS (label, value) pairs: the plan's columns in order, then
    the rest. Unconfirmed ones and the subtitle repeated are left out."""
    labels = {c["key"]: c.get("label") or c["key"] for c in columns if c.get("key")}
    fields = item.get("fields") or {}
    order = [k for k in labels if k in fields] + [k for k in fields if k not in labels]
    out = []
    for key in order:
        field = fields.get(key) or {}
        shown = str(field.get("display") or "").strip()
        if not shown or field.get("status") == "unknown" or shown == item.get("subtitle"):
            continue
        out.append((labels.get(key) or key.replace("_", " ").capitalize(), shown[:120]))
        if len(out) == FACTS:
            break
    return out


def compose(task: dict, *, summary: dict | None, top: list[dict], columns: list[dict]) -> dict:
    """The email for a task that just finished: subject, html and text."""
    summary = summary or {}
    progress = decode_jsonb(task.get("progress"), {}) or {}
    name = (task.get("title") or task.get("directive") or "Your task")[:TITLE_CHARS]
    done = task.get("status") == "done"
    headline = str(summary.get("headline") or "").strip() if done else ""
    if done:
        lines = [str(summary.get("summary") or progress.get("note") or "").strip()]
    else:
        lines = [str(task.get("error") or progress.get("note") or "It couldn't go on.").strip()]
    lines = [line[:TEXT_CHARS] for line in lines if line]
    why = {str(p.get("item_id")): str(p.get("why") or "").strip()
           for p in summary.get("top") or [] if isinstance(p, dict)}
    picked = []
    for item in top[:TOP_ITEMS]:
        picked.append({
            "title": item.get("title") or "",
            "subtitle": item.get("subtitle") or "",
            "url": _web(item.get("url")),
            "image": _web(((item.get("images") or [{}])[0] or {}).get("url")),
            "facts": facts(item, columns),
            "homes": homes_line(item.get("homes")),
            "why": why.get(str(item.get("id")), "")[:TEXT_CHARS],
        })
    subject = f"{'Done' if done else 'Stopped'}: {name}"
    leave = "Open Espresso and go to Tasks to see everything it found, refine it or search for more."
    return {
        "subject": subject,
        "html": _html(subject, headline, lines, picked, leave),
        "text": _text(subject, headline, lines, picked, leave),
    }


def _html(subject, headline, lines, picked, leave) -> str:
    e = html.escape
    parts = [f'<h2 style="margin:0 0 6px;font-size:20px;color:#1c1917">{e(subject)}</h2>']
    if headline:
        parts.append(f'<p style="margin:0 0 10px;font-size:16px;font-weight:600;color:#1c1917">{e(headline)}</p>')
    parts += [f'<p style="margin:0 0 14px;color:#44403c">{e(line)}</p>' for line in lines]
    for n, pick in enumerate(picked, 1):
        title = e(pick["title"])
        if pick["url"]:
            title = f'<a href="{e(pick["url"])}" style="color:#7c4a1e;text-decoration:none">{title}</a>'
        image = (f'<td width="104" valign="top" style="padding-right:12px"><img src="{e(pick["image"])}" '
                 f'width="96" height="72" alt="" style="border-radius:6px;display:block;object-fit:cover;'
                 f'background:#f5f5f4"></td>') if pick["image"] else ""
        detail = [f'<div style="font-size:15px;font-weight:600">{n}. {title}</div>']
        if pick["subtitle"]:
            detail.append(f'<div style="color:#78716c;font-size:13px">{e(pick["subtitle"])}</div>')
        if pick["facts"]:
            shown = " · ".join(f"{e(label)}: {e(value)}" for label, value in pick["facts"])
            detail.append(f'<div style="font-size:13px;margin-top:4px">{shown}</div>')
        if pick["homes"]:
            detail.append(f'<div style="font-size:13px;color:#15803d;margin-top:2px">{e(pick["homes"])}</div>')
        if pick["why"]:
            detail.append(f'<div style="font-size:13px;color:#44403c;margin-top:4px">{e(pick["why"])}</div>')
        parts.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 14px">'
                     f'<tr>{image}<td valign="top">{"".join(detail)}</td></tr></table>')
    parts.append(f'<p style="margin:18px 0 0;color:#78716c;font-size:13px">{e(leave)}<br>'
                 f'You get this email when a task you started in Espresso finishes.</p>')
    return ('<!DOCTYPE html><html><body style="margin:0;padding:0">'
            '<div style="max-width:600px;margin:0 auto;padding:24px;font-family:-apple-system,'
            "BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.5;color:#1c1917\">"
            + "".join(parts) + "</div></body></html>")


def _text(subject, headline, lines, picked, leave) -> str:
    out = [subject, ""]
    if headline:
        out += [headline, ""]
    out += lines + ([""] if lines else [])
    for n, pick in enumerate(picked, 1):
        out.append(f"{n}. {pick['title']}" + (f" ({pick['subtitle']})" if pick["subtitle"] else ""))
        if pick["facts"]:
            out.append("   " + " · ".join(f"{label}: {value}" for label, value in pick["facts"]))
        if pick["homes"]:
            out.append(f"   {pick['homes']}")
        if pick["why"]:
            out.append(f"   {pick['why']}")
        if pick["url"]:
            out.append(f"   {pick['url']}")
        out.append("")
    out += [leave, "You get this email when a task you started in Espresso finishes."]
    return "\n".join(out)


async def _recipient(conn, user_id: UUID) -> str | None:
    row = await conn.fetchrow("SELECT email, is_active, is_suspended FROM users WHERE id = $1", user_id)
    if row is None or not row["email"] or row["is_active"] is False or row["is_suspended"]:
        return None
    return row["email"]


async def _send(to: str, message: dict, task_id) -> bool:
    from app.core.services.email import get_email_service

    service = get_email_service()
    if not service.is_configured():
        logger.warning("task email skipped: email not configured task=%s", task_id)
        return False
    return await service.send_email_with_fallback(
        to_email=to, to_name=None, subject=message["subject"], html_content=message["html"],
        text_content=message["text"], from_name=FROM_NAME,
    )


async def round_finished(conn, task_id: UUID) -> bool:
    """Email the task's round that just ended, unless it was quick. Never raises."""
    from .service import plan_view

    try:
        task = await conn.fetchrow(
            """SELECT t.id, t.user_id, t.playbook, t.title, t.directive, t.status, t.progress, t.error,
                      t.plan, r.summary, r.created_at AS asked_at, r.completed_at AS settled_at
               FROM mw_agent_tasks t
               JOIN mw_agent_task_rounds r ON r.task_id = t.id AND r.n = t.current_round
               WHERE t.id = $1 AND t.deleted_at IS NULL""",
            task_id,
        )
        if task is None or task["status"] not in FINISHED:
            return False
        if task["asked_at"] and task["settled_at"] and task["settled_at"] - task["asked_at"] < EMAIL_AFTER:
            return False
        to = await _recipient(conn, task["user_id"])
        if to is None:
            return False
        summary = decode_jsonb(task["summary"], {}) or {}
        top = picks([items_mod.item_summary(r) for r in await picked_from(conn, task_id, summary)],
                    summary) if task["status"] == "done" else []
        message = compose(dict(task), summary=summary, top=top, columns=plan_view(dict(task))["columns"])
        from ..recaps.delivery import own_mail
        if await own_mail(conn, kind="research", source_id=task_id, message=message):
            return True
        return await _send(to, message, task_id)
    except Exception:
        logger.warning("task email failed task=%s", task_id, exc_info=True)
        return False


async def search_finished(conn, task: dict, top: list[dict]) -> bool:
    """Email a job search's task once it finished. Never raises."""
    try:
        if task.get("status") not in FINISHED:
            return False
        to = await _recipient(conn, task["user_id"])
        if to is None:
            return False
        message = compose(task, summary=None, top=top, columns=[])
        from ..recaps.delivery import own_mail
        if task.get("job_search_id") and await own_mail(conn, kind="jobs", source_id=task["job_search_id"], message=message):
            return True
        return await _send(to, message, task.get("id"))
    except Exception:
        logger.warning("job search task email failed task=%s", task.get("id"), exc_info=True)
        return False
