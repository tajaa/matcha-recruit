"""HR Pilot citation corpus — traceable grounding for supervisor guidance.

HR Pilot mode grounds answers in the company's own written material, but until
now it did so as *uncitable prose*: the model was told to answer from the
handbook, and nothing checked that the rule it quoted actually existed. This
module gives that same source material a flat citation index (`{sources, index,
notes}` — the shape `legal_defense.validate_citations` consumes) so every
enforceable claim carries a bracketed corpus id, and any id the model invents is
dropped before the answer is persisted.

Corpus cid scheme (one flat index; the audit gate keys on it):
- ``profile``                        — company handbook profile          (via handbook_pilot)
- ``law:<state>-<cat>-<title-slug>`` — applicable jurisdiction requirement (via handbook_pilot)
- ``handbook:<uuid>``                — active handbook section            (via handbook_pilot)
- ``policy:<uuid>``                  — active policy                      (via handbook_pilot)
- ``playbook:<slug>``                — industry baseline section          (via handbook_pilot)
- ``floor:<level>-<juris>-<cat>``    — governing compliance requirement   (this module)
- ``ladder:<step-slug>``             — progressive-discipline step        (this module)

The first five are minted by `handbook_pilot.build_corpus` — reused wholesale,
not reimplemented, because HR Pilot fetches the same four sources Handbook Pilot
does (compare `handbook_pilot.gather_grounding`). Its law cids are derived from
requirement *content* rather than fetch position, for reasons documented at
length in that module's docstring; do not re-mint them here.

`floor:` records are a separate namespace on purpose. They come from
`matcha_work_node.build_compliance_context`'s reasoning chains — the
precedence-resolved *governing* requirement per category — which overlaps the
same statutes `law:` records cover but at a different resolution. Minting them
as `law:` would collide two different views of one statute onto one cid and the
index (keyed by cid) would silently drop one.

A floor cell is a **governing requirement**, not a location: two offices in the
same state share one California meal-break obligation. Keying on the location
would mint it once per office, and the model would cite whichever copy it saw
first — three cids naming one rule. The location labels merge into `applies_to`
instead.

Pure functions here are unit-tested (`tests/matcha_work/test_hr_pilot_corpus.py`);
only `gather_hr_pilot_grounding` touches the DB.
"""

import logging
import re

from .handbook_pilot import _slug, build_corpus

logger = logging.getLogger(__name__)

_MAX_HR_PILOT_SECTIONS = 60
_MAX_HR_PILOT_POLICIES = 60

# Namespaces the audit gate will recognise inside brackets. Deliberately a
# closed list: a bare `[...]` regex also matches markdown link text and the
# `[Handbook — Title]` headers this corpus renders, so unknown brackets must be
# left alone rather than treated as a citation that failed to resolve.
_CID_NAMESPACES = ("profile", "law", "handbook", "policy", "playbook", "floor", "ladder")
_CITATION_RE = re.compile(
    r"\[(" + "|".join(_CID_NAMESPACES) + r")(:[^\]\s]+)?\]"
)

# Progressive-discipline ladder — static company procedure, cited like any other
# record so "the next step is a written warning" is traceable rather than
# asserted. Replaces the prose _DISCIPLINE_LADDER_SUMMARY this module took over
# from matcha_work_mode_contexts.
_LADDER_STEPS = [
    ("verbal-warning", "Verbal warning",
     "First documented step. Supervisor discusses the issue with the employee and "
     "records that the conversation happened."),
    ("written-warning", "Written warning",
     "Second step. A written record the employee acknowledges, stating the conduct, "
     "the expectation, and the timeframe for improvement."),
    ("final-warning", "Final warning",
     "Third step. States plainly that the next step is a termination review."),
    ("termination-review", "Termination review",
     "Final step. NOT drafted or advised here — a final warning already on file means "
     "the supervisor must be routed to corporate HR."),
]


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Grounding — DB-touching. Mirrors handbook_pilot.gather_grounding, but reads
# only what is ACTUALLY IN FORCE (active handbook + active policies, no drafts):
# a supervisor acting today needs the rule in force today, not a proposal.
# --------------------------------------------------------------------------- #

