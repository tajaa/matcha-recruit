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
- ``profile``                        — the company handbook profile record
- ``law:<state>-<cat>-<title-slug>`` — one record per applicable jurisdiction requirement
- ``handbook:<uuid>``                — one record per existing handbook section
- ``policy:<uuid>``                  — one record per existing policy
- ``playbook:<slug>``                — one record per industry playbook baseline section

Law cids are derived from the requirement's *content* (state + category + title),
not its position in the fetch, because `_fetch_state_requirements` orders by
effective/updated date — a jurisdiction data refresh reorders the rows. Cids used
to carry the enumeration ordinal (`law:<state>-<cat>-<n>`), so a refresh silently
re-pointed every stored citation and cited requirements fell back to "uncovered".
Citations stored under that old scheme are recovered by `lookup_record`, which
matches on the `state-category` prefix when it names exactly one requirement.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

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
            SELECT id, title, category, status, description, content
            FROM policies
            WHERE company_id = $1 AND status IN ('active', 'draft')
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_EXISTING_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("handbook_pilot: existing-policy fetch failed for %s", company_id)

    # Precedence-resolved compliance floor — the GOVERNING requirement per
    # category (federal → state → local), which is what a drafting tool should
    # write against; `requirements` above is the flat overlapping list.
    # `build_compliance_context` is already Redis-cached with a per-key build
    # lock (120s, `mw:compliance_ctx:{company_id}`) and the chains survive the
    # cache round-trip, so the expensive resolution runs at most once per company
    # per window no matter which pilot asks — no second cache layer here.
    reasoning_chains: list = []
    try:
        from . import matcha_work_node
        result = await matcha_work_node.build_compliance_context(company_id)
        reasoning_chains = list(getattr(result, "reasoning_chains", None) or [])
    except Exception:  # noqa: BLE001 — same degrade-to-empty as every source here
        logger.warning("handbook_pilot: compliance floor fetch failed for %s", company_id)

    return {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": session.get("industry"),
        "reasoning_chains": reasoning_chains,
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
    state -> [requirement dict] map from handbook_service._fetch_state_requirements.

    The cid is derived from the requirement's *content* (state + category +
    title), never its position in the fetch — see the module docstring. Two
    requirements can legitimately share state + category + title (a state and a
    city minimum wage), so a collision qualifies every colliding member with its
    jurisdiction. Members still identical after that are indistinguishable on
    content and get an ordinal over a sorted key, so the assignment doesn't
    depend on fetch order either.

    Disambiguation is applied to ALL members of a colliding group, not just the
    later ones: giving the first arrival the bare cid would hand a different
    requirement the bare cid after a reorder, which is the bug this scheme
    exists to kill."""
    recs: list[dict] = []
    for state, reqs in (requirements or {}).items():
        rows = [r for r in (reqs or [])[:_LAW_PER_STATE_CAP] if isinstance(r, dict)]

        def _parts(r: dict) -> tuple[str, str, str, str]:
            title = r.get("title") or r.get("category") or "requirement"
            return (
                str(title),
                str(r.get("category") or title),
                str(r.get("jurisdiction_name") or state),
                f"law:{_slug(state)}-{_slug(r.get('category') or title)}-{_slug(title)}",
            )

        base_counts: dict[str, int] = {}
        qual_counts: dict[str, int] = {}
        for r in rows:
            _, _, juris, base = _parts(r)
            base_counts[base] = base_counts.get(base, 0) + 1
            qual_counts[f"{base}-{_slug(juris)}"] = qual_counts.get(f"{base}-{_slug(juris)}", 0) + 1

        # Content sort key for the last-resort ordinal. Keys on EVERY field, not
        # a hand-picked few: two rows tying here are indistinguishable on content,
        # so which one wins the ordinal cannot matter. Picking a subset would let
        # rows that differ in an unlisted field (source_url, numeric_value) tie,
        # and a stable sort would then hand out ordinals by fetch order —
        # re-pointing citations on a data refresh, the bug this scheme kills.
        def _tiebreak(r: dict) -> str:
            return repr(sorted((str(k), str(v)) for k, v in r.items()))

        ordinals: dict[int, int] = {}
        next_ordinal: dict[str, int] = {}
        for r in sorted(rows, key=_tiebreak):
            _, _, juris, base = _parts(r)
            qual = f"{base}-{_slug(juris)}"
            if base_counts[base] > 1 and qual_counts[qual] > 1:
                ordinals[id(r)] = next_ordinal.get(qual, 0)
                next_ordinal[qual] = next_ordinal.get(qual, 0) + 1

        # Mint in content order (never fetch order), then emit in fetch order.
        # Groups are disambiguated independently, so a qualified cid from one
        # group can still equal a bare cid from another (category `minimum_wage`
        # + title "Minimum wage" in San Francisco collides with title "Minimum
        # wage San Francisco"). build_corpus keys the index by cid and would
        # silently drop the loser — force a suffix instead.
        minted: set[str] = set()
        cid_by_row: dict[int, str] = {}
        for r in sorted(rows, key=_tiebreak):
            _, _, juris, base = _parts(r)
            cid = base
            if base_counts[base] > 1:
                cid = f"{base}-{_slug(juris)}"
                if qual_counts[cid] > 1:
                    cid = f"{cid}-{ordinals[id(r)] + 1}"
            if cid in minted:
                n = 2
                while f"{cid}-x{n}" in minted:
                    n += 1
                cid = f"{cid}-x{n}"
            minted.add(cid)
            cid_by_row[id(r)] = cid

        for r in rows:
            title, category, juris, _ = _parts(r)
            cid = cid_by_row[id(r)]

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
                # Structured fields the viewer groups + joins on, so the client
                # never has to parse `ref` apart.
                "state": str(state),
                "title": str(title),
                "category": category,
                "jurisdiction": str(juris),
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


def _floor_records(reasoning_chains: list | None) -> list[dict]:
    """One record per GOVERNING compliance requirement, deduped across
    locations. `reasoning_chains` is the structured list from
    `matcha_work_node.build_compliance_context`.

    The cid keys on what makes the obligation unique — governing level,
    jurisdiction, category — never on the location that surfaced it, so the same
    state rule reached from three offices is one citable record whose
    `applies_to` names all three."""
    by_cid: dict[str, dict] = {}
    for chain in reasoning_chains or []:
        if not isinstance(chain, dict):
            continue
        label = str(chain.get("location_label") or "").strip()
        for cat in chain.get("categories") or []:
            if not isinstance(cat, dict) or not cat.get("category"):
                continue
            category = str(cat["category"])
            level = str(cat.get("governing_level") or "unknown")

            governing = next(
                (lv for lv in (cat.get("all_levels") or [])
                 if isinstance(lv, dict) and lv.get("is_governing")),
                None,
            )
            juris = str((governing or {}).get("jurisdiction_name") or level)
            cid = f"floor:{_slug(level)}-{_slug(juris)}-{_slug(category)}"

            existing = by_cid.get(cid)
            if existing is not None:
                # Same obligation reached from another location — widen the
                # scope note, don't mint a second cid.
                if label and label not in existing["applies_to"]:
                    existing["applies_to"].append(label)
                continue

            title = str((governing or {}).get("title") or _hum(category))
            bits = [title]
            value = (governing or {}).get("current_value")
            if value:
                bits.append(f"requirement: {value}")
            if cat.get("precedence_type"):
                bits.append(f"precedence {cat['precedence_type']}")
            citation = cat.get("legal_citation") or (governing or {}).get("statute_citation")
            if citation:
                bits.append(f"cite {citation}")
            if cat.get("reasoning_text"):
                bits.append(str(cat["reasoning_text"])[:280])

            by_cid[cid] = {
                "cid": cid,
                "ref": f"{_hum(level)} · {juris}: {title}",
                "summary": " — ".join(bits) + ".",
                "when": str((governing or {}).get("effective_date") or "current"),
                # Structured fields so the client can group without parsing `ref`.
                "category": category,
                "governing_level": level,
                "jurisdiction": juris,
                "source_url": (governing or {}).get("source_url"),
                "applies_to": [label] if label else [],
            }
    return list(by_cid.values())


# Full-text injection. A corpus record's `summary` is an INDEX ENTRY — sections
# cap at 280 chars and policy records carry no body at all — which is fine for a
# citation footer and useless to draft a replacement from: the model was being
# asked to revise the company's attendance policy from a preview of it. So the
# prompt gets the real bodies while the STORED records stay index-sized (they
# ride in message/draft metadata; HR Pilot's invariant, kept here).
_FULL_TEXT_PER_RECORD = 4_000     # chars of one section/policy body
_FULL_TEXT_BUDGET = 120_000       # total chars of body text in one prompt


def _full_text_map(grounding: dict) -> tuple[dict[str, str], int]:
    """cid → full body for existing sections and policies, per-record capped and
    stopped at a total budget. Returns (map, records_that_missed_the_budget) —
    the overflow falls back to its 280-char summary and is named in a note, so a
    truncated corpus never reads as a complete one. Pure."""
    out: dict[str, str] = {}
    spent = 0
    overflow = 0
    for prefix, rows, field in (("handbook", grounding.get("sections"), "content"),
                                ("policy", grounding.get("policies"), "content")):
        for row in rows or []:
            body = str(row.get(field) or "").strip()
            if not body:
                continue
            clipped = body[:_FULL_TEXT_PER_RECORD]
            if len(body) > _FULL_TEXT_PER_RECORD:
                clipped += "\n… (body truncated)"
            if spent + len(clipped) > _FULL_TEXT_BUDGET:
                overflow += 1
                continue
            spent += len(clipped)
            out[f"{prefix}:{row.get('id')}"] = clipped
    return out, overflow


def build_corpus(grounding: dict) -> dict:
    """Assemble the grounding corpus `{sources, index, notes}` — the same shape
    Legal/Broker Pilot use, so `validate_citations` works unchanged. Pure.

    Also carries `full_text`: cid → the record's real body, used only when
    rendering the prompt (see `_full_text_map`). It is deliberately NOT folded
    into the records — those are stored."""
    grounding = grounding or {}
    sources = {
        "profile": {"label": "Company profile",
                    "records": _profile_record(grounding.get("profile"))},
        "compliance_floor": {"label": "Governing compliance requirements",
                             "records": _floor_records(grounding.get("reasoning_chains"))},
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
    if not sources["compliance_floor"]["records"]:
        # Same wording HR Pilot uses — without it, a corpus carrying only the
        # flat overlapping list reads as if the governing rule were established.
        notes.append(
            "No precedence-resolved compliance floor available — answers ground on "
            "the flat per-state requirement list only."
        )
    full_text, overflow = _full_text_map(grounding)
    if overflow:
        notes.append(
            f"{overflow} existing section(s)/policy(ies) exceeded the prompt's full-text "
            "budget and are represented by their summary only — do not treat their "
            "wording as fully shown."
        )
    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}
    return {"sources": sources, "index": index, "notes": notes, "full_text": full_text}


# Law cids minted under the old positional scheme: `law:<state>-<category>-<n>`.
_LEGACY_LAW_CID = re.compile(r"^(law:.+)-(\d+)$")


def lookup_record(cid, index: dict) -> dict | None:
    """Resolve a STORED citation to its corpus record, or None.

    Read paths only (`resolve_citations`, coverage) — never the citation gate.
    A cid the model emits must exact-match the index or be dropped; routing new
    citations through the legacy recovery below would launder an invented id
    into a real requirement.

    Citations written before law cids became content-derived carry an ordinal
    (`law:ca-meal-rest-breaks-0`) that no longer names anything, but the
    state+category it encodes still does. Recovery compares the legacy prefix
    against each record's *structured* state/category fields — exact slug
    equality, so category `paid-leave` never bleeds into `paid-leave-and-sick-time`,
    and a current-scheme cid whose title slug happens to end in digits
    (`law:ca-osha-recordkeeping-osha-form-300`) parses to a prefix matching no
    state+category pair and correctly stays unresolved.

    When two or more current requirements share a state+category (a state AND a
    city minimum wage), the lost ordinal was the only thing that told them apart
    — refuse to guess; the viewer flags the citation as out of scope. Pure."""
    index = index or {}
    if not isinstance(cid, str):
        return None
    rec = index.get(cid)
    if rec is not None:
        return rec
    m = _LEGACY_LAW_CID.match(cid)
    if not m:
        return None
    prefix = m.group(1)
    matches = [
        r for c, r in index.items()
        if c.startswith("law:") and _legacy_prefix(r) == prefix
    ]
    return matches[0] if len(matches) == 1 else None


def _legacy_prefix(rec: dict) -> str:
    """The `law:<state>-<category>` stem the old positional scheme built cids on."""
    title = rec.get("title") or "requirement"
    return f"law:{_slug(rec.get('state'))}-{_slug(rec.get('category') or title)}"


def canonical_cid(cid, index: dict) -> str:
    """The canonical cid a stored citation resolves to (itself, unless it's a
    legacy positional law cid). Pure."""
    rec = lookup_record(cid, index)
    return (rec or {}).get("cid") or cid


# --------------------------------------------------------------------------- #
# Grounded AI turn — HR policy drafter, grounded in the corpus.
# --------------------------------------------------------------------------- #

_SYSTEM = """You are an HR handbook and policy drafting assistant working for a company's HR administrator. You draft employee-handbook sections and standalone workplace policies, grounding EVERY enforceable clause in the EVIDENCE CORPUS below: the company profile (`profile`), the GOVERNING requirement per compliance category after federal/state/local precedence is resolved (`floor:` IDs), the full list of jurisdiction requirements that apply to the company's work locations (`law:` IDs), the company's existing handbook sections (`handbook:` IDs) and existing policies (`policy:` IDs), and the industry playbook baseline (`playbook:` IDs).

