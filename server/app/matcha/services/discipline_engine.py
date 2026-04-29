"""Discipline Escalation Engine.

Pure-ish service powering /api/discipline. Reads policy mapping per company,
recommends the next discipline level given an employee's active history,
issues records atomically with supersede flips, sweeps stale records to
expired, and writes an audit row on every state change.

The engine never returns "termination" as an issuable level — it returns a
`termination_review` flag that routes the caller into the existing
pre-termination risk check flow.

Look-back rule: first-in-first-out, no refresh. New infractions never
extend the timer of prior ones. Each record carries its own `expires_at`
snapshot from the active policy at issue time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_INFRACTION_TYPES: list[dict[str, Any]] = [
    {
        "infraction_type": "attendance",
        "label": "Attendance",
        "default_severity": "moderate",
        "lookback_minor": 6, "lookback_moderate": 9, "lookback_severe": 12,
        "auto_to_written": False,
    },
    {
        "infraction_type": "performance",
        "label": "Performance",
        "default_severity": "moderate",
        "lookback_minor": 6, "lookback_moderate": 9, "lookback_severe": 12,
        "auto_to_written": False,
    },
    {
        "infraction_type": "safety",
        "label": "Safety",
        "default_severity": "severe",
        "lookback_minor": 6, "lookback_moderate": 9, "lookback_severe": 12,
        "auto_to_written": False,
    },
    {
        "infraction_type": "harassment",
        "label": "Harassment",
        "default_severity": "severe",
        "lookback_minor": 12, "lookback_moderate": 12, "lookback_severe": 24,
        "auto_to_written": True,
    },
    {
        "infraction_type": "policy_violation",
        "label": "Policy Violation",
        "default_severity": "moderate",
        "lookback_minor": 6, "lookback_moderate": 9, "lookback_severe": 12,
        "auto_to_written": False,
    },
    {
        "infraction_type": "gross_misconduct",
        "label": "Gross Misconduct",
        "default_severity": "immediate_written",
        "lookback_minor": 12, "lookback_moderate": 12, "lookback_severe": 24,
        "auto_to_written": True,
    },
]

VALID_LEVELS = ("verbal_warning", "written_warning", "pip", "final_warning", "suspension")
VALID_SEVERITIES = ("minor", "moderate", "severe", "immediate_written")

LEVEL_RANK = {
    "verbal_warning": 1,
    "written_warning": 2,
    "pip": 2,
    "final_warning": 3,
    "suspension": 3,
}


# ── Policy mapping ──────────────────────────────────────────────────────

async def ensure_default_policy_mapping(conn, company_id: UUID) -> None:
    """Seed the six default infraction-type rows for a company if missing."""
    for cfg in DEFAULT_INFRACTION_TYPES:
        await conn.execute(
            """
            INSERT INTO discipline_policy_mapping
              (company_id, infraction_type, label, default_severity,
               lookback_months_minor, lookback_months_moderate, lookback_months_severe,
               auto_to_written, notify_grandparent_manager)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE)
            ON CONFLICT (company_id, infraction_type) DO NOTHING
            """,
            company_id,
            cfg["infraction_type"],
            cfg["label"],
            cfg["default_severity"],
            cfg["lookback_minor"],
            cfg["lookback_moderate"],
            cfg["lookback_severe"],
            cfg["auto_to_written"],
        )


async def list_policy_mappings(conn, company_id: UUID) -> list[dict[str, Any]]:
    await ensure_default_policy_mapping(conn, company_id)
    rows = await conn.fetch(
        """
        SELECT id, company_id, infraction_type, label, default_severity,
               lookback_months_minor, lookback_months_moderate, lookback_months_severe,
               auto_to_written, notify_grandparent_manager,
               created_at, updated_at
        FROM discipline_policy_mapping
        WHERE company_id = $1
        ORDER BY label
        """,
        company_id,
    )
    return [dict(r) for r in rows]


async def get_policy_mapping(conn, company_id: UUID, infraction_type: str) -> dict[str, Any]:
    """Return the mapping row for (company, type), seeding defaults first."""
    await ensure_default_policy_mapping(conn, company_id)
    row = await conn.fetchrow(
        """
        SELECT id, company_id, infraction_type, label, default_severity,
               lookback_months_minor, lookback_months_moderate, lookback_months_severe,
               auto_to_written, notify_grandparent_manager
        FROM discipline_policy_mapping
        WHERE company_id = $1 AND infraction_type = $2
        """,
        company_id, infraction_type,
    )
    if row:
        return dict(row)
    # Unknown type — fall back to a moderate default so the engine still works.
    return {
        "company_id": company_id,
        "infraction_type": infraction_type,
        "label": infraction_type.replace("_", " ").title(),
        "default_severity": "moderate",
        "lookback_months_minor": 6,
        "lookback_months_moderate": 9,
        "lookback_months_severe": 12,
        "auto_to_written": False,
        "notify_grandparent_manager": True,
    }


async def upsert_policy_mapping(
    conn, company_id: UUID, infraction_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    label = payload.get("label") or infraction_type.replace("_", " ").title()
    row = await conn.fetchrow(
        """
        INSERT INTO discipline_policy_mapping
          (company_id, infraction_type, label, default_severity,
           lookback_months_minor, lookback_months_moderate, lookback_months_severe,
           auto_to_written, notify_grandparent_manager, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        ON CONFLICT (company_id, infraction_type) DO UPDATE SET
          label = EXCLUDED.label,
          default_severity = EXCLUDED.default_severity,
          lookback_months_minor = EXCLUDED.lookback_months_minor,
          lookback_months_moderate = EXCLUDED.lookback_months_moderate,
          lookback_months_severe = EXCLUDED.lookback_months_severe,
          auto_to_written = EXCLUDED.auto_to_written,
          notify_grandparent_manager = EXCLUDED.notify_grandparent_manager,
          updated_at = NOW()
        RETURNING id, company_id, infraction_type, label, default_severity,
                  lookback_months_minor, lookback_months_moderate, lookback_months_severe,
                  auto_to_written, notify_grandparent_manager,
                  created_at, updated_at
        """,
        company_id,
        infraction_type,
        label,
        payload.get("default_severity", "moderate"),
        int(payload.get("lookback_months_minor", 6)),
        int(payload.get("lookback_months_moderate", 9)),
        int(payload.get("lookback_months_severe", 12)),
        bool(payload.get("auto_to_written", False)),
        bool(payload.get("notify_grandparent_manager", True)),
    )
    return dict(row)


# ── Active history + recommendation ─────────────────────────────────────

async def fetch_active_history(conn, employee_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, discipline_type, severity, infraction_type,
               issued_date, expires_at, status, description, lookback_months
        FROM progressive_discipline
        WHERE employee_id = $1
          AND status = 'active'
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY issued_date DESC
        """,
        employee_id,
    )
    return [dict(r) for r in rows]


