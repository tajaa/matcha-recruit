"""Risk Pilot routes (`/risk-pilot/pilot/*`) — company-scoped, gated at mount by
`require_feature("risk_pilot")`.

Bring-your-own-data risk analysis: the company opens a session, uploads datasets
(CSV / XLSX / financial-document PDF), a DETERMINISTIC engine computes the risk
metrics (`services/risk_analyzers`), and a GROUNDED AI narrates over the computed
numbers and exports an analyst report. Documents go through a Gemini extraction
the user CONFIRMS before analysis. Every mutation/generation/download is
audit-logged. Tenant isolation on every route via `get_client_company_id`.
"""

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.core.services.storage import get_storage
from ..services import risk_pilot as rp
from ..services import risk_analyzers as RA
from ..services.er_document_parser import ERDocumentParser
from ..models.risk_pilot import (
    SessionCreate, SessionUpdate, DatasetPatch, ComparisonCreate, ChatIn, ReportIn,
)
# Shared ASCII filename hardening (Starlette latin-1-encodes headers).
from .legal_defense import _safe_name, _safe_filename

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_BYTES = 25_000_000
_MAX_DATASETS_PER_SESSION = 20
_EXT_TO_KIND = {".csv": "csv", ".xlsx": "xlsx", ".pdf": "pdf"}


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


