"""DB-free unit tests for `record_view.py`'s pure helpers and dispatch
tables. The builders themselves (`_model_*`/`_build_*_view`) need a
connection and are exercised via `TestShowRecord` in
`test_huume_lookups.py` only up to the gate/uuid-parse boundary — these
tests cover the normalization logic every builder leans on, which had zero
coverage before (the gate tests never reach it, by design).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_record_view.py -q
"""

from uuid import UUID

from app.matcha.services.huume.record_view import (
    _MODEL_BUILDERS,
    _VIEW_BUILDERS,
    RECORD_REQUIRED_FEATURE,
    _iso,
    _normalize_json_list,
    _parse_uuid,
)
from app.matcha.services.huume.tools import SHOW_RECORD_TYPES


class TestParseUuid:
    def test_valid_uuid_string(self):
        rid = "12345678-1234-5678-1234-567812345678"
        assert _parse_uuid(rid) == UUID(rid)

    def test_valid_uuid_object_passthrough(self):
        rid = UUID("12345678-1234-5678-1234-567812345678")
        assert _parse_uuid(rid) == rid

    def test_garbage_string_returns_none(self):
        assert _parse_uuid("not-even-a-uuid") is None

    def test_none_returns_none(self):
        assert _parse_uuid(None) is None

    def test_int_returns_none(self):
        assert _parse_uuid(12345) is None


class TestNormalizeJsonList:
    def test_list_passthrough(self):
        assert _normalize_json_list([{"a": 1}]) == [{"a": 1}]

    def test_json_string_of_list_is_parsed(self):
        assert _normalize_json_list('[{"name": "Jane"}]') == [{"name": "Jane"}]

    def test_json_string_of_object_returns_empty(self):
        # A malformed/legacy column holding an object, not a list — must not
        # blow up the caller, which always iterates the result as a list.
        assert _normalize_json_list('{"name": "Jane"}') == []

    def test_invalid_json_string_returns_empty(self):
        assert _normalize_json_list("not json") == []

    def test_none_returns_empty(self):
        assert _normalize_json_list(None) == []

    def test_int_returns_empty(self):
        assert _normalize_json_list(42) == []


class TestIso:
    def test_none_passthrough(self):
        assert _iso(None) is None

    def test_plain_value_without_isoformat_passthrough(self):
        assert _iso("already-a-string") == "already-a-string"

    def test_date_like_object_is_converted(self):
        class _FakeDate:
            def isoformat(self):
                return "2026-07-28"

        assert _iso(_FakeDate()) == "2026-07-28"


class TestDispatchTablesAgree:
    def test_all_four_registries_share_the_same_keys(self):
        assert (
            set(SHOW_RECORD_TYPES)
            == set(RECORD_REQUIRED_FEATURE)
            == set(_MODEL_BUILDERS)
            == set(_VIEW_BUILDERS)
        )
