"""IR Copilot card + chain state machine.

Everything the Copilot endpoints do *between* receiving a request and writing
the response: emitting a chain card, advancing the OSHA recordable/description
chains, validating a set_field value, running a quick-reply / numeric / text
input turn, closing an incident, and seeding structured corrective actions.
Also the transcript coercion helpers and the protected-card guard that
`inbound_email.py` resumes through.

Extracted from `routes/ir_incidents/copilot.py` in refactor round 2 stage 5 —
1,269 lines of business logic that had accumulated in the route file, leaving
the 5 endpoints behind. Sits next to `ir_flow.py`, the deterministic gate
resolver these functions consult.

Two coupling notes:

* The functions here take an open `conn` and are called from inside the routes'
  transactions; they do not open their own. That is unchanged from the route
  file and is what lets `_close_incident_via_copilot` write its close, audit,
  and training assignment atomically.
* Card *builders* stay in `routes/ir_incidents/_cards.py` (re-exported through
  that package's `_shared.py`) and are imported here. They are pure, and the
  L5 split already treated them as the shared vocabulary; only the DB-touching
  dispatchers moved.

`copilot.py` re-exports every public name below, so
`from app.matcha.routes.ir_incidents.copilot import X` still resolves. Tests
that `monkeypatch.setattr` a collaborator must target THIS module — a function
resolves globals in the module it is defined in, not the one it is imported
into.
"""
import json
import logging
import re
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.database import get_connection
from app.matcha.services.ir import ir_flow
from app.core.services.osha_privacy import compose_clinical_description
from app.matcha.models.ir.copilot import IRCopilotAcceptRequest, IRCopilotCard, IRCopilotMessage



class _LazyIrShared:
    """Lazy proxy for `app.matcha.routes.ir_incidents._shared`.

    A module-level import cannot work: importing this module would import the
    `ir_incidents` package, whose `__init__` imports `copilot.py`, which imports
    this module back — and at that point this module is half-built, so the
    `from ... import` of its names raises. The repo's existing convention for
    this exact edge (see `ir_flow.py`'s docstring) is a function-local import;
    this proxy is the same deferral with one object instead of ~19 copies of the
    import line.

    Resolution happens per attribute access, deliberately NOT cached: a test
    that `monkeypatch.setattr`s `ir_incidents._shared` is then seen by the
    functions below, which is how the existing OSHA copilot tests patch
    `next_case_step`.

    Reaching for `_shared` at all is a services -> routes dependency. It is the
    IR package's own vocabulary (pure card builders from `_cards.py` plus the
    DB-backed `next_case_step` / `ensure_osha_case_rows` dispatchers, both used
    by half the package's submodules), so it stayed put rather than being
    dragged into services by this move.
    """

    __slots__ = ()

    def __getattr__(self, name):
        from app.matcha.routes.ir_incidents import _shared

        return getattr(_shared, name)


_ir = _LazyIrShared()

logger = logging.getLogger(__name__)


