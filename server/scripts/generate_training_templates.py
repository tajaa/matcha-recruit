"""Generate global CA harassment-prevention training lesson templates via Gemini.

Run once at deploy (or whenever a content version is bumped):
    venv/bin/python -m scripts.generate_training_templates

Writes two rows into `training_lesson_templates`:
  - template_key='ca_harassment_nonsupervisor', variant='nonsupervisor', 60 min, 10 quiz questions
  - template_key='ca_harassment_supervisor',    variant='supervisor',    120 min, 15 quiz questions

Idempotent on (template_key, version). To regenerate, bump VERSION below or run with --force.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai

from app.config import load_settings
from app.database import get_connection, init_db
from app.core.services.handbook_service import _extract_json_payload


VERSION = 1
FORCE = "--force" in sys.argv


VARIANTS = [
    {
        "template_key": "ca_harassment_nonsupervisor",
        "variant": "nonsupervisor",
        "required_minutes": 60,
        "frequency_months": 24,
        "title": "California Harassment Prevention — Employee (1 hour)",
        "training_type": "harassment_prevention",
        "jurisdiction": "CA",
        "quiz_count": 10,
        "scenario_min": 4,
        "extra_coverage": "",
    },
    {
        "template_key": "ca_harassment_supervisor",
        "variant": "supervisor",
        "required_minutes": 120,
        "frequency_months": 24,
        "title": "California Harassment Prevention — Supervisor (2 hours)",
        "training_type": "harassment_prevention",
        "jurisdiction": "CA",
        "quiz_count": 15,
        "scenario_min": 6,
        "extra_coverage": (
            "ADDITIONAL FOR SUPERVISOR (must include — adds ~60 minutes of content):\n"
            "9. Supervisor's affirmative duty to take all reasonable steps to prevent harassment "
            "(Gov. Code §12940(k)).\n"
            "10. Required immediate response when receiving complaints; documentation; the "
            "investigation duty.\n"
            "11. Practical scenarios: receiving complaints, witness interviews, retaliation flags.\n"
            "12. Strict liability for supervisors' conduct vs. negligence standard for coworker "
            "conduct.\n"
            "13. Personal liability under FEHA §12940(j)(3).\n"
        ),
    },
]


def build_prompt(v: dict) -> str:
    """Construct the lesson + quiz prompt for a given variant."""
    sup_or_non = v["variant"]
    minutes = v["required_minutes"]
    quiz_count = v["quiz_count"]
    scenarios = v["scenario_min"]
    return (
        "You are drafting an interactive employee training module that satisfies "
        "California SB 1343 sexual-harassment-prevention training requirements.\n\n"
        f"VARIANT: {sup_or_non} ({minutes} minutes)\n"
        "JURISDICTION: California\n"
        "LEGAL BASIS: Government Code §12950.1, FEHA, FEHC regulations 2 CCR §11023-11024\n\n"
        "RETURN JSON ONLY with this shape (no markdown fences, no preamble):\n"
        "{\n"
        '  "title": "string",\n'
        '  "summary_for_certificate": "1-2 sentences for the printed certificate",\n'
        f'  "estimated_minutes": {minutes},\n'
        '  "sections": [\n'
        '    {\n'
        '      "id": "snake_case_unique",\n'
        '      "title": "string",\n'
        '      "estimated_minutes": <integer>,\n'
        '      "body_md": "Markdown body, 400-600 words per section, plain language, '
        'practical examples, no legalese in body (legalese OK in rationales).",\n'
        '      "key_takeaways": ["bullet 1", "bullet 2", "bullet 3"]\n'
        '    }\n'
        '  ],\n'
        '  "quiz": {\n'
        '    "questions": [\n'
        '      {\n'
        '        "id": "q01",\n'
        '        "prompt": "Scenario or knowledge-check question.",\n'
        '        "options": [\n'
        '          {"key": "A", "text": "..."},\n'
        '          {"key": "B", "text": "..."},\n'
        '          {"key": "C", "text": "..."},\n'
        '          {"key": "D", "text": "..."}\n'
        '        ],\n'
        '        "correct_key": "B",\n'
        '        "rationale": "Why B is correct, citing FEHA / Gov. Code where relevant."\n'
        '      }\n'
        '    ]\n'
        '  }\n'
        "}\n\n"
        "SECTION COVERAGE (must include):\n"
        "1. Definition: sexual harassment, gender harassment, hostile-environment harassment, "
        "quid pro quo.\n"
        "2. FEHA and Title VII overview, protected categories under California law.\n"
        "3. Examples of unlawful conduct (verbal, visual, physical), with realistic scenarios.\n"
        "4. Bystander intervention and how to support colleagues safely.\n"
        "5. Reporting procedures: employer's complaint mechanism, plus the right to file with "
        "California's Civil Rights Department (formerly DFEH) directly.\n"
        "6. Employer obligations and anti-retaliation protections.\n"
        "7. Abusive conduct (workplace bullying) — required by SB 396.\n"
        "8. Harassment based on gender identity, gender expression, sexual orientation.\n"
        f"{v['extra_coverage']}\n"
        "QUIZ RULES:\n"
        f"- Exactly {quiz_count} questions.\n"
        "- Each question 4 options, exactly one correct.\n"
        f"- At least {scenarios} questions must be scenario-based, not pure knowledge-recall.\n"
        "- Spread the correct-answer letter (A/B/C/D) roughly evenly across the quiz.\n\n"
        "STYLE:\n"
        "- 8th-grade reading level. Active voice. Plain language.\n"
        "- Cite specific California Government Code sections inline where it adds clarity.\n"
        "- Avoid examples that name real companies, real people, or real cases.\n"
        "- No images. Markdown formatting allowed in body_md (headings, lists, bold, italics).\n"
        "- Do NOT include opinions about politics or unrelated commentary.\n"
    )


def validate_payload(parsed: dict, v: dict) -> list[str]:
    """Return a list of validation errors; empty list means valid."""
    errors: list[str] = []
    if not isinstance(parsed, dict):
        return ["payload is not an object"]

    if not parsed.get("title"):
        errors.append("missing title")
    if not parsed.get("summary_for_certificate"):
        errors.append("missing summary_for_certificate")

    sections = parsed.get("sections")
    if not isinstance(sections, list) or len(sections) < 6:
        errors.append(f"sections must be a list with >=6 entries, got {type(sections).__name__}")
    else:
        for i, s in enumerate(sections):
            if not isinstance(s, dict):
                errors.append(f"section[{i}] is not an object")
                continue
            for k in ("id", "title", "body_md"):
                if not s.get(k):
                    errors.append(f"section[{i}] missing {k}")

    quiz = parsed.get("quiz")
    if not isinstance(quiz, dict):
        errors.append("quiz must be an object")
    else:
        questions = quiz.get("questions")
        if not isinstance(questions, list) or len(questions) != v["quiz_count"]:
            errors.append(
                f"quiz.questions must have exactly {v['quiz_count']} entries, "
                f"got {len(questions) if isinstance(questions, list) else 'not-a-list'}"
            )
        else:
            for i, q in enumerate(questions):
                if not isinstance(q, dict):
                    errors.append(f"question[{i}] is not an object")
                    continue
                if not q.get("prompt"):
                    errors.append(f"question[{i}] missing prompt")
                opts = q.get("options")
                if not isinstance(opts, list) or len(opts) != 4:
                    errors.append(f"question[{i}] options must have exactly 4 entries")
                    continue
                keys = [o.get("key") for o in opts if isinstance(o, dict)]
                if sorted(keys) != ["A", "B", "C", "D"]:
                    errors.append(f"question[{i}] options must use keys A,B,C,D")
                if q.get("correct_key") not in {"A", "B", "C", "D"}:
                    errors.append(f"question[{i}] correct_key must be A|B|C|D")
                if not q.get("rationale"):
                    errors.append(f"question[{i}] missing rationale")
    return errors


async def call_gemini(prompt: str, model_name: str) -> dict | None:
    settings = load_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)
    response = await asyncio.wait_for(
        client.aio.models.generate_content(model=model_name, contents=prompt),
        timeout=120,
    )
    raw_text = (getattr(response, "text", None) or "").strip()
    return _extract_json_payload(raw_text)


async def upsert_template(v: dict, payload: dict, model_name: str) -> str:
    """Insert or update the template row. Returns 'inserted' | 'skipped' | 'replaced'."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM training_lesson_templates "
            "WHERE template_key = $1 AND version = $2",
            v["template_key"], VERSION,
        )
        if existing and not FORCE:
            return "skipped"

        if existing and FORCE:
            await conn.execute(
                """
                UPDATE training_lesson_templates
                SET lesson_content = $1::jsonb,
                    quiz = $2::jsonb,
                    title = $3,
                    required_minutes = $4,
                    frequency_months = $5,
                    pass_score_percent = 80,
                    model_used = $6,
                    generated_at = NOW(),
                    is_active = TRUE
                WHERE id = $7
                """,
                json.dumps({
                    "title": payload["title"],
                    "summary_for_certificate": payload.get("summary_for_certificate", ""),
                    "estimated_minutes": payload.get("estimated_minutes", v["required_minutes"]),
                    "sections": payload["sections"],
                }),
                json.dumps(payload["quiz"]),
                payload["title"] or v["title"],
                v["required_minutes"],
                v["frequency_months"],
                model_name,
                existing["id"],
            )
            return "replaced"

        await conn.execute(
            """
            INSERT INTO training_lesson_templates
              (template_key, variant, jurisdiction, training_type, title,
               required_minutes, frequency_months, lesson_content, quiz,
               pass_score_percent, version, model_used, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, 80, $10, $11, TRUE)
            """,
            v["template_key"],
            v["variant"],
            v["jurisdiction"],
            v["training_type"],
            payload["title"] or v["title"],
            v["required_minutes"],
            v["frequency_months"],
            json.dumps({
                "title": payload["title"],
                "summary_for_certificate": payload.get("summary_for_certificate", ""),
                "estimated_minutes": payload.get("estimated_minutes", v["required_minutes"]),
                "sections": payload["sections"],
            }),
            json.dumps(payload["quiz"]),
            VERSION,
            model_name,
        )
        return "inserted"


