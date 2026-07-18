"""Analysis Pilot routes (`/analysis-pilot/pilot/*`) — company-scoped, gated at mount by
`require_feature("analysis_pilot")`.

Bring-your-own-data risk analysis: the company opens a session, uploads datasets
(CSV / XLSX / financial-document PDF), a DETERMINISTIC engine computes the risk
metrics (`services/analysis_packs`, run via asyncio.to_thread — it is seconds of
pure CPU), and a GROUNDED AI narrates over the computed numbers and exports an
analyst report. Documents go through a Gemini extraction the user CONFIRMS
before the metrics enter the corpus/report (until then the dataset is
`needs_review` and only its raw figures are citable, marked unverified).
Every mutation/generation/download is audit-logged. Tenant isolation on every
route via `get_client_company_id`.
"""

import asyncio
import json
import logging
import math
from datetime import timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.core.services.storage import get_storage
from app.matcha.services import analysis_pilot as ap
from app.matcha.services import analysis_packs as packs
from app.matcha.services.er_document_parser import ERDocumentParser
from app.matcha.models.analysis_pilot import (
    SessionCreate, SessionUpdate, DatasetPatch, ComparisonCreate, ChatIn, ReportIn, DemoDatasetIn,
)
# Shared ASCII filename hardening (Starlette latin-1-encodes headers).
from .legal_defense import _safe_name, _safe_filename

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_BYTES = 25_000_000
_MAX_DATASETS_PER_SESSION = 20
_EXT_TO_KIND = {".csv": "csv", ".xlsx": "xlsx", ".pdf": "pdf"}

# Bundled sample datasets for the Examples tab's live demo — small, self-contained
# CSVs shipped with the server (not user data), one per analyzer-pack domain, so
# clicking an example shows a real computed-and-cited answer, not a mockup.
_DEMO_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "analysis_pilot_demos"
_DEMO_DATASETS = {
    "volatility": "fund_prices_weekly.csv",
    "financial": "quarterly_financials.csv",
    "insurance": "gl_loss_run.csv",
    "inventory": "inventory_ops_monthly.csv",
}

# Explicit column list — `SELECT *` would drag multi-MB `normalized` jsonb
# through the pool on every load. Slim mode drops the heavy series values
# (callers that only need names/roles/metrics: session GET, dataset list).
_DATASET_COLS = ("id, session_id, company_id, filename, storage_path, source_kind, "
                 "content_type, file_size, row_count, column_count, status, extraction, "
                 "normalized, mapping, metrics, config, error, uploaded_by, created_at")