def _coerce_metadata_dict(value):
    """asyncpg returns JSONB as str when no codec is registered."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _serialize_message(row) -> IRCopilotMessage:
    return IRCopilotMessage(
        id=row["id"],
        role=row["role"],
        message_type=row.get("message_type", "text") if isinstance(row, dict) else row["message_type"],
        content=row["content"],
        metadata=_coerce_metadata_dict(row["metadata"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _extract_current_cards(messages: list) -> list[IRCopilotCard]:
    """Latest assistant card-set is everything between the last assistant text and now."""
    cards: list[dict] = []
    saw_assistant_text = False
    for m in messages:
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = (m["message_type"] if isinstance(m, dict) else m.message_type) if hasattr(m, 'message_type') or isinstance(m, dict) else "text"
        if role == "assistant" and mtype == "text":
            saw_assistant_text = True
            cards = []  # reset — start fresh after each assistant text
            continue
        if saw_assistant_text and role == "assistant" and mtype == "card":
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            card = md.get("card")
            if isinstance(card, dict):
                # Only include cards that haven't been accepted, superseded, or skipped.
                if not md.get("accepted") and not md.get("superseded") and not md.get("skipped"):
                    try:
                        cards.append(IRCopilotCard.model_validate(card))
                    except Exception:
                        continue
    return cards


def _extract_summary_and_open_questions(messages: list) -> tuple[Optional[str], list[str]]:
    summary: Optional[str] = None
    open_questions: list[str] = []
    for m in reversed(messages):
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = m["message_type"] if isinstance(m, dict) else m.message_type
        if role == "assistant" and mtype == "text":
            summary = m["content"] if isinstance(m, dict) else m.content
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            raw_q = md.get("open_questions") or []
            if isinstance(raw_q, list):
                open_questions = [str(q)[:280] for q in raw_q if isinstance(q, str)]
            break
    return summary, open_questions


# Card ids that kick off a multi-step chain. Superseding one mid-chain strands
# the partially-written JSONB behind it, so the skip endpoint refuses them and
# the background auto-resume declines to run at all while one is open.
_PROTECTED_CHAIN_CARD_ID_PREFIXES = ("osha_days_count",)


_PROTECTED_CHAIN_CARD_IDS = {
    "osha_recordable_query",
    "osha_days_type_query",
    "osha_injury_type_query",
}


def _has_pending_protected_card(messages: list) -> bool:
    """True when an unanswered card sits mid-chain in the transcript.

    Mirrors the refusals in the skip endpoint: the OSHA emergency alert, the
    root-cause interview steps, and the OSHA 300 capture chain. "Pending" uses
    the same accepted/superseded/skipped triple the panel filters on, so this
    sees exactly the cards the admin still has on screen.
    """
    for m in messages or []:
        if (m.get("role") if isinstance(m, dict) else None) != "assistant":
            continue
        if m.get("message_type") != "card":
            continue
        md = _coerce_metadata_dict(m.get("metadata")) or {}
        if md.get("accepted") or md.get("superseded") or md.get("skipped"):
            continue
        card = md.get("card")
        if not isinstance(card, dict):
            continue
        action = card.get("action") or {}
        if action.get("type") == "osha_emergency_alert":
            return True
        if (
            action.get("type") == "text_input"
            and action.get("target_field") in _ir.ROOT_CAUSE_INTERVIEW_STEPS
        ):
            return True
        card_id = card.get("id") or ""
        if isinstance(card_id, str) and (
            card_id in _PROTECTED_CHAIN_CARD_IDS
            or card_id.startswith(_PROTECTED_CHAIN_CARD_ID_PREFIXES)
        ):
            return True
    return False


async def resume_copilot_after_info_request(*, company_id: str, incident_id: UUID) -> None:
    """Auto-resume Copilot guidance after an external "Request More Info"
    submission lands a new system event in the transcript (``submit_info_request``
    in ``intake/inbound_email.py``). Without this, the AI only reacts the next
    time an admin manually types a chat message — the respondent's answers
    would otherwise just sit in the transcript as an inert system event until
    someone prompts the copilot by hand.

    Runs as a ``BackgroundTasks`` job: no request-scoped connection and no
    authenticated user (the submitter is an anonymous public respondent), so
    failures are logged and swallowed rather than surfaced to the
    already-responded HTTP caller. Mirrors the connection-release pattern in
    ``stream_copilot_round`` — state is loaded and released before the
    (up-to-60s) Gemini call, then a fresh connection persists the result.
    """
    from app.matcha.services.ir.ir_ai_orchestrator import (
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    try:
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, UUID(str(company_id)),
            )
        if incident is None or incident.get("status") in {"closed", "resolved"}:
            return

        # Don't run a round while the admin is mid-chain. persist_assistant_round
        # opens by superseding every unaccepted card, and the skip endpoint
        # (400s on these same cards) exists precisely because abandoning one
        # strands its chain: a half-answered root-cause interview leaves
        # category_data.root_cause_interview populated, which then satisfies
        # needs_root_cause — so the incident could close with an investigation
        # that was never finished, triggered by an anonymous respondent with no
        # admin action at all. The answers are already in the transcript and
        # surface via the panel's poll; the copilot picks them up on the
        # admin's next turn.
        if _has_pending_protected_card(messages):
            logger.info(
                "IR Copilot auto-resume skipped for incident %s — protected card pending",
                incident_id,
            )
            return

        payload = await generate_guidance(
            incident=incident, analyses=analyses, messages=messages,
        )

        # One transaction for the whole round. persist_assistant_round opens by
        # marking every unaccepted card superseded, so without this an admin
        # accepting a card at the same moment could interleave with the
        # supersede sweep and land a card that is both accepted and superseded;
        # the row locks serialize the two. It also keeps the audit entry from
        # being dropped (this task swallows exceptions) while the cards it
        # describes stay committed.
        async with get_connection() as conn, conn.transaction():
            await persist_assistant_round(
                conn,
                incident_id=incident_id,
                user_id=None,
                user_message=None,
                guidance_payload=payload,
            )
            await _ir.log_audit(
                conn,
                incident_id=str(incident_id),
                user_id=None,
                action="copilot_auto_resume",
                entity_type="incident",
                entity_id=str(incident_id),
                details={
                    "trigger": "info_request_submitted",
                    "cards": len(payload.get("cards") or []),
                },
                ip_address=None,
            )
    except Exception:
        logger.exception(
            "IR Copilot auto-resume failed for incident %s", incident_id,
        )


_FIELD_WHITELIST = {
    "category": "incident_type",  # alias — DB col is incident_type
    "incident_type": "incident_type",
    "severity": "severity",
    "status": "status",
    "root_cause": "root_cause",
    "corrective_actions": "corrective_actions",
}


_FIELD_LABELS = {
    "incident_type": "Type",
    "severity": "Severity",
    "status": "Status",
    "root_cause": "Root cause",
    "corrective_actions": "Corrective actions",
}


_VALID_INCIDENT_TYPES = {"safety", "behavioral", "property", "near_miss", "other"}


_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


_VALID_STATUSES = {"reported", "investigating", "action_required", "resolved", "closed"}


def _validate_field_value(field: str, value):
    if field == "incident_type" and value not in _VALID_INCIDENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid incident_type: {value}")
    if field == "severity" and value not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {value}")
    if field == "status" and value not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")


async def _emit_chain_card(conn, *, incident_id: UUID, card: dict, created_by=None) -> dict:
    """Append a single assistant card row to the transcript and return the inserted row.

    Used by the OSHA recordable chain to drop the next step's card after the
    user accepts the previous one (or after the close-time guard redirects).
    Shape matches what ``persist_assistant_round`` writes for AI-emitted cards.
    """
    from app.matcha.services.ir.ir_ai_orchestrator import append_message

    return await append_message(
        conn,
        incident_id=incident_id,
        role="assistant",
        message_type="card",
        content=card.get("title") or "Recommendation",
        metadata={"card": card, "accepted": False},
        created_by=created_by,
    )


async def ensure_case_chain(conn, incident_id, current_user) -> None:
    """Ensure the per-injured-employee OSHA case-capture chain is running.

    Creates one ir_osha_case_details row per injured employee, then emits the
    next capture card (days/classification → injury → privacy) if none is already
    pending. Idempotent — safe after recordability is set by ANY path. Covers
    recordability set OUTSIDE the Copilot chain (e.g. the manual PUT /osha
    override), which would otherwise skip per-case capture + privacy entirely and
    leave Column-B masking to the determine_privacy_case safety net alone.
    """
    await _ir.ensure_osha_case_rows(conn, incident_id)
    pending = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND (
            metadata->'card'->>'id' IN ('osha_clean_description_review', 'osha_days_type_query', 'osha_injury_type_query', 'privacy_case_query')
            OR metadata->'card'->>'id' LIKE 'osha_days_count%'
          )
          AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
        LIMIT 1
        """,
        incident_id,
    )
    if pending:
        return
    # Human-approve the name-free Column F description first; the per-case loop
    # (days/injury/privacy) resumes only after approval.
    if await _emit_osha_description_review(conn, incident_id, current_user) is not None:
        return
    card = await _ir.next_case_step(conn, incident_id)
    if card is None:
        return
    await _emit_chain_card(
        conn, incident_id=incident_id, card=card,
        created_by=current_user.id if current_user else None,
    )


