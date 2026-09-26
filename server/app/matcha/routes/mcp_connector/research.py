"""Research-card operations the MCP connector exposes.

The MVP of "run a kanban research card on the person's own Claude / ChatGPT
plan": the person's AI client reads the card, does the web research itself, and
hands the finished report back. Matcha spends no model tokens on it.

Everything here takes an already-authenticated `CurrentUser` and re-derives
access from it on every call — never from ids the model supplies:

- a card is only visible through `_verify_project_access`, the same guard the
  kanban REST routes use (company boards, collaborator boards, the werk-lite
  sensitive-project hiding for employees);
- the report lands through the same task-file upload policy and the same
  `update_project_task` / `log_task_activity` writes a person's own edits take.

The published report follows the AutoPR research lane's file contract
(`research-report-<id8>-r<N>.md`, a `note` announcing it, the card moved to
`review`) so Espresso and the web board render it with no client change, and so
a later AutoPR revision round finds it as the previous version.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from app.database import get_connection

logger = logging.getLogger(__name__)

RESEARCH_CATEGORY = "research"
# Where a research card waits for work. `in_progress` is listed too so a
# person can find the card their assistant already claimed.
_OPEN_COLUMNS = ("todo", "changes_requested", "in_progress")
_CLAIMABLE_COLUMNS = ("todo", "changes_requested")
_SENSITIVE_PROJECT_TYPES = ("discipline", "recruiting")

REPORT_MAX_BYTES = 200_000
CARD_NOTE_MAX = 240
_INLINE_TEXT_MAX = 64_000
_INLINE_TEXT_EXTENSIONS = (".md", ".txt", ".csv", ".json")
_REPORT_NAME_RE = re.compile(r"^research-report-.*\.md$")

REQUIRED_HEADINGS = ("### Summary", "### Findings", "### Recommendation", "### Sources")
REPORT_CONTRACT = {
    "format": "markdown",
    "required_headings_in_order": list(REQUIRED_HEADINGS),
    "optional_headings": ["### How it applies", "### Confidence"],
    "citations": "Cite every external claim inline as [n], resolving to a numbered entry "
    "under ### Sources with the page title and full URL. Only list pages you actually read.",
    "max_bytes": REPORT_MAX_BYTES,
    "card_note": f"One line, at most {CARD_NOTE_MAX} characters, no line breaks: the "
    "takeaway a teammate sees on the card.",
}


class ConnectorError(Exception):
    """A refusal the model should read and act on. The message is shown to it
    verbatim, so it names what to do next and never leaks another tenant's data.
    `status_code` is what the REST launch route maps it to."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


_NOT_VISIBLE = "No research card with that id is visible to you."


def _http_to_connector_error(exc: HTTPException) -> ConnectorError:
    if exc.status_code == 404:
        return ConnectorError(_NOT_VISIBLE, 404)
    if exc.status_code == 403:
        return ConnectorError("You do not have access to that board.", 403)
    return ConnectorError(str(exc.detail), exc.status_code)


def _parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(str(value).strip())
    except (TypeError, ValueError):
        raise ConnectorError(f"{label} must be a UUID like 3f2b8a8e-…; got {value!r}.")


