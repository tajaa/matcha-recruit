"""Schedule-rule extraction — link the schedule-compliance gate to the
ALREADY-CODIFIED compliance catalog, instead of hand-researching states.

`jurisdiction_requirements` already holds researched, cited statute rows for
every state that's been worked (overtime, meal breaks, scheduling/reporting,
minor work permits). What it can't do is drive a deterministic gate directly:
`numeric_value` is semantically overloaded (a meal-break row's `30` is a break
DURATION in minutes; an overtime row's `1.5` is a pay MULTIPLIER) and the
actual trigger condition ("after the 5th hour") lives in prose, not a
structured field. `services/schedule_compliance.py`'s own docstring already
names this as why its curated `_SCHEDULING_RULES` table can't just read the
catalog.

So this module does the ONE-TIME (re-runnable) resolution: feed a state's
codified catalog rows to Gemini, get back structured
`{rule_key, rule_value|no_rule, citation, source_requirement_id}` rows keyed to
the exact fields `schedule_compliance.py`'s evaluators consume, and land them
in `schedule_rule_extractions` as **pending**. Nothing here ever reaches the
write-path gate directly — `services/schedule_compliance.py:rules_for_state`
only reads rows with `review_status='approved'`. This is the load-bearing
invariant repeated everywhere in this codebase's statute tables: an
unconfirmed AI extraction must never drive a verdict.

Two other invariants specific to this module:

- **Approved values are never silently overwritten by a re-run.** A re-run
  that disagrees with an approved row writes to `proposed` + `stale_since` for
  a human to look at — the gate keeps enforcing what was approved until
  someone acts. Only `pending`/`rejected` rows get overwritten in place.
- **Every emitted rule must cite a catalog row the query actually returned.**
  `source_requirement_id` is validated against the id set handed to the model
  — that plus the codified-only fetch is the hallucination guard.

⚠️ Extracted citations are only as good as the catalog rows underneath them —
still researched-not-attorney-reviewed, same posture as every curated statute
table in this codebase.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_MODEL = "gemini-3-flash-preview"

# The 4 catalog categories that carry scheduling law. Deliberately NOT
# `sick_leave` (also in `schedule_compliance.SCHEDULE_CATEGORIES`) — no
# evaluator in this codebase enforces a sick-leave threshold; extracting it
# would create approved rows implying coverage nothing reads.
CATALOG_CATEGORIES = ("overtime", "meal_breaks", "scheduling_reporting", "minor_work_permit")

# States the in-code `_SCHEDULING_RULES` table already curates by hand — the
# hand-authored row is the attorney-facing baseline, so a state present there
# is skipped entirely rather than accumulating a shadow DB copy nothing reads
# (`schedule_compliance.rules_for_state` ignores DB rows for these states; see
# its per-state-precedence rule).
CODE_CURATED_STATES = ("US", "CA")

# Exactly the fields `schedule_compliance.py`'s pure evaluators consume today.
# Extracting a wider vocabulary would produce approved rows no evaluator reads.
RULE_KEYS = (
    "meal_break_after_hours",
    "meal_break_minutes",
    "second_meal_after_hours",
    "daily_ot_hours",
    "daily_doubletime_hours",
    "weekly_ot_hours",
    "min_rest_between_shifts_hours",
    "minor_u16_day_hours",
    "minor_u16_week_hours",
    "minor_16_17_day_hours",
    "minor_16_17_week_hours",
)

# (min, max) sanity bounds per rule_key — a bright-line reasonableness check
# on Gemini's output, not a legal judgment. A value outside these is rejected
# rather than silently landing as a "researched" threshold.
_RANGES: dict[str, tuple[float, float]] = {
    "meal_break_after_hours": (2, 12),
    "meal_break_minutes": (10, 120),
    "second_meal_after_hours": (2, 16),
    "daily_ot_hours": (4, 24),
    "daily_doubletime_hours": (4, 24),
    "weekly_ot_hours": (20, 80),
    "min_rest_between_shifts_hours": (4, 24),
    "minor_u16_day_hours": (3, 12),
    "minor_u16_week_hours": (3, 48),
    "minor_16_17_day_hours": (3, 16),
    "minor_16_17_week_hours": (3, 60),
}

_FIELD_GLOSSARY = """
- meal_break_after_hours: shift length (hours) that TRIGGERS a required meal break.
- meal_break_minutes: the required meal break's DURATION in minutes.
- second_meal_after_hours: shift length (hours) that triggers a SECOND required meal break.
- daily_ot_hours: hours worked in one day after which daily overtime pay is owed.
- daily_doubletime_hours: hours worked in one day after which DOUBLE time pay is owed (omit if the state has no daily double-time rule).
- weekly_ot_hours: hours worked in one week after which weekly overtime pay is owed.
- min_rest_between_shifts_hours: minimum hours of rest required between the end of one shift and the start of the next.
- minor_u16_day_hours / minor_u16_week_hours: daily/weekly hour caps for workers under 16.
- minor_16_17_day_hours / minor_16_17_week_hours: daily/weekly hour caps for 16-17 year olds.
""".strip()


# ── Pure validation ──────────────────────────────────────────────────────

def validate_extraction(
    payload: dict[str, Any], allowed_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a parsed Gemini response into (valid_rows, rejected).

    Pure — no DB, no network. `allowed_ids` is the set of catalog requirement
    ids actually handed to the model for this state; a `source_requirement_id`
    outside that set is a hallucination and the row is rejected outright, not
    down-weighted.
    """
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in (payload or {}).get("rules") or []:
        if not isinstance(raw, dict):
            rejected.append({"row": raw, "reason": "not_an_object"})
            continue

        rule_key = raw.get("rule_key")
        if rule_key not in RULE_KEYS:
            rejected.append({"row": raw, "reason": "unknown_rule_key"})
            continue

        source_id = raw.get("source_requirement_id")
        if not source_id or str(source_id) not in allowed_ids:
            rejected.append({"row": raw, "reason": "unverifiable_source_requirement_id"})
            continue

        citation = (raw.get("citation") or "").strip()
        if not citation:
            rejected.append({"row": raw, "reason": "missing_citation"})
            continue

        no_rule = bool(raw.get("no_rule"))
        rule_value = raw.get("rule_value")
        if no_rule and rule_value is not None:
            rejected.append({"row": raw, "reason": "no_rule_and_value_both_set"})
            continue
        if not no_rule and rule_value is None:
            rejected.append({"row": raw, "reason": "no_value_and_not_no_rule"})
            continue

        if rule_value is not None:
            try:
                value = float(rule_value)
            except (TypeError, ValueError):
                rejected.append({"row": raw, "reason": "non_numeric_value"})
                continue
            lo, hi = _RANGES[rule_key]
            if not (lo <= value <= hi):
                rejected.append({"row": raw, "reason": "value_out_of_range"})
                continue
            rule_value = value

        valid.append({
            "rule_key": rule_key,
            "rule_value": rule_value,
            "no_rule": no_rule,
            "citation": citation,
            "source_requirement_id": str(source_id),
            "confidence": raw.get("confidence"),
            "rationale": raw.get("rationale"),
        })

    return valid, rejected