_DATASET_COLS_SLIM = _DATASET_COLS.replace("normalized,", "(normalized - 'series') AS normalized,")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _parse_jsonb(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def _dump_jsonb(obj) -> Optional[str]:
    """json.dumps that can never emit bare NaN/Infinity tokens — Postgres
    rejects them on the ::jsonb cast, which would 500 a request from data that
    merely contained a non-finite float."""
    if obj is None:
        return None

    def _san(x):
        if isinstance(x, float) and not math.isfinite(x):
            return None
        if isinstance(x, dict):
            return {k: _san(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_san(v) for v in x]
        return x

    return json.dumps(_san(obj))


async def _audit(conn, session_id, current_user, request: Request, action: str,
                 details: dict | None = None):
    await conn.execute(
        """INSERT INTO analysis_pilot_audit_log (session_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        session_id, getattr(current_user, "id", None), action,
        json.dumps(details or {}), client_ip(request),
    )


async def _load_session(conn, session_id: str, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM analysis_pilot_sessions WHERE id = $1 AND company_id = $2",
        session_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


async def _load_messages(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM analysis_pilot_messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return [{**dict(r), "metadata": _parse_jsonb(r["metadata"])} for r in rows]


_compaction_tasks: set = set()  # strong refs so fire-and-forget tasks aren't GC'd mid-flight


def _spawn_compaction(session_id: str) -> None:
    task = asyncio.create_task(_maybe_compact(session_id))
    _compaction_tasks.add(task)
    task.add_done_callback(_compaction_tasks.discard)


async def _maybe_compact(session_id: str) -> None:
    """Roll older turns into a summary row once enough have accrued since the
    last one. Best-effort, fire-and-forget (see callsite): opens its OWN
    connection and must never be awaited inline on the chat response path — the
    summarization call can take up to ~60s and the client is already done
    reading the stream by the time this runs."""
    try:
        async with get_connection() as conn:
            history = await _load_messages(conn, session_id)
            split = ap.split_history(history)
            if split["uncompacted_count"] <= ap._COMPACT_TRIGGER:
                return
            to_compact = split["recent"][:-ap._HISTORY_TURNS]
            if not to_compact:
                return
            summary = await ap.summarize_history(to_compact, split["summary"])
            if not summary:
                return
            # Position the summary row just AFTER the last compacted message so
            # the newest _HISTORY_TURNS kept-live turns sort after it and stay
            # verbatim in the prompt (split_history takes messages after the
            # latest summary).
            boundary = to_compact[-1].get("created_at")
            created_at = (boundary + timedelta(microseconds=1)) if boundary else None
            await conn.execute(
                "INSERT INTO analysis_pilot_messages (session_id, role, content, metadata, created_at) "
                "VALUES ($1,'system',$2,$3, COALESCE($4, NOW()))",
                session_id, summary,
                json.dumps({"kind": "summary", "covers": len(to_compact)}), created_at)
    except Exception:
        logger.exception("analysis_pilot: compaction hook failed")


async def _load_datasets(conn, session_id: str, *, slim: bool = False) -> list[dict]:
    cols = _DATASET_COLS_SLIM if slim else _DATASET_COLS
    rows = await conn.fetch(
        f"SELECT {cols} FROM analysis_pilot_datasets WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("extraction", "normalized", "mapping", "metrics", "config"):
            d[k] = _parse_jsonb(d.get(k))
        out.append(d)
    return out


async def _load_dataset(conn, session_id: str, dataset_id: str) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_DATASET_COLS} FROM analysis_pilot_datasets WHERE id=$1 AND session_id=$2",
        dataset_id, session_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Dataset not found")
    d = dict(row)
    for k in ("extraction", "normalized", "mapping", "metrics", "config"):
        d[k] = _parse_jsonb(d.get(k))
    return d


async def _load_comparisons(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, title, dataset_ids, spec, result, created_at FROM analysis_pilot_comparisons "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("dataset_ids", "spec", "result"):
            d[k] = _parse_jsonb(d.get(k))
        out.append(d)
    return out


async def _latest_memo(conn, session_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT content, metadata FROM analysis_pilot_messages "
        "WHERE session_id = $1 AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
        session_id,
    )
    if not row:
        return None
    meta = _parse_jsonb(row["metadata"]) or {}
    return {
        "assistant_text": row["content"] or "",
        "evidence_map": meta.get("evidence_map") or [],
        "open_questions": meta.get("open_questions") or [],
    }


def _dataset_out(d: dict) -> dict:
    """API payload for a dataset — parsed jsonb, heavy series values stripped
    (the mapping UI only needs names/roles/periods), engine warnings surfaced
    as their own field instead of masquerading as a metrics pack."""
    norm = d.get("normalized") or {}
    columns = norm.get("columns") or list((norm.get("series") or {}).keys())
    slim_norm = {
        "roles": norm.get("roles") or {},
        "kind": norm.get("kind"),
        "periods": norm.get("periods"),
        "columns": columns,
        "meta": norm.get("meta") or {},
    }
    metrics = d.get("metrics") or {}
    return {
        "id": str(d.get("id")),
        "filename": d.get("filename"),
        "source_kind": d.get("source_kind"),
        "status": d.get("status"),
        "row_count": d.get("row_count"),
        "column_count": d.get("column_count"),
        "error": d.get("error"),
        "created_at": d.get("created_at"),
        "extraction": d.get("extraction"),
        "config": d.get("config") or {},
        "mapping": d.get("mapping") or {},
        "normalized": slim_norm,
        "metrics": {k: v for k, v in metrics.items() if k != "_warnings"},
        "warnings": list(metrics.get("_warnings") or []),
    }


async def _read_upload(file: UploadFile) -> tuple[bytes, str, str]:
    filename = file.filename or "dataset"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == ".xls":
        raise HTTPException(status_code=400, detail="Legacy .xls isn't supported — save as .xlsx or .csv.")
    if ext not in _EXT_TO_KIND:
        raise HTTPException(status_code=400, detail="Unsupported file — upload a CSV, XLSX, or PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (25 MB max)")
    return data, filename, _EXT_TO_KIND[ext]


async def _persist_dataset_analysis(ds_id, session_id: str, status: str, error,
                                    extraction, normalized, metrics,
                                    row_count: int, column_count: int) -> dict:
    async with get_connection() as conn:
        updated = await conn.fetchrow(
            f"""UPDATE analysis_pilot_datasets
               SET status=$2, error=$3, extraction=$4::jsonb, normalized=$5::jsonb,
                   metrics=$6::jsonb, row_count=$7, column_count=$8
               WHERE id=$1 RETURNING {_DATASET_COLS}""",
            ds_id, status, error,
            _dump_jsonb(extraction), _dump_jsonb(normalized), _dump_jsonb(metrics),
            row_count, column_count,
        )
        await conn.execute("UPDATE analysis_pilot_sessions SET updated_at=NOW() WHERE id=$1", session_id)
    d = dict(updated)
    for k in ("extraction", "normalized", "mapping", "metrics", "config"):
        d[k] = _parse_jsonb(d.get(k))
    return d


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions")
async def create_session(body: SessionCreate, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO analysis_pilot_sessions (company_id, title, domain, goal, created_by)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            company_id, body.title, body.domain, body.goal, getattr(current_user, "id", None),
        )
        await _audit(conn, row["id"], current_user, request, "create",
                     {"title": body.title, "domain": body.domain})
    return dict(row)


@router.get("/pilot/sessions")
async def list_sessions(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT s.*,
                   (SELECT COUNT(*) FROM analysis_pilot_messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT COUNT(*) FROM analysis_pilot_datasets d WHERE d.session_id = s.id) AS dataset_count,
                   (SELECT COUNT(*) FROM analysis_pilot_packets p WHERE p.session_id = s.id) AS packet_count
               FROM analysis_pilot_sessions s
               WHERE s.company_id = $1 ORDER BY s.updated_at DESC""",
            company_id,
        )
    return [dict(r) for r in rows]


@router.get("/pilot/sessions/{session_id}")
async def get_session(session_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        session["messages"] = await _load_messages(conn, session_id)
        session["datasets"] = [_dataset_out(d) for d in await _load_datasets(conn, session_id, slim=True)]
        session["comparisons"] = await _load_comparisons(conn, session_id)
        packets = await conn.fetch(
            "SELECT id, filename, citations, file_size, generated_at "
            "FROM analysis_pilot_packets WHERE session_id = $1 ORDER BY generated_at DESC",
            session_id,
        )
        session["packets"] = [{**dict(p), "citations": _parse_jsonb(p["citations"])} for p in packets]
    session["canonical_roles"] = list(packs.CANONICAL_ROLES)
    session["message_count"] = sum(1 for m in session["messages"] if m.get("role") in ("user", "assistant"))
    session["message_limit"] = ap._MAX_SESSION_MESSAGES
    return session


@router.patch("/pilot/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdate, request: Request,
                         current_user=Depends(require_admin_or_client)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        sets, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=1):
            sets.append(f"{k} = ${i}")
            vals.append(v)
        vals.extend([session_id, company_id])
        closed = ", closed_at = NOW()" if fields.get("status") == "closed" else ""
        row = await conn.fetchrow(
            f"UPDATE analysis_pilot_sessions SET {', '.join(sets)}, updated_at = NOW(){closed} "
            f"WHERE id = ${len(vals) - 1} AND company_id = ${len(vals)} RETURNING *",
            *vals,
        )
        await _audit(conn, session_id, current_user, request, "update", {"fields": list(fields.keys())})
    return dict(row)


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/datasets")
async def upload_dataset(session_id: str, request: Request, file: UploadFile = File(...),
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    data, filename, source_kind = await _read_upload(file)

    # Pre-work: ownership, cap, local text extraction (pdf), S3 store, row insert.
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        await check_rate_limit(str(company_id), "analysis_pilot_upload", 40, 3600)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM analysis_pilot_datasets WHERE session_id = $1", session_id)
        if int(count or 0) >= _MAX_DATASETS_PER_SESSION:
            raise HTTPException(status_code=400,
                                detail=f"Session dataset limit reached ({_MAX_DATASETS_PER_SESSION})")
        text = ""
        if source_kind == "pdf":
            try:
                text, _pages = await asyncio.to_thread(
                    ERDocumentParser().extract_text_from_bytes, data, filename)
            except Exception:  # noqa: BLE001
                logger.warning("analysis_pilot: local text extraction failed for %s", filename)
        try:
            storage_path = await get_storage().upload_private_file(
                data, filename, prefix=f"analysis-pilot/{session_id}", content_type=file.content_type)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO analysis_pilot_datasets
                   (session_id, company_id, filename, storage_path, source_kind,
                    content_type, file_size, uploaded_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            session_id, company_id, filename, storage_path, source_kind,
            file.content_type, len(data), getattr(current_user, "id", None),
        )
        ds_id = row["id"]
        await _audit(conn, session_id, current_user, request, "upload",
                     {"dataset_id": str(ds_id), "filename": filename, "source_kind": source_kind})

    # Analysis (connection released). Parsing + the analyzer packs are seconds
    # of pure CPU — run in a worker thread, never on the event loop. The PDF
    # branch calls Gemini; its unconfirmed metrics stay out of the corpus
    # (`needs_review`) until the user reviews the figures.
    status, error, extraction, normalized, metrics = "ready", None, None, {}, {}
    row_count = column_count = 0
    try:
        if source_kind == "pdf":
            result = await ap.extract_dataset(data, text, is_pdf=True, filename=filename)
            extraction = result["extraction"]
            if not result["available"]:
                status, error = "failed", "No numeric data could be extracted from the document."
            else:
                normalized, metrics, (row_count, column_count) = await asyncio.to_thread(
                    ap.analyze_dataset, ds_id, source_kind, filename, extraction=extraction)
                status = "needs_review"  # figures must be confirmed before metrics count
        else:
            parsed = await asyncio.to_thread(packs.parse_tabular, data, source_kind)
            normalized, metrics, (row_count, column_count) = await asyncio.to_thread(
                ap.analyze_dataset, ds_id, source_kind, filename, parsed=parsed)
            if not normalized.get("series"):
                status, error = "failed", "No numeric columns detected."
    except Exception:  # noqa: BLE001 - degrade, never 500 the upload
        logger.exception("analysis_pilot: analysis failed for %s", filename)
        status, error = "failed", "Could not analyze the file."

    updated = await _persist_dataset_analysis(ds_id, session_id, status, error,
                                              extraction, normalized, metrics,
                                              row_count, column_count)
    return _dataset_out(updated)


@router.post("/pilot/sessions/{session_id}/datasets/demo")
async def load_demo_dataset(session_id: str, body: DemoDatasetIn, request: Request,
                            current_user=Depends(require_admin_or_client)):
    """Load one of the bundled sample datasets (Examples tab's live demo) into
    this session — same pipeline as `upload_dataset` post-multipart-read, minus
    the upload itself. Idempotent: a repeat call for a demo_key already present
    in this session just returns the existing row."""
    company_id = await get_client_company_id(current_user)
    filename = _DEMO_DATASETS[body.demo_key]
    data = (_DEMO_DATA_DIR / filename).read_bytes()

    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        existing = await conn.fetchrow(
            "SELECT * FROM analysis_pilot_datasets WHERE session_id = $1 AND filename = $2",
            session_id, filename)
        if existing:
            return _dataset_out(dict(existing))
        storage_path = await get_storage().upload_private_file(
            data, filename, prefix=f"analysis-pilot/{session_id}", content_type="text/csv")
        row = await conn.fetchrow(
            """INSERT INTO analysis_pilot_datasets
                   (session_id, company_id, filename, storage_path, source_kind,
                    content_type, file_size, uploaded_by)
               VALUES ($1,$2,$3,$4,'csv','text/csv',$5,$6) RETURNING id""",
            session_id, company_id, filename, storage_path, len(data),
            getattr(current_user, "id", None),
        )
        ds_id = row["id"]
        await _audit(conn, session_id, current_user, request, "upload",
                     {"dataset_id": str(ds_id), "filename": filename, "source_kind": "csv", "demo_key": body.demo_key})

    status, error, normalized, metrics = "ready", None, {}, {}
    row_count = column_count = 0
    try:
        parsed = await asyncio.to_thread(packs.parse_tabular, data, "csv")
        normalized, metrics, (row_count, column_count) = await asyncio.to_thread(
            ap.analyze_dataset, ds_id, "csv", filename, parsed=parsed)
        if not normalized.get("series"):
            status, error = "failed", "No numeric columns detected."
    except Exception:  # noqa: BLE001 - degrade, never 500
        logger.exception("analysis_pilot: demo analysis failed for %s", filename)
        status, error = "failed", "Could not analyze the demo file."

    updated = await _persist_dataset_analysis(ds_id, session_id, status, error,
                                              None, normalized, metrics,
                                              row_count, column_count)
    return _dataset_out(updated)


@router.get("/pilot/sessions/{session_id}/datasets")
async def list_datasets(session_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        datasets = await _load_datasets(conn, session_id, slim=True)
    return [_dataset_out(d) for d in datasets]


@router.patch("/pilot/sessions/{session_id}/datasets/{dataset_id}")
async def patch_dataset(session_id: str, dataset_id: str, body: DatasetPatch, request: Request,
                        current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        d = await _load_dataset(conn, session_id, dataset_id)

    is_pdf = d["source_kind"] == "pdf"
    if body.extraction is not None and not is_pdf:
        raise HTTPException(status_code=400,
                            detail="Extraction only applies to document (PDF) datasets.")
    if body.reextract and not is_pdf:
        raise HTTPException(status_code=400,
                            detail="Re-extraction only applies to document (PDF) datasets.")
    if body.orientation is not None and is_pdf:
        raise HTTPException(status_code=400,
                            detail="Orientation only applies to tabular (CSV/XLSX) datasets.")

    # Merge overrides.
    mapping = {**(d.get("mapping") or {}), **(body.mapping or {})}
    config = dict(d.get("config") or {})
    if body.column_kinds is not None:
        config["column_kinds"] = {**(config.get("column_kinds") or {}), **body.column_kinds}
    if body.periods_per_year is not None:
        config["periods_per_year"] = body.periods_per_year
    if body.risk_free is not None:
        config["risk_free"] = body.risk_free
    if body.orientation is not None:
        config["orientation"] = body.orientation

    extraction = d.get("extraction")
    audit_action = "confirm_mapping"
    status = "ready"  # a confirmed/recomputed dataset is trusted
    error = None
    try:
        if body.reextract:
            # Recovery path: transient Gemini failure at upload must not be
            # terminal — re-run the extraction from the stored original.
            audit_action = "reextract"
            raw = await get_storage().download_file(d["storage_path"])
            result = await ap.extract_dataset(raw, "", is_pdf=True, filename=d["filename"])
            extraction = result["extraction"]
            if not result["available"]:
                raise HTTPException(status_code=502,
                                    detail="Extraction failed again — try later or enter figures manually.")
            status = "needs_review"  # fresh extraction ⇒ back through the review gate
            normalized, metrics, counts = await asyncio.to_thread(
                ap.analyze_dataset, dataset_id, d["source_kind"], d["filename"],
                extraction=extraction, mapping=mapping, config=config, kind=body.kind)
        elif body.orientation is not None:
            # Orientation override re-parses the STORED ORIGINAL — the stored
            # normalized series are already oriented, so they can't be reused.
            audit_action = "reorient"
            raw = await get_storage().download_file(d["storage_path"])
            parsed = await asyncio.to_thread(packs.parse_tabular, raw, d["source_kind"], body.orientation)
            normalized, metrics, counts = await asyncio.to_thread(
                ap.analyze_dataset, dataset_id, d["source_kind"], d["filename"],
                parsed=parsed, mapping=mapping, config=config, kind=body.kind)
        elif is_pdf and (body.extraction is not None or extraction is not None):
            coerced = ap.coerce_extraction(body.extraction if body.extraction is not None else extraction)
            extraction = coerced
            normalized, metrics, counts = await asyncio.to_thread(
                ap.analyze_dataset, dataset_id, d["source_kind"], d["filename"],
                extraction=coerced, mapping=mapping, config=config, kind=body.kind)
        else:
            normalized, metrics, counts = await asyncio.to_thread(
                ap.analyze_dataset, dataset_id, d["source_kind"], d["filename"],
                prev_normalized=d.get("normalized") or {}, mapping=mapping,
                config=config, kind=body.kind)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("analysis_pilot: recompute failed for %s", dataset_id)
        raise HTTPException(status_code=400, detail="Could not recompute with those settings.")

    if not normalized.get("series"):
        # A recompute that yields nothing must NOT promote the dataset into the
        # corpus as an empty-but-'ready' record.
        status, error = "failed", "No numeric series after recompute."
    row_count, column_count = counts

    async with get_connection() as conn:
        updated = await conn.fetchrow(
            f"""UPDATE analysis_pilot_datasets
               SET status=$2, error=$3, mapping=$4::jsonb, config=$5::jsonb, extraction=$6::jsonb,
                   normalized=$7::jsonb, metrics=$8::jsonb, row_count=$9, column_count=$10
               WHERE id=$1 RETURNING {_DATASET_COLS}""",
            dataset_id, status, error, _dump_jsonb(mapping), _dump_jsonb(config),
            _dump_jsonb(extraction), _dump_jsonb(normalized), _dump_jsonb(metrics),
            row_count, column_count,
        )
        await _audit(conn, session_id, current_user, request, audit_action,
                     {"dataset_id": dataset_id})
        await conn.execute("UPDATE analysis_pilot_sessions SET updated_at=NOW() WHERE id=$1", session_id)
    out = dict(updated)
    for k in ("extraction", "normalized", "mapping", "metrics", "config"):
        out[k] = _parse_jsonb(out.get(k))
    return _dataset_out(out)


@router.delete("/pilot/sessions/{session_id}/datasets/{dataset_id}")
async def delete_dataset(session_id: str, dataset_id: str, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        row = await conn.fetchrow(
            "DELETE FROM analysis_pilot_datasets WHERE id=$1 AND session_id=$2 RETURNING storage_path",
            dataset_id, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        await _audit(conn, session_id, current_user, request, "delete_dataset", {"dataset_id": dataset_id})
    try:
        await get_storage().delete_private_file(row["storage_path"])
    except Exception:  # noqa: BLE001
        logger.warning("analysis_pilot: could not delete stored file %s", row["storage_path"])
    return {"deleted": True}


@router.get("/pilot/sessions/{session_id}/datasets/{dataset_id}/download")
async def download_dataset(session_id: str, dataset_id: str, request: Request,
                           current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        row = await conn.fetchrow(
            "SELECT storage_path, filename FROM analysis_pilot_datasets WHERE id=$1 AND session_id=$2",
            dataset_id, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        # Source financial documents leaving the system must land in the trail.
        await _audit(conn, session_id, current_user, request, "download_dataset",
                     {"dataset_id": dataset_id, "filename": row["filename"]})
    url = get_storage().get_presigned_download_url(row["storage_path"], expires_in=900)
    if not url:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    return {"url": url, "filename": row["filename"]}


# --------------------------------------------------------------------------- #
# Comparisons
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/comparisons")
async def create_comparison(session_id: str, body: ComparisonCreate, request: Request,
                            current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    ids = [str(x) for x in body.dataset_ids]
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        rows = await conn.fetch(
            "SELECT id, filename, metrics FROM analysis_pilot_datasets "
            "WHERE session_id=$1 AND id = ANY($2::uuid[])",
            session_id, ids)
        by_id = {str(r["id"]): dict(r) for r in rows}
        # Preserve the caller's order (the comparison axis).
        ordered = [by_id[i] for i in ids if i in by_id]
        if len(ordered) < 2:
            raise HTTPException(status_code=400, detail="Select at least two datasets in this session.")
        payload = [{"id": str(d["id"]), "label": d["filename"],
                    "metrics": _parse_jsonb(d.get("metrics")) or {}} for d in ordered]
        # Mint the id first so the stored result's `compare:<id>:…` cids are
        # keyed correctly in ONE build + ONE insert.
        cmp_id = uuid4()
        result = packs.build_comparison(str(cmp_id), payload)
        row = await conn.fetchrow(
            """INSERT INTO analysis_pilot_comparisons
                   (id, session_id, company_id, title, dataset_ids, spec, result, created_by)
               VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$8)
               RETURNING id, title, dataset_ids, spec, result, created_at""",
            cmp_id, session_id, company_id, body.title, json.dumps(ids),
            _dump_jsonb(body.spec or {}), _dump_jsonb(result), getattr(current_user, "id", None),
        )
        await _audit(conn, session_id, current_user, request, "compare",
                     {"comparison_id": str(cmp_id), "datasets": len(ordered)})
    out = dict(row)
    for k in ("dataset_ids", "spec", "result"):
        out[k] = _parse_jsonb(out.get(k))
    return out


@router.get("/pilot/sessions/{session_id}/comparisons")
async def list_comparisons(session_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        return await _load_comparisons(conn, session_id)


# --------------------------------------------------------------------------- #
# Corpus preview + grounded chat
# --------------------------------------------------------------------------- #

@router.get("/pilot/sessions/{session_id}/metrics")
async def get_metrics(session_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        datasets = await _load_datasets(conn, session_id)
        comparisons = await _load_comparisons(conn, session_id)
    corpus = packs.build_corpus(datasets, comparisons)
    return {
        "sources": {k: {"label": s["label"], "count": len(s["records"])}
                    for k, s in corpus["sources"].items()},
        "notes": corpus["notes"],
        "total": sum(len(s["records"]) for s in corpus["sources"].values()),
    }


@router.post("/pilot/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatIn, request: Request,
               current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        await check_rate_limit(str(company_id), "analysis_pilot_chat", 40, 3600)
        msg_count = await conn.fetchval(
            "SELECT count(*) FROM analysis_pilot_messages WHERE session_id=$1 AND role IN ('user','assistant')",
            session_id)
        if msg_count >= ap._MAX_SESSION_MESSAGES:
            raise HTTPException(
                status_code=400,
                detail="This session has reached its conversation limit. Generate a report to "
                       "capture the analysis, then start a new session.")
        history = await _load_messages(conn, session_id)
        datasets = await _load_datasets(conn, session_id)
        comparisons = await _load_comparisons(conn, session_id)
        corpus = packs.build_corpus(datasets, comparisons)
        # Highlighted records: keep only cids that exist in the corpus (the same
        # trust rule as citations — unknown ids are dropped, not errored).
        focus_records = [corpus["index"][c] for c in (body.focus or []) if c in corpus["index"]]
        await conn.execute(
            "INSERT INTO analysis_pilot_messages (session_id, role, content, metadata) "
            "VALUES ($1,'user',$2,$3)",
            session_id, body.message,
            json.dumps({"focus": [r["cid"] for r in focus_records]}) if focus_records else None)
        await _audit(conn, session_id, current_user, request, "message",
                     {"role": "user", "focus": len(focus_records)})

    async def _persist(payload: dict):
        """Persist the assistant turn on a fresh connection. Wrapped in
        asyncio.shield by the caller so a client disconnect right after the
        result is produced doesn't drop the (already-generated) turn."""
        async with get_connection() as c2:
            await c2.execute(
                "INSERT INTO analysis_pilot_messages (session_id, role, content, metadata) "
                "VALUES ($1,'assistant',$2,$3)",
                session_id, payload.get("assistant_text", ""),
                json.dumps({
                    "analysis_plan": payload.get("analysis_plan"),
                    "evidence_map": payload.get("evidence_map"),
                    "open_questions": payload.get("open_questions"),
                    "dropped_citations": payload.get("dropped_citations"),
                    "proposed_edits": payload.get("proposed_edits"),
                    "dropped_edits": payload.get("dropped_edits"),
                }))
            await c2.execute("UPDATE analysis_pilot_sessions SET updated_at=NOW() WHERE id=$1",
                             session_id)
        # Fire-and-forget: compaction can take ~60s (a Gemini summarization
        # call) and must not delay [DONE] — the client has already rendered
        # the answer and is waiting only to re-enable the composer.
        _spawn_compaction(session_id)

    async def event_stream():
        result_payload = None
        try:
            async for ev in ap.run_chat_turn(session, corpus, history, body.message,
                                             focus_records=focus_records, datasets=datasets,
                                             session_id=str(session_id)):
                if ev.get("type") == "result":
                    result_payload = ev.get("data")
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("analysis_pilot: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis failed.'})}\n\n"
        # Persist after streaming. shield() so a disconnect at this point still
        # commits the completed turn (the Gemini tokens were already spent).
        if result_payload:
            try:
                await asyncio.shield(_persist(result_payload))
            except Exception:
                logger.exception("analysis_pilot: failed to persist assistant message")
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
# Report PDF
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/report")
async def generate_report(session_id: str, body: ReportIn, request: Request,
                          current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        memo = await _latest_memo(conn, session_id)
        if not memo:
            raise HTTPException(status_code=400,
                                detail="Discuss your data in chat first — the report is built from that analysis.")
        datasets = await _load_datasets(conn, session_id)
        comparisons = await _load_comparisons(conn, session_id)
        if body.comparison_id:
            comparisons = [c for c in comparisons if str(c["id"]) == str(body.comparison_id)]
        company_name = await conn.fetchval("SELECT name FROM companies WHERE id=$1", company_id)

        corpus = packs.build_corpus(datasets, comparisons)
        packet = await ap.build_analysis_report(session, corpus, memo, datasets, comparisons,
                                                company_name=company_name)
        base = _safe_name(session.get("title"))
        filename = f"analysis-pilot-{base}.pdf"
        try:
            path = await get_storage().upload_private_file(
                packet["pdf"], filename, prefix="analysis-pilot", content_type="application/pdf")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO analysis_pilot_packets
                   (session_id, company_id, storage_path, filename, citations, file_size, generated_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               RETURNING id, filename, citations, file_size, generated_at""",
            session_id, company_id, path, filename,
            json.dumps(packet["citations"]), len(packet["pdf"]), getattr(current_user, "id", None),
        )
        await _audit(conn, session_id, current_user, request, "generate_report",
                     {"packet_id": str(row["id"]), "citations": len(packet["citations"])})
    return {**dict(row), "citations": _parse_jsonb(row["citations"])}


@router.get("/pilot/sessions/{session_id}/packets/{packet_id}/download")
async def download_packet(session_id: str, packet_id: str, request: Request,
                          current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        pkt = await conn.fetchrow(
            "SELECT storage_path, filename FROM analysis_pilot_packets WHERE id=$1 AND session_id=$2",
            packet_id, session_id)
        if not pkt:
            raise HTTPException(status_code=404, detail="Report not found")
        await _audit(conn, session_id, current_user, request, "export", {"packet_id": packet_id})
    data = await get_storage().download_file(pkt["storage_path"])
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_filename(pkt["filename"])}"'})
