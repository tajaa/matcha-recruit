from uuid import uuid4

from app.matcha.services.scheduling.schedule_eligibility_authorization import EligibilityManagerScope


def test_company_operations_can_manage_any_location():
    scope = EligibilityManagerScope(is_company_operations=True, managed_location_ids=frozenset())
    assert scope.permits(uuid4())


def test_location_manager_is_limited_to_their_locations():
    location_id = uuid4()
    scope = EligibilityManagerScope(is_company_operations=False, managed_location_ids=frozenset({location_id}))
    assert scope.permits(location_id)
    assert not scope.permits(uuid4())
    assert not scope.permits(None)