async def _load_card(task_id: UUID) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.id, t.project_id, t.title, t.description, t.category,
                   t.board_column, t.status, t.priority, t.progress_note,
                   t.review_note, t.updated_at, t.autopr_run_requested_at,
                   p.title AS project_title
              FROM mw_tasks t
              JOIN mw_projects p ON p.id = t.project_id
             WHERE t.id = $1
            """,
            task_id,
        )
    return dict(row) if row else None


async def _authorized_card(current_user, task_id: UUID) -> tuple[dict, dict, Optional[str]]:
    """(card, project, role) or ConnectorError. Existence is only confirmed
    after access passes, so a guessed id in another tenant reads as absent."""
    from app.matcha.routes.matcha_work._shared import _verify_project_access

    card = await _load_card(task_id)
    if not card:
        raise ConnectorError(_NOT_VISIBLE, 404)
    try:
        project, role = await _verify_project_access(card["project_id"], current_user)
    except HTTPException as exc:
        raise _http_to_connector_error(exc)
    if card["category"] != RESEARCH_CATEGORY:
        raise ConnectorError(
            "That card is not a research card. Only cards created with the Research "
            "template can be worked through this connector."
        )
    return card, project, role


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


# ── list ─────────────────────────────────────────────────────────────────────


async def list_research_cards(
    current_user, *, project_id: Optional[str] = None, limit: int = 20
) -> dict[str, Any]:
    from app.matcha.dependencies import get_client_company_id

    limit = max(1, min(int(limit or 20), 50))
    company_id = None if current_user.role == "admin" else await get_client_company_id(current_user)
    args: list[Any] = [company_id, current_user.id, list(_OPEN_COLUMNS), RESEARCH_CATEGORY]
    filters = [
        "t.category = $4",
        "t.board_column = ANY($3::text[])",
        "COALESCE(t.status, 'pending') <> 'cancelled'",
        """(
            ($1::uuid IS NOT NULL AND p.company_id = $1)
            OR EXISTS (
                SELECT 1 FROM mw_project_collaborators pc
                 WHERE pc.project_id = p.id AND pc.user_id = $2 AND pc.status = 'active'
            )
        )""",
    ]
    if current_user.role == "employee":
        args.append(list(_SENSITIVE_PROJECT_TYPES))
        filters.append(f"COALESCE(p.project_type, '') <> ALL(${len(args)}::text[])")
    if project_id:
        args.append(_parse_uuid(project_id, "project_id"))
        filters.append(f"t.project_id = ${len(args)}")
    args.append(limit)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT t.id, t.project_id, p.title AS project_title, t.title,
                   t.board_column, t.priority, t.updated_at,
                   t.autopr_run_requested_at
              FROM mw_tasks t
              JOIN mw_projects p ON p.id = t.project_id
             WHERE {' AND '.join(filters)}
             ORDER BY t.updated_at DESC NULLS LAST
             LIMIT ${len(args)}
            """,
            *args,
        )
    cards = [
        {
            "task_id": str(r["id"]),
            "project_id": str(r["project_id"]),
            "project": r["project_title"],
            "title": r["title"],
            "column": r["board_column"],
            "priority": r["priority"],
            "queued_for_autopr": r["autopr_run_requested_at"] is not None,
            "updated_at": _iso(r["updated_at"]),
        }
        for r in rows
    ]
    return {"cards": cards, "count": len(cards)}


# ── get ──────────────────────────────────────────────────────────────────────


async def _attachment_summaries(project_id: UUID, task_id: UUID) -> tuple[list[dict], Optional[dict]]:
    from app.core.services.storage import get_storage
    from app.matcha.services.matcha_work import project_file_service

    files = await project_file_service.list_task_files(project_id, task_id)
    storage = get_storage()
    attachments: list[dict] = []
    reports = [f for f in files if _REPORT_NAME_RE.match(f.get("filename") or "")]
    latest_report = max(reports, key=lambda f: f.get("created_at") or datetime.min.replace(tzinfo=timezone.utc)) if reports else None

    async def read_text(record: dict) -> Optional[str]:
        size = record.get("file_size") or 0
        if size and size > _INLINE_TEXT_MAX:
            return None
        try:
            data = await storage.download_file(record["storage_url"])
        except Exception:
            logger.warning("[mcp] could not read attachment %s", record.get("id"), exc_info=True)
            return None
        if len(data) > _INLINE_TEXT_MAX:
            return None
        return data.decode("utf-8", errors="replace")

    for f in files:
        name = f.get("filename") or ""
        entry = {
            "filename": name,
            "content_type": f.get("content_type"),
            "size_bytes": f.get("file_size"),
            "uploaded_at": _iso(f.get("created_at")),
        }
        if latest_report is not None and f is latest_report:
            continue  # returned separately as previous_report
        if name.lower().endswith(_INLINE_TEXT_EXTENSIONS):
            entry["text"] = await read_text(f)
        attachments.append(entry)

    previous = None
    if latest_report is not None:
        previous = {
            "filename": latest_report.get("filename"),
            "uploaded_at": _iso(latest_report.get("created_at")),
            "text": await read_text(latest_report),
        }
    return attachments, previous


