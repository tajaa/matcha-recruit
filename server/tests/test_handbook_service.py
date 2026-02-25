import asyncio
import sys
import types
from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.core.models.handbook import HandbookGuidedDraftRequest, HandbookUpdateRequest
from app.core.services import handbook_service as handbook_service_module
from app.core.services import rate_limiter as rate_limiter_module
from app.core.services.handbook_service import (
    GuidedDraftRateLimitError,
    HandbookService,
    _build_core_sections,
    _build_template_sections,
    _build_state_sections,
    _coerce_jurisdiction_scope,
    _normalize_custom_sections,
    _sanitize_guided_profile_updates,
    _sanitize_guided_questions,
    _translate_handbook_db_error,
)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeConnection:
    def __init__(self, current_row: dict, scope_count: int = 1):
        self.current_row = current_row
        self.scope_count = scope_count
        self.executed: list[tuple[str, tuple]] = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        if "FROM handbooks" in query:
            return self.current_row
        return None

    async def fetchval(self, query, *args):
        if "COUNT(*) FROM handbook_scopes" in query:
            return self.scope_count
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if query.lstrip().upper().startswith("UPDATE"):
            return "UPDATE 1"
        return "INSERT 0 1"


class _FakeConnContext:
    def __init__(self, conn: _FakeConnection):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _patch_connection(monkeypatch, conn: _FakeConnection):
    monkeypatch.setattr(handbook_service_module, "get_connection", lambda: _FakeConnContext(conn))


def test_update_handbook_rejects_mode_scope_mismatch(monkeypatch):
    conn = _FakeConnection(
        current_row={
            "id": "hb-1",
            "company_id": "co-1",
            "mode": "multi_state",
            "source_type": "template",
            "active_version": 1,
        },
        scope_count=2,
    )
    _patch_connection(monkeypatch, conn)

    with pytest.raises(ValueError, match="Single-state handbooks must have exactly one scope"):
        asyncio.run(
            HandbookService.update_handbook(
                "hb-1",
                "co-1",
                HandbookUpdateRequest(mode="single_state"),
                "user-1",
            )
        )


def test_update_handbook_invalidates_cached_pdf_for_template_changes(monkeypatch):
    conn = _FakeConnection(
        current_row={
            "id": "hb-1",
            "company_id": "co-1",
            "mode": "single_state",
            "source_type": "template",
            "active_version": 1,
        },
        scope_count=1,
    )
    _patch_connection(monkeypatch, conn)

    async def _fake_get(*args, **kwargs):
        return SimpleNamespace(id="hb-1")

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get)

    asyncio.run(
        HandbookService.update_handbook(
            "hb-1",
            "co-1",
            HandbookUpdateRequest(title="Updated Handbook"),
            "user-1",
        )
    )

    update_queries = [query for query, _ in conn.executed if query.lstrip().upper().startswith("UPDATE HANDBOOKS SET")]
    assert update_queries, "Expected handbook update query to be executed"
    assert "file_url = NULL" in update_queries[0]
    assert "file_name = NULL" in update_queries[0]


def test_generate_handbook_pdf_bytes_escapes_html(monkeypatch):
    captured: dict[str, str] = {}

    class DummyHTML:
        def __init__(self, string):
            captured["html"] = string

        def write_pdf(self):
            return b"%PDF-test"

    monkeypatch.setitem(sys.modules, "weasyprint", types.SimpleNamespace(HTML=DummyHTML))

    fake_handbook = SimpleNamespace(
        title="<script>alert(1)</script>",
        active_version=3,
        status="draft",
        scopes=[SimpleNamespace(state="CA")],
        profile=SimpleNamespace(
            legal_name="<b>Acme</b>",
            dba=None,
            ceo_or_president='Jane "CEO" <Leader>',
            headcount=42,
        ),
        sections=[
            SimpleNamespace(
                title="Welcome <img src=x>",
                content="Line 1\n<script>bad()</script>",
            )
        ],
    )

    async def _fake_get(*args, **kwargs):
        return fake_handbook

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get)

    pdf_bytes, filename = asyncio.run(
        HandbookService.generate_handbook_pdf_bytes("hb-1", "co-1")
    )
    assert pdf_bytes == b"%PDF-test"
    assert filename.endswith("-v3.pdf")

    rendered_html = captured["html"]
    assert "<script>" not in rendered_html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in rendered_html
    assert "&lt;b&gt;Acme&lt;/b&gt;" in rendered_html


