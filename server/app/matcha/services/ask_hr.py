"""Employee "Ask HR" — grounded, citation-gated policy answers for employees.

The employee-facing counterpart to HR Pilot. Same company corpus
(`services/hr_pilot_corpus.py`), same anti-hallucination gate
(`legal_defense.validate_citations`), same deterministic hard-stop classifier
(`services/hr_pilot_escalation.classify_message`) — but a different reader, and
the differences matter:

- **Different voice.** HR Pilot coaches a supervisor on how to handle someone
  else. Ask HR answers an employee about their own situation, in plain language,
  with no management framing ("document this", "consider progressive
  discipline") leaking across.
- **No actions.** HR Pilot can stage a discipline draft through the skill engine.
  Ask HR has no action vocabulary at all — it answers questions and nothing else.
- **The hard stop is heavier here.** When a supervisor asks about harassment they
  are usually asking how to handle a report. When an employee does, they may BE
  the report. So the gate runs first, the answer is refused, and the escalation
  is filed automatically rather than offered — see `should_refuse`.

Answers are generated whole and gated before anything is persisted or shown, in
the style of the other grounded pilots ("groundedness over token-streaming" —
`legal_defense.run_chat_turn`).
"""

import asyncio
import logging

from app.core.services.genai_client import get_genai_client

from .hr_pilot_escalation import EMPLOYEE, classify_message
from .legal_defense import _parse_json, validate_citations

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 60
_HISTORY_TURNS = 10

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


# --------------------------------------------------------------------------- #
# The hard stop — pure, runs before any model call.
# --------------------------------------------------------------------------- #

# What the employee is told when a question is refused. Deliberately does NOT
# repeat their words back (the reply is persisted and may be read over their
# shoulder on a shared terminal), and deliberately DOES tell them HR was
# notified: filing on their behalf without saying so would be a surprise at
# exactly the moment trust matters most.
_REFUSAL = (
    "This is something the HR team should handle directly with you, so I'm not going "
    "to try to answer it here.\n\n"
    "I've let your HR team know you raised it — someone will follow up with you. "
    "Nothing you wrote has been shared with your manager or your coworkers.\n\n"
    "If this is an emergency, or someone is in immediate danger, contact emergency "
    "services first."
)


def should_refuse(text: str):
    """Classify an employee question. Returns the shared `EscalationVerdict`.

    Same four categories as the supervisor path — they are exactly the ones an
    employee must reach a human about — but run against the EMPLOYEE pattern
    set, which adds first-person phrasing ("he keeps touching me", "I slipped on
    the wet floor") that the supervisor vocabulary misses entirely. Those extra
    patterns are employee-only on purpose; see `_EMPLOYEE_EXTRA_PATTERNS`."""
    return classify_message(text or "", surface=EMPLOYEE)


def refusal_message(_verdict) -> str:
    """The refusal shown to the employee. Category-independent on purpose: the
    four categories map to one action (a person follows up), and naming the
    category back at them ("this looks like a harassment matter") both presumes
    on a keyword match and makes the reply awkward to have on screen."""
    return _REFUSAL


# --------------------------------------------------------------------------- #
# Grounded answer turn
# --------------------------------------------------------------------------- #

_SYSTEM = """You are an HR assistant answering an EMPLOYEE's question about their own workplace, using only their employer's own written material.

WHO YOU ARE TALKING TO: an employee, about their own situation. Not a manager, not HR staff. Write in plain, direct, second-person language ("you get", "your manager should"). Never coach them on managing, disciplining, documenting, or evaluating another person — that is not their job and not what they asked.

HARD RULES:
- Answer ONLY from the SOURCE RECORDS below. Cite the bracketed ID of every record you rely on, copied exactly (e.g. [policy:8f3c...]).
- NEVER invent a policy, a number, a deadline, or an ID. An ID that is not in the list below is stripped out before the employee sees your answer, leaving your claim visibly unsupported.
- If the records do not answer the question, say so plainly and tell them to ask their HR team. Do not guess, and do not fill the gap with what is typical elsewhere.
- Order of authority: (1) the company's own handbook/policy, (2) the legal floor as the minimum the law requires, (3) the industry baseline ONLY where the company's material is silent — and say when you are doing that.
- You are NOT giving legal advice. Do not tell them what they are legally entitled to beyond what the records state, and do not assess whether the company has complied with anything.
- Be brief. Two or three short paragraphs at most.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your reply to the employee, with [cid] markers inline>",
 "evidence_map": [{"point": "<a claim you made>", "cited_ids": ["<cid>", ...]}],
 "cannot_answer": <true if the records do not cover the question>,
 "open_questions": ["<what they should ask HR directly>"]}"""


