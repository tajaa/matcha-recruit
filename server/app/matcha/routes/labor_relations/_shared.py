"""Cross-cutting helpers for the Labor Relations package.

Holds the contractual-deadline math (the edge-case-heavy core), the shared
audit writer, grievance numbering, step seeding, row serialization, and the
tenant-ownership 404 guards. Routers import everything they need from here —
don't redefine these locally.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ── Default grievance procedure ──────────────────────────────────────────────
# Used to seed steps when a grievance has no CBA, or the CBA's
# grievance_step_config is empty / unconfirmed. Deadlines computed off this are
# advisory until HR confirms a real procedure on the CBA — callers should
# surface `used_fallback=True` to the UI rather than treat these as contractual.
DEFAULT_GRIEVANCE_STEPS: list[dict[str, Any]] = [
    {"step": 1, "name": "Step 1 — Supervisor", "file_within_days": 10, "respond_within_days": 5, "day_basis": "calendar"},
    {"step": 2, "name": "Step 2 — HR / Dept Head", "file_within_days": 5, "respond_within_days": 10, "day_basis": "calendar"},
    {"step": 3, "name": "Step 3 — Executive / Labor Relations", "file_within_days": 5, "respond_within_days": 15, "day_basis": "calendar"},
    {"step": 4, "name": "Step 4 — Arbitration", "file_within_days": 30, "respond_within_days": 0, "day_basis": "calendar"},
]


# ── Serialization ────────────────────────────────────────────────────────────

def _serialize(row: Any) -> Any:
    """Convert an asyncpg Record (or dict) to a JSON-friendly dict.

    UUID/date/datetime → str; JSON/JSONB text columns are left as-is (asyncpg
    returns jsonb as Python objects already). Returns None unchanged.
    """
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k, v in dict(row).items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _serialize_list(rows: Any) -> list[dict[str, Any]]:
    return [_serialize(r) for r in (rows or [])]


# ── Contractual deadline math ────────────────────────────────────────────────
# v1 supports calendar days and a simple business-day mode (skip Sat/Sun).
# Holiday roll-forward and tolling (mutual extensions) are KNOWN GAPS — the
# day_basis is a per-CBA config field so it can be corrected without a migration.

def add_days(anchor: date, n: int, basis: str = "calendar") -> date:
    """Return ``anchor`` + ``n`` days, by calendar or working (Mon–Fri) basis."""
    if n <= 0:
        return anchor
    if basis == "working":
        d = anchor
        remaining = n
        while remaining > 0:
            d = d + timedelta(days=1)
            if d.weekday() < 5:  # 0=Mon .. 4=Fri
                remaining -= 1
        return d
    return anchor + timedelta(days=n)


def normalize_step_config(raw: Any) -> list[dict[str, Any]]:
    """Coerce a stored/posted grievance_step_config into a clean ordered list."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = []
    if not isinstance(raw, list):
        return []
    steps: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        steps.append({
            "step": int(item.get("step") or (i + 1)),
            "name": str(item.get("name") or f"Step {i + 1}"),
            "file_within_days": int(item.get("file_within_days") or 0),
            "respond_within_days": int(item.get("respond_within_days") or 0),
            "day_basis": "working" if item.get("day_basis") == "working" else "calendar",
        })
    steps.sort(key=lambda s: s["step"])
    return steps