def test_normalize_custom_sections_produces_unique_safe_keys():
    sections = [
        SimpleNamespace(
            section_key="",
            title="My Custom Policy!!!",
            content="A",
            section_order=300,
            jurisdiction_scope={},
        ),
        SimpleNamespace(
            section_key="my custom policy",
            title="My Custom Policy",
            content="B",
            section_order=301,
            jurisdiction_scope={},
        ),
    ]

    normalized = _normalize_custom_sections(sections)  # type: ignore[arg-type]
    keys = [item["section_key"] for item in normalized]
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert all(len(key) <= 120 for key in keys)


def test_translate_handbook_db_error_handles_profile_schema_drift():
    err = Exception('column "tip_pooling" of relation "company_handbook_profiles" does not exist')
    translated = _translate_handbook_db_error(err)
    assert translated == "Handbook tables are out of date. Restart the API to apply schema updates."


def test_translate_handbook_db_error_handles_jsonb_dict_binding_error():
    err = Exception(
        "invalid input for query argument $6: {'mode': 'multi_state'} (expected str, got dict)"
    )
    translated = _translate_handbook_db_error(err)
    assert translated == "Failed to encode handbook section metadata. Please retry."


def test_coerce_jurisdiction_scope_parses_json_string():
    value = '{"mode":"multi_state","states":["CA","NV"]}'
    assert _coerce_jurisdiction_scope(value) == {
        "mode": "multi_state",
        "states": ["CA", "NV"],
    }


def test_coerce_jurisdiction_scope_rejects_non_dict_json():
    assert _coerce_jurisdiction_scope('["CA"]') == {}


def test_build_core_sections_includes_enforceable_language_and_operational_hooks():
    profile = {
        "legal_name": "Acme, Inc.",
        "dba": None,
        "ceo_or_president": "Jordan Finch",
        "headcount": 120,
        "remote_workers": True,
        "minors": False,
        "tipped_employees": False,
        "union_employees": False,
        "federal_contracts": False,
        "group_health_insurance": True,
        "background_checks": True,
        "hourly_employees": True,
        "salaried_employees": True,
        "commissioned_employees": False,
        "tip_pooling": False,
    }

    sections = _build_core_sections(profile, "single_state", ["CA"])
    by_key = {section["section_key"]: section for section in sections}

    assert "at-will" in by_key["employment_relationship"]["content"].lower()
    assert "[HARASSMENT_REPORTING_HOTLINE]" in by_key["equal_opportunity"]["content"]
    assert "[WORKWEEK_START_DAY]" in by_key["hours_and_pay"]["content"]
    assert "Excused absences include approved protected leave" in by_key["attendance_and_remote"]["content"]
    assert "employer's legal responsibility" in by_key["custom_policy_responsibility"]["content"].lower()
    assert "Safe-harbor statement" in by_key["acknowledgement"]["content"]


