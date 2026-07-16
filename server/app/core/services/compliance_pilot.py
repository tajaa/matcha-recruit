"""Compliance Pilot — chat-driven library building for the admin Compliance Studio.

Modeled on Broker Pilot (`matcha/services/broker_pilot.py`): a static mode tuple
(`PILOT_TEMPLATES`), one strict-JSON Gemini turn per message (status → validated
result), the shared `legal_defense.validate_citations` gate. The difference is the
ACTION layer Broker Pilot lacks — a chat turn may emit one structured PROPOSAL
(research / check_sources over an industry × jurisdiction coordinate), which the
admin confirms into a background run that drives the EXISTING pipeline:

- research  → `research_specialization_for_jurisdiction(..., initial_status='pending',
              route_by_level=True)` stages rows; approve (`research_review.approve_staged`)
              activates + codifies them.
- check_sources → `compliance_evals.authority.run_authority` + a thin `source_url_status`
              write-back for genuinely dead links.
- ask      → `ComplianceRAGService.search_requirements` over `compliance_embeddings`.
- scope    → research's coverage snapshot, narrated; proposes the research gap.

Every write is labeled for the jrver01 version trigger via `set_change_context`.
Actions run in their OWN connections (the runner is a background task that outlives
the request; never hand it a request-scoped connection).
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import UUID


def _norm_cat(s) -> str:
    """Collapse a category slug/name/topic to a comparable key: lowercase, no
    spaces/underscores/hyphens. 'Clinical Safety' == 'clinical_safety'."""
    return re.sub(r"[\s_\-]+", "", str(s or "").strip().lower())

from app.core.services.genai_client import get_genai_client

from app.database import get_connection
from .change_context import set_change_context

# NOTE: `legal_defense.validate_citations` / `_parse_json` (the shared, pure gate)
# are imported LAZILY inside run_chat_turn — a module-level `from app.matcha...`
# here would be the first core→matcha startup edge (circular-import landmine).
# Existing core precedent (channels_ws.py) is lazy-only; follow it.

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 90
_HISTORY_TURNS = 12
_MAX_ASK_HITS = 12
_MAX_CITED = 12
_TEXT_CAP = 1500

_genai_client = None


def _genai():
    global _genai_client
    if _genai_client is None:
        _genai_client = get_genai_client()
    return _genai_client


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
# `focus` is appended to the system prompt every turn (persisted via
# compliance_pilot_sessions.mode). It steers behavior AND names whether the mode
# may emit an action proposal. Public fields only reach the client; `focus` stays
# server-side (same split as Broker Pilot).

PILOT_TEMPLATES: tuple[dict, ...] = (
    {
        "key": "research",
        "label": "Research industry",
        "description": "Research the compliance requirements for an industry in a "
                       "jurisdiction, stage them for review, then codify + commit.",
        "title": "Research",
        "focus": (
            "You help an admin BUILD the shared compliance catalog. When the admin "
            "names an industry and a place (e.g. 'manufacturing in Los Angeles'), "
            "emit ONE proposal: {\"kind\":\"research\", \"industry\":\"<industry>\", "
            "\"state\":\"<2-letter>\", \"city\":\"<city or null>\", "
            "\"categories\":[<topics>]|null, \"rationale\":\"<one sentence>\"}. Infer the "
            "2-letter state from the city when obvious (Los Angeles→CA, NYC→NY, "
            "Chicago→IL). CATEGORY SCOPING (important — each category is a Gemini "
            "research pass, so scope tightly): if the admin names a SPECIFIC topic — "
            "'clinical safety', 'HIPAA', 'overtime', 'sick leave', 'medical waste' — set "
            "`categories` to JUST that topic (a short list, snake_case, e.g. "
            "[\"clinical_safety\"]). Set `categories` to null ONLY when the admin "
            "explicitly asks for ALL / every / the full set of requirements. Never widen "
            "a single named topic into the whole catalog. Do NOT invent requirement "
            "values in prose — the research run produces them. If the request is "
            "ambiguous, ask a short clarifying question and emit no proposal."
        ),
        "starters": [
            "Research clinical safety requirements for healthcare in Los Angeles.",
            "Get the HIPAA rules for a clinic in New York City.",
            "Research ALL compliance requirements for a manufacturing company in Chicago.",
        ],
    },
    {
        "key": "ask",
        "label": "Ask the catalog",
        "description": "Semantic Q&A over the jurisdiction-data DB. Grounded, cited "
                       "answers from what's already researched.",
        "title": "Ask",
        "focus": (
            "Answer regulatory questions ONLY from the CATALOG RESULTS in the corpus "
            "(`req:` records). Cite the `req:` ids that support each statement. If the "
            "catalog does not cover it, say so plainly — never guess a rate, date, or "
            "rule. Emit no proposal in this mode."
        ),
        "starters": [
            "What's the tipped minimum wage in Chicago?",
            "What paid-sick-leave rules apply in California?",
            "Summarize the OSHA recordkeeping requirements we have on file for Texas.",
        ],
    },
    {
        "key": "check_sources",
        "label": "Check sources",
        "description": "Check the catalog's source links for an industry/jurisdiction — "
                       "find dead or unreachable citations (data quality).",
        "title": "Check sources",
        "focus": (
            "You audit citation LINK health. When the admin names a place (optionally an "
            "industry), emit ONE proposal: {\"kind\":\"check_sources\", \"state\":"
            "\"<2-letter>\", \"city\":\"<city or null>\", \"rationale\":\"<one sentence>\"}. "
            "The run fetches every source URL in that jurisdiction chain and flags dead "
            "ones. If ambiguous, ask a short clarifying question and emit no proposal."
        ),
        "starters": [
            "Check sources for healthcare compliance in New York.",
            "Are our California citation links still live?",
            "Find broken source links for Texas.",
        ],
    },
    {
        "key": "scope",
        "label": "Scope coverage",
        "description": "Narrate where the catalog is thin for an industry across "
                       "jurisdictions, and propose what to research next.",
        "title": "Scope",
        "focus": (
            "You help the admin decide WHAT to build next. Read the COVERAGE SNAPSHOT in "
            "the corpus and narrate where the catalog is thin. You MAY emit one research "
            "proposal (same shape as the research mode) for the gap you'd fill first. "
            "Ground claims about coverage in the snapshot; do not invent counts."
        ),
        "starters": [
            "Where are we thin on manufacturing coverage?",
            "What should we research next for California?",
            "Which core labor categories are unchecked for Chicago?",
        ],
    },
)

_TEMPLATE_BY_KEY = {t["key"]: t for t in PILOT_TEMPLATES}
_MODE_KEYS = tuple(t["key"] for t in PILOT_TEMPLATES)
_PROPOSAL_MODES = {"research", "scope", "check_sources"}


def get_template(key: Optional[str]) -> Optional[dict]:
    return _TEMPLATE_BY_KEY.get((key or "").strip() or "")


def template_catalog() -> list[dict]:
    return [{k: v for k, v in t.items() if k != "focus"} for t in PILOT_TEMPLATES]


def _mode_focus(key: Optional[str]) -> str:
    t = get_template(key)
    return f"SESSION MODE — {t['label']}. {t['focus']}" if t else ""


# --------------------------------------------------------------------------- #
# Corpus builders (per mode)
# --------------------------------------------------------------------------- #

async def build_ask_corpus(conn, query: str,
                           jurisdiction_ids: Optional[List[UUID]] = None,
                           industry_tags: Optional[List[str]] = None) -> dict:
    """Semantic hits over the catalog as `req:` cid records + a flat index."""
    from .compliance_rag import ComplianceRAGService
    from .embedding_service import get_embedding_service

    try:
        rag = ComplianceRAGService(get_embedding_service())
        hits = await rag.search_requirements(
            query, conn, jurisdiction_ids=jurisdiction_ids, industry_tags=industry_tags,
            top_k=_MAX_ASK_HITS, min_similarity=0.25, statuses=["active"],
        )
    except Exception:  # noqa: BLE001 — a dead embed path shouldn't 500 the chat
        logger.exception("compliance_pilot: ask search failed")
        hits = []

    records, index = [], {}
    for h in hits:
        cid = f"req:{h['requirement_id']}"
        val = h.get("current_value") or ""
        summary = f"{h.get('jurisdiction_name') or ''} · {h.get('category') or ''} · " \
                  f"{h.get('title') or ''}{(' = ' + val) if val else ''}"
        rec = {
            "cid": cid, "summary": summary.strip(" ·"),
            "citation": h.get("statute_citation"), "source_url": h.get("source_url"),
            "state": None, "city": None,  # deep-link resolved client-side by jurisdiction_name
            "jurisdiction_name": h.get("jurisdiction_name"),
        }
        records.append(rec)
        index[cid] = rec
    return {"records": records, "index": index}


async def build_scope_snapshot(conn, state: str, city: Optional[str],
                               industry_tag: Optional[str]) -> dict:
    """Coverage snapshot for a coordinate: chain + general coverage map + existing
    row counts. Used both as research/scope chat corpus and the proposal preview."""
    from .scope_registry.jurisdiction_chain import resolve_jurisdiction_chain
    from .vertical_coverage import general_coverage_map

    chain = await resolve_jurisdiction_chain(conn, state, city)
    ids = chain["ids"]
    cov = await general_coverage_map(conn, ids) if ids else {}
    covered = sum(1 for s in cov.values() if s == "covered")
    empty = sum(1 for s in cov.values() if s == "empty")
    unchecked = sum(1 for s in cov.values() if s == "unchecked")

    existing = 0
    industry_existing = 0
    if ids:
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements "
            "WHERE jurisdiction_id = ANY($1::uuid[]) AND status='active'",
            ids,
        ) or 0
        if industry_tag:
            industry_existing = await conn.fetchval(
                "SELECT COUNT(*) FROM jurisdiction_requirements "
                "WHERE jurisdiction_id = ANY($1::uuid[]) AND status='active' "
                "AND applicable_industries && $2::text[]",
                ids, [industry_tag],
            ) or 0
    return {
        "state": state, "city": city, "city_found": chain.get("city_found", False),
        "state_found": chain.get("state_found", False),
        "general_coverage": {"covered": covered, "empty": empty, "unchecked": unchecked},
        "existing_active_rows": int(existing),
        "industry_active_rows": int(industry_existing),
    }


def _scope_corpus_text(snapshot: Optional[dict]) -> str:
    if not snapshot:
        return "(no coordinate resolved yet — name an industry and a place)"
    g = snapshot["general_coverage"]
    return (
        f"COVERAGE SNAPSHOT for {snapshot.get('city') or ''} {snapshot['state']}:\n"
        f"- general (core-labor) categories: {g['covered']} covered, {g['empty']} nothing-applies, "
        f"{g['unchecked']} never checked\n"
        f"- active catalog rows in this chain: {snapshot['existing_active_rows']} "
        f"(industry-specific: {snapshot['industry_active_rows']})\n"
        f"- city row found: {snapshot.get('city_found')}"
    )


def _ask_corpus_text(corpus: dict) -> str:
    recs = corpus.get("records") or []
    if not recs:
        return "(the catalog returned no matching requirements)"
    return "CATALOG RESULTS (cite these `req:` ids):\n" + "\n".join(
        f"- [{r['cid']}] {r['summary']}" for r in recs
    )


# --------------------------------------------------------------------------- #
# Grounded turn
# --------------------------------------------------------------------------- #

_SYSTEM = """You are the Compliance Pilot, an assistant that helps a platform admin BUILD and QUALITY-CHECK a shared US compliance catalog (jurisdiction_requirements). You are grounded and honest: cite only ids present in the CORPUS, never invent a rate, date, statute, or count.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<direct answer / next step, <=120 words, plain prose>",
 "citations": [{"point": "<a factual observation>", "cited_ids": ["req:<uuid>", ...]}],
 "proposal": <one action proposal object, or null>}

