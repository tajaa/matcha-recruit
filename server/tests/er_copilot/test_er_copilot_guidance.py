from app.matcha.services.er_guidance import (
    _build_fallback_guidance_payload,
    _determination_confidence_floor,
    _normalize_guidance_action,
    _normalize_suggested_guidance_payload,
)
from app.matcha.routes.er_copilot._shared import _load_guidance_context, _resolve_involved_parties


def test_fallback_guidance_prompts_for_more_docs_when_discrepancy_unavailable():
    payload = _build_fallback_guidance_payload(
        timeline_data={"gaps_identified": []},
        discrepancies_data={"discrepancies": []},
        policy_data={"violations": []},
        completed_non_policy_docs=[{"id": "doc-1", "filename": "statement-a.txt"}],
        objective=None,
        immediate_risk=None,
    )

    assert payload["fallback_used"] is True
    assert any(card["action"]["type"] == "upload_document" for card in payload["cards"])


def test_normalize_guidance_action_blocks_discrepancy_when_doc_count_is_low():
    action = _normalize_guidance_action(
        {
            "type": "run_analysis",
            "label": "Run Discrepancy Analysis",
            "analysis_type": "discrepancies",
            "tab": "discrepancies",
        },
        can_run_discrepancies=False,
    )

    assert action["type"] == "upload_document"
    assert action["analysis_type"] is None


def test_normalize_suggested_guidance_payload_uses_fallback_cards_for_bad_payload():
    fallback = _build_fallback_guidance_payload(
        timeline_data={"gaps_identified": ["Missing 2pm interview notes"]},
        discrepancies_data={"discrepancies": []},
        policy_data={"violations": []},
        completed_non_policy_docs=[
            {"id": "doc-1", "filename": "statement-a.txt"},
            {"id": "doc-2", "filename": "statement-b.txt"},
        ],
        objective="timeline",
        immediate_risk="no",
    )

    normalized = _normalize_suggested_guidance_payload(
        raw_payload={"summary": "", "cards": "invalid"},
        fallback_payload=fallback,
        can_run_discrepancies=True,
        model_name="gemini-2.5-flash",
    )

    assert normalized["summary"] == fallback["summary"]
    assert normalized["cards"] == fallback["cards"]
    assert normalized["model"] == "gemini-2.5-flash"
    assert normalized["fallback_used"] is False


# ===========================================
# _determination_confidence_floor tests
# ===========================================

def test_confidence_floor_no_evidence():
    assert _determination_confidence_floor(
        completed_doc_count=0,
        transcript_count=0,
        has_analyses=False,
        has_policy_violations=False,
    ) == 0.10


def test_confidence_floor_with_transcripts_only():
    assert _determination_confidence_floor(
        completed_doc_count=1,
        transcript_count=1,
        has_analyses=False,
        has_policy_violations=False,
    ) == 0.15


def test_confidence_floor_with_analyses_no_violations():
    assert _determination_confidence_floor(
        completed_doc_count=2,
        transcript_count=0,
        has_analyses=True,
        has_policy_violations=False,
    ) == 0.20


def test_confidence_floor_with_policy_violations():
    assert _determination_confidence_floor(
        completed_doc_count=1,
        transcript_count=0,
        has_analyses=True,
        has_policy_violations=True,
    ) == 0.30


def test_confidence_floor_violations_plus_multiple_transcripts():
    assert _determination_confidence_floor(
        completed_doc_count=3,
        transcript_count=2,
        has_analyses=True,
        has_policy_violations=True,
    ) == 0.35


# ===========================================
# evaluate_determination_confidence unit tests (no LLM)
# ===========================================

import asyncio
import json
import sys
from unittest.mock import AsyncMock, patch, MagicMock


def _make_analyzer():
    # Stub out google.genai so er_analyzer can be imported without the package installed.
    google_stub = MagicMock()
    google_stub.genai = MagicMock()
    with patch.dict(sys.modules, {"google": google_stub, "google.genai": google_stub.genai}):
        from app.matcha.services.er_analyzer import ERAnalyzer  # noqa: PLC0415
        analyzer = ERAnalyzer.__new__(ERAnalyzer)
    analyzer.model = "gemini-2.5-flash"
    analyzer.client = MagicMock()
    return analyzer