def test_build_state_sections_injects_state_requirements_when_available():
    profile = {"tip_pooling": True}
    state_requirement_map = {
        "CA": [
            {
                "state": "CA",
                "category": "minimum_wage",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "title": "California Minimum Wage",
                "description": "Statewide minimum wage baseline.",
                "current_value": "$16.00/hr",
                "effective_date": date(2026, 1, 1),
                "source_url": "https://dir.ca.gov/dlse/minimum_wage.htm",
                "source_name": "CA Labor Commissioner",
                "rate_type": "general",
            },
            {
                "state": "CA",
                "category": "other",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "title": "Lactation Accommodation",
                "description": "Employers must provide break time and private space for lactation.",
                "current_value": "Break time and private space required",
                "effective_date": date(2025, 1, 1),
                "source_url": "https://www.dir.ca.gov/dlse/Lactation_Accommodation.htm",
                "source_name": "CA DIR",
                "rate_type": None,
            },
        ]
    }

    sections = _build_state_sections(["CA"], profile, state_requirement_map)
    assert len(sections) == 1
    content = sections[0]["content"]

    assert "$16.00/hr" in content
    assert "Lactation Accommodation" in content
    assert "Authoritative Sources Referenced" in content
    assert "https://dir.ca.gov/dlse/minimum_wage.htm" in content
    assert "[HR_CONTACT_EMAIL]" in content


def test_build_state_sections_includes_repository_fallback_when_missing():
    sections = _build_state_sections(["NY"], {"tip_pooling": False}, {"NY": []})
    assert len(sections) == 1
    content = sections[0]["content"]
    assert "No verified statutory entries were found in the compliance repository" in content


def test_build_state_sections_mentions_selected_city_scope():
    sections = _build_state_sections(
        ["CA"],
        {"tip_pooling": False},
        {"CA": []},
        selected_cities_by_state={"CA": ["Los Angeles"]},
    )
    assert len(sections) == 1
    content = sections[0]["content"]
    assert "Covered city/local scopes in this state: Los Angeles." in content


def test_build_template_sections_requires_mandatory_topics_for_hospitality():
    profile = {
        "legal_name": "Acme Cafe LLC",
        "dba": None,
        "ceo_or_president": "Owner Name",
        "headcount": 24,
        "remote_workers": False,
        "minors": False,
        "tipped_employees": True,
        "union_employees": False,
        "federal_contracts": False,
        "group_health_insurance": False,
        "background_checks": True,
        "hourly_employees": True,
        "salaried_employees": False,
        "commissioned_employees": False,
        "tip_pooling": True,
    }
    state_requirement_map = {
        "CA": [
            {
                "state": "CA",
                "category": "minimum_wage",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "title": "California Minimum Wage",
                "description": "Statewide minimum wage baseline.",
                "current_value": "$16.00/hr",
                "effective_date": date(2026, 1, 1),
                "source_url": "https://example.com/ca-minimum-wage",
                "source_name": "CA Source",
                "rate_type": "general",
            }
        ]
    }

    with pytest.raises(ValueError, match="Missing required state boilerplate coverage"):
        _build_template_sections(
            mode="single_state",
            scopes=[{"state": "CA", "city": "Los Angeles", "zipcode": "90012", "location_id": None}],
            profile=profile,
            custom_sections=[],
            industry_key="hospitality",
            state_requirement_map=state_requirement_map,
        )


def _guided_profile() -> dict:
    return {
        "legal_name": "Matcha Tech Inc.",
        "dba": None,
        "ceo_or_president": "Ash Finch",
        "headcount": 140,
        "remote_workers": False,
        "minors": False,
        "tipped_employees": False,
        "union_employees": False,
        "federal_contracts": False,
        "group_health_insurance": True,
        "background_checks": True,
        "hourly_employees": True,
        "salaried_employees": True,
        "commissioned_employees": False,
        "tip_pooling": False,
    }


class _GuidedDraftConnection:
    async def fetchrow(self, query, *args):
        if "SELECT name, industry FROM companies" in query:
            return {"name": "Matcha Tech", "industry": "Software"}
        return None