Rules:
- `assistant_text` leads with the answer or the action you're proposing. No headings.
- `citations` may cite ONLY ids that appear in the CORPUS. Emit [] when the mode has no corpus records or you cite nothing.
- `proposal` is null unless the SESSION MODE explicitly allows one AND the admin's message names enough to act. Emit at most ONE. Never fabricate a proposal to seem useful.
"""


def _corpus_text(mode: str, corpus: dict, snapshot: Optional[dict]) -> str:
    if mode == "ask":
        return _ask_corpus_text(corpus)
    if mode in ("research", "scope"):
        return _scope_corpus_text(snapshot)
    if mode == "check_sources":
        return _scope_corpus_text(snapshot)
    return "(no corpus)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def _build_prompt(mode: str, corpus: dict, snapshot: Optional[dict],
                  history: list[dict], latest: str) -> str:
    focus = _mode_focus(mode)
    return f"""{_SYSTEM}
{focus}

CORPUS (the ONLY records you may cite):
{_corpus_text(mode, corpus, snapshot)}

CONVERSATION (oldest first):
{_history_text(history)}

LATEST ADMIN MESSAGE:
{latest}
"""


def _coerce_proposal(raw, mode: str) -> Optional[dict]:
    """Clamp a model proposal into a whitelisted shape. Pure. None if the mode
    disallows proposals or the object is unusable. Validation (does the industry /
    jurisdiction resolve?) is done separately, against the DB, read-only."""
    if mode not in _PROPOSAL_MODES or not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in ("research", "check_sources"):
        return None
    state = str(raw.get("state") or "").strip().upper()[:2]
    if not state:
        return None
    city = raw.get("city")
    city = str(city).strip()[:120] if city else None
    out = {
        "kind": kind, "state": state, "city": city,
        "rationale": str(raw.get("rationale") or "").strip()[:300],
    }
    if kind == "research":
        out["industry"] = str(raw.get("industry") or "").strip()[:80]
        cats = raw.get("categories")
        out["categories"] = [str(c).strip() for c in cats][:60] if isinstance(cats, list) else None
    return out


def _coerce_turn(data, mode: str) -> dict:
    if not isinstance(data, dict):
        data = {}
    cits = data.get("citations")
    citations = []
    if isinstance(cits, list):
        for item in cits[:_MAX_CITED]:
            if not isinstance(item, dict):
                continue
            point = str(item.get("point") or "").strip()[:_TEXT_CAP]
            raw = item.get("cited_ids")
            ids = [str(c) for c in raw if c] if isinstance(raw, list) else []
            if point:
                citations.append({"point": point, "cited_ids": ids})
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "citations": citations,
        "proposal": _coerce_proposal(data.get("proposal"), mode),
    }


async def run_chat_turn(mode: str, corpus: dict, snapshot: Optional[dict],
                        history: list[dict], latest: str):
    """Async generator of SSE dicts for one turn: a status tick, then one validated
    `result`. The citation gate runs before anything reaches the admin. Proposal
    validation against the DB happens in the route (needs a connection)."""
    from app.matcha.services.legal_defense import validate_citations, _parse_json  # lazy — see module note

    yield {"type": "status", "message": "Thinking…"}
    try:
        prompt = _build_prompt(mode, corpus, snapshot, history, latest)
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(model=MODEL, contents=prompt),
            timeout=_GEMINI_TIMEOUT,
        )
        result = _coerce_turn(_parse_json(getattr(resp, "text", "") or ""), mode)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "The model timed out — please try again."}
        return
    except Exception:
        logger.exception("compliance_pilot: chat turn failed")
        yield {"type": "error", "message": "That failed — please try again."}
        return

    index = corpus.get("index", {})
    clean, dropped = validate_citations(result.get("citations"), index)
    result["citations"] = clean
    if dropped:
        result["dropped_citations"] = dropped
    if not result["assistant_text"]:
        result["assistant_text"] = "I couldn't produce a response this time — try rephrasing."
    yield {"type": "result", "data": result}


# --------------------------------------------------------------------------- #
# Proposal resolution (read-only) + category defaults
# --------------------------------------------------------------------------- #

async def default_categories(conn, industry_tag: Optional[str]) -> List[str]:
    """General (core-labor) categories + the industry's own categories."""
    rows = await conn.fetch(
        "SELECT slug FROM compliance_categories "
        "WHERE industry_tag IS NULL OR ($1::text IS NOT NULL AND industry_tag = $1)",
        industry_tag,
    )
    return [r["slug"] for r in rows]


