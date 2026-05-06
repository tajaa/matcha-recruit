"""Unit tests for grade_quiz + sanitize_lesson_template (pure functions)."""

import json

from app.matcha.services.training_grading import (
    grade_quiz as _grade_quiz,
    parse_jsonb as _parse_jsonb,
    sanitize_lesson_template as _sanitize_lesson_template,
)


QUIZ = {
    "questions": [
        {
            "id": "q01",
            "prompt": "Q1?",
            "options": [
                {"key": "A", "text": "a"},
                {"key": "B", "text": "b"},
                {"key": "C", "text": "c"},
                {"key": "D", "text": "d"},
            ],
            "correct_key": "B",
            "rationale": "B because…",
        },
        {
            "id": "q02",
            "prompt": "Q2?",
            "options": [
                {"key": "A", "text": "a"},
                {"key": "B", "text": "b"},
                {"key": "C", "text": "c"},
                {"key": "D", "text": "d"},
            ],
            "correct_key": "D",
            "rationale": "D because…",
        },
    ]
}


def test_grade_quiz_all_correct():
    score, correct, total = _grade_quiz(QUIZ, {"q01": "B", "q02": "D"})
    assert correct == 2
    assert total == 2
    assert score == 100.0


def test_grade_quiz_partial():
    score, correct, total = _grade_quiz(QUIZ, {"q01": "B", "q02": "A"})
    assert correct == 1
    assert total == 2
    assert score == 50.0


def test_grade_quiz_no_answers():
    score, correct, total = _grade_quiz(QUIZ, {})
    assert correct == 0
    assert total == 2
    assert score == 0.0


def test_grade_quiz_handles_jsonb_string():
    """Quiz comes from asyncpg as a JSON string when DB driver lacks codec."""
    score, correct, total = _grade_quiz(json.dumps(QUIZ), {"q01": "B", "q02": "D"})
    assert score == 100.0
    assert correct == 2


def test_sanitize_lesson_strips_correct_key_and_rationale():
    """Employee-facing lesson must NOT leak correct_key or rationale."""
    content = {"title": "T", "summary_for_certificate": "s", "estimated_minutes": 60, "sections": []}
    sanitized = _sanitize_lesson_template(content, QUIZ)
    for q in sanitized["quiz"]["questions"]:
        assert "correct_key" not in q
        assert "rationale" not in q
        assert q["id"]
        assert q["prompt"]
        assert q["options"]


def test_parse_jsonb_handles_dict_and_string():
    assert _parse_jsonb({"a": 1}) == {"a": 1}
    assert _parse_jsonb('{"a": 1}') == {"a": 1}
    assert _parse_jsonb("not-json") is None
    assert _parse_jsonb(None) is None
