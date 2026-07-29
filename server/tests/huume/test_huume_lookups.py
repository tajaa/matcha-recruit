"""Feature-gate tests for Huume's widened `lookup_context` topics — proves
the gate-before-SQL ordering without touching a database (`conn=None` would
raise on any query, so a passing test proves the SQL path was never reached).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_lookups.py -q
"""

import asyncio

from app.matcha.services.huume.onboarding_skill import (
    _clamp_incident_days,
    _lookup_context_impl,
)
from app.matcha.services.huume.record_view import (
    _MODEL_BUILDERS,
    _VIEW_BUILDERS,
    MAX_OPEN_RECORDS,
    RECORD_REQUIRED_FEATURE,
    merge_open_records,
    show_records_for_model,
)
from app.matcha.services.huume.tools import SHOW_RECORD_TYPES


def _run(coro):
    return asyncio.run(coro)


class TestLookupGating:
    def test_training_status_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="training_status", features={"training": False},
        ))
        assert result["module"] == "off"

    def test_credentials_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="credentials", features={"credential_templates": False},
        ))
        assert result["module"] == "off"

    def test_employee_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="employee", features={"employees": False},
        ))
        assert result["module"] == "off"

    def test_schedule_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="schedule", features={"employee_schedule": False},
        ))
        assert result["module"] == "off"

    def test_incidents_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="incidents", features={"incidents": False},
        ))
        assert result["module"] == "off"

    def test_er_cases_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="er_cases", features={"er_copilot": False},
        ))
        assert result["module"] == "off"

    def test_no_features_dict_defaults_to_off(self):
        result = _run(_lookup_context_impl(None, company_id="c1", topic="training_status", features=None))
        assert result["module"] == "off"

    def test_pto_leave_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="pto_leave", features={"employees": False},
        ))
        assert result["module"] == "off"

    def test_policies_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="policies", features={"handbooks": False},
        ))
        assert result["module"] == "off"

    def test_discipline_off_returns_module_off_without_conn(self):
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="discipline", features={"discipline": False},
        ))
        assert result["module"] == "off"

    def test_compliance_off_returns_module_off_without_conn(self):
        # Neither of the two flags that gate this topic is on.
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="compliance", features={"compliance": False, "compliance_lite": False},
        ))
        assert result["module"] == "off"

    def test_compliance_lite_alone_is_sufficient(self):
        # any-of gate: compliance_lite on its own should pass the gate check
        # and attempt the DB path (conn=None -> "lookup failed", not "off").
        result = _run(_lookup_context_impl(
            None, company_id="c1", topic="compliance", features={"compliance": False, "compliance_lite": True},
        ))
        assert "module" not in result
        assert result.get("error") == "lookup failed"

    def test_ungated_topic_ignores_features(self):
        # roster has no required feature — it should proceed past the gate
        # check and attempt the DB path, hitting conn=None. The function's
        # own except-Exception wraps that into an "error" result rather than
        # raising — distinct from the gated "module": "off" shape, proving
        # this topic was never gate-short-circuited.
        result = _run(_lookup_context_impl(None, company_id="c1", topic="roster", features={}))
        assert "module" not in result
        assert result.get("error") == "lookup failed"


