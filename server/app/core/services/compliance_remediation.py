"""Compliance remediation trail — issue-lifecycle diff + manual actions.

The risk cockpit computes issues live each load; this module persists their
lifecycle so a fix is *documented* (for ER / legal defense), not just silently
gone. Two responsibilities:

1. `reconcile_issue_state` — called on every risk-summary compute. Upserts the
   current open issues, and any previously-open issue no longer produced by the
   live check flips to `resolved` (auto-documented, cause re-queried). A
   `dismissed` false-positive re-surfaces only if its underlying `basis` values
   change. Every transition is written to the immutable audit log, and only when
   a row actually transitioned (conditional UPDATE … RETURNING) so two
   concurrent GETs can't double-log.

2. Manual actions — `dismiss_issue`, `annotate_issue`, `reopen_issue` — and
   `fetch_recent_remediations` for the cockpit history + legal-defense evidence.

`basis` is stored/compared as a plain dict; asyncpg may hand JSONB back as a str
depending on codec, so every read goes through `_as_dict`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from uuid import UUID

from ..models.compliance import RemediationRecord

logger = logging.getLogger(__name__)


def _as_dict(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


async def _log(conn, company_id, issue_key, entity_type, entity_id, action, actor_user_id=None, details=None):
    await conn.execute(
        """
        INSERT INTO compliance_remediation_audit_log
            (company_id, issue_key, entity_type, entity_id, action, actor_user_id, details)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        company_id, issue_key, entity_type, entity_id, action, actor_user_id,
        json.dumps(details) if details else None,
    )


async def _auto_resolution_note(conn, row) -> str:
    """Re-query the actual cause of an auto-resolution — never assume a fix.
    A terminated underpaid employee must not read as 'pay was corrected'."""
    source = row["source"]
    emp_id = row["employee_id"]
    if source == "wage" and emp_id:
        emp = await conn.fetchrow(
            "SELECT pay_rate, termination_date FROM employees WHERE id = $1", emp_id
        )
        if emp is None or emp["termination_date"] is not None:
            return "Employee is no longer active."
        if emp["pay_rate"] is not None:
            return f"Pay is now ${float(emp['pay_rate']):,.2f} (was below the minimum)."
        return "No longer flagged by the compliance check."
    if source == "credential":
        return "Credential renewed or employee no longer active."
    if source == "incident":
        return "Incident closed or resolved."
    return "No longer flagged by the compliance check."


async def reconcile_issue_state(conn, company_id: UUID, current_issues, basis_by_key: dict) -> dict:
    """Upsert current open issues, auto-resolve vanished ones, reactivate
    dismissed ones whose basis changed. Returns {issue_key: state_row}."""
    async with conn.transaction():
        existing = await conn.fetch(
            "SELECT * FROM compliance_issue_state WHERE company_id = $1", company_id
        )
        existing_by_key = {r["issue_key"]: r for r in existing}
        current_keys = {i.id for i in current_issues}

        for iss in current_issues:
            key = iss.id
            basis = basis_by_key.get(key) or {}
            penalty_json = json.dumps(iss.penalty.model_dump()) if iss.penalty else None
            prev = existing_by_key.get(key)

            if prev is None:
                await conn.execute(
                    """
                    INSERT INTO compliance_issue_state
                        (company_id, issue_key, source, entity_type, entity_id, employee_id,
                         title, detail, severity, penalty, statute_citation, basis, status)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'open')
                    ON CONFLICT (company_id, issue_key) DO NOTHING
                    """,
                    company_id, key, iss.source, iss.source, _entity_id(iss),
                    _employee_uuid(iss), iss.title, iss.detail, iss.severity,
                    penalty_json, iss.statute_citation, json.dumps(basis),
                )
                await _log(conn, company_id, key, iss.source, _entity_id(iss), "opened")
                continue

            # A live issue that maps to a non-open row means the violation is
            # back: a previously auto-resolved one always reactivates; a
            # dismissed false-positive reactivates only if its basis changed
            # (an unchanged dismissal is the manager's standing call).
            reactivate = prev["status"] == "resolved" or (
                prev["status"] == "dismissed" and _as_dict(prev["basis"]) != basis
            )
            if reactivate:
                reopened = await conn.fetchrow(
                    """
                    UPDATE compliance_issue_state
                       SET status='open', basis=$2, title=$3, detail=$4, severity=$5,
                           penalty=$6, statute_citation=$7, last_seen_at=NOW(), updated_at=NOW(),
                           resolution_method=NULL, resolution_note=NULL, resolved_at=NULL, resolved_by=NULL
                     WHERE id=$1 AND status IN ('dismissed','resolved')
                     RETURNING id
                    """,
                    prev["id"], json.dumps(basis), iss.title, iss.detail,
                    iss.severity, penalty_json, iss.statute_citation,
                )
                if reopened:
                    await _log(conn, company_id, key, iss.source, _entity_id(iss), "reactivated")
            else:
                # Refresh snapshot + heartbeat; keep status (open stays open, a
                # still-matching dismissed stays dismissed).
                await conn.execute(
                    """
                    UPDATE compliance_issue_state
                       SET title=$2, detail=$3, severity=$4, penalty=$5, statute_citation=$6,
                           basis=$7, last_seen_at=NOW(), updated_at=NOW()
                     WHERE id=$1
                    """,
                    prev["id"], iss.title, iss.detail, iss.severity, penalty_json,
                    iss.statute_citation, json.dumps(basis),
                )

        # Auto-resolve: open rows the live check no longer produces.
        for r in existing:
            if r["status"] == "open" and r["issue_key"] not in current_keys:
                note = await _auto_resolution_note(conn, r)
                resolved = await conn.fetchrow(
                    """
                    UPDATE compliance_issue_state
                       SET status='resolved', resolved_at=NOW(), resolution_method='auto_resolved',
                           resolution_note=$2, updated_at=NOW()
                     WHERE id=$1 AND status='open'
                     RETURNING id
                    """,
                    r["id"], note,
                )
                if resolved:
                    await _log(conn, company_id, r["issue_key"], r["source"], r["entity_id"],
                               "auto_resolved", details={"note": note})

    rows = await conn.fetch(
        "SELECT * FROM compliance_issue_state WHERE company_id = $1", company_id
    )
    return {r["issue_key"]: r for r in rows}


