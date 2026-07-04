"""Legal Pilot routes (`/legal-pilot`, feature `legal_defense`).

Litigation-readiness evidence assembly for full-platform (Pro) companies. An
admin opens a legal matter, converses with a grounded AI that organizes the
company's own records (service: `services/legal_defense.py`), and exports an
attorney-facing packet (memo PDF + ZIP bundle). Business-facing, tenant-isolated.
A token-gated public route delivers a generated packet to outside counsel.

The AI is an organizer, not an advocate (see the service). Every matter mutation,
chat turn, packet generation, download, and share is written to
`legal_matter_audit_log` (legal-grade trail).
"""

import json
import logging
import secrets
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from app.core.feature_flags import merge_company_features
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.core.services.storage import get_storage
from ..services import legal_defense as ld
from ..services import legal_research

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

_MATTER_TYPES = ("subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class _JurisdictionStateMixin(BaseModel):
    # check_fields=False: the field lives on the concrete models below, not
    # on this mixin — without it Pydantic v2 rejects the class at definition.
    @field_validator("jurisdiction_state", check_fields=False)
    @classmethod
    def _upper_state(cls, v):
        return v.upper() if v else v


class MatterCreate(_JurisdictionStateMixin):
    title: str = Field(..., min_length=1, max_length=300)
    matter_type: Literal["subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other"] = "other"
    allegation: Optional[str] = Field(None, max_length=20_000)
    defense_theory: Optional[str] = Field(None, max_length=20_000)
    evidence_start: Optional[date] = None
    evidence_end: Optional[date] = None
    counsel_directed: bool = False
    counsel_name: Optional[str] = Field(None, max_length=200)
    counsel_email: Optional[str] = Field(None, max_length=320)
    location_id: Optional[UUID] = None
    jurisdiction_state: Optional[str] = Field(None, min_length=2, max_length=2)


class MatterUpdate(_JurisdictionStateMixin):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    allegation: Optional[str] = Field(None, max_length=20_000)
    defense_theory: Optional[str] = Field(None, max_length=20_000)
    evidence_start: Optional[date] = None
    evidence_end: Optional[date] = None
    status: Optional[Literal["draft", "active", "closed"]] = None
    counsel_directed: Optional[bool] = None
    counsel_name: Optional[str] = Field(None, max_length=200)
    counsel_email: Optional[str] = Field(None, max_length=320)
    location_id: Optional[UUID] = None
    jurisdiction_state: Optional[str] = Field(None, min_length=2, max_length=2)


class ResearchOptions(BaseModel):
    # False skips the ~90s grounded-Gemini synthesis call — just the
    # CourtListener case search, for a fast case-law-only refresh.
    include_guidance: bool = True


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5_000)


class PacketIn(BaseModel):
    kind: Literal["pdf", "zip", "both"] = "both"
    include_research: bool = False


class ShareIn(BaseModel):
    recipient_email: Optional[str] = Field(None, max_length=320)
    expires_days: int = Field(14, ge=1, le=365)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

