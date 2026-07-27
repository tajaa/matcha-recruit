"""Huume skill #2 — Legal Pilot in chat.

Thin agent-facing wrappers over the same `services/pilots/legal_defense`
library the `/legal-pilot` UI uses, writing to the SAME tables
(`legal_matters` / `legal_matter_messages` / `legal_matter_packets` /
`legal_matter_audit_log`) — a matter opened or discussed here shows up in the
Legal Pilot page and vice versa, with the full transcript shared between the
two surfaces.

Same split as `onboarding_skill`: `actions.evaluate_pilot_tool` owns the
authz/feature envelope (the skill engine gates nothing itself); everything
here assumes it already passed. Handlers open their own connections, never
raise past the agent loop (agent.py wraps calls in try/except anyway), and
return plain dicts the model reads as function responses.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from app.core.services.ai_usage import feature_scope

logger = logging.getLogger(__name__)

MATTER_TYPES = ("subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other")

_LIST_CAP = 10


def _citation_records(cids: list[str], index: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve validated cids to FE-renderable citation records (the shape
    `components/ui/CitationSources.tsx` expects). Only ids already validated
    against the corpus index reach here, so a miss is just skipped. Pure."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cid in cids or []:
        rec = (index or {}).get(cid)
        if not rec or cid in seen:
            continue
        seen.add(cid)
        out.append({
            "cid": cid,
            "ref": rec.get("ref") or cid,
            "summary": rec.get("summary") or "",
            "when": rec.get("when") or "",
            "source": rec.get("source") or "",
            "source_label": rec.get("source_label") or "",
        })
    return out


def _parse_iso_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _matter_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "matter_id": str(row["id"]),
        "title": row.get("title"),
        "matter_type": row.get("matter_type"),
        "status": row.get("status"),
        "jurisdiction_state": row.get("jurisdiction_state"),
        "response_deadline": row["response_deadline"].isoformat() if row.get("response_deadline") else None,
    }


async def list_matters(*, company_id: UUID) -> dict[str, Any]:
    """Read tool: the company's legal matters, newest activity first."""
    from app.database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT m.id, m.title, m.matter_type, m.status, m.jurisdiction_state,
                   m.response_deadline, m.updated_at,
                   (SELECT COUNT(*) FROM legal_matter_packets p WHERE p.matter_id = m.id) AS packet_count
            FROM legal_matters m
            WHERE m.company_id = $1
            ORDER BY m.updated_at DESC
            LIMIT $2
            """,
            company_id, _LIST_CAP,
        )
    matters = [{**_matter_summary(dict(r)), "packet_count": r["packet_count"]} for r in rows]
    if not matters:
        return {"matters": [], "note": "No legal matters exist yet — open one with open_legal_matter."}
    return {"matters": matters}


async def open_matter(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    title: str, matter_type: Optional[str] = None, allegation: Optional[str] = None,
    jurisdiction_state: Optional[str] = None,
    evidence_start: Optional[str] = None, evidence_end: Optional[str] = None,
) -> dict[str, Any]:
    """Create a legal matter (status 'active', same as the UI's create). The
    matter is a real record shared with the Legal Pilot page — audit-logged
    with the originating thread."""
    from app.database import get_connection

    title = (title or "").strip()[:300]
    if not title:
        return {"status": "error", "message": "A matter needs a title."}
    mtype = (matter_type or "other").strip().lower()
    if mtype not in MATTER_TYPES:
        mtype = "other"
    state = (jurisdiction_state or "").strip().upper()[:2] or None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO legal_matters
                (company_id, title, matter_type, allegation, jurisdiction_state,
                 evidence_start, evidence_end, created_by, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'active')
            RETURNING *
            """,
            company_id, title, mtype, (allegation or "").strip() or None, state,
            _parse_iso_date(evidence_start), _parse_iso_date(evidence_end), actor_user_id,
        )
        from app.matcha.services.pilots import legal_defense as ld
        await ld.audit_matter(
            conn, row["id"], actor_user_id, "create",
            {"title": title, "via": "huume", "thread_id": str(thread_id)},
        )
    return {"status": "ok", **_matter_summary(dict(row)),
            "message": f"Opened matter '{title}' — it's also visible on the Legal Pilot page."}


