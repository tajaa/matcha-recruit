"""Which abilities a person has switched on (`mw_agent_ability_grants`)."""
from __future__ import annotations

import json
import re
from uuid import UUID

from fastapi import HTTPException

from app.database import connection_or_direct, decode_jsonb

from . import consent

_PHONE = re.compile(r"^[0-9+()\-. ]{7,24}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_settings(ability_key: str, settings: dict | None) -> dict:
    """The settings an ability may hold, validated. Unknown keys are dropped."""
    settings = settings if isinstance(settings, dict) else {}
    if ability_key != "reservations":
        return {}
    contact = settings.get("contact") if isinstance(settings.get("contact"), dict) else {}
    name = str(contact.get("name") or "").strip()[:80]
    phone = str(contact.get("phone") or "").strip()[:24]
    email = str(contact.get("email") or "").strip()[:160]
    if not name:
        raise HTTPException(status_code=422, detail="A name to book under is required.")
    if phone and not _PHONE.match(phone):
        raise HTTPException(status_code=422, detail="That phone number doesn't look right.")
    if email and not _EMAIL.match(email):
        raise HTTPException(status_code=422, detail="That email address doesn't look right.")
    if not phone and not email:
        raise HTTPException(status_code=422, detail="Add a phone number or an email for the booking.")
    return {"contact": {"name": name, "phone": phone, "email": email}}


def is_active(row: dict | None, ability_key: str) -> bool:
    """A grant counts only while enabled and agreed to at the current version."""
    if not row or not row.get("enabled"):
        return False
    return row.get("consent_version") == consent.current_version(ability_key)


async def load_grants(conn, user_id: UUID) -> dict[str, dict]:
    """`{ability_key: settings}` for every grant that is active right now."""
    rows = await conn.fetch(
        """SELECT ability_key, enabled, consent_version, settings
           FROM mw_agent_ability_grants WHERE user_id = $1""",
        user_id,
    )
    active: dict[str, dict] = {}
    for row in rows:
        if is_active(dict(row), row["ability_key"]):
            active[row["ability_key"]] = decode_jsonb(row["settings"], {}) or {}
    return active


async def list_rows(user_id: UUID) -> dict[str, dict]:
    async with connection_or_direct() as conn:
        rows = await conn.fetch(
            """SELECT ability_key, enabled, consent_version, consented_at, settings
               FROM mw_agent_ability_grants WHERE user_id = $1""",
            user_id,
        )
    return {
        row["ability_key"]: {**dict(row), "settings": decode_jsonb(row["settings"], {}) or {}}
        for row in rows
    }


async def enable(
    user_id: UUID,
    company_id: UUID,
    ability_key: str,
    *,
    consent_version: str | None,
    settings: dict | None = None,
) -> dict:
    required = consent.current_version(ability_key)
    if required is not None and consent_version != required:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "consent_required",
                "message": "Read and accept what this ability does first.",
                "disclosure": consent.disclosure_view(ability_key),
            },
        )
    cleaned = clean_settings(ability_key, settings)
    async with connection_or_direct() as conn:
        await conn.execute(
            """INSERT INTO mw_agent_ability_grants
                   (user_id, company_id, ability_key, enabled, consent_version, consented_at, settings)
               VALUES ($1, $2, $3, TRUE, $4, CASE WHEN $4::text IS NULL THEN NULL ELSE NOW() END, $5::jsonb)
               ON CONFLICT (user_id, ability_key) DO UPDATE
                   SET enabled = TRUE, company_id = EXCLUDED.company_id,
                       consent_version = EXCLUDED.consent_version,
                       consented_at = EXCLUDED.consented_at,
                       settings = EXCLUDED.settings, updated_at = NOW()""",
            user_id, company_id, ability_key, required, json.dumps(cleaned),
        )
    return {"key": ability_key, "enabled": True, "settings": cleaned}


async def disable(user_id: UUID, ability_key: str) -> dict:
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_ability_grants SET enabled = FALSE, updated_at = NOW()
               WHERE user_id = $1 AND ability_key = $2""",
            user_id, ability_key,
        )
    return {"key": ability_key, "enabled": False}
