"""A task's findings as a document: fixed Markdown, saved as a journal note.

No model writes it. It is the brief, a table of the top findings, a section
per finding with each fact's evidence (and an apartment building's homes to
let, the ones that meet every limit first), and the sources, "as of" today.
Every link is a finding's own page or a fact's source, both of which a run
saw, or a home's own page or tour from the building's leasing system.
"""
from __future__ import annotations

import re
from datetime import date
from uuid import UUID

from app.database import decode_jsonb
from app.matcha.services.matcha_work.agent_card.schema import normalize_url

from . import items as items_mod, playbooks
from .research import batches
from .research.units import unit_line

MAX_ITEMS = 10
# A building's homes listed under it, the ones that fit first.
HOMES_LISTED = 8
_TABLE_COLUMNS = 4
_UNSAFE = re.compile(r"[\\`*_{}\[\]<>|#]")


def _md(text: object, limit: int = 200) -> str:
    """Plain text that can't become Markdown structure, a link or HTML."""
    flat = " ".join(str(text or "").split())[:limit]
    return _UNSAFE.sub(lambda m: "\\" + m.group(0), flat)


def _link(label: str, url: object) -> str:
    if not isinstance(url, str) or normalize_url(url) is None:
        return _md(label)
    safe = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("<", "%3C").replace(">", "%3E")
    return f"[{_md(label)}]({safe})"


def _fact(entry: dict) -> str:
    shown = _md(entry.get("display"), 120)
    if entry.get("status") != "verified":
        shown += " (unconfirmed)"
    evidence = entry.get("evidence") or {}
    if evidence.get("quote"):
        shown += f' — "{_md(evidence["quote"], 240)}"'
    if evidence.get("url"):
        shown += f" ({_link('source', evidence['url'])})"
    return shown


def _homes(row: dict) -> list[str]:
    homes = items_mod.units_view(row)
    if not homes:
        return []
    fit = [h for h in homes if h["fits"]]
    head = f"- Homes to let: {len(homes)} listed"
    if any(h["fits"] is not None for h in homes):
        head += f", {len(fit)} meet every limit"
    out = [head]
    for home in (fit + [h for h in homes if not h["fits"]])[:HOMES_LISTED]:
        line = f"  - {_md(unit_line(home), 300)}"
        if home.get("url") and home["url"] != row.get("url"):
            line += f" ({_link('its page', home['url'])})"
        if home.get("tour_url"):
            line += f" ({_link('tour', home['tour_url'])})"
        out.append(line)
    return out


def render(task: dict, rows: list[dict], *, today: date) -> tuple[str, str]:
    """(title, Markdown) for these findings, in the order given."""
    playbook = playbooks.get(task.get("playbook"))
    library = playbook.field_library if playbook else {}
    describe = (playbook.describe_constraint if playbook else None) or (lambda _c: "")
    plan = decode_jsonb(task.get("plan"), {}) or {}
    title = (task.get("title") or task.get("directive") or "Task")[:120]
    columns = [k for k in plan.get("fields") or [] if k in library][:_TABLE_COLUMNS]
    lines = [f"# {_md(title, 120)}", "", f"_{_md(task.get('directive'), 600)}_", "",
             f"As of {today:%B} {today.day}, {today.year}. {len(rows)} shown."]
    rules = [describe(c) for c in plan.get("constraints") or []]
    asked = [r for r in rules if r]
    for key, label in (("location", "Where"),):
        if plan.get(key):
            asked.insert(0, f"{label}: {plan[key]}")
    for key, label in (("must_haves", "Must have"), ("nice_to_haves", "Nice to have"), ("avoid", "Avoid")):
        if plan.get(key):
            asked.append(f"{label}: {', '.join(plan[key])}")
    if asked:
        lines += ["", "## What it looked for", *[f"- {_md(a, 300)}" for a in asked]]
    if rows:
        header = ["#", "Name", *[library[k].label for k in columns]]
        lines += ["", "## Top picks", "", "| " + " | ".join(header) + " |",
                  "|" + "|".join("---" for _ in header) + "|"]
        for i, row in enumerate(rows, start=1):
            fields = decode_jsonb(row.get("fields"), {}) or {}
            cells = [str(i), _link(row.get("title") or "Untitled", row.get("url"))]
            for key in columns:
                entry = fields.get(key) or {}
                cell = _md(entry.get("display"), 60) if entry else "—"
                if entry and entry.get("status") != "verified":
                    cell += " (unconfirmed)"
                cells.append(cell)
            lines.append("| " + " | ".join(cells) + " |")
    sources: list[str] = []
    for i, row in enumerate(rows, start=1):
        fields = decode_jsonb(row.get("fields"), {}) or {}
        lines += ["", f"## {i}. {_md(row.get('title'), 160)}"]
        if row.get("subtitle"):
            lines.append(_md(row["subtitle"], 200))
        if row.get("url"):
            lines.append(_link("Open its page", row["url"]))
            sources.append(row["url"])
        for key, entry in fields.items():
            if key in library and isinstance(entry, dict):
                lines.append(f"- {library[key].label}: {_fact(entry)}")
                url = (entry.get("evidence") or {}).get("url")
                if isinstance(url, str):
                    sources.append(url)
        lines += _homes(row)
        reasons = decode_jsonb(row.get("fit_reasons"), []) or []
        if reasons:
            lines.append(f"- Why it fits: {_md('; '.join(reasons), 400)}")
        if row.get("notes"):
            lines.append(f"- Your notes: {_md(row['notes'], 1000)}")
    unique = [u for u in dict.fromkeys(sources) if normalize_url(u)]
    if unique:
        lines += ["", "## Sources", *[f"- {_link(u, u)}" for u in unique[:60]]]
    return f"{title} — findings", "\n".join(lines) + "\n"


async def pick_rows(conn, task_id: UUID, item_ids: list[UUID]) -> list[dict]:
    """The findings a document covers: the ones asked for, else what the
    person chose or saved, then the best of the rest."""
    if item_ids:
        rows = await conn.fetch(
            """SELECT * FROM mw_agent_task_items WHERE task_id = $1 AND id = ANY($2::uuid[])
               ORDER BY rank NULLS LAST, created_at""",
            task_id, item_ids,
        )
    else:
        # What the person has been shown (`research/batches.py`), never the waiting list.
        rows = await conn.fetch(
            f"""SELECT i.* FROM mw_agent_task_items i JOIN mw_agent_tasks t ON t.id = i.task_id
                WHERE i.task_id = $1 AND (i.rank_band < 9 OR i.user_state IN ('saved', 'chosen'))
                  AND {batches.SHOWN_SQL}
                ORDER BY CASE i.user_state WHEN 'chosen' THEN 0 WHEN 'saved' THEN 1 ELSE 2 END,
                         i.rank NULLS LAST, i.created_at
                LIMIT {MAX_ITEMS}""",
            task_id,
        )
    return [dict(row) for row in rows][:MAX_ITEMS * 2]


async def write(conn, task: dict, *, item_ids: list[UUID], today: date) -> dict:
    """Write the note on the caller's connection. Returns what the round keeps."""
    from app.matcha.services.matcha_work import journal_service

    rows = await pick_rows(conn, task["id"], item_ids)
    title, markdown = render(task, rows, today=today)
    note = await journal_service.create_note_direct(
        conn, task["user_id"], task["company_id"], title=title, content=markdown,
        description=(task.get("directive") or "")[:300] or None,
    )
    return {"journal_id": note["id"], "entry_id": note["entry_id"], "title": title, "items": len(rows)}