def test_generate_guided_draft_returns_industry_baseline_when_ai_missing(monkeypatch):
    _patch_connection(monkeypatch, _GuidedDraftConnection())

    async def _fake_ai_payload(**kwargs):
        return None

    monkeypatch.setattr(
        HandbookService,
        "_generate_guided_draft_ai_payload",
        staticmethod(_fake_ai_payload),
    )

    response = asyncio.run(
        HandbookService.generate_guided_draft(
            "co-1",
            HandbookGuidedDraftRequest(
                title="Employee Handbook 2026",
                mode="single_state",
                scopes=[{"state": "CA", "city": None, "zipcode": None, "location_id": None}],
                profile=_guided_profile(),
                industry="technology",
                answers={},
                existing_custom_sections=[],
            ),
        )
    )

    assert response.industry == "technology"
    assert response.clarification_needed is True
    assert len(response.questions) > 0
    assert any(question.id == "hr_contact_email" for question in response.questions)
    assert any(section.title == "Remote Work Location and Payroll Compliance" for section in response.suggested_sections)
    assert response.profile_updates.get("remote_workers") is True


def test_generate_guided_draft_merges_ai_payload_and_skips_existing_titles(monkeypatch):
    _patch_connection(monkeypatch, _GuidedDraftConnection())

    async def _fake_ai_payload(**kwargs):
        return {
            "summary": "Technology policy pack generated.",
            "questions": [],
            "profile_updates": {"remote_workers": False, "nonexistent_key": True},
            "suggested_sections": [
                {
                    "section_key": "custom_incident_escalation",
                    "title": "Custom Incident Escalation Matrix",
                    "content": "Escalate privacy, security, and retaliation concerns to HR within one business day.",
                    "section_order": 340,
                }
            ],
        }

    monkeypatch.setattr(
        HandbookService,
        "_generate_guided_draft_ai_payload",
        staticmethod(_fake_ai_payload),
    )

    answers = {
        "hr_contact_email": "hr@matcha-tech.com",
        "leave_admin_email": "leave@matcha-tech.com",
        "harassment_hotline": "1-800-555-0123",
        "workweek_definition": "Sunday 12:00 AM PT",
        "attendance_notice_window": "24 hours",
        "remote_work_jurisdiction_tracking": "Notify HR five business days before any state change.",
        "security_incident_reporting_window": "Immediate report to security@matcha-tech.com",
    }

    response = asyncio.run(
        HandbookService.generate_guided_draft(
            "co-1",
            HandbookGuidedDraftRequest(
                title="Employee Handbook 2026",
                mode="single_state",
                scopes=[{"state": "CA", "city": None, "zipcode": None, "location_id": None}],
                profile=_guided_profile(),
                industry="technology",
                answers=answers,
                existing_custom_sections=[
                    {
                        "section_key": "existing_remote_work",
                        "title": "Remote Work Location and Payroll Compliance",
                        "content": "Existing company policy text.",
                        "section_order": 300,
                        "section_type": "custom",
                        "jurisdiction_scope": {},
                    }
                ],
            ),
        )
    )

    assert response.summary == "Technology policy pack generated."
    assert response.clarification_needed is False
    assert response.questions == []
    assert "salaried_employees" not in response.profile_updates
    assert response.profile_updates.get("remote_workers") is False
    section_titles = {section.title for section in response.suggested_sections}
    assert "Remote Work Location and Payroll Compliance" not in section_titles
    assert "Custom Incident Escalation Matrix" in section_titles


def test_sanitize_guided_profile_updates_parses_boolean_strings():
    updates = _sanitize_guided_profile_updates(
        {
            "remote_workers": "false",
            "tip_pooling": "1",
            "hourly_employees": "TRUE",
            "union_employees": "no",
            "minors": "maybe",
        },
        {"remote_workers": False},
    )
    assert updates["remote_workers"] is False
    assert updates["tip_pooling"] is True
    assert updates["hourly_employees"] is True
    assert updates["union_employees"] is False
    assert "minors" not in updates


def test_sanitize_guided_questions_parses_required_string_values():
    questions = _sanitize_guided_questions(
        [
            {
                "id": "optional_q",
                "question": "Should this question be optional?",
                "required": "false",
            },
            {
                "id": "required_q",
                "question": "Should this question be required?",
                "required": "true",
            },
        ]
    )
    assert questions[0]["required"] is False
    assert questions[1]["required"] is True


