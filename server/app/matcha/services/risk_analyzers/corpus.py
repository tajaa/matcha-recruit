"""Grounding corpus assembly for Risk Pilot.

Flattens the session's datasets (each with its computed per-pack metrics) and
saved comparisons into the ``{sources, index, notes}`` contract shared by every
Pilot — the same shape ``legal_defense.validate_citations`` and the report
renderer consume. Every computed number is a citable record; the AI may cite
ONLY these ids.

Pure (no DB) — datasets/comparisons are already-loaded dicts.
"""

from __future__ import annotations

from .base import slug, fmt_num

_ANALYZABLE = ("ready", "needs_review")


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
        recs.extend(_figure_records(d))
        metrics = d.get("metrics") or {}
        for pack, block in metrics.items():
            if pack == "_warnings":
                notes.extend(str(w) for w in (block or []))
                continue
            recs.extend((block or {}).get("records") or [])
        for w in ((d.get("normalized") or {}).get("meta") or {}).get("warnings") or []:
            notes.append(f"{name}: {w}")
        if status == "needs_review":
            notes.append(f"Dataset '{name}' has document-extracted figures pending your review — verify before relying on them.")
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