async def get_research_card(current_user, *, task_id: str) -> dict[str, Any]:
    card, _project, _role = await _authorized_card(current_user, _parse_uuid(task_id, "task_id"))
    attachments, previous_report = await _attachment_summaries(card["project_id"], card["id"])
    return {
        "task_id": str(card["id"]),
        "project_id": str(card["project_id"]),
        "project": card["project_title"],
        "title": card["title"],
        "description": card["description"] or "",
        "review_note": card.get("review_note") or None,
        "column": card["board_column"],
        "priority": card["priority"],
        "attachments": attachments,
        "previous_report": previous_report,
        "report_contract": REPORT_CONTRACT,
        "next_step": (
            "Call claim_research_card before researching, then attach_research_report "
            "with the finished markdown."
            if card["board_column"] in _CLAIMABLE_COLUMNS
            else "This card is already in progress; attach_research_report when done."
            if card["board_column"] == "in_progress"
            else "This card is not waiting for research right now."
        ),
    }


# ── claim ────────────────────────────────────────────────────────────────────


async def claim_research_card(current_user, *, task_id: str, client_name: str) -> dict[str, Any]:
    from app.matcha.routes.matcha_work._shared import _can_edit_project
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    card, project, role = await _authorized_card(current_user, _parse_uuid(task_id, "task_id"))
    if not _can_edit_project(role):
        raise ConnectorError("You can view this board but not move its cards.")
    if card["board_column"] == "in_progress":
        return {"claimed": True, "already_in_progress": True, "task_id": str(card["id"])}
    if card["board_column"] not in _CLAIMABLE_COLUMNS:
        raise ConnectorError(
            f"The card is in '{card['board_column']}', not waiting for research. "
            "Ask the person to move it back to To do first."
        )
    if card["autopr_run_requested_at"] is not None:
        raise ConnectorError(
            "This card is queued for the AutoPR bot. Ask the person to unqueue it in "
            "Espresso before researching it here, so the work is not done twice."
        )
    # Moving to In Progress is what keeps AutoPR off it: the bot only ever
    # selects cards sitting in To do / Changes requested.
    try:
        await pt_svc.update_project_task(
            card["project_id"],
            card["id"],
            {"board_column": "in_progress"},
            actor_user_id=current_user.id,
            project_title=project.get("title"),
        )
    except ValueError as exc:
        raise ConnectorError(str(exc))
    await pt_svc.log_task_activity(
        project_id=card["project_id"],
        task_id=card["id"],
        actor_user_id=current_user.id,
        kind="note",
        body=f"Researching this with {client_name} (on your own plan, through the Matcha connector).",
    )
    logger.info("[mcp] research claim task=%s user=%s client=%s", card["id"], current_user.id, client_name)
    return {"claimed": True, "already_in_progress": False, "task_id": str(card["id"])}


# ── attach ───────────────────────────────────────────────────────────────────


def validate_report(report_markdown: str, card_note: str) -> tuple[str, str]:
    """Normalized (report, card_note) or ConnectorError explaining the fix."""
    report = (report_markdown or "").strip()
    if not report:
        raise ConnectorError("report_markdown is empty.")
    if len(report.encode("utf-8")) > REPORT_MAX_BYTES:
        raise ConnectorError(f"The report is over {REPORT_MAX_BYTES // 1000} KB; tighten it and retry.")
    position = -1
    for heading in REQUIRED_HEADINGS:
        match = re.search(rf"^{re.escape(heading)}\s*$", report, flags=re.MULTILINE)
        if not match:
            raise ConnectorError(
                f"The report is missing the heading '{heading}'. Required, in this order: "
                + ", ".join(REQUIRED_HEADINGS)
            )
        if match.start() < position:
            raise ConnectorError("The required headings are out of order: " + ", ".join(REQUIRED_HEADINGS))
        position = match.start()
    note = " ".join((card_note or "").split())
    if not note:
        raise ConnectorError("card_note is empty; give the one-line takeaway.")
    if len(note) > CARD_NOTE_MAX:
        raise ConnectorError(f"card_note is {len(note)} characters; keep it to {CARD_NOTE_MAX}.")
    return report, note


