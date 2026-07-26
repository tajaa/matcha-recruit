"""Broker Pilot document requirements — the pure rules behind the per-mode
document checklist and the forceable chat gate.

A session's template ("mode") declares the documents its analysis actually needs
(`PILOT_TEMPLATES[*].required_docs` in `broker_pilot.py`). This module answers,
for one session, which of them are satisfied — and by what.

Satisfaction is DYNAMIC, not a file-presence check. Three ways, tried in order:

1. ``upload``       — an uploaded document classified as the required type.
2. ``unclassified`` — a document whose classification is unavailable
                      (Gemini down / unreadable → ``text_only``). The broker
                      uploaded *something*; refusing to count it would strand the
                      session on an outage. One such document satisfies at most one
                      requirement (greedy, in declaration order) — it can't
                      simultaneously stand in for a loss run and a dec page.
3. ``platform``     — the client's own platform data already covers it
                      (``platform_source`` on the spec: contract clauses on file
                      satisfy contract review; loss-development history satisfies
                      a mid-term/renewal loss run). This is the reason the checklist
                      is computed per subject rather than rendered from the mode
                      alone: an on-platform client with contracts on file is never
                      asked to upload one.

A `platform_source` of None means the DOCUMENT ITSELF is required and platform
data deliberately cannot stand in — `loss_run` ("Loss-run deep dive") is the case:
platform triangles are aggregates and cannot answer claim-level questions, so
letting them satisfy the requirement would silently hollow out the mode.

DB-free and import-free of `broker_pilot` (it takes the template dict, not a key),
so the whole gate is unit-testable without a database or an app boot — same shape
as `schedule_rules.py`, whose forceable-409 convention `missing_docs_detail`
mirrors.
"""

# Statuses whose document is real enough to satisfy a requirement. `processing`
# hasn't been read yet and `failed` never will be — neither counts, so the
# checklist row stays open rather than flickering satisfied.
_USABLE_STATUSES = ("ready", "text_only")

# The platform-context flags a `platform_source` may name. Kept here (not in the
# catalog) so a typo'd source in a template is caught by a test rather than
# silently never matching.
PLATFORM_SOURCES = ("clauses", "lossdev", "limits")

_QUOTE_TEMPLATE = "quote_comparison"


def platform_flags(corpus: dict | None) -> dict[str, bool]:
    """Which platform-data sources this subject actually has, derived from the
    already-built corpus (no extra queries — the caller has it in hand).

    Keyed on the corpus cid scheme rather than the raw context dict: the corpus
    is what the analyst can actually cite, so a section that produced no citable
    record can't satisfy a requirement it would only be able to hand-wave at.
    """
    sources = (corpus or {}).get("sources") or {}

    def _cids(key: str) -> list[str]:
        return [r.get("cid") or "" for r in (sources.get(key) or {}).get("records") or []]

    platform_cids = _cids("platform")
    return {
        "clauses": bool(_cids("clauses")),
        "lossdev": any(c.startswith("platform:lossdev.") for c in platform_cids),
        "limits": any(c.startswith("platform:limits.") for c in platform_cids),
    }


def _doc_is_usable(doc: dict) -> bool:
    return (doc.get("status") or "") in _USABLE_STATUSES


def _is_unclassified(doc: dict) -> bool:
    """A usable document the classifier couldn't type. `text_only` is the
    explicit degraded status; a `ready` row with no doc_type shouldn't happen,
    but if it does it's the same situation — treat it the same way."""
    return _doc_is_usable(doc) and not doc.get("doc_type")


