"""Research-task persistence for matcha-work projects.

Extracted verbatim from `routes/matcha_work/tasks.py` (2026-07-19 split) — the
route handlers previously inlined every one of these read-modify-write cycles.

STORAGE (deliberately unchanged): research tasks live as a **list under the
`research_tasks` key of the `mw_projects.project_data` JSONB blob** — there is no
`research_tasks` table and no migration behind this module. Each task is a dict
`{id, name, instructions, inputs[], results[]}`; each input is
`{id, url, status, queued_at}` (+ `error` / `completed_at` written by
`research_browse_service`). The web client
(`client/src/work/api/matchaWork/research.ts`) decodes these shapes directly, so
every return value here is byte-identical to what the routes returned before.

Every mutation takes `SELECT ... FOR UPDATE` on the project row inside a
transaction, because the whole blob is rewritten on each write and concurrent
research runs would otherwise clobber each other's input-status updates.
"""
import json
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.database import get_connection


class ResearchTaskError(Exception):
    """Carries the HTTP status + detail the route should surface.

    The routes used to raise HTTPException inline; keeping the status on the
    exception is what makes this extraction behavior-preserving (400 for a
    validation miss vs 404 for a missing task/input).
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load(row) -> dict:
    """Normalize the project_data blob — asyncpg may hand back str or dict.

    A corrupt/non-JSON blob degrades to `{}` rather than raising, matching the
    sibling normalizers (`routes/matcha_work/_shared.py:_json_object` and the
    guarded `json.loads` sites in `project_service.py`). Well-formed input is
    unaffected.
    """
    data = row["project_data"] if row else {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            data = {}
    return data or {}


async def _save(conn, project_id: UUID, data: dict) -> None:
    await conn.execute(
        "UPDATE mw_projects SET project_data = $1::jsonb, updated_at = NOW() WHERE id = $2",
        json.dumps(data), project_id,
    )


def _find_task(data: dict, task_id: str) -> Optional[dict]:
    for task in data.get("research_tasks", []):
        if task["id"] == task_id:
            return task
    return None


async def create_task(project_id: UUID, name: str, instructions: str) -> dict:
    task = {
        "id": str(_uuid.uuid4()),
        "name": name,
        "instructions": instructions,
        "inputs": [],
        "results": [],
    }
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            tasks = data.get("research_tasks", [])
            tasks.append(task)
            data["research_tasks"] = tasks
            await _save(conn, project_id, data)
    return task


async def update_task(project_id: UUID, task_id: str, body: dict) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                raise ResearchTaskError(404, "Research task not found")
            if "name" in body:
                task["name"] = body["name"]
            if "instructions" in body:
                task["instructions"] = body["instructions"]
            await _save(conn, project_id, data)
            return task


async def delete_task(project_id: UUID, task_id: str) -> dict:
    """Idempotent by design — deleting an unknown id is a 200, not a 404."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            data["research_tasks"] = [
                t for t in data.get("research_tasks", []) if t["id"] != task_id
            ]
            await _save(conn, project_id, data)
    return {"deleted": True}


async def add_inputs(project_id: UUID, task_id: str, urls: list) -> dict:
    if not urls:
        raise ResearchTaskError(400, "No URLs provided")

    new_inputs = []
    for url in urls:
        url = url.strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue
        new_inputs.append({
            "id": str(_uuid.uuid4()),
            "url": url,
            "status": "pending",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })

    if not new_inputs:
        raise ResearchTaskError(400, "No valid URLs provided")

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                raise ResearchTaskError(404, "Research task not found")
            task.setdefault("inputs", []).extend(new_inputs)
            await _save(conn, project_id, data)
            return {"added": len(new_inputs), "inputs": new_inputs}


