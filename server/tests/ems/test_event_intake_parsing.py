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
             suggested_incident_type, suggested_severity,
             urgency, protocol_qualifies, protocol_reasoning) = args
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
                "urgency": urgency, "protocol_qualifies": protocol_qualifies,
                "protocol_reasoning": protocol_reasoning,
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

    def test_not_an_event_true(self):
        raw = json.dumps({"not_an_event": True, "category": "uncategorized"})
        data = event_intake._parse_model_json(raw)
        assert data["not_an_event"] is True

    def test_not_an_event_false(self):
        raw = json.dumps({"not_an_event": False, "category": "safety"})
        data = event_intake._parse_model_json(raw)
        assert data["not_an_event"] is False

    def test_not_an_event_missing_defaults_false(self):
        raw = json.dumps({"category": "safety"})
        data = event_intake._parse_model_json(raw)
        assert data["not_an_event"] is False

    def test_severe_true(self):
        raw = json.dumps({"category": "safety", "severe": True})
        data = event_intake._parse_model_json(raw)
        assert data["severe"] is True

    def test_severe_missing_defaults_false(self):
        raw = json.dumps({"category": "safety"})
        data = event_intake._parse_model_json(raw)
        assert data["severe"] is False

    def test_protocol_assessment_parsed(self):
        raw = json.dumps({
            "category": "guest_experience",
            "protocol_assessment": {"qualifies": True, "reasoning": "Matches the guest-complaint definition."},
        })
        data = event_intake._parse_model_json(raw)
        assert data["protocol_qualifies"] is True
        assert data["protocol_reasoning"] == "Matches the guest-complaint definition."

    def test_protocol_assessment_reasoning_capped_at_500(self):
        raw = json.dumps({
            "category": "safety",
            "protocol_assessment": {"qualifies": False, "reasoning": "x" * 800},
        })
        data = event_intake._parse_model_json(raw)
        assert len(data["protocol_reasoning"]) == 500

    def test_protocol_assessment_missing_stays_none(self):
        raw = json.dumps({"category": "safety"})
        data = event_intake._parse_model_json(raw)
        assert data["protocol_qualifies"] is None
        assert data["protocol_reasoning"] is None

    def test_protocol_assessment_malformed_stays_none(self):
        for bad in ('"yes"', "[]", '{"reasoning": "no qualifies key"}'):
            raw = json.dumps({"category": "safety", "protocol_assessment": json.loads(bad)})
            data = event_intake._parse_model_json(raw)
            assert data["protocol_qualifies"] is None
            assert data["protocol_reasoning"] is None

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

    def test_ack_parsed_and_sanitized(self):
        raw = json.dumps({"category": "equipment", "ack": "Ugh, the **ice machine** again\n"})
        data = event_intake._parse_model_json(raw)
        assert data["ack"] == "Ugh, the ice machine again"

    def test_missing_ack_becomes_none(self):
        raw = json.dumps({"category": "equipment"})
        data = event_intake._parse_model_json(raw)
        assert data["ack"] is None


class TestSanitizePillText:
    def test_collapses_newlines_and_whitespace(self):
        assert event_intake._sanitize_pill_text("line one\n\nline  two", 200) == "line one line two"

    def test_strips_asterisks(self):
        # ** would mis-pair with the **category** emphasis _confirmation_text
        # wraps around it — see that function's docstring.
        assert event_intake._sanitize_pill_text("the *freezer* broke", 200) == "the freezer broke"

    def test_caps_length(self):
        assert len(event_intake._sanitize_pill_text("x" * 500, 50)) == 50

    def test_empty_or_none_becomes_none(self):
        assert event_intake._sanitize_pill_text(None, 200) is None
        assert event_intake._sanitize_pill_text("   ", 200) is None
        assert event_intake._sanitize_pill_text("", 200) is None


class TestCoerceDoc:
    """coerce_doc is the single normalization point for BOTH doc writers —
    the model parse path (_parse_model_json) and the admin PUT
    (routes/ems.py:update_event). EventDetail.tsx renders values with
    v.trim(), so a non-string value here is a client crash."""

    def test_non_dict_returns_empty(self):
        assert event_intake.coerce_doc(None) == {}
        assert event_intake.coerce_doc("not a dict") == {}
        assert event_intake.coerce_doc([1, 2, 3]) == {}

    def test_non_string_values_coerced(self):
        assert event_intake.coerce_doc({"count": 3}) == {"count": "3"}
        assert event_intake.coerce_doc({"flag": True}) == {"flag": "True"}
        assert event_intake.coerce_doc({"nested": {"a": 1}}) == {"nested": "{'a': 1}"}

    def test_caps_pairs_keys_values(self):
        eleven_pairs = {f"k{i}": "v" for i in range(11)}
        assert len(event_intake.coerce_doc(eleven_pairs)) == 10

        long_key = "k" * 150
        assert len(list(event_intake.coerce_doc({long_key: "v"}).keys())[0]) == 100

        long_value = "v" * 3000
        assert len(list(event_intake.coerce_doc({"k": long_value}).values())[0]) == 2000


