"""Grounding corpus assembly for Analysis Pilot.

Flattens the session's datasets (each with its computed per-pack metrics) and
saved comparisons into the ``{sources, index, notes}`` contract shared by every
Pilot — the same shape ``legal_defense.validate_citations`` and the report
renderer consume. Every computed number is a citable record; the AI may cite
ONLY these ids.

Pure (no DB) — datasets/comparisons are already-loaded dicts.
"""

from __future__ import annotations

from .base import slug, fmt_num, to_float

_ANALYZABLE = ("ready", "needs_review")

# Hard ceiling on citable records per dataset source — an uncapped corpus is
# re-serialized into EVERY chat-turn prompt (broker_pilot caps per source too).
# Dataset + figure records rank first; pack records fill the remainder.
_PER_SOURCE_CAP = 300


def _dataset_record(d: dict) -> dict:
    norm = d.get("normalized") or {}
    meta = norm.get("meta") or {}
    n_series = len(norm.get("series") or {})
    n_periods = len(norm.get("periods") or []) or (d.get("row_count") or 0)
    src = meta.get("source_kind") or d.get("source_kind") or "?"
    kind = norm.get("kind") or "generic"
    return {
        "cid": f"dataset:{d.get('id')}",
        "ref": d.get("filename") or "dataset",
        "summary": f"{d.get('filename') or 'dataset'} — {n_periods} rows/periods × {n_series} "
                   f"numeric series (source: {src}; kind: {kind}).",
        "when": str(d.get("created_at") or "uploaded"),
    }


def _figure_records(d: dict) -> list[dict]:
    """Raw document-extracted line-item values with provenance — one per series,
    citable so the AI can quote a figure and point at its page."""
    norm = d.get("normalized") or {}
    meta = norm.get("meta") or {}
    prov = meta.get("provenance") or {}
    if (meta.get("source_kind") or d.get("source_kind")) != "pdf":
        return []
    periods = norm.get("periods") or []
    out = []
    for name, values in (norm.get("series") or {}).items():
        page = (prov.get(name) or {}).get("page")
        pairs = []
        for i, v in enumerate(values or []):
            if v is None:
                continue
            lab = periods[i] if i < len(periods) else str(i + 1)
            pairs.append(f"{lab} {fmt_num(v)}")
        if not pairs:
            continue
        page_s = f" (p.{page})" if page else ""
        out.append({
            "cid": f"figure:{d.get('id')}:{slug(name)}",
            "ref": f"{name} — extracted{page_s}",
            "summary": f"{name}{page_s}: " + ", ".join(pairs) + ".",
            "when": "document",
        })
    return out


def build_corpus(datasets: list[dict], comparisons: list[dict] | None = None) -> dict:
    """Assemble ``{sources, index, notes}``. ``datasets`` are stored dataset
    rows (dicts with parsed ``normalized`` + ``metrics``); ``comparisons`` are
    stored comparison rows (dicts with ``result``)."""
    sources: dict = {}
    notes: list[str] = []

    for d in datasets or []:
        status = d.get("status") or "processing"
        name = d.get("filename") or "dataset"
        if status == "failed":
            notes.append(f"Dataset '{name}' failed processing and is not in scope.")
            continue
        if status == "processing":
            notes.append(f"Dataset '{name}' is still processing and is not in scope.")
            continue
        if status not in _ANALYZABLE:
            continue
        recs = [_dataset_record(d)]
        figures = _figure_records(d)
        if status == "needs_review":
            # The confirmation gate is ENFORCED here: until the user reviews the
            # document extraction, only the raw extracted figures (marked
            # unverified) are citable — computed metrics stay out of the corpus
            # so the AI can't narrate risk numbers built on unconfirmed data.
            for f in figures:
                f = dict(f)
                f["summary"] = f"[unverified] {f['summary']}"
                recs.append(f)
            notes.append(
                f"Dataset '{name}': document-extracted figures are pending your review — "
                "computed metrics are excluded from analysis until you confirm them."
            )
        else:
            recs.extend(figures)
            metrics = d.get("metrics") or {}
            for pack, block in metrics.items():
                if pack == "_warnings":
                    notes.extend(str(w) for w in (block or []))
                    continue
                recs.extend((block or {}).get("records") or [])
                notes.extend(str(n) for n in (block or {}).get("notes") or [])
        for w in ((d.get("normalized") or {}).get("meta") or {}).get("warnings") or []:
            notes.append(f"{name}: {w}")
        if len(recs) > _PER_SOURCE_CAP:
            notes.append(f"{name}: showing {_PER_SOURCE_CAP} of {len(recs)} computed records.")
            recs = recs[:_PER_SOURCE_CAP]
        sources[f"ds:{d.get('id')}"] = {"label": name, "records": recs}

    for c in comparisons or []:
        result = c.get("result") or {}
        recs = result.get("records") or []
        if recs:
            sources[f"cmp:{c.get('id')}"] = {"label": c.get("title") or "Comparison", "records": recs}
        notes.extend(result.get("notes") or [])

    if not sources:
        notes.append("No analyzed datasets in scope yet — upload a CSV/XLSX or a financial document to begin.")

    index: dict = {}
    for key, s in sources.items():
        for r in s["records"]:
            index[r["cid"]] = {**r, "source": key, "source_label": s["label"]}
    return {"sources": sources, "index": index, "notes": notes}


def validate_edit_proposals(proposals, datasets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Anti-hallucination gate for chat-proposed extraction corrections — the
    sibling of ``legal_defense.validate_citations``. Keep only proposals that
    target a REAL figure: a pdf dataset in this session whose stored extraction
    has exactly that line-item label and period, with a finite proposed value.
    The AI only proposes; edits take effect solely through the user-confirmed
    dataset PATCH → recompute path. Pure (unit-tested). Returns
    ``(clean, dropped)``."""
    by_id: dict[str, dict] = {}
    for d in datasets or []:
        if d.get("source_kind") == "pdf" and isinstance(d.get("extraction"), dict):
            by_id[str(d.get("id"))] = d["extraction"]
    clean, dropped = [], []
    for p in proposals or []:
        if not isinstance(p, dict):
            continue
        ds_id = str(p.get("dataset_id") or "")
        label = str(p.get("label") or "").strip()
        period = str(p.get("period") or "").strip()
        proposed = to_float(p.get("proposed_value"))
        ext = by_id.get(ds_id)
        item = next((it for it in (ext.get("line_items") or []) if it.get("label") == label), None) \
            if ext else None
        periods = [str(x) for x in (ext.get("periods") or [])] if ext else []
        if item is None or period not in periods or proposed is None:
            dropped.append({k: p.get(k) for k in ("dataset_id", "label", "period", "proposed_value")})
            continue
        idx = periods.index(period)
        vals = item.get("values") or []
        current = vals[idx] if idx < len(vals) else None
        clean.append({
            "dataset_id": ds_id,
            "label": label,
            "period": period,
            "current_value": current,
            "proposed_value": proposed,
            "reason": str(p.get("reason") or "").strip()[:300],
        })
    return clean, dropped