def resolve_step_config(cba_row: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Resolve the grievance procedure for a CBA.

    Returns (steps, used_fallback). Falls back to DEFAULT_GRIEVANCE_STEPS when
    there is no CBA or its config is empty.
    """
    if cba_row:
        steps = normalize_step_config(cba_row.get("grievance_step_config"))
        if steps:
            return steps, False
    return list(DEFAULT_GRIEVANCE_STEPS), True


def _find_step(step_config: list[dict[str, Any]], step_number: int) -> Optional[dict[str, Any]]:
    for s in step_config:
        if s.get("step") == step_number:
            return s
    return None


def compute_step_deadlines(
    step_config: list[dict[str, Any]],
    step_number: int,
    anchor_date: date,
) -> dict[str, Optional[date]]:
    """Compute the contractual deadlines for one grievance step.

    ``anchor_date`` is when this step became active (typically the filing /
    advance date). ``deadline_to_respond`` is management's window to answer this
    step; ``deadline_to_advance`` is the union's window to carry an unresolved
    grievance to the NEXT step (so it depends on the next step's
    ``file_within_days``). Either may be None when the relevant config is absent.
    """
    step = _find_step(step_config, step_number)
    if not step:
        return {"deadline_to_respond": None, "deadline_to_advance": None}

    basis = step.get("day_basis", "calendar")
    respond_days = int(step.get("respond_within_days") or 0)
    deadline_to_respond = add_days(anchor_date, respond_days, basis) if respond_days > 0 else None

    next_step = _find_step(step_config, step_number + 1)
    deadline_to_advance: Optional[date] = None
    if next_step:
        advance_days = int(next_step.get("file_within_days") or 0)
        if advance_days > 0:
            # The advance window opens once this step is answered; at seed time
            # we anchor it off the response deadline as a planning estimate. It
            # is recomputed off the real response date when a response lands.
            base = deadline_to_respond or anchor_date
            deadline_to_advance = add_days(base, advance_days, next_step.get("day_basis", "calendar"))
    return {"deadline_to_respond": deadline_to_respond, "deadline_to_advance": deadline_to_advance}


# ── Audit ────────────────────────────────────────────────────────────────────

async def write_audit(
    conn,
    company_id: UUID,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: Optional[UUID],
    action: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """Append a row to lr_audit_log. Call inside the mutating transaction."""
    await conn.execute(
        """
        INSERT INTO lr_audit_log (company_id, entity_type, entity_id, actor_user_id, action, details)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        company_id, entity_type, entity_id, actor_user_id, action,
        json.dumps(details or {}),
    )


# ── Grievance numbering ──────────────────────────────────────────────────────

async def next_grievance_number(conn, company_id: UUID) -> str:
    """Generate the next per-company grievance number: GRV-YYYY-NNNN.

    Per-company sequential within the current year. The UNIQUE(company_id,
    grievance_number) constraint is the backstop against a concurrent dup —
    callers retry on a unique violation.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"GRV-{year}-"
    last = await conn.fetchval(
        """
        SELECT grievance_number FROM lr_grievances
        WHERE company_id = $1 AND grievance_number LIKE $2
        ORDER BY grievance_number DESC
        LIMIT 1
        """,
        company_id, prefix + "%",
    )
    seq = 1
    if last:
        try:
            seq = int(str(last).rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:04d}"


# ── Step seeding ─────────────────────────────────────────────────────────────

async def seed_grievance_steps(
    conn,
    grievance_id: UUID,
    company_id: UUID,
    step_config: list[dict[str, Any]],
) -> None:
    """Insert the per-step timeline rows (all 'pending') from a step config."""
    for s in step_config:
        await conn.execute(
            """
            INSERT INTO lr_grievance_steps
                (grievance_id, company_id, step_number, step_name, status)
            VALUES ($1, $2, $3, $4, 'pending')
            ON CONFLICT (grievance_id, step_number) DO NOTHING
            """,
            grievance_id, company_id, int(s["step"]), str(s["name"]),
        )


# ── Tenant-ownership guards ──────────────────────────────────────────────────

def _require_company(company_id: Optional[UUID]) -> UUID:
    """Reject callers with no resolvable company scope."""
    if not company_id:
        raise HTTPException(status_code=403, detail="No company context for this user")
    return company_id


async def get_cba_or_404(conn, cba_id: UUID, company_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT * FROM lr_cbas WHERE id = $1 AND company_id = $2",
        cba_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="CBA not found")
    return dict(row)


async def get_grievance_or_404(conn, grievance_id: UUID, company_id: UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT * FROM lr_grievances WHERE id = $1 AND company_id = $2",
        grievance_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return dict(row)
