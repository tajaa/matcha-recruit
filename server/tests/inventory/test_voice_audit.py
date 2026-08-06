"""Voice stock-count dictation — pure clamp logic, resolve_count_lines
against a fake connection, and the Gemini wrapper's never-raises/retry
contract with a fake client. No real DB, no real Gemini call.

    cd server && ./venv/bin/python -m pytest tests/inventory/test_voice_audit.py -q
"""

import asyncio
import json

from app.matcha.services.inventory import voice_audit


def _run(coro):
    return asyncio.run(coro)


class TestCoerceVoiceCounts:
    def test_valid_payload_passes_through(self):
        raw = {"transcript": "twelve boxes of gloves", "lines": [
            {"item_name": "Gloves", "quantity": 12, "unit": "boxes"},
        ]}
        result = voice_audit._coerce_voice_counts(raw)
        assert result["transcript"] == "twelve boxes of gloves"
        assert result["lines"] == [{"item_name": "Gloves", "quantity": 12.0, "unit": "boxes"}]

    def test_negative_quantity_dropped(self):
        raw = {"lines": [{"item_name": "Gloves", "quantity": -1}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"] == []

    def test_bool_quantity_dropped(self):
        raw = {"lines": [{"item_name": "Gloves", "quantity": True}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"] == []

    def test_non_numeric_quantity_dropped(self):
        raw = {"lines": [{"item_name": "Gloves", "quantity": "a dozen"}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"] == []

    def test_empty_item_name_dropped(self):
        raw = {"lines": [{"item_name": "  ", "quantity": 5}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"] == []

    def test_non_str_item_name_dropped(self):
        raw = {"lines": [{"item_name": 5, "quantity": 5}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"] == []

    def test_long_item_name_clamped(self):
        raw = {"lines": [{"item_name": "x" * 500, "quantity": 1}]}
        assert len(voice_audit._coerce_voice_counts(raw)["lines"][0]["item_name"]) == 200

    def test_line_count_capped(self):
        raw = {"lines": [{"item_name": f"item {i}", "quantity": 1} for i in range(voice_audit.MAX_VOICE_LINES + 10)]}
        assert len(voice_audit._coerce_voice_counts(raw)["lines"]) == voice_audit.MAX_VOICE_LINES

    def test_missing_keys_never_raises(self):
        assert voice_audit._coerce_voice_counts({}) == {"transcript": None, "lines": []}

    def test_unit_omitted_becomes_none(self):
        raw = {"lines": [{"item_name": "Gloves", "quantity": 1}]}
        assert voice_audit._coerce_voice_counts(raw)["lines"][0]["unit"] is None

    def test_non_list_lines_never_raises(self):
        assert voice_audit._coerce_voice_counts({"lines": "not a list"}) == {"transcript": None, "lines": []}

    def test_non_dict_entries_skipped(self):
        raw = {"lines": ["not a dict", {"item_name": "Gloves", "quantity": 1}]}
        assert len(voice_audit._coerce_voice_counts(raw)["lines"]) == 1

    def test_non_dict_payload_never_raises(self):
        # A model that returns valid JSON but not a JSON object (e.g. a
        # top-level array) must not blow up _coerce_voice_counts with an
        # AttributeError on .get() — same never-raises contract as the
        # missing-keys case.
        assert voice_audit._coerce_voice_counts([1, 2, 3]) == {"transcript": None, "lines": []}
        assert voice_audit._coerce_voice_counts("not json-ish") == {"transcript": None, "lines": []}
        assert voice_audit._coerce_voice_counts(None) == {"transcript": None, "lines": []}


class FakeConn:
    pass


class TestResolveCountLines:
    def test_exact_match_attaches_item_and_exact_true(self, monkeypatch):
        async def fake_list(conn, company_id, location_id=None):
            return [{"id": "item-1", "name": "Gloves", "normalized_name": "glove"}]

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )
        lines = _run(voice_audit.resolve_count_lines(
            FakeConn(), company_id="c1", location_id=None,
            lines=[{"item_name": "Gloves", "quantity": 12, "unit": "boxes"}],
        ))
        assert lines[0]["item_id"] == "item-1"
        assert lines[0]["exact"] is True

    def test_fuzzy_match_attaches_item_and_exact_false(self, monkeypatch):
        async def fake_list(conn, company_id, location_id=None):
            return [{"id": "item-1", "name": "Cherry Farms Cookies", "normalized_name": "cherry farm cookie"}]

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )
        lines = _run(voice_audit.resolve_count_lines(
            FakeConn(), company_id="c1", location_id=None,
            lines=[{"item_name": "cheery farms cookies", "quantity": 3, "unit": None}],
        ))
        assert lines[0]["item_id"] == "item-1"
        assert lines[0]["exact"] is False

    def test_no_match_leaves_item_id_none(self, monkeypatch):
        async def fake_list(conn, company_id, location_id=None):
            return []

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )
        lines = _run(voice_audit.resolve_count_lines(
            FakeConn(), company_id="c1", location_id=None,
            lines=[{"item_name": "Brand New Widget", "quantity": 1, "unit": None}],
        ))
        assert lines[0]["item_id"] is None
        assert lines[0]["matched_name"] is None
        assert lines[0]["exact"] is False

    def test_existing_catalog_skips_requery(self, monkeypatch):
        # routes/inventory.py's /audit/voice-parse fetches the catalog once
        # for the grounding prompt and passes it straight through here —
        # resolve_count_lines must not fetch it a second time.
        calls = {"n": 0}

        async def fake_list(conn, company_id, location_id=None):
            calls["n"] += 1
            return []

        monkeypatch.setattr(
            "app.matcha.services.inventory.movements.list_item_names", fake_list,
        )
        existing = [{"id": "item-1", "name": "Gloves", "normalized_name": "glove"}]
        lines = _run(voice_audit.resolve_count_lines(
            FakeConn(), company_id="c1", location_id=None,
            lines=[{"item_name": "Gloves", "quantity": 12, "unit": "boxes"}],
            existing=existing,
        ))
        assert lines[0]["item_id"] == "item-1"
        assert calls["n"] == 0


class _FakeModels:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    async def generate_content(self, *, model, contents, config):
        if self._raises:
            raise self._raises
        return self._response


class _FakeAio:
    def __init__(self, models):
        self.models = models


class _FakeClient:
    def __init__(self, response=None, raises=None):
        self.aio = _FakeAio(_FakeModels(response=response, raises=raises))


class _FakeResp:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class TestParseVoiceCounts:
    def test_gemini_failure_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            voice_audit, "genai_env_client", lambda: _FakeClient(raises=RuntimeError("boom")),
        )
        result = _run(voice_audit.parse_voice_counts(b"fake wav", "audio/wav", item_names=[]))
        assert result["available"] is False
        assert result["lines"] == []

    def test_successful_parse_returns_lines(self, monkeypatch):
        payload = {"transcript": "six bags of espresso", "lines": [
            {"item_name": "Espresso Beans", "quantity": 6, "unit": "bags"},
        ]}
        monkeypatch.setattr(
            voice_audit, "genai_env_client", lambda: _FakeClient(response=_FakeResp(payload)),
        )
        result = _run(voice_audit.parse_voice_counts(b"fake wav", "audio/wav", item_names=["Espresso Beans"]))
        assert result["available"] is True
        assert result["lines"][0]["item_name"] == "Espresso Beans"
        assert result["model"] == voice_audit.GEMINI_FLASH

    def test_timeout_then_success_retries_once(self, monkeypatch):
        payload = {"transcript": "ok", "lines": [{"item_name": "Gloves", "quantity": 1, "unit": None}]}
        calls = {"n": 0}

        class _RetryModels:
            async def generate_content(self, *, model, contents, config):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise asyncio.TimeoutError()
                return _FakeResp(payload)

        class _RetryClient:
            aio = _FakeAio(_RetryModels())

        monkeypatch.setattr(voice_audit, "genai_env_client", lambda: _RetryClient())
        result = _run(voice_audit.parse_voice_counts(b"fake wav", "audio/wav", item_names=[]))
        assert calls["n"] == 2
        assert result["available"] is True

    def test_clean_transcript_with_zero_counts_still_available(self, monkeypatch):
        # A successful Gemini call that heard no countable items (e.g. pure
        # chatter) is NOT a failure — `available` must stay True so the UI
        # shows "didn't catch any counts", not "couldn't understand the
        # audio". Regression for available previously being bool(lines).
        payload = {"transcript": "just checking the mic, one two three", "lines": []}
        monkeypatch.setattr(
            voice_audit, "genai_env_client", lambda: _FakeClient(response=_FakeResp(payload)),
        )
        result = _run(voice_audit.parse_voice_counts(b"fake wav", "audio/wav", item_names=[]))
        assert result["available"] is True
        assert result["lines"] == []

    def test_top_level_json_array_never_raises(self, monkeypatch):
        # A model response that's valid JSON but not an object (top-level
        # array) must not 500 the route — same never-raises contract as any
        # other malformed response.
        class _ArrayResp:
            text = "[1, 2, 3]"

        monkeypatch.setattr(
            voice_audit, "genai_env_client", lambda: _FakeClient(response=_ArrayResp()),
        )
        result = _run(voice_audit.parse_voice_counts(b"fake wav", "audio/wav", item_names=[]))
        assert result["lines"] == []
