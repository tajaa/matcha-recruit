"""Role-triggered auto-assign — `rule_matches_scheduled_role`, the pure
predicate `evaluate_scheduled_role_rules` (services/training_assignment.py)
runs per active `trigger='scheduled_role'` rule. No DB needed: the async
orchestrator is a thin DB-fetch wrapper around this function.
"""

from datetime import date, timedelta

from app.matcha.services.training_assignment import rule_matches_scheduled_role


def _rule(**overrides):
    rule = {
        "roles": None,
        "departments": None,
        "work_states": None,
        "applies_to": "all",
        "req_is_active": True,
    }
    rule.update(overrides)
    return rule


def _employee(**overrides):
    emp = {"work_state": "CA", "department": "Kitchen", "is_supervisor": False}
    emp.update(overrides)
    return emp


# ── role matching ────────────────────────────────────────────────────────────

def test_empty_roles_matches_any_role_including_none():
    rule = _rule(roles=None)
    assert rule_matches_scheduled_role(rule, _employee(), "Forklift Operator")
    assert rule_matches_scheduled_role(rule, _employee(), None)


def test_role_match_is_case_insensitive_and_trimmed():
    rule = _rule(roles=["Forklift Operator"])
    assert rule_matches_scheduled_role(rule, _employee(), " forklift operator ")
    assert rule_matches_scheduled_role(rule, _employee(), "FORKLIFT OPERATOR")


def test_nonmatching_role_is_excluded():
    rule = _rule(roles=["Forklift Operator"])
    assert not rule_matches_scheduled_role(rule, _employee(), "Cashier")


def test_nonempty_roles_vs_open_shift_role_does_not_match():
    # An open shift with no role set can't satisfy a rule scoped to a
    # specific role — there's nothing to match against.
    rule = _rule(roles=["Forklift Operator"])
    assert not rule_matches_scheduled_role(rule, _employee(), None)


# ── other filters ─────────────────────────────────────────────────────────────

def test_department_filter():
    rule = _rule(departments=["Kitchen"])
    assert rule_matches_scheduled_role(rule, _employee(department="Kitchen"), None)
    assert not rule_matches_scheduled_role(rule, _employee(department="Front of House"), None)


def test_work_state_filter():
    rule = _rule(work_states=["CA", "NY"])
    assert rule_matches_scheduled_role(rule, _employee(work_state="CA"), None)
    assert not rule_matches_scheduled_role(rule, _employee(work_state="TX"), None)


def test_applies_to_supervisor_only():
    rule = _rule(applies_to="supervisor")
    assert rule_matches_scheduled_role(rule, _employee(is_supervisor=True), None)
    assert not rule_matches_scheduled_role(rule, _employee(is_supervisor=False), None)


def test_applies_to_nonsupervisor_only():
    rule = _rule(applies_to="nonsupervisor")
    assert rule_matches_scheduled_role(rule, _employee(is_supervisor=False), None)
    assert not rule_matches_scheduled_role(rule, _employee(is_supervisor=True), None)


def test_inactive_requirement_never_matches():
    rule = _rule(req_is_active=False)
    assert not rule_matches_scheduled_role(rule, _employee(), None)


def test_all_filters_must_pass_simultaneously():
    rule = _rule(roles=["Line Cook"], departments=["Kitchen"], work_states=["CA"], applies_to="nonsupervisor")
    ok_employee = _employee(department="Kitchen", work_state="CA", is_supervisor=False)
    assert rule_matches_scheduled_role(rule, ok_employee, "Line Cook")

    wrong_state = _employee(department="Kitchen", work_state="TX", is_supervisor=False)
    assert not rule_matches_scheduled_role(rule, wrong_state, "Line Cook")