def doc_requirements(template: dict | None, docs: list[dict] | None,
                     flags: dict | None = None) -> list[dict]:
    """The session's live document checklist.

    Returns one row per declared requirement:
    ``{doc_type, label, hint, required, satisfied, satisfied_by, doc_ids}``
    where ``satisfied_by`` is ``'upload' | 'unclassified' | 'platform' | None``.

    A session with no mode has no requirements — the checklist and the gate are
    both no-ops, so an open-analysis session behaves exactly as it did before.
    """
    specs = (template or {}).get("required_docs") or []
    if not specs:
        return []

    docs = docs or []
    flags = flags or {}
    usable = [d for d in docs if _doc_is_usable(d)]

    # Unclassified docs are a scarce pool: each is spent on at most one
    # requirement, so two open requirements aren't both "satisfied" by one
    # unreadable PDF.
    unclassified = [d for d in usable if _is_unclassified(d)]
    spent: set[str] = set()

    rows: list[dict] = []
    for spec in specs:
        doc_type = spec.get("doc_type")
        matched = [d for d in usable if d.get("doc_type") == doc_type]

        satisfied_by = None
        doc_ids: list[str] = []
        if matched:
            satisfied_by = "upload"
            doc_ids = [str(d.get("id")) for d in matched]
        else:
            spare = next((d for d in unclassified if str(d.get("id")) not in spent), None)
            if spare is not None:
                satisfied_by = "unclassified"
                doc_ids = [str(spare.get("id"))]
                spent.add(str(spare.get("id")))
            else:
                source = spec.get("platform_source")
                if source and flags.get(source):
                    satisfied_by = "platform"

        rows.append({
            "doc_type": doc_type,
            "label": spec.get("label"),
            "hint": spec.get("hint"),
            "required": bool(spec.get("required")),
            "platform_source": spec.get("platform_source"),
            "satisfied": satisfied_by is not None,
            "satisfied_by": satisfied_by,
            "doc_ids": doc_ids,
        })
    return rows


def missing_required(reqs: list[dict] | None) -> list[dict]:
    """The rows that block the chat gate — required and unsatisfied. Optional
    rows never block; they are guidance, and the analyst notes their absence."""
    return [r for r in (reqs or []) if r.get("required") and not r.get("satisfied")]


def missing_docs_detail(missing: list[dict] | None) -> dict:
    """The 409 body for a chat turn on a mode whose documents aren't in yet.

    Forceable — the frontend offers "Ask anyway", which re-sends with
    ``?force=true``. Mirrors `schedule_rules.conflict_detail`: the `code` is the
    contract the frontend keys on, and everything it needs to render the prompt
    (label + hint per document) rides in the payload.
    """
    missing = missing or []
    labels = ", ".join(str(m.get("label") or m.get("doc_type")) for m in missing)
    return {
        "code": "missing_required_documents",
        "message": (f"This session mode analyzes documents that haven't been provided yet: "
                    f"{labels}." if labels else
                    "This session mode expects documents that haven't been provided yet."),
        "missing": [
            {
                "doc_type": m.get("doc_type"),
                "label": m.get("label"),
                "hint": m.get("hint"),
            }
            for m in missing
        ],
    }


def scope_notes(template: dict | None, docs: list[dict] | None,
                reqs: list[dict] | None) -> list[str]:
    """Corpus scope notes the analyst must see — what the mode expected and did
    not get. Without these the model has no way to know a document is *missing*
    (an absent record is indistinguishable from a record that doesn't exist), so
    it would answer confidently from whatever else is in scope.
    """
    notes: list[str] = []
    for m in missing_required(reqs):
        label = m.get("label") or m.get("doc_type")
        notes.append(
            f"This session's mode analyzes a {label}, which has NOT been provided. "
            f"Do not infer its contents — say plainly that it is missing and put it "
            f"under key questions."
        )

    quote_note = single_quote_note(template, docs)
    if quote_note:
        notes.append(quote_note)
    return notes


def single_quote_note(template: dict | None, docs: list[dict] | None) -> str | None:
    """Quote comparison with exactly one quote on file.

    The gate passes (one quote against the expiring program is a real
    comparison), but the analyst must not narrate a head-to-head that doesn't
    exist — so it's told, rather than left to infer it from the corpus.
    """
    if (template or {}).get("key") != _QUOTE_TEMPLATE:
        return None
    quotes = [d for d in (docs or []) if _doc_is_usable(d) and d.get("doc_type") == "quote"]
    if len(quotes) != 1:
        return None
    return (
        "Only ONE carrier quote is in scope. Compare it against the expiring program and "
        "the loss history — do not describe it as a comparison between competing quotes, "
        "and note that a second quote would be needed for that."
    )
