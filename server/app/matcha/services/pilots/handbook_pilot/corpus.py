"""Corpus build -- one flat citation index over profile / law / existing sections
and policies / industry playbook / audit gaps / freshness findings / compliance
floor records, plus the full-text map and cid lookup + canonicalization.

`build_corpus`, `_floor_records` and `_slug` are imported by
`hr_pilot_corpus.py`, which reuses the five shared source groups wholesale.
"""
import logging
import re
from datetime import datetime, timezone

from ._config import _AUDIT_STALE_DAYS, _FRESHNESS_LABELS, _FULL_TEXT_BUDGET, _FULL_TEXT_PER_RECORD, _LAW_PER_STATE_CAP, _MAX_AUDIT_GAPS, _MAX_FRESHNESS_FINDINGS, _SEVERITY_RANK
from app.matcha.services._shared.text import _hum, _slug

logger = logging.getLogger(__name__)


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


def _audit_records(audit: dict | None) -> tuple[list[dict], list[str]]:
    """(records, notes) for the latest handbook-audit gap list. Pure.

    Severity-ranked before the cap, so a truncated corpus keeps the criticals.
    The cid keys on state + requirement key, not list position: the same audit
    is re-read on every turn and re-ranked here, and a positional cid would
    still resolve after a re-rank — to a different gap.

    A gap is a finding about the company's HANDBOOK, never a statement of law.
    The summary says which handbook document was graded and how old the grading
    is, because both are things the model would otherwise assume."""
    audit = audit or {}
    gaps = [g for g in (audit.get("gaps") or []) if isinstance(g, dict) and not g.get("covered")]
    if not gaps:
        return [], []

    when = audit.get("completed_at")
    when_s = when.date().isoformat() if hasattr(when, "date") else (str(when)[:10] or "unknown date")
    notes: list[str] = []
    age_days = None
    if hasattr(when, "date"):
        try:
            age_days = (datetime.now(timezone.utc) - when).days
        except TypeError:                       # naive timestamp — skip the staleness note
            age_days = None
    if age_days is not None and age_days > _AUDIT_STALE_DAYS:
        notes.append(
            f"The handbook audit these gaps come from ran {age_days} days ago ({when_s}); "
            "a gap may already have been closed by a later handbook edit."
        )

    ranked = sorted(
        gaps,
        key=lambda g: (_SEVERITY_RANK.get(str(g.get("severity") or "").lower(), 9),
                       str(g.get("state") or ""), str(g.get("requirement_title") or "")),
    )
    if len(ranked) > _MAX_AUDIT_GAPS:
        notes.append(
            f"{len(ranked)} audit gaps on file; the {_MAX_AUDIT_GAPS} most severe are in scope."
        )
        ranked = ranked[:_MAX_AUDIT_GAPS]

    recs, seen = [], {}
    for g in ranked:
        state = str(g.get("state") or "").strip().upper() or "US"
        title = str(g.get("requirement_title") or g.get("requirement_key") or "requirement")
        cid = f"audit:{_slug(state)}-{_slug(g.get('requirement_key') or title)}"
        n = seen.get(cid, 0)
        seen[cid] = n + 1
        if n:
            cid = f"{cid}-{n + 1}"
        severity = str(g.get("severity") or "recommended").lower()
        bits = [f"{state} — {severity} gap: the audited handbook does not adequately cover "
                f"{title}"]
        if g.get("what_good_looks_like"):
            bits.append(f"what good looks like: {str(g['what_good_looks_like'])[:400]}")
        if g.get("matched_section_title"):
            bits.append(f"closest existing section: {g['matched_section_title']}")
        if g.get("citation"):
            bits.append(f"cited authority: {g['citation']}")
        recs.append({
            "cid": cid,
            "ref": f"Handbook gap — {title} ({state})",
            "summary": "; ".join(bits) + ".",
            "when": when_s,
        })
    return recs, notes


def _freshness_records(findings: list[dict] | None) -> tuple[list[dict], list[str]]:
    """(records, notes) for the latest freshness check per handbook. Pure.

    Cids key on the finding's own row id, which is stable — unlike the audit
    gaps, these are real rows."""
    rows = [f for f in (findings or []) if isinstance(f, dict)]
    if not rows:
        return [], []
    notes: list[str] = []
    if len(rows) > _MAX_FRESHNESS_FINDINGS:
        notes.append(
            f"More than {_MAX_FRESHNESS_FINDINGS} handbook-freshness findings are open; "
            f"the {_MAX_FRESHNESS_FINDINGS} most recent are in scope."
        )
        rows = rows[:_MAX_FRESHNESS_FINDINGS]
    recs = []
    for f in rows:
        kind = str(f.get("finding_type") or "").lower()
        bits = [str(f.get("summary") or _FRESHNESS_LABELS.get(kind) or "handbook freshness finding")]
        if f.get("handbook_title"):
            bits.insert(0, f"handbook “{f['handbook_title']}”")
        if f.get("section_key"):
            bits.append(f"section {f['section_key']}")
        if kind and kind in _FRESHNESS_LABELS:
            bits.append(_FRESHNESS_LABELS[kind])
        if f.get("effective_date"):
            bits.append(f"change effective {f['effective_date']}")
        if f.get("age_days") is not None:
            bits.append(f"section {f['age_days']} day(s) old")
        if f.get("source_url"):
            bits.append(f"source {f['source_url']}")
        if f.get("change_request_id"):
            # Otherwise the pilot re-proposes work the admin has already queued.
            bits.append("a change request has already been raised for this finding")
        checked = f.get("checked_at")
        recs.append({
            "cid": f"fresh:{f.get('id')}",
            "ref": (f"Freshness finding — {_hum(kind) or 'handbook'}"
                    + (f" ({f['section_key']})" if f.get("section_key") else "")),
            "summary": "; ".join(bits) + ".",
            "when": (checked.date().isoformat() if hasattr(checked, "date")
                     else str(checked or "")[:10] or "current"),
        })
    return recs, notes


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


def build_corpus(grounding: dict, *, with_full_text: bool = False) -> dict:
    """Assemble the grounding corpus `{sources, index, notes}` — the same shape
    Legal/Broker Pilot use, so `validate_citations` works unchanged. Pure.

    ``with_full_text`` adds `full_text`: cid → the record's real body, for the
    ONE caller that renders a prompt (see `_full_text_map`). Off by default
    because the other callers don't render one — `/context` counts records,
    `assemble_handbook` reads the index, and HR Pilot builds its own full-text
    map — and the map is up to 120k characters that HR Pilot's Redis-cached
    corpus would otherwise carry per company for nothing. It is never folded
    into the records either way; those are stored."""
    grounding = grounding or {}
    audit_recs, audit_notes = _audit_records(grounding.get("audit"))
    fresh_recs, fresh_notes = _freshness_records(grounding.get("freshness"))
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
        # Findings ABOUT the company's handbook — where it falls short and where
        # the law moved under it. Not law themselves: `law_citation_count` below
        # deliberately does not count them, so a draft citing only a gap is still
        # "ungrounded" and shows amber.
        "handbook_audit": {"label": "Handbook audit gaps", "records": audit_recs},
        "handbook_freshness": {"label": "Handbook freshness findings", "records": fresh_recs},
    }
    notes: list[str] = [*audit_notes, *fresh_notes]
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
    full_text, overflow = _full_text_map(grounding) if with_full_text else ({}, 0)
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
