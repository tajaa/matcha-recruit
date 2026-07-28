"""The grounded drafting turn: system prompt, prompt assembly, the Gemini call,
coercion of proposed drafts, and run_chat_turn.

`_corpus_text` and `_build_prompt` are deliberately NOT shared with
broker_pilot's same-named functions -- different signatures and render format
(this one inlines the tenant's real policy bodies from the full-text map; that
one inlines raw uploaded document text).
"""
import asyncio
import logging
import re
from app.matcha.services.pilots.legal_defense import _parse_json  # pure, unit-tested

from ._config import DRAFT_KINDS, MODEL, _CONTENT_CAP, _GEMINI_TIMEOUT, _HISTORY_TURNS, _MAX_DRAFTS_PER_TURN
from app.matcha.services._shared.gemini import _genai
from app.matcha.services._shared.text import history_text
from app.matcha.services._shared.text import _slug

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Grounded AI turn — HR policy drafter, grounded in the corpus.
# --------------------------------------------------------------------------- #

_SYSTEM = """You are an HR handbook and policy drafting assistant working for a company's HR administrator. You draft employee-handbook sections and standalone workplace policies, grounding EVERY enforceable clause in the EVIDENCE CORPUS below: the company profile (`profile`), the GOVERNING requirement per compliance category after federal/state/local precedence is resolved (`floor:` IDs), the full list of jurisdiction requirements that apply to the company's work locations (`law:` IDs), the company's existing handbook sections (`handbook:` IDs) and existing policies (`policy:` IDs), the industry playbook baseline (`playbook:` IDs), and the findings the platform has already recorded about this company's handbook — audited gaps (`audit:` IDs) and freshness findings (`fresh:` IDs).

HARD RULES:
- Cite ONLY the bracketed IDs that appear in the EVIDENCE CORPUS. NEVER invent a statute, dollar figure, deadline, or ID.
- When a `floor:` record and a `law:` record cover the same category, the `floor:` record is the GOVERNING requirement — draft to it and cite it. The `law:` list is every overlapping rule, including ones a stricter jurisdiction supersedes; drafting to one of those instead states the wrong obligation.
- Put those corpus IDs ONLY in the `cited_ids` array. NEVER write a corpus ID (like `law:…` or `handbook:…`) into the `content` prose — `content` is employee-facing handbook text. (Placeholder tokens like [HR_CONTACT_EMAIL] are fine in content.)
- When you assert a legal obligation (a required notice window, an accrual rate, a posting duty, a covered-employer threshold), cite the `law:` ID it comes from. If the corpus does not establish it, say so under open_questions instead of stating it as fact.
- Revise rather than duplicate: if an existing `handbook:`/`policy:` record already covers the topic, cite it and build on it.
- `audit:` and `fresh:` records are findings ABOUT this company's handbook — a graded gap, or a section the law has moved under. They are NOT law: never cite one as the source of a legal obligation, and never restate its wording as the requirement. Use them to decide WHAT to draft or revise, then cite the `floor:`/`law:` record for what the rule actually is. If the corpus has a finding but no matching `floor:`/`law:` record, say so under open_questions rather than inventing the obligation.
- An `audit:` gap is graded against a handbook DOCUMENT that was uploaded for audit — it may predate the sections in this corpus. Where a `handbook:` record already covers a gap, say the gap appears closed instead of drafting the section again.
- Write clear, enforceable, employee-facing prose. You MAY use the placeholder tokens the company resolves later, e.g. [HR_CONTACT_EMAIL], [HARASSMENT_REPORTING_HOTLINE], [ATTENDANCE_NOTICE_WINDOW].
- You draft; you do not give legal advice. Note where counsel review is warranted.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your conversational reply to the admin — what you drafted and why, and any choices you made>",
 "proposed_drafts": [{"kind": "<handbook_section | policy>", "title": "<short title>", "section_key": "<lowercase_snake_key or null>", "content": "<the full drafted body text>", "cited_ids": ["<id>", ...]}],
 "open_questions": ["<what the corpus does NOT establish / what the admin should confirm or provide>"]}

Only include proposed_drafts when the admin asked you to draft or revise something; a purely conversational turn may return an empty proposed_drafts list."""


def _corpus_text(corpus: dict) -> str:
    """Render the citable records for the prompt. Where `corpus['full_text']`
    has the record's real body (existing sections and policies), that body is
    rendered instead of the 280-char index summary — a drafting tool revising a
    policy has to see the policy.

    Kept in this module's own `## label` + `(when)` format rather than reusing
    `hr_pilot_corpus.render_corpus_block`: `when` carries effective dates that
    matter for a `law:`/`floor:` record, and HR Pilot's block drops it."""
    full_text = corpus.get("full_text") or {}
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            body = full_text.get(r["cid"])
            if body:
                out.append(f"- [{r['cid']}] ({r['when']}) {r['ref']}\n{body}")
            else:
                out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")
    return "\n".join(out) or "(no grounding records in scope)"


def _history_text(history: list[dict]) -> str:
    return history_text(history, _HISTORY_TURNS)


def _build_prompt(session: dict, history: list[dict], corpus: dict, latest: str) -> str:
    return f"""{_SYSTEM}

SESSION: {session.get('title') or 'Handbook drafting session'}
GOAL: {session.get('goal') or '(not specified)'}
INDUSTRY: {session.get('industry') or 'general'}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus)}

CONVERSATION (oldest first):
{_history_text(history)}

LATEST ADMIN MESSAGE:
{latest}
"""


