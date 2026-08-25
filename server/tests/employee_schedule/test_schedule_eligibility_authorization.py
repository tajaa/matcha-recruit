from uuid import uuid4

from app.matcha.services.scheduling.schedule_eligibility_authorization import (
    EligibilityManagerScope,
    eligibility_case_decision_error,
)


def test_company_operations_can_manage_any_location():
    scope = EligibilityManagerScope(is_company_operations=True, managed_location_ids=frozenset())
    assert scope.permits(uuid4())


def test_location_manager_is_limited_to_their_locations():
    location_id = uuid4()
    scope = EligibilityManagerScope(is_company_operations=False, managed_location_ids=frozenset({location_id}))
    assert scope.permits(location_id)
    assert not scope.permits(uuid4())
    assert not scope.permits(None)


def test_warnings_and_automatic_cases_cannot_be_decided():
    assert eligibility_case_decision_error({
        "status": "warning_open", "blocking_reason_code": "credential_expiring",
    })
    assert eligibility_case_decision_error({
        "status": "removal_requested", "blocking_reason_code": "credential_expired_auto_unassigned",
    })
    assert eligibility_case_decision_error({
        "status": "removal_requested", "blocking_reason_code": "credential_expired",
    }) is None