async def resolve_matter(
    conn, company_id: UUID, requested: Optional[str], fallback_id: Optional[str],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Resolve which matter a tool call means: explicit id → the thread's
    active matter (`current_state.huume_legal`) → the company's only open
    matter. Returns (matter, error) — mirrors `actions.resolve_plan_offer_id`'s
    shape so ambiguity is a refusal naming the candidates, never a guess."""
    from app.matcha.services.pilots import legal_defense as ld

    if requested:
        try:
            UUID(str(requested))
        except ValueError:
            return None, (
                f"'{requested}' isn't a matter id — call list_legal_matters and use the matter_id it returns."
            )
        matter = await ld.load_matter(conn, str(requested), company_id)
        if not matter:
            return None, "No matter with that id exists for this company."
        return matter, None

    if fallback_id:
        matter = await ld.load_matter(conn, str(fallback_id), company_id)
        if matter:
            return matter, None

    rows = await conn.fetch(
        "SELECT id, title FROM legal_matters WHERE company_id = $1 AND status != 'closed' "
        "ORDER BY updated_at DESC LIMIT $2",
        company_id, _LIST_CAP,
    )
    if not rows:
        return None, "No legal matters exist yet — open one with open_legal_matter first."
    if len(rows) > 1:
        names = "; ".join(f"{r['title']} (matter_id={r['id']})" for r in rows)
        return None, f"More than one matter is open — say which: {names}."
    matter = await ld.load_matter(conn, rows[0]["id"], company_id)
    return matter, None


async def ask_matter(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    matter_id: Optional[str], state_matter_id: Optional[str],
    question: str, features: dict[str, Any],
) -> dict[str, Any]:
    """One grounded Legal Pilot turn from chat: gather the matter's evidence
    corpus, run the citation-gated analysis, and persist BOTH sides of the
    exchange into `legal_matter_messages` — so the Legal Pilot page shows the
    same transcript and later turns (from either surface) carry this context.

    Mirrors the route's chat endpoint exactly, including releasing the
    connection before the long Gemini call."""
    from app.database import get_connection
    from app.matcha.services.pilots import legal_defense as ld

    question = (question or "").strip()
    if not question:
        return {"status": "error", "message": "Ask a question about the matter."}

    async with get_connection() as conn:
        matter, err = await resolve_matter(conn, company_id, matter_id, state_matter_id)
        if err:
            return {"status": "error", "message": err}
        history = await ld.load_messages(conn, matter["id"])
        corpus = await ld.gather_evidence(
            conn, company_id, matter["evidence_start"], matter["evidence_end"], features, matter=matter,
        )
        await conn.execute(
            "INSERT INTO legal_matter_messages (matter_id, role, content) VALUES ($1, 'user', $2)",
            matter["id"], question,
        )
        await ld.audit_matter(
            conn, matter["id"], actor_user_id, "message",
            {"role": "user", "via": "huume", "thread_id": str(thread_id)},
        )

    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    # Attribute the pilot's Gemini call to huume in the admin AI ledger —
    # without this it lands under the stack-derived `matcha.legal_defense`,
    # indistinguishable from the standalone /app/legal-pilot UI.
    with feature_scope("matcha.huume.legal_pilot"):
        async for ev in ld.run_chat_turn(matter, history, corpus, question):
            if ev.get("type") == "result":
                result = ev.get("data")
            elif ev.get("type") == "error":
                error_message = ev.get("message")
    if not result:
        return {"status": "error", "message": error_message or "Analysis failed — please try again."}

    async with get_connection() as c2:
        await c2.execute(
            "INSERT INTO legal_matter_messages (matter_id, role, content, metadata) "
            "VALUES ($1, 'assistant', $2, $3)",
            matter["id"], result.get("assistant_text", ""),
            json.dumps({
                "evidence_map": result.get("evidence_map"),
                "open_questions": result.get("open_questions"),
                "dropped_citations": result.get("dropped_citations"),
                "intake_requests": result.get("intake_requests"),
                "ready_for_analysis": result.get("ready_for_analysis"),
                "via": "huume",
            }),
        )
        await c2.execute("UPDATE legal_matters SET updated_at = NOW() WHERE id = $1", matter["id"])

    cited = [c for item in (result.get("evidence_map") or []) for c in (item.get("cited_ids") or [])]
    return {
        "status": "ok",
        "matter_id": str(matter["id"]),
        "title": matter.get("title"),
        "assistant_text": result.get("assistant_text") or "",
        "ready_for_analysis": result.get("ready_for_analysis"),
        "intake_requests": result.get("intake_requests") or [],
        "evidence_map": result.get("evidence_map") or [],
        "open_questions": result.get("open_questions") or [],
        "dropped_citations": result.get("dropped_citations") or [],
        "citation_records": _citation_records(cited, corpus.get("index") or {}),
    }


async def generate_packet(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    matter_id: Optional[str], state_matter_id: Optional[str],
    kind: str = "both", features: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Generate the attorney-facing packet(s) for a matter — same builder,
    storage upload and `legal_matter_packets` rows as the route, minus the
    external-research attach (that stays a Legal Pilot page action). Downloads
    happen from the Legal Pilot page, which lists every generated packet."""
    from app.core.services.storage import get_storage
    from app.database import get_connection
    from app.matcha.services.pilots import legal_defense as ld

    kind = (kind or "both").strip().lower()
    if kind not in ("pdf", "zip", "both"):
        kind = "both"

    async with get_connection() as conn:
        matter, err = await resolve_matter(conn, company_id, matter_id, state_matter_id)
        if err:
            return {"status": "error", "message": err}
        memo = await ld.latest_memo(conn, matter["id"])
        if not memo:
            return {
                "status": "refused",
                "message": "Discuss the matter first (ask_legal_pilot) — the packet is built from that analysis.",
            }
        # apply_theory=False: the packet is an attorney deliverable — the
        # appendix/ZIP must carry every in-scope record so the compilation
        # can't read as selective (same rule as the route).
        corpus = await ld.gather_evidence(
            conn, company_id, matter["evidence_start"], matter["evidence_end"],
            features or {}, matter=matter, apply_theory=False,
        )
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)

        with feature_scope("matcha.huume.legal_pilot"):
            packet = await ld.build_defense_packet(
                conn, matter, corpus, memo, company_name=company["name"] if company else None,
            )

        storage = get_storage()
        base = ld.safe_name(matter.get("title"))
        out: list[dict[str, Any]] = []

        async def _store(pkind: str, blob: bytes, ext: str, mime: str):
            path = await storage.upload_private_file(
                blob, f"legal-defense-{base}.{ext}", prefix="legal-defense", content_type=mime
            )
            row = await conn.fetchrow(
                """INSERT INTO legal_matter_packets
                       (matter_id, company_id, kind, storage_path, filename, citations, file_size, generated_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id, kind, filename, file_size, generated_at""",
                matter["id"], company_id, pkind, path, f"legal-defense-{base}.{ext}",
                json.dumps(packet["citations"]), len(blob), actor_user_id,
            )
            out.append({
                "packet_id": str(row["id"]), "kind": row["kind"], "filename": row["filename"],
                "file_size": row["file_size"],
            })

        if kind in ("pdf", "both"):
            await _store("pdf", packet["pdf"], "pdf", "application/pdf")
        if kind in ("zip", "both") and packet.get("zip"):
            await _store("zip", packet["zip"], "zip", "application/zip")

        await ld.audit_matter(
            conn, matter["id"], actor_user_id, "generate_packet",
            {"kind": kind, "citations": len(packet["citations"]), "via": "huume",
             "thread_id": str(thread_id)},
        )

    return {
        "status": "ok",
        "matter_id": str(matter["id"]),
        "title": matter.get("title"),
        "packets": out,
        "message": "Packet generated — download it from the Legal Pilot page (matter → Packets).",
    }
