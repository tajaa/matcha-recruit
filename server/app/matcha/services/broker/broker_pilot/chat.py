"""The grounded chat turn: system prompt, prompt assembly over the corpus +
history, the Gemini call with its retry, coercion of findings, the citation
gate, and run_chat_turn.

`_corpus_text` and `_build_prompt` are deliberately NOT shared with
handbook_pilot's same-named functions -- different signatures, different render
format (this one inlines raw document text; that one inlines policy bodies).
"""
import asyncio
import logging
from app.matcha.services._shared.citations import validate_citations, _parse_json  # pure, unit-tested

from ._config import MODEL, _DOC_TEXT_CAP, _FINDING_POINT_CAP, _GAP_SEVERITIES, _GEMINI_TIMEOUT, _HISTORY_TURNS, _MAX_DOC_TEXT_BLOCKS, _MAX_FINDINGS, _MAX_QUESTIONS, _QUESTION_CAP
from app.matcha.services._shared.gemini import _genai
from .templates import _mode_focus

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Grounded AI turn (analyst, not advisor)
# --------------------------------------------------------------------------- #

_SYSTEM = """You are a commercial P&C insurance analysis assistant working for a licensed insurance broker who is preparing analysis for a client. You ground EVERY statement in the EVIDENCE CORPUS below: the client's platform records (`platform:` IDs), the company's operational records generated natively on the platform (`incident:` / `er_case:` / `compliance_req:` / `compliance_alert:` / `discipline:` / `training:` / `policy_ack:` / `accommodation:` / `charge:` (agency charges — EEOC/NLRB/OSHA/state) / `preterm:` (pre-termination risk reviews) / `separation:` (separation agreements) / `ptclaim:` (post-termination claims) IDs — present only for on-platform clients), the indemnification clauses extracted from the client's contracts (`clause:` IDs), the codified state and federal statutory obligations the client must follow (`jur:` IDs — present only for on-platform clients), and the broker's uploaded documents (`doc:` / `docfig:` IDs).

HARD RULES:
- Cite ONLY the bracketed IDs that appear in the EVIDENCE CORPUS. NEVER invent a figure, carrier, date, limit, premium, or ID.
- When an uploaded document and the platform data disagree, say so explicitly and cite both sides — do not silently pick one.
- Where the corpus does not address a point, say so plainly and put it under open_questions — never speculate or fill gaps.
- You MAY compute simple derived figures (differences, ratios, loss ratios, year-over-year changes) from cited values — state the inputs and cite their IDs.
- You are an ANALYST, NOT AN ADVISOR: do not recommend buying or declining coverage, do not opine on legal duties, and note that quotes and forms must be verified against actual policy language.
- On `clause:` records: your remit is INSURANCE AND RISK TRANSFER ONLY. Discuss indemnity form, insurability, and the endorsements a clause requires — never opine on payment terms, termination, IP, or dispute resolution, and never state that a clause IS or IS NOT enforceable. A recorded verdict is a starting point for counsel, so report it as such and say so.
- A `clause:` record marked PROVISIONAL comes from an unconfirmed AI extraction — say that whenever you rely on it.
- On `jur:` records: these are the client's CODIFIED state and federal statutory obligations (e.g. final-pay timing, pay-transparency, anti-discrimination). Cite the statute when a point turns on the law, and never state a legal conclusion, opine on whether the client is compliant, or give legal advice — surface the obligation and route the judgment to counsel.
- On property and index records: `platform:property.cat` (catastrophe tiers), `platform:property.exposure` (modeled AAL/PML), `platform:property.plan.<n>` (ranked property fixes) and `platform:property.risk` (TIV-weighted score) are the platform's own property analytics, and `platform:risk` plus `platform:risk.<component>` are its composite risk index. These are the platform's models, not carrier output — cite them as the platform's figures, and where a record says a tier is a directional baseline rather than a documented probability, repeat that qualifier when you use it.
- On `platform:fleet` and `platform:fleet.<driver>` records: these are the commercial-auto driver-risk view, scored from MVR data the EMPLOYER recorded — not a pulled motor-vehicle record and not carrier output. Say that whenever you rely on them, and treat a named driver's tier as the platform's score, not a finding about that person.
- On `platform:schedule`: a directional estimate computed from the tenant's own scheduling data (understaffing/incident correlation, Fair Workweek exposure, qualified-coverage gaps) — never a causal claim, a payroll figure, or legal advice. Repeat that framing whenever you rely on it.
- Raw document text (DOCUMENT TEXT blocks) belongs to its `doc:` ID — cite that ID when using it.

ANSWER SHAPE — a short lead answer, then three reviewable lists. The broker reads
the lists, not a wall of prose:
- assistant_text: the direct answer to what was asked, at most 120 words, plain
  prose. Lead with the conclusion. Do NOT write section headings, do NOT restate
  the lists below, and do NOT pad with caveats that belong in key_questions.
- key_questions: what the broker should put to the client, the underwriter, or
  counsel before acting — including anything the corpus does not establish and
  the data that would settle it. This is the broker's next-action list.
- considerations: the strategic reading — what the material means for how the
  account is positioned, marketed, or negotiated. Judgment, grounded in cited
  records wherever it rests on a fact. Never a recommendation to buy or decline
  coverage.
- gaps: the concrete, specific gaps the record supports — a limit below what a
  contract requires, a missing endorsement, an uninsurable indemnity form, an
  exclusion or sublimit, a coverage line carried nowhere, or a hole in the data
  needed to place the account. Every gap MUST cite the records that establish it
  and carry a severity of "high", "medium", or "low". An unsupported gap is a
  key_question, not a gap — do not manufacture gaps to fill the list.

Emit a list ONLY where the corpus supports entries; an empty list is correct and
expected. Every `point` is one sentence.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<direct answer, <=120 words, no headings>",
 "key_questions": ["<question the broker should ask / what to obtain to settle it>"],
 "considerations": [{"point": "<what this means for the account>", "cited_ids": ["<id>", ...]}],
 "gaps": [{"point": "<the specific gap>", "severity": "high|medium|low", "cited_ids": ["<id>", ...]}],
 "evidence_map": [{"point": "<a factual observation grounded in the corpus>", "cited_ids": ["<id>", ...]}]}"""


