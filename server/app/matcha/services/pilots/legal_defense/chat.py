"""Grounded AI turn (organizer, not advocate) — prompt build, intake gaps,
citation validation, and the SSE chat generator."""

import asyncio
import logging

from ..._shared.citations import validate_citations  # noqa: F401 — re-export, see Stage 6
from ..._shared.text import history_text
from ._shared import (
    _GEMINI_TIMEOUT,
    _HISTORY_TURNS,
    _MAX_INTAKE_REQUESTS,
    MODEL,
    _genai,
    _parse_json,
)
from .gather import _SOURCES

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Grounded AI turn (organizer, not advocate)
# --------------------------------------------------------------------------- #

_SYSTEM = """You are a litigation-readiness analyst helping an employer prepare to hand its OUTSIDE COUNSEL an organized factual record. You are NOT a lawyer.

Your job is to ORGANIZE and SURFACE what the company's own system records show, in relation to the matter — so counsel can do the legal analysis efficiently.

HARD RULES:
- You are an ORGANIZER, NOT AN ADVOCATE. Do NOT argue the company is right, do NOT opine on liability, fault, or who will win, and do NOT render conclusions. State what the records show; let counsel draw conclusions.
- Cite ONLY the bracketed record IDs (e.g. [incident:<uuid>]) that appear in the EVIDENCE CORPUS below. NEVER invent a record, fact, date, name, or ID.
- Where the records DO NOT address a point, say so plainly and put it under open_questions — never speculate or fill gaps.
- Be neutral, precise, and specific. Tie each observation to the records that support it.
- This is not legal advice; frame everything for attorney review.
- Employee-linked history carries its own IDs: `leave:` (leave of absence — type, status and dates only; the stated reason is deliberately not in the record), `charge:` (a charge filed with an agency such as the EEOC, NLRB or OSHA), `preterm:` (a pre-termination risk review run before a separation), `separation:` (a separation agreement, including its ADEA/OWBPA consideration and revocation windows), and `ptclaim:` (a claim filed after separation). Report what each shows and its dates; NEVER infer motive, causation, or retaliation from the sequence — chronology is for counsel to interpret.
- Employment-practices registers carry their own IDs and are the company's record of its OWN diligence: `payequity:` (a pay-equity study), `aiaudit:` (a bias audit of an AI hiring tool), `paytransp:` (per-state pay-transparency posting status), and `biometric:` (a biometric/BIPA collection point and whether consent was recorded). Report what each shows and its date. Two rules: NEVER merge a measured "adjusted pay gap" with a "pay-dispersion screen" percentage — they are different measurements and the record says which it is; and an absent audit, missing consent, or overdue study is a GAP IN THE RECORD to raise under open_questions, never a statement that the company violated anything.
- Records with `law:`, `bill:`, or `case:` IDs are LEGAL CONTEXT (governing requirements, pending legislation, externally researched case law) — they describe the legal landscape, NOT the company's conduct. You may cite them to identify which requirements or authorities appear relevant. NEVER conclude the company complied with or violated anything, and NEVER present a `case:` record as precedent analysis — flag it for counsel to evaluate.

INTAKE FIRST — build the case file before you analyze it:
- A matter usually opens before its record is complete. When material listed under MATERIAL NOT YET IN THE RECORD is still missing, spend the turn ASKING THE ADMIN for it instead of concluding. Ask conversationally, in plain language, for what would actually change the picture — name the document or fact, and say briefly why it matters.
- Ask in small batches: AT MOST 3 requests in a turn. Prefer the ones that matter most for this matter type.
- On a turn where you are still gathering, set "ready_for_analysis": false and return "evidence_map": [] and "open_questions": [] — an empty record produces no observations. Put your questions in "intake_requests".
- ADVANCE, never loop. Do NOT ask for the same item twice. If the admin supplies it, says they do not have it, declines, or asks you to proceed anyway, set "ready_for_analysis": true and analyze what exists — then record the still-missing item under "open_questions" for counsel.
- When the corpus is already substantive, or the conversation has resolved the gaps, set "ready_for_analysis": true and produce the analysis. Do not manufacture an intake round on a matter that is already well documented.
- "intake_requests" is addressed to the ADMIN (things they can go get). "open_questions" is addressed to COUNSEL (what the assembled record does not establish). Never mix them.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your neutral, conversational reply to the user>",
 "ready_for_analysis": true|false,
 "intake_requests": ["<a specific document or fact to ask the ADMIN to provide>"],
 "evidence_map": [{"point": "<a factual observation grounded in the records>", "cited_ids": ["<source:uuid>", ...]}],
 "open_questions": ["<what the records do NOT establish / what counsel should clarify>"]}"""


