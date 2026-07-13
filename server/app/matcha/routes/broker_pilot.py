"""Broker Pilot routes (`/broker/pilot/*`, Broker Pro).

Grounded per-client analysis chat: the broker opens a session for one client
(on-platform company or off-platform external client), uploads ad-hoc P&C
documents, and converses with an AI grounded in the uploads + the platform
data on file (service: `services/broker_pilot.py`). Exports an analysis-memo
PDF whose citations were validated against the corpus.

Every endpoint is `require_broker_pro`-gated; per-subject ownership is asserted
via the same helpers the other broker routers use. Every session mutation, chat
turn, upload, memo generation, and download lands in `broker_pilot_audit_log`.
"""

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import (APIRouter, Depends, File, HTTPException, Query, Request, Response,
                     UploadFile)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_broker_pro
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.core.services.storage import get_storage
from ..services import broker_pilot as bp
from ..services import broker_pilot_requirements as bpr
from ..services import external_clients as ext
from ..services.er_document_parser import ERDocumentParser
from .broker_portfolio import _assert_broker_owns_company
from .broker_external import _broker_id
from .broker_submission import _tenant_context, _external_context
# Shared ASCII filename hardening (Starlette latin-1-encodes headers; an em dash
# in a title would 500 every download). One implementation, one place to patch.
from .legal_defense import _safe_name, _safe_filename

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_BYTES = 15_000_000
_ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".csv")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class SessionCreate(BaseModel):
    subject_kind: Literal["company", "external"]
    subject_id: UUID
    # Optional: a starter template ("mode") that seeds the title + steers every
    # turn. When title is blank, it's derived from the template (or the client
    # name). Validated against bp.PILOT_TEMPLATES in create_session.
    template_key: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, min_length=1, max_length=300)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    status: Optional[Literal["active", "closed"]] = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5_000)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