async def resolve_proposal(conn, proposal: dict) -> tuple[Optional[dict], List[str]]:
    """Validate a proposal against the DB, READ-ONLY (never creates a jurisdiction).
    Returns (resolved | None, errors). A resolved proposal carries the concrete
    coordinate + a coverage preview the ProposalCard renders."""
    from .compliance_service import _resolve_industry
    from .scope_registry.jurisdiction_chain import resolve_jurisdiction_chain

    errors: List[str] = []
    kind = proposal["kind"]
    state = (proposal.get("state") or "").upper()
    city = proposal.get("city")

    if not state or len(state) != 2 or not state.isalpha():
        errors.append("Need a valid 2-letter state — say which state.")
        return None, errors

    chain = await resolve_jurisdiction_chain(conn, state, city)
    if not chain.get("state_found"):
        errors.append(f"No jurisdiction on file for state {state}.")
        return None, errors

    resolved: Dict[str, Any] = {
        "kind": kind, "state": state, "city": city,
        "city_found": chain.get("city_found", False),
        "rationale": proposal.get("rationale", ""),
    }

    if kind == "research":
        industry_tag = _resolve_industry(proposal.get("industry"))
        if not industry_tag:
            errors.append(f"Couldn't resolve the industry '{proposal.get('industry')}'.")
            return None, errors
        cats = proposal.get("categories")
        cat_labels: Dict[str, str] = {}
        if cats:
            # Match each named topic by slug OR normalized display name (the model
            # may return "clinical safety" or "clinical_safety"). Named-but-unmatched
            # is an error — never silently widen one topic to the whole catalog.
            norm = {_norm_cat(c): c for c in cats}
            rows = await conn.fetch(
                "SELECT slug, name FROM compliance_categories "
                "WHERE industry_tag IS NULL OR industry_tag = $1", industry_tag)
            categories = []
            for r in rows:
                if _norm_cat(r["slug"]) in norm or _norm_cat(r["name"]) in norm:
                    categories.append(r["slug"])
                    cat_labels[r["slug"]] = r["name"]
            if not categories:
                errors.append(f"Couldn't match any category to '{', '.join(cats)}'. "
                              "Name a topic like 'clinical safety' or 'HIPAA', or say 'all requirements'.")
                return None, errors
        else:
            categories = await default_categories(conn, industry_tag)
            rows = await conn.fetch(
                "SELECT slug, name FROM compliance_categories WHERE slug = ANY($1::text[])", categories)
            cat_labels = {r["slug"]: r["name"] for r in rows}
        snapshot = await build_scope_snapshot(conn, state, city, industry_tag)
        resolved.update({
            "industry_tag": industry_tag,
            "categories": categories,
            "category_labels": [cat_labels.get(c, c) for c in categories],
            "category_count": len(categories),
            "coverage": snapshot["general_coverage"],
            "existing_active_rows": snapshot["existing_active_rows"],
        })
    else:  # check_sources
        url_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements "
            "WHERE jurisdiction_id = ANY($1::uuid[]) AND source_url IS NOT NULL",
            chain["ids"],
        ) or 0
        resolved.update({
            "chain_ids": [str(i) for i in chain["ids"]],
            "source_urls": int(url_rows),
        })
    return resolved, errors