def test_evaluate_confidence_parses_valid_response():
    analyzer = _make_analyzer()
    mock_response = json.dumps({
        "confidence": 0.62,
        "signals": [
            {"name": "hard_evidence", "present": True, "strength": "strong", "reasoning": "Policy logs confirm violation."},
            {"name": "admission", "present": False, "strength": "weak", "reasoning": "No admission found."},
        ],
        "summary": "Substantial evidence present.",
    })

    async def run():
        with patch.object(analyzer, "_generate_content_async", new=AsyncMock(return_value=mock_response)):
            return await analyzer.evaluate_determination_confidence(
                case_info={}, evidence_overview={}, transcript_excerpts="",
                timeline_summary="", discrepancies_summary="", policy_summary="",
            )

    result = asyncio.run(run())
    assert result["confidence"] == 0.62
    assert len(result["signals"]) == 2
    assert result["summary"] == "Substantial evidence present."


def test_evaluate_confidence_clamps_out_of_range():
    analyzer = _make_analyzer()
    mock_response = json.dumps({"confidence": 1.5, "signals": [], "summary": "Too high."})

    async def run():
        with patch.object(analyzer, "_generate_content_async", new=AsyncMock(return_value=mock_response)):
            return await analyzer.evaluate_determination_confidence(
                case_info={}, evidence_overview={}, transcript_excerpts="",
                timeline_summary="", discrepancies_summary="", policy_summary="",
            )

    result = asyncio.run(run())
    assert result["confidence"] == 0.95


