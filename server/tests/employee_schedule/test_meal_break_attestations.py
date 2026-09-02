"""Contract checks for the employee-profile meal-break waiver surface."""

from pathlib import Path

from app.matcha.models.scheduling.employee_schedule import MealWaiverAttestationResponse


def test_no_attestation_has_an_explicit_safe_response_shape():
    response = MealWaiverAttestationResponse(employee_id="0f9dc4aa-03fc-4dae-bf04-6c9cde1b6f4b", on_file=False, attested=False)
    assert response.on_file is False
    assert response.attested is False
    assert response.effective_from is None


def test_waiver_endpoint_scopes_to_company_and_returns_only_effective_attestation():
    route = Path(__file__).parents[2] / "app/matcha/routes/employee_schedule/attestations.py"
    source = route.read_text()
    assert '@router.get("/employees/{employee_id}/meal-break-waiver"' in source
    assert "await assert_employee_in_company(conn, company_id, employee_id)" in source
    assert "effective_from <= COALESCE((NOW() AT TIME ZONE l.timezone)::date, CURRENT_DATE)" in source
    assert "FROM employee_compliance_attestations a" in source
    assert "WHERE a.company_id = $1 AND a.employee_id = $2" in source
    assert "ORDER BY a.effective_from DESC, a.confirmed_at DESC" in source
    assert "s.starts_at >= NOW()" in source


def test_guidance_evaluates_waivers_on_the_location_calendar_day():
    guidance = Path(__file__).parents[2] / "app/matcha/services/scheduling/schedule_guidance.py"
    source = guidance.read_text()
    assert "starts_at.astimezone(location_timezone).date()" in source
    assert "starts_at.astimezone(effective_timezone).date()" in source