async def _audit(conn, matter_id, current_user, request: Request, action: str, details: dict | None = None):
    await conn.execute(
        """INSERT INTO legal_matter_audit_log (matter_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        matter_id, getattr(current_user, "id", None), action,
        json.dumps(details or {}), client_ip(request),
    )


async def _load_matter(conn, matter_id: str, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM legal_matters WHERE id = $1 AND company_id = $2",
        matter_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Matter not found")
    return dict(row)


async def _check_location(conn, location_id, company_id) -> None:
    row = await conn.fetchrow(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=400, detail="Location not found")


async def _features(conn, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
    )
    if not row:
        return {}
    return merge_company_features(row["enabled_features"], row["signup_source"])


async def _load_messages(conn, matter_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM legal_matter_messages "
        "WHERE matter_id = $1 ORDER BY created_at",
        matter_id,
    )
    return [dict(r) for r in rows]


async def _latest_memo(conn, matter_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT content, metadata FROM legal_matter_messages "
        "WHERE matter_id = $1 AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
        matter_id,
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
        "open_questions": meta.get("open_questions") or [],
    }


# --------------------------------------------------------------------------- #
# Matters CRUD
# --------------------------------------------------------------------------- #

@router.post("/matters")
async def create_matter(body: MatterCreate, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        if body.location_id:
            await _check_location(conn, body.location_id, company_id)
        row = await conn.fetchrow(
            """
            INSERT INTO legal_matters
                (company_id, title, matter_type, allegation, defense_theory,
                 evidence_start, evidence_end, counsel_directed, counsel_name,
                 counsel_email, created_by, location_id, jurisdiction_state, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'active')
            RETURNING *
            """,
            company_id, body.title, body.matter_type, body.allegation, body.defense_theory,
            body.evidence_start, body.evidence_end, body.counsel_directed,
            body.counsel_name, body.counsel_email, getattr(current_user, "id", None),
            body.location_id, body.jurisdiction_state,
        )
        await _audit(conn, row["id"], current_user, request, "create", {"title": body.title})
    return dict(row)


@router.get("/matters")
async def list_matters(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT m.*,
                   (SELECT COUNT(*) FROM legal_matter_packets p WHERE p.matter_id = m.id) AS packet_count
            FROM legal_matters m
            WHERE m.company_id = $1
            ORDER BY m.updated_at DESC
            """,
            company_id,
        )
    return [dict(r) for r in rows]


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
        matter["messages"] = await _load_messages(conn, matter_id)
        packets = await conn.fetch(
            "SELECT id, kind, filename, citations, file_size, generated_at "
            "FROM legal_matter_packets WHERE matter_id = $1 ORDER BY generated_at DESC",
            matter_id,
        )
        share_rows = await conn.fetch(
            """SELECT packet_id, recipient_email, download_count, last_downloaded_at,
                      expires_at, revoked, created_at
                 FROM legal_matter_share_links
                WHERE matter_id = $1 ORDER BY created_at DESC""",
            matter_id,
        )
        # Most recent share link per packet — a packet can be re-shared, we
        # only need the latest to answer "has counsel opened this".
        shares_by_packet: dict = {}
        for s in share_rows:
            pid = str(s["packet_id"])
            shares_by_packet.setdefault(pid, dict(s))
        matter["packets"] = [
            {**dict(p), "share": shares_by_packet.get(str(p["id"]))} for p in packets
        ]
    return matter


@router.patch("/matters/{matter_id}")
async def update_matter(matter_id: str, body: MatterUpdate, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        await _load_matter(conn, matter_id, company_id)  # ownership
        if fields.get("location_id"):
            await _check_location(conn, fields["location_id"], company_id)
        sets, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=1):
            sets.append(f"{k} = ${i}")
            vals.append(v)
        vals.append(matter_id)
        closed = ", closed_at = NOW()" if fields.get("status") == "closed" else ""
        await conn.execute(
            f"UPDATE legal_matters SET {', '.join(sets)}, updated_at = NOW(){closed} WHERE id = ${len(vals)}",
            *vals,
        )
        await _audit(conn, matter_id, current_user, request, "update", {"fields": list(fields.keys())})
        row = await _load_matter(conn, matter_id, company_id)
    return row


# --------------------------------------------------------------------------- #
# Evidence preview + grounded chat
# --------------------------------------------------------------------------- #

