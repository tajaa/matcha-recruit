"""The Espresso assistant's REST side.

The conversation itself runs over the channel socket (`werk/routes/channels_ws.py`
hands every message in a private conversation to
`services/matcha_work/agent_runtime/chat_entry`). These routes are the rest:
open the private conversation, read a run and its steps, and switch abilities
on and off.

The whole router is for personal Espresso accounts only
(`agent_runtime.eligibility`); there is no company flag. Plan limits apply on
top, in `enqueue.preflight`.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import decode_jsonb, get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.matcha_work.assistant import AbilityEnableRequest
from app.matcha.services.matcha_work.agent_runtime import (
    assistant as assistant_run,
    catalog,
    consent,
    conversation,
    enqueue,
    grants,
    result,
)
from app.matcha.services.matcha_work.gmail_service import GmailService

async def require_personal_workspace(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None or not await enqueue.workspace_enabled(company_id):
        raise HTTPException(status_code=403, detail={
            "code": "feature_disabled",
            "message": "The Espresso assistant comes with a personal Espresso account.",
        })
    return current_user


router = APIRouter(
    prefix="/assistant",
    dependencies=[Depends(require_personal_workspace)],
)


def _iso(value):
    return value.isoformat() if value is not None else None


async def _company(current_user: CurrentUser) -> UUID:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No workspace is selected.")
    return company_id


async def _no_fetch(_url: str):  # the catalog is only being listed here
    return {}, set()


def _ability(key: str):
    for ability in catalog.build_catalog(fetch_page=_no_fetch):
        if ability.key == key:
            return ability
    raise HTTPException(status_code=404, detail="No such ability.")


@router.post("/channel")
async def ensure_assistant_channel(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """The caller's private conversation with Espresso, created on first use."""
    company_id = await _company(current_user)
    async with get_connection() as conn:
        channel_id = await conversation.ensure_assistant_channel(
            conn, user_id=current_user.id, company_id=company_id,
        )
    return {"channel_id": str(channel_id)}


@router.get("/runs/{run_id}")
async def get_assistant_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """One of the caller's own runs, with its steps. Nobody else's: a run in a
    private conversation can hold what was read from email."""
    async with get_connection() as conn:
        run = await conn.fetchrow(
            """SELECT id, status, surface, abilities, result, error, model_calls, search_calls,
                      created_at, started_at, completed_at
               FROM mw_project_agent_runs
               WHERE id = $1 AND kind = 'assistant' AND requested_by = $2""",
            run_id, current_user.id,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        steps = await conn.fetch(
            """SELECT seq, kind, label, status, created_at
               FROM mw_project_agent_steps WHERE run_id = $1 ORDER BY seq""",
            run_id,
        )
    return {
        "id": str(run["id"]),
        "status": run["status"],
        "surface": run["surface"],
        "abilities": list(run["abilities"] or []),
        "result": result.read_result(decode_jsonb(run["result"], None)),
        "error": run["error"],
        "model_calls": run["model_calls"],
        "search_calls": run["search_calls"],
        "created_at": _iso(run["created_at"]),
        "started_at": _iso(run["started_at"]),
        "completed_at": _iso(run["completed_at"]),
        "steps": [
            {"seq": s["seq"], "kind": s["kind"], "label": s["label"], "status": s["status"],
             "created_at": _iso(s["created_at"])}
            for s in steps
        ],
    }


@router.get("/abilities")
async def list_abilities(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Every ability, whether the caller has it switched on, and what stands in
    the way if it cannot be used yet. Availability is given for the private
    conversation, which is where the acting abilities run."""
    rows = await grants.list_rows(current_user.id)
    active = {key: row["settings"] for key, row in rows.items() if grants.is_active(row, key)}
    gmail = GmailService(current_user.id)
    await gmail.load_token()
    situation = catalog.Situation(
        private=True, grants=active,
        google_connected=gmail.is_configured, granted_scopes=gmail.granted_scopes,
        allowed=catalog.allowances_for(current_user),
    )
    abilities = []
    for ability in catalog.build_catalog(fetch_page=_no_fetch):
        if not catalog.offered(ability, situation):
            continue  # not offered to this account: not listed either
        state = catalog.availability(ability, situation)
        row = rows.get(ability.key)
        abilities.append({
            "key": ability.key,
            "label": ability.label,
            "always_on": ability.consent_version is None,
            "enabled": ability.consent_version is None or ability.key in active,
            "available": state.available,
            "reason": state.reason,
            "needs_consent": state.needs_consent,
            "needs_connection": state.needs_connection,
            "missing_scopes": list(state.missing_scopes),
            "private_only": ability.private_only,
            "acts": any(tool.effect == "commit" for tool in ability.tools),
            "disclosure": consent.disclosure_view(ability.key),
            # Re-consent: they agreed to an older disclosure than the current one.
            "consent_outdated": bool(row and row["enabled"] and ability.key not in active),
            "settings": (row or {}).get("settings") or {},
        })
    return {
        "abilities": abilities,
        "google": {"connected": gmail.is_configured, "scopes": sorted(gmail.granted_scopes)},
        "commit_mode": assistant_run.commit_mode(),
    }


@router.put("/abilities/{key}")
async def enable_ability(
    key: str,
    body: AbilityEnableRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    ability = _ability(key)
    # Not offered to this account: as if it did not exist, the same as the listing.
    if not catalog.offered(ability, catalog.Situation(private=True, allowed=catalog.allowances_for(current_user))):
        raise HTTPException(status_code=404, detail="No such ability.")
    if ability.consent_version is None:
        raise HTTPException(status_code=400, detail="That ability is always on.")
    company_id = await _company(current_user)
    return await grants.enable(
        current_user.id, company_id, key,
        consent_version=body.consent_version, settings=body.settings,
    )


@router.delete("/abilities/{key}")
async def disable_ability(
    key: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    ability = _ability(key)
    if ability.consent_version is None:
        raise HTTPException(status_code=400, detail="That ability is always on.")
    return await grants.disable(current_user.id, key)
