"""A run's progress, shown in the chat it was asked in.

One Espresso message per run carries `metadata.kind = "agent_progress"` and
the run id. While the run works, its state goes out as `agent_run_progress`
socket events; a reloaded chat reads the same state from the run's own rows
(`overlay_run_progress`), so the message itself never has to be rewritten.
"""
from __future__ import annotations

import logging
import time
from uuid import UUID

from app.database import decode_jsonb

logger = logging.getLogger(__name__)

PROGRESS_METADATA_KIND = "agent_progress"
PROGRESS_EVENT = "agent_run_progress"
MAX_STEPS = 30
_NOTE_MIN_INTERVAL = 1.5


def progress_metadata(run_id: UUID | str) -> dict:
    return {"kind": PROGRESS_METADATA_KIND, "run_id": str(run_id)}


def progress_view(run_id, status: str, steps: list[dict], note: str | None = None) -> dict:
    return {
        "run_id": str(run_id),
        "status": status,
        "note": note,
        "steps": steps[-MAX_STEPS:],
    }


async def _publish(channel_id: UUID, event: dict) -> None:
    from app.matcha.services.matcha_work.project_task_notifications import broadcast_channel_event

    await broadcast_channel_event(channel_id, event)


class ChatProgress:
    """The runtime's progress sink for a run asked in chat. Best-effort: a
    chat that cannot be reached never fails the run."""

    def __init__(self, *, channel_id: UUID, run_id: UUID) -> None:
        self.channel_id = channel_id
        self.run_id = run_id
        self.steps: list[dict] = []
        self.last_note: str | None = None
        self._last_sent = 0.0

    async def _send(self, status: str) -> None:
        try:
            await _publish(self.channel_id, {
                "type": PROGRESS_EVENT,
                "channel_id": str(self.channel_id),
                **progress_view(self.run_id, status, self.steps, self.last_note),
            })
        except Exception:
            logger.warning("agent progress event failed run=%s", self.run_id, exc_info=True)

    async def note(self, text: str, *, force: bool = False) -> None:
        self.last_note = text
        now = time.monotonic()
        if not force and now - self._last_sent < _NOTE_MIN_INTERVAL:
            return
        self._last_sent = now
        await self._send("running")

    async def step(self, seq: int, kind: str, label: str, status: str) -> None:
        self.steps.append({"seq": seq, "kind": kind, "label": label, "status": status})
        self._last_sent = time.monotonic()
        await self._send("running")

    async def finish(self, status: str, note: str | None = None) -> None:
        self.last_note = note
        await self._send(status)


def run_reference(raw_metadata) -> UUID | None:
    metadata = decode_jsonb(raw_metadata)
    if not isinstance(metadata, dict) or metadata.get("kind") != PROGRESS_METADATA_KIND:
        return None
    try:
        return UUID(str(metadata.get("run_id")))
    except (TypeError, ValueError):
        return None


async def overlay_run_progress(conn, messages, *, channel_id: UUID) -> list:
    """Stamp each progress message with its run's state as of now.

    One query for the runs and one for their steps per history page; every
    other message passes through untouched.
    """
    ids: set[UUID] = set()
    for message in messages:
        run_id = run_reference(message.get("metadata"))
        if run_id is not None:
            ids.add(run_id)
    if not ids:
        return list(messages)
    ordered = sorted(ids, key=str)
    runs = await conn.fetch(
        """SELECT id, status, error FROM mw_project_agent_runs
           WHERE id = ANY($1::uuid[]) AND channel_id = $2 AND kind = 'assistant'""",
        ordered, channel_id,
    )
    states = {row["id"]: row for row in runs}
    step_rows = await conn.fetch(
        """SELECT run_id, seq, kind, label, status FROM mw_project_agent_steps
           WHERE run_id = ANY($1::uuid[]) ORDER BY run_id, seq""",
        [row["id"] for row in runs],
    ) if runs else []
    steps: dict[UUID, list[dict]] = {}
    for row in step_rows:
        steps.setdefault(row["run_id"], []).append({
            "seq": row["seq"], "kind": row["kind"], "label": row["label"], "status": row["status"],
        })
    out = []
    for message in messages:
        run_id = run_reference(message.get("metadata"))
        row = states.get(run_id)
        if row is not None:
            message = dict(message)
            message["metadata"] = {
                **(decode_jsonb(message.get("metadata"), {}) or {}),
                "progress": progress_view(run_id, row["status"], steps.get(run_id, [])),
            }
        out.append(message)
    return out
