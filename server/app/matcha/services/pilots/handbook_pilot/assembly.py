"""Citation resolution + draft assembly: cid coercion, resolve_citations against
the corpus index, per-draft assembly, floor-coverage accounting, and
assemble_handbook.
"""
import json
import logging

from app.matcha.services._shared.text import _slug
from .corpus import canonical_cid, lookup_record
from .chat import strip_corpus_citations

logger = logging.getLogger(__name__)


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


def _floor_coverage(cited_by: dict, index: dict) -> tuple[dict, dict]:
    """Two maps over the corpus's `floor:` records:

    * ``cover``: (category slug, jurisdiction slug) → draft ids that cited that
      floor. A federally-governing floor is filed under ``*``.
    * ``local``: category slug → the set of NON-federal jurisdictions that have
      a governing floor of their own, cited or not.

    ``local`` is what keeps the ``*`` wildcard honest. A company with CA and TX
    locations can have federal governing a category in TX while California
    governs it in CA. Citing the federal floor must not mark California's
    requirement covered — the draft would state the weaker federal obligation
    for California employees, which is exactly the mis-attribution the
    jurisdiction match exists to prevent. Pure."""
    cover: dict[tuple[str, str], list[str]] = {}
    local: dict[str, set] = {}
    for cid, rec in (index or {}).items():
        if not (isinstance(cid, str) and cid.startswith("floor:")):
            continue
        category = _slug((rec or {}).get("category"))
        if not category or category == "x":
            continue
        level = str((rec or {}).get("governing_level") or "").lower()
        if level != "federal":
            local.setdefault(category, set()).add(_slug(rec.get("jurisdiction")))
        drafts = cited_by.get(cid) or []
        if not drafts:
            continue
        juris = "*" if level == "federal" else _slug(rec.get("jurisdiction"))
        cover.setdefault((category, juris), []).extend(drafts)
    return cover, local


def _floor_citers(floor_cover: dict, floor_local: dict, law_rec: dict) -> list[str]:
    """Draft ids whose cited floor record governs this flat requirement.

    Matched on category plus jurisdiction, never category alone — California's
    meal-break floor must not mark Texas's meal-break requirement covered. The
    state is compared both as a code and as its full name, since a floor record
    carries the jurisdiction's name ("California") and a law record its code
    ("CA"). A city-level floor won't match its state's requirement; that
    under-credits coverage, which is the safe direction for a gap report.

    The federal ``*`` wildcard applies only where no jurisdiction of this
    requirement's own has a governing floor for the category — see
    `_floor_coverage`."""
    category = _slug(law_rec.get("category"))
    if not category or category == "x":
        return []
    keys: set = set()
    own: set = set()
    state = str(law_rec.get("state") or "").strip()
    if state:
        own.add(_slug(state))
        try:
            from app.core.services.compliance_service import _CODE_TO_STATE_NAME
            name = _CODE_TO_STATE_NAME.get(state.upper())
        except Exception:  # noqa: BLE001 — matching degrades, never raises
            name = None
        if name:
            own.add(_slug(name))
    juris = str(law_rec.get("jurisdiction") or "").strip()
    if juris:
        own.add(_slug(juris))
    keys.update((category, j) for j in own)

    # Federal covers this requirement only when nothing local governs the
    # category here; otherwise the local floor is the operative rule and only a
    # draft citing THAT one covers it.
    if not (floor_local.get(category) or set()) & own:
        keys.add((category, "*"))

    out: list[str] = []
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

    floor_cover, floor_local = _floor_coverage(cited_by, index)

    law_records = [(cid, rec) for cid, rec in index.items()
                   if isinstance(cid, str) and cid.startswith("law:")]
    covered, uncovered = [], []
    for cid, rec in law_records:
        citing = list(cited_by.get(cid) or [])
        # A draft that cited the GOVERNING requirement for this category covers
        # the flat requirement too — the prompt tells the model to prefer
        # `floor:`, so counting only direct `law:` cites would report the
        # best-grounded sections as gaps.
        for draft_id in _floor_citers(floor_cover, floor_local, rec):
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