@router.get("/matters/{matter_id}/evidence")
async def get_evidence(matter_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
        features = await _features(conn, company_id)
        corpus = await ld.gather_evidence(
            conn, company_id, matter["evidence_start"], matter["evidence_end"], features, matter=matter
        )
    # Return source summaries + counts (the flat index is internal).
    return {
        "sources": corpus["sources"],
        "notes": corpus["notes"],
        "total": sum(len(s["records"]) for s in corpus["sources"].values()),
        "legal_context": corpus.get("legal_context"),
    }


@router.post("/matters/{matter_id}/chat")
async def chat(matter_id: str, body: ChatIn, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    # Pre-work in one connection; release it before the long Gemini call.
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
        history = await _load_messages(conn, matter_id)
        features = await _features(conn, company_id)
        corpus = await ld.gather_evidence(
            conn, company_id, matter["evidence_start"], matter["evidence_end"], features, matter=matter
        )
        await conn.execute(
            "INSERT INTO legal_matter_messages (matter_id, role, content) VALUES ($1, 'user', $2)",
            matter_id, body.message,
        )
        await _audit(conn, matter_id, current_user, request, "message", {"role": "user"})

    async def event_stream():
        result_payload = None
        try:
            async for ev in ld.run_chat_turn(matter, history, corpus, body.message):
                if ev.get("type") == "result":
                    result_payload = ev.get("data")
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("legal_defense: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis failed.'})}\n\n"
        # Persist the assistant turn (+ validated evidence map) after streaming.
        if result_payload:
            try:
                async with get_connection() as c2:
                    await c2.execute(
                        "INSERT INTO legal_matter_messages (matter_id, role, content, metadata) "
                        "VALUES ($1, 'assistant', $2, $3)",
                        matter_id, result_payload.get("assistant_text", ""),
                        json.dumps({
                            "evidence_map": result_payload.get("evidence_map"),
                            "open_questions": result_payload.get("open_questions"),
                            "dropped_citations": result_payload.get("dropped_citations"),
                        }),
                    )
                    await c2.execute(
                        "UPDATE legal_matters SET updated_at = NOW() WHERE id = $1", matter_id
                    )
            except Exception:
                logger.exception("legal_defense: failed to persist assistant message")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


# --------------------------------------------------------------------------- #
# External legal research (CourtListener case search + grounded Gemini
# guidance) — synchronous POST (worst case ~110s: 20s CourtListener + 90s
# Gemini), acceptable behind an explicit button. The row-status design
# supports a later move to BackgroundTasks + GET-poll with no schema change.
# --------------------------------------------------------------------------- #

@router.post("/matters/{matter_id}/research")
async def run_matter_research(
    matter_id: str, request: Request, body: ResearchOptions = ResearchOptions(),
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    # Load (and 404) BEFORE consuming the rate budget — a typo'd matter id
    # must not burn the company's 10/hour research allowance.
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
    await check_rate_limit(str(company_id), "legal_research", 10, 3600)
    # run_research manages its own short-lived connections so no pooled
    # connection is held across the ~110s of external CourtListener + Gemini
    # calls (same discipline as chat()'s pre-work/release pattern).
    row = await legal_research.run_research(
        matter, getattr(current_user, "id", None), include_guidance=body.include_guidance,
    )
    async with get_connection() as conn:
        await _audit(conn, matter_id, current_user, request, "research",
                     {"cases": len(row.get("cases") or []), "status": row.get("status"),
                      "include_guidance": body.include_guidance})
    return row


@router.get("/matters/{matter_id}/research")
async def list_matter_research(matter_id: str, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _load_matter(conn, matter_id, company_id)  # ownership
        rows = await conn.fetch(
            "SELECT * FROM legal_matter_research WHERE matter_id = $1 ORDER BY created_at DESC",
            matter_id,
        )
    return [legal_research.parse_research_row(dict(r)) for r in rows]


# --------------------------------------------------------------------------- #
# Packet generation + download + counsel share
# --------------------------------------------------------------------------- #

def _safe_name(s: str) -> str:
    """ASCII-only filename slug. Non-ASCII survives into Content-Disposition
    otherwise, and Starlette encodes header values as latin-1 — a title with
    an em dash or accent crashes every download of that packet with a 500."""
    ascii_s = unicodedata.normalize("NFKD", s or "matter").encode("ascii", "ignore").decode("ascii")
    return (ascii_s or "matter").replace("/", "-").replace('"', "").replace(" ", "-")[:60] or "matter"


def _safe_filename(name: Optional[str]) -> str:
    """Defensive re-sanitize for filenames already stored in the DB (packets
    created before ``_safe_name`` was hardened to strip non-ASCII)."""
    base, _, ext = (name or "packet").rpartition(".")
    return f"{_safe_name(base or name)}.{ext or 'bin'}"


@router.post("/matters/{matter_id}/packet")
async def generate_packet(matter_id: str, body: PacketIn, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        matter = await _load_matter(conn, matter_id, company_id)
        memo = await _latest_memo(conn, matter_id)
        if not memo:
            raise HTTPException(status_code=400, detail="Discuss the matter in chat first — the packet is built from that analysis.")
        features = await _features(conn, company_id)
        corpus = await ld.gather_evidence(
            conn, company_id, matter["evidence_start"], matter["evidence_end"], features, matter=matter
        )
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)

        research_row = None
        if body.include_research:
            # Same jurisdiction guard as _gather_case_law: a run grounded in a
            # different state than the matter's CURRENT jurisdiction is stale
            # and must not ride along in the packet.
            current_state = (corpus.get("legal_context") or {}).get("state")
            research_row = await conn.fetchrow(
                "SELECT * FROM legal_matter_research WHERE matter_id = $1 AND status = 'complete' "
                "AND ($2::varchar IS NULL OR jurisdiction_state IS NULL OR jurisdiction_state = $2) "
                "ORDER BY created_at DESC LIMIT 1",
                matter_id, current_state,
            )
            research_row = legal_research.parse_research_row(dict(research_row)) if research_row else None

        packet = await ld.build_defense_packet(conn, matter, corpus, memo,
                                                company_name=company["name"] if company else None,
                                                research=research_row)

        storage = get_storage()
        base = _safe_name(matter.get("title"))
        out = []

        async def _store(kind: str, blob: bytes, ext: str, mime: str):
            path = await storage.upload_private_file(
                blob, f"legal-defense-{base}.{ext}", prefix="legal-defense", content_type=mime
            )
            row = await conn.fetchrow(
                """INSERT INTO legal_matter_packets
                       (matter_id, company_id, kind, storage_path, filename, citations, file_size, generated_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id, kind, filename, file_size, generated_at""",
                matter_id, company_id, kind, path, f"legal-defense-{base}.{ext}",
                json.dumps(packet["citations"]), len(blob), getattr(current_user, "id", None),
            )
            out.append(dict(row))

        if body.kind in ("pdf", "both"):
            await _store("pdf", packet["pdf"], "pdf", "application/pdf")
        if body.kind in ("zip", "both") and packet.get("zip"):
            await _store("zip", packet["zip"], "zip", "application/zip")

        await _audit(conn, matter_id, current_user, request, "generate_packet",
                     {"kind": body.kind, "citations": len(packet["citations"]), "research": body.include_research})
    return {"packets": out}


async def _owned_packet(conn, matter_id: str, packet_id: str, company_id) -> dict:
    row = await conn.fetchrow(
        """SELECT p.* FROM legal_matter_packets p
           JOIN legal_matters m ON m.id = p.matter_id
           WHERE p.id = $1 AND p.matter_id = $2 AND m.company_id = $3""",
        packet_id, matter_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Packet not found")
    return dict(row)


@router.get("/matters/{matter_id}/packets/{packet_id}/download")
async def download_packet(matter_id: str, packet_id: str, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        pkt = await _owned_packet(conn, matter_id, packet_id, company_id)
        await _audit(conn, matter_id, current_user, request, "export", {"packet_id": packet_id})
    data = await get_storage().download_file(pkt["storage_path"])
    mime = "application/zip" if pkt["kind"] == "zip" else "application/pdf"
    return Response(
        content=data, media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(pkt["filename"])}"'},
    )


@router.post("/matters/{matter_id}/packets/{packet_id}/share")
async def share_packet(matter_id: str, packet_id: str, body: ShareIn, request: Request, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=body.expires_days)
    async with get_connection() as conn:
        await _owned_packet(conn, matter_id, packet_id, company_id)  # ownership
        await conn.execute(
            """INSERT INTO legal_matter_share_links
                   (matter_id, company_id, packet_id, token, recipient_email, expires_at, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            matter_id, company_id, packet_id, token, body.recipient_email, expires,
            getattr(current_user, "id", None),
        )
        await _audit(conn, matter_id, current_user, request, "share",
                     {"packet_id": packet_id, "recipient": body.recipient_email})
    return {"token": token, "path": f"/legal-pilot/share/{token}", "expires_at": expires}


# --------------------------------------------------------------------------- #
# Public counsel download (no auth — token-gated). Mounted without the feature
# gate, like inbound_email's /report token routes.
# --------------------------------------------------------------------------- #

@public_router.get("/legal-pilot/share/{token}")
async def download_shared_packet(token: str, request: Request):
    await check_rate_limit(client_ip(request), "legal_share_dl", 30, 3600)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT s.id, s.revoked, s.expires_at, p.storage_path, p.filename, p.kind, s.matter_id
               FROM legal_matter_share_links s
               JOIN legal_matter_packets p ON p.id = s.packet_id
               WHERE s.token = $1""",
            token,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Invalid or expired link")
        if row["revoked"]:
            raise HTTPException(status_code=410, detail="This link has been revoked")
        if row["expires_at"] is not None and row["expires_at"] <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="This link has expired")
        await conn.execute(
            "UPDATE legal_matter_share_links SET download_count = download_count + 1, "
            "last_downloaded_at = NOW() WHERE id = $1",
            row["id"],
        )
        await conn.execute(
            "INSERT INTO legal_matter_audit_log (matter_id, action, details, ip_address) VALUES ($1,$2,$3,$4)",
            row["matter_id"], "shared_download", json.dumps({"token_id": str(row["id"])}), client_ip(request),
        )
    data = await get_storage().download_file(row["storage_path"])
    mime = "application/zip" if row["kind"] == "zip" else "application/pdf"
    return Response(
        content=data, media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(row["filename"])}"'},
    )
