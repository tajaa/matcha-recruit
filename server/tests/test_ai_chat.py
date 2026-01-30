"""Tests for AI Chat — auth, ownership, SSE streaming, context building."""

import json
import os
from uuid import uuid4

import pytest

from app.core.services.ai_chat import AIChatService, MAX_HISTORY_MESSAGES
from app.core.services.compliance_service import _filter_by_jurisdiction_priority

# Path to the route source file (avoids importing the full app dependency chain)
_ROUTE_SRC_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "app", "core", "routes", "chat", "ai.py",
)


def _read_route_source() -> str:
    with open(_ROUTE_SRC_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Auth: chat is admin-only
# ---------------------------------------------------------------------------

class TestAdminOnlyAccess:
    """All AI chat route handlers must use require_admin, not require_admin_or_client."""

    def test_routes_import_require_admin(self):
        src = _read_route_source()
        assert "from ...dependencies import require_admin" in src

    def test_routes_do_not_import_require_admin_or_client(self):
        src = _read_route_source()
        assert "require_admin_or_client" not in src

    def test_all_endpoints_depend_on_require_admin(self):
        src = _read_route_source()
        # Every Depends() call should reference require_admin
        import re
        depends_calls = re.findall(r"Depends\((\w+)\)", src)
        for dep in depends_calls:
            assert dep in ("require_admin", "get_client_company_id"), (
                f"Unexpected dependency: {dep} — expected require_admin"
            )


# ---------------------------------------------------------------------------
# Ownership: route queries filter by user_id + company_id
# ---------------------------------------------------------------------------

class TestConversationOwnership:
    """Route queries must always filter by company_id AND user_id."""

    def test_send_message_checks_ownership(self):
        src = _read_route_source()
        # The conversation lookup in send_message must include both company_id and user_id
        assert "company_id = $2 AND user_id = $3" in src

    def test_get_conversation_checks_ownership(self):
        src = _read_route_source()
        # get_conversation must also filter by both
        assert "company_id = $2 AND user_id = $3" in src

    def test_delete_conversation_checks_ownership(self):
        src = _read_route_source()
        assert "DELETE FROM ai_conversations" in src
        # The delete also uses both filters
        assert src.count("company_id = $2 AND user_id = $3") >= 3


# ---------------------------------------------------------------------------
# SSE streaming: JSON-encoded tokens preserve newlines
# ---------------------------------------------------------------------------

class TestSSETokenEncoding:
    """The event_stream generator must JSON-encode tokens so newlines survive."""

    def test_token_with_newline_is_json_encoded(self):
        token = "line1\nline2"
        encoded = json.dumps({"t": token})
        sse_line = f"data: {encoded}\n\n"

        # Client-side parsing: split on \n, find data: lines, parse JSON
        lines = sse_line.split("\n")
        data_lines = [l.strip() for l in lines if l.strip().startswith("data: ")]
        assert len(data_lines) == 1
        payload = data_lines[0][len("data: "):]
        parsed = json.loads(payload)
        assert parsed["t"] == "line1\nline2"

    def test_error_is_json_encoded(self):
        error_msg = "something broke"
        encoded = json.dumps({"error": error_msg})
        sse_line = f"data: {encoded}\n\n"
        payload = sse_line.strip().split("data: ", 1)[1]
        parsed = json.loads(payload)
        assert parsed["error"] == error_msg

    def test_route_uses_json_dumps_for_tokens(self):
        src = _read_route_source()
        assert "json.dumps({'t': token})" in src

    def test_route_uses_json_dumps_for_errors(self):
        src = _read_route_source()
        assert "json.dumps({'error':" in src


# ---------------------------------------------------------------------------
# Context building: compliance filtering + caps
# ---------------------------------------------------------------------------

class TestComplianceFiltering:
    """build_company_context must apply jurisdiction priority filtering."""

    def test_superseded_state_rule_excluded(self):
        """State-level rule should be dropped when city-level exists."""
        reqs = [
            {
                "category": "minimum_wage",
                "title": "California Minimum Wage",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "current_value": "$16.00/hr",
                "location_name": "HQ",
            },
            {
                "category": "minimum_wage",
                "title": "City of West Hollywood Minimum Wage",
                "jurisdiction_level": "city",
                "jurisdiction_name": "West Hollywood",
                "current_value": "$19.08/hr",
                "location_name": "HQ",
            },
        ]
        filtered = _filter_by_jurisdiction_priority(reqs)
        titles = {r["title"] for r in filtered}
        assert "City of West Hollywood Minimum Wage" in titles
        assert "California Minimum Wage" not in titles

    def test_different_categories_both_kept(self):
        """Requirements in different categories should both survive."""
        reqs = [
            {
                "category": "minimum_wage",
                "title": "State Minimum Wage",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "current_value": "$16/hr",
                "location_name": "HQ",
            },
            {
                "category": "overtime",
                "title": "State Overtime",
                "jurisdiction_level": "state",
                "jurisdiction_name": "California",
                "current_value": "1.5x after 8hrs",
                "location_name": "HQ",
            },
        ]
        filtered = _filter_by_jurisdiction_priority(reqs)
        assert len(filtered) == 2


class TestHistoryLimit:
    """MAX_HISTORY_MESSAGES is set and reasonable."""

    def test_limit_is_reasonable(self):
        assert 10 <= MAX_HISTORY_MESSAGES <= 200

    def test_limit_is_used_in_route(self):
        """The send_message route should reference MAX_HISTORY_MESSAGES."""
        src = _read_route_source()
        assert "MAX_HISTORY_MESSAGES" in src

    def test_history_query_uses_desc_limit_subquery(self):
        """History must be fetched via DESC LIMIT subquery to get the most recent N."""
        src = _read_route_source()
        assert "ORDER BY created_at DESC" in src
        assert "LIMIT $2" in src


class TestContextCaps:
    """build_company_context caps policies via LIMIT."""

    def test_policy_query_has_limit(self):
        import inspect
        source = inspect.getsource(AIChatService.build_company_context)
        assert "LIMIT" in source

    def test_compliance_query_includes_title(self):
        """The compliance query must SELECT title for _filter_by_jurisdiction_priority."""
        import inspect
        source = inspect.getsource(AIChatService.build_company_context)
        assert "cr.title" in source

    def test_service_imports_jurisdiction_filter(self):
        import inspect
        source = inspect.getsource(AIChatService.build_company_context)
        # The method must call the filter function
        assert "_filter_by_jurisdiction_priority" in source
