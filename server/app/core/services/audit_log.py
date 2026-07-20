"""Shared audit-log row writer.

Per-domain audit tables stay separate on purpose — `ir_audit_log`,
`er_audit_log`, `accommodation_audit_log` are distinct compliance artifacts and
must not track each other's schema churn (the same reason `IRAuditLogEntry` was
NOT folded into the shared Pydantic pair in J9). What was duplicated is the
*write*: three byte-identical helpers differing only in the table name and the
name of the foreign-key column.

`insert_audit_log` is that shared body. The domain `log_audit` helpers stay as
thin wrappers with their existing signatures, so every call site is untouched.

`table` and `id_column` are always code-level constants at the call site (never
user input), so interpolating them is safe under the "never f-string user input
into SQL" rule — every actual *value* still binds as a parameter.
"""

from __future__ import annotations

import json
from typing import Any, Optional

__all__ = ["insert_audit_log"]


async def insert_audit_log(
    conn: Any,
    *,
    table: str,
    id_column: str,
    id_value: Optional[Any],
    user_id: Optional[Any],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Insert one row into a `<domain>_audit_log` table.

    Columns are the shared shape:
    ``(<id_column>, user_id, action, entity_type, entity_id, details, ip_address)``.
    `details` is JSON-encoded (NULL when falsy), matching the prior per-domain
    helpers exactly.
    """
    await conn.execute(
        f"""
        INSERT INTO {table} ({id_column}, user_id, action, entity_type, entity_id, details, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        id_value,
        user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        ip_address,
    )