HARD RULES:
- Cite ONLY the bracketed IDs that appear in the EVIDENCE CORPUS. NEVER invent a statute, dollar figure, deadline, or ID.
- When a `floor:` record and a `law:` record cover the same category, the `floor:` record is the GOVERNING requirement — draft to it and cite it. The `law:` list is every overlapping rule, including ones a stricter jurisdiction supersedes; drafting to one of those instead states the wrong obligation.
- Put those corpus IDs ONLY in the `cited_ids` array. NEVER write a corpus ID (like `law:…` or `handbook:…`) into the `content` prose — `content` is employee-facing handbook text. (Placeholder tokens like [HR_CONTACT_EMAIL] are fine in content.)
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


# Inline corpus-id tokens the model embeds in prose despite the prompt asking for
# cited_ids only (e.g. "...report concerns [handbook:0e29…]."). Colon-form
# (law:/handbook:/policy:/playbook:) is unambiguous; `profile` is the one bare
# cid. `(?!\()` protects markdown links [text](url), mirroring the frontend
# highlightPlaceholders guard; ALL-CAPS placeholder tokens like [HR_CONTACT_EMAIL]
# never match (the prefixes are lowercase keywords). Leading `[ \t]*` eats the
# space before the tag so removal doesn't leave a double space.
_INLINE_CID = re.compile(
    r"[ \t]*\[(?:(?:law|handbook|policy|playbook):[^\]\s]+|profile)\](?!\()"
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


# --------------------------------------------------------------------------- #
# Handbook viewer — assemble the session's drafts into a live, cataloged
# document and resolve each draft's citations back to real corpus records.
# Pure (no DB / no Gemini); the route hands it drafts + a freshly-built corpus.
# --------------------------------------------------------------------------- #

_SEVERITY_ORDER = {"critical": 0, "important": 1, "recommended": 2}


def _coerce_cid_list(raw) -> list[str]:
    """Drafts loaded via the route already have `citations` JSON-parsed, but be
    defensive: accept a list or a JSON-encoded string, keep only str cids."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(raw, list):
        return []
    return [c for c in raw if isinstance(c, str)]


def resolve_citations(cids, index: dict) -> list[dict]:
    """Map each stored citation cid to its human-readable corpus record. Unknown
    cids (a requirement that aged out of scope since the draft was proposed)
    resolve to a minimal, clearly-flagged record so the viewer never silently
    hides a citation. A legacy positional cid resolves to its record and is
    displayed under the canonical cid.

    Deduped by RESOLVED cid: two legacy cids under one state+category collapse
    onto the same record, and the viewer keys its citation cards on `cid`. Pure."""
    index = index or {}
    out: list[dict] = []
    seen: set[str] = set()
    for cid in _coerce_cid_list(cids):
        rec = lookup_record(cid, index)
        if rec:
            entry = {
                "cid": rec.get("cid") or cid,
                "ref": rec.get("ref") or cid,
                "summary": rec.get("summary") or "",
                "source": rec.get("source") or "unknown",
                "source_label": rec.get("source_label") or "",
                "when": rec.get("when") or "",
            }
        else:
            entry = {
                "cid": cid,
                "ref": cid,
                "summary": "",
                "source": "unknown",
                "source_label": "No longer in scope",
                "when": "",
            }
        if entry["cid"] in seen:
            continue
        seen.add(entry["cid"])
        out.append(entry)
    return out


def _assemble_draft(d: dict, index: dict) -> dict:
    cids = _coerce_cid_list(d.get("citations"))
    citations = resolve_citations(cids, index)
    # `floor:` counts as legal grounding alongside `law:`. The drafting prompt
    # tells the model to prefer the precedence-resolved governing requirement
    # over the flat list, so counting only `law:` would mark exactly the
    # best-grounded drafts ungrounded.
    law_citation_count = sum(1 for c in cids if c.startswith("law:") or c.startswith("floor:"))
    return {
        "id": str(d.get("id")),
        "kind": d.get("kind"),
        "title": d.get("title"),
        "section_key": d.get("section_key"),
        # Strip inline corpus-id tags on the read path too, so legacy drafts
        # stored before this fix (and their edit textarea) render clean without a
        # backfill. Coverage is unaffected — it reads the stored citations field.
        "content": strip_corpus_citations(d.get("content") or "")[0],
        "status": d.get("status"),
        "promoted_ref": d.get("promoted_ref"),
        "citations": citations,
        "law_citation_count": law_citation_count,
        "grounded": law_citation_count > 0,
    }


def _floor_coverage(cited_by: dict, index: dict) -> dict[tuple[str, str], list[str]]:
    """(category slug, jurisdiction slug) → draft ids, over the cited `floor:`
    records. A federally-governing floor is filed under `*`: it is the operative
    rule in every state the chain resolved for. Pure."""
    out: dict[tuple[str, str], list[str]] = {}
    for cid, drafts in cited_by.items():
        if not (isinstance(cid, str) and cid.startswith("floor:")):
            continue
        rec = index.get(cid) or {}
        category = _slug(rec.get("category"))
        if not category or category == "x":
            continue
        level = str(rec.get("governing_level") or "").lower()
        juris = "*" if level == "federal" else _slug(rec.get("jurisdiction"))
        out.setdefault((category, juris), []).extend(drafts)
    return out


def _floor_citers(floor_cover: dict, law_rec: dict) -> list[str]:
    """Draft ids whose cited floor record governs this flat requirement.

    Matched on category plus jurisdiction, never category alone — California's
    meal-break floor must not mark Texas's meal-break requirement covered. The
    state is compared both as a code and as its full name, since a floor record
    carries the jurisdiction's name ("California") and a law record its code
    ("CA"). A city-level floor won't match its state's requirement; that
    under-credits coverage, which is the safe direction for a gap report."""
    category = _slug(law_rec.get("category"))
    if not category or category == "x":
        return []
    out: list[str] = []
    keys = {(category, "*")}
    state = str(law_rec.get("state") or "").strip()
    if state:
        keys.add((category, _slug(state)))
        try:
            from app.core.services.compliance_service import _CODE_TO_STATE_NAME
            name = _CODE_TO_STATE_NAME.get(state.upper())
        except Exception:  # noqa: BLE001 — matching degrades, never raises
            name = None
        if name:
            keys.add((category, _slug(name)))
    juris = str(law_rec.get("jurisdiction") or "").strip()
    if juris:
        keys.add((category, _slug(juris)))
    for key in keys:
        for draft_id in floor_cover.get(key) or []:
            if draft_id not in out:
                out.append(draft_id)
    return out


def assemble_handbook(session: dict, drafts: list[dict], corpus: dict) -> dict:
    """Assemble the session's drafts into a viewable handbook: ordered handbook
    sections, a cataloged policy list, and a deterministic session-level
    coverage map (which applicable `law:` requirements are cited by at least one
    draft vs not covered by any). `uncovered` are the candidate missing /
    non-compliant elements the free live signal surfaces. Pure — the caller
    passes drafts already ordered by created_at and a corpus from build_corpus."""
    drafts = drafts or []
    index = (corpus or {}).get("index") or {}

    sections = [_assemble_draft(d, index) for d in drafts if d.get("kind") == "handbook_section"]
    policies = [_assemble_draft(d, index) for d in drafts if d.get("kind") == "policy"]

    # Deterministic coverage: all applicable jurisdiction requirements in the
    # corpus vs the set of cids cited by any draft in this session. Citations
    # stored under the legacy positional scheme collapse onto their canonical
    # cid, so an old draft still counts toward coverage exactly once.
    cited_by: dict[str, list[str]] = {}
    for d in drafts:
        for c in _coerce_cid_list(d.get("citations")):
            canon = canonical_cid(c, index)
            ids = cited_by.setdefault(canon, [])
            draft_id = str(d.get("id"))
            if draft_id not in ids:
                ids.append(draft_id)

    floor_cover = _floor_coverage(cited_by, index)

    law_records = [(cid, rec) for cid, rec in index.items()
                   if isinstance(cid, str) and cid.startswith("law:")]
    covered, uncovered = [], []
    for cid, rec in law_records:
        citing = list(cited_by.get(cid) or [])
        # A draft that cited the GOVERNING requirement for this category covers
        # the flat requirement too — the prompt tells the model to prefer
        # `floor:`, so counting only direct `law:` cites would report the
        # best-grounded sections as gaps.
        for draft_id in _floor_citers(floor_cover, rec):
            if draft_id not in citing:
                citing.append(draft_id)
        entry = {
            "cid": cid,
            "ref": rec.get("ref") or cid,
            "summary": rec.get("summary") or "",
            "source_label": rec.get("source_label") or "",
            "state": rec.get("state") or "",
            "title": rec.get("title") or "",
            "category": rec.get("category"),
            "jurisdiction": rec.get("jurisdiction") or "",
            "cited_by": citing,
        }
        (covered if citing else uncovered).append(entry)

    return {
        "sections": sections,
        "policies": policies,
        "coverage": {"covered": covered, "uncovered": uncovered},
        "summary": {
            "section_count": len(sections),
            "policy_count": len(policies),
            "grounded_sections": sum(1 for s in sections if s["grounded"]),
            "law_records": len(law_records),
            "covered": len(covered),
            "uncovered": len(uncovered),
        },
    }


# --------------------------------------------------------------------------- #
# Deep compliance scan — on-demand Gemini grade of the in-progress drafts,
# reusing the handbook-audit grader (no PDF; grades in-memory draft sections).
# --------------------------------------------------------------------------- #

def _dedupe_matched(state: str, results: list[dict]) -> list[dict]:
    """Covered results for a state, deduped by requirement key — the grader's
    positive signal ('this topic IS addressed, in section X')."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in results or []:
        if not r.get("covered"):
            continue
        key = r.get("requirement_key") or r.get("requirement_title") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "state": state,
            "requirement_key": r.get("requirement_key"),
            "requirement_title": r.get("requirement_title"),
            "matched_section_title": r.get("matched_section_title"),
            "citation": r.get("citation"),
        })
    return out