def _corpus_text(corpus: dict, docs: list[dict]) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")

    # Raw text for the most recent usable docs — deeper than the extraction,
    # bounded so five 15MB uploads can't blow the prompt.
    usable = [d for d in (docs or []) if d.get("status") in ("ready", "text_only")
              and (d.get("extracted_text") or "").strip()]
    for d in usable[-_MAX_DOC_TEXT_BLOCKS:]:
        text = (d.get("extracted_text") or "").strip()
        clipped = text[:_DOC_TEXT_CAP]
        note = " …(truncated)" if len(text) > _DOC_TEXT_CAP else ""
        out.append(f"### DOCUMENT TEXT [doc:{d.get('id')}] {d.get('filename')}")
        out.append(clipped + note)
    return "\n".join(out) or "(no records or documents in scope)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def _scope_text(corpus: dict) -> str:
    """Corpus notes as a prompt block. An absent record is indistinguishable from
    a record that doesn't exist, so without this the model answers confidently
    from whatever else is in scope and never says "you haven't given me the loss
    run". The notes are the only channel that tells it what is MISSING."""
    notes = corpus.get("notes") or []
    if not notes:
        return ""
    listed = "\n".join(f"- {n}" for n in notes)
    return (
        "\nSCOPE NOTES (limits of what you were given — honor them; never invent "
        f"material to fill a gap they name):\n{listed}\n"
    )


def _build_prompt(session: dict, subject_name: str, history: list[dict],
                  corpus: dict, docs: list[dict], latest: str) -> str:
    kind = "on-platform Matcha client" if session.get("subject_kind") == "company" \
        else "off-platform client (broker-recorded data only)"
    focus = _mode_focus(session.get("template_key"))
    mode_block = f"\n{focus}\n" if focus else ""
    return f"""{_SYSTEM}
{mode_block}
CLIENT: {subject_name} — {kind}
SESSION: {session.get('title') or 'Analysis session'}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus, docs)}
{_scope_text(corpus)}
CONVERSATION (oldest first):
{_history_text(history)}

LATEST BROKER MESSAGE:
{latest}
"""