def _resolve_lookback(mapping: dict[str, Any], severity: str) -> int:
    if severity == "minor":
        return int(mapping["lookback_months_minor"])
    if severity == "severe" or severity == "immediate_written":
        return int(mapping["lookback_months_severe"])
    return int(mapping["lookback_months_moderate"])


def _next_level_from_history(active_levels: set[str]) -> tuple[str, bool]:
    """Returns (recommended_level, termination_review_flag).

    Climbs the ladder by counting distinct active levels:
      0 active → verbal_warning
      verbal active → written_warning
      written active → final_warning
      final active → termination_review
    """
    has_verbal = "verbal_warning" in active_levels
    has_written = "written_warning" in active_levels or "pip" in active_levels
    has_final = "final_warning" in active_levels or "suspension" in active_levels

    if has_final:
        return ("final_warning", True)  # routes to pre-term flow
    if has_written:
        return ("final_warning", False)
    if has_verbal:
        return ("written_warning", False)
    return ("verbal_warning", False)


async def recommend_next_discipline(
    conn,
    *,
    employee_id: UUID,
    company_id: UUID,
    infraction_type: str,
    severity: str,
) -> dict[str, Any]:
    """Pure recommendation. No row created.

    Returns:
        {
          "recommended_level": str,
          "termination_review": bool,   # final-warning already active
          "reasoning": [{...}],
          "supersedes": [<uuid>...],
          "lookback_months": int,
          "expires_at_preview": ISO8601 string,
          "override_available": True,
          "auto_to_written_triggered": bool,
          "policy_mapping": {...},
        }
    """
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")

    mapping = await get_policy_mapping(conn, company_id, infraction_type)
    history = await fetch_active_history(conn, employee_id)

    active_levels = {h["discipline_type"] for h in history}
    auto_to_written = bool(mapping.get("auto_to_written"))
    auto_triggered = severity == "immediate_written" or auto_to_written

    if auto_triggered:
        recommended_level = "final_warning"
        termination_review = "final_warning" in active_levels or "suspension" in active_levels
    else:
        recommended_level, termination_review = _next_level_from_history(active_levels)

    # Supersede: every active record at <= the new level's rank is escalated.
    new_rank = LEVEL_RANK.get(recommended_level, 1)
    supersedes = [
        str(h["id"]) for h in history
        if LEVEL_RANK.get(h["discipline_type"], 1) <= new_rank
    ]

    lookback = _resolve_lookback(mapping, severity)
    issued = datetime.now(timezone.utc)
    expires_preview = issued.replace(microsecond=0).isoformat()
    # Preview only — actual expires_at is computed in SQL on insert.

    reasoning: list[dict[str, Any]] = []
    if not history:
        reasoning.append({
            "text": "No active discipline records on file. Starting with verbal warning.",
        })
    else:
        for h in history:
            reasoning.append({
                "text": (
                    f"{h['discipline_type'].replace('_', ' ').title()} issued "
                    f"{h['issued_date'].isoformat() if h['issued_date'] else 'unknown date'} "
                    f"still active until "
                    f"{h['expires_at'].date().isoformat() if h['expires_at'] else 'no expiry set'}"
                ),
                "discipline_id": str(h["id"]),
            })
    if auto_triggered:
        reasoning.append({
            "text": (
                "Severity 'immediate_written' or policy 'auto_to_written' — "
                "skipping ladder climb and recommending final warning."
            ),
        })

    return {
        "recommended_level": recommended_level,
        "termination_review": termination_review,
        "reasoning": reasoning,
        "supersedes": supersedes,
        "lookback_months": lookback,
        "expires_at_preview": expires_preview,
        "override_available": True,
        "auto_to_written_triggered": auto_triggered,
        "policy_mapping": {
            "infraction_type": mapping["infraction_type"],
            "label": mapping["label"],
            "default_severity": mapping["default_severity"],
            "auto_to_written": auto_to_written,
            "notify_grandparent_manager": bool(mapping.get("notify_grandparent_manager", True)),
        },
    }


