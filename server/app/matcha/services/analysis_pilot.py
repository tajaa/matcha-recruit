"""Analysis Pilot — grounded, deterministic general-purpose data analysis
(bring-your-own-data, in a chat UI).

The company uploads any dataset (CSV, XLSX, or a 10-K / P&L / loss-run PDF); a
**deterministic** Python engine (``analysis_packs``) computes the metrics —
general descriptive stats plus volatility/risk, financial-ratio, insurance, and
inventory packs — and a **grounded** AI answers questions over the COMPUTED
numbers and exports an analyst report. Chat turns can FOCUS on highlighted
records, and the AI may PROPOSE corrections to document-extracted figures
(gated by ``validate_edit_proposals``); proposals only take effect through the
user-confirmed dataset PATCH → recompute path. Three-stage integrity:

  1. Extraction  — AI, ONLY for documents. Metrics are computed eagerly for the
     review UI, but until the user confirms the figures the dataset is
     ``needs_review`` and the corpus/report EXCLUDE its computed metrics
     (``analysis_packs.corpus`` keeps only the raw figures, marked unverified).
  2. Computation — deterministic Python over the FULL parsed series; a
     hallucinated figure can't enter a metric.
  3. Narration   — AI, citation-gated via legal_defense.validate_citations.

Derived from the Broker Pilot architecture and reusing its pure gates directly.
Never raises on the analysis path — failures degrade, they don't 500.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.core.services.genai_client import get_genai_client
from app.core.services.pdf import safe_url_fetcher

from . import analysis_packs as packs
from .analysis_packs.base import to_float
from .analysis_packs.corpus import validate_edit_proposals  # pure gate, unit-tested
from .claims_readiness import _PDF_CSS, _esc, _fmt_dt
from .legal_defense import validate_citations, _parse_json  # pure, unit-tested

logger = logging.getLogger(__name__)

MODEL = "gemini-3-flash-preview"
_GEMINI_TIMEOUT = 90
_HISTORY_TURNS = 12
_MAX_LINE_ITEMS = 40
_MAX_PERIODS = 12
_STORED_TEXT_CAP = 40_000

DISCLAIMER = (
    "Prepared from data you provided. Every figure is either a value you uploaded "
    "or a metric computed deterministically from it; the narrative cites the "
    "specific records it relies on. This is an analytical aid, not financial, "
    "actuarial, or investment advice — verify figures against your source data."
)

_client = None


def _genai():
    global _client
    if _client is None:
        _client = get_genai_client()
    return _client


# --------------------------------------------------------------------------- #
# Document extraction — one Gemini pass at upload (line-items × periods). Never
# raises. The user CONFIRMS the extracted figures before they drive analysis.
# --------------------------------------------------------------------------- #

_EXTRACT_PROMPT = """You are a financial data analyst. Extract the numeric time-series / financial line-items from the attached document (could be a 10-K, income statement / P&L, balance sheet, insurance loss run, or inventory report).

Return ONLY valid JSON, exactly this shape:
{"kind": "<one of: financial_statement | loss_run | inventory | timeseries | generic>",
 "title": "<short description of what this document contains>",
 "periods": ["<column/period label>", ...],
 "line_items": [{"label": "<row/line-item name, e.g. 'Revenue' or 'Incurred Losses'>",
                 "values": [<number aligned to each period, or null if absent>],
                 "unit": "<e.g. 'USD thousands' or null>",
                 "page": <page number the figures appear on, or null>}],
 "notes": ["<anything ambiguous, restated, or worth the reviewer's attention>"]}

