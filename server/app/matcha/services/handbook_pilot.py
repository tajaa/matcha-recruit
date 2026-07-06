"""Handbook Pilot — grounded conversational handbook/policy generation (Pro + Matcha-X).

A business admin opens a generation session and converses with an AI grounded in
the company's own material: the handbook profile, the jurisdiction/compliance
requirements that apply to the company's work locations (the same
`jurisdiction_requirements` corpus the template generator and the audit grader
read), the industry playbook baseline, and the company's existing handbook
sections + policies (so the pilot revises rather than duplicates). The model
proposes candidate handbook sections and standalone policies; every enforceable
clause must cite a bracketed corpus ID, and the shared
`legal_defense.validate_citations` gate drops any citation not in the corpus
before anything reaches the user. Proposed drafts persist as reviewable rows
that the admin edits and PROMOTES into the real handbooks / policies tables.

Derived from the Broker Pilot / Legal Pilot architecture
(`services/broker_pilot.py`, `services/legal_defense.py`) and reuses their pure
gates directly. Never raises on the analysis path — failures degrade, not 500.

Corpus cid scheme (one flat index; the citation gate keys on it):
- ``profile``               — the company handbook profile record
- ``law:<state>-<slug>-<n>``— one record per applicable jurisdiction requirement
- ``handbook:<uuid>``       — one record per existing handbook section
- ``policy:<uuid>``         — one record per existing policy
- ``playbook:<slug>``       — one record per industry playbook baseline section
"""

import asyncio
import logging
import re

from app.core.services.genai_client import get_genai_client

from .legal_defense import _parse_json  # pure, unit-tested

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 90
_HISTORY_TURNS = 12
_LAW_PER_STATE_CAP = 40          # applicable requirements per state fed to the model
_MAX_EXISTING_SECTIONS = 60
_MAX_EXISTING_POLICIES = 60
_MAX_DRAFTS_PER_TURN = 6         # candidate artifacts the model may propose per turn
_CONTENT_CAP = 12_000            # generated body cap per draft

DRAFT_KINDS = ("handbook_section", "policy")

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


def _slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Grounding — fetch the raw records the corpus is built from. DB-touching.
# --------------------------------------------------------------------------- #