async def _emit_osha_description_review(conn, incident_id, current_user):
    """Generate + emit the name-free OSHA Description (Column F) review card.

    Returns ``(card, message_id)`` when a review card is emitted, else ``None``
    (already approved, or one is already pending). Builds the prefilled DRAFT
    best-effort — prior draft → AI ``cleanse_description`` → structured clinical
    phrase → blank — and stores it under ``category_data.osha_clean_description_draft``
    (a separate key, so the unapproved draft never reaches the log). The canonical
    ``osha_clean_description`` is written only when the human approves the card.
    """
    cd = _ir._safe_json_loads(
        await conn.fetchval("SELECT category_data FROM ir_incidents WHERE id = $1", incident_id), {}
    ) or {}
    if cd.get("osha_description_approved") is True:
        return None
    already = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND metadata->'card'->>'id' = 'osha_clean_description_review'
          AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
        LIMIT 1
        """,
        incident_id,
    )
    if already:
        return None

    # Prefill order: prior draft → any existing cleansed value (legacy incidents
    # cleansed pre-approval) → AI cleanse → structured clinical phrase. All of
    # these are name-free, so cleansed=True. If every one comes up empty (AI off
    # and nothing structured yet), fall back to seeding the editor with the RAW
    # narrative (cleansed=False) so the box is never blank — the human strips the
    # names. The raw fallback is display-only; only cleansed drafts are persisted.
    draft = (cd.get("osha_clean_description_draft") or cd.get("osha_clean_description") or "").strip()
    cleansed = True
    if not draft:
        row = await conn.fetchrow(
            "SELECT title, description FROM ir_incidents WHERE id = $1", incident_id
        )
        try:
            from app.matcha.services.ir.ir_analysis import get_ir_analyzer
            clean = await get_ir_analyzer().cleanse_description(
                title=(row["title"] if row else "") or "",
                description=(row["description"] if row else "") or "",
            )
            draft = (clean or "").strip()
        except Exception:
            logger.exception(f"[IR] osha description cleanse (review) failed for {incident_id}")
            draft = ""
        if not draft:
            draft = (compose_clinical_description(cd) or "").strip()
        if draft:
            # genuine name-free draft → persist for re-display and reuse
            await conn.execute(
                """
                UPDATE ir_incidents
                SET category_data = jsonb_set(
                    COALESCE(category_data, '{}'::jsonb),
                    '{osha_clean_description_draft}',
                    to_jsonb($2::text),
                    true
                ),
                updated_at = NOW()
                WHERE id = $1
                """,
                incident_id, draft,
            )
        else:
            # last resort: seed the raw narrative for the human to rewrite.
            # NOT persisted (may contain names; never printed until approved).
            draft = ((row["description"] if row else "") or "").strip()[:2000]
            cleansed = False

    card = _ir.build_osha_clean_description_card(draft, cleansed=cleansed)
    inserted = await _emit_chain_card(
        conn, incident_id=incident_id, card=card,
        created_by=current_user.id if current_user else None,
    )
    return card, str(inserted["id"])


async def _should_emit_osha_recordable_chain(conn, incident_id) -> bool:
    """Pure check (no writes). True when the OSHA recordable chain hasn't
    run yet and the incident is OSHA-flagged via the emergency alert
    keyword scan or severity=critical.

    Used as the gate for the safety-net call sites that emit the
    recordable chain proactively when otherwise the AI fallback would
    suggest "close for documentation only" on a reportable injury.
    """
    row = await conn.fetchrow(
        "SELECT severity, osha_recordable, category_data "
        "FROM ir_incidents WHERE id = $1",
        incident_id,
    )
    if row is None or row["osha_recordable"] is not None:
        return False
    cd = _ir._safe_json_loads(row["category_data"], {}) or {}
    flagged = (
        row["severity"] == "critical"
        or cd.get("osha_emergency_alert_active") in (True, "true")
        or "reported_to_osha_notes" in cd  # alert was acked, flag now false
    )
    if not flagged:
        return False
    if cd.get("osha_recordable_chain_started") is True:
        return False
    # Mirror the dedup at _close_incident_via_copilot:427-440 so a
    # repeat poll while a recordable_query card is already pending
    # doesn't stack identical cards in the transcript.
    existing = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND metadata->'card'->>'id' = 'osha_recordable_query'
          AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
          AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
          AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
        LIMIT 1
        """,
        incident_id,
    )
    return existing is None