class TestQuestionMarker:
    def test_marker_codepoint_pinned(self):
        # extract_question() scans already-posted pill text for this exact
        # string. A "fix the comment/emoji" edit that changes the codepoint
        # would silently orphan every armed clarify question in the field —
        # pin it as a failing test, not just a comment.
        assert event_intake._QUESTION_MARKER == "\n\U0001F914 "

    def test_extract_question_roundtrip(self):
        pill = event_intake.question_text("\U0001F4CB Logged **Safety** event.", "Who was hurt?")
        assert event_intake.extract_question(pill) == "Who was hurt?"

    def test_extract_question_no_marker_returns_input_unchanged(self):
        assert event_intake.extract_question("plain confirmation, no question") == \
            "plain confirmation, no question"

    def test_extract_question_strips_legacy_suffix(self):
        # Pills armed before the casual-voice pass carry the old suffix —
        # already-posted pills in the field must still round-trip.
        pill = (
            "\U0001F4CB Logged this as **Safety**." + event_intake._QUESTION_MARKER
            + "Who was hurt?" + event_intake._LEGACY_QUESTION_SUFFIX
        )
        assert event_intake.extract_question(pill) == "Who was hurt?"


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

    def test_has_hr_visibility_clause(self):
        # The only disclosure telling a reporter their channel message became
        # an HR-reviewed record — must survive every confirmation pill.
        text = event_intake._confirmation_text({"category": "equipment", "incident_recommendation": False})
        assert "HR admins" in text

    def test_ack_used_when_present(self):
        text = event_intake._confirmation_text(
            {"category": "equipment", "incident_recommendation": False},
            ack="Ugh, the ice machine again",
        )
        assert text.startswith("\U0001F4CB Ugh, the ice machine again — filed under **Equipment**")

    def test_falls_back_without_ack(self):
        text = event_intake._confirmation_text({"category": "equipment", "incident_recommendation": False})
        assert text == "\U0001F4CB Logged this as **Equipment** (visible to HR admins in Events)."

    def test_emphasizes_only_the_category(self):
        # `**` is the ONLY markup the channel renderer parses
        # (systemContent.tsx:renderSystemContent, applied by MessageList's
        # message_type === 'system' branch). Anything else renders as
        # literal characters in the pill, so the markers must (a) be
        # balanced and (b) wrap the category label and nothing else.
        for category, rec, ack in [
            ("safety", True, None), ("operational", False, "Noted, thanks"),
        ]:
            text = event_intake._confirmation_text(
                {"category": category, "incident_recommendation": rec}, ack=ack,
            )
            label = categories.category_label(category)
            assert f"**{label}**" in text, text
            assert text.count("**") == 2, text
            assert "__" not in text, text  # underscore emphasis is NOT parsed


class TestUpdateText:
    def test_ack_used_when_present(self):
        text = event_intake.update_text(
            {"category": "safety", "incident_recommendation": False}, ack="Got it, added that",
        )
        assert text == "\U0001F4CB Got it, added that — updated the **Safety** event."

    def test_falls_back_without_ack(self):
        text = event_intake.update_text({"category": "safety", "incident_recommendation": False})
        assert text == "\U0001F4CB Thanks, updated the **Safety** event."

    def test_flags_incident_recommendation(self):
        text = event_intake.update_text({"category": "safety", "incident_recommendation": True})
        assert "incident" in text.lower()

    def test_osha_urgency_leads_with_siren(self):
        text = event_intake.update_text(
            {"category": "safety", "incident_recommendation": True, "urgency": "osha"},
        )
        assert text.startswith("\U0001F6A8")