def _codify_gate(regulation_key, citation, source_url, source_url_status):
    """Deterministic 'can this become AUTHORITATIVE?' check. Returns
    (ok, reason, domain_class). Authoritative demands the actual primary legal
    source — never a blog/aggregator link. A failed gate never blocks the approve;
    the row just stays live-but-uncodified with the reason shown."""
    from .compliance_evals.authority import classify_domain
    domain_class = classify_domain(source_url) if source_url else "missing"
    if not regulation_key:
        return False, "no regulation key", domain_class
    if not citation or not str(citation).strip():
        return False, "no statute citation from research", domain_class
    if domain_class != "primary":
        return False, f"source is not a primary legal source ({domain_class})", domain_class
    if source_url_status == "dead":
        return False, "source link is dead", domain_class
    return True, None, domain_class


# --------------------------------------------------------------------------- #
# Action runner (background task — owns its connections)
# --------------------------------------------------------------------------- #

async def _set_action(conn, action_id: UUID, **fields):
    if not fields:
        return
    sets, vals = [], []
    for i, (k, v) in enumerate(fields.items(), start=1):
        if k in ("progress", "result"):
            sets.append(f"{k} = ${i}::jsonb"); vals.append(json.dumps(v))
        elif k == "staged_ids":
            sets.append(f"{k} = ${i}::uuid[]"); vals.append(v)
        elif k == "status" and v in ("done", "failed"):
            sets.append(f"{k} = ${i}"); vals.append(v)
            sets.append("finished_at = NOW()")
        else:
            sets.append(f"{k} = ${i}"); vals.append(v)
    vals.append(action_id)
    await conn.execute(
        f"UPDATE compliance_pilot_actions SET {', '.join(sets)} WHERE id = ${len(vals)}",
        *vals,
    )