async def _emit_osha_recordable_chain(conn, *, incident_id, current_user):
    """Insert the osha_recordable_query card, stamp the chain-started
    flag on category_data, and return (card_dict, message_id_str).

    The caller must mark the triggering card accepted (if any) and skip
    the AI guidance round so the deterministic chain doesn't compete
    with an overlapping Gemini suggestion.
    """
    card = _ir.build_osha_recordable_query_card()
    inserted = await _emit_chain_card(
        conn,
        incident_id=incident_id,
        card=card,
        created_by=current_user.id if current_user else None,
    )
    await conn.execute(
        """
        UPDATE ir_incidents
        SET category_data = jsonb_set(
            COALESCE(category_data, '{}'::jsonb),
            '{osha_recordable_chain_started}',
            'true'::jsonb,
            true
        ),
            updated_at = NOW()
        WHERE id = $1
        """,
        incident_id,
    )
    return card, str(inserted["id"])


async def _close_incident_via_copilot(
    conn,
    *,
    incident_id: UUID,
    source_card_id: Optional[UUID] = None,
    current_user=None,
) -> dict:
    """Close an incident and supersede any open card recommendations.

    Called from both the card-accept path (with source_card_id set) and the
    direct-button path (source_card_id None — supersede ALL open cards).
    Idempotent: returns ``already_closed=True`` and skips writes when the
    incident is already in 'closed' status.

    Two pre-close guards run first:

    1. **OSHA emergency block** — if ``category_data.osha_emergency_alert_active``
       is true, the reportable-event alert hasn't been acknowledged. Return
       ``{blocked_by_emergency: True}``; callers should surface a 400 to the
       user. They can clear the block by accepting the ``osha_emergency_alert``
       card with confirmation notes.

    2. **OSHA recordable chain redirect** — if ``treatment_beyond_first_aid``
       is true AND ``osha_recordable`` is null, the OSHA 300 capture chain
       hasn't run. Emit the first chain card (``osha_recordable_query``) and
       return ``{redirected_to_osha_chain: True, redirect_card: <inserted row>}``
       without changing status. Callers should NOT mark close successful.

    Returns the normal close result dict when no guard trips.
    """
    row = await conn.fetchrow(
        """
        SELECT status, osha_recordable, category_data, root_cause,
               incident_type, severity, company_id, involved_employee_ids
        FROM ir_incidents WHERE id = $1
        """,
        incident_id,
    )
    prev_status = row["status"] if row else None
    if prev_status == "closed":
        return {"already_closed": True, "previous_value": prev_status, "new_value": "closed"}

    category_data = _ir._safe_json_loads(row["category_data"] if row else None, {}) or {}
    if ir_flow.osha_emergency_blocking(category_data):
        return {
            "blocked_by_emergency": True,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

    # Pre-close root-cause prompt: for safety / near-miss / high-severity
    # incidents, require the user to either log a root cause or
    # explicitly decline before closing. Otherwise the wizard could let a
    # safety incident close with no investigation captured — which the
    # user reported as a regression. Skipped when:
    #   - root_cause is non-empty (already logged)
    #   - category_data.root_cause_declined is true (user said No)
    #   - category_data.root_cause_interview has any keys (mid-interview)
    # Predicate lives in ir_flow so the progress meter (ir_flow.close_progress)
    # and this redirect can never disagree about whether root cause is still
    # outstanding — a meter reading 100% while Close bounces the user back into
    # a root-cause card is exactly the confusion the meter exists to remove.
    needs_root_cause_prompt = ir_flow.needs_root_cause(
        incident_type=row["incident_type"] if row else None,
        severity=row["severity"] if row else None,
        root_cause=row["root_cause"] if row else None,
        category_data=category_data,
    )
    if needs_root_cause_prompt:
        card = _ir.build_log_root_cause_query_card()
        # Idempotency: reuse a pending log_root_cause_query if one is
        # already in the transcript (e.g. double-click on Close).
        existing = await conn.fetchrow(
            """
            SELECT id FROM ir_incident_ai_messages
            WHERE incident_id = $1
              AND message_type = 'card'
              AND metadata->'card'->>'id' = $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            incident_id, card["id"],
        )
        if existing:
            message_id = str(existing["id"])
        else:
            inserted = await _emit_chain_card(
                conn,
                incident_id=incident_id,
                card=card,
                created_by=current_user.id if current_user else None,
            )
            message_id = str(inserted["id"])
        return {
            "redirected_to_root_cause": True,
            "redirect_card": card,
            "redirect_message_id": message_id,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

    if ir_flow.needs_osha_recordable(
        category_data=category_data,
        osha_recordable=row["osha_recordable"] if row else None,
    ):
        card = _ir.build_osha_recordable_query_card()
        # Idempotency: if a prior close attempt already emitted the
        # recordable query and the user hasn't answered or skipped, reuse
        # that row instead of inserting a duplicate (a double-click on the
        # Close button would otherwise stack identical cards in the
        # transcript).
        existing = await conn.fetchrow(
            """
            SELECT id FROM ir_incident_ai_messages
            WHERE incident_id = $1
              AND message_type = 'card'
              AND metadata->'card'->>'id' = $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            incident_id, card["id"],
        )
        if existing:
            message_id = str(existing["id"])
        else:
            inserted = await _emit_chain_card(
                conn,
                incident_id=incident_id,
                card=card,
                created_by=current_user.id if current_user else None,
            )
            message_id = str(inserted["id"])
        return {
            "redirected_to_osha_chain": True,
            "redirect_card": card,
            "redirect_message_id": message_id,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

    await conn.execute(
        "UPDATE ir_incidents SET status = 'closed', resolved_at = NOW(), "
        "updated_at = NOW() WHERE id = $1",
        incident_id,
    )
    if source_card_id is not None:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND id != $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id, source_card_id,
        )
    else:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id,
        )

    # Auto-assign training per training_assignment_rules(trigger='incident').
    # Best-effort — a rule-matching failure must never block the close.
    if row and row["company_id"]:
        try:
            from app.matcha.services.training.training_assignment import on_incident_closed

            await on_incident_closed(
                conn,
                row["company_id"],
                {
                    "id": incident_id,
                    "incident_type": row["incident_type"],
                    "severity": row["severity"],
                    "involved_employee_ids": row["involved_employee_ids"] or [],
                },
            )
        except Exception:
            logger.exception("Failed to auto-assign incident training for %s", incident_id)

    return {
        "already_closed": False,
        "previous_value": prev_status,
        "new_value": "closed",
        "field": "status",
        "field_label": "Status",
    }