def _coerce_findings(raw, *, with_severity: bool) -> list[dict]:
    """Clamp a model-emitted findings list into the stored shape. Pure.

    Shape is `{point, cited_ids}` (+ `severity` for gaps) — the same shape the
    citation gate consumes, so a coerced list can go straight to it."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:_MAX_FINDINGS]:
        if not isinstance(item, dict):
            continue
        point = str(item.get("point") or "").strip()[:_FINDING_POINT_CAP]
        if not point:
            continue
        cited = item.get("cited_ids")
        ids = [str(c) for c in cited if c] if isinstance(cited, list) else []
        finding = {"point": point, "cited_ids": ids}
        if with_severity:
            sev = str(item.get("severity") or "").strip().lower()
            # Unknown/absent severity is not an error — the gap still stands, it
            # just isn't ranked. Never guess a severity the model didn't give.
            finding["severity"] = sev if sev in _GAP_SEVERITIES else None
        out.append(finding)
    return out


def _coerce_turn(data) -> dict:
    """Clamp one model turn into the stored answer schema. Pure.

    `key_questions` falls back to the legacy `open_questions` key so a model
    (or a stored message) still speaking the old shape keeps working."""
    if not isinstance(data, dict):
        data = {}
    questions = data.get("key_questions")
    if not isinstance(questions, list) or not questions:
        questions = data.get("open_questions")
    if not isinstance(questions, list):
        questions = []
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "key_questions": [
            str(q).strip()[:_QUESTION_CAP] for q in questions[:_MAX_QUESTIONS]
            if q and str(q).strip()
        ],
        "considerations": _coerce_findings(data.get("considerations"), with_severity=False),
        "gaps": _coerce_findings(data.get("gaps"), with_severity=True),
        "evidence_map": data.get("evidence_map") or [],
    }


def _gate(items: list[dict], index: dict) -> tuple[list[dict], list[str]]:
    """Run the shared anti-hallucination gate over a findings list, preserving
    per-item keys it doesn't know about (`severity`).

    `validate_citations` returns only `{point, cited_ids}`, so gate item-by-item
    and re-attach the rest — a positional zip would misalign the moment the gate
    skips a non-dict item."""
    clean, dropped = [], []
    for item in items:
        [checked], drops = validate_citations([item], index)
        clean.append({**item, **checked})
        dropped.extend(drops)
    return clean, dropped


def _why_empty(resp) -> str:
    """One-line diagnosis of a reply that produced no usable turn.

    The empty-answer path used to be silent, so a broker hitting the "I couldn't
    produce an analysis" fallback left nothing behind to diagnose — the three
    causes (safety block, output-cap truncation, prose instead of JSON) are
    indistinguishable from the outside and want different fixes."""
    cand = (getattr(resp, "candidates", None) or [None])[0]
    reason = getattr(cand, "finish_reason", None)
    usage = getattr(resp, "usage_metadata", None)
    return (
        f"finish_reason={reason} "
        f"prompt_feedback={getattr(resp, 'prompt_feedback', None)} "
        f"candidates_tokens={getattr(usage, 'candidates_token_count', None)} "
        f"thoughts_tokens={getattr(usage, 'thoughts_token_count', None)}"
    )


async def _generate_once(prompt: str) -> tuple[dict, str]:
    """One generation. Returns (coerced turn, raw text).

    ``response_mime_type="application/json"`` is what every sibling pilot already
    passes (`analysis_pilot._gen_config`); without it the model is free to answer
    in prose or fenced markdown, `_parse_json` returns {}, and the whole turn
    degrades to the fallback string."""
    from google.genai import types
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        ),
        timeout=_GEMINI_TIMEOUT,
    )
    text = getattr(resp, "text", "") or ""
    turn = _coerce_turn(_parse_json(text))
    if not turn["assistant_text"]:
        logger.warning(
            "broker_pilot: empty turn from model — %s text_len=%d head=%r",
            _why_empty(resp), len(text), text[:400],
        )
    return turn, text


async def _generate(session: dict, subject_name: str, history: list[dict],
                    corpus: dict, docs: list[dict], latest: str) -> dict:
    """Generate one turn, retrying once on a wholly empty result.

    The retry is deliberately narrow: an empty `assistant_text` AND no buckets
    means nothing usable came back at all (a safety block, a truncated reply, or
    a parse failure), and those are transient often enough that one more attempt
    beats showing the broker a dead end. A turn with *any* content is kept as-is
    — re-rolling a real answer would be non-determinism the broker can't see."""
    prompt = _build_prompt(session, subject_name, history, corpus, docs, latest)
    turn, _ = await _generate_once(prompt)
    if not _is_empty_turn(turn):
        return turn
    logger.info("broker_pilot: empty first turn — retrying once")
    retried, _ = await _generate_once(prompt)
    return retried if not _is_empty_turn(retried) else turn