def _entity_id(iss) -> str | None:
    return iss.alert_id or (iss.id.split(":", 2)[1] if ":" in iss.id else None)


def _employee_uuid(iss):
    if iss.source in ("wage", "credential"):
        parts = iss.id.split(":")
        if len(parts) >= 2:
            return parts[1]
    return None


async def fetch_recent_remediations(conn, company_id: UUID, days: int = 30) -> list[RemediationRecord]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = await conn.fetch(
        """
        SELECT s.*, u.email AS resolver_name
        FROM compliance_issue_state s
        LEFT JOIN users u ON u.id = s.resolved_by
        WHERE s.company_id = $1
          AND s.status IN ('resolved','dismissed')
          AND COALESCE(s.resolved_at, s.updated_at) >= $2
        ORDER BY COALESCE(s.resolved_at, s.updated_at) DESC
        LIMIT 50
        """,
        company_id, cutoff,
    )
    out = []
    for r in rows:
        out.append(RemediationRecord(
            issue_key=r["issue_key"],
            source=r["source"],
            severity=r["severity"],
            title=r["title"],
            detail=r["detail"],
            status=r["status"],
            resolution_method=r["resolution_method"],
            resolution_note=r["resolution_note"],
            resolved_at=(r["resolved_at"] or r["updated_at"]).isoformat() if (r["resolved_at"] or r["updated_at"]) else None,
            resolved_by_name=r["resolver_name"],
            first_seen_at=r["first_seen_at"].isoformat() if r["first_seen_at"] else None,
            employee_id=str(r["employee_id"]) if r["employee_id"] else None,
        ))
    return out


async def dismiss_issue(conn, company_id: UUID, issue_key: str, reason: str, actor_user_id) -> bool:
    """Mark a currently-open issue as a dismissed false-positive. Idempotent;
    returns False if the issue_key isn't a known open row."""
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE compliance_issue_state
               SET status='dismissed', resolution_method='manual_dismiss',
                   resolution_note=$3, resolved_at=NOW(), resolved_by=$4, updated_at=NOW()
             WHERE company_id=$1 AND issue_key=$2 AND status='open'
             RETURNING entity_type, entity_id
            """,
            company_id, issue_key, reason, actor_user_id,
        )
        if row:
            await _log(conn, company_id, issue_key, row["entity_type"], row["entity_id"],
                       "dismissed", actor_user_id, {"reason": reason})
    return bool(row)


async def annotate_issue(conn, company_id: UUID, issue_key: str, note: str, actor_user_id) -> bool:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE compliance_issue_state
               SET resolution_note=$3, updated_at=NOW()
             WHERE company_id=$1 AND issue_key=$2
             RETURNING entity_type, entity_id
            """,
            company_id, issue_key, note,
        )
        if row:
            await _log(conn, company_id, issue_key, row["entity_type"], row["entity_id"],
                       "noted", actor_user_id, {"note": note})
    return bool(row)


async def reopen_issue(conn, company_id: UUID, issue_key: str, actor_user_id) -> bool:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE compliance_issue_state
               SET status='open', resolution_method=NULL, resolution_note=NULL,
                   resolved_at=NULL, resolved_by=NULL, updated_at=NOW()
             WHERE company_id=$1 AND issue_key=$2 AND status='dismissed'
             RETURNING entity_type, entity_id
            """,
            company_id, issue_key,
        )
        if row:
            await _log(conn, company_id, issue_key, row["entity_type"], row["entity_id"],
                       "reopened", actor_user_id)
    return bool(row)