def decide_upsert(existing: Optional[dict[str, Any]], new: dict[str, Any]) -> dict[str, Any]:
    """What to do with one extracted row against whatever's already stored.

    Pure. `existing` is `{review_status, rule_value, no_rule, citation}` or
    None; `new` is a validated row from `validate_extraction`.

    - No existing row → insert pending.
    - Existing pending/rejected → overwrite in place, back to pending (a
      rejected row gets a fresh look on re-extraction rather than staying
      permanently rejected against stale data).
    - Existing approved, values match → no-op (nothing for a human to see).
    - Existing approved, values differ → the enforced row is untouched; the
      new values land in `proposed` for review.
    """
    if existing is None:
        return {"action": "insert"}
    if existing["review_status"] in ("pending", "rejected"):
        return {"action": "overwrite_pending"}
    # approved
    same = (
        existing.get("rule_value") == new.get("rule_value")
        and existing.get("no_rule") == new.get("no_rule")
        and existing.get("citation") == new.get("citation")
    )
    return {"action": "noop"} if same else {"action": "set_proposed"}


# ── DB-touching orchestration ────────────────────────────────────────────

def _build_prompt(state: str, rows: list[dict[str, Any]]) -> str:
    catalog_json = json.dumps([
        {
            "id": str(r["id"]),
            "category": r["category"],
            "requirement_key": r["requirement_key"],
            "title": r["title"],
            "description": r.get("description"),
            "current_value": r.get("current_value"),
            "numeric_value": float(r["numeric_value"]) if r.get("numeric_value") is not None else None,
            "statute_citation": r.get("statute_citation"),
        }
        for r in rows
    ], indent=2)

    return f"""You are a labor-law compliance expert extracting SCHEDULING thresholds from an
already-researched catalog of state labor-law requirements. You must extract ONLY
what these rows state — do not add outside knowledge, do not infer from silence.

STATE: {state}

CATALOG ROWS (each has a real "id" — you MUST cite the exact id whose
title/description/numeric_value/current_value supports each rule you emit):
{catalog_json}

FIELD GLOSSARY (extract a value ONLY for fields these rows actually address):
{_FIELD_GLOSSARY}

For each field you can support from the rows above, return one entry:
{{
  "rule_key": "<one of the glossary keys>",
  "rule_value": <number, or null if no_rule is true>,
  "no_rule": <true ONLY if a row explicitly states this state imposes NO such
              limit — never set this from silence; if a row is simply silent
              on a field, OMIT that field entirely>,
  "source_requirement_id": "<the exact id of the row that supports this>",
  "citation": "<the statute citation from that row>",
  "confidence": <0.0-1.0>,
  "rationale": "<briefly quote the part of the row that states the trigger/value>"
}}

Do NOT fabricate a rule for a field the rows don't address — omit it.
Do NOT use a row's numeric_value for the wrong purpose (a meal-break row's
number is a DURATION in minutes or a trigger in hours depending on which
field it supports — read the description/title to tell which).

Return ONLY a JSON object: {{"rules": [...]}}"""


