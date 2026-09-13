"""Pure regression coverage for error-autofix incident normalization."""
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE = Path(__file__).parents[1] / "error-autofix" / "_query.py"
SPEC = spec_from_file_location("autofix_query", MODULE)
assert SPEC and SPEC.loader
query = module_from_spec(SPEC)
SPEC.loader.exec_module(query)


def test_server_stable_key_remains_value_independent():
    first = query.stable_key(
        "http_error", "DataError", "bad argument: '12'",
        'File "/app/app/example.py", line 12, in create',
    )
    second = query.stable_key(
        "http_error", "DataError", "bad argument: '99'",
        'File "/app/app/example.py", line 99, in create',
    )
    assert first == second
    assert len(first) == 12


def test_client_key_ignores_build_hash_and_line_numbers():
    first = query.stable_client_key(
        "react_error", "Cannot read property 12345678", "at render (https://hey-matcha.com/assets/App-aBcDeFgH.js:12:3)",
        None, "https://hey-matcha.com/app/employees/123e4567-e89b-12d3-a456-426614174000", "at EmployeeDetail",
    )
    second = query.stable_client_key(
        "react_error", "Cannot read property 87654321", "at render (https://hey-matcha.com/assets/App-ZyXwVuTs.js:88:9)",
        None, "https://hey-matcha.com/app/employees/223e4567-e89b-12d3-a456-426614174000", "at EmployeeDetail",
    )
    assert first == second


def test_client_key_keeps_distinct_component_contexts_distinct():
    common = ("js_error", "boom", "at render (src/App.tsx:12:3)", None, "/app")
    assert query.stable_client_key(*common, "at EmployeeDetail") != query.stable_client_key(*common, "at IncidentDetail")


def test_client_filter_skips_transport_and_stale_chunk_noise():
    base = {"kind": "api_error", "message": "failure", "stack": "", "url": "https://hey-matcha.com/app", "api_status_code": 500}
    assert query._client_actionable(base)
    assert not query._client_actionable({**base, "api_status_code": 503})
    assert not query._client_actionable({**base, "message": "Failed to fetch dynamically imported module"})
    assert not query._client_actionable({**base, "url": "http://localhost:5174/app"})


def test_client_grouping_counts_days_and_suppresses_matching_server_api_error():
    now = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    row = {
        "id": "client-1", "kind": "react_error", "message": "boom", "stack": "at render (src/App.tsx:12:3)",
        "url": "https://hey-matcha.com/app", "api_endpoint": None, "api_status_code": None,
        "context": '{"request_id":"rid-1","component_stack":"at App"}', "occurred_at": now,
    }
    grouped, skipped, correlated = query._group_client([row, {**row, "id": "client-2", "occurred_at": tomorrow}], set())
    incident = next(iter(grouped.values()))
    assert skipped == 0 and correlated == 0
    assert incident["occurrences"] == 2 and incident["days_seen"] == 2

    api_row = {
        **row, "kind": "api_error", "api_endpoint": "/employees/123", "api_status_code": 500,
        "context": '{"request_id":"rid-2"}',
    }
    grouped, _, correlated = query._group_client([api_row], {("rid-2", query._path("/employees/123"))})
    assert grouped == {}
    assert correlated == 1


def test_incident_priority_is_newest_first():
    older_hot = {
        "last_seen": "2026-08-28T20:00:00Z",
        "level": "CRITICAL",
        "occurrences": 500,
    }
    new_single = {
        "last_seen": "2026-08-28T21:00:41Z",
        "level": "ERROR",
        "occurrences": 1,
    }

    incidents = sorted(
        [older_hot, new_single],
        key=query._incident_priority,
        reverse=True,
    )

    assert incidents == [new_single, older_hot]


def test_query_module_imports_without_the_database_driver():
    """stable_key/stable_client_key are exercised by host-side tests whose
    interpreter has no asyncpg; the driver is only imported inside main()."""
    import sys

    assert "asyncpg" not in getattr(query, "__dict__", {})
    source = MODULE.read_text()
    assert "\nimport asyncpg\n" not in source.split("async def main")[0]
    assert "import asyncpg" in source.split("async def main")[1]
    sys.modules.pop("asyncpg", None)


def test_client_request_id_outside_the_safe_alphabet_is_dropped():
    """A client incident's request_id is attacker-controlled (free-form context
    on an unauthenticated endpoint) and is later interpolated into a remote
    shell command. Only [A-Za-z0-9-]{4,64} may leave the collector."""
    now = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
    hostile = 'x"; touch /tmp/pwned; echo "'
    row = {
        "id": "client-9", "kind": "react_error", "message": "boom", "stack": "at render (src/App.tsx:12:3)",
        "url": "https://hey-matcha.com/app", "api_endpoint": None, "api_status_code": None,
        "context": '{"request_id":"%s"}' % hostile.replace('"', '\\"'), "occurred_at": now,
    }
    grouped, _, _ = query._group_client([row], set())
    incident = next(iter(grouped.values()))
    assert incident["request_id"] is None

    safe = {**row, "context": '{"request_id":"req-abc-123"}'}
    grouped, _, _ = query._group_client([safe], set())
    assert next(iter(grouped.values()))["request_id"] == "req-abc-123"

    assert query._safe_request_id("ab") is None
    assert query._safe_request_id("a" * 65) is None
    assert query._safe_request_id(None) is None
