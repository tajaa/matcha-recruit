from app.matcha.services.er_guidance import (
    _build_fallback_guidance_payload,
    _determination_confidence_floor,
    _normalize_guidance_action,
    _normalize_suggested_guidance_payload,
)


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