async def extract_state_rules(
    conn, state: str, *, triggered_by: Optional[UUID] = None
) -> dict[str, Any]:
    """Run extraction for one state. Idempotent to re-run (see `decide_upsert`).

    Returns `{status, requirement_count, extracted_count, rejected_count}`.
    `status` is `"skipped_curated"` for US/CA (never touched — the in-code
    table is authoritative for them), `"empty"` when the catalog has no
    codified scheduling rows for this state yet (not a failure — there is
    simply nothing to extract, and the state stays "not researched" for the
    gate, same as today), `"complete"`, or `"failed"`.
    """
    state = (state or "").strip().upper()
    if state in CODE_CURATED_STATES:
        return {"status": "skipped_curated", "requirement_count": 0,
                "extracted_count": 0, "rejected_count": 0}

    run_id = await conn.fetchval(
        """
        INSERT INTO schedule_rule_extraction_runs (state, status, ai_model, triggered_by)
        VALUES ($1, 'running', $2, $3)
        RETURNING id
        """,
        state, _MODEL, triggered_by,
    )

    try:
        from app.core.services.scope_registry.codify import codified_sql

        rows = [dict(r) for r in await conn.fetch(
            f"""
            SELECT jr.id, jr.requirement_key, jr.category, jr.title, jr.description,
                   jr.current_value, jr.numeric_value, jr.statute_citation
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE j.state = $1
              AND jr.status = 'active'
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
              AND jr.category = ANY($2::varchar[])
              AND (jr.applicable_industries IS NULL OR jr.applicable_industries = '{{}}')
              AND {codified_sql("jr")}
            """,
            state, list(CATALOG_CATEGORIES),
        )]

        if not rows:
            await conn.execute(
                """
                UPDATE schedule_rule_extraction_runs
                SET status = 'empty', requirement_count = 0, completed_at = NOW()
                WHERE id = $1
                """,
                run_id,
            )
            return {"status": "empty", "requirement_count": 0,
                    "extracted_count": 0, "rejected_count": 0}

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

        from google.genai import types
        from app.core.services.genai_client import get_genai_client

        client = get_genai_client(api_key=api_key)
        response = client.models.generate_content(
            model=_MODEL,
            contents=[types.Content(parts=[types.Part.from_text(text=_build_prompt(state, rows))])],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=4096),
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        payload = json.loads(text.strip())

        allowed_ids = {str(r["id"]) for r in rows}
        valid, rejected = validate_extraction(payload, allowed_ids)
        source_by_id = {str(r["id"]): r for r in rows}

        for row in valid:
            await _upsert_extraction(conn, state, row, run_id, source_by_id[row["source_requirement_id"]])

        await conn.execute(
            """
            UPDATE schedule_rule_extraction_runs
            SET status = 'complete', requirement_count = $1, extracted_count = $2, completed_at = NOW()
            WHERE id = $3
            """,
            len(rows), len(valid), run_id,
        )
        if rejected:
            logger.warning("schedule_rule_extraction: %s rejected row(s) for %s: %s",
                            len(rejected), state, [r["reason"] for r in rejected])
        return {"status": "complete", "requirement_count": len(rows),
                "extracted_count": len(valid), "rejected_count": len(rejected)}

    except Exception as exc:  # noqa: BLE001
        logger.exception("schedule_rule_extraction failed for %s", state)
        await conn.execute(
            """
            UPDATE schedule_rule_extraction_runs
            SET status = 'failed', error_message = $1, completed_at = NOW()
            WHERE id = $2
            """,
            str(exc), run_id,
        )
        return {"status": "failed", "requirement_count": 0,
                "extracted_count": 0, "rejected_count": 0}


