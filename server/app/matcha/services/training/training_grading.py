"""Pure functions for training quiz grading + lesson sanitization.

Extracted to its own module so unit tests can import without pulling in the
full FastAPI route stack (twilio_webhook → audio_convert → audioop, etc.)
"""

import json
from typing import Any


def parse_jsonb(value: Any) -> Any:
    """asyncpg sometimes returns JSONB as str; this normalizes."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def sanitize_lesson_template(content: Any, quiz: Any) -> dict:
    """Strip correct_key and rationale from quiz before returning to employee."""
    parsed_content = parse_jsonb(content) or {}
    parsed_quiz = parse_jsonb(quiz) or {}
    sanitized_questions = []
    for q in (parsed_quiz.get("questions") or []):
        sanitized_questions.append({
            "id": q.get("id"),
            "prompt": q.get("prompt"),
            "options": q.get("options") or [],
        })
    return {
        "title": parsed_content.get("title"),
        "summary_for_certificate": parsed_content.get("summary_for_certificate"),
        "estimated_minutes": parsed_content.get("estimated_minutes"),
        "sections": parsed_content.get("sections") or [],
        "quiz": {"questions": sanitized_questions},
    }


def grade_quiz(quiz_payload: Any, submitted_answers: dict[str, str]) -> tuple[float, int, int]:
    """Return (score_percent, correct_count, total_count). Quiz payload is the raw template quiz."""
    parsed = parse_jsonb(quiz_payload) or {}
    questions = parsed.get("questions") or []
    if not questions:
        return 0.0, 0, 0
    correct = 0
    for q in questions:
        qid = q.get("id")
        if not qid:
            continue
        chosen = submitted_answers.get(qid)
        if chosen and chosen == q.get("correct_key"):
            correct += 1
    total = len(questions)
    score = (correct / total) * 100.0 if total else 0.0
    return round(score, 2), correct, total