def test_evaluate_confidence_returns_fallback_on_llm_error():
    analyzer = _make_analyzer()

    async def run():
        with patch.object(analyzer, "_generate_content_async", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
            return await analyzer.evaluate_determination_confidence(
                case_info={}, evidence_overview={}, transcript_excerpts="",
                timeline_summary="", discrepancies_summary="", policy_summary="",
            )

    result = asyncio.run(run())
    assert result["confidence"] == 0.10
    assert result["signals"] == []


# ===========================================
# _generate_content_async timeout + retry
# ===========================================

class _FakeResponse:
    def __init__(self, text):
        self.text = text


def test_generate_content_async_retries_once_on_timeout_then_succeeds():
    analyzer = _make_analyzer()
    analyzer.client.aio.models.generate_content = AsyncMock(
        side_effect=[asyncio.TimeoutError(), _FakeResponse("recovered")]
    )

    result = asyncio.run(analyzer._generate_content_async("prompt"))

    assert result == "recovered"
    call_args = analyzer.client.aio.models.generate_content.call_args_list
    assert len(call_args) == 2
    # Timeout must retry the SAME model candidate, not advance to a fallback.
    assert call_args[0].kwargs["model"] == call_args[1].kwargs["model"] == analyzer.model


def test_generate_content_async_gives_up_after_repeated_timeout():
    analyzer = _make_analyzer()
    analyzer.client.aio.models.generate_content = AsyncMock(
        side_effect=[asyncio.TimeoutError(), asyncio.TimeoutError()]
    )

    async def run():
        await analyzer._generate_content_async("prompt")

    try:
        asyncio.run(run())
        assert False, "expected TimeoutError to propagate"
    except TimeoutError as exc:
        assert "TIMED OUT" in str(exc)

    # Bounded to 2 attempts on the first candidate — does not cascade through
    # every fallback model on a timeout (that would blow past the nginx
    # SSE timeout budget sized for a 2-attempt worst case).
    assert analyzer.client.aio.models.generate_content.call_count == 2


def test_generate_content_async_timeout_logs_error_with_marker(caplog):
    analyzer = _make_analyzer()
    analyzer.client.aio.models.generate_content = AsyncMock(
        side_effect=[asyncio.TimeoutError(), _FakeResponse("ok")]
    )

    with caplog.at_level("ERROR", logger="app.matcha.services.er_analyzer"):
        asyncio.run(analyzer._generate_content_async("prompt"))

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert any("TIMED OUT" in r.getMessage() and "120" in r.getMessage() for r in error_records)


# ===========================================
# _generate_content_streaming timeout + retry
# ===========================================

class _FakeChunk:
    def __init__(self, text):
        self.text = text


class _FakeStream:
    """Minimal async-iterable stand-in for the Gemini stream response."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeChunk(item)


def test_generate_content_streaming_retries_before_any_chunk_yielded():
    analyzer = _make_analyzer()
    timed_out_stream = _FakeStream([asyncio.TimeoutError()])
    recovered_stream = _FakeStream(["hello ", "world"])
    analyzer.client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[timed_out_stream, recovered_stream]
    )

    async def run():
        return [chunk async for chunk in analyzer._generate_content_streaming("prompt")]

    chunks = asyncio.run(run())

    assert chunks == ["hello ", "world"]
    assert analyzer.client.aio.models.generate_content_stream.call_count == 2


def test_generate_content_streaming_does_not_retry_after_chunk_yielded():
    analyzer = _make_analyzer()
    stream = _FakeStream(["partial output", asyncio.TimeoutError()])
    analyzer.client.aio.models.generate_content_stream = AsyncMock(return_value=stream)

    async def run():
        collected = []
        async for chunk in analyzer._generate_content_streaming("prompt"):
            collected.append(chunk)
        return collected

    try:
        asyncio.run(run())
        assert False, "expected TimeoutError to propagate after a chunk was already yielded"
    except TimeoutError as exc:
        assert "mid-stream" in str(exc)

    # Must NOT retry once output has started — retrying would duplicate
    # already-yielded text in the caller's accumulator.
    assert analyzer.client.aio.models.generate_content_stream.call_count == 1


# ===========================================
# _load_guidance_context — one query, three filtered views
# ===========================================

class _FakeConn:
    """Records queries and returns canned rows by matching a SQL substring."""

    def __init__(self, doc_rows, involved_employees_rows):
        self._doc_rows = doc_rows
        self._involved_employees_rows = involved_employees_rows
        self.fetch_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append(query)
        if "er_case_documents" in query:
            return self._doc_rows
        if "FROM employees" in query:
            return self._involved_employees_rows
        return []

    async def fetchrow(self, query, *args):
        return None

    async def fetchval(self, query, *args):
        return 0


def test_load_guidance_context_filters_one_query_into_three_views():
    import uuid

    doc_rows = [
        {"id": "d1", "filename": "policy.pdf", "document_type": "policy", "scrubbed_text": "policy text"},
        {"id": "d2", "filename": "interview.txt", "document_type": "transcript", "scrubbed_text": "witness said..."},
        {"id": "d3", "filename": "empty.txt", "document_type": "other", "scrubbed_text": ""},
        {"id": "d4", "filename": "email.txt", "document_type": "email", "scrubbed_text": "some email body"},
    ]
    conn = _FakeConn(doc_rows=doc_rows, involved_employees_rows=[])
    case_row = {"involved_employees": []}

    ctx = asyncio.run(_load_guidance_context(conn, uuid.uuid4(), case_row))

    # evidence_rows excludes policy docs.
    assert [r["id"] for r in ctx["evidence_rows"]] == ["d2", "d3", "d4"]
    # transcript_rows contains only transcript-type docs.
    assert [r["id"] for r in ctx["transcript_rows"]] == ["d2"]
    # all_doc_text_rows excludes docs with null/empty scrubbed_text.
    assert [r["id"] for r in ctx["all_doc_text_rows"]] == ["d1", "d2", "d4"]
    # Only one query hit er_case_documents (consolidated from 3).
    assert sum(1 for q in conn.fetch_calls if "er_case_documents" in q) == 1


def test_resolve_involved_parties_skips_malformed_entries():
    import uuid

    good_id = uuid.uuid4()
    involved = [
        {"employee_id": str(good_id), "role": "respondent"},
        {"employee_id": "not-a-uuid", "role": "witness"},  # invalid UUID → skip
        {"role": "complainant"},                            # missing id → skip
        "garbage-string-entry",                             # non-dict → skip
        {"employee_id": None},                              # falsy id → skip
    ]
    conn = _FakeConn(
        doc_rows=[],
        involved_employees_rows=[
            {"id": good_id, "first_name": "Jane", "last_name": "Doe"},
        ],
    )

    result = asyncio.run(_resolve_involved_parties(conn, involved))

    assert result == [{"name": "Jane Doe", "role": "respondent"}]