async def run_sweep(states: list[str], *, triggered_by: Optional[UUID] = None) -> dict[str, Any]:
    """Extract every state in `states` (default: all US states minus the
    in-code-curated ones), one at a time.

    Runs as a FastAPI `BackgroundTasks` job from the admin trigger route, not
    Celery: this is an on-demand admin action (not a scheduled/periodic
    sweep), and each state's extraction is a single Gemini call plus a few
    queries — `BackgroundTasks` already detaches it from the response, and the
    per-state `try/except` in `extract_state_rules` means one state's failure
    (or a mid-sweep server restart) never corrupts another's already-committed
    rows. Opens a fresh connection per state (not one held for the whole
    sweep) — each state's Gemini call can take several seconds, and holding a
    pooled connection idle across all of them would starve the pool for
    concurrent request traffic during a sweep.
    """
    from app.database import get_connection

    results: dict[str, str] = {}
    for state in states:
        async with get_connection() as conn:
            outcome = await extract_state_rules(conn, state, triggered_by=triggered_by)
        results[state] = outcome["status"]
    return results


async def _upsert_extraction(
    conn, state: str, row: dict[str, Any], run_id: UUID, source_row: dict[str, Any]
) -> None:
    existing = await conn.fetchrow(
        """
        SELECT review_status, rule_value, no_rule, citation
        FROM schedule_rule_extractions WHERE state = $1 AND rule_key = $2
        """,
        state, row["rule_key"],
    )
    decision = decide_upsert(dict(existing) if existing else None, row)
    snapshot = json.dumps({
        "title": source_row.get("title"),
        "description": source_row.get("description"),
        "requirement_key": source_row.get("requirement_key"),
    })
    rule_value = Decimal(str(row["rule_value"])) if row["rule_value"] is not None else None

    if decision["action"] == "insert":
        await conn.execute(
            """
            INSERT INTO schedule_rule_extractions
                (state, rule_key, rule_value, no_rule, citation, source_requirement_id,
                 source_snapshot, extraction_run_id, ai_confidence, ai_rationale, review_status)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,'pending')
            """,
            state, row["rule_key"], rule_value, row["no_rule"], row["citation"],
            UUID(row["source_requirement_id"]), snapshot, run_id,
            row.get("confidence"), row.get("rationale"),
        )
    elif decision["action"] == "overwrite_pending":
        await conn.execute(
            """
            UPDATE schedule_rule_extractions SET
                rule_value = $3, no_rule = $4, citation = $5, source_requirement_id = $6,
                source_snapshot = $7::jsonb, extraction_run_id = $8, ai_confidence = $9,
                ai_rationale = $10, review_status = 'pending', proposed = NULL,
                stale_since = NULL, updated_at = NOW()
            WHERE state = $1 AND rule_key = $2
            """,
            state, row["rule_key"], rule_value, row["no_rule"], row["citation"],
            UUID(row["source_requirement_id"]), snapshot, run_id,
            row.get("confidence"), row.get("rationale"),
        )
    elif decision["action"] == "set_proposed":
        proposed = json.dumps({
            "rule_value": row["rule_value"], "no_rule": row["no_rule"], "citation": row["citation"],
            "source_requirement_id": row["source_requirement_id"],
        })
        await conn.execute(
            """
            UPDATE schedule_rule_extractions
            SET proposed = $3::jsonb, stale_since = COALESCE(stale_since, NOW()), updated_at = NOW()
            WHERE state = $1 AND rule_key = $2
            """,
            state, row["rule_key"], proposed,
        )
    # "noop": nothing to write
