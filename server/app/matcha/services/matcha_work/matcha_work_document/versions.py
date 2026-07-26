"""Thread state versioning — apply_update / revert / list."""
import json
from typing import Optional
from uuid import UUID

from app.database import get_connection

from ._coerce import _parse_jsonb
from .elements import _sync_element_for_thread


async def apply_update(
    thread_id: UUID,
    updates: dict,
    diff_summary: Optional[str] = None,
) -> dict:
    """Merge updates into current_state, bump version, snapshot to mw_document_versions."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT current_state, version FROM mw_threads WHERE id=$1 FOR UPDATE",
                thread_id,
            )
            current_state = _parse_jsonb(row["current_state"])
            current_version = row["version"]

            merged_state = {**current_state, **updates}
            # Clear fields that were explicitly set to None
            merged_state = {k: v for k, v in merged_state.items() if v is not None}
            new_version = current_version + 1

            await conn.execute(
                """
                UPDATE mw_threads
                SET current_state=$1, version=$2, updated_at=NOW()
                WHERE id=$3
                """,
                json.dumps(merged_state),
                new_version,
                thread_id,
            )
            await conn.execute(
                """
                INSERT INTO mw_document_versions(thread_id, version, state_json, diff_summary)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(thread_id, version) DO NOTHING
                """,
                thread_id,
                new_version,
                json.dumps(merged_state),
                diff_summary,
            )
            await _sync_element_for_thread(conn, thread_id)
        return {"version": new_version, "current_state": merged_state}


async def revert_to_version(thread_id: UUID, target_version: int) -> dict:
    """Load a historical snapshot and create a NEW version with that state."""
    async with get_connection() as conn:
        snap = await conn.fetchrow(
            "SELECT state_json FROM mw_document_versions WHERE thread_id=$1 AND version=$2",
            thread_id,
            target_version,
        )
        if snap is None:
            raise ValueError(f"Version {target_version} not found for thread {thread_id}")

        old_state = _parse_jsonb(snap["state_json"])

        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT version FROM mw_threads WHERE id=$1 FOR UPDATE",
                thread_id,
            )
            new_version = row["version"] + 1

            await conn.execute(
                """
                UPDATE mw_threads
                SET current_state=$1, version=$2, updated_at=NOW()
                WHERE id=$3
                """,
                json.dumps(old_state),
                new_version,
                thread_id,
            )
            await conn.execute(
                """
                INSERT INTO mw_document_versions(thread_id, version, state_json, diff_summary)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(thread_id, version) DO NOTHING
                """,
                thread_id,
                new_version,
                json.dumps(old_state),
                f"Reverted to version {target_version}",
            )
            await _sync_element_for_thread(conn, thread_id)
        return {"version": new_version, "current_state": old_state}


async def list_versions(thread_id: UUID, include_state: bool = False) -> list[dict]:
    async with get_connection() as conn:
        if include_state:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, version, state_json, diff_summary, created_at
                FROM mw_document_versions
                WHERE thread_id=$1
                ORDER BY version DESC
                """,
                thread_id,
            )
            result = []
            for r in rows:
                d = dict(r)
                d["state_json"] = _parse_jsonb(d["state_json"])
                result.append(d)
            return result
        else:
            rows = await conn.fetch(
                """
                SELECT id, thread_id, version, diff_summary, created_at
                FROM mw_document_versions
                WHERE thread_id=$1
                ORDER BY version DESC
                """,
                thread_id,
            )
            return [
                {**dict(r), "state_json": {}}
                for r in rows
            ]
