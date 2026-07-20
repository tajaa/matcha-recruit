"""Who to email about a company.

The same DISTINCT clients-join-users query was written out three times — in
``workers/tasks/ir_deadline_alerts.py``, ``matcha/services/leave_agent.py`` and
``core/services/compliance_service.py`` — which is three places to update when
"who counts as a company admin" changes (adding a role, honouring a
notification-preferences opt-out, excluding a deactivated seat).

The connection-taking form is primary on purpose: Celery workers are pool-free
(see the note in the root CLAUDE.md), so a helper that acquires its own pooled
connection cannot be called from a worker. ``get_company_name_and_contacts``
exists for the one caller that has no connection in hand and also wants the
company name; it uses ``connection_or_direct`` so it works in both worlds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import UUID

__all__ = ["get_company_admin_contacts", "get_company_name_and_contacts"]

# Business admins for a company: an active user linked through `clients`. The
# display name falls back to the local part of the email so a contact row is
# never nameless.
_CONTACTS_SQL = """
    SELECT DISTINCT
        u.email,
        COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
    FROM clients c
    JOIN users u ON u.id = c.user_id
    WHERE c.company_id = $1
      AND u.is_active = true
      AND u.email IS NOT NULL
    ORDER BY u.email
"""


async def get_company_admin_contacts(conn: Any, company_id: UUID) -> List[Dict[str, str]]:
    """Email recipients for a company's business admins. Takes an open connection."""
    rows = await conn.fetch(_CONTACTS_SQL, company_id)
    return [{"email": r["email"], "name": r["name"] or r["email"]} for r in rows]


async def get_company_name_and_contacts(
    company_id: UUID,
) -> Tuple[str, List[Dict[str, str]]]:
    """Company display name plus its admin contacts, acquiring its own connection."""
    from app.database import connection_or_direct

    async with connection_or_direct() as conn:
        company_name = (
            await conn.fetchval("SELECT name FROM companies WHERE id = $1", company_id)
            or "Your company"
        )
        return company_name, await get_company_admin_contacts(conn, company_id)