async def _handle_quick_reply(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Dispatch quick_reply card accepts by ``quick_reply_kind``.

    Returns a dict with optional ``error``, ``event_summary``, ``event_extra``,
    ``next_card`` (raw card dict to surface to the user), and
    ``next_message_id`` (the transcript row id of the inserted card).

    Three kinds handled:
      * ``osha_recordable_query`` — Yes/No → write ``osha_recordable``
      * ``osha_days_type_query`` — Days Away / Restriction / Neither → write
        ``osha_classification`` and dispatch the next card
      * ``osha_injury_type_query`` — 6-option picker → write injury type to
        ``osha_form_301_data->>'injury_type'``
    """
    kind = (action.get("quick_reply_kind") or "").strip()
    selected = (body.selected_value or "").strip().lower()
    if not selected:
        return {"error": "Pick an option to continue."}

    allowed_by_kind = {
        "treatment_query": {"yes", "no"},
        "osha_recordable_query": {"yes", "no"},
        "osha_days_type_query": {"days_away", "restricted_duty", "neither"},
        "osha_injury_type_query": _ir.OSHA_INJURY_TYPES,
        "log_root_cause_query": {"yes", "no"},
        "privacy_case_query": set(_ir.PRIVACY_CASE_REASONS) | {"none"},
    }
    if kind not in allowed_by_kind:
        return {"error": f"Unknown quick_reply kind: {kind}"}
    if selected not in allowed_by_kind[kind]:
        return {"error": f"Invalid selection '{selected}' for {kind}"}

    if kind == "treatment_query":
        # Injury-assessment gate. Writes category_data.treatment_beyond_first_aid
        # (same JSONB key the set_field path uses). "Yes" → injury is generally
        # OSHA recordable, so chain straight into the recordable query.
        bool_value = selected == "yes"
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{treatment_beyond_first_aid}',
                $1::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            "true" if bool_value else "false",
            incident_id,
        )
        event_extra = {
            "field": "treatment_beyond_first_aid",
            "field_label": "Treatment beyond first aid",
            "previous_value": None,
            "new_value": bool_value,
        }
        if bool_value:
            next_card = _ir.build_osha_recordable_query_card()
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Recorded: treatment beyond on-site first aid",
                "event_extra": event_extra,
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        return {
            "event_summary": "Recorded: on-site first aid only",
            "event_extra": event_extra,
        }

    if kind == "log_root_cause_query":
        # Skip-if-answered: a non-empty existing root_cause means the user
        # already filled this in (manual edit or prior interview round).
        existing = await conn.fetchval(
            "SELECT NULLIF(TRIM(root_cause), '') FROM ir_incidents WHERE id = $1",
            incident_id,
        )
        if existing:
            return {
                "event_summary": "Root cause already on file — skipping the interview.",
                "event_extra": {},
            }
        if selected == "yes":
            first = _ir.build_root_cause_text_card(step="hazard")
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=first, created_by=current_user.id,
            )
            return {
                "event_summary": "Starting root cause interview.",
                "event_extra": {},
                "next_card": first,
                "next_message_id": str(inserted["id"]),
            }
        # No: stamp category_data.root_cause_declined so the next guidance
        # round's safety-net rewrite skips re-prompting. Otherwise the AI
        # sees an empty root_cause and re-emits run_analysis root_cause,
        # which we'd just rewrite back to the same Yes/No card — an
        # infinite loop from the user's perspective.
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{root_cause_declined}',
                'true'::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $1
            """,
            incident_id,
        )
        return {
            "event_summary": "Noted — no root cause logged.",
            "event_extra": {
                "field": "root_cause_declined",
                "field_label": "Root cause",
                "previous_value": None,
                "new_value": "declined",
            },
        }

    if kind == "osha_recordable_query":
        bool_value = selected == "yes"
        await conn.execute(
            "UPDATE ir_incidents SET osha_recordable = $1, updated_at = NOW() WHERE id = $2",
            bool_value, incident_id,
        )
        event_summary = (
            "Marked as OSHA recordable" if bool_value else "Marked as not OSHA recordable"
        )
        event_extra = {
            "field": "osha_recordable",
            "field_label": "OSHA recordable",
            "previous_value": None,
            "new_value": bool_value,
        }
        if bool_value:
            # Recordable → create one case row per injured employee, then ask the
            # human to approve the name-free 300-log description (Column F). The
            # per-employee capture chain (days / classification / injury / privacy,
            # looping case-by-case via _ir.next_case_step) resumes after approval.
            await _ir.ensure_osha_case_rows(conn, incident_id)
            review = await _emit_osha_description_review(conn, incident_id, current_user)
            if review is not None:
                review_card, review_msg_id = review
                return {
                    "event_summary": event_summary,
                    "event_extra": event_extra,
                    "next_card": review_card,
                    "next_message_id": review_msg_id,
                }
            # review is None only on a re-answer (card already pending/approved).
            # The per-case loop (days/injury/privacy) is owned by the description
            # approval handler — never start it here, so a pending review is never
            # bypassed.
            return {"event_summary": event_summary, "event_extra": event_extra}
        # Not recordable — OSHA capture is done. Hand back to the conversational
        # guidance round (root cause / clarifying questions / closure) instead of
        # jumping straight to a close button. Omitting next_card makes the accept
        # dispatcher run a normal generate_guidance round.
        return {
            "event_summary": event_summary,
            "event_extra": event_extra,
        }

    if kind == "osha_days_type_query":
        # Per-case classification (this employee's ir_osha_case_details row).
        case_key = (action.get("case_key") or "reporter").strip()
        emp_name = action.get("employee_name")
        if selected == "days_away":
            next_card = _ir.build_osha_days_count_card(
                target_field="days_away_from_work", pending_classification="days_away",
                case_key=case_key, employee_name=emp_name,
            )
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Captured: Days Away",
                "event_extra": {"field": "osha_classification_pending", "field_label": "OSHA case classification", "previous_value": None, "new_value": "days_away"},
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        if selected == "restricted_duty":
            next_card = _ir.build_osha_days_count_card(
                target_field="days_restricted_duty", pending_classification="restricted_duty",
                case_key=case_key, employee_name=emp_name,
            )
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Captured: Job Restriction",
                "event_extra": {"field": "osha_classification_pending", "field_label": "OSHA case classification", "previous_value": None, "new_value": "restricted_duty"},
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        # Neither — medical-treatment-only; set this case's classification, then
        # advance the chain (→ this case's injury-type step) via _ir.next_case_step.
        await conn.execute(
            "UPDATE ir_osha_case_details SET classification = 'medical_treatment', updated_at = NOW() "
            "WHERE incident_id = $1 AND case_key = $2",
            incident_id, case_key,
        )
        event_extra = {"field": "osha_classification", "field_label": "OSHA case classification", "previous_value": None, "new_value": "medical_treatment"}
        next_card = await _ir.next_case_step(conn, incident_id)
        if next_card is not None:
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {"event_summary": "Captured: Medical treatment only", "event_extra": event_extra, "next_card": next_card, "next_message_id": str(inserted["id"])}
        return {"event_summary": "Captured: Medical treatment only", "event_extra": event_extra}

    if kind == "privacy_case_query":
        # Per-injured-employee OSHA Privacy Case answer (Column B name masking),
        # written to this employee's ir_osha_case_details row (source of truth).
        # The chain advances to the next case (or ends) via _ir.next_case_step.
        case_key = (action.get("employee_key") or action.get("case_key") or "").strip()
        employee_name = action.get("employee_name") or "the employee"
        if not case_key:
            return {"error": "Privacy-case card is missing its employee reference."}
        await conn.execute(
            "UPDATE ir_osha_case_details SET privacy_case_reason = $1, updated_at = NOW() "
            "WHERE incident_id = $2 AND case_key = $3",
            selected, incident_id, case_key,
        )
        if selected == "none":
            summary = f"{employee_name}: not a privacy case"
            new_value = "not_privacy_case"
        else:
            summary = f"{employee_name}: privacy case — {_ir.PRIVACY_CASE_REASON_LABELS.get(selected, selected)}"
            new_value = selected
        event_extra = {
            "field": "privacy_case",
            "field_label": "OSHA privacy case",
            "previous_value": None,
            "new_value": new_value,
        }
        next_card = await _ir.next_case_step(conn, incident_id)
        if next_card is not None:
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": summary,
                "event_extra": event_extra,
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        return {"event_summary": summary, "event_extra": event_extra}

    # osha_injury_type_query — write this case's OSHA M-column injury type to its
    # ir_osha_case_details row, then advance the chain (→ this case's privacy
    # prompt, then the next injured employee) via _ir.next_case_step.
    case_key = (action.get("case_key") or "reporter").strip()
    await conn.execute(
        "UPDATE ir_osha_case_details SET injury_type = $1, updated_at = NOW() "
        "WHERE incident_id = $2 AND case_key = $3",
        selected, incident_id, case_key,
    )
    event_extra = {
        "field": "osha_case_injury_type",
        "field_label": "OSHA injury type",
        "previous_value": None,
        "new_value": selected,
    }
    summary = f"Captured injury type: {_ir.OSHA_INJURY_TYPE_LABELS[selected]}"
    next_card = await _ir.next_case_step(conn, incident_id)
    if next_card is not None:
        inserted = await _emit_chain_card(
            conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
        )
        return {
            "event_summary": summary,
            "event_extra": event_extra,
            "next_card": next_card,
            "next_message_id": str(inserted["id"]),
        }
    return {"event_summary": summary, "event_extra": event_extra}