def test_generate_guided_draft_ai_payload_raises_rate_limit_error(monkeypatch):
    settings = SimpleNamespace(
        use_vertex=True,
        gemini_api_key=None,
        vertex_project="demo-project",
        vertex_location="us-central1",
        analysis_model="gemini-3-flash-preview",
    )
    monkeypatch.setattr(handbook_service_module, "get_settings", lambda: settings)

    fake_google = types.ModuleType("google")
    fake_google.genai = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "google", fake_google)

    class _LimitOnlyRateLimiter:
        async def check_limit(self, service_name, endpoint=None):
            raise rate_limiter_module.RateLimitExceeded(
                "Gemini API hourly limit exceeded (100/100)",
                limit_type="hourly",
                current_count=100,
                limit=100,
            )

    monkeypatch.setattr(
        rate_limiter_module,
        "get_rate_limiter",
        lambda: _LimitOnlyRateLimiter(),
    )

    with pytest.raises(GuidedDraftRateLimitError, match="Guided draft rate limit exceeded"):
        asyncio.run(
            HandbookService._generate_guided_draft_ai_payload(
                company_name="Matcha Tech",
                industry_key="technology",
                industry_label="Technology / Professional Services",
                title="Employee Handbook",
                mode="single_state",
                scopes=[{"state": "CA"}],
                normalized_profile={"remote_workers": True},
                answers={},
                baseline_questions=[],
                baseline_sections=[],
            )
        )


class _HandbookDistributionConn:
    def __init__(self, recipient_rows=None):
        self.recipient_rows = recipient_rows or []

    def transaction(self):
        return _FakeTransaction()

    async def fetch(self, query, *args):
        if "FROM employees e" in query:
            return self.recipient_rows
        return []


def test_distribute_to_employees_rejects_empty_specific_selection(monkeypatch):
    async def _fake_get_handbook(*args, **kwargs):
        return SimpleNamespace(status="active", title="Employee Handbook", active_version=2)

    async def _fake_ensure_pdf(*args, **kwargs):
        return "https://example.com/handbook.pdf", "handbook.pdf", 2

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get_handbook)
    monkeypatch.setattr(HandbookService, "_ensure_handbook_pdf", _fake_ensure_pdf)

    conn = _HandbookDistributionConn()
    monkeypatch.setattr(handbook_service_module, "get_connection", lambda: _FakeConnContext(conn))

    with pytest.raises(ValueError, match="Select at least one employee"):
        asyncio.run(
            HandbookService.distribute_to_employees(
                handbook_id="11111111-1111-1111-1111-111111111111",
                company_id="22222222-2222-2222-2222-222222222222",
                distributed_by="33333333-3333-3333-3333-333333333333",
                employee_ids=[],
            )
        )


def test_list_distribution_recipients_includes_assignment_status(monkeypatch):
    async def _fake_get_handbook(*args, **kwargs):
        return SimpleNamespace(status="active", active_version=4)

    monkeypatch.setattr(HandbookService, "get_handbook_by_id", _fake_get_handbook)

    rows = [
        {
            "employee_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "name": "Jane Doe",
            "email": "jane@example.com",
            "invitation_status": "pending",
            "already_assigned": True,
        },
        {
            "employee_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "name": "John Smith",
            "email": "john@example.com",
            "invitation_status": None,
            "already_assigned": False,
        },
    ]
    conn = _HandbookDistributionConn(recipient_rows=rows)
    monkeypatch.setattr(handbook_service_module, "get_connection", lambda: _FakeConnContext(conn))

    result = asyncio.run(
        HandbookService.list_distribution_recipients(
            handbook_id="11111111-1111-1111-1111-111111111111",
            company_id="22222222-2222-2222-2222-222222222222",
        )
    )

    assert result is not None
    assert len(result) == 2
    assert result[0].employee_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert result[0].already_assigned is True
    assert result[1].employee_id == UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert result[1].already_assigned is False