# Corpus sources a matter type would normally draw on. Used only to ask the
# admin better questions — never to assert a record is absent (a source key can
# be missing from the corpus because the feature is off, the query failed, or
# the window/subject filter excluded it; see _intake_source_gaps).
_MATTER_TYPE_EXPECTED: dict[str, tuple[str, ...]] = {
    "eeoc_charge": ("policy_ack", "training", "er_cases", "discipline", "pay_equity"),
    "single_plaintiff": ("er_cases", "discipline", "policy_ack"),
    "class_action": ("discipline", "policy_ack", "compliance", "pay_equity"),
    "subpoena": ("er_cases", "incidents"),
    "audit": ("compliance", "training", "policy_ack"),
    "other": ("er_cases", "policy_ack"),
}


def _intake_source_gaps(matter: dict, corpus: dict) -> list[dict]:
    """Expected-but-empty evidence sources for this matter type.

    A source is only a gap when the company actually RUNS it: ``gather_evidence``
    omits a key when the feature is disabled, when the query errored, and when it
    simply returned nothing — three very different things that look identical in
    ``corpus["sources"]``. Asking an employer without the training feature to go
    find training records is noise, so anything not enabled is skipped here.
    """
    features = corpus.get("features") or {}
    enabled_for = {key: pred for key, _label, _fn, pred in _SOURCES}
    labels = {key: label for key, label, _fn, _pred in _SOURCES}
    sources = corpus.get("sources") or {}
    out = []
    for key in _MATTER_TYPE_EXPECTED.get(matter.get("matter_type") or "other", ()):
        pred = enabled_for.get(key)
        if pred is None or not pred(features):
            continue
        if sources.get(key, {}).get("records"):
            continue
        out.append({"key": key, "label": labels.get(key, key)})
    return out


def intake_gaps(matter: dict, corpus: dict) -> list[dict]:
    """What the case file is still missing — matter facts plus empty sources.

    Pure function (unit-tested): reads only the matter dict and the already
    assembled corpus, so it costs no queries and no latency on the chat turn.
    Returns ``[{"key", "label"}]``.

    This is a prompt-context signal for asking better questions. It is NOT a
    finding of absence and must never be rendered as one — see the wording in
    ``_intake_text``.
    """
    gaps: list[dict] = []
    if not (matter.get("allegation") or "").strip():
        gaps.append({"key": "allegation", "label": "What is actually being alleged or claimed"})
    if not (matter.get("defense_theory") or "").strip():
        gaps.append({"key": "context", "label": "The company's account of what happened"})
    if not matter.get("evidence_start") and not matter.get("evidence_end"):
        gaps.append({"key": "window", "label": "The relevant time period for evidence"})
    if not ((corpus.get("legal_context") or {}).get("chain")):
        gaps.append({"key": "jurisdiction", "label": "Governing jurisdiction (work location or state)"})
    gaps.extend(_intake_source_gaps(matter, corpus))
    return gaps


def _corpus_text(corpus: dict) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")
    return "\n".join(out) or "(no records found in the selected scope)"


def _history_text(history: list[dict]) -> str:
    return history_text(history, _HISTORY_TURNS)


def _scope_text(corpus: dict) -> str:
    """What the corpus was narrowed by. Without this the model reads a filtered
    corpus as a factual finding ("the company logged no safety incidents") —
    which is false and, in a memo handed to counsel, dangerous.

    ``notes`` already carries every narrowing fact (subject, location, window,
    subsystems not in use), so this renders them rather than restating any. The
    empty case must never claim completeness: a corpus with no notes can still
    be shaped by a feature gate or a date bound this function cannot see."""
    lines = [f"- {n}" for n in corpus.get("notes") or []]
    return "\n".join(lines) or "- No subject filter was applied to this corpus."