async def delete_input(project_id: UUID, task_id: str, input_id: str) -> dict:
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                raise ResearchTaskError(404, "Research task not found")
            task["inputs"] = [i for i in task.get("inputs", []) if i["id"] != input_id]
            task["results"] = [
                r for r in task.get("results", []) if r.get("input_id") != input_id
            ]
            await _save(conn, project_id, data)
            return {"deleted": True}


async def claim_pending_inputs(project_id: UUID, task_id: str) -> tuple[list, str]:
    """Flip every pending/error input to `running` and hand the route the list
    to stream over. Claiming inside the FOR UPDATE txn is what stops two
    concurrent /run calls from researching the same URL twice.

    Returns `(pending_inputs, instructions)`. An unknown task_id yields
    `([], "")` — matching the original `break`-out-of-loop fallthrough, which
    returned `{"queued": 0}` rather than 404ing.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                return [], ""

            instructions = task.get("instructions", "")
            if not instructions:
                raise ResearchTaskError(400, "Task has no instructions")

            pending_inputs = []
            for inp in task.get("inputs", []):
                if inp["status"] in ("pending", "error"):
                    inp["status"] = "running"
                    inp.pop("error", None)
                    pending_inputs.append({"id": inp["id"], "url": inp["url"]})

            await _save(conn, project_id, data)
            return pending_inputs, instructions


async def claim_follow_up(
    project_id: UUID, task_id: str, input_id: str, follow_up: str,
) -> tuple[str, str]:
    """Mark one input `running` and build the follow-up prompt.

    Previous findings for the same input are folded into the instructions so
    the browse pass builds on them instead of restarting. Existing results are
    deliberately KEPT (unlike retry) — the new ones merge on top.

    Returns `(url, combined_instructions)`; `("", "")` if not found.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                return "", ""

            base_instructions = task.get("instructions", "")

            prev_findings: Any = {}
            for r in task.get("results", []):
                if r.get("input_id") == input_id:
                    prev_findings = r.get("findings", {})
                    break

            combined_instructions = base_instructions
            if prev_findings:
                combined_instructions += (
                    f"\n\nPREVIOUS FINDINGS (already gathered):\n"
                    f"{json.dumps(prev_findings, indent=2)}"
                )
            combined_instructions += f"\n\nADDITIONAL REQUEST:\n{follow_up}"

            follow_url = ""
            for inp in task.get("inputs", []):
                if inp["id"] == input_id:
                    inp["status"] = "running"
                    inp.pop("error", None)
                    inp.pop("completed_at", None)
                    follow_url = inp["url"]
                    break

            await _save(conn, project_id, data)
            return follow_url, combined_instructions


async def claim_retry(project_id: UUID, task_id: str, input_id: str) -> tuple[str, str]:
    """Mark one failed input `running` and drop its stale results (unlike
    follow-up, a retry replaces rather than merges).

    Returns `(url, instructions)`; `("", "")` if not found.
    """
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            task = _find_task(data, task_id)
            if task is None:
                return "", ""

            retry_instructions = task.get("instructions", "")
            retry_url = ""
            for inp in task.get("inputs", []):
                if inp["id"] == input_id:
                    inp["status"] = "running"
                    inp.pop("error", None)
                    inp.pop("completed_at", None)
                    retry_url = inp["url"]
                    task["results"] = [
                        r for r in task.get("results", []) if r.get("input_id") != input_id
                    ]
                    await _save(conn, project_id, data)
                    break

            return retry_url, retry_instructions


async def stop_task(project_id: UUID, task_id: str) -> dict:
    """Reset in-flight inputs back to pending. Never 404s — a stop against an
    unknown task reports `{"reset": 0}`."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT project_data FROM mw_projects WHERE id = $1 FOR UPDATE", project_id,
            )
            data = _load(row)
            reset_count = 0
            task = _find_task(data, task_id)
            if task is not None:
                for inp in task.get("inputs", []):
                    if inp["status"] == "running":
                        inp["status"] = "pending"
                        reset_count += 1

            if reset_count:
                await _save(conn, project_id, data)

    return {"reset": reset_count}
