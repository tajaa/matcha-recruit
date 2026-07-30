"""Tests for EMS event intake classify/parse + the Gemini-outage fallback.

Patches the genai client on `event_intake` itself (the module that DEFINES
`_get_client`), per the repo's patch-the-defining-module rule — patching a
facade re-export would silently no-op and let the call reach a real client.

    cd server && ./venv/bin/python -m pytest tests/ems/test_event_intake_parsing.py -q
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.ems import categories, event_intake


class _FakeConn:
    """Minimal asyncpg-shaped stub: enough to drive
    create_event_from_message without a real database. The INSERT branch
    reconstructs its RETURNING row from the positional args it was called
    with, mirroring what real column defaults (`status='logged'`) would do.
    """

    def __init__(self, context_created_at=None, context_rows=None):
        self._context_created_at = context_created_at
        self._context_rows = context_rows or []
        self.executed = []

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "SELECT created_at FROM channel_messages" in q:
            return {"created_at": self._context_created_at} if self._context_created_at else None
        if "INSERT INTO ems_events" in q:
            (company_id, channel_id, message_id, reporter_user_id,
             title, category, severity_hint, doc_json, narrative,
             incident_recommendation, incident_reasoning,
             suggested_incident_type, suggested_severity) = args
            now = datetime.now(timezone.utc)
            return {
                "id": uuid4(), "company_id": company_id, "channel_id": channel_id,
                "message_id": message_id, "reporter_user_id": reporter_user_id,
                "title": title, "category": category, "severity_hint": severity_hint,
                "doc": doc_json, "narrative": narrative,
                "incident_recommendation": incident_recommendation,
                "incident_reasoning": incident_reasoning,
                "suggested_incident_type": suggested_incident_type,
                "suggested_severity": suggested_severity,
                "status": "logged", "created_at": now, "updated_at": now,
            }
        raise AssertionError(f"unexpected fetchrow: {q}")

    async def fetch(self, query, *args):
        return self._context_rows

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "INSERT 0 1"


class TestParseModelJson:
    def test_valid_payload(self):
        raw = json.dumps({
            "title": "Julia slipped in back of house",
            "category": "safety",
            "severity_hint": "medium",
            "doc": {"who": "Julia", "where": "back of house"},
            "incident_recommendation": True,
            "incident_reasoning": "Possible injury requiring follow-up.",
        })
        data = event_intake._parse_model_json(raw)
        assert data["title"] == "Julia slipped in back of house"
        assert data["category"] == "safety"
        assert data["severity_hint"] == "medium"
        assert data["doc"] == {"who": "Julia", "where": "back of house"}
        assert data["incident_recommendation"] is True
        assert data["incident_reasoning"]

    def test_unknown_category_normalized_to_fallback(self):
        raw = json.dumps({"title": "t", "category": "weather", "doc": {}})
        data = event_intake._parse_model_json(raw)
        assert data["category"] == categories.FALLBACK_KEY

    def test_invalid_severity_hint_becomes_none(self):
        raw = json.dumps({"category": "safety", "severity_hint": "extreme"})
        data = event_intake._parse_model_json(raw)
        assert data["severity_hint"] is None

    def test_non_dict_doc_becomes_empty(self):
        raw = json.dumps({"category": "safety", "doc": ["not", "a", "dict"]})
        data = event_intake._parse_model_json(raw)
        assert data["doc"] == {}

    def test_missing_title_becomes_none(self):
        raw = json.dumps({"category": "safety"})
        data = event_intake._parse_model_json(raw)
        assert data["title"] is None

    def test_clarify_fields_roundtrip(self):
        raw = json.dumps({
            "category": "behavioral", "needs_clarification": True,
            "clarify_question": "Who was involved?",
        })
        data = event_intake._parse_model_json(raw)
        assert data["needs_clarification"] is True
        assert data["clarify_question"] == "Who was involved?"

    def test_empty_question_forces_no_clarification(self):
        raw = json.dumps({
            "category": "behavioral", "needs_clarification": True, "clarify_question": "",
        })
        data = event_intake._parse_model_json(raw)
        assert data["needs_clarification"] is False
        assert data["clarify_question"] is None

    def test_question_capped_at_300(self):
        raw = json.dumps({
            "category": "behavioral", "needs_clarification": True,
            "clarify_question": "x" * 500,
        })
        data = event_intake._parse_model_json(raw)
        assert len(data["clarify_question"]) == 300


class TestConfirmationText:
    def test_names_category_label(self):
        text = event_intake._confirmation_text({"category": "guest_experience", "incident_recommendation": False})
        assert "Guest Experience" in text

    def test_flags_incident_recommendation(self):
        text = event_intake._confirmation_text({"category": "property", "incident_recommendation": True})
        assert "incident" in text.lower()

    def test_no_flag_when_not_recommended(self):
        text = event_intake._confirmation_text({"category": "equipment", "incident_recommendation": False})
        assert "incident" not in text.lower()


class TestCreateEventFromMessage:
    @pytest.mark.asyncio
    async def test_gemini_failure_inserts_fallback_shape(self, monkeypatch):
        def _boom():
            raise RuntimeError("Gemini unavailable")
        monkeypatch.setattr(event_intake, "_get_client", _boom)

        conn = _FakeConn()
        event_row, confirmation = await event_intake.create_event_from_message(
            conn,
            company_id=uuid4(), channel_id=uuid4(), message_id=uuid4(),
            reporter_user_id=uuid4(), content="the ice machine is broken",
        )

        assert event_row is not None
        assert event_row["category"] == categories.FALLBACK_KEY
        assert event_row["narrative"] == "the ice machine is broken"
        assert event_row["doc"] == "{}"
        assert event_row["incident_recommendation"] is False
        assert confirmation  # still confirms in-channel despite the outage

    @pytest.mark.asyncio
    async def test_dedupe_hit_returns_none_and_empty_confirmation(self, monkeypatch):
        def _boom():
            raise RuntimeError("Gemini unavailable")
        monkeypatch.setattr(event_intake, "_get_client", _boom)

        class _DedupeConn(_FakeConn):
            async def fetchrow(self, query, *args):
                if "INSERT INTO ems_events" in " ".join(query.split()):
                    return None  # ON CONFLICT ... DO NOTHING hit
                return await super().fetchrow(query, *args)

        event_row, confirmation = await event_intake.create_event_from_message(
            _DedupeConn(),
            company_id=uuid4(), channel_id=uuid4(), message_id=uuid4(),
            reporter_user_id=uuid4(), content="retried message",
        )
        assert event_row is None
        assert confirmation == ""


class TestClassifyEvent:
    """classify_event is the seam channels_ws.py:_bg_ems_intake calls with NO
    pooled connection held — it makes 1-3 Gemini calls (classify + best-effort
    IR categorize/severity) and must never accept or need a `conn`."""

    @pytest.mark.asyncio
    async def test_takes_no_connection_argument(self):
        import inspect
        params = inspect.signature(event_intake.classify_event).parameters
        assert "conn" not in params

    @pytest.mark.asyncio
    async def test_gemini_failure_returns_fallback_shape(self, monkeypatch):
        def _boom():
            raise RuntimeError("Gemini unavailable")
        monkeypatch.setattr(event_intake, "_get_client", _boom)

        classified = await event_intake.classify_event("the ice machine is broken", [])

        assert classified["category"] == categories.FALLBACK_KEY
        assert classified["incident_recommendation"] is False
        assert classified["suggested_incident_type"] is None
        assert classified["suggested_severity"] is None
        assert classified["needs_clarification"] is False  # never ask during an outage
        assert classified["model_ok"] is False

    @pytest.mark.asyncio
    async def test_success_sets_model_ok(self, monkeypatch):
        class _FakeResp:
            text = json.dumps({"category": "equipment", "doc": {}})

        class _FakeModels:
            async def generate_content(self, **kwargs):
                return _FakeResp()

        class _FakeAio:
            models = _FakeModels()

        class _FakeClient:
            aio = _FakeAio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _FakeClient())

        classified = await event_intake.classify_event("the ice machine is broken", [])
        assert classified["model_ok"] is True
        assert classified["category"] == "equipment"

    @pytest.mark.asyncio
    async def test_degenerate_empty_json_is_not_model_ok(self, monkeypatch):
        """A response that parses as valid JSON but names none of the six
        real categories (so normalize_category falls back to
        FALLBACK_KEY) must not count as model_ok=True — the classify prompt
        never offers "uncategorized" as a real choice, so this only happens
        on a degenerate parse, and apply_refinement's model_ok gate exists
        precisely to keep that from overwriting a good prior classification."""
        class _FakeResp:
            text = json.dumps({})

        class _FakeModels:
            async def generate_content(self, **kwargs):
                return _FakeResp()

        class _FakeAio:
            models = _FakeModels()

        class _FakeClient:
            aio = _FakeAio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _FakeClient())

        classified = await event_intake.classify_event("something happened", [])
        assert classified["category"] == categories.FALLBACK_KEY
        assert classified["model_ok"] is False

    @pytest.mark.asyncio
    async def test_ir_analysis_error_never_propagates(self, monkeypatch):
        """A raising IR analyzer (even the module's own IRAnalysisError) must
        not escape classify_event — this is the failure mode fixed by
        importing IRAnalysisError at module level instead of inside the
        try/except in _ir_suggestions (an import failure there would have
        made the `except IRAnalysisError` clause itself raise NameError)."""
        class _FakeResp:
            text = json.dumps({
                "title": "t", "category": "safety", "doc": {},
                "incident_recommendation": True, "incident_reasoning": "r",
            })

        class _FakeModels:
            async def generate_content(self, **kwargs):
                return _FakeResp()

        class _FakeAio:
            models = _FakeModels()

        class _FakeClient:
            aio = _FakeAio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _FakeClient())

        def _raise_ir_error():
            raise event_intake.IRAnalysisError("analyzer unavailable")
        monkeypatch.setattr(event_intake, "get_ir_analyzer", _raise_ir_error)

        classified = await event_intake.classify_event("Julia slipped", [])

        assert classified["category"] == "safety"
        assert classified["suggested_incident_type"] is None
        assert classified["suggested_severity"] is None


class TestPersistEvent:
    @pytest.mark.asyncio
    async def test_inserts_from_already_classified_dict(self):
        conn = _FakeConn()
        classified = {
            "title": "t", "category": "safety", "severity_hint": "low", "doc": {},
            "incident_recommendation": False, "incident_reasoning": None,
            "suggested_incident_type": None, "suggested_severity": None,
        }
        event_row, confirmation = await event_intake.persist_event(
            conn,
            company_id=uuid4(), channel_id=uuid4(), message_id=uuid4(),
            reporter_user_id=uuid4(), content="Julia slipped", classified=classified,
        )
        assert event_row is not None
        assert event_row["category"] == "safety"
        assert confirmation


class TestRefinementHelpers:
    def test_compose_refinement_content(self):
        text = event_intake.compose_refinement_content(
            "Julia slipped", "Where exactly?", "In the walk-in freezer",
        )
        # Order matters: original narrative first, then the Q, then the A —
        # classify_event re-reads this as an ordinary narrative.
        assert text.index("Julia slipped") < text.index("[Huume asked]: Where exactly?")
        assert text.index("[Huume asked]:") < text.index("[Reply]: In the walk-in freezer")

    @pytest.mark.parametrize(
        "needs_clarification,rounds,expected",
        [
            (True, 0, True),   # intake question was round 1; 1 more allowed
            (True, 1, False),  # 2 rounds used (intake + 1 answer) — cap hit
            (False, 0, False),
        ],
    )
    def test_should_ask_again_cap(self, needs_clarification, rounds, expected):
        classified = {"needs_clarification": needs_clarification}
        assert event_intake.should_ask_again(classified, rounds) is expected

    def test_question_text_appends_prompt(self):
        text = event_intake.question_text("Logged.", "Who was involved?")
        assert "Logged." in text
        assert "Who was involved?" in text
        assert "reply to this message" in text.lower()


class _RefinementFakeConn:
    """Fakes both apply_refinement UPDATE variants (model_ok True/False),
    distinguished by SQL shape — the True variant sets `category = $5`, the
    False variant doesn't touch classification columns at all. Echoes args
    back into a RETURNING-shaped dict rather than modeling real `narrative
    || $3` concatenation, which is enough to assert on for these tests.
    """

    def __init__(self, update_returns_none=False):
        self.update_returns_none = update_returns_none
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.executed: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        self.fetchrow_calls.append((q, args))
        if "UPDATE ems_events" not in q:
            raise AssertionError(f"unexpected fetchrow: {q}")
        if self.update_returns_none:
            return None  # WHERE status='logged' guard missed (promoted/dismissed race)

        now = datetime.now(timezone.utc)
        base = {
            "channel_id": uuid4(), "message_id": uuid4(), "reporter_user_id": uuid4(),
            "status": "logged", "clarification_rounds": 1, "created_at": now, "updated_at": now,
        }
        if "category = $5" in q:
            (event_id, company_id, appended, title, category, severity_hint, doc_json,
             incident_recommendation, incident_reasoning,
             suggested_incident_type, suggested_severity) = args
            return {
                **base, "id": event_id, "company_id": company_id,
                "title": title, "category": category, "severity_hint": severity_hint,
                "doc": doc_json, "narrative": f"original{appended}",
                "incident_recommendation": incident_recommendation,
                "incident_reasoning": incident_reasoning,
                "suggested_incident_type": suggested_incident_type,
                "suggested_severity": suggested_severity,
            }
        event_id, company_id, appended = args
        return {
            **base, "id": event_id, "company_id": company_id,
            "title": None, "category": "uncategorized", "severity_hint": None,
            "doc": "{}", "narrative": f"original{appended}",
            "incident_recommendation": False, "incident_reasoning": None,
            "suggested_incident_type": None, "suggested_severity": None,
        }

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "INSERT 0 1"


class TestApplyRefinement:
    @pytest.mark.asyncio
    async def test_updates_classification_when_model_ok(self):
        conn = _RefinementFakeConn()
        classified = {
            "title": "Slip in freezer", "category": "safety", "severity_hint": "medium",
            "doc": {"where": "walk-in freezer"}, "incident_recommendation": True,
            "incident_reasoning": "Possible injury.", "suggested_incident_type": "safety",
            "suggested_severity": "medium", "model_ok": True,
        }
        updated = await event_intake.apply_refinement(
            conn, event_id=uuid4(), company_id=uuid4(), answer="In the walk-in freezer",
            classified=classified, answered_by=uuid4(),
        )
        assert updated is not None
        assert updated["category"] == "safety"
        assert "Follow-up: In the walk-in freezer" in updated["narrative"]
        # The audit INSERT ran (action='clarified').
        assert any("ems_event_audit_log" in q for q, _ in conn.executed)

    @pytest.mark.asyncio
    async def test_append_only_when_model_failed(self):
        conn = _RefinementFakeConn()
        updated = await event_intake.apply_refinement(
            conn, event_id=uuid4(), company_id=uuid4(), answer="not sure, ask Jenna",
            classified={"model_ok": False}, answered_by=uuid4(),
        )
        assert updated is not None
        # No classification column was touched by the UPDATE this test's
        # single fetchrow call issued.
        update_query = conn.fetchrow_calls[0][0]
        assert "category =" not in update_query
        assert "Follow-up: not sure, ask Jenna" in updated["narrative"]

    @pytest.mark.asyncio
    async def test_none_when_event_not_logged(self):
        conn = _RefinementFakeConn(update_returns_none=True)
        updated = await event_intake.apply_refinement(
            conn, event_id=uuid4(), company_id=uuid4(), answer="answer",
            classified={"model_ok": False}, answered_by=uuid4(),
        )
        assert updated is None
        # No audit row when the guard missed.
        assert conn.executed == []