# Inline corpus-id tokens the model embeds in prose despite the prompt asking for
# cited_ids only (e.g. "...report concerns [handbook:0e29…]."). Colon-form
# (law:/floor:/handbook:/policy:/playbook:/audit:/fresh:) is unambiguous; `profile` is the one bare
# cid. `(?!\()` protects markdown links [text](url), mirroring the frontend
# highlightPlaceholders guard; ALL-CAPS placeholder tokens like [HR_CONTACT_EMAIL]
# never match (the prefixes are lowercase keywords). Leading `[ \t]*` eats the
# space before the tag so removal doesn't leave a double space.
_INLINE_CID = re.compile(
    r"[ \t]*\[(?:(?:law|floor|handbook|policy|playbook|audit|fresh):[^\]\s]+|profile)\](?!\()"
)


def strip_corpus_citations(content: str) -> tuple[str, list[str]]:
    """Remove inline corpus-id tags from a draft body. Returns
    (clean_content, found_ids); found_ids are raw (not filtered against the
    index — harvesting/validation is the caller's choice). Pure."""
    found: list[str] = []

    def _sub(m):
        found.append(m.group(0).strip()[1:-1])  # the cid inside the brackets
        return ""

    clean = _INLINE_CID.sub(_sub, content or "")
    clean = re.sub(r"[ \t]{2,}", " ", clean)          # squeeze spaces removal left
    clean = re.sub(r"[ \t]+([.,;:])", r"\1", clean)   # no space before punctuation
    clean = re.sub(r"[ \t]+\n", "\n", clean)          # no trailing spaces per line
    return clean.strip(), found


def _coerce_drafts(raw, index: dict) -> tuple[list[dict], list[str]]:
    """Clamp the model's proposed_drafts into the stored schema and filter each
    draft's citations against the corpus index. Returns (drafts, dropped_ids).

    Inline corpus-id tags the model wrote into the prose are stripped from
    `content` here; any that name a real corpus record are harvested into the
    draft's cited_ids so groundedness survives even if the model only tagged
    inline, and invented ones are reported as dropped (same gate as the field).

    Filters citations per-draft directly (same rule as the shared
    ``validate_citations`` gate — keep only ids present in ``index``) rather than
    round-tripping through an evidence_map, so the citation→draft mapping doesn't
    depend on that function's row ordering.

    Membership is EXACT — deliberately not ``lookup_record``. That helper's
    legacy-cid recovery exists for citations already stored in the database; run
    a model-emitted id through it and an invented `law:ca-overtime-2025` would
    resolve to the one real overtime requirement instead of being dropped, which
    is precisely the hallucination this gate exists to stop."""
    if not isinstance(raw, list):
        return [], []
    drafts: list[dict] = []
    dropped: list[str] = []
    for d in raw[:_MAX_DRAFTS_PER_TURN]:
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind") or "").strip().lower()
        if kind not in DRAFT_KINDS:
            kind = "handbook_section"
        title = str(d.get("title") or "").strip()[:300]
        content = str(d.get("content") or "").strip()[:_CONTENT_CAP]
        content, inline_ids = strip_corpus_citations(content)
        if not (title and content):
            continue
        raw_ids = d.get("cited_ids")
        ids = [c for c in raw_ids if isinstance(c, str)] if isinstance(raw_ids, list) else []
        kept: list[str] = []
        # The separate cited_ids field first, then any real ids the model only
        # wrote inline (now stripped from the prose above) — invented ids from
        # either source are dropped identically.
        for c in [*ids, *inline_ids]:
            if c not in index:
                dropped.append(c)
                continue
            if c not in kept:
                kept.append(c)
        section_key = d.get("section_key")
        section_key = _slug(section_key)[:120] if section_key else _slug(title)[:120]
        drafts.append({
            "kind": kind,
            "title": title,
            "section_key": section_key,
            "content": content,
            "cited_ids": kept,
        })
    return drafts, dropped


async def _generate(session: dict, history: list[dict], corpus: dict, latest: str) -> dict:
    prompt = _build_prompt(session, history, corpus, latest)
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(model=MODEL, contents=prompt),
        timeout=_GEMINI_TIMEOUT,
    )
    data = _parse_json(getattr(resp, "text", "") or "")
    drafts, dropped = _coerce_drafts(data.get("proposed_drafts"), corpus.get("index", {}))
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "proposed_drafts": drafts,
        "open_questions": [str(q) for q in (data.get("open_questions") or []) if q],
        "dropped_citations": dropped,
    }


async def run_chat_turn(session: dict, history: list[dict], corpus: dict, latest: str):
    """Async generator of SSE-shaped dicts for one grounded drafting turn. Yields
    a status tick, then a single validated ``result`` (the citation gate runs
    before anything reaches the admin — groundedness over token-streaming)."""
    yield {"type": "status", "message": "Drafting from your profile, applicable law, and existing policies…"}
    try:
        result = await _generate(session, history, corpus, latest)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Drafting timed out — please try again."}
        return
    except Exception:
        logger.exception("handbook_pilot: chat turn failed")
        yield {"type": "error", "message": "Drafting failed — please try again."}
        return

    if result.get("dropped_citations"):
        logger.info("handbook_pilot: dropped %d hallucinated citation(s)",
                    len(result["dropped_citations"]))
    if not result["assistant_text"]:
        result["assistant_text"] = (
            "I couldn't produce a draft from the material this time. Try rephrasing, "
            "or confirm the session's work locations so the applicable requirements load."
        )
    yield {"type": "result", "data": result}