class TestPillEmojiAndFlagClause:
    def test_no_urgency_uses_clipboard(self):
        assert event_intake._pill_emoji({"urgency": None}) == "\U0001F4CB"
        assert event_intake._pill_emoji({}) == "\U0001F4CB"

    def test_urgency_uses_siren(self):
        assert event_intake._pill_emoji({"urgency": "osha"}) == "\U0001F6A8"
        assert event_intake._pill_emoji({"urgency": "severe"}) == "\U0001F6A8"

    def test_osha_clause_contains_hotline_and_window(self):
        clause = event_intake._flag_clause({
            "urgency": "osha", "incident_recommendation": True, "protocol_qualifies": None,
        })
        assert "OSHA-reportable" in clause
        assert event_intake.OSHA_EMERGENCY_HOTLINE in clause
        assert event_intake.OSHA_REPORTING_WINDOW in clause

    def test_severe_clause(self):
        clause = event_intake._flag_clause({
            "urgency": "severe", "incident_recommendation": True, "protocol_qualifies": None,
        })
        assert "flagged severe" in clause

    def test_protocol_qualifies_true_clause(self):
        clause = event_intake._flag_clause({
            "urgency": None, "incident_recommendation": True, "protocol_qualifies": True,
        })
        assert "qualifies as an incident" in clause

    def test_protocol_qualifies_false_clause(self):
        clause = event_intake._flag_clause({
            "urgency": None, "incident_recommendation": False, "protocol_qualifies": False,
        })
        assert "doesn't qualify" in clause

    def test_osha_wins_over_protocol_false(self):
        # OSHA bypasses protocol per spec — the pill must lead with the
        # OSHA clause even when the protocol assessment said "no".
        clause = event_intake._flag_clause({
            "urgency": "osha", "incident_recommendation": True, "protocol_qualifies": False,
        })
        assert "OSHA-reportable" in clause

    def test_osha_pill_has_balanced_bold_and_siren_lead(self):
        text = event_intake._confirmation_text({
            "category": "safety", "incident_recommendation": True, "urgency": "osha",
        })
        assert text.startswith("\U0001F6A8")
        assert text.count("**") % 2 == 0

    def test_osha_pill_question_text_round_trips(self):
        confirmation = event_intake._confirmation_text({
            "category": "safety", "incident_recommendation": True, "urgency": "osha",
        })
        pill = event_intake.question_text(confirmation, "Who was hurt?")
        assert pill.startswith("\U0001F6A8")
        assert event_intake.extract_question(pill) == "Who was hurt?"


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


class TestBuildClassifyPrompt:
    def test_no_protocol_text_omits_protocol_sections(self):
        prompt = event_intake._build_classify_prompt("the fridge is loud", [])
        assert "COMPANY INCIDENT PROTOCOL" not in prompt
        assert "protocol_assessment" not in prompt

    def test_protocol_text_adds_both_sections(self):
        prompt = event_intake._build_classify_prompt(
            "we had an incident with a guest", [], protocol_text="Only injuries count as incidents.",
        )
        assert "COMPANY INCIDENT PROTOCOL" in prompt
        assert "Only injuries count as incidents." in prompt
        assert "protocol_assessment" in prompt

    def test_severe_field_always_present(self):
        prompt = event_intake._build_classify_prompt("x", [])
        assert '"severe": bool' in prompt


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
        # An outage must still LOG (documentation survives everything) —
        # never reroute to the ASK backstop just because the model was
        # unreachable.
        assert classified["not_an_event"] is False

    @pytest.mark.asyncio
    async def test_gemini_outage_with_osha_words_still_flags(self, monkeypatch):
        def _boom():
            raise RuntimeError("Gemini unavailable")
        monkeypatch.setattr(event_intake, "_get_client", _boom)
        # OSHA-forced incident_recommendation makes _ir_suggestions run —
        # keep it from attempting a real Gemini call in this outage test.
        def _raise_ir_error():
            raise event_intake.IRAnalysisError("analyzer unavailable")
        monkeypatch.setattr(event_intake, "get_ir_analyzer", _raise_ir_error)

        classified = await event_intake.classify_event(
            "the truck driver was hospitalized after the crash", [],
        )
        assert classified["urgency"] == "osha"
        assert classified["incident_recommendation"] is True
        # Deterministic OSHA prefill overrides the (unavailable) IR suggestions.
        assert classified["suggested_severity"] == "critical"
        assert classified["suggested_incident_type"] == "safety"
        # Still logs as uncategorized — the outage invariant is untouched.
        assert classified["category"] == categories.FALLBACK_KEY

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
    async def test_protocol_assessment_dropped_when_no_protocol_shown(self, monkeypatch):
        """A model that volunteers protocol_assessment despite never being
        shown a protocol block (protocol_text=None — no company protocol
        saved, or the message didn't mention "incident") must not have that
        verdict persisted: it would tell a company with no protocol file
        that its event "doesn't qualify" under one."""
        class _FakeResp:
            text = json.dumps({
                "category": "guest_experience", "doc": {},
                "protocol_assessment": {"qualifies": False, "reasoning": "no protocol on file"},
            })

        class _FakeModels:
            async def generate_content(self, **kwargs):
                return _FakeResp()

        class _FakeAio:
            models = _FakeModels()

        class _FakeClient:
            aio = _FakeAio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _FakeClient())

        classified = await event_intake.classify_event(
            "we had an incident with a guest", [], protocol_text=None,
        )
        assert classified["protocol_qualifies"] is None
        assert classified["protocol_reasoning"] is None

    @pytest.mark.asyncio
    async def test_protocol_assessment_preserved_when_protocol_shown(self, monkeypatch):
        class _FakeResp:
            text = json.dumps({
                "category": "guest_experience", "doc": {},
                "protocol_assessment": {"qualifies": True, "reasoning": "matches the definition"},
            })

        class _FakeModels:
            async def generate_content(self, **kwargs):
                return _FakeResp()

        class _FakeAio:
            models = _FakeModels()

        class _FakeClient:
            aio = _FakeAio()

        monkeypatch.setattr(event_intake, "_get_client", lambda: _FakeClient())

        classified = await event_intake.classify_event(
            "we had an incident with a guest", [], protocol_text="Only injuries count",
        )
        assert classified["protocol_qualifies"] is True
        assert classified["protocol_reasoning"] == "matches the definition"

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

    @pytest.mark.asyncio
    async def test_urgency_and_protocol_columns_roundtrip(self):
        conn = _FakeConn()
        classified = {
            "title": "Hospitalization", "category": "safety", "severity_hint": "high", "doc": {},
            "incident_recommendation": True, "incident_reasoning": "OSHA",
            "suggested_incident_type": "safety", "suggested_severity": "critical",
            "urgency": "osha", "protocol_qualifies": True, "protocol_reasoning": "Matches definition.",
        }
        event_row, _ = await event_intake.persist_event(
            conn,
            company_id=uuid4(), channel_id=uuid4(), message_id=uuid4(),
            reporter_user_id=uuid4(), content="someone was hospitalized", classified=classified,
        )
        assert event_row["urgency"] == "osha"
        assert event_row["protocol_qualifies"] is True
        assert event_row["protocol_reasoning"] == "Matches definition."
        # Audit details carry urgency too.
        audit_query, audit_args = conn.executed[0]
        assert "ems_event_audit_log" in audit_query
        assert '"urgency": "osha"' in audit_args[2]


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


