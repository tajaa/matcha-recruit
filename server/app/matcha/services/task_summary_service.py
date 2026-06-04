"""1-click ticket summary — Gemini Flash Lite condenses a kanban task's
current state + recent activity into a short catch-up blurb. For teammates
deep in the rounds or a new collaborator getting up to speed.

Self-contained Gemini call (mirrors ticket_draft_service / commit_scan_service)
rather than the entangled matcha_work_ai.generate() chat pipeline.
"""

import json
import logging
import os
from typing import Optional
from uuid import UUID

from google import genai
from google.genai import types

from ...config import get_settings
from ...database import get_connection

logger = logging.getLogger(__name__)

# Flash-lite: cheapest/fastest tier — a summary is a one-shot, throwaway read.
FLASH_LITE_MODEL = "gemini-3.1-flash-lite"

# Cap the activity trail so a long-running ticket doesn't blow the prompt.
_MAX_TRAIL = 40

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or settings.gemini_api_key)
    return _client


def _meta(raw) -> dict:
    """mw_task_history.metadata is JSONB; asyncpg hands it back as a string
    (no codec registered), so coerce to dict and tolerate junk."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


async def generate_task_summary(project_id: UUID, task_id: UUID) -> Optional[str]:
    """Build context from the task row + current-round checklist + activity
    trail, then ask Flash Lite for a tight catch-up summary.

    Returns:
      - None  → task not found in this project (caller should 404)
      - ""    → AI was unavailable (caller shows a soft retry message)
      - str   → the summary
    Never raises — a flaky Gemini call must not 500 the endpoint.
    """
    async with get_connection() as conn:
        task = await conn.fetchrow(
            """SELECT title, description, progress_note, review_note,
                      priority, board_column, status
                 FROM mw_tasks
                WHERE id = $1 AND project_id = $2""",
            task_id, project_id,
        )
        if not task:
            return None

        subtasks = await conn.fetch(
            """SELECT title, is_done FROM mw_subtasks
                WHERE task_id = $1
                  AND round_index = (
                        SELECT COALESCE(MAX(round_index), 0)
                          FROM mw_subtasks WHERE task_id = $1
                  )
                ORDER BY position ASC, created_at ASC""",
            task_id,
        )

        history = await conn.fetch(
            """SELECT h.event_type, h.from_value, h.to_value, h.metadata, h.created_at,
                      COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS actor
                 FROM mw_task_history h
                 LEFT JOIN users u   ON u.id = h.actor_user_id
                 LEFT JOIN clients c ON c.user_id = h.actor_user_id
                 LEFT JOIN employees e ON e.user_id = h.actor_user_id
                 LEFT JOIN admins a  ON a.user_id = h.actor_user_id
                WHERE h.task_id = $1
                ORDER BY h.created_at ASC""",
            task_id,
        )

    context = _build_context(task, subtasks, history)
    prompt = (
        "You are catching a teammate up on a work ticket. Using ONLY the ticket "
        "data below, write a tight 2-4 sentence summary of where the work stands "
        "right now and what has been done recently. Lead with the current state, "
        "then what's left or blocking. Plain and concrete — no preamble, no bullet "
        "points, and don't just restate the title.\n\n"
        f"--- TICKET ---\n{context}\n--- END ---\n\nSummary:"
    )

    try:
        resp = await _get_client().aio.models.generate_content(
            model=FLASH_LITE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=400),
        )
        return (resp.text or "").strip()
    except Exception as e:  # noqa: BLE001 — soft-fail, never 500 the endpoint
        logger.warning("task summary: Gemini failed task=%s: %s", task_id, e)
        return ""


def _build_context(task, subtasks, history) -> str:
    lines: list[str] = [
        f"TITLE: {task['title']}",
        f"COLUMN: {task['board_column']}  STATUS: {task['status']}  PRIORITY: {task['priority']}",
    ]
    if task["description"]:
        lines.append(f"DESCRIPTION: {task['description'].strip()}")
    if task["progress_note"]:
        lines.append(f"PROGRESS NOTE: {task['progress_note'].strip()}")
    if task["review_note"]:
        lines.append(f"CHANGES REQUESTED: {task['review_note'].strip()}")

    if subtasks:
        done = sum(1 for s in subtasks if s["is_done"])
        lines.append(f"CHECKLIST ({done}/{len(subtasks)} done):")
        for s in subtasks:
            lines.append(f"  [{'x' if s['is_done'] else ' '}] {s['title']}")

    trail: list[str] = []
    for h in history:
        et = h["event_type"]
        md = _meta(h["metadata"])
        actor = h["actor"] or "someone"
        if et == "activity":
            body = (md.get("body") or "").strip()
            if body:
                trail.append(f"{actor} noted: {body}")
        elif et == "column_change":
            trail.append(f"{actor} moved it {h['from_value']} → {h['to_value']}")
        elif et == "round_started":
            detail = md.get("title") or md.get("feedback") or ""
            trail.append(f"{actor} started a new round{(': ' + detail) if detail else ''}")
        elif et == "review_rejected":
            trail.append(f"{actor} sent it back for changes")
        elif et == "review_approved":
            trail.append(f"{actor} approved the review")
        elif et == "subtask_added":
            trail.append(f"{actor} added a checklist item")
        elif et == "progress_note_change":
            trail.append(f"{actor} updated the progress note")

    if trail:
        lines.append("RECENT ACTIVITY (oldest to newest):")
        lines.extend(f"  - {t}" for t in trail[-_MAX_TRAIL:])

    return "\n".join(lines)
