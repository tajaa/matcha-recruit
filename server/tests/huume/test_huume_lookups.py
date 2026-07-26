"""Feature-gate tests for Huume's widened `lookup_context` topics — proves
the gate-before-SQL ordering without touching a database (`conn=None` would
raise on any query, so a passing test proves the SQL path was never reached).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_lookups.py -q
"""

import asyncio

from app.matcha.services.huume.onboarding_skill import _lookup_context_impl


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