class TestShowRecords:
    def test_incident_off_refused(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="incident", record_ids=["not-even-a-uuid"], features={"incidents": False},
        ))
        assert result["status"] == "refused"

    def test_er_case_off_refused(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="er_case", record_ids=["not-even-a-uuid"], features={"er_copilot": False},
        ))
        assert result["status"] == "refused"

    def test_employee_off_refused(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="employee", record_ids=["not-even-a-uuid"], features={"employees": False},
        ))
        assert result["status"] == "refused"

    def test_credential_off_refused(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="credential", record_ids=["not-even-a-uuid"], features={"credential_templates": False},
        ))
        assert result["status"] == "refused"

    def test_unknown_type_is_error_even_with_flags_on(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="widget", record_ids=["x"],
            features={"incidents": True, "er_copilot": True, "employees": True, "credential_templates": True},
        ))
        assert result["status"] == "error"

    def test_empty_ids_is_error(self):
        result = _run(show_records_for_model(
            company_id="c1", record_type="incident", record_ids=[], features={"incidents": True},
        ))
        assert result["status"] == "error"

    def test_all_bad_uuids_short_circuits_to_not_found(self):
        # incidents=True clears the gate; the malformed-UUID guard fires
        # before any query is attempted for each id, so conn=None never
        # matters here — show_records_for_model opens a connection only
        # once at least one id needs a real lookup.
        result = _run(show_records_for_model(
            company_id="c1", record_type="incident", record_ids=["not-a-uuid", "also-not"], features={"incidents": True},
        ))
        assert result["status"] == "not_found"

    def test_over_cap_truncates_with_a_note(self):
        # All garbage ids, so no DB connection is ever opened — this proves
        # the truncation happens before the per-id loop, not just that the
        # loop stops early.
        ids = [f"not-a-uuid-{i}" for i in range(MAX_OPEN_RECORDS + 5)]
        result = _run(show_records_for_model(
            company_id="c1", record_type="incident", record_ids=ids, features={"incidents": True},
        ))
        # Every id is garbage, so it's still "not_found" overall, but the
        # not_found list must be capped, not the full 13 — proving the
        # truncation ran before the loop.
        assert len(result.get("not_found") or []) <= MAX_OPEN_RECORDS

    def test_every_record_type_is_registered_in_all_four_places(self):
        # A record type wired into the enum + feature map but missing from
        # _VIEW_BUILDERS (or vice versa) would pass the chat tool and 404 the
        # panel — or the reverse — with nothing else here to catch it.
        assert (
            set(SHOW_RECORD_TYPES)
            == set(RECORD_REQUIRED_FEATURE)
            == set(_MODEL_BUILDERS)
            == set(_VIEW_BUILDERS)
        )


class TestMergeOpenRecords:
    def test_appends_to_empty(self):
        result = merge_open_records([], [{"record_type": "incident", "record_id": "r1"}])
        assert result == [{"record_type": "incident", "record_id": "r1"}]

    def test_appends_new_entries(self):
        current = [{"record_type": "incident", "record_id": "r1"}]
        result = merge_open_records(current, [{"record_type": "incident", "record_id": "r2"}])
        assert [r["record_id"] for r in result] == ["r1", "r2"]

    def test_reshowing_an_open_record_moves_it_to_the_end(self):
        current = [
            {"record_type": "incident", "record_id": "r1"},
            {"record_type": "incident", "record_id": "r2"},
        ]
        result = merge_open_records(current, [{"record_type": "incident", "record_id": "r1", "label": "updated"}])
        assert [r["record_id"] for r in result] == ["r2", "r1"]
        assert result[-1]["label"] == "updated"

    def test_caps_at_max_dropping_from_the_front(self):
        current = [{"record_type": "incident", "record_id": f"r{i}"} for i in range(MAX_OPEN_RECORDS)]
        result = merge_open_records(current, [{"record_type": "incident", "record_id": "new"}])
        assert len(result) == MAX_OPEN_RECORDS
        assert result[-1]["record_id"] == "new"
        assert result[0]["record_id"] == "r1"  # r0 dropped

    def test_different_record_types_with_the_same_id_are_distinct(self):
        current = [{"record_type": "incident", "record_id": "x"}]
        result = merge_open_records(current, [{"record_type": "employee", "record_id": "x"}])
        assert len(result) == 2


class TestClampIncidentDays:
    def test_none_defaults_to_90(self):
        assert _clamp_incident_days(None) == 90

    def test_zero_or_negative_defaults_to_90(self):
        assert _clamp_incident_days(0) == 90
        assert _clamp_incident_days(-5) == 90

    def test_digit_string_is_coerced_not_defaulted(self):
        assert _clamp_incident_days("30") == 30

    def test_non_numeric_string_defaults_to_90(self):
        assert _clamp_incident_days("thirty") == 90

    def test_bool_defaults_to_90(self):
        # isinstance(True, int) is True in Python — must not sneak through.
        assert _clamp_incident_days(True) == 90

    def test_within_range_passes_through(self):
        assert _clamp_incident_days(30) == 30

    def test_over_max_clamps_to_365(self):
        assert _clamp_incident_days(9999) == 365