def _corpus_text(corpus: dict) -> str:
    out = []
    for key, source in (corpus.get("sources") or {}).items():
        records = source.get("records") or []
        if not records:
            continue
        out.append(f"## {source.get('label') or key} ({key})")
        for r in records:
            out.append(f"- [{r['cid']}] ({r.get('when') or 'current'}) {r.get('summary') or ''}")
    return "\n".join(out) or "(the company has no handbook or policy material on file)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def build_prompt(employee: dict, history: list[dict], corpus: dict, latest: str) -> str:
    """Pure — unit-tested. The employee's own attributes are included because a
    grounded answer often depends on them (their state's leave floor, their
    location's posting rules); nothing about any OTHER employee is ever in
    scope."""
    employee = employee or {}
    where = ", ".join(
        str(v) for v in (employee.get("work_state"), employee.get("work_location_name")) if v
    ) or "(not on file)"
    return f"""{_SYSTEM}

WHO IS ASKING
Job title: {employee.get('job_title') or '(not on file)'}
Works in: {where}

SOURCE RECORDS (the ONLY things you may cite):
{_corpus_text(corpus)}

CONVERSATION (oldest first):
{_history_text(history)}

LATEST QUESTION FROM THE EMPLOYEE:
{latest}
"""


async def _generate(employee: dict, history: list[dict], corpus: dict, latest: str) -> dict:
    prompt = build_prompt(employee, history, corpus, latest)
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(model=MODEL, contents=prompt),
        timeout=_GEMINI_TIMEOUT,
    )
    data = _parse_json(getattr(resp, "text", "") or "")
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "evidence_map": data.get("evidence_map") or [],
        "cannot_answer": bool(data.get("cannot_answer")),
        "open_questions": [str(q) for q in (data.get("open_questions") or []) if q],
    }


async def run_ask_hr_turn(employee: dict, history: list[dict], corpus: dict, latest: str):
    """Async generator of SSE-shaped dicts for one grounded Ask HR turn.

    Yields a status tick, then a single validated ``result``. The hard-stop gate
    is NOT here — it runs in the route, before this is ever called, because a
    refused question must never reach a model at all."""
    yield {"type": "status", "message": "Checking your company's handbook and policies…"}
    try:
        result = await _generate(employee, history, corpus, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "That took too long — please try again."}
        return
    except Exception:
        logger.exception("ask_hr: turn failed")
        yield {"type": "error", "message": "Something went wrong — please try again."}
        return

    index = (corpus or {}).get("index") or {}
    clean_map, dropped = validate_citations(result.get("evidence_map"), index)
    result["evidence_map"] = clean_map

    # The narrative text carries the citations the employee actually sees, so it
    # gets the same treatment as the structured map — the map alone being clean
    # would still leave an invented [cid] rendered mid-sentence.
    from .hr_pilot_corpus import audit_citations
    clean_text, citations, text_dropped = audit_citations(result["assistant_text"], index)
    result["assistant_text"] = clean_text
    result["citations"] = citations
    all_dropped = list(dict.fromkeys([*dropped, *text_dropped]))
    if all_dropped:
        result["dropped_citations"] = all_dropped
        logger.info("ask_hr: dropped %d uncorroborated citation(s)", len(all_dropped))

    if not result["assistant_text"]:
        result["assistant_text"] = (
            "I couldn't find anything in your company's handbook or policies that answers "
            "that. Your HR team can tell you directly — it's worth asking them."
        )
    yield {"type": "result", "data": result}