async def _audit(conn, session_id, current_user, request: Request, action: str,
                 details: dict | None = None):
    await conn.execute(
        """INSERT INTO risk_pilot_audit_log (session_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        session_id, getattr(current_user, "id", None), action,
        json.dumps(details or {}), client_ip(request),
    )


async def _load_session(conn, session_id: str, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM risk_pilot_sessions WHERE id = $1 AND company_id = $2",
        session_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


async def _load_messages(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM risk_pilot_messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return [{**dict(r), "metadata": _parse_jsonb(r["metadata"])} for r in rows]


async def _load_datasets(conn, session_id: str, *, full: bool = True) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM risk_pilot_datasets WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("extraction", "normalized", "mapping", "metrics", "config"):
            d[k] = _parse_jsonb(d.get(k))
        out.append(d)
    return out


async def _load_comparisons(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, title, dataset_ids, spec, result, created_at FROM risk_pilot_comparisons "
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
        "SELECT content, metadata FROM risk_pilot_messages "
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
    """API payload for a dataset — parsed jsonb, but the heavy series values are
    stripped from `normalized` (the mapping UI only needs names/roles/periods)."""
    norm = _parse_jsonb(d.get("normalized")) or {}
    columns = list((norm.get("series") or {}).keys())
    slim_norm = {
        "roles": norm.get("roles") or {},
        "kind": norm.get("kind"),
        "periods": norm.get("periods"),
        "columns": columns,
        "meta": norm.get("meta") or {},
    }
    return {
        "id": str(d.get("id")),
        "filename": d.get("filename"),
        "source_kind": d.get("source_kind"),
        "status": d.get("status"),
        "row_count": d.get("row_count"),
        "column_count": d.get("column_count"),
        "error": d.get("error"),
        "created_at": d.get("created_at"),
        "extraction": _parse_jsonb(d.get("extraction")),
        "config": _parse_jsonb(d.get("config")) or {},
        "mapping": _parse_jsonb(d.get("mapping")) or {},
        "normalized": slim_norm,
        "metrics": _parse_jsonb(d.get("metrics")) or {},
    }


def _analyze(ds_id, source_kind: str, filename: str, *, parsed=None, prev_normalized=None,
             extraction=None, mapping=None, config=None, kind=None) -> tuple[dict, dict]:
    """Pure deterministic (re)analysis: build the normalized model and run every
    applicable analyzer pack. No DB, no Gemini."""
    if extraction is not None:
        parsed = RA.parsed_from_extraction(extraction)
    elif parsed is None and prev_normalized is not None:
        meta = prev_normalized.get("meta") or {}
        parsed = {
            "series": prev_normalized.get("series") or {},
            "periods": prev_normalized.get("periods"),
            "truncated": bool(meta.get("truncated")),
            "warnings": list(meta.get("warnings") or []),
            "provenance": meta.get("provenance"),
        }
    normalized = RA.normalize(parsed or {"series": {}}, source_kind=source_kind,
                              filename=filename, roles_override=mapping, kind_override=kind)
    metrics = RA.run_analyzers(normalized, config or {}, str(ds_id))
    return normalized, metrics


def _shape_counts(normalized: dict) -> tuple[int, int]:
    series = normalized.get("series") or {}
    periods = normalized.get("periods") or []
    row_count = len(periods) or (max((len(v) for v in series.values()), default=0))
    return row_count, len(series)


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


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions")
async def create_session(body: SessionCreate, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO risk_pilot_sessions (company_id, title, domain, goal, created_by)
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
                   (SELECT COUNT(*) FROM risk_pilot_messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT COUNT(*) FROM risk_pilot_datasets d WHERE d.session_id = s.id) AS dataset_count,
                   (SELECT COUNT(*) FROM risk_pilot_packets p WHERE p.session_id = s.id) AS packet_count
               FROM risk_pilot_sessions s
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
        session["datasets"] = [_dataset_out(d) for d in await _load_datasets(conn, session_id)]
        session["comparisons"] = await _load_comparisons(conn, session_id)
        packets = await conn.fetch(
            "SELECT id, filename, scope, citations, file_size, generated_at "
            "FROM risk_pilot_packets WHERE session_id = $1 ORDER BY generated_at DESC",
            session_id,
        )
        session["packets"] = [{**dict(p), "citations": _parse_jsonb(p["citations"])} for p in packets]
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
            f"UPDATE risk_pilot_sessions SET {', '.join(sets)}, updated_at = NOW(){closed} "
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
        await check_rate_limit(str(company_id), "risk_pilot_upload", 40, 3600)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM risk_pilot_datasets WHERE session_id = $1", session_id)
        if int(count or 0) >= _MAX_DATASETS_PER_SESSION:
            raise HTTPException(status_code=400,
                                detail=f"Session dataset limit reached ({_MAX_DATASETS_PER_SESSION})")
        text = ""
        if source_kind == "pdf":
            try:
                text, _pages = await asyncio.to_thread(
                    ERDocumentParser().extract_text_from_bytes, data, filename)
            except Exception:  # noqa: BLE001
                logger.warning("risk_pilot: local text extraction failed for %s", filename)
        try:
            storage_path = await get_storage().upload_private_file(
                data, filename, prefix=f"risk-pilot/{session_id}", content_type=file.content_type)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO risk_pilot_datasets
                   (session_id, company_id, filename, storage_path, source_kind,
                    content_type, file_size, uploaded_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            session_id, company_id, filename, storage_path, source_kind,
            file.content_type, len(data), getattr(current_user, "id", None),
        )
        ds_id = row["id"]
        await _audit(conn, session_id, current_user, request, "upload",
                     {"dataset_id": str(ds_id), "filename": filename, "source_kind": source_kind})

    # Analysis (connection released). Tabular is pure/fast; PDF calls Gemini.
    status, error, extraction, normalized, metrics = "ready", None, None, {}, {}
    try:
        if source_kind == "pdf":
            result = await rp.extract_dataset(data, text, is_pdf=True, filename=filename)
            extraction = result["extraction"]
            if not result["available"]:
                status, error = "failed", "No numeric data could be extracted from the document."
            else:
                normalized, metrics = _analyze(ds_id, source_kind, filename, extraction=extraction)
                status = "needs_review"  # user confirms extracted figures before trusting metrics
        else:
            parsed = RA.parse_tabular(data, source_kind)
            normalized, metrics = _analyze(ds_id, source_kind, filename, parsed=parsed)
            if not (normalized.get("series")):
                status, error = "failed", "No numeric columns detected."
    except Exception as exc:  # noqa: BLE001 - degrade, never 500 the upload
        logger.exception("risk_pilot: analysis failed for %s", filename)
        status, error = "failed", "Could not analyze the file."

    row_count, column_count = _shape_counts(normalized)
    async with get_connection() as conn:
        updated = await conn.fetchrow(
            """UPDATE risk_pilot_datasets
               SET status=$2, error=$3, extraction=$4::jsonb, normalized=$5::jsonb,
                   metrics=$6::jsonb, row_count=$7, column_count=$8
               WHERE id=$1 RETURNING *""",
            ds_id, status, error,
            json.dumps(extraction) if extraction else None,
            json.dumps(normalized) if normalized else None,
            json.dumps(metrics) if metrics else None,
            row_count, column_count,
        )
        await conn.execute("UPDATE risk_pilot_sessions SET updated_at=NOW() WHERE id=$1", session_id)
    return _dataset_out(dict(updated))


@router.get("/pilot/sessions/{session_id}/datasets")
async def list_datasets(session_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        datasets = await _load_datasets(conn, session_id)
    return [_dataset_out(d) for d in datasets]


@router.patch("/pilot/sessions/{session_id}/datasets/{dataset_id}")
async def patch_dataset(session_id: str, dataset_id: str, body: DatasetPatch, request: Request,
                        current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        row = await conn.fetchrow(
            "SELECT * FROM risk_pilot_datasets WHERE id=$1 AND session_id=$2", dataset_id, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        d = dict(row)
        prev_norm = _parse_jsonb(d.get("normalized")) or {}
        prev_mapping = _parse_jsonb(d.get("mapping")) or {}
        prev_config = _parse_jsonb(d.get("config")) or {}
        prev_extraction = _parse_jsonb(d.get("extraction"))

    # Merge overrides.
    mapping = {**prev_mapping, **(body.mapping or {})}
    config = dict(prev_config)
    if body.column_kinds is not None:
        config["column_kinds"] = {**(config.get("column_kinds") or {}), **body.column_kinds}
    if body.periods_per_year is not None:
        config["periods_per_year"] = body.periods_per_year
    if body.risk_free is not None:
        config["risk_free"] = body.risk_free
    extraction = body.extraction if body.extraction is not None else prev_extraction

    try:
        if d["source_kind"] == "pdf" and extraction is not None:
            coerced = rp._coerce_extraction(extraction)
            normalized, metrics = _analyze(dataset_id, d["source_kind"], d["filename"],
                                           extraction=coerced, mapping=mapping, config=config,
                                           kind=body.kind)
            extraction = coerced
        else:
            normalized, metrics = _analyze(dataset_id, d["source_kind"], d["filename"],
                                           prev_normalized=prev_norm, mapping=mapping,
                                           config=config, kind=body.kind)
    except Exception:  # noqa: BLE001
        logger.exception("risk_pilot: recompute failed for %s", dataset_id)
        raise HTTPException(status_code=400, detail="Could not recompute with those settings.")

    row_count, column_count = _shape_counts(normalized)
    status = "ready"  # a confirmed/recomputed dataset is trusted
    async with get_connection() as conn:
        updated = await conn.fetchrow(
            """UPDATE risk_pilot_datasets
               SET status=$2, mapping=$3::jsonb, config=$4::jsonb, extraction=$5::jsonb,
                   normalized=$6::jsonb, metrics=$7::jsonb, row_count=$8, column_count=$9, error=NULL
               WHERE id=$1 RETURNING *""",
            dataset_id, status, json.dumps(mapping), json.dumps(config),
            json.dumps(extraction) if extraction else None,
            json.dumps(normalized), json.dumps(metrics), row_count, column_count,
        )
        await _audit(conn, session_id, current_user, request, "confirm_mapping",
                     {"dataset_id": dataset_id})
        await conn.execute("UPDATE risk_pilot_sessions SET updated_at=NOW() WHERE id=$1", session_id)
    return _dataset_out(dict(updated))


@router.delete("/pilot/sessions/{session_id}/datasets/{dataset_id}")
async def delete_dataset(session_id: str, dataset_id: str, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        row = await conn.fetchrow(
            "DELETE FROM risk_pilot_datasets WHERE id=$1 AND session_id=$2 RETURNING storage_path",
            dataset_id, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        await _audit(conn, session_id, current_user, request, "delete_dataset", {"dataset_id": dataset_id})
    try:
        await get_storage().delete_private_file(row["storage_path"])
    except Exception:  # noqa: BLE001
        logger.warning("risk_pilot: could not delete stored file %s", row["storage_path"])
    return {"deleted": True}


@router.get("/pilot/sessions/{session_id}/datasets/{dataset_id}/download")
async def download_dataset(session_id: str, dataset_id: str,
                           current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        row = await conn.fetchrow(
            "SELECT storage_path, filename FROM risk_pilot_datasets WHERE id=$1 AND session_id=$2",
            dataset_id, session_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
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
            "SELECT * FROM risk_pilot_datasets WHERE session_id=$1 AND id = ANY($2::uuid[])",
            session_id, ids)
        by_id = {str(r["id"]): dict(r) for r in rows}
        # Preserve the caller's order (the comparison axis).
        ordered = [by_id[i] for i in ids if i in by_id]
        if len(ordered) < 2:
            raise HTTPException(status_code=400, detail="Select at least two datasets in this session.")
        payload = [{"id": str(d["id"]), "label": d["filename"],
                    "metrics": _parse_jsonb(d.get("metrics")) or {}} for d in ordered]
        result = RA.build_comparison(session_id, payload, body.spec)
        row = await conn.fetchrow(
            """INSERT INTO risk_pilot_comparisons (session_id, company_id, title, dataset_ids, spec, result, created_by)
               VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7)
               RETURNING id, title, dataset_ids, spec, result, created_at""",
            session_id, company_id, body.title, json.dumps(ids),
            json.dumps(body.spec or {}), json.dumps(result), getattr(current_user, "id", None),
        )
        # Give the comparison its own id in the result cids so citations resolve.
        result = RA.build_comparison(str(row["id"]), payload, body.spec)
        await conn.execute("UPDATE risk_pilot_comparisons SET result=$2::jsonb WHERE id=$1",
                           row["id"], json.dumps(result))
        await _audit(conn, session_id, current_user, request, "compare",
                     {"comparison_id": str(row["id"]), "datasets": len(ordered)})
    out = dict(row)
    out["result"] = result
    out["dataset_ids"] = ids
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
    corpus = RA.build_corpus(datasets, comparisons)
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
        await check_rate_limit(str(company_id), "risk_pilot_chat", 40, 3600)
        history = await _load_messages(conn, session_id)
        datasets = await _load_datasets(conn, session_id)
        comparisons = await _load_comparisons(conn, session_id)
        await conn.execute(
            "INSERT INTO risk_pilot_messages (session_id, role, content) VALUES ($1,'user',$2)",
            session_id, body.message)
        await _audit(conn, session_id, current_user, request, "message", {"role": "user"})

    corpus = RA.build_corpus(datasets, comparisons)

    async def event_stream():
        result_payload = None
        try:
            async for ev in rp.run_chat_turn(session, corpus, history, body.message):
                if ev.get("type") == "result":
                    result_payload = ev.get("data")
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("risk_pilot: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis failed.'})}\n\n"
        if result_payload:
            try:
                async with get_connection() as c2:
                    await c2.execute(
                        "INSERT INTO risk_pilot_messages (session_id, role, content, metadata) "
                        "VALUES ($1,'assistant',$2,$3)",
                        session_id, result_payload.get("assistant_text", ""),
                        json.dumps({
                            "evidence_map": result_payload.get("evidence_map"),
                            "open_questions": result_payload.get("open_questions"),
                            "dropped_citations": result_payload.get("dropped_citations"),
                        }))
                    await c2.execute("UPDATE risk_pilot_sessions SET updated_at=NOW() WHERE id=$1",
                                     session_id)
            except Exception:
                logger.exception("risk_pilot: failed to persist assistant message")
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
        if body.scope == "comparison" and body.comparison_id:
            comparisons = [c for c in comparisons if str(c["id"]) == str(body.comparison_id)]
        company_name = await conn.fetchval("SELECT name FROM companies WHERE id=$1", company_id)

        corpus = RA.build_corpus(datasets, comparisons)
        packet = await rp.build_risk_report(session, corpus, memo, datasets, comparisons,
                                            company_name=company_name)
        base = _safe_name(session.get("title"))
        filename = f"risk-pilot-{base}.pdf"
        try:
            path = await get_storage().upload_private_file(
                packet["pdf"], filename, prefix="risk-pilot", content_type="application/pdf")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO risk_pilot_packets
                   (session_id, company_id, scope, storage_path, filename, citations, file_size, generated_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               RETURNING id, filename, scope, citations, file_size, generated_at""",
            session_id, company_id, body.scope, path, filename,
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
            "SELECT storage_path, filename FROM risk_pilot_packets WHERE id=$1 AND session_id=$2",
            packet_id, session_id)
        if not pkt:
            raise HTTPException(status_code=404, detail="Report not found")
        await _audit(conn, session_id, current_user, request, "export", {"packet_id": packet_id})
    data = await get_storage().download_file(pkt["storage_path"])
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_filename(pkt["filename"])}"'})