Rules:
- Extract ONLY figures the document actually shows. NEVER invent, estimate, or infer a number.
- Align every line_item's `values` array to the `periods` array (same length; use null for a missing period).
- At most %d line_items and %d periods — pick the ones a risk/financial analyst would use.
- If the document has no extractable numeric data, return empty `periods`/`line_items` and say so in `notes`.""" % (_MAX_LINE_ITEMS, _MAX_PERIODS)


def coerce_extraction(payload: dict) -> dict:
    """Clamp an extraction (Gemini's or a user PATCH) into the stored schema.
    Pure. Values are coerced through ``to_float`` — non-finite floats (NaN/Inf)
    become None, since ``json.dumps`` would otherwise emit bare ``NaN`` tokens
    that Postgres rejects on the ``::jsonb`` cast. Values arrays are capped even
    when ``periods`` is empty (user input is otherwise unbounded)."""
    if not isinstance(payload, dict):
        payload = {}
    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in ("financial_statement", "loss_run", "inventory", "timeseries", "generic"):
        kind = "generic"
    periods = [str(p).strip()[:40] for p in (payload.get("periods") or [])][:_MAX_PERIODS]
    n_periods = len(periods)
    items = []
    for it in (payload.get("line_items") or [])[:_MAX_LINE_ITEMS]:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()[:120]
        if not label:
            continue
        raw_vals = it.get("values")
        vals = [to_float(v) for v in raw_vals] if isinstance(raw_vals, list) else []
        # normalize length to periods (pad/trim) so downstream alignment holds;
        # with no periods, still cap — never store unbounded arrays.
        vals = (vals + [None] * n_periods)[:n_periods] if n_periods else vals[:_MAX_PERIODS]
        page = it.get("page")
        items.append({
            "label": label,
            "values": vals,
            "unit": (str(it.get("unit")).strip()[:40] if it.get("unit") else None),
            "page": (int(page) if isinstance(page, (int, float)) else None),
        })
    notes = [str(n).strip()[:200] for n in (payload.get("notes") or [])[:10] if str(n).strip()]
    return {"kind": kind, "title": (str(payload.get("title")).strip()[:200] if payload.get("title") else None),
            "periods": periods, "line_items": items, "notes": notes}


async def extract_dataset(data: bytes | None, text: str | None, *, is_pdf: bool,
                          filename: str) -> dict:
    """One-shot financial extraction. Best-effort, never raises —
    returns ``{"extraction": {...}, "available": bool}``."""
    payload: dict = {}
    try:
        from google.genai import types
        if is_pdf and data:
            part = types.Part.from_bytes(data=data, mime_type="application/pdf")
            contents = [f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}", part]
        else:
            contents = (f"{_EXTRACT_PROMPT}\n\nFILENAME: {filename}\n\n"
                        f"DOCUMENT TEXT:\n{(text or '')[:_STORED_TEXT_CAP]}")
        resp = await asyncio.wait_for(
            _genai().aio.models.generate_content(
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            ),
            timeout=_GEMINI_TIMEOUT,
        )
        payload = _parse_json(getattr(resp, "text", "") or "")
    except Exception as exc:  # noqa: BLE001 - degrade, never 500 the upload
        logger.warning("analysis_pilot: extraction failed for %s: %s", filename, exc)
        payload = {}
    extraction = coerce_extraction(payload)
    available = bool(extraction["line_items"])
    return {"extraction": extraction, "available": available}


# --------------------------------------------------------------------------- #
# Deterministic (re)analysis — normalization + analyzer packs. Pure/sync (run
# it via asyncio.to_thread from routes: openpyxl + the N² correlation pass are
# seconds of CPU that must not block the event loop).
# --------------------------------------------------------------------------- #

def analyze_dataset(ds_id, source_kind: str, filename: str, *, parsed=None,
                    prev_normalized=None, extraction=None, mapping=None,
                    config=None, kind=None) -> tuple[dict, dict, tuple[int, int]]:
    """Build the normalized model, run every applicable analyzer pack on the
    FULL series, then downsample what will be persisted. Returns
    ``(storage_ready_normalized, metrics, (row_count, column_count))`` — the
    counts describe the FULL data, not the stored sample. No DB, no Gemini.

    Recompute paths reuse the STORED (possibly downsampled) series — when that
    happens on a truncated dataset, a disclosure warning is appended so the
    report never presents recomputed numbers as full-resolution."""
    recomputed_on_stored = False
    if extraction is not None:
        parsed = packs.parsed_from_extraction(extraction)
    elif parsed is None and prev_normalized is not None:
        meta = prev_normalized.get("meta") or {}
        recomputed_on_stored = bool(meta.get("truncated"))
        parsed = {
            "series": prev_normalized.get("series") or {},
            "periods": prev_normalized.get("periods"),
            "truncated": bool(meta.get("truncated")),
            "warnings": list(meta.get("warnings") or []),
            "provenance": meta.get("provenance"),
        }
    normalized = packs.normalize(parsed or {"series": {}}, source_kind=source_kind,
                              filename=filename, roles_override=mapping, kind_override=kind)
    if recomputed_on_stored:
        note = "Metrics recomputed on the stored, downsampled series."
        warnings = normalized["meta"].setdefault("warnings", [])
        if note not in warnings:
            warnings.append(note)
    metrics = packs.run_analyzers(normalized, config or {}, str(ds_id))
    counts = _shape_counts(normalized)  # full-data counts, before downsampling
    return packs.downsample_for_storage(normalized), metrics, counts


def _shape_counts(normalized: dict) -> tuple[int, int]:
    series = normalized.get("series") or {}
    periods = normalized.get("periods") or []
    row_count = len(periods) or (max((len(v) for v in series.values()), default=0))
    return row_count, len(series)


# --------------------------------------------------------------------------- #
# Grounded AI turn (analyst over computed metrics, not an advisor)
# --------------------------------------------------------------------------- #

_SYSTEM = """You are a general-purpose data analysis assistant. You summarize, rank, describe trends, and explain risk in the user's data — grounding EVERY statement in the EVIDENCE CORPUS below, which contains ONLY figures the user provided and metrics computed DETERMINISTICALLY from them — datasets (`dataset:` ids), series and document-extracted figures (`series:` / `figure:` ids), computed metrics and ratios (`metric:` / `ratio:` ids), correlations (`corr:` ids), and cross-dataset comparisons (`compare:` ids).

HARD RULES:
- Cite ONLY the bracketed ids that appear in the EVIDENCE CORPUS. NEVER invent a number, ratio, percentage, date, or id.
- Every quantitative claim MUST cite the `metric:`/`ratio:`/`corr:`/`compare:`/`figure:` id it comes from. The metrics were already computed for you — do not recompute or estimate.
- Summaries, rankings, and trend descriptions are welcome — build them from the cited `metric:` records (latest / trend / peak / low / total / share) rather than raw guesswork.
- You MAY interpret and contextualize (what a trend, volatility, VaR, loss ratio, or drawdown implies), but the underlying numbers must be cited, not restated from memory.
- Where the corpus does not address a point, say so plainly under open_questions — never speculate or fill gaps.
- You are an ANALYST, not an advisor: explain what the numbers say; do not give investment, actuarial, or coverage advice.

FOCUSED RECORDS: when the user has highlighted records, address them specifically. If the user is questioning a DOCUMENT-EXTRACTED figure (`figure:` ids) and the conversation establishes the stored value is wrong (mis-read units, transposed periods, typo), you MAY propose a correction in `proposed_edits` — the user reviews and applies it; you never change data yourself. Only propose edits for values you can justify from the conversation; use the exact line-item label and period shown in the corpus.

Return STRICT JSON ONLY (no markdown, no prose outside the JSON), shape:
{"assistant_text": "<your precise, conversational reply>",
 "evidence_map": [{"point": "<a factual observation grounded in the corpus>", "cited_ids": ["<id>", ...]}],
 "open_questions": ["<what the data does NOT establish / what to obtain or verify>"],
 "proposed_edits": [{"dataset_id": "<uuid of the pdf dataset>", "label": "<exact line-item label>", "period": "<exact period label>", "current_value": <number or null>, "proposed_value": <number>, "reason": "<why the stored value is wrong>"}]}
`proposed_edits` is OPTIONAL — omit it (or use []) unless a document figure is genuinely in question."""


def _corpus_text(corpus: dict) -> str:
    out = []
    for key, s in corpus.get("sources", {}).items():
        if not s["records"]:
            continue
        out.append(f"## {s['label']} ({key})")
        for r in s["records"]:
            out.append(f"- [{r['cid']}] {r['summary']}")
    return "\n".join(out) or "(no analyzed datasets in scope)"


def _history_text(history: list[dict]) -> str:
    msgs = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-_HISTORY_TURNS:]
    return "\n".join(f"[{m['role']}] {m.get('content', '')}" for m in msgs) or "(no prior messages)"


def _focus_text(focus_records: list[dict] | None) -> str:
    if not focus_records:
        return ""
    lines = "\n".join(f"- [{r['cid']}] {r.get('summary', '')}" for r in focus_records)
    return f"\nFOCUSED RECORDS (the user highlighted these — address them specifically):\n{lines}\n"


def _build_prompt(session: dict, corpus: dict, history: list[dict], latest: str,
                  focus_records: list[dict] | None = None) -> str:
    return f"""{_SYSTEM}

ANALYSIS SESSION: {session.get('title') or 'Data analysis'}
DOMAIN / GOAL: {session.get('domain') or 'general'} — {session.get('goal') or '(not specified)'}

EVIDENCE CORPUS (the ONLY records you may cite):
{_corpus_text(corpus)}
{_focus_text(focus_records)}
CONVERSATION (oldest first):
{_history_text(history)}

LATEST USER MESSAGE:
{latest}
"""


async def _generate(session: dict, corpus: dict, history: list[dict], latest: str,
                    focus_records: list[dict] | None = None) -> dict:
    from google.genai import types
    prompt = _build_prompt(session, corpus, history, latest, focus_records)
    resp = await asyncio.wait_for(
        _genai().aio.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        ),
        timeout=_GEMINI_TIMEOUT,
    )
    data = _parse_json(getattr(resp, "text", "") or "")
    return {
        "assistant_text": str(data.get("assistant_text") or "").strip(),
        "evidence_map": data.get("evidence_map") or [],
        "open_questions": [str(q) for q in (data.get("open_questions") or []) if q],
        "proposed_edits": data.get("proposed_edits") or [],
    }


async def run_chat_turn(session: dict, corpus: dict, history: list[dict], latest: str,
                        focus_records: list[dict] | None = None,
                        datasets: list[dict] | None = None):
    """Async generator of SSE-shaped dicts for one grounded turn. Status tick →
    single validated ``result`` (both gates — citations AND edit proposals —
    run before anything reaches the user)."""
    yield {"type": "status", "message": "Analyzing your data…"}
    try:
        result = await _generate(session, corpus, history, latest, focus_records)
    except asyncio.TimeoutError:
        yield {"type": "error", "message": "Analysis timed out — please try again."}
        return
    except Exception:
        logger.exception("analysis_pilot: chat turn failed")
        yield {"type": "error", "message": "Analysis failed — please try again."}
        return

    clean_map, dropped = validate_citations(result.get("evidence_map"), corpus.get("index", {}))
    result["evidence_map"] = clean_map
    if dropped:
        result["dropped_citations"] = dropped
        logger.info("analysis_pilot: dropped %d hallucinated citation(s)", len(dropped))

    clean_edits, dropped_edits = validate_edit_proposals(result.get("proposed_edits"), datasets or [])
    result["proposed_edits"] = clean_edits
    if dropped_edits:
        result["dropped_edits"] = dropped_edits
        logger.info("analysis_pilot: dropped %d invalid edit proposal(s)", len(dropped_edits))

    if not result["assistant_text"]:
        result["assistant_text"] = (
            "I couldn't produce an analysis from the data this time. Try rephrasing, "
            "or check that your datasets finished processing."
        )
    yield {"type": "result", "data": result}


# --------------------------------------------------------------------------- #
# Analyst report PDF — deterministic metrics/charts + grounded narrative with
# footnote-style citations. Model text appears ONLY in the narrative; every
# tile/table/chart is rendered from the stored computed metrics.
# --------------------------------------------------------------------------- #

_REPORT_CSS = """
  @page { size: Letter; margin: 18mm 15mm 16mm 15mm;
    @bottom-left { content: "Analysis Pilot analysis — confidential"; font-size:7px; color:#9ca3af; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size:7px; color:#9ca3af; } }
  body { padding:0; }
  .letterhead { display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:2px solid #166534; padding-bottom:10px; }
  .brand { font-size:8px; letter-spacing:2px; text-transform:uppercase; color:#166534; font-weight:700; }
  h1 { border:none; color:#14532d; font-size:20px; margin:2px 0; }
  h2 { border-bottom:2px solid #166534; color:#14532d; page-break-after:avoid; }
  h3 { color:#14532d; font-size:12px; margin:10px 0 4px; }
  .tiles { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; }
  .tile { flex:1; min-width:110px; border:1px solid #e5e7eb; border-radius:8px; padding:7px 10px; }
  .tile .l { font-size:7.5px; text-transform:uppercase; letter-spacing:.6px; color:#888; }
  .tile .v { font-size:15px; font-weight:600; color:#14532d; margin-top:2px; }
  .chart { margin:6px 0; page-break-inside:avoid; }
  .chart .t { font-size:8px; color:#888; text-transform:uppercase; letter-spacing:.5px; }
  .ds { page-break-inside:avoid; margin-bottom:10px; }
  .narr { background:#f4faf6; border-left:3px solid #166534; padding:8px 12px; border-radius:0 6px 6px 0; }
  .narr p { margin:0 0 7px; } .narr p:last-child { margin-bottom:0; }
  sup.cite { color:#166534; font-weight:700; }
  .obs { display:flex; gap:10px; margin:8px 0; padding:8px 10px; border:1px solid #e5e7eb; border-radius:8px; page-break-inside:avoid; }
  .obs-n { flex-shrink:0; width:18px; height:18px; border-radius:50%; background:#166534; color:#fff;
    font-size:9px; font-weight:700; display:flex; align-items:center; justify-content:center; }
  .obs-point { font-weight:600; margin-bottom:2px; }
  tr, .tile { page-break-inside:avoid; }
"""

_GONE = "(no longer in scope at generation time)"


def _cited_ids(memo: dict) -> list[str]:
    seen, out = set(), []
    for item in memo.get("evidence_map") or []:
        for c in item.get("cited_ids") or []:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _table_html(table: dict) -> str:
    cols = "".join(f"<th>{_esc(c)}</th>" for c in table.get("columns") or [])
    rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
        for row in table.get("rows") or []
    ) or f"<tr><td colspan='{len(table.get('columns') or []) or 1}'>No data.</td></tr>"
    return (f"<h3>{_esc(table.get('title'))}</h3>"
            f"<table><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table>")


def _block_html(block: dict) -> str:
    tiles = "".join(
        f"<div class='tile'><div class='l'>{_esc(t.get('label'))}</div>"
        f"<div class='v'>{_esc(t.get('value'))}</div></div>"
        for t in block.get("tiles") or []
    )
    tiles_html = f"<div class='tiles'>{tiles}</div>" if tiles else ""
    tables = "".join(_table_html(t) for t in block.get("tables") or [])
    charts = "".join(
        f"<div class='chart'><div class='t'>{_esc(c.get('title'))}</div>{c.get('svg') or ''}</div>"
        for c in block.get("charts") or []
    )
    return f"<h3 style='border-bottom:1px solid #e5e7eb'>{_esc(block.get('label'))}</h3>{tiles_html}{tables}{charts}"


def _dataset_section_html(d: dict) -> str:
    norm = d.get("normalized") or {}
    kind = norm.get("kind") or "generic"
    src = (norm.get("meta") or {}).get("source_kind") or d.get("source_kind") or "?"
    if d.get("status") == "needs_review":
        # Review gate: unconfirmed document extractions never present computed
        # metrics in an exported report — only the notice that review is due.
        return (f"<div class='ds'><h2>Dataset — {_esc(d.get('filename'))}</h2>"
                f"<p class='sub'>{kind} · source {src}</p>"
                f"<div class='narr'>Document-extracted figures are pending review. "
                f"Computed metrics are excluded from this report until the figures "
                f"are confirmed in Analysis Pilot.</div></div>")
    metrics = d.get("metrics") or {}
    blocks = "".join(_block_html(b) for pk, b in metrics.items() if pk != "_warnings" and b)
    return (f"<div class='ds'><h2>Dataset — {_esc(d.get('filename'))}</h2>"
            f"<p class='sub'>{kind} · source {src}</p>{blocks or '<p>No metrics computed.</p>'}</div>")


def _comparison_section_html(c: dict) -> str:
    result = c.get("result") or {}
    return f"<div class='ds'><h2>Comparison — {_esc(c.get('title'))}</h2>{_block_html(result)}</div>"


def _narrative_html(text: str) -> str:
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    return "".join(f"<p>{_esc(p)}</p>" for p in paras) or "<p>—</p>"


def _report_html(session: dict, corpus: dict, memo: dict, datasets: list[dict],
                 comparisons: list[dict], company_name: str | None) -> str:
    index = corpus.get("index", {})
    cited = _cited_ids(memo)
    fn = {c: i + 1 for i, c in enumerate(cited)}

    points = ""
    for n, item in enumerate(memo.get("evidence_map") or [], start=1):
        cites = "".join(
            f"<li><sup class='cite'>[{fn.get(c, '?')}]</sup> "
            f"{_esc(index[c].get('summary', '')) if c in index else _GONE}</li>"
            for c in (item.get("cited_ids") or [])
        )
        points += (f"<div class='obs'><div class='obs-n'>{n}</div>"
                   f"<div><div class='obs-point'>{_esc(item.get('point'))}</div>"
                   f"<ul>{cites or '<li>—</li>'}</ul></div></div>")
    points = points or "<p>No grounded observations were recorded.</p>"

    oq = "".join(f"<li>{_esc(q)}</li>" for q in (memo.get("open_questions") or []))
    oq_block = f"<ul>{oq}</ul>" if oq else "<p>None recorded.</p>"

    idx_rows = "".join(
        f"<tr><td>[{fn[c]}]</td><td>{_esc(index[c].get('source_label', ''))}</td>"
        f"<td>{_esc(index[c].get('ref', ''))}</td><td>{_esc(index[c].get('summary', ''))}</td></tr>"
        if c in index else f"<tr><td>[{fn[c]}]</td><td colspan='3'>{_GONE}</td></tr>"
        for c in cited
    ) or "<tr><td colspan='4'>No records cited.</td></tr>"

    ds_sections = "".join(_dataset_section_html(d) for d in datasets
                          if d.get("status") in ("ready", "needs_review"))
    cmp_sections = "".join(_comparison_section_html(c) for c in comparisons or [])

    notes = "".join(f"<li>{_esc(n)}</li>" for n in corpus.get("notes") or [])
    notes_block = f"<h2>Scope notes</h2><ul>{notes}</ul>" if notes else ""

    generated = datetime.now(timezone.utc).strftime("%B %d, %Y · %H:%M UTC")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
      <style>{_PDF_CSS}{_REPORT_CSS}</style></head><body>
      <div class="letterhead">
        <div><div class="brand">Matcha · Analysis Pilot</div>
          <h1>Data Analysis Report</h1><p class="sub">{_esc(session.get('title'))}</p></div>
        <div class="meta" style="font-size:9px;color:#888;text-align:right">
          {f"<div style='font-weight:600;color:#1a1a2e'>{_esc(company_name)}</div>" if company_name else ""}
          <div>Generated {generated}</div></div>
      </div>

      <div class="narr" style="margin-top:10px"><b>About this report.</b> A sourced analysis of the data
      you provided. Every metric was computed deterministically from your figures; every observation cites
      the specific records it relies on. {_esc(DISCLAIMER)}</div>

      <h2>Analysis narrative</h2>
      <div class="narr">{_narrative_html(memo.get('assistant_text') or '')}</div>

      <h2>Grounded observations</h2>
      {points}

      <h2>Open questions</h2>
      {oq_block}

      {cmp_sections}
      {ds_sections}

      <h2>Evidence index (cited records)</h2>
      <table><thead><tr><th>#</th><th>Source</th><th>Ref</th><th>Record</th></tr></thead>
      <tbody>{idx_rows}</tbody></table>

      {notes_block}
      <div class="foot">{_esc(DISCLAIMER)}</div>
    </body></html>"""


async def _render_pdf(html_str: str) -> bytes:
    def _r() -> bytes:
        from weasyprint import HTML
        return HTML(string=html_str, url_fetcher=safe_url_fetcher).write_pdf()
    return await asyncio.to_thread(_r)


async def build_analysis_report(session: dict, corpus: dict, memo: dict, datasets: list[dict],
                                comparisons: list[dict], company_name: str | None = None) -> dict:
    """Render the analyst report. Returns ``{"pdf": bytes, "citations": [...]}``."""
    html = _report_html(session, corpus, memo, datasets, comparisons, company_name)
    pdf = await _render_pdf(html)
    return {"pdf": pdf, "citations": _cited_ids(memo)}
