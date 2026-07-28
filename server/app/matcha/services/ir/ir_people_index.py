"""IR People — lightweight per-person identity (matcha-lite, no roster).

Moved from routes/ir_incidents/_shared.py (refactor round 2, stage 3).

People named in incidents get a stable id WITHOUT a managed employee
roster: identity is the typed name, normalized for dedup. This is
distinct from `involved_employee_ids` (which targets the real
`employees` table). Name-based identity trades exactness for zero
upkeep — two genuinely-different "John Smith"s collapse to one row; the
`verified` flag exists so a future manual-merge/confirm step can split
or promote them. The create form's type-ahead nudges consistent
spelling so the dedup actually catches repeats.
"""
import re
from typing import Optional

IR_PERSON_ROLES = ("reporter", "involved", "witness", "interviewee")

# Roles owned by the incident create/update body. Interviewee rows are
# managed separately by the investigation-interview endpoints, so a
# re-sync from incident edit must NOT delete them.
IR_INCIDENT_BODY_ROLES = ("reporter", "involved", "witness")

_WS_RE = re.compile(r"\s+")


def _normalize_person_name(name: Optional[str]) -> str:
    """Casefold + collapse whitespace for dedup matching. '' if blank."""
    if not name:
        return ""
    return _WS_RE.sub(" ", str(name).strip()).casefold()


def _gather_incident_people(
    *,
    reported_by_name: Optional[str] = None,
    reported_by_email: Optional[str] = None,
    witnesses=None,
    category_data: Optional[dict] = None,
) -> list[tuple[str, Optional[str], str]]:
    """Extract (display_name, email, role) tuples from an incident's people
    fields. Roles: reporter, witness (witnesses JSONB), involved
    (category_data injured_person + parties_involved). Blank names dropped.
    """
    out: list[tuple[str, Optional[str], str]] = []

    if reported_by_name and reported_by_name.strip().lower() not in ("", "anonymous", "unknown"):
        out.append((reported_by_name.strip(), (reported_by_email or None), "reporter"))

    for w in (witnesses or []):
        name = getattr(w, "name", None) if not isinstance(w, dict) else w.get("name")
        contact = getattr(w, "contact", None) if not isinstance(w, dict) else w.get("contact")
        if name and name.strip():
            out.append((name.strip(), (contact or None), "witness"))

    cd = category_data or {}
    injured = cd.get("injured_person")
    if injured and str(injured).strip():
        out.append((str(injured).strip(), None, "involved"))
    for party in (cd.get("parties_involved") or []):
        pname = party.get("name") if isinstance(party, dict) else None
        if pname and str(pname).strip():
            out.append((str(pname).strip(), None, "involved"))

    return out


async def _upsert_ir_person(
    conn, company_id: str, name: str, email: Optional[str] = None,
) -> Optional[str]:
    """Insert-or-touch an ir_people row by normalized name. Returns id."""
    norm = _normalize_person_name(name)
    if not norm or not company_id:
        return None
    row = await conn.fetchrow(
        """
        INSERT INTO ir_people (company_id, display_name, normalized_name, email)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (company_id, normalized_name)
        DO UPDATE SET last_seen = NOW(),
                      email = COALESCE(ir_people.email, EXCLUDED.email)
        RETURNING id::text AS id
        """,
        company_id, name.strip(), norm, (email or None),
    )
    return row["id"] if row else None


async def _link_incident_person(
    conn, company_id: str, incident_id: str, name: str,
    email: Optional[str], role: str,
) -> None:
    """Upsert a person and attach them to an incident in a given role."""
    person_id = await _upsert_ir_person(conn, company_id, name, email)
    if not person_id:
        return
    await conn.execute(
        """
        INSERT INTO ir_incident_people (incident_id, person_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        incident_id, person_id, role,
    )


async def _sync_incident_people(
    conn, company_id: Optional[str], incident_id: str,
    entries: list[tuple[str, Optional[str], str]],
    managed_roles: tuple[str, ...] = IR_INCIDENT_BODY_ROLES,
) -> None:
    """Re-sync an incident's people rows for the managed roles.

    Delete-and-reinsert scoped to ``managed_roles`` so interviewee links
    (owned by the interview endpoints) survive an incident edit. Best-effort
    by contract — callers wrap this and swallow failures so identity tracking
    never blocks incident submission.
    """
    if not company_id:
        return
    await conn.execute(
        "DELETE FROM ir_incident_people WHERE incident_id = $1 AND role = ANY($2::text[])",
        incident_id, list(managed_roles),
    )
    for name, email, role in entries:
        if role in managed_roles:
            await _link_incident_person(conn, company_id, incident_id, name, email, role)
