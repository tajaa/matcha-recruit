"""Review of a manager-written corrective-action letter.

Four layers, in order of authority:

1. **Protected-leave gate** — `discipline_compliance.check_discipline_compliance`
   (deterministic, cited statutes; reused as a library). A block means the
   draft cannot go to HR approval as written. No override.
2. **Ladder fit** — deterministic, against this employee's earlier HR cases
   (the retired discipline tables are not consulted).
3. **Letter structure** — deterministic: does it name the employee, give a
   date, describe the conduct, state the expectation and consequence, and
   carry an acknowledgment/signature block.
4. **Writing risk** — one Gemini pass of this module's own (`ai_wording_review`),
   grounded on the incident account and the policies triage matched. It does
   NOT use `discipline_ai`, whose corpus build seeds rows into the retired
   `discipline_policy_mapping` table. An outage degrades to one advisory; the
   gate above already ran without it.

The model never decides legality.

**Two audiences.** HR sees the whole review. The manager sees
`for_manager(review)`: letter-structure notes only, and a block collapsed to
"HR needs to look at this" — a block names which protected leave overlapped,
which is not the manager's to know.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from uuid import UUID

INFRACTION_TYPES = ("attendance", "performance", "conduct", "safety", "policy_violation")
LEVEL_RANK = {"verbal_warning": 1, "written_warning": 2, "pip": 2, "final_warning": 3, "suspension": 3}
_LEVEL_LABEL = {
    "verbal_warning": "verbal warning", "written_warning": "written warning", "pip": "PIP",
    "final_warning": "final warning", "suspension": "suspension", "other": "other action",
}
LADDER_LOOKBACK_DAYS = 365
MIN_WORDS = 60

_EXPECTATION = re.compile(
    r"\b(expect(?:ed|ation|s)?|going forward|moving forward|in the future|must|required to|will need to|improv\w*)\b", re.I,
)
_CONSEQUENCE = re.compile(
    r"\b(further (?:disciplinary|corrective) action|termination|next step|consequence\w*|up to and including)\b", re.I,
)
_SIGNATURE = re.compile(r"\b(signature|signed|sign(?:ing)? below|acknowledg\w*)\b", re.I)
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_ANY_DATE = re.compile(
    rf"\b(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?)\b", re.I,
)


def _advisory(source: str, code: str, detail: str) -> dict[str, str]:
    return {"source": source, "code": code, "detail": detail}


def check_structure(text: str, *, employee_name: Optional[str], occurrence_dates: Iterable[date] = ()) -> list[dict]:
    """Pure. What a corrective-action letter is missing."""
    text = text or ""
    out: list[dict] = []
    name = (employee_name or "").strip()
    if name:
        parts = [p for p in re.split(r"\s+", name) if len(p) > 1]
        if not any(re.search(rf"\b{re.escape(p)}\b", text, re.I) for p in parts):
            out.append(_advisory("structure", "missing_employee_name", f"The letter never names {name}."))
    if not _ANY_DATE.search(text):
        dates = ", ".join(d.isoformat() for d in occurrence_dates) if occurrence_dates else ""
        out.append(_advisory(
            "structure", "missing_date",
            "The letter doesn't say when the conduct happened" + (f" ({dates})." if dates else "."),
        ))
    if len(re.findall(r"\w+", text)) < MIN_WORDS:
        out.append(_advisory("structure", "too_short", "The letter is very short — describe what happened specifically."))
    if not _EXPECTATION.search(text):
        out.append(_advisory("structure", "missing_expectation", "The letter doesn't say what's expected going forward."))
    if not _CONSEQUENCE.search(text):
        out.append(_advisory("structure", "missing_consequence", "The letter doesn't say what happens if it continues."))
    if not _SIGNATURE.search(text):
        out.append(_advisory("structure", "missing_signature_block", "There's no acknowledgment or signature line for the employee."))
    return out


def ladder_advisories(action_type: str, prior: Iterable[tuple[str, Any]]) -> list[dict]:
    """Pure. `prior` = (action_type, when) for this employee's recent
    delivered/closed HR cases."""
    rank = LEVEL_RANK.get(action_type)
    if rank is None:
        return []
    prior_ranks = [LEVEL_RANK[a] for a, _ in prior if a in LEVEL_RANK]
    top = max(prior_ranks, default=0)
    label = _LEVEL_LABEL.get(action_type, action_type)
    if rank > top + 1:
        return [_advisory(
            "ladder", "skips_step",
            f"A {label} skips a step: " + ("there's no earlier warning on file in the last year."
                                           if not prior_ranks else "the most recent action on file is lower."),
        )]
    if prior_ranks and rank <= top:
        return [_advisory(
            "ladder", "repeats_level",
            f"There's already a {label} or higher on file in the last year — consider the next step up.",
        )]
    return []


_AI_RULES = """You are reviewing a corrective-action letter a manager wrote, for LEGAL RISK IN
THE WRITING. You are not deciding whether discipline is lawful or deserved; a
separate deterministic check handles protected leave. Flag only concrete,
fixable problems in THIS letter:
- It treats protected activity (taking leave, making a complaint, reporting an
  incident or injury) as misconduct or as part of the pattern.
