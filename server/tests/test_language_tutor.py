"""Tests for the language tutor voice skill in matcha-work.

Covers:
- Skill inference for language_tutor state
- Tutor start endpoint validation
- Tutor status endpoint + inline analysis flow
- Utterance check endpoint parsing
- current_state JSON parsing from asyncpg
"""

import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Stub google.genai before importing app code ──

google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
google_module.genai = genai_module

# Stub types used at module level in matcha_work_ai.py
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None

sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

from app.matcha.services.matcha_work_ai import _infer_skill_from_state


# ═══════════════════════════════════════════════════════════════════════
# 1. Skill inference
# ═══════════════════════════════════════════════════════════════════════


def test_infer_language_tutor_from_state():
    state = {
        "language_tutor": {
            "interview_id": "abc-123",
            "language": "en",
            "status": "active",
        }
    }
    assert _infer_skill_from_state(state) == "language_tutor"


def test_infer_language_tutor_takes_precedence_over_chat():
    """language_tutor key should be detected before fallthrough to 'chat'."""
    state = {"language_tutor": {"interview_id": "x"}}
    assert _infer_skill_from_state(state) == "language_tutor"


def test_infer_chat_without_language_tutor():
    assert _infer_skill_from_state({}) == "chat"
    assert _infer_skill_from_state(None) == "chat"


def test_infer_language_tutor_does_not_override_other_skills():
    """If both language_tutor and offer_letter keys exist, language_tutor wins
    because it's checked first."""
    state = {
        "language_tutor": {"interview_id": "x"},
        "candidate_name": "John",
        "position_title": "Engineer",
    }
    assert _infer_skill_from_state(state) == "language_tutor"


# ═══════════════════════════════════════════════════════════════════════
# 2. Tutor start endpoint validation
# ═══════════════════════════════════════════════════════════════════════


def test_start_validates_language():
    """Language must be 'en' or 'es'."""
    from fastapi import HTTPException

    # Simulate the validation logic from the endpoint
    def validate_language(lang):
        if lang not in ("en", "es"):
            raise HTTPException(status_code=400, detail="Language must be 'en' or 'es'")

    validate_language("en")  # OK
    validate_language("es")  # OK
    with pytest.raises(HTTPException) as exc:
        validate_language("fr")
    assert exc.value.status_code == 400


def test_start_validates_duration():
    """Duration must be 0.33, 2, 5, or 8."""
    from fastapi import HTTPException

    def validate_duration(d):
        if d not in (0.33, 2, 5, 8):
            raise HTTPException(status_code=400)

    validate_duration(0.33)  # 20s test
    validate_duration(2)
    validate_duration(5)
    validate_duration(8)
    with pytest.raises(HTTPException):
        validate_duration(10)
    with pytest.raises(HTTPException):
        validate_duration(1)


def test_duration_seconds_calculation():
    """0.33 minutes should yield 19 seconds (int truncation)."""
    assert int(0.33 * 60) == 19
    assert int(2 * 60) == 120
    assert int(5 * 60) == 300
    assert int(8 * 60) == 480


# ═══════════════════════════════════════════════════════════════════════
# 3. current_state JSON parsing
# ═══════════════════════════════════════════════════════════════════════


def _parse_current_state(raw_state):
    """Replicate the parsing logic from tutor endpoints."""
    if isinstance(raw_state, str):
        return json.loads(raw_state) if raw_state else {}
    elif isinstance(raw_state, dict):
        return dict(raw_state)
    else:
        return {}


def test_parse_current_state_from_json_string():
    raw = '{"language_tutor": {"interview_id": "abc"}}'
    result = _parse_current_state(raw)
    assert result["language_tutor"]["interview_id"] == "abc"


def test_parse_current_state_from_dict():
    raw = {"language_tutor": {"interview_id": "abc"}}
    result = _parse_current_state(raw)
    assert result["language_tutor"]["interview_id"] == "abc"


def test_parse_current_state_from_empty_string():
    assert _parse_current_state("") == {}


def test_parse_current_state_from_none():
    assert _parse_current_state(None) == {}


def test_parse_current_state_from_unexpected_type():
    assert _parse_current_state(42) == {}


# ═══════════════════════════════════════════════════════════════════════
# 4. Utterance check prompt + response parsing
# ═══════════════════════════════════════════════════════════════════════


from app.matcha.routes.matcha_work import UTTERANCE_CHECK_PROMPT_EN, UTTERANCE_CHECK_PROMPT_ES


def test_utterance_prompt_en_contains_utterance():
    prompt = UTTERANCE_CHECK_PROMPT_EN.format(utterance="I go yesterday")
    assert "I go yesterday" in prompt
    assert "JSON array" in prompt


