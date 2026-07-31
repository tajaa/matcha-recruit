"""Company event-protocol file — the per-company doc EMS intake grounds on.

Structured half (notify_emails / notify_all_admins) is read
deterministically by urgent_notify.py — email routing never depends on AI
parsing prose. Free-text half (incident_definition / culture_notes) is what
classify_event injects as the COMPANY INCIDENT PROTOCOL prompt block, and
only when the trigger message mentions "incident" (per spec).
"""

from typing import Optional
from uuid import UUID

# Free-text injected into the classify prompt is capped — the prompt already
# carries 15 context messages + a 4000-char narrative.
_MAX_PROTOCOL_PROMPT_CHARS = 4000


def mentions_incident(content: str) -> bool:
    """Case-insensitive substring per spec — 'Incident', 'incidents' gate in."""
    return "incident" in (content or "").lower()


async def fetch_protocol(conn, company_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT * FROM company_event_protocols WHERE company_id = $1", company_id,
    )
    return dict(row) if row else None


def protocol_prompt_excerpt(protocol_row: Optional[dict]) -> Optional[str]:
    """The free-text half rendered for the classify prompt, or None when
    there is nothing to judge against — a contacts-only protocol row must
    not trigger an assessment over empty text. corrective_actions is
    deliberately excluded: it guides remediation, not qualification."""
    if not protocol_row:
        return None
    parts = []
    definition = (protocol_row.get("incident_definition") or "").strip()
    culture = (protocol_row.get("culture_notes") or "").strip()
    if definition:
        parts.append(f"What counts as an incident:\n{definition}")
    if culture:
        parts.append(f"Culture notes:\n{culture}")
    if not parts:
        return None
    return "\n\n".join(parts)[:_MAX_PROTOCOL_PROMPT_CHARS]


async def upsert_protocol(conn, *, company_id: UUID, updated_by: UUID, body: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO company_event_protocols
            (company_id, notify_emails, notify_all_admins,
             incident_definition, culture_notes, corrective_actions, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (company_id) DO UPDATE SET
            notify_emails = EXCLUDED.notify_emails,
            notify_all_admins = EXCLUDED.notify_all_admins,
            incident_definition = EXCLUDED.incident_definition,
            culture_notes = EXCLUDED.culture_notes,
            corrective_actions = EXCLUDED.corrective_actions,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        RETURNING *
        """,
        company_id, body["notify_emails"], body["notify_all_admins"],
        body["incident_definition"], body["culture_notes"],
        body["corrective_actions"], updated_by,
    )
    return dict(row)