- It states facts that aren't in the incident account below.
- The expectation going forward is vague, unmeasurable, or impossible.
- The tone attacks the person rather than describing conduct.
- The stated basis doesn't support the level of action chosen.
Say nothing if the letter is clean — an advisory nobody needs trains HR to
click past the one that matters. At most 5.

Return STRICT JSON, no markdown fence:
{"advisories": [{"detail": "<the specific problem and how to fix it>"}]}
"""

_AI_TIMEOUT = 45
_AI_TEXT_CAP = 12_000


async def ai_wording_review(
    *, text: str, action_type: str, infraction_type: str,
    incident_account: Optional[str], policy_titles: Iterable[str],
) -> list[dict]:
    """One grounded wording pass. Never raises: an outage is one advisory."""
    import asyncio

    from app.core.services.ai_usage import feature_scope
    from app.core.services.model_catalog import GEMINI_FLASH
    from app.matcha.services._shared.citations import _parse_json
    from app.matcha.services._shared.gemini import _genai

    policies = "; ".join(p for p in policy_titles if p) or "(none matched)"
    prompt = (
        f"ACTION: {_LEVEL_LABEL.get(action_type, action_type)} | infraction: {infraction_type.replace('_', ' ')}\n"
        f"POLICIES THE INCIDENT MAY INVOLVE: {policies}\n\n"
        f"INCIDENT ACCOUNT (what was reported):\n{(incident_account or '(no incident on file)')[:_AI_TEXT_CAP]}\n\n"
        f"THE LETTER:\n{(text or '')[:_AI_TEXT_CAP]}\n\n{_AI_RULES}"
    )
    try:
        with feature_scope("matcha.hr_cases.draft_review"):
            resp = await asyncio.wait_for(
                _genai().aio.models.generate_content(model=GEMINI_FLASH, contents=prompt),
                timeout=_AI_TIMEOUT,
            )
        data = _parse_json(getattr(resp, "text", "") or "")
    except Exception:
        return [_advisory(
            "ai", "ai_review_unavailable",
            "The AI wording review couldn't run. The protected-leave check did run and its result stands.",
        )]
    raw = data.get("advisories") if isinstance(data, dict) else None
    out = []
    for item in (raw or [])[:5]:
        detail = str(item.get("detail") or "").strip() if isinstance(item, dict) else ""
        if detail:
            out.append(_advisory("ai", "ai_review", detail[:600]))
    return out


async def _prior_actions(conn, *, company_id: UUID, employee_id: UUID, exclude_case_id: Optional[UUID]) -> list[tuple[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=LADDER_LOOKBACK_DAYS)
    rows = await conn.fetch(
        """
        SELECT action_type, delivered_at FROM hr_cases
        WHERE company_id = $1 AND employee_id = $2 AND action_type IS NOT NULL
          AND delivered_at IS NOT NULL AND delivered_at > $3
          AND ($4::uuid IS NULL OR id <> $4)
        """,
        company_id, employee_id, since, exclude_case_id,
    )
    return [(r["action_type"], r["delivered_at"]) for r in rows]


async def review_draft(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    employee_name: Optional[str],
    text: str,
    action_type: str,
    infraction_type: str,
    occurrence_dates: list[date],
    case_id: Optional[UUID] = None,
    incident_account: Optional[str] = None,
    policy_titles: Iterable[str] = (),
    run_ai: bool = True,
) -> dict[str, Any]:
    from app.matcha.services.discipline.discipline_compliance import check_discipline_compliance

    verdict = await check_discipline_compliance(
        conn, company_id=company_id, employee_id=employee_id,
        infraction_type=infraction_type, occurrence_dates=occurrence_dates,
    )
    advisories: list[dict] = [
        _advisory("compliance", a.get("code") or "compliance", a.get("detail") or "")
        for a in verdict.get("advisories") or []
    ]
    prior = await _prior_actions(conn, company_id=company_id, employee_id=employee_id, exclude_case_id=case_id)
    advisories += ladder_advisories(action_type, prior)
    advisories += check_structure(text, employee_name=employee_name, occurrence_dates=occurrence_dates)

    if run_ai and not verdict.get("blocks"):
        advisories += await ai_wording_review(
            text=text, action_type=action_type, infraction_type=infraction_type,
            incident_account=incident_account, policy_titles=policy_titles,
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "blocks": [
            {"source": "compliance", "code": b.get("code"), "detail": b.get("detail"), "statute": b.get("statute")}
            for b in verdict.get("blocks") or []
        ],
        "advisories": advisories,
        "compliance": verdict,
        "text_chars": len(text or ""),
    }


def for_manager(review: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The manager's view of a review: structure notes only, blocks collapsed."""
    if not review:
        return None
    held = bool(review.get("blocks"))
    return {
        "held_for_hr": held,
        "message": (
            "This write-up can't go forward as written. HR has been told and will follow up with you."
            if held else None
        ),
        "notes": [
            {"code": a["code"], "detail": a["detail"]}
            for a in review.get("advisories") or [] if a.get("source") == "structure"
        ],
    }
