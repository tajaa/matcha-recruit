from app.core.services.company_features import _introduced_dependency_violations


def test_dependency_diff_detects_new_missing_parent_on_existing_violation():
    previous = {"schedule_intelligence": ("employee_schedule",)}
    current = {
        "schedule_intelligence": ("matcha_ops", "employee_schedule"),
    }
    assert _introduced_dependency_violations(previous, current) == {
        "schedule_intelligence": ("matcha_ops", "employee_schedule"),
    }


def test_dependency_diff_ignores_unchanged_invalid_state():
    violations = {"inventory": ("matcha_ops",)}
    assert _introduced_dependency_violations(violations, violations) == {}


def test_dependency_diff_detects_new_dependent_feature():
    assert _introduced_dependency_violations(
        {}, {"inventory": ("matcha_ops",)}
    ) == {"inventory": ("matcha_ops",)}