async def _handle_numeric_input(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Validate and persist a numeric_input card.

    Writes ``action.target_field`` (must be days_away_from_work or
    days_restricted_duty) and sets ``osha_classification`` to the carried
    ``pending_classification`` so the 300-log filter picks it up. Emits the
    injury-type picker as the next chain card.
    """
    target = (action.get("target_field") or "").strip()
    pending_classification = (action.get("pending_classification") or "").strip()
    allowed_targets = {"days_away_from_work", "days_restricted_duty"}
    if target not in allowed_targets:
        return {"error": f"Invalid target_field: {target}"}
    if pending_classification not in {"days_away", "restricted_duty"}:
        return {"error": f"Invalid pending_classification: {pending_classification}"}

    if body.numeric_value is None:
        return {"error": "Enter a number of days."}
    days = int(body.numeric_value)
    lo = int(action.get("input_min") or 1)
    hi = int(action.get("input_max") or 365)
    if days < lo or days > hi:
        return {"error": f"Days must be between {lo} and {hi}."}

    # Per-case day count + classification (this employee's case row). case_col
    # is whitelisted via `target` above, so the format is injection-safe.
    case_key = (action.get("case_key") or "reporter").strip()
    case_col = "days_away" if target == "days_away_from_work" else "days_restricted"
    await conn.execute(
        f"UPDATE ir_osha_case_details SET {case_col} = $1, classification = $2, "
        "updated_at = NOW() WHERE incident_id = $3 AND case_key = $4",
        days, pending_classification, incident_id, case_key,
    )
    field_label = "Days away from work" if target == "days_away_from_work" else "Days on job restriction"
    event_extra = {"field": target, "field_label": field_label, "previous_value": None, "new_value": days}
    summary = f"Captured: {field_label} = {days}"
    next_card = await _ir.next_case_step(conn, incident_id)
    if next_card is not None:
        inserted = await _emit_chain_card(
            conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
        )
        return {"event_summary": summary, "event_extra": event_extra, "next_card": next_card, "next_message_id": str(inserted["id"])}
    return {"event_summary": summary, "event_extra": event_extra}


async def _handle_text_input(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Persist one root-cause interview answer and emit the next chain step.

    ``action.target_field`` carries the step name (hazard / why / prevention).
    Each answer lands in ``ir_incidents.category_data->'root_cause_interview'->>step``
    (JSONB). After the third step we compose all three into the existing
    ``root_cause`` TEXT column so the OSHA 301 printable form, broker readers,
    and the AI Analysis tab see a populated value.
    """
    step = (action.get("target_field") or "").strip()

    # OSHA 300 Description (Column F) — human approves/edits the name-free verbiage
    # before it prints. Writes the canonical category_data.osha_clean_description
    # (the field the 300 log reads) + the approval gate, then resumes the
    # per-employee capture loop (days/injury/privacy).
    if step == "osha_clean_description":
        approved = (body.text_value or "").strip()
        if not approved:
            return {"error": "Add a description before approving — it must name no one."}
        approved = approved[:2000]
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                jsonb_set(
                    COALESCE(category_data, '{}'::jsonb),
                    '{osha_clean_description}',
                    to_jsonb($1::text),
                    true
                ),
                '{osha_description_approved}',
                'true'::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            approved, incident_id,
        )
        event_extra = {
            "field": "osha_clean_description",
            "field_label": "OSHA 300 description",
            "previous_value": None,
            "new_value": approved,
        }
        next_card = await _ir.next_case_step(conn, incident_id)
        if next_card is not None:
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "OSHA 300 description approved",
                "event_extra": event_extra,
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        return {"event_summary": "OSHA 300 description approved", "event_extra": event_extra}

    # Investigation findings — free-text documentation capture (not part of the
    # root-cause interview chain). Writes category_data.investigation_notes and
    # stamps investigation_documented so the deterministic flow advances.
    if step == "investigation_notes":
        raw = (body.text_value or "").strip()
        if not raw:
            return {"error": "Add your findings before saving (or Skip if there's nothing to add)."}
        notes = raw[:4000]
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                jsonb_set(
                    COALESCE(category_data, '{}'::jsonb),
                    '{investigation_notes}',
                    to_jsonb($1::text),
                    true
                ),
                '{investigation_documented}',
                'true'::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            notes, incident_id,
        )
        return {
            "event_summary": "Investigation findings documented",
            "event_extra": {
                "field": "investigation_notes",
                "field_label": "Investigation notes",
                "previous_value": None,
                "new_value": notes,
            },
        }

    if step not in _ir.ROOT_CAUSE_INTERVIEW_STEPS:
        return {"error": f"Invalid text_input target_field: {step}"}

    raw = body.text_value or ""
    answer = raw.strip()
    if not answer:
        return {"error": "Answer can't be empty. Type your response and Save."}
    if len(answer) > 4000:
        answer = answer[:4000]

    # Postgres jsonb_set does NOT auto-create intermediate object keys —
    # for a fresh incident with category_data='{}', writing the nested
    # path ['root_cause_interview', step] in one call silently returns
    # the original unchanged. Two-step: ensure the parent key exists as
    # an object, then write the leaf.
    await conn.execute(
        """
        UPDATE ir_incidents
        SET category_data = jsonb_set(
            jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{root_cause_interview}',
                COALESCE(category_data->'root_cause_interview', '{}'::jsonb),
                true
            ),
            ARRAY['root_cause_interview', $1],
            to_jsonb($2::text),
            true
        ),
        updated_at = NOW()
        WHERE id = $3
        """,
        step, answer, incident_id,
    )

    step_idx = _ir.ROOT_CAUSE_INTERVIEW_STEPS.index(step)
    event_summary = f"Captured root cause — {step}"
    event_extra = {
        "field": f"root_cause_interview.{step}",
        "field_label": f"Root cause · {step}",
        "previous_value": None,
        "new_value": answer,
    }

    if step_idx + 1 < len(_ir.ROOT_CAUSE_INTERVIEW_STEPS):
        next_step = _ir.ROOT_CAUSE_INTERVIEW_STEPS[step_idx + 1]
        next_card = _ir.build_root_cause_text_card(step=next_step)
        inserted = await _emit_chain_card(
            conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
        )
        return {
            "event_summary": event_summary,
            "event_extra": event_extra,
            "next_card": next_card,
            "next_message_id": str(inserted["id"]),
        }

    # Final step — compose the combined text and write to root_cause column.
    # If the incident is OSHA-flagged (severity=critical or emergency-alert
    # markers in category_data) and the recordable chain hasn't started,
    # emit osha_recordable_query as next_card so the deterministic chain
    # takes over from here. Otherwise leave next_card unset so the
    # post-dispatch flow runs a normal AI guidance round.
    row = await conn.fetchrow(
        "SELECT category_data FROM ir_incidents WHERE id = $1",
        incident_id,
    )
    cd = _ir._safe_json_loads(row["category_data"] if row else None, {}) or {}
    interview = cd.get("root_cause_interview") or {}
    combined = _ir.compose_root_cause_text(interview)
    await conn.execute(
        "UPDATE ir_incidents SET root_cause = $1, updated_at = NOW() WHERE id = $2",
        combined, incident_id,
    )
    event_extra = {
        "field": "root_cause",
        "field_label": "Root cause",
        "previous_value": None,
        "new_value": combined,
    }
    if await _should_emit_osha_recordable_chain(conn, incident_id):
        chain_card, chain_message_id = await _emit_osha_recordable_chain(
            conn, incident_id=incident_id, current_user=current_user,
        )
        return {
            "event_summary": "Root cause logged",
            "event_extra": event_extra,
            "next_card": chain_card,
            "next_message_id": chain_message_id,
        }
    return {
        "event_summary": "Root cause logged",
        "event_extra": event_extra,
    }