async def gather_grounding(conn, company_id, session: dict) -> dict:
    """Fetch the raw grounding material for a session: handbook profile,
    applicable jurisdiction requirements, existing handbook sections, existing
    policies. Best-effort at every level — a dead source degrades to empty and
    the chat still grounds on whatever else is available."""
    from app.core.services import handbook_service as hb

    # Always re-derive scopes from the live employee roster so a company that
    # expands into a new state grounds on that state's requirements immediately
    # (the session snapshot, seeded at create time, is only a fallback when
    # derivation fails or the roster is empty).
    snapshot = session.get("scopes") or []
    if isinstance(snapshot, str):
        import json
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            snapshot = []
    try:
        derived = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: scope derivation failed for %s", company_id)
        derived = []
    scopes = derived or snapshot

    profile = None
    try:
        profile = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: profile fetch failed for %s", company_id)

    requirements: dict = {}
    if scopes:
        try:
            requirements = await hb._fetch_state_requirements(conn, scopes)
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: requirement fetch failed for %s", company_id)
            requirements = {}

    sections: list = []
    try:
        sections = await conn.fetch(
            """
            SELECT hs.id, hs.title, hs.section_key, hs.section_type, hs.content,
                   h.title AS handbook_title
            FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1
              AND h.status IN ('active', 'draft')
              AND hv.version_number = h.active_version
            ORDER BY h.status = 'active' DESC, hs.section_order
            LIMIT $2
            """,
            company_id, _MAX_EXISTING_SECTIONS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: existing-section fetch failed for %s", company_id)

    policies: list = []
    try:
        policies = await conn.fetch(
            """
            SELECT id, title, category, status, description
            FROM policies
            WHERE company_id = $1 AND status IN ('active', 'draft')
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_EXISTING_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: existing-policy fetch failed for %s", company_id)

    return {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": session.get("industry"),
    }


# --------------------------------------------------------------------------- #
# Corpus build — pure (no DB), unit-tested. Assembles the flat citation index.
# --------------------------------------------------------------------------- #

def _profile_record(profile: dict | None) -> list[dict]:
    if not profile:
        return []
    bits = []
    if profile.get("legal_name"):
        bits.append(f"legal name {profile['legal_name']}")
    if profile.get("headcount") is not None:
        bits.append(f"headcount {profile['headcount']}")
    flags = [k for k, v in profile.items()
             if isinstance(v, bool) and v and k not in ("id",)]
    if flags:
        bits.append("workforce attributes: " + ", ".join(_hum(f) for f in flags[:12]))
    if not bits:
        return []
    return [{
        "cid": "profile",
        "ref": "Company handbook profile",
        "summary": "; ".join(bits) + ".",
        "when": "current",
    }]


def _law_records(requirements: dict) -> list[dict]:
    """One record per applicable jurisdiction requirement. `requirements` is the
    state -> [requirement dict] map from handbook_service._fetch_state_requirements."""
    recs: list[dict] = []
    for state, reqs in (requirements or {}).items():
        for n, r in enumerate((reqs or [])[:_LAW_PER_STATE_CAP]):
            if not isinstance(r, dict):
                continue
            title = r.get("title") or r.get("category") or "requirement"
            cid = f"law:{_slug(state)}-{_slug(r.get('category') or title)}-{n}"
            juris = r.get("jurisdiction_name") or state
            parts = [str(title)]
            if r.get("current_value"):
                parts.append(f"value {r['current_value']}")
            if r.get("description"):
                parts.append(str(r["description"])[:280])
            recs.append({
                "cid": cid,
                "ref": f"{state} · {juris}: {title}",
                "summary": " — ".join(parts) + ".",
                "when": str(r.get("effective_date") or "current"),
            })
    return recs


def _existing_section_records(sections: list[dict]) -> list[dict]:
    recs = []
    for s in sections or []:
        recs.append({
            "cid": f"handbook:{s.get('id')}",
            "ref": f"Existing section — {s.get('title')}",
            "summary": (str(s.get("content") or "")[:280] or "existing handbook section")
                       + (" …" if len(str(s.get("content") or "")) > 280 else ""),
            "when": "current",
        })
    return recs


def _existing_policy_records(policies: list[dict]) -> list[dict]:
    recs = []
    for p in policies or []:
        bits = [str(p.get("title") or "policy")]
        if p.get("category"):
            bits.append(f"category {_hum(p['category'])}")
        if p.get("status"):
            bits.append(f"status {p['status']}")
        if p.get("description"):
            bits.append(str(p["description"])[:200])
        recs.append({
            "cid": f"policy:{p.get('id')}",
            "ref": f"Existing policy — {p.get('title')}",
            "summary": "; ".join(bits) + ".",
            "when": "current",
        })
    return recs


def _playbook_records(industry: str | None) -> list[dict]:
    from app.core.services.handbook_service import GUIDED_INDUSTRY_PLAYBOOK
    key = (industry or "general").strip().lower()
    play = GUIDED_INDUSTRY_PLAYBOOK.get(key) or GUIDED_INDUSTRY_PLAYBOOK.get("general") or {}
    recs = []
    if play.get("summary"):
        recs.append({
            "cid": f"playbook:{_slug(key)}-summary",
            "ref": f"{play.get('label') or _hum(key)} baseline",
            "summary": str(play["summary"]),
            "when": "baseline",
        })
    for sec in play.get("sections") or []:
        if not isinstance(sec, dict) or not sec.get("title"):
            continue
        recs.append({
            "cid": f"playbook:{_slug(sec['title'])}",
            "ref": f"Playbook section — {sec['title']}",
            "summary": str(sec.get("content") or "")[:400],
            "when": "baseline",
        })
    return recs


def build_corpus(grounding: dict) -> dict:
    """Assemble the grounding corpus `{sources, index, notes}` — the same shape
    Legal/Broker Pilot use, so `validate_citations` works unchanged. Pure."""
    grounding = grounding or {}
    sources = {
        "profile": {"label": "Company profile",
                    "records": _profile_record(grounding.get("profile"))},
        "law": {"label": "Applicable jurisdiction requirements",
                "records": _law_records(grounding.get("requirements"))},
        "existing_handbook": {"label": "Existing handbook sections",
                              "records": _existing_section_records(grounding.get("sections"))},
        "existing_policies": {"label": "Existing policies",
                              "records": _existing_policy_records(grounding.get("policies"))},
        "playbook": {"label": "Industry playbook baseline",
                     "records": _playbook_records(grounding.get("industry"))},
    }
    notes: list[str] = []
    if not grounding.get("scopes"):
        notes.append(
            "No work locations on file — add employee locations or session scopes "
            "so applicable jurisdiction requirements can ground the draft."
        )
    if not sources["law"]["records"]:
        notes.append("No jurisdiction requirements found for the session's locations.")
    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}
    return {"sources": sources, "index": index, "notes": notes}


# --------------------------------------------------------------------------- #
# Grounded AI turn — HR policy drafter, grounded in the corpus.
# --------------------------------------------------------------------------- #

_SYSTEM = """You are an HR handbook and policy drafting assistant working for a company's HR administrator. You draft employee-handbook sections and standalone workplace policies, grounding EVERY enforceable clause in the EVIDENCE CORPUS below: the company profile (`profile`), the jurisdiction requirements that apply to the company's work locations (`law:` IDs), the company's existing handbook sections (`handbook:` IDs) and existing policies (`policy:` IDs), and the industry playbook baseline (`playbook:` IDs).

HARD RULES:
- Cite ONLY the bracketed IDs that appear in the EVIDENCE CORPUS. NEVER invent a statute, dollar figure, deadline, or ID.
- When you assert a legal obligation (a required notice window, an accrual rate, a posting duty, a covered-employer threshold), cite the `law:` ID it comes from. If the corpus does not establish it, say so under open_questions instead of stating it as fact.
- Revise rather than duplicate: if an existing `handbook:`/`policy:` record already covers the topic, cite it and build on it.
- Write clear, enforceable, employee-facing prose. You MAY use the placeholder tokens the company resolves later, e.g. [HR_CONTACT_EMAIL], [HARASSMENT_REPORTING_HOTLINE], [ATTENDANCE_NOTICE_WINDOW].
- You draft; you do not give legal advice. Note where counsel review is warranted.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your conversational reply to the admin — what you drafted and why, and any choices you made>",
 "proposed_drafts": [{"kind": "<handbook_section | policy>", "title": "<short title>", "section_key": "<lowercase_snake_key or null>", "content": "<the full drafted body text>", "cited_ids": ["<id>", ...]}],
 "open_questions": ["<what the corpus does NOT establish / what the admin should confirm or provide>"]}

Only include proposed_drafts when the admin asked you to draft or revise something; a purely conversational turn may return an empty proposed_drafts list."""


def _corpus_text(corpus: dict) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] ({r['when']}) {r['summary']}")
    return "\n".join(out) or "(no grounding records in scope)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


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


def _coerce_drafts(raw, index: dict) -> tuple[list[dict], list[str]]:
    """Clamp the model's proposed_drafts into the stored schema and filter each
    draft's citations against the corpus index. Returns (drafts, dropped_ids).

    Filters citations per-draft directly (same rule as the shared
    ``validate_citations`` gate — keep only ids present in ``index``) rather than
    round-tripping through an evidence_map, so the citation→draft mapping doesn't
    depend on that function's row ordering."""
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
        if not (title and content):
            continue
        raw_ids = d.get("cited_ids")
        ids = [c for c in raw_ids if isinstance(c, str)] if isinstance(raw_ids, list) else []
        kept = [c for c in ids if c in index]
        dropped.extend(c for c in ids if c not in index)
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
