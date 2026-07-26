"""Huume's confirm-first safety envelope + plan step executors.

Mirrors `services/pilots/hr_pilot_actions.py` exactly: a PURE, DB-free verdict
function carries every check that doesn't need the database (two-turn
confirm, role, feature flags, ordering, idempotency), and thin async
executors do the writes. The matcha-work skill engine does not feature- or
role-gate execution on its own — every guard a normal record write would get
must be re-asserted here.

Two staged things live in `mw_threads.current_state`:
  - `huume_action` — a single staged action (currently only `send_offer`).
  - `huume_plan`   — the onboarding plan staged after an offer is accepted.

Both follow the same two-turn rule: the model stages a proposal on one turn
and the loop executes it only after an explicit confirmation on a LATER turn
(never within the same turn that staged it).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Only a business admin / platform admin may execute a Huume action or plan
# step. Employees/creators/etc. reaching a thread must never trigger a write.
_ALLOWED_ROLES = {"client", "admin"}

# Every plan step Huume can propose, and the company feature flag (beyond
# `huume` + `matcha_work`) each one re-checks before executing. `None` means
# no extra flag — the step only needs `huume` + the ordering/idempotency
# checks below.
STEP_REQUIRED_FEATURE: dict[str, Optional[str]] = {
    "create_employee": "employees",
    "portal_invitation": "employees",
    "onboarding_tasks": "employees",
    "credential_requirements": "credential_templates",
    "training_assignment": "training",
    "google_workspace": None,   # gated on integration connection state instead
    "slack": None,              # gated on integration connection state instead
    "schedule_note": "employee_schedule",
    "benefits_note": "benefits_admin",
    "jurisdiction_packet_note": None,  # always available, read-only
}

# Steps that depend on the employee record existing before they can run.
_DEPENDS_ON_EMPLOYEE = {
    "portal_invitation", "onboarding_tasks", "credential_requirements",
    "training_assignment", "google_workspace", "slack",
    "schedule_note", "benefits_note", "jurisdiction_packet_note",
}

# Steps that need a connected integration (checked against the `integrations`
# dict passed to evaluate_plan_step: {provider: bool}).
_STEP_INTEGRATION_PROVIDER = {
    "google_workspace": "google_workspace",
    "slack": "slack",
}


@dataclass(frozen=True)
class HuumeVerdict:
    """Result of the pure safety envelope for a staged `huume_action`
    (currently only `send_offer`). Mirrors HrActionVerdict.

    kind: "proceed" — cleared for the executor (see `action`).
          "stage"   — staged this turn; tell the admin to confirm.
          "refuse"  — a guard blocked it.
    """
    kind: str
    message: str
    action: Optional[dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def evaluate_huume_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    role: Optional[str],
    thread_huume_mode: bool,
    this_turn_staged_new: bool,
) -> HuumeVerdict:
    """Pure, DB-free safety envelope for executing a staged `huume_action`
    (e.g. send_offer). Order: confirm-first → something staged → authz."""
    features = features or {}

    if this_turn_staged_new:
        return HuumeVerdict(
            kind="stage",
            message="I've drafted this for your review above. Reply \"confirm\" (or tell me what to change) and I'll do it.",
        )
    if not isinstance(staged_action, dict):
        return HuumeVerdict(kind="refuse", message="There's nothing staged to confirm yet.")

    if staged_action.get("status") != "proposed":
        return HuumeVerdict(kind="refuse", message="That action isn't awaiting confirmation (it may already be done).")

    action_type = str(staged_action.get("type") or "").strip()
    if action_type not in {"send_offer"}:
        return HuumeVerdict(kind="refuse", message="That action type isn't something I can execute.")

    if not thread_huume_mode:
        return HuumeVerdict(kind="refuse", message="Huume actions are only available in a Huume thread.")
    if not features.get("huume"):
        return HuumeVerdict(kind="refuse", message="Huume isn't enabled for this company.")
    if not features.get("matcha_work"):
        return HuumeVerdict(kind="refuse", message="Matcha Work isn't enabled for this company.")
    if not features.get("offer_letters"):
        return HuumeVerdict(kind="refuse", message="Offer letters aren't enabled for this company.")
    if (role or "").strip().lower() not in _ALLOWED_ROLES:
        return HuumeVerdict(kind="refuse", message="Only a business admin can send an offer.")

    offer_id = staged_action.get("offer_id")
    if not offer_id:
        return HuumeVerdict(kind="refuse", message="There's no offer to send.")

    return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))


def evaluate_plan_step(
    step: dict[str, Any],
    *,
    features: dict[str, Any],
    integrations: dict[str, bool],
    employee_id: Optional[str],
) -> Optional[str]:
    """Pure. Returns None if `step` may execute now, else a skip/refuse
    reason string. Re-run at execute time (not just at plan-build time) so a
    flag flip or an already-done step between turns is caught."""
    features = features or {}
    integrations = integrations or {}
    key = step.get("key")

    if step.get("record_id"):
        return "already done"
    if step.get("status") == "skipped":
        return step.get("reason") or "skipped"

    # Feature/integration checks come BEFORE the employee-dependency check —
    # at plan-build time employee_id is always None (the employee doesn't
    # exist yet), so if the employee check ran first every dependent step
    # would report "waiting on create_employee" and mask its real reason
    # (missing feature flag / unconnected integration) from the admin.
    required = STEP_REQUIRED_FEATURE.get(key)
    if required and not features.get(required):
        return f"{required} isn't enabled for this company"

    provider = _STEP_INTEGRATION_PROVIDER.get(key)
    if provider and not integrations.get(provider):
        return f"{provider.replace('_', ' ').title()} isn't connected"

    if key in _DEPENDS_ON_EMPLOYEE and not employee_id:
        return "waiting on create_employee to run first"

    return None


# ---------------------------------------------------------------------------
# DB-bound: staged action executor
# ---------------------------------------------------------------------------

async def execute_huume_action(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]) -> dict[str, Any]:
    """Execute a validated staged huume_action. Assumes evaluate_huume_action
    returned kind=='proceed'."""
    from app.matcha.services.huume import onboarding_skill

    if action.get("type") == "send_offer":
        return await onboarding_skill.execute_send_offer(
            company_id=company_id, actor_user_id=actor_user_id, offer_id=action["offer_id"],
        )
    return {"status": "error", "message": "Unsupported action."}


# ---------------------------------------------------------------------------
# DB-bound: plan step executors
# ---------------------------------------------------------------------------

@dataclass
class PlanExecutionResult:
    plan: dict[str, Any]
    summaries: list[str] = field(default_factory=list)


def mark_steps_approved(plan: dict[str, Any], step_keys: Optional[list[str]]) -> dict[str, Any]:
    """Pure. Flips matching `proposed` steps to `approved` in place on a copy.
    Empty/None `step_keys` approves every step still `proposed` (an admin
    saying "approve everything"). A step already skipped/done/failed/executing
    is left untouched — this never resurrects or re-queues one."""
    plan = dict(plan)
    steps = [dict(s) for s in (plan.get("steps") or [])]
    wanted = set(step_keys) if step_keys else None
    for step in steps:
        if step.get("status") != "proposed":
            continue
        if wanted is not None and step.get("key") not in wanted:
            continue
        step["status"] = "approved"
    plan["steps"] = steps
    if plan.get("status") == "proposed":
        plan["status"] = "approved"
    return plan


async def execute_plan_steps(
    *, company_id: UUID, actor_user_id: Optional[UUID], plan: dict[str, Any],
    features: dict[str, Any], integrations: dict[str, bool],
) -> PlanExecutionResult:
    """Run every `approved` step in `plan["steps"]` sequentially. Skip-and-
    report: one step failing does not abort the batch. `create_employee`
    always runs first regardless of list order so its `employee_id` is
    available to every dependent step in the same execution."""
    from app.matcha.services.huume import onboarding_skill

    steps = list(plan.get("steps") or [])
    steps.sort(key=lambda s: 0 if s.get("key") == "create_employee" else 1)

    employee_id = plan.get("employee_id")
    summaries: list[str] = []

    for step in steps:
        if step.get("status") != "approved":
            continue
        reason = evaluate_plan_step(
            step, features=features, integrations=integrations, employee_id=employee_id,
        )
        if reason:
            step["status"] = "skipped"
            step["reason"] = reason
            summaries.append(f"Skipped {step.get('label', step.get('key'))}: {reason}")
            continue

        step["status"] = "executing"
        try:
            result = await onboarding_skill.execute_plan_step(
                key=step["key"], company_id=company_id, actor_user_id=actor_user_id,
                plan=plan, employee_id=employee_id,
            )
        except Exception:
            logger.exception("huume plan step %s failed for company %s", step.get("key"), company_id)
            step["status"] = "failed"
            step["error"] = "unexpected error"
            summaries.append(f"Failed {step.get('label', step.get('key'))}: unexpected error")
            continue

        if result.get("status") == "created":
            step["status"] = "done"
            step["record_id"] = result.get("record_id")
            summaries.append(result.get("message") or f"Completed {step.get('label', step.get('key'))}")
            if step["key"] == "create_employee" and result.get("record_id"):
                employee_id = result["record_id"]
                plan["employee_id"] = employee_id
        elif result.get("status") == "skipped":
            step["status"] = "skipped"
            step["reason"] = result.get("message") or "skipped"
            summaries.append(f"Skipped {step.get('label', step.get('key'))}: {step['reason']}")
        else:
            step["status"] = "failed"
            step["error"] = result.get("message") or "failed"
            summaries.append(f"Failed {step.get('label', step.get('key'))}: {step['error']}")

    plan["steps"] = steps
    if all(s.get("status") in ("done", "skipped", "failed") for s in steps):
        plan["status"] = "done"
    else:
        plan["status"] = "executing"
    return PlanExecutionResult(plan=plan, summaries=summaries)