def _is_empty_turn(turn: dict) -> bool:
    """Nothing usable came back — no answer and no populated bucket."""
    return not turn.get("assistant_text") and not any(
        turn.get(k) for k in ("key_questions", "considerations", "gaps", "evidence_map")
    )


async def run_chat_turn(session: dict, subject_name: str, history: list[dict],
                        corpus: dict, docs: list[dict], latest: str):
    """Async generator of SSE-shaped dicts for one grounded chat turn. Yields a
    status tick, then a single validated ``result`` (the citation gate runs
    before anything reaches the broker — groundedness over token-streaming)."""
    yield {"type": "status", "message": "Analyzing the documents and platform data…"}
    try:
        result = await _generate(session, subject_name, history, corpus, docs, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Analysis timed out — please try again."}
        return
    except Exception:
        logger.exception("broker_pilot: chat turn failed")
        yield {"type": "error", "message": "Analysis failed — please try again."}
        return

    index = corpus.get("index", {})
    dropped: list[str] = []

    clean_map, drops = validate_citations(result.get("evidence_map"), index)
    result["evidence_map"] = clean_map
    dropped.extend(drops)

    considerations, drops = _gate(result.get("considerations") or [], index)
    result["considerations"] = considerations
    dropped.extend(drops)

    gaps, drops = _gate(result.get("gaps") or [], index)
    dropped.extend(drops)
    # A gap is a claim ABOUT the record — if the gate stripped every record it
    # rested on, nothing grounds it, so it doesn't survive as a gap. The prompt
    # says an unsupported gap is a question; demote it rather than drop it, so
    # the broker still sees the thread to pull.
    result["gaps"] = [g for g in gaps if g["cited_ids"]]
    demoted = [g["point"] for g in gaps if not g["cited_ids"]]
    if demoted:
        result["key_questions"] = (result.get("key_questions") or []) + demoted
        logger.info("broker_pilot: demoted %d ungrounded gap(s) to key questions", len(demoted))

    if dropped:
        result["dropped_citations"] = dropped
        logger.info("broker_pilot: dropped %d hallucinated citation(s)", len(dropped))
    if not result["assistant_text"]:
        # Nothing usable survived (or ever arrived). Surface it as an ERROR, not a
        # result: an error is transient in the console and — unlike a result — is
        # never persisted, so a dead turn can't enter the history that grounds the
        # next one. `_generate` has already retried once and logged the cause.
        if _is_empty_turn(result):
            yield {"type": "error", "message": (
                "I couldn't produce an analysis from the material this time. "
                "Try rephrasing, or check that the documents finished processing."
            )}
            return
        # A turn with lists but no lead answer is still worth keeping — the
        # broker reads the lists. Say the lead is missing rather than fake one.
        result["assistant_text"] = (
            "No summary came back for this turn — the findings below are what the "
            "material supports."
        )
    yield {"type": "result", "data": result}