def report_filename(task_id: UUID, existing_filenames: list[str]) -> str:
    """Same rule as apps/msandbox/harness/publish-research.sh: round N is how
    many research reports the card already carries, plus one."""
    prior = sum(1 for name in existing_filenames if _REPORT_NAME_RE.match(name or ""))
    return f"research-report-{str(task_id)[:8]}-r{prior + 1}.md"


async def attach_research_report(
    current_user,
    *,
    task_id: str,
    report_markdown: str,
    card_note: str,
    client_name: str,
) -> dict[str, Any]:
    from app.matcha.dependencies import get_client_company_id
    from app.matcha.routes.matcha_work._shared import _can_edit_project
    from app.matcha.services.matcha_work import project_file_service
    from app.matcha.services.matcha_work import project_task_service as pt_svc

    card, project, role = await _authorized_card(current_user, _parse_uuid(task_id, "task_id"))
    if not _can_edit_project(role):
        raise ConnectorError("You can view this board but not attach to its cards.")
    if card["board_column"] not in (*_CLAIMABLE_COLUMNS, "in_progress"):
        raise ConnectorError(
            f"The card is in '{card['board_column']}', so it is not waiting for a report."
        )
    report, note = validate_report(report_markdown, card_note)

    existing = await project_file_service.list_task_files(card["project_id"], card["id"])
    filename = report_filename(card["id"], [f.get("filename") or "" for f in existing])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Trusted provenance line, written here rather than by the model.
    body = f"_Research via {client_name} on the requester's own plan · {stamp}_\n\n{report}\n"

    company_id = project.get("company_id") or await get_client_company_id(current_user)
    try:
        record = await project_file_service.store_project_file_bytes(
            body.encode("utf-8"),
            filename=filename,
            content_type="text/markdown",
            project_id=card["project_id"],
            uploaded_by=current_user.id,
            prefix=f"matcha-work/{company_id}/{card['project_id']}/tasks/{card['id']}/files",
            task_id=card["id"],
        )
    except HTTPException as exc:
        raise _http_to_connector_error(exc)

    await pt_svc.log_task_activity(
        project_id=card["project_id"],
        task_id=card["id"],
        actor_user_id=current_user.id,
        kind="note",
        body=f"{note}\n\nReport attached: {filename}",
        attachment_ids=[record["id"]] if record.get("id") else None,
    )
    try:
        await pt_svc.update_project_task(
            card["project_id"],
            card["id"],
            {
                "board_column": "review",
                "progress_note": f"🧠 CONNECTOR · {client_name} · READY FOR REVIEW · note: {note}",
            },
            actor_user_id=current_user.id,
            project_title=project.get("title"),
        )
    except ValueError as exc:
        raise ConnectorError(str(exc))
    logger.info(
        "[mcp] research report task=%s user=%s client=%s file=%s",
        card["id"], current_user.id, client_name, filename,
    )
    return {"attached": True, "filename": filename, "column": "review", "task_id": str(card["id"])}


# ── launch prompt (used by the Espresso / web "Research with…" button) ───────


def launch_prompt(task_id: UUID, title: str) -> str:
    title = " ".join((title or "").split())[:140]
    return (
        f"Use the Matcha connector to work on my research card \"{title}\" "
        f"(task_id {task_id}). Call get_research_card with that task_id, then "
        "claim_research_card, research it thoroughly with web search, and finish by "
        "calling attach_research_report with a report that follows report_contract "
        "exactly. Reply to me with the card_note only."
    )
