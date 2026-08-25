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
    assert "effective_from <= CURRENT_DATE" in source
    assert "ORDER BY effective_from DESC, confirmed_at DESC" in source