async def gather_hr_pilot_grounding(conn, company_id) -> dict:
    """Fetch the raw grounding material HR Pilot cites. Best-effort at every
    level — a dead source degrades to empty and the rest still grounds."""
    from app.core.services import handbook_service as hb

    sections: list = []
    try:
        sections = await conn.fetch(
            """
            SELECT hs.id, hs.title, hs.section_type, hs.content,
                   h.title AS handbook_title
            FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1 AND h.status = 'active'
              AND hv.version_number = h.active_version
            ORDER BY hs.section_order
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_SECTIONS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: handbook-section fetch failed for %s", company_id)

    policies: list = []
    try:
        policies = await conn.fetch(
            """
            SELECT id, title, category, status, content, description
            FROM policies
            WHERE company_id = $1 AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: policy fetch failed for %s", company_id)

    scopes: list = []
    requirements: dict = {}
    try:
        scopes = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
        if scopes:
            requirements = await hb._fetch_state_requirements(conn, scopes)
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: requirement fetch failed for %s", company_id)

    industry = None
    try:
        industry = await conn.fetchval(
            "SELECT industry FROM companies WHERE id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: industry fetch failed for %s", company_id)

    profile = None
    try:
        profile = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: profile fetch failed for %s", company_id)

    return {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": industry,
    }


# --------------------------------------------------------------------------- #
# Corpus build — pure. Extends handbook_pilot's five source groups with two.
# --------------------------------------------------------------------------- #

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


def _ladder_records() -> list[dict]:
    return [
        {
            "cid": f"ladder:{slug}",
            "ref": f"Discipline ladder — {label}",
            "summary": summary,
            "when": "company procedure",
            "step": i + 1,
        }
        for i, (slug, label, summary) in enumerate(_LADDER_STEPS)
    ]


def build_hr_pilot_corpus(grounding: dict, reasoning_chains: list | None = None) -> dict:
    """Assemble the HR Pilot citation corpus `{sources, index, notes}`. Pure.

    Delegates the five shared source groups to `handbook_pilot.build_corpus`
    (identical source material, already-hardened cid minting) and appends the
    two HR-Pilot-specific ones."""
    corpus = build_corpus(grounding or {})
    sources = corpus["sources"]

    sources["compliance_floor"] = {
        "label": "Governing compliance requirements",
        "records": _floor_records(reasoning_chains),
    }
    sources["discipline_ladder"] = {
        "label": "Progressive discipline ladder",
        "records": _ladder_records(),
    }

    # Rebuild the flat index over ALL groups. A cid appearing in two groups
    # would silently lose one here — the namespaces are disjoint by
    # construction, and test_no_cid_collisions_across_groups holds them so.
    index: dict = {}
    for key, source in sources.items():
        for record in source["records"]:
            index[record["cid"]] = {**record, "source": key, "source_label": source["label"]}

    notes = list(corpus.get("notes") or [])
    if not sources["compliance_floor"]["records"]:
        notes.append(
            "No precedence-resolved compliance floor available — answers ground on "
            "the flat per-state requirement list only."
        )
    return {"sources": sources, "index": index, "notes": notes}


# --------------------------------------------------------------------------- #
# The gate — pure. Runs on the finished answer, before it is persisted.
# --------------------------------------------------------------------------- #

def audit_citations(text: str, index: dict) -> tuple[str, list[dict], list[str]]:
    """Strip unresolvable citations from a finished HR Pilot answer.

    Returns `(clean_text, citations, dropped)`:
    - `clean_text` — the answer with unresolvable `[cid]` markers removed
      (resolvable ones stay in place so the client can render them as chips).
    - `citations`  — the corpus records actually cited, in first-use order.
    - `dropped`    — the invented ids, for logging and a client-side notice.

    Exact-match only, deliberately. `handbook_pilot.lookup_record` recovers
    legacy cids by prefix, but that is a READ path over already-stored
    citations; routing new model output through it would launder an invented id
    into a real requirement.

    A dropped citation removes the bracket, not the sentence around it — the
    claim survives uncited, visibly ungrounded, rather than the answer
    developing a hole mid-sentence. The count is surfaced to the user so an
    answer leaning on invented sources is legible as such.
    """
    if not text:
        return "", [], []
    index = index or {}

    citations: list[dict] = []
    seen: set[str] = set()
    dropped: list[str] = []

    def _replace(match: re.Match) -> str:
        cid = match.group(0)[1:-1]
        record = index.get(cid)
        if record is None:
            if cid not in dropped:
                dropped.append(cid)
            return ""
        if cid not in seen:
            seen.add(cid)
            citations.append(record)
        return match.group(0)

    clean = _CITATION_RE.sub(_replace, text)
    # Dropping a marker can leave doubled spaces or a space before punctuation.
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r" ([.,;:!?])", r"\1", clean)
    return clean.strip(), citations, dropped


def render_corpus_block(corpus: dict, full_text: dict | None = None) -> str:
    """Render the corpus as the citable source block injected into the prompt.

    Every record is emitted with its own `[cid]` so the model has something
    exact to cite; the instruction block at the end is what makes the citation
    obligation explicit.

    `full_text` maps cid → the record's FULL body, and exists because the corpus
    record `summary` is an index entry, not the source. `handbook_pilot`'s
    section/policy records cap their summary at 280 characters (and policy
    records carry only title/category/description, never the policy body) —
    fine for a citation footer, useless for answering from. Feeding those to the
    model would leave HR Pilot quoting the company's handbook from a 280-char
    preview of it. Callers pass the real text here; the stored records stay
    index-sized so message metadata doesn't balloon."""
    corpus = corpus or {}
    full_text = full_text or {}
    sources = corpus.get("sources") or {}
    lines: list[str] = []
    for source in sources.values():
        records = source.get("records") or []
        if not records:
            continue
        lines.append(f"\n--- {str(source.get('label') or 'Records').upper()} ({len(records)}) ---")
        for record in records:
            body = full_text.get(record["cid"]) or record.get("summary") or ""
            lines.append(f"[{record['cid']}] {record.get('ref') or ''}\n{body}")
    return "\n".join(lines)