async def _audit(conn, session_id, current_user, request: Request, action: str,
                 details: dict | None = None):
    await conn.execute(
        """INSERT INTO broker_pilot_audit_log (session_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        session_id, getattr(current_user, "id", None), action,
        json.dumps(details or {}), client_ip(request),
    )


async def _load_session(conn, session_id: str, broker_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM broker_pilot_sessions WHERE id = $1 AND broker_id = $2",
        session_id, broker_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


async def _assert_subject(conn, user_id, broker_id: UUID, kind: str, subject_id: UUID) -> str:
    """Verify the broker owns the subject; return its display name."""
    if kind == "company":
        meta = await _assert_broker_owns_company(conn, user_id, subject_id)
        return meta["name"]
    client = await ext.get_client(conn, broker_id, subject_id)
    if not client:
        raise HTTPException(status_code=404, detail="External client not found")
    return client["name"]


async def _build_ctx(conn, user_id, session: dict) -> dict:
    """Platform grounding context, dispatched by subject kind. Sections inside
    are already `_safe()`-isolated; a total failure degrades to {} so the chat
    still grounds on the uploaded documents."""
    try:
        if session["subject_kind"] == "company":
            return await _tenant_context(conn, user_id, session["subject_id"])
        return await _external_context(conn, user_id, session["subject_id"])
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - docs-only grounding beats a dead chat
        logger.exception("broker_pilot: context build failed for session %s", session.get("id"))
        return {}


async def _native_for(conn, session: dict) -> dict | None:
    """Platform-generated operational corpus (incidents, ER, compliance,
    discipline, training, policy acks) — company subjects only. None for
    off-platform clients, which makes build_corpus surface the on-platform
    upsell note instead."""
    if session["subject_kind"] != "company":
        return None
    return await bp.gather_native_sources(conn, session["subject_id"])


def _corpus_and_requirements(session: dict, subject_name: str, ctx: dict,
                             docs: list[dict], native: dict | None) -> tuple[dict, list[dict]]:
    """Build the corpus, then the mode's document checklist against it, then fold
    the resulting scope notes back into the corpus.

    The order is forced: requirement satisfaction reads `platform_flags(corpus)`
    (platform data can satisfy a requirement), so the corpus must exist first —
    which is why the notes are appended here rather than passed into
    `build_corpus`. Every caller (context preview, chat, memo) goes through this
    one function, so the checklist the broker sees, the gate the chat enforces,
    and the scope notes the analyst reads can never disagree.
    """
    corpus = bp.build_corpus(subject_name, ctx, docs, native)
    template = bp.get_template(session.get("template_key"))
    reqs = bpr.doc_requirements(template, docs, bpr.platform_flags(corpus))
    corpus["notes"].extend(bpr.scope_notes(template, docs, reqs))
    return corpus, reqs


async def _load_messages(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM broker_pilot_messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return [{**dict(r), "metadata": _parse_jsonb(r["metadata"])} for r in rows]


async def _load_docs(conn, session_id: str, *, with_text: bool = False) -> list[dict]:
    cols = "id, session_id, filename, content_type, file_size, page_count, doc_type, " \
           "status, extraction, error, created_at"
    if with_text:
        cols += ", extracted_text"
    rows = await conn.fetch(
        f"SELECT {cols} FROM broker_pilot_documents WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    # Parse extraction at the load boundary — downstream (corpus build, memo
    # appendix, API payloads) always sees a dict/None, never a raw jsonb string.
    return [{**dict(r), "extraction": _parse_jsonb(r["extraction"])} for r in rows]


async def _latest_memo(conn, session_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT content, metadata FROM broker_pilot_messages "
        "WHERE session_id = $1 AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
        session_id,
    )
    if not row:
        return None
    meta = row["metadata"]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    meta = meta or {}
    return {
        "assistant_text": row["content"] or "",
        "evidence_map": meta.get("evidence_map") or [],
        # `open_questions` is the pre-structured-answer key — a memo generated
        # over an older transcript still renders its questions.
        "key_questions": meta.get("key_questions") or meta.get("open_questions") or [],
        "considerations": meta.get("considerations") or [],
        "gaps": meta.get("gaps") or [],
    }


def _parse_jsonb(v):
    """The asyncpg pool registers no jsonb codec — jsonb columns come back as
    raw JSON strings. Parse before returning to the frontend."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def _doc_out(d: dict) -> dict:
    """Document row for API payloads (extraction parsed, no raw text)."""
    out = {k: v for k, v in d.items() if k != "extracted_text"}
    out["extraction"] = _parse_jsonb(out.get("extraction"))
    return out


async def _read_upload(file: UploadFile) -> tuple[bytes, str, bool]:
    """Validate + read an upload. Returns (bytes, filename, is_pdf)."""
    filename = file.filename or "document"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type — allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (15 MB max)")
    return data, filename, ext == ".pdf"


# --------------------------------------------------------------------------- #
# Starter templates ("modes") + Sessions
# --------------------------------------------------------------------------- #

@router.get("/pilot/templates")
async def list_templates(current_user=Depends(require_broker_pro)):
    """Static catalog of starter modes for the new-session picker. Public
    fields only (the per-mode system-prompt `focus` stays server-side)."""
    return bp.template_catalog()


@router.post("/pilot/sessions")
async def create_session(body: SessionCreate, request: Request,
                         current_user=Depends(require_broker_pro)):
    # An unselected picker naturally serializes template_key as "" — normalize
    # blank to None (open analysis); only a genuinely unknown key is a 400.
    template_key = (body.template_key or "").strip() or None
    tmpl = bp.get_template(template_key)
    if template_key is not None and tmpl is None:
        raise HTTPException(status_code=400, detail="Unknown template")
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        subject_name = await _assert_subject(conn, current_user.id, broker_id,
                                             body.subject_kind, body.subject_id)
        # Derive the title when blank: the mode's title scoped to the client,
        # else the generic "<client> — analysis".
        title = (body.title or "").strip()
        if not title:
            title = (f"{tmpl['title']} — {subject_name}" if tmpl
                     else f"{subject_name} — analysis")[:300]
        row = await conn.fetchrow(
            """INSERT INTO broker_pilot_sessions
                   (broker_id, subject_kind, subject_id, title, template_key, created_by)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            broker_id, body.subject_kind, body.subject_id, title, template_key,
            getattr(current_user, "id", None),
        )
        await _audit(conn, row["id"], current_user, request, "create",
                     {"title": title, "subject_kind": body.subject_kind,
                      "template_key": template_key})
    return {**dict(row), "subject_name": subject_name, "template": tmpl}


@router.get("/pilot/sessions")
async def list_sessions(subject_kind: Optional[str] = None, subject_id: Optional[UUID] = None,
                        current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        rows = await conn.fetch(
            """
            SELECT s.*,
                   CASE WHEN s.subject_kind = 'company' THEN c.name ELSE e.name END AS subject_name,
                   (SELECT COUNT(*) FROM broker_pilot_messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT COUNT(*) FROM broker_pilot_documents d WHERE d.session_id = s.id) AS document_count,
                   (SELECT COUNT(*) FROM broker_pilot_packets p WHERE p.session_id = s.id) AS packet_count
            FROM broker_pilot_sessions s
            LEFT JOIN companies c ON s.subject_kind = 'company' AND c.id = s.subject_id
            LEFT JOIN broker_external_clients e ON s.subject_kind = 'external' AND e.id = s.subject_id
            WHERE s.broker_id = $1
              AND ($2::varchar IS NULL OR s.subject_kind = $2)
              AND ($3::uuid IS NULL OR s.subject_id = $3)
            ORDER BY s.updated_at DESC
            """,
            broker_id, subject_kind, subject_id,
        )
    return [dict(r) for r in rows]


@router.get("/pilot/sessions/{session_id}")
async def get_session(session_id: str, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        session = await _load_session(conn, session_id, broker_id)
        subject_name = await _assert_subject(conn, current_user.id, broker_id,
                                             session["subject_kind"], session["subject_id"])
        session["subject_name"] = subject_name
        # Mode metadata so the console renders the session's tailored starters
        # without a second fetch (None for legacy / open-analysis sessions).
        session["template"] = bp.get_template(session.get("template_key"))
        session["messages"] = await _load_messages(conn, session_id)
        session["documents"] = [_doc_out(d) for d in await _load_docs(conn, session_id)]
        packets = await conn.fetch(
            "SELECT id, filename, citations, file_size, generated_at "
            "FROM broker_pilot_packets WHERE session_id = $1 ORDER BY generated_at DESC",
            session_id,
        )
        session["packets"] = [
            {**dict(p), "citations": _parse_jsonb(p["citations"])} for p in packets
        ]
    return session


@router.patch("/pilot/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdate, request: Request,
                         current_user=Depends(require_broker_pro)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        sets, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=1):
            sets.append(f"{k} = ${i}")
            vals.append(v)
        vals.extend([session_id, broker_id])
        closed = ", closed_at = NOW()" if fields.get("status") == "closed" else ""
        row = await conn.fetchrow(
            f"UPDATE broker_pilot_sessions SET {', '.join(sets)}, updated_at = NOW(){closed} "
            f"WHERE id = ${len(vals) - 1} AND broker_id = ${len(vals)} RETURNING *",
            *vals,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        await _audit(conn, session_id, current_user, request, "update",
                     {"fields": list(fields.keys())})
    # Carry the resolved mode so a caller that adopts this PATCH response as the
    # session state can't silently drop the mode (get_session attaches it too).
    return {**dict(row), "template": bp.get_template(row.get("template_key"))}


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/documents")
async def upload_document(session_id: str, request: Request, file: UploadFile = File(...),
                          current_user=Depends(require_broker_pro)):
    data, filename, is_pdf = await _read_upload(file)

    # Pre-work in one connection: ownership, cap, local text extraction, S3
    # store, row insert. Released before the (≤90s) Gemini extraction call.
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        session = await _load_session(conn, session_id, broker_id)
        await check_rate_limit(str(broker_id), "broker_pilot_doc", 20, 3600)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM broker_pilot_documents WHERE session_id = $1", session_id
        )
        if int(count or 0) >= bp._MAX_DOCS_PER_SESSION:
            raise HTTPException(status_code=400,
                                detail=f"Session document limit reached ({bp._MAX_DOCS_PER_SESSION})")

        text, page_count = "", None
        try:
            text, page_count = await asyncio.to_thread(
                ERDocumentParser().extract_text_from_bytes, data, filename
            )
        except Exception:  # noqa: BLE001 - PDFs still get the Gemini multimodal pass
            logger.warning("broker_pilot: local text extraction failed for %s", filename)
        text = (text or "")[:bp._STORED_TEXT_CAP]

        try:
            storage_path = await get_storage().upload_private_file(
                data, filename, prefix=f"broker-pilot/{session_id}",
                content_type=file.content_type,
            )
        except RuntimeError as exc:  # private bucket unconfigured — 503, not 500
            raise HTTPException(status_code=503, detail="Document storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO broker_pilot_documents
                   (session_id, broker_id, filename, storage_path, content_type,
                    file_size, page_count, extracted_text, uploaded_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
            session_id, broker_id, filename, storage_path, file.content_type,
            len(data), page_count, text, getattr(current_user, "id", None),
        )
        doc_id = row["id"]
        await _audit(conn, session_id, current_user, request, "upload_document",
                     {"document_id": str(doc_id), "filename": filename, "size": len(data)})

    # Gemini classify+extract (never raises). Non-PDFs go text-only to the model.
    result = await bp.extract_document(data if is_pdf else None, text,
                                       is_pdf=is_pdf, filename=filename)
    extraction = result["extraction"]
    if result["available"]:
        status = "ready"
    elif text.strip():
        status = "text_only"
    else:
        status = "failed"

    async with get_connection() as conn:
        updated = await conn.fetchrow(
            """UPDATE broker_pilot_documents
               SET status = $2, doc_type = $3, extraction = $4::jsonb,
                   error = $5
               WHERE id = $1
               RETURNING id, session_id, filename, content_type, file_size, page_count,
                         doc_type, status, extraction, error, created_at""",
            doc_id, status,
            extraction.get("doc_type") if result["available"] else None,
            json.dumps(extraction) if result["available"] else None,
            None if status != "failed" else "Could not extract text or analyze the document",
        )
        await conn.execute(
            "UPDATE broker_pilot_sessions SET updated_at = NOW() WHERE id = $1", session_id
        )
    return _doc_out(dict(updated))


@router.get("/pilot/sessions/{session_id}/documents")
async def list_documents(session_id: str, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _load_session(conn, session_id, broker_id)
        docs = await _load_docs(conn, session_id)
    return [_doc_out(d) for d in docs]


@router.delete("/pilot/sessions/{session_id}/documents/{doc_id}")
async def delete_document(session_id: str, doc_id: str, request: Request,
                          current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _load_session(conn, session_id, broker_id)
        row = await conn.fetchrow(
            "DELETE FROM broker_pilot_documents WHERE id = $1 AND session_id = $2 "
            "RETURNING storage_path, filename",
            doc_id, session_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        await _audit(conn, session_id, current_user, request, "delete_document",
                     {"document_id": doc_id, "filename": row["filename"]})
    try:
        await get_storage().delete_private_file(row["storage_path"])
    except Exception:  # noqa: BLE001 - best-effort; the row is gone either way
        logger.warning("broker_pilot: could not delete stored file %s", row["storage_path"])
    return {"deleted": True}


@router.get("/pilot/sessions/{session_id}/documents/{doc_id}/download")
async def download_document(session_id: str, doc_id: str, request: Request,
                            current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _load_session(conn, session_id, broker_id)
        row = await conn.fetchrow(
            "SELECT storage_path, filename FROM broker_pilot_documents "
            "WHERE id = $1 AND session_id = $2",
            doc_id, session_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        await _audit(conn, session_id, current_user, request, "download_document",
                     {"document_id": doc_id})
    # NB: sync method (unlike the other storage calls) — boto3 presign is local.
    url = get_storage().get_presigned_download_url(row["storage_path"], expires_in=900)
    if not url:
        raise HTTPException(status_code=503, detail="Document storage unavailable")
    return {"url": url, "filename": row["filename"]}


# --------------------------------------------------------------------------- #
# Context preview + grounded chat
# --------------------------------------------------------------------------- #

@router.get("/pilot/sessions/{session_id}/context")
async def get_context(session_id: str, current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        session = await _load_session(conn, session_id, broker_id)
        subject_name = await _assert_subject(conn, current_user.id, broker_id,
                                             session["subject_kind"], session["subject_id"])
        ctx = await _build_ctx(conn, current_user.id, session)
        docs = await _load_docs(conn, session_id)
        native = await _native_for(conn, session)
    corpus, reqs = _corpus_and_requirements(session, subject_name, ctx, docs, native)
    # Source summaries + counts only — the flat index is internal. The document
    # checklist rides here (not on GET /sessions/{id}) because satisfaction needs
    # the corpus this endpoint already pays to build; the frontend loads session
    # and context in parallel, so it has both at first paint.
    return {
        "sources": corpus["sources"],
        "notes": corpus["notes"],
        "total": sum(len(s["records"]) for s in corpus["sources"].values()),
        "doc_requirements": reqs,
    }


@router.post("/pilot/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatIn, request: Request,
               force: bool = Query(False,
                                   description="Answer even though the mode's required documents "
                                               "are missing ('Ask anyway')"),
               current_user=Depends(require_broker_pro)):
    # Pre-work in one connection; release it before the long Gemini call.
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        session = await _load_session(conn, session_id, broker_id)
        await check_rate_limit(str(broker_id), "broker_pilot_chat", 30, 3600)
        subject_name = await _assert_subject(conn, current_user.id, broker_id,
                                             session["subject_kind"], session["subject_id"])
        history = await _load_messages(conn, session_id)
        ctx = await _build_ctx(conn, current_user.id, session)
        docs = await _load_docs(conn, session_id, with_text=True)
        native = await _native_for(conn, session)

        corpus, reqs = _corpus_and_requirements(session, subject_name, ctx, docs, native)

        # The mode's document gate — soft, and it runs BEFORE the message is
        # persisted so a refused turn leaves no orphan in the transcript. Forceable
        # because a broker legitimately asks exploratory questions before the paper
        # lands, and because doc_type is AI-assigned (a misclassified upload must
        # never trap someone).
        missing = bpr.missing_required(reqs)
        if missing and not force:
            raise HTTPException(status_code=409, detail=bpr.missing_docs_detail(missing))

        await conn.execute(
            "INSERT INTO broker_pilot_messages (session_id, role, content) VALUES ($1, 'user', $2)",
            session_id, body.message,
        )
        await _audit(conn, session_id, current_user, request, "message",
                     {"role": "user",
                      **({"forced_missing": [m["doc_type"] for m in missing]} if missing else {})})

    async def event_stream():
        result_payload = None
        try:
            async for ev in bp.run_chat_turn(session, subject_name, history, corpus,
                                             docs, body.message):
                if ev.get("type") == "result":
                    result_payload = ev.get("data")
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("broker_pilot: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis failed.'})}\n\n"
        # Persist the assistant turn (+ the validated, structured buckets) after
        # streaming. Everything stored here has already been through the citation
        # gate in run_chat_turn.
        if result_payload:
            try:
                async with get_connection() as c2:
                    await c2.execute(
                        "INSERT INTO broker_pilot_messages (session_id, role, content, metadata) "
                        "VALUES ($1, 'assistant', $2, $3)",
                        session_id, result_payload.get("assistant_text", ""),
                        json.dumps({
                            "evidence_map": result_payload.get("evidence_map"),
                            "key_questions": result_payload.get("key_questions"),
                            "considerations": result_payload.get("considerations"),
                            "gaps": result_payload.get("gaps"),
                            "dropped_citations": result_payload.get("dropped_citations"),
                        }),
                    )
                    await c2.execute(
                        "UPDATE broker_pilot_sessions SET updated_at = NOW() WHERE id = $1",
                        session_id,
                    )
            except Exception:
                logger.exception("broker_pilot: failed to persist assistant message")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


# --------------------------------------------------------------------------- #
# Memo PDF
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/memo")
async def generate_memo(session_id: str, request: Request,
                        current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        session = await _load_session(conn, session_id, broker_id)
        memo = await _latest_memo(conn, session_id)
        if not memo:
            raise HTTPException(status_code=400,
                                detail="Discuss the client in chat first — the memo is built from that analysis.")
        subject_name = await _assert_subject(conn, current_user.id, broker_id,
                                             session["subject_kind"], session["subject_id"])
        ctx = await _build_ctx(conn, current_user.id, session)
        docs = await _load_docs(conn, session_id)
        native = await _native_for(conn, session)
        broker_name = await conn.fetchval("SELECT name FROM brokers WHERE id = $1", broker_id)

        # Memo generation is NOT gated on the mode's documents — a memo of a
        # forced analysis is legitimate. It carries the scope note instead, so
        # the reader sees what the analysis did not have.
        corpus, _reqs = _corpus_and_requirements(session, subject_name, ctx, docs, native)
        packet = await bp.build_memo_pdf(session, subject_name, corpus, memo, docs,
                                         broker_name=broker_name)

        base = _safe_name(session.get("title"))
        filename = f"broker-pilot-{base}.pdf"
        try:
            path = await get_storage().upload_private_file(
                packet["pdf"], filename, prefix="broker-pilot", content_type="application/pdf"
            )
        except RuntimeError as exc:  # private bucket unconfigured — 503, not 500
            raise HTTPException(status_code=503, detail="Document storage unavailable") from exc
        row = await conn.fetchrow(
            """INSERT INTO broker_pilot_packets
                   (session_id, broker_id, storage_path, filename, citations, file_size, generated_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               RETURNING id, filename, citations, file_size, generated_at""",
            session_id, broker_id, path, filename,
            json.dumps(packet["citations"]), len(packet["pdf"]),
            getattr(current_user, "id", None),
        )
        await _audit(conn, session_id, current_user, request, "generate_memo",
                     {"packet_id": str(row["id"]), "citations": len(packet["citations"])})
    return {**dict(row), "citations": _parse_jsonb(row["citations"])}


@router.get("/pilot/sessions/{session_id}/packets/{packet_id}/download")
async def download_packet(session_id: str, packet_id: str, request: Request,
                          current_user=Depends(require_broker_pro)):
    async with get_connection() as conn:
        broker_id = await _broker_id(conn, current_user.id)
        await _load_session(conn, session_id, broker_id)
        pkt = await conn.fetchrow(
            "SELECT storage_path, filename FROM broker_pilot_packets "
            "WHERE id = $1 AND session_id = $2",
            packet_id, session_id,
        )
        if not pkt:
            raise HTTPException(status_code=404, detail="Packet not found")
        await _audit(conn, session_id, current_user, request, "export",
                     {"packet_id": packet_id})
    data = await get_storage().download_file(pkt["storage_path"])
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(pkt["filename"])}"'},
    )
