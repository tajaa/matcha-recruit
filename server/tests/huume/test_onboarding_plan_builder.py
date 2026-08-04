"""Pure-function tests for Huume's onboarding plan builder (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_onboarding_plan_builder.py -q
"""

from uuid import uuid4

from app.matcha.services.huume.onboarding_skill import (
    build_onboarding_plan, PLAN_STEP_ORDER, _derive_work_state, _normalize_employment_type,
)

FULL_FEATURES = {
    "employees": True, "credential_templates": True, "training": True,
    "employee_schedule": True, "benefits_admin": True,
}
NO_FEATURES = {}


def _offer(**overrides):
    base = {
        "id": uuid4(), "candidate_name": "Jane Doe",
        "candidate_email": "jane.doe@example.com", "position_title": "RN",
        "start_date": None, "location": "CA",
    }
    base.update(overrides)
    return base


class TestBuildOnboardingPlan:
    def test_step_count_matches_registry(self):
        plan = build_onboarding_plan(offer=_offer(), features=FULL_FEATURES, integrations={"google_workspace": True, "slack": True})
        assert len(plan["steps"]) == len(PLAN_STEP_ORDER)
        assert {s["key"] for s in plan["steps"]} == {k for k, _ in PLAN_STEP_ORDER}

    def test_create_employee_never_skipped_for_missing_flag(self):
        # create_employee itself only needs `employees`; with NO_FEATURES it's
        # correctly skipped (employees off), but it must not be skipped for the
        # bogus "waiting on itself" reason.
        plan = build_onboarding_plan(offer=_offer(), features=NO_FEATURES, integrations={})
        create_step = next(s for s in plan["steps"] if s["key"] == "create_employee")
        assert create_step["status"] == "skipped"
        assert create_step["reason"] != "waiting on create_employee to run first"

    def test_full_features_only_skips_unconnected_integrations(self):
        plan = build_onboarding_plan(offer=_offer(), features=FULL_FEATURES, integrations={})
        by_key = {s["key"]: s for s in plan["steps"]}
        assert by_key["create_employee"]["status"] == "proposed"
        assert by_key["portal_invitation"]["status"] == "proposed"
        assert by_key["credential_requirements"]["status"] == "proposed"
        assert by_key["training_assignment"]["status"] == "proposed"
        assert by_key["schedule_note"]["status"] == "proposed"
        assert by_key["benefits_note"]["status"] == "proposed"
        assert by_key["jurisdiction_packet_note"]["status"] == "proposed"
        # No connected integrations → both provisioning steps skipped.
        assert by_key["google_workspace"]["status"] == "skipped"
        assert by_key["slack"]["status"] == "skipped"

    def test_no_features_skips_everything_gated(self):
        plan = build_onboarding_plan(offer=_offer(), features=NO_FEATURES, integrations={})
        by_key = {s["key"]: s for s in plan["steps"]}
        assert by_key["credential_requirements"]["status"] == "skipped"
        assert by_key["training_assignment"]["status"] == "skipped"
        assert by_key["schedule_note"]["status"] == "skipped"
        assert by_key["benefits_note"]["status"] == "skipped"
        # Always-available read-only note is never gated.
        assert by_key["jurisdiction_packet_note"]["status"] == "proposed"

    def test_connected_integrations_propose_provisioning_steps(self):
        plan = build_onboarding_plan(
            offer=_offer(), features=FULL_FEATURES, integrations={"google_workspace": True, "slack": True},
        )
        by_key = {s["key"]: s for s in plan["steps"]}
        assert by_key["google_workspace"]["status"] == "proposed"
        assert by_key["slack"]["status"] == "proposed"

    def test_employee_fields_derived_from_offer(self):
        plan = build_onboarding_plan(offer=_offer(), features=FULL_FEATURES, integrations={})
        assert plan["employee"]["first_name"] == "Jane"
        assert plan["employee"]["last_name"] == "Doe"
        assert plan["employee"]["email"] == "jane.doe@example.com"
        assert plan["employee"]["position_title"] == "RN"

    def test_plan_starts_proposed_with_no_employee_id(self):
        plan = build_onboarding_plan(offer=_offer(), features=FULL_FEATURES, integrations={})
        assert plan["status"] == "proposed"
        assert plan["employee_id"] is None

    def test_single_name_candidate_handled(self):
        plan = build_onboarding_plan(offer=_offer(candidate_name="Cher"), features=FULL_FEATURES, integrations={})
        assert plan["employee"]["first_name"] == "Cher"
        assert plan["employee"]["last_name"] is None


class TestNormalizeEmploymentType:
    def test_offer_default_maps_to_full_time(self):
        assert _normalize_employment_type("Full-Time Exempt") == "full_time"

    def test_common_variants(self):
        assert _normalize_employment_type("Full-time") == "full_time"
        assert _normalize_employment_type("at_will") == "full_time"
        assert _normalize_employment_type("Salaried") == "full_time"
        assert _normalize_employment_type("Part-Time Hourly") == "part_time"
        assert _normalize_employment_type("Contractor") == "contractor"
        assert _normalize_employment_type("1099") == "contractor"
        assert _normalize_employment_type("Internship") == "intern"

    def test_unmappable_returns_none(self):
        assert _normalize_employment_type("Hybrid") is None
        assert _normalize_employment_type("") is None
        assert _normalize_employment_type(None) is None


class TestDeriveWorkState:
    def test_bare_code(self):
        assert _derive_work_state("CA") == "CA"
        assert _derive_work_state("ca") == "CA"

    def test_city_comma_state(self):
        assert _derive_work_state("Los Angeles, CA") == "CA"
        assert _derive_work_state("Aliso Viejo, CA") == "CA"

    def test_full_state_name(self):
        assert _derive_work_state("California") == "CA"

    def test_unmappable(self):
        assert _derive_work_state("Remote in the US") is None
        assert _derive_work_state("") is None
        assert _derive_work_state(None) is None