def _build_recommendations_corrective_card(recs) -> Optional[dict]:
    """Turn a RecommendationsAnalysis into a pre-filled corrective_actions card.

    The run_analysis:recommendations path generates corrective actions and
    caches them to ir_incident_analysis, but the content otherwise never
    reaches the copilot conversation — the user just saw a "review them" note
    with nothing to review. This surfaces the actual recommendations in the
    card's *visible* recommendation text (the frontend renders
    ``recommendation``/``rationale``, not ``field_value``) and pre-fills
    field_value so accepting writes them to ir_incidents.corrective_actions.
    Returns None when there's nothing to recommend.
    """
    items = getattr(recs, "recommendations", None) or []
    actions: list[str] = []
    for it in items:
        action = (getattr(it, "action", None) or "").strip()
        if action:
            prio = (getattr(it, "priority", None) or "").strip()
            actions.append(f"{action} ({prio} priority)" if prio else action)
    summary = (getattr(recs, "summary", None) or "").strip()
    if not actions and not summary:
        return None

    # Visible card text: the card body renders `recommendation` as a single
    # paragraph, so number the actions inline rather than as line breaks.
    numbered = "  ".join(f"({i}) {a}" for i, a in enumerate(actions, 1))
    shown = " ".join(p for p in (summary, numbered) if p).strip()[:900]

    # Saved value: newline-separated for clean storage / report rendering.
    saved_lines = ([summary] if summary else []) + [f"• {a}" for a in actions]
    field_value = "\n".join(saved_lines).strip()[:1800] or shown

    return {
        "id": "recommendations_corrective_actions",
        "title": "Recommended corrective actions",
        "recommendation": shown or "Apply the recommended corrective actions.",
        "rationale": "Accept to save these to the incident record, or skip to refine.",
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "set_field",
            "label": "Save corrective actions",
            "field_name": "corrective_actions",
            "field_value": field_value,
        },
    }


