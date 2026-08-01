"""DB-free unit tests for `record_view.py`'s pure helpers and dispatch
tables. The builders themselves (`_model_*`/`_build_*_view`) need a
connection and are exercised via `TestShowRecord` in
`test_huume_lookups.py` only up to the gate/uuid-parse boundary — these
tests cover the normalization logic every builder leans on, which had zero
coverage before (the gate tests never reach it, by design).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_record_view.py -q
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.matcha.services.huume.record_view import (
    _MODEL_BUILDERS,
    _VIEW_BUILDERS,
    RECORD_REQUIRED_FEATURE,
    _build_ems_event_view,
    _iso,
    _model_ems_events_batch,
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


class _FakeFetchConn:
    def __init__(self, *, fetch_rows=(), fetchrow_result=None, fetchval_result=None):
        self._fetch_rows = list(fetch_rows)
        self._fetchrow_result = fetchrow_result
        self._fetchval_result = fetchval_result

    async def fetch(self, query, *args):
        return self._fetch_rows

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def fetchval(self, query, *args):
        return self._fetchval_result


class TestModelEmsEventsBatch:
    @pytest.mark.asyncio
    async def test_includes_truncated_narrative(self):
        rid = uuid4()
        row = {
            "id": rid, "title": "Autoclave failure", "category": "equipment",
            "severity_hint": "high", "status": "logged", "incident_recommendation": True,
            "suggested_incident_type": "property", "suggested_severity": "high",
            "narrative": "x" * 600, "doc": None, "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
        }
        conn = _FakeFetchConn(fetch_rows=[row])
        out = await _model_ems_events_batch(conn, uuid4(), [rid])
        entry = out[rid]
        assert entry["label"] == "Autoclave failure"
        assert len(entry["narrative"]) == 500
        assert entry["record_id"] == str(rid)

    @pytest.mark.asyncio
    async def test_empty_ids_short_circuits(self):
        conn = _FakeFetchConn()
        out = await _model_ems_events_batch(conn, uuid4(), [])
        assert out == {}

    @pytest.mark.asyncio
    async def test_includes_urgency_and_protocol_qualifies(self):
        # An admin asking Huume about events must be able to see which ones
        # were OSHA/severe-flagged, not just incident_recommendation.
        rid = uuid4()
        row = {
            "id": rid, "title": "Fall in stockroom", "category": "safety",
            "severity_hint": "high", "status": "logged", "incident_recommendation": True,
            "suggested_incident_type": "safety", "suggested_severity": "critical",
            "urgency": "osha", "protocol_qualifies": True,
            "narrative": "Marcus was hospitalized.", "doc": None,
            "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
        }
        conn = _FakeFetchConn(fetch_rows=[row])
        out = await _model_ems_events_batch(conn, uuid4(), [rid])
        assert out[rid]["urgency"] == "osha"
        assert out[rid]["protocol_qualifies"] is True


class TestBuildEmsEventView:
    @pytest.mark.asyncio
    async def test_view_shape_and_link(self):
        rid = uuid4()
        row = {
            "id": rid, "company_id": uuid4(), "channel_id": uuid4(), "channel_name": "safety",
            "message_id": uuid4(), "reporter_user_id": uuid4(), "reporter_name": "Jane Doe",
            "title": "Autoclave failure", "category": "equipment", "severity_hint": "high",
            "doc": {}, "narrative": "It stopped mid-cycle.", "incident_recommendation": True,
            "incident_reasoning": "Repeat failure pattern.", "suggested_incident_type": "property",
            "suggested_severity": "high", "status": "logged", "incident_id": None,
            "awaiting_reply": False, "clarification_rounds": 0,
            "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc), "updated_at": None,
        }
        conn = _FakeFetchConn(fetchrow_result=row)
        view = await _build_ems_event_view(conn, uuid4(), rid)
        assert view["record_type"] == "ems_event"
        assert view["link"] == f"/work/events/{rid}"
        assert view["title"] == "Autoclave failure"
        assert any(c["label"] == "Flagged for incident review" for c in view["chips"])
        assert any(s["label"] == "Narrative" for s in view["sections"])

    @pytest.mark.asyncio
    async def test_incident_meta_shows_number_not_raw_path(self):
        # Regression: the meta row used to be a raw "/app/ir/<uuid>" path,
        # which RecordViewer.tsx renders as literal (unclickable) text.
        rid = uuid4()
        incident_id = uuid4()
        row = {
            "id": rid, "company_id": uuid4(), "channel_id": uuid4(), "channel_name": "safety",
            "message_id": uuid4(), "reporter_user_id": uuid4(), "reporter_name": "Jane Doe",
            "title": "Autoclave failure", "category": "equipment", "severity_hint": "high",
            "doc": {}, "narrative": "It stopped mid-cycle.", "incident_recommendation": False,
            "incident_reasoning": None, "suggested_incident_type": "property",
            "suggested_severity": "high", "status": "promoted", "incident_id": incident_id,
            "awaiting_reply": False, "clarification_rounds": 0,
            "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc), "updated_at": None,
        }
        conn = _FakeFetchConn(fetchrow_result=row, fetchval_result="IR-2026-004")
        view = await _build_ems_event_view(conn, uuid4(), rid)
        incident_meta = next(m for m in view["meta"] if m["label"] == "Incident")
        assert incident_meta["value"] == "IR-2026-004"
        assert "app/ir" not in incident_meta["value"]

    @pytest.mark.asyncio
    async def test_doc_list_fields_render_as_items(self):
        rid = uuid4()
        row = {
            "id": rid, "company_id": uuid4(), "channel_id": uuid4(), "channel_name": "safety",
            "message_id": uuid4(), "reporter_user_id": uuid4(), "reporter_name": "Jane Doe",
            "title": "Autoclave failure", "category": "equipment", "severity_hint": "high",
            "doc": {"people_involved": ["Jane", "John"]}, "narrative": "x",
            "incident_recommendation": False, "incident_reasoning": None,
            "suggested_incident_type": "property", "suggested_severity": "high",
            "status": "logged", "incident_id": None, "awaiting_reply": False,
            "clarification_rounds": 0, "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
            "updated_at": None,
        }
        conn = _FakeFetchConn(fetchrow_result=row)
        view = await _build_ems_event_view(conn, uuid4(), rid)
        section = next(s for s in view["sections"] if s["label"] == "People Involved")
        assert section["items"] == ["Jane", "John"]

    @pytest.mark.asyncio
    async def test_osha_urgency_gets_red_chip(self):
        rid = uuid4()
        row = {
            "id": rid, "company_id": uuid4(), "channel_id": uuid4(), "channel_name": "safety",
            "message_id": uuid4(), "reporter_user_id": uuid4(), "reporter_name": "Jane Doe",
            "title": "Fall in stockroom", "category": "safety", "severity_hint": "high",
            "doc": {}, "narrative": "Marcus was hospitalized.", "incident_recommendation": True,
            "incident_reasoning": "OSHA reasoning.", "suggested_incident_type": "safety",
            "suggested_severity": "critical", "status": "logged", "incident_id": None,
            "urgency": "osha", "protocol_qualifies": None, "protocol_reasoning": None,
            "awaiting_reply": False, "clarification_rounds": 0,
            "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc), "updated_at": None,
        }
        conn = _FakeFetchConn(fetchrow_result=row)
        view = await _build_ems_event_view(conn, uuid4(), rid)
        chip = next(c for c in view["chips"] if c["label"] == "OSHA-reportable")
        assert chip["tone"] == "red"

    @pytest.mark.asyncio
    async def test_protocol_assessment_renders_as_section(self):
        rid = uuid4()
        row = {
            "id": rid, "company_id": uuid4(), "channel_id": uuid4(), "channel_name": "front-desk",
            "message_id": uuid4(), "reporter_user_id": uuid4(), "reporter_name": "Jane Doe",
            "title": "Guest refund dispute", "category": "guest_experience", "severity_hint": None,
            "doc": {}, "narrative": "A guest asked for a refund.", "incident_recommendation": True,
            "incident_reasoning": None, "suggested_incident_type": None, "suggested_severity": None,
            "status": "logged", "incident_id": None,
            "urgency": None, "protocol_qualifies": True,
            "protocol_reasoning": "Matches the refund-dispute clause.",
            "awaiting_reply": False, "clarification_rounds": 0,
            "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc), "updated_at": None,
        }
        conn = _FakeFetchConn(fetchrow_result=row)
        view = await _build_ems_event_view(conn, uuid4(), rid)
        assert not any(c["label"] in ("OSHA-reportable", "Severe") for c in view["chips"])
        section = next(s for s in view["sections"] if "Qualifies as an incident" in s["label"])
        assert section["body"] == "Matches the refund-dispute clause."