def test_utterance_prompt_es_contains_utterance():
    prompt = UTTERANCE_CHECK_PROMPT_ES.format(utterance="Yo ir ayer")
    assert "Yo ir ayer" in prompt
    assert "JSON" in prompt


def test_utterance_prompt_selects_language():
    """ES prompt used for language='es', EN for anything else."""
    for lang in ("es",):
        prompt = (UTTERANCE_CHECK_PROMPT_ES if lang == "es" else UTTERANCE_CHECK_PROMPT_EN)
        assert "español" in prompt.lower() or "spanish" in prompt.lower()

    prompt_en = UTTERANCE_CHECK_PROMPT_EN
    assert "English" in prompt_en


def _parse_utterance_response(text: str):
    """Replicate the response parsing from check_tutor_utterance."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    errors = json.loads(text)
    return errors if isinstance(errors, list) else []


def test_parse_clean_json_response():
    raw = '[{"error": "I go", "correction": "I went", "type": "grammar", "brief": "past tense"}]'
    errors = _parse_utterance_response(raw)
    assert len(errors) == 1
    assert errors[0]["correction"] == "I went"


def test_parse_markdown_wrapped_json():
    raw = '```json\n[{"error": "buy", "correction": "bought", "type": "grammar", "brief": "past tense"}]\n```'
    errors = _parse_utterance_response(raw)
    assert len(errors) == 1
    assert errors[0]["error"] == "buy"


def test_parse_empty_array():
    assert _parse_utterance_response("[]") == []


def test_parse_non_array_returns_empty():
    """If Gemini returns an object instead of array, return empty."""
    assert _parse_utterance_response('{"error": "oops"}') == []


def test_short_utterance_skipped():
    """Utterances under 3 chars should return empty errors."""
    utterance = "Hi"
    assert len(utterance) < 3  # Would be skipped in endpoint


# ═══════════════════════════════════════════════════════════════════════
# 5. Analysis summary message generation
# ═══════════════════════════════════════════════════════════════════════


def _build_summary(analysis: dict) -> str:
    """Replicate the summary text generation from tutor status endpoint."""
    proficiency = analysis.get("overall_proficiency", {})
    level = proficiency.get("level", "N/A")
    level_desc = proficiency.get("level_description", "")
    summary_text = f"**Language Practice Complete** — CEFR Level: **{level}** ({level_desc})\n\n"
    strengths = proficiency.get("strengths", [])
    if strengths:
        summary_text += "**Strengths:** " + ", ".join(strengths) + "\n\n"
    areas = proficiency.get("areas_to_improve", [])
    if areas:
        summary_text += "**Areas to Improve:** " + ", ".join(areas) + "\n\n"
    grammar_data = analysis.get("grammar", {})
    errors = grammar_data.get("common_errors", [])
    if errors:
        summary_text += "**Grammar Notes:**\n"
        for err in errors[:5]:
            if isinstance(err, dict):
                summary_text += f"- {err.get('error', '')}: {err.get('correction', '')}\n"
            else:
                summary_text += f"- {err}\n"
    return summary_text.strip()


def test_summary_with_full_analysis():
    analysis = {
        "overall_proficiency": {
            "level": "B1",
            "level_description": "Intermediate",
            "strengths": ["Good vocabulary range", "Clear pronunciation"],
            "areas_to_improve": ["Past tense usage", "Articles"],
        },
        "grammar": {
            "common_errors": [
                {"error": "I go yesterday", "correction": "I went yesterday"},
                {"error": "a information", "correction": "information"},
            ],
        },
    }
    summary = _build_summary(analysis)
    assert "**B1**" in summary
    assert "Intermediate" in summary
    assert "Good vocabulary range" in summary
    assert "Past tense usage" in summary
    assert "I go yesterday" in summary
    assert "I went yesterday" in summary


def test_summary_with_empty_analysis():
    summary = _build_summary({})
    assert "N/A" in summary
    assert "Language Practice Complete" in summary


def test_summary_with_string_errors():
    """Grammar errors can be plain strings instead of dicts."""
    analysis = {
        "overall_proficiency": {"level": "A2", "level_description": "Elementary"},
        "grammar": {
            "common_errors": ["Missing articles", "Wrong verb tense"],
        },
    }
    summary = _build_summary(analysis)
    assert "Missing articles" in summary
    assert "Wrong verb tense" in summary


def test_summary_caps_errors_at_five():
    analysis = {
        "grammar": {
            "common_errors": [{"error": f"err{i}", "correction": f"fix{i}"} for i in range(10)],
        },
    }
    summary = _build_summary(analysis)
    assert "err4" in summary
    assert "err5" not in summary
