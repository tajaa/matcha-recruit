"""Shared training-assignment logic — the one place that decides who gets a
training record and why.

Extracted from the `bulk_assign` route (`routes/employee_lifecycle/training.py`)
so the same audience-matching + conflict-safe insert is reusable from:
  - the manual bulk-assign button (existing route, now a thin wrapper)
  - the cadence worker (`workers/tasks/training_cadence.py`, pool-free Celery)
  - new-hire assignment rules (called from employee create / bulk upload / HRIS sync)
  - incident-close auto-rules and admin/Copilot-driven assignment
  - discipline issuance (remedial training)

Every write here stamps `source_type`/`source_ref` (migration `trainint01`) so
downstream consumers (epl_readiness, legal_defense, hr_pilot_corpus, ...) can
tell a routine assignment from a remedial one.

Pool-free-safe: every function takes `conn` explicitly rather than opening its
own connection, so it works unchanged inside a Celery task (see the
`connection_or_direct` note in the root CLAUDE.md) and inside a FastAPI route.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Sequence
from uuid import UUID

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = {
    "manual",
    "bulk_assign",
    "rule",
    "new_hire",
    "incident",
    "discipline",
    "credential",
    "cadence",
    "schedule",
}


@dataclass
class AssignResult:
    assigned: int = 0
    accelerated: int = 0
    already_open: int = 0

    @property
    def requirement_id(self) -> Optional[str]:
        return None

    def as_dict(self) -> dict:
        return {
            "assigned_count": self.assigned,
            "accelerated_count": self.accelerated,
            "already_open_count": self.already_open,
        }


async def resolve_audience(
    conn,
    company_id: UUID,
    *,
    applies_to: str = "all",
    work_states: Optional[Sequence[str]] = None,
    departments: Optional[Sequence[str]] = None,
    employee_ids: Optional[Sequence[UUID]] = None,
) -> list[UUID]:
    """Return active employee ids matching the given audience predicate.

    Mirrors the WHERE clause `bulk_assign` used inline
    (`routes/employee_lifecycle/training.py:337-350`): active employment,
    `applies_to` against `is_supervisor`, and an optional `work_states`
    filter. `employee_ids`, when given, further restricts the result to that
    set (still requiring active employment) — this is how incident/discipline
    triggers scope to specific people instead of a full audience sweep.
    """
    applies_to = (applies_to or "all").lower()
    conditions = [
        "org_id = $1",
        "(termination_date IS NULL OR termination_date > CURRENT_DATE)",
    ]
    params: list = [company_id]

    if applies_to == "supervisor":
        conditions.append("is_supervisor = TRUE")
    elif applies_to == "nonsupervisor":
        conditions.append("is_supervisor = FALSE")

    if work_states:
        params.append(list(work_states))
        conditions.append(f"work_state = ANY(${len(params)})")

    if departments:
        params.append(list(departments))
        conditions.append(f"department = ANY(${len(params)})")

    if employee_ids:
        params.append(list(employee_ids))
        conditions.append(f"id = ANY(${len(params)})")

    rows = await conn.fetch(
        f"SELECT id FROM employees WHERE {' AND '.join(conditions)}",
        *params,
    )
    return [r["id"] for r in rows]


async def assign_training(
    conn,
    company_id: UUID,
    requirement: dict,
    employee_ids: Sequence[UUID],
    *,
    source_type: str,
    source_ref: Optional[UUID] = None,
    source_note: Optional[str] = None,
    due_date: Optional[date] = None,
    assigned_by: Optional[UUID] = None,
) -> AssignResult:
    """Assign `requirement` to each of `employee_ids`, stamping provenance.

    Conflict policy: the partial unique index
    `idx_training_records_active_assignment` blocks a second active
    assignment of the same requirement to the same employee. Rather than
    silently no-op (the previous `bulk_assign` behavior, fine for routine
    audience sweeps but wrong for remediation), an already-open record has
    its `due_date` pulled in to `LEAST(existing, proposed)` and the new
    source note appended — an incident-driven assignment should never be
    invisible just because a routine one is already pending.
    """
    result = AssignResult()
    if not employee_ids:
        return result

    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type!r}")

    assigned_date = date.today()
    resolved_due_date = due_date
    if resolved_due_date is None and requirement.get("frequency_months"):
        resolved_due_date = assigned_date + timedelta(days=requirement["frequency_months"] * 30)

    values_parts = []
    params: list = [
        company_id,
        requirement["id"],
        requirement["title"],
        requirement["training_type"],
        assigned_date,
        resolved_due_date,
        assigned_by,
        source_type,
        source_ref,
        source_note,
    ]
    base_idx = len(params) + 1
    for i, employee_id in enumerate(employee_ids):
        values_parts.append(f"($1, ${base_idx + i}, $2, $3, $4, $5, $6, $7, $8, $9, $10)")
        params.append(employee_id)

    inserted_rows = await conn.fetch(
        f"""
        INSERT INTO training_records
            (company_id, employee_id, requirement_id, title, training_type,
             assigned_date, due_date, assigned_by, source_type, source_ref, source_note)
        VALUES {', '.join(values_parts)}
        ON CONFLICT (employee_id, requirement_id)
            WHERE status IN ('assigned', 'in_progress')
        DO NOTHING
        RETURNING employee_id
        """,
        *params,
    )
    result.assigned = len(inserted_rows)

    assigned_ids = {r["employee_id"] for r in inserted_rows}
    skipped_ids = [eid for eid in employee_ids if eid not in assigned_ids]

    if skipped_ids and (resolved_due_date is not None or source_note):
        note_suffix = f" | {source_note}" if source_note else ""
        accelerated_rows = await conn.fetch(
            """
            UPDATE training_records
            SET due_date = LEAST(due_date, $3),
                notes = COALESCE(notes, '') || $4
            WHERE requirement_id = $1
              AND employee_id = ANY($2)
              AND status IN ('assigned', 'in_progress')
              AND $3 IS NOT NULL
              AND (due_date IS NULL OR due_date > $3)
            RETURNING employee_id
            """,
            requirement["id"],
            skipped_ids,
            resolved_due_date,
            note_suffix,
        )
        result.accelerated = len(accelerated_rows)
        result.already_open = len(skipped_ids) - result.accelerated
    else:
        result.already_open = len(skipped_ids)

    return result


async def evaluate_new_hire_rules(conn, company_id: UUID, employee_id: UUID) -> AssignResult:
    """Match `employee_id` against active `trigger='new_hire'` rules and
    assign each matching requirement. Called from every employee-creation
    path (single create, bulk CSV, HRIS sync) so a new hire is enrolled at
    hire time instead of waiting on the cadence worker's periodic sweep.
    """
    employee = await conn.fetchrow(
        "SELECT id, work_state, department, is_supervisor, start_date "
        "FROM employees WHERE id = $1 AND org_id = $2",
        employee_id,
        company_id,
    )
    if not employee:
        return AssignResult()

    rules = await conn.fetch(
        """
        SELECT r.*, req.id AS req_id, req.title AS req_title,
               req.training_type AS req_training_type,
               req.frequency_months AS req_frequency_months,
               req.is_active AS req_is_active
        FROM training_assignment_rules r
        JOIN training_requirements req ON req.id = r.requirement_id
        WHERE r.company_id = $1 AND r.trigger = 'new_hire' AND r.is_active = TRUE
        """,
        company_id,
    )

    total = AssignResult()
    for rule in rules:
        if not rule["req_is_active"]:
            continue
        if rule["work_states"] and employee["work_state"] not in rule["work_states"]:
            continue
        if rule["departments"] and employee["department"] not in rule["departments"]:
            continue
        applies_to = (rule["applies_to"] or "all").lower()
        if applies_to == "supervisor" and not employee["is_supervisor"]:
            continue
        if applies_to == "nonsupervisor" and employee["is_supervisor"]:
            continue

        base_date = employee["start_date"] or date.today()
        due_date = base_date + timedelta(days=rule["due_days"]) if rule["due_days"] else None

        requirement = {
            "id": rule["req_id"],
            "title": rule["req_title"],
            "training_type": rule["req_training_type"],
            "frequency_months": rule["req_frequency_months"],
        }
        outcome = await assign_training(
            conn,
            company_id,
            requirement,
            [employee_id],
            source_type="new_hire",
            source_ref=rule["id"],
            due_date=due_date,
        )
        total.assigned += outcome.assigned
        total.accelerated += outcome.accelerated
        total.already_open += outcome.already_open

    return total


async def evaluate_incident_rules(
    conn,
    company_id: UUID,
    incident_id: UUID,
    *,
    incident_type: Optional[str],
    severity: Optional[str],
    involved_employee_ids: Sequence[UUID],
) -> AssignResult:
    """Match a just-closed incident against active `trigger='incident'` rules
    and assign matching requirements to its involved employees.

    Only `ir_incidents.involved_employee_ids` is used as the trainee pool —
    witnesses and `ir_people` rows are name-based with no `employees` FK and
    are deliberately excluded (see the plan's out-of-scope note).
    """
    total = AssignResult()
    if not involved_employee_ids:
        return total

    rules = await conn.fetch(
        """
        SELECT r.*, req.id AS req_id, req.title AS req_title,
               req.training_type AS req_training_type,
               req.frequency_months AS req_frequency_months,
               req.is_active AS req_is_active
        FROM training_assignment_rules r
        JOIN training_requirements req ON req.id = r.requirement_id
        WHERE r.company_id = $1 AND r.trigger = 'incident' AND r.is_active = TRUE
        """,
        company_id,
    )

    severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    for rule in rules:
        if not rule["req_is_active"]:
            continue
        if rule["incident_types"] and incident_type not in rule["incident_types"]:
            continue
        if rule["min_severity"]:
            min_rank = severity_order.get(rule["min_severity"], 0)
            cur_rank = severity_order.get(severity or "", -1)
            if cur_rank < min_rank:
                continue

        employee_ids = await resolve_audience(
            conn,
            company_id,
            applies_to=rule["applies_to"],
            work_states=rule["work_states"],
            departments=rule["departments"],
            employee_ids=involved_employee_ids,
        )
        if not employee_ids:
            continue

        requirement = {
            "id": rule["req_id"],
            "title": rule["req_title"],
            "training_type": rule["req_training_type"],
            "frequency_months": rule["req_frequency_months"],
        }
        outcome = await assign_training(
            conn,
            company_id,
            requirement,
            employee_ids,
            source_type="incident",
            source_ref=incident_id,
            source_note=f"Auto-assigned from incident rule (incident_type={incident_type})",
        )
        total.assigned += outcome.assigned
        total.accelerated += outcome.accelerated
        total.already_open += outcome.already_open

    return total


async def on_incident_closed(conn, company_id: UUID, incident: dict) -> AssignResult:
    """Entry point for the incident-close hook. `incident` must carry
    `id`, `incident_type`, `severity`, and `involved_employee_ids`. Called
    from both close paths (`ir_incidents/copilot.py:_close_incident_via_copilot`
    and the generic `PUT` in `ir_incidents/crud.py`) — after the status write,
    never before, so the three pre-close guards (OSHA emergency, root-cause
    prompt, OSHA recordable chain) never fire a spurious assignment.
    """
    return await evaluate_incident_rules(
        conn,
        company_id,
        incident["id"],
        incident_type=incident.get("incident_type"),
        severity=incident.get("severity"),
        involved_employee_ids=incident.get("involved_employee_ids") or [],
    )


def rule_matches_scheduled_role(
    rule: dict, employee: dict, shift_role: Optional[str],
) -> bool:
    """Pure predicate for a `trigger='scheduled_role'` rule.

    `rule` carries `roles` (list[str] | None — empty/None matches any role,
    including an open shift with no role set), `departments`, `work_states`,
    `applies_to`, `req_is_active`. `employee` carries `work_state`,
    `department`, `is_supervisor`. Role matching is case-insensitive /
    whitespace-trimmed — admins type roles by hand on both the shift and the
    rule, and a stray casing mismatch shouldn't silently skip the rule.
    """
    if not rule.get("req_is_active", True):
        return False

    roles = rule.get("roles")
    if roles:
        normalized = {r.strip().lower() for r in roles if r}
        if not shift_role or shift_role.strip().lower() not in normalized:
            return False

    if rule.get("departments") and employee.get("department") not in rule["departments"]:
        return False
    if rule.get("work_states") and employee.get("work_state") not in rule["work_states"]:
        return False

    applies_to = (rule.get("applies_to") or "all").lower()
    if applies_to == "supervisor" and not employee.get("is_supervisor"):
        return False
    if applies_to == "nonsupervisor" and employee.get("is_supervisor"):
        return False

    return True


async def evaluate_scheduled_role_rules(
    conn,
    company_id: UUID,
    employee_id: UUID,
    *,
    shift_id: UUID,
    shift_role: Optional[str],
    shift_start: date,
) -> AssignResult:
    """Match `employee_id` being scheduled into `shift_role` against active
    `trigger='scheduled_role'` rules and assign each matching requirement.

    Called after the assignment write commits (assign / swap-approve / shift
    create with up-front assignees) for `kind='work'` shifts — training-kind
    shifts (see migration `trainsched01`) assign their own
    `training_requirement_id` directly instead of going through rule
    matching. Due date is the shift's start date, clamped earlier by the
    rule's `due_days` when that would land sooner — the point is the
    training lands before the shift, not on the rule's usual cadence.
    """
    employee = await conn.fetchrow(
        "SELECT id, work_state, department, is_supervisor "
        "FROM employees WHERE id = $1 AND org_id = $2",
        employee_id,
        company_id,
    )
    if not employee:
        return AssignResult()

    rules = await conn.fetch(
        """
        SELECT r.*, req.id AS req_id, req.title AS req_title,
               req.training_type AS req_training_type,
               req.frequency_months AS req_frequency_months,
               req.is_active AS req_is_active
        FROM training_assignment_rules r
        JOIN training_requirements req ON req.id = r.requirement_id
        WHERE r.company_id = $1 AND r.trigger = 'scheduled_role' AND r.is_active = TRUE
        """,
        company_id,
    )

    total = AssignResult()
    for rule in rules:
        if not rule_matches_scheduled_role(dict(rule), dict(employee), shift_role):
            continue

        due_date = shift_start
        if rule["due_days"] is not None:
            candidate = date.today() + timedelta(days=rule["due_days"])
            due_date = min(shift_start, candidate)

        requirement = {
            "id": rule["req_id"],
            "title": rule["req_title"],
            "training_type": rule["req_training_type"],
            "frequency_months": rule["req_frequency_months"],
        }
        outcome = await assign_training(
            conn,
            company_id,
            requirement,
            [employee_id],
            source_type="schedule",
            source_ref=shift_id,
            source_note=f"Scheduled into role '{shift_role}'" if shift_role else "Scheduled shift assignment",
            due_date=due_date,
        )
        total.assigned += outcome.assigned
        total.accelerated += outcome.accelerated
        total.already_open += outcome.already_open

    return total