def _intake_text(matter: dict, corpus: dict) -> str:
    """Render the intake gaps for the prompt.

    Deliberately worded as "not provided", never "does not exist": CORPUS SCOPE
    already warns that a filtered corpus is not a finding of absence, and this
    block must not undo that by reading as one. It tells the model what to ASK
    for — it never licenses a statement about what the company does or does not
    have."""
    gaps = intake_gaps(matter, corpus)
    if not gaps:
        return "- Nothing obvious is missing. Analyze what the records show."
    return "\n".join(f"- {g['label']}" for g in gaps)


def _build_prompt(matter: dict, history: list[dict], corpus: dict, latest: str) -> str:
    return f"""{_SYSTEM}

MATTER
Type: {matter.get('matter_type') or 'other'}
Jurisdiction: {" → ".join(c["display_name"] for c in (corpus.get("legal_context") or {}).get("chain", [])) or "(not specified)"}
Allegation / what's being claimed: {matter.get('allegation') or '(not specified)'}
Factual context the company provided: {matter.get('defense_theory') or '(not specified)'}

CORPUS SCOPE — the corpus below is a FILTERED subset of the company's records.
A record type missing from it was filtered out, NOT proven absent. Never state or
imply the company has no records of a kind that this scope excluded.
{_scope_text(corpus)}

MATERIAL NOT YET IN THE RECORD — things the admin has not provided, which is NOT
the same as things that do not exist. Use this to decide what to ASK FOR. Never
state or imply the company lacks any of it.
{_intake_text(matter, corpus)}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus)}

CONVERSATION (oldest first):
{_history_text(history)}

LATEST USER MESSAGE:
{latest}
"""


async def _generate(matter: dict, history: list[dict], corpus: dict, latest: str) -> dict:
    prompt = _build_prompt(matter, history, corpus, latest)
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(model=MODEL, contents=prompt),
        timeout=_GEMINI_TIMEOUT,
    )
    data = _parse_json(getattr(resp, "text", "") or "")
    # Default TRUE when the key is absent or non-boolean: a malformed response
    # then degrades to the pre-intake behavior (analyze and show it) rather than
    # silently withholding every observation the model just produced.
    ready = data.get("ready_for_analysis")
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "ready_for_analysis": ready if isinstance(ready, bool) else True,
        "intake_requests": [
            str(r).strip() for r in (data.get("intake_requests") or [])
            if isinstance(r, (str, int, float)) and str(r).strip()
        ][:_MAX_INTAKE_REQUESTS],
        "evidence_map": data.get("evidence_map") or [],
        "open_questions": [str(q) for q in (data.get("open_questions") or []) if q],
    }


async def run_chat_turn(matter: dict, history: list[dict], corpus: dict, latest: str):
    """Async generator of SSE-shaped dicts for one grounded chat turn.

    Yields a status tick, then a single validated ``result`` (groundedness over
    token-streaming — the citation gate runs before anything reaches the user)."""
    yield {"type": "status", "message": "Organizing your records…"}
    try:
        result = await _generate(matter, history, corpus, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Analysis timed out — please try again."}
        return
    except Exception:
        logger.exception("legal_defense: chat turn failed")
        yield {"type": "error", "message": "Analysis failed — please try again."}
        return

    clean_map, dropped = validate_citations(result.get("evidence_map"), corpus.get("index", {}))
    result["evidence_map"] = clean_map
    if dropped:
        result["dropped_citations"] = dropped
        logger.info("legal_defense: dropped %d hallucinated citation(s)", len(dropped))

    # Still gathering: withhold the analysis blocks. The prompt already asks for
    # this; enforcing it here means a model that ignores the instruction cannot
    # hand counsel-facing conclusions drawn from a record the admin is still
    # assembling. Guarded on there actually being something to ask — a turn that
    # claims not-ready but produced no requests would otherwise render as a dead
    # end, so it degrades to showing whatever analysis it did produce.
    if not result.get("ready_for_analysis") and result.get("intake_requests"):
        result["evidence_map"] = []
        result["open_questions"] = []
    else:
        result["ready_for_analysis"] = True

    if not result["assistant_text"]:
        result["assistant_text"] = (
            "I still need a bit more before I can organize this."
            if result.get("intake_requests") else
            "I couldn't organize a response from the records this time. Try rephrasing, "
            "or widen the matter's date range."
        )
    yield {"type": "result", "data": result}