# ── Issue (atomic supersede + audit) ────────────────────────────────────

async def issue_discipline_with_supersede(
    *,
    actor_user_id: UUID,
    company_id: UUID,
    employee_id: UUID,
    infraction_type: str,
    severity: str,
    discipline_type: str,
    issued_date,  # date
    description: Optional[str],
    expected_improvement: Optional[str],
    review_date=None,  # date
    documents: Optional[list[Any]] = None,
    override_level: bool = False,
    override_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Insert new record, flip prior actives to escalated, write audit log."""
    if discipline_type not in VALID_LEVELS:
        raise ValueError(f"Invalid discipline_type: {discipline_type}")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")
    if override_level and not (override_reason and len(override_reason.strip()) >= 20):
        raise ValueError("override_reason must be at least 20 characters when override_level is true")

    async with get_connection() as conn:
        async with conn.transaction():
            mapping = await get_policy_mapping(conn, company_id, infraction_type)
            lookback = _resolve_lookback(mapping, severity)

            # Find supersede candidates (same employee, active, <= new rank)
            history = await fetch_active_history(conn, employee_id)
            new_rank = LEVEL_RANK.get(discipline_type, 1)
            supersede_ids = [
                h["id"] for h in history
                if LEVEL_RANK.get(h["discipline_type"], 1) <= new_rank
            ]
            escalated_from = supersede_ids[0] if supersede_ids else None

            row = await conn.fetchrow(
                """
                INSERT INTO progressive_discipline (
                    employee_id, company_id, discipline_type, issued_date, issued_by,
                    description, expected_improvement, review_date,
                    status, documents, infraction_type, severity, lookback_months,
                    expires_at, escalated_from_id, override_level, override_reason,
                    signature_status
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    'draft', $9::jsonb, $10, $11, $12,
                    ($4::date)::timestamptz + ($12 || ' months')::interval,
                    $13, $14, $15, 'pending'
                )
                RETURNING id, employee_id, company_id, discipline_type, issued_date,
                          issued_by, description, expected_improvement, review_date,
                          status, outcome_notes, documents, infraction_type, severity,
                          lookback_months, expires_at, escalated_from_id,
                          override_level, override_reason, signature_status,
                          signature_requested_at, signature_completed_at,
                          signature_envelope_id, signed_pdf_storage_path,
                          meeting_held_at, created_at, updated_at
                """,
                employee_id, company_id, discipline_type, issued_date, actor_user_id,
                description, expected_improvement, review_date,
                json.dumps(documents or []),
                infraction_type, severity, lookback,
                escalated_from, override_level, override_reason,
            )

            new_id = row["id"]

            # Flip superseded actives → escalated
            if supersede_ids:
                await conn.execute(
                    """
                    UPDATE progressive_discipline
                    SET status = 'escalated', updated_at = NOW()
                    WHERE id = ANY($1::uuid[]) AND status = 'active'
                    """,
                    supersede_ids,
                )
                for sid in supersede_ids:
                    await write_audit(
                        conn, sid, actor_user_id, "escalated",
                        details={"superseded_by": str(new_id)},
                    )

            # Audit row for the new record
            await write_audit(
                conn, new_id, actor_user_id, "created",
                details={
                    "infraction_type": infraction_type,
                    "severity": severity,
                    "discipline_type": discipline_type,
                    "lookback_months": lookback,
                    "override_level": override_level,
                    "override_reason": override_reason,
                    "supersedes": [str(s) for s in supersede_ids],
                },
            )
            if override_level:
                await write_audit(
                    conn, new_id, actor_user_id, "overridden",
                    details={"override_reason": override_reason},
                )

            return _row_to_dict(row)


# ── State transitions ───────────────────────────────────────────────────

async def transition_status(
    conn, discipline_id: UUID, *, expected_from: list[str], to: str,
    extra_sets: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Idempotent-friendly status flip. Returns updated row or None if no-op."""
    extra_sql = ""
    extra_values: list[Any] = []
    if extra_sets:
        parts = []
        idx = 4
        for col, val in extra_sets.items():
            parts.append(f"{col} = ${idx}")
            extra_values.append(val)
            idx += 1
        extra_sql = ", " + ", ".join(parts)

    row = await conn.fetchrow(
        f"""
        UPDATE progressive_discipline
        SET status = $2, updated_at = NOW(){extra_sql}
        WHERE id = $1 AND status = ANY($3::text[])
        RETURNING id, employee_id, company_id, discipline_type, issued_date,
                  issued_by, description, expected_improvement, review_date,
                  status, outcome_notes, documents, infraction_type, severity,
                  lookback_months, expires_at, escalated_from_id,
                  override_level, override_reason, signature_status,
                  signature_requested_at, signature_completed_at,
                  signature_envelope_id, signed_pdf_storage_path,
                  meeting_held_at, created_at, updated_at
        """,
        discipline_id, to, expected_from, *extra_values,
    )
    return _row_to_dict(row) if row else None


async def update_signature_status(
    conn, discipline_id: UUID, *, signature_status: str,
    extra_sets: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    sets_sql = ""
    extra_values: list[Any] = []
    if extra_sets:
        parts = []
        idx = 3
        for col, val in extra_sets.items():
            parts.append(f"{col} = ${idx}")
            extra_values.append(val)
            idx += 1
        sets_sql = ", " + ", ".join(parts)

    row = await conn.fetchrow(
        f"""
        UPDATE progressive_discipline
        SET signature_status = $2, updated_at = NOW(){sets_sql}
        WHERE id = $1
        RETURNING id, employee_id, company_id, discipline_type, issued_date,
                  issued_by, description, expected_improvement, review_date,
                  status, outcome_notes, documents, infraction_type, severity,
                  lookback_months, expires_at, escalated_from_id,
                  override_level, override_reason, signature_status,
                  signature_requested_at, signature_completed_at,
                  signature_envelope_id, signed_pdf_storage_path,
                  meeting_held_at, created_at, updated_at
        """,
        discipline_id, signature_status, *extra_values,
    )
    return _row_to_dict(row) if row else None


# ── Audit log ───────────────────────────────────────────────────────────

async def write_audit(
    conn, discipline_id: UUID, actor_user_id: Optional[UUID], action: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO discipline_audit_log (discipline_id, actor_user_id, action, details)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        discipline_id, actor_user_id, action, json.dumps(details or {}),
    )


async def list_audit_log(conn, discipline_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, discipline_id, actor_user_id, action, details, created_at
        FROM discipline_audit_log
        WHERE discipline_id = $1
        ORDER BY created_at ASC
        """,
        discipline_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        details = d.get("details")
        if isinstance(details, str):
            try:
                d["details"] = json.loads(details)
            except (json.JSONDecodeError, ValueError):
                d["details"] = {}
        out.append(d)
    return out


# ── Expiry sweep ────────────────────────────────────────────────────────

async def expire_stale_records() -> int:
    """Flip active → expired where expires_at <= NOW(). Returns count."""
    async with get_connection() as conn:
        async with conn.transaction():
            ids = await conn.fetch(
                """
                UPDATE progressive_discipline
                SET status = 'expired', updated_at = NOW()
                WHERE status = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at <= NOW()
                RETURNING id
                """
            )
            for r in ids:
                await write_audit(conn, r["id"], None, "expired", {"reason": "expires_at passed"})
            return len(ids)


# ── Fetchers ────────────────────────────────────────────────────────────

async def fetch_record(conn, discipline_id: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT id, employee_id, company_id, discipline_type, issued_date,
               issued_by, description, expected_improvement, review_date,
               status, outcome_notes, documents, infraction_type, severity,
               lookback_months, expires_at, escalated_from_id,
               override_level, override_reason, signature_status,
               signature_requested_at, signature_completed_at,
               signature_envelope_id, signed_pdf_storage_path,
               meeting_held_at, created_at, updated_at
        FROM progressive_discipline
        WHERE id = $1
        """,
        discipline_id,
    )
    return _row_to_dict(row) if row else None


async def fetch_record_by_envelope(conn, envelope_id: str) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT id, employee_id, company_id, discipline_type, issued_date,
               issued_by, description, expected_improvement, review_date,
               status, outcome_notes, documents, infraction_type, severity,
               lookback_months, expires_at, escalated_from_id,
               override_level, override_reason, signature_status,
               signature_requested_at, signature_completed_at,
               signature_envelope_id, signed_pdf_storage_path,
               meeting_held_at, created_at, updated_at
        FROM progressive_discipline
        WHERE signature_envelope_id = $1
        """,
        envelope_id,
    )
    return _row_to_dict(row) if row else None


async def list_records_for_employee(conn, employee_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, employee_id, company_id, discipline_type, issued_date,
               issued_by, description, expected_improvement, review_date,
               status, outcome_notes, documents, infraction_type, severity,
               lookback_months, expires_at, escalated_from_id,
               override_level, override_reason, signature_status,
               signature_requested_at, signature_completed_at,
               signature_envelope_id, signed_pdf_storage_path,
               meeting_held_at, created_at, updated_at
        FROM progressive_discipline
        WHERE employee_id = $1
        ORDER BY issued_date DESC, created_at DESC
        """,
        employee_id,
    )
    return [_row_to_dict(r) for r in rows]


async def list_records_for_company(
    conn, company_id: UUID, *, status_filter: Optional[str] = None, limit: int = 200,
) -> list[dict[str, Any]]:
    if status_filter:
        rows = await conn.fetch(
            """
            SELECT id, employee_id, company_id, discipline_type, issued_date,
                   issued_by, description, expected_improvement, review_date,
                   status, outcome_notes, documents, infraction_type, severity,
                   lookback_months, expires_at, escalated_from_id,
                   override_level, override_reason, signature_status,
                   signature_requested_at, signature_completed_at,
                   signature_envelope_id, signed_pdf_storage_path,
                   meeting_held_at, created_at, updated_at
            FROM progressive_discipline
            WHERE company_id = $1 AND status = $2
            ORDER BY issued_date DESC, created_at DESC
            LIMIT $3
            """,
            company_id, status_filter, limit,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, employee_id, company_id, discipline_type, issued_date,
                   issued_by, description, expected_improvement, review_date,
                   status, outcome_notes, documents, infraction_type, severity,
                   lookback_months, expires_at, escalated_from_id,
                   override_level, override_reason, signature_status,
                   signature_requested_at, signature_completed_at,
                   signature_envelope_id, signed_pdf_storage_path,
                   meeting_held_at, created_at, updated_at
            FROM progressive_discipline
            WHERE company_id = $1
            ORDER BY issued_date DESC, created_at DESC
            LIMIT $2
            """,
            company_id, limit,
        )
    return [_row_to_dict(r) for r in rows]


# ── Helpers ─────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    docs = d.get("documents")
    if isinstance(docs, str):
        try:
            d["documents"] = json.loads(docs)
        except (json.JSONDecodeError, ValueError):
            d["documents"] = []
    return d