# Trailing "(<priority> priority)" tag that _build_recommendations_corrective_card
# appends to each bullet — parsed back out so the seeded structured rows keep the
# AI's priority instead of defaulting.
_ACTION_PRIORITY_RE = re.compile(r"\s*\((immediate|short_term|long_term)\s+priority\)\s*$", re.I)


def _parse_action_bullets(field_value) -> list[tuple[str, str]]:
    """Parse the "• action (priority)" bullets the recommendations card produced
    into (description, priority) pairs. Pure — unit-tested.

    Non-bullet lines (e.g. the leading summary paragraph) are skipped; a bullet
    with no recognized priority tag defaults to 'short_term'.
    """
    out: list[tuple[str, str]] = []
    for raw_line in str(field_value or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("•"):
            continue
        body = line.lstrip("•").strip()
        priority = "short_term"
        m = _ACTION_PRIORITY_RE.search(body)
        if m:
            priority = m.group(1).lower()
            body = _ACTION_PRIORITY_RE.sub("", body).strip()
        if body:
            out.append((body[:2000], priority))
    return out


async def _seed_structured_corrective_actions(conn, incident_id, company_id, user_id, field_value) -> int:
    """Materialize the AI's recommended corrective actions as tracked CAPA rows.

    Bridges the free-text recommendations card (which only ever wrote the
    ir_incidents.corrective_actions notes blob) into structured, owner/due-date/
    status-tracked ir_corrective_actions rows — one per bulleted action. The text
    write still happens (back-compat); this is additive.

    Deterministic-parse of the "• action (priority)" bullets the card builder
    produced. Idempotent-ish: skips seeding if this incident already has any
    corrective-action row, so re-accepting (or a manual add first) won't duplicate.
    """
    if not company_id or not field_value:
        return 0
    existing = await conn.fetchval(
        "SELECT COUNT(*) FROM ir_corrective_actions WHERE incident_id = $1", incident_id
    )
    if existing:
        return 0
    seeded = 0
    for body, priority in _parse_action_bullets(field_value):
        await conn.execute(
            """
            INSERT INTO ir_corrective_actions
                (incident_id, company_id, description, action_type, priority, created_by)
            VALUES ($1, $2, $3, 'corrective', $4, $5)
            """,
            incident_id, str(company_id), body, priority,
            str(user_id) if user_id else None,
        )
        seeded += 1
    return seeded