def _sort_gaps_by_severity(gaps: list[dict]) -> list[dict]:
    return sorted(
        gaps,
        key=lambda g: (_SEVERITY_ORDER.get((g.get("severity") or "").lower(), 9),
                       g.get("requirement_title") or ""),
    )


def _empty_scan(sections_graded: int) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_state": {},
        "gaps": [],
        "matched": [],
        "counts": {"critical": 0, "important": 0, "recommended": 0, "covered": 0},
        "states": [],
        "sections_graded": sections_graded,
    }


async def run_compliance_scan(session: dict, drafts: list[dict], grounding: dict) -> dict:
    """Grade the session's in-progress drafts against the applicable jurisdiction
    requirements, per state, reusing the handbook-audit grader. Returns a
    covered/gap map: each gap carries severity + `what_good_looks_like` (the "why
    this element isn't compliant" copy) + `matched_section_title`. Never raises —
    a dead grader degrades to an empty scan, matching the audit module's pattern."""
    from app.core.services.handbook_audit_service import (
        MAX_REQUIREMENTS_PER_STATE,
        _collapse_same_level_jurisdictions,
        _grade_state_coverage,
        _merge_duplicate_gaps_for_state,
    )

    drafts = drafts or []
    industry = session.get("industry") if session else None

    draft_sections: list[dict] = []
    for d in drafts:
        title = str(d.get("title") or "").strip()
        content = str(d.get("content") or "").strip()
        if title and content:
            draft_sections.append({"title": title[:240], "excerpt": content[:600]})

    requirements_map = (grounding or {}).get("requirements") or {}

    prepared: list[tuple[str, list[dict]]] = []
    for state, reqs in requirements_map.items():
        if not state or not reqs:
            continue
        collapsed = _collapse_same_level_jurisdictions(reqs)[:MAX_REQUIREMENTS_PER_STATE]
        if collapsed:
            prepared.append((state, collapsed))

    if not draft_sections or not prepared:
        return _empty_scan(len(draft_sections))

    async def _grade(state: str, reqs: list[dict]):
        try:
            results = await _grade_state_coverage(
                state=state, industry=industry, requirements=reqs, sections=draft_sections,
            )
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: compliance grade failed for %s", state)
            results = None
        return state, results

    graded = await asyncio.gather(*[_grade(s, r) for s, r in prepared])

    by_state: dict[str, dict] = {}
    all_gaps: list[dict] = []
    all_matched: list[dict] = []
    totals = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}

    for state, results in graded:
        counts = {"critical": 0, "important": 0, "recommended": 0, "covered": 0}
        if not results:
            by_state[state] = {"counts": counts, "gaps": [], "matched": []}
            continue
        gaps = _merge_duplicate_gaps_for_state(state, results, counts)
        matched = _dedupe_matched(state, results)
        by_state[state] = {"counts": counts, "gaps": gaps, "matched": matched}
        all_gaps.extend(gaps)
        all_matched.extend(matched)
        for k in totals:
            totals[k] += counts.get(k, 0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "by_state": by_state,
        "gaps": _sort_gaps_by_severity(all_gaps),
        "matched": all_matched,
        "counts": totals,
        "states": [s for s, _ in prepared],
        "sections_graded": len(draft_sections),
    }