class _FoldFakeConn:
    """Fakes fold_answer's UPDATE — narrative append + rounds increment
    only, never classification columns. Echoes args back into a
    RETURNING-shaped dict rather than modeling real `narrative || $3`
    concatenation, which is enough to assert on for these tests."""

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

        event_id, company_id, appended, escalate, reasoning = args
        now = datetime.now(timezone.utc)
        return {
            "id": event_id, "company_id": company_id,
            "channel_id": uuid4(), "message_id": uuid4(), "reporter_user_id": uuid4(),
            "title": None, "category": "uncategorized", "severity_hint": None,
            "doc": "{}", "narrative": f"original{appended}",
            "incident_recommendation": bool(escalate),
            "incident_reasoning": reasoning if escalate else None,
            "suggested_incident_type": None, "suggested_severity": None,
            "urgency": "osha" if escalate else None,
            "protocol_qualifies": None, "protocol_reasoning": None,
            "status": "logged", "clarification_rounds": 1, "created_at": now, "updated_at": now,
        }

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "INSERT 0 1"


class TestFoldAnswer:
    @pytest.mark.asyncio
    async def test_appends_narrative_and_bumps_rounds(self):
        conn = _FoldFakeConn()
        folded = await event_intake.fold_answer(
            conn, event_id=uuid4(), company_id=uuid4(),
            answer="In the walk-in freezer", answered_by=uuid4(),
        )
        assert folded is not None
        assert "Follow-up: In the walk-in freezer" in folded["narrative"]
        # No classification column in the single UPDATE this issued.
        update_query = conn.fetchrow_calls[0][0]
        assert "category =" not in update_query
        assert "title =" not in update_query
        # The audit INSERT ran (action='clarified').
        assert any("ems_event_audit_log" in q for q, _ in conn.executed)

    @pytest.mark.asyncio
    async def test_none_when_event_not_logged(self):
        conn = _FoldFakeConn(update_returns_none=True)
        folded = await event_intake.fold_answer(
            conn, event_id=uuid4(), company_id=uuid4(),
            answer="answer", answered_by=uuid4(),
        )
        assert folded is None
        # No audit row when the guard missed.
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_osha_answer_escalates(self):
        # Deterministic escalation on the ANSWER text — must fire even
        # though this whole function never calls Gemini (the Gemini-outage
        # clarify path relies on exactly this).
        conn = _FoldFakeConn()
        folded = await event_intake.fold_answer(
            conn, event_id=uuid4(), company_id=uuid4(),
            answer="he was hospitalized overnight", answered_by=uuid4(),
        )
        assert folded["urgency"] == "osha"
        assert folded["incident_recommendation"] is True
        assert folded["incident_reasoning"] == event_intake.OSHA_INCIDENT_REASONING
        # The 4th positional UPDATE param is the escalate flag; 5th is the
        # default reasoning text (only applied by the SQL CASE when the
        # column was previously empty).
        _, args = conn.fetchrow_calls[0]
        assert args[3] is True
        assert args[4] == event_intake.OSHA_INCIDENT_REASONING

    @pytest.mark.asyncio
    async def test_plain_answer_does_not_escalate(self):
        conn = _FoldFakeConn()
        folded = await event_intake.fold_answer(
            conn, event_id=uuid4(), company_id=uuid4(),
            answer="it was near the front counter", answered_by=uuid4(),
        )
        assert folded["urgency"] is None
        _, args = conn.fetchrow_calls[0]
        assert args[3] is False


