"""Writes: the unpaid-Matcha-X gate reason, per-turn transcript + draft
persistence, and promotion of reviewed drafts into the real handbook / policy
tables.
"""
import json
import logging

from .chat import strip_corpus_citations

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Persistence + promotion — shared by the HTTP route (routes/pilots/handbook.py)
# and the Huume chat skill (services/huume/handbook_skill.py). HTTP-free:
# refusals are return values, never HTTPExceptions; audit logging stays with
# the caller (the route has a request IP, Huume doesn't).
# --------------------------------------------------------------------------- #

async def unpaid_x_reason(conn, company_id) -> str | None:
    """Why generation/promotion is blocked for this company, or None.

    handbook_pilot is granted to Matcha-X via the tier overlay *before*
    checkout, and the Stripe webhook flips `incidents` on payment (the X paid
    gate) — so an abandoned-checkout X company can reach the feature but must
    not run Gemini generation or promote until paid. Pro/bespoke
    (contract-billed) has no such gate."""
    from app.core.feature_flags import merge_company_features

    row = await conn.fetchrow(
        "SELECT signup_source, enabled_features FROM companies WHERE id = $1", company_id
    )
    if not row or row["signup_source"] != "matcha_x":
        return None
    features = merge_company_features(row["enabled_features"], row["signup_source"])
    if not features.get("incidents"):
        return "Subscribe to Matcha-X to use Handbook Pilot drafting."
    return None


async def persist_turn(session_id, company_id, result_payload: dict, user_id) -> list[str]:
    """Persist one chat turn's assistant message + proposed draft rows in a
    single transaction. Returns the new draft row ids (as strings, in
    proposal order). Opens its own connection — callers wrap in
    asyncio.shield when a client disconnect must not drop a paid-for turn."""
    from app.database import get_connection

    drafts = result_payload.get("proposed_drafts") or []
    async with get_connection() as c2:
        async with c2.transaction():
            draft_ids: list[str] = []
            for d in drafts:
                new_id = await c2.fetchval(
                    """INSERT INTO handbook_pilot_drafts
                           (session_id, company_id, kind, title, section_key,
                            content, citations, created_by)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                    session_id, company_id, d["kind"], d["title"],
                    d.get("section_key"), d["content"],
                    json.dumps(d.get("cited_ids") or []), user_id,
                )
                draft_ids.append(str(new_id))
            await c2.execute(
                "INSERT INTO handbook_pilot_messages (session_id, role, content, metadata) "
                "VALUES ($1, 'assistant', $2, $3)",
                session_id, result_payload.get("assistant_text", ""),
                json.dumps({
                    "open_questions": result_payload.get("open_questions"),
                    "dropped_citations": result_payload.get("dropped_citations"),
                    "draft_ids": draft_ids,
                }),
            )
            await c2.execute(
                "UPDATE handbook_pilot_sessions SET updated_at = NOW() WHERE id = $1",
                session_id,
            )
    return draft_ids


async def promote_drafts(company_id, session: dict, drafts: list[dict], *,
                         scopes: list, handbook_title: str | None = None,
                         user_id=None) -> dict:
    """Push reviewed pending drafts into the real handbooks / policies tables.

    Section drafts become ONE new draft handbook (atomic —
    create_handbook_from_sections runs in a single transaction); policy drafts
    become one draft policy each (independent; a failure doesn't block the
    rest). Partial success is first-class: successes are marked
    `status='promoted'` with a `promoted_ref` pointing at the real record (so a
    re-promote of the rest never re-creates them), failures return in
    `failed[]` rather than raising.

    Returns {"promoted_refs": {draft_id: ref}, "handbook": {...}|None,
             "policies": [...], "failed": [{draft_id, title, error}]}.
    """
    from uuid import UUID as _UUID

    from app.database import get_connection

    section_drafts = [d for d in drafts if d["kind"] == "handbook_section"]
    policy_drafts = [d for d in drafts if d["kind"] == "policy"]

    promoted: dict[str, dict] = {}      # draft_id -> promoted_ref
    handbook_result: dict | None = None
    policy_results: list[dict] = []
    failed: list[dict] = []             # {draft_id, title, error}

    if section_drafts:
        from app.core.services.handbook_service import HandbookService
        sections = [{
            "section_key": d.get("section_key"),
            "title": d["title"],
            # Belt-and-suspenders: strip any inline corpus-id tags before the
            # text lands in the real handbook (covers legacy/edited drafts that
            # predate the generation-time strip).
            "content": strip_corpus_citations(d["content"])[0],
            "section_type": "custom",
        } for d in section_drafts]
        title = (handbook_title or session.get("title") or "Handbook Pilot draft")[:300]
        try:
            handbook = await HandbookService.create_handbook_from_sections(
                str(company_id), title, scopes, sections, str(user_id) if user_id else None,
            )
            hb_id = str(handbook.id)
            handbook_result = {"id": hb_id, "title": title}
            for d in section_drafts:
                promoted[str(d["id"])] = {"kind": "handbook", "handbook_id": hb_id}
        except Exception as exc:  # noqa: BLE001 - surface as a per-draft failure, not a 500
            logger.exception("handbook_pilot: handbook promotion failed")
            for d in section_drafts:
                failed.append({"draft_id": str(d["id"]), "title": d["title"], "error": str(exc)})

    if policy_drafts:
        from app.core.services.policy_service import PolicyService
        from app.core.models.policy import PolicyCreate
        for d in policy_drafts:
            try:
                policy = await PolicyService.create_policy(
                    str(company_id),
                    PolicyCreate(title=d["title"],
                                 content=strip_corpus_citations(d["content"])[0],
                                 status="draft", source_type="manual"),
                    str(user_id) if user_id else None,
                )
                pid = str(policy.id)
                policy_results.append({"id": pid, "title": d["title"]})
                promoted[str(d["id"])] = {"kind": "policy", "policy_id": pid}
            except Exception as exc:  # noqa: BLE001
                logger.exception("handbook_pilot: policy promotion failed for draft %s", d["id"])
                failed.append({"draft_id": str(d["id"]), "title": d["title"], "error": str(exc)})

    # Mark whatever succeeded as promoted (each ref points at the real record so
    # a re-promote of the rest never re-creates the succeeded ones).
    async with get_connection() as conn:
        for draft_id, ref in promoted.items():
            await conn.execute(
                "UPDATE handbook_pilot_drafts SET status = 'promoted', promoted_ref = $2::jsonb, "
                "updated_at = NOW() WHERE id = $1",
                _UUID(draft_id), json.dumps(ref),
            )
        await conn.execute(
            "UPDATE handbook_pilot_sessions SET updated_at = NOW() WHERE id = $1", session["id"]
        )

    return {
        "promoted_refs": promoted,
        "handbook": handbook_result,
        "policies": policy_results,
        "failed": failed,
    }
