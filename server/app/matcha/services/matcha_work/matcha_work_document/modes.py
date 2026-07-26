"""Thread pin + mode toggles."""
from typing import Optional
from uuid import UUID

from app.database import get_connection
from app.matcha.services.matcha_work.matcha_work_modes import MODE_COLUMNS_SQL, MODES_BY_KEY

from .threads import _thread_list_item_from_row
from .elements import _sync_element_for_thread


async def set_thread_pinned(
    thread_id: UUID,
    company_id: UUID,
    is_pinned: bool,
) -> Optional[dict]:
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE mw_threads
            SET is_pinned=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at, current_state
            """,
            is_pinned,
            thread_id,
            company_id,
        )
        if row is None:
            return None
        await _sync_element_for_thread(conn, thread_id)
        return _thread_list_item_from_row(dict(row))


async def set_thread_mode(
    thread_id: UUID,
    company_id: UUID,
    mode_key: str,
    enabled: bool,
) -> Optional[dict]:
    """Registry-driven mode toggle. mode_key must exist in
    matcha_work_modes.MODES_BY_KEY — the column name comes from the registry,
    never from the caller, so the f-string SQL stays injection-safe."""
    mode = MODES_BY_KEY.get(mode_key)
    if mode is None:
        raise ValueError(f"Unknown thread mode: {mode_key}")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE mw_threads
            SET {mode.column}=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at, current_state
            """,
            enabled,
            thread_id,
            company_id,
        )
        if row is None:
            return None
        return _thread_list_item_from_row(dict(row))


# Legacy named setters — kept for pre-registry callsites. New code goes
# through set_thread_mode.

async def set_thread_node_mode(
    thread_id: UUID,
    company_id: UUID,
    node_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "node", node_mode)


async def set_thread_compliance_mode(
    thread_id: UUID,
    company_id: UUID,
    compliance_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "compliance", compliance_mode)


async def set_thread_payer_mode(
    thread_id: UUID,
    company_id: UUID,
    payer_mode: bool,
) -> Optional[dict]:
    return await set_thread_mode(thread_id, company_id, "payer", payer_mode)