async def seed_matcha_lite_requirements() -> int:
    """Insert one training_requirements row per (matcha_lite company, active template).

    Idempotent — uses NOT EXISTS so re-running is safe.
    Returns number of rows inserted.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """
            INSERT INTO training_requirements
              (company_id, title, description, training_type, jurisdiction,
               frequency_months, applies_to, template_id, required_minutes,
               pass_score_percent, is_active)
            SELECT c.id,
                   t.title,
                   NULL,
                   t.training_type,
                   t.jurisdiction,
                   t.frequency_months,
                   CASE t.variant
                       WHEN 'supervisor' THEN 'supervisor'
                       ELSE 'nonsupervisor'
                   END,
                   t.id,
                   t.required_minutes,
                   t.pass_score_percent,
                   TRUE
            FROM companies c
            CROSS JOIN training_lesson_templates t
            WHERE c.signup_source = 'matcha_lite'
              AND t.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM training_requirements tr
                  WHERE tr.company_id = c.id
                    AND tr.template_id = t.id
              )
            """
        )
        # asyncpg returns "INSERT 0 N" — parse N
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0


async def main() -> None:
    settings = load_settings()
    model_name = settings.analysis_model or "gemini-2.5-pro"

    await init_db()

    for v in VARIANTS:
        print(f"\n=== Generating {v['template_key']} ({v['required_minutes']} min, "
              f"{v['quiz_count']} quiz Qs) ===")

        # Skip Gemini call if already exists and not forcing
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM training_lesson_templates "
                "WHERE template_key = $1 AND version = $2",
                v["template_key"], VERSION,
            )
        if exists and not FORCE:
            print(f"  exists at version {VERSION} — skipping (use --force to regenerate)")
            continue

        prompt = build_prompt(v)
        print(f"  calling {model_name}…")
        payload = await call_gemini(prompt, model_name)
        if not payload:
            print(f"  FAILED: no JSON returned")
            sys.exit(1)

        errors = validate_payload(payload, v)
        if errors:
            print(f"  FAILED validation:")
            for e in errors:
                print(f"    - {e}")
            sys.exit(2)

        result = await upsert_template(v, payload, model_name)
        print(f"  {result}: {len(payload['sections'])} sections, "
              f"{len(payload['quiz']['questions'])} questions")

    print("\n=== Seeding matcha_lite training_requirements ===")
    seeded = await seed_matcha_lite_requirements()
    print(f"  inserted {seeded} requirement rows")


if __name__ == "__main__":
    asyncio.run(main())