class _ReclassifyFakeConn:
    """Fakes apply_reclassification's UPDATE — classification columns only,
    never narrative/clarification_rounds (fold_answer already did both)."""

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

        (event_id, company_id, title, category, severity_hint, doc_json,
         incident_recommendation, incident_reasoning,
         suggested_incident_type, suggested_severity,
         urgency, protocol_qualifies, protocol_reasoning) = args
        now = datetime.now(timezone.utc)
        return {
            "id": event_id, "company_id": company_id,
            "channel_id": uuid4(), "message_id": uuid4(), "reporter_user_id": uuid4(),
            "title": title, "category": category, "severity_hint": severity_hint,
            "doc": doc_json, "narrative": "original + follow-up (untouched by this UPDATE)",
            "incident_recommendation": incident_recommendation,
            "incident_reasoning": incident_reasoning,
            "suggested_incident_type": suggested_incident_type,
            "suggested_severity": suggested_severity,
            "urgency": urgency, "protocol_qualifies": protocol_qualifies,
            "protocol_reasoning": protocol_reasoning,
            "status": "logged", "clarification_rounds": 1, "created_at": now, "updated_at": now,
        }

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "INSERT 0 1"


class TestApplyReclassification:
    _CLASSIFIED_OK = {
        "title": "Slip in freezer", "category": "safety", "severity_hint": "medium",
        "doc": {"where": "walk-in freezer"}, "incident_recommendation": True,
        "incident_reasoning": "Possible injury.", "suggested_incident_type": "safety",
        "suggested_severity": "medium", "model_ok": True,
    }

    @pytest.mark.asyncio
    async def test_rewrites_classification_when_model_ok(self):
        conn = _ReclassifyFakeConn()
        reclassified = await event_intake.apply_reclassification(
            conn, event_id=uuid4(), company_id=uuid4(), classified=self._CLASSIFIED_OK,
        )
        assert reclassified is not None
        assert reclassified["category"] == "safety"
        # Never WRITES narrative or clarification_rounds — fold_answer's
        # job. (RETURNING still names them, hence checking for the
        # assignment form, not bare substring presence.)
        update_query = conn.fetchrow_calls[0][0]
        assert "narrative =" not in update_query
        assert "clarification_rounds =" not in update_query
        assert any("ems_event_audit_log" in q for q, _ in conn.executed)

    @pytest.mark.asyncio
    async def test_noop_when_model_not_ok(self):
        conn = _ReclassifyFakeConn()
        reclassified = await event_intake.apply_reclassification(
            conn, event_id=uuid4(), company_id=uuid4(), classified={"model_ok": False},
        )
        assert reclassified is None
        # Never even issues the UPDATE — a Gemini failure during reclassify
        # must not touch the row fold_answer already committed.
        assert conn.fetchrow_calls == []
        assert conn.executed == []

    @pytest.mark.asyncio
    async def test_none_when_event_not_logged(self):
        conn = _ReclassifyFakeConn(update_returns_none=True)
        reclassified = await event_intake.apply_reclassification(
            conn, event_id=uuid4(), company_id=uuid4(), classified=self._CLASSIFIED_OK,
        )
        assert reclassified is None
        assert conn.executed == []