async def run_action(action_id: UUID, actor_id: Optional[UUID]):
    """Execute a proposed action. Runs as a detached background task and owns ALL
    its connections (never a request-scoped one). Marks the row done/failed."""
    try:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT kind, params FROM compliance_pilot_actions WHERE id = $1", action_id)
        if not row:
            return
        kind = row["kind"]
        params = row["params"]
        if isinstance(params, str):
            params = json.loads(params)

        if kind == "research":
            await _run_research(action_id, actor_id, params)
        elif kind == "check_sources":
            await _run_check_sources(action_id, actor_id, params)
    except Exception as exc:  # noqa: BLE001 — a failed run must land as 'failed', not vanish
        logger.exception("compliance_pilot: action %s failed", action_id)
        try:
            async with get_connection() as conn:
                await _set_action(conn, action_id, status="failed",
                                  result={"error": str(exc)[:500]})
        except Exception:
            logger.exception("compliance_pilot: could not mark action %s failed", action_id)


async def _run_research(action_id: UUID, actor_id, params: dict):
    from .compliance_service import (research_specialization_for_jurisdiction,
                                     _get_or_create_jurisdiction)

    state = params["state"]
    city = params.get("city")
    industry_tag = params["industry_tag"]
    categories = params["categories"]

    async with get_connection() as conn:
        await _set_action(conn, action_id,
                          progress={"phase": "researching",
                                    "message": f"Researching {industry_tag} for {city or state}…",
                                    "categories": len(categories)})
        # Jurisdiction creation happens HERE (confirm time), never at chat/validation.
        jid = await _get_or_create_jurisdiction(conn, city or "", state)
        await set_change_context(conn, "pilot_research", actor_id)
        # Fence the staged-row recovery to rows this run created. route_by_level
        # files rows on the shared federal/state chain nodes, where the admin queue
        # (and other pilot sessions) also stage pending rows in the same categories;
        # without the timestamp fence, "Approve & codify all" would sweep in and
        # activate THEIR un-reviewed rows. (Residual: a truly concurrent run in the
        # same category+node within the same second — narrow; accepted for v1.)
        # NOTE(fast-follow): this path does NOT read/write jurisdiction_vertical_coverage,
        # so the nightly sweep may re-research what the pilot paid for, and ledger
        # `empty` cells are re-spent. Ledger integration is its own change.
        # created_at is `timestamp WITHOUT time zone` (naive) — match it, or asyncpg
        # can't compare a tz-aware NOW() against the column.
        run_started = await conn.fetchval("SELECT NOW()::timestamp")
        result = await research_specialization_for_jurisdiction(
            conn, jid, categories, industry_tag,
            route_by_level=True, initial_status="pending",
        )
        written = result.get("jurisdictions_written") or [jid]
        staged = await conn.fetch(
            "SELECT r.id, r.title, r.jurisdiction_level, r.regulation_key, r.category, "
            "       r.source_url, r.source_url_status, r.metadata, j.state, j.city "
            "FROM jurisdiction_requirements r JOIN jurisdictions j ON j.id = r.jurisdiction_id "
            "WHERE r.status='pending' AND r.jurisdiction_id = ANY($1::uuid[]) "
            "AND r.category = ANY($2::text[]) AND r.created_at >= $3",
            written, categories, run_started,
        )
        staged_ids = [r["id"] for r in staged]
        # Per-policy detail for the checklist card — provenance + the codify gate,
        # computed once here so the frontend needs no extra call.
        staged_rows = []
        for r in staged:
            meta = r["metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            meta = meta or {}
            citation = meta.get("research_citation") or (
                (meta.get("grounded_citations") or [None])[0])
            ok, reason, domain_class = _codify_gate(
                r["regulation_key"], citation, r["source_url"], r["source_url_status"])
            staged_rows.append({
                "id": str(r["id"]), "title": r["title"],
                "jurisdiction_level": r["jurisdiction_level"],
                "regulation_key": r["regulation_key"], "category": r["category"],
                "source_url": r["source_url"], "source_domain_class": domain_class,
                "source_url_status": r["source_url_status"],
                "research_citation": citation,
                "state": r["state"], "city": r["city"],
                "gate_ok": ok, "gate_reason": reason,
            })
        await _set_action(
            conn, action_id, status="done", staged_ids=staged_ids,
            progress={"phase": "done"},
            result={
                "new": result.get("new", 0),
                "staged": len(staged_ids),
                "staged_rows": staged_rows,
                "codifiable": sum(1 for s in staged_rows if s["gate_ok"]),
                "categories_written": result.get("categories") or [],
                "failed": result.get("failed") or [],
                "state": state, "city": city, "industry_tag": industry_tag,
            },
        )


async def _run_check_sources(action_id: UUID, actor_id, params: dict):
    from .compliance_evals.authority import run_authority
    from .scope_registry.jurisdiction_chain import resolve_jurisdiction_chain

    state = params["state"]
    city = params.get("city")

    async with get_connection() as conn:
        await _set_action(conn, action_id,
                          progress={"phase": "checking",
                                    "message": f"Checking source links for {city or state}…"})
        chain = await resolve_jurisdiction_chain(conn, state, city)
        report = await run_authority(conn, chain["ids"])
        findings = report.get("findings") or []

        dead = [f for f in findings if f.get("finding_type") == "dead_url"]
        unreachable = [f for f in findings if f.get("finding_type") == "url_unreachable"]
        missing = [f for f in findings if f.get("finding_type") == "missing_citation"]

        # Write-back: mark ONLY genuinely dead links. Timeouts (url_unreachable) are
        # left alone. No updated_at bump (would mass-stale the embeddings); stamp
        # source_checked_at + label for the jrver01 trigger.
        dead_ids = list({f["requirement_id"] for f in dead if f.get("requirement_id")})
        if dead_ids:
            await set_change_context(conn, "pilot_check_sources", actor_id)
            await conn.execute(
                "UPDATE jurisdiction_requirements "
                "SET source_url_status='dead', source_checked_at=NOW() "
                "WHERE id = ANY($1::uuid[])",
                dead_ids,
            )

        # Top dead rows for the card (with coordinate for Library deep-links).
        dead_rows = []
        if dead_ids:
            rows = await conn.fetch(
                "SELECT r.id, r.category, r.source_url, UPPER(j.state) AS state, LOWER(j.city) AS city "
                "FROM jurisdiction_requirements r JOIN jurisdictions j ON j.id = r.jurisdiction_id "
                "WHERE r.id = ANY($1::uuid[]) LIMIT 20",
                dead_ids,
            )
            dead_rows = [{"id": str(r["id"]), "category": r["category"],
                          "source_url": r["source_url"], "state": r["state"], "city": r["city"]}
                         for r in rows]

        await _set_action(
            conn, action_id, status="done", progress={"phase": "done"},
            result={
                "checked": len(chain["ids"]),
                "dead": len(dead_ids), "unreachable": len(unreachable),
                "missing_citation": len(missing),
                "dead_rows": dead_rows,
                "state": state, "city": city,
            },
        )
