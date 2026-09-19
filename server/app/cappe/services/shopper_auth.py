"""Passwordless, site-bound shopper identity and rotating refresh sessions."""
import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.config import get_settings
from app.core.services.scoped_auth import is_token_revoked, make_token_helpers
from app.core.services.session_tokens import SessionLifetimes
from app.cappe.models.shopper import Shopper
from app.cappe.services.entitlements import resolve_entitlements


def token_helpers():
    settings = get_settings()
    return make_token_helpers(
        "cappe_shopper",
        lifetimes=SessionLifetimes(settings.cappe_shopper_refresh_idle_days * 1440,
                                  settings.cappe_shopper_refresh_absolute_days * 1440),
        extra_claims_keys=("site_id", "sid", "nonce"),
    )


async def published_shopper_site(conn, slug):
    site = await conn.fetchrow(
        "SELECT s.*, a.plan AS owner_plan FROM cappe_sites s "
        "JOIN cappe_accounts a ON a.id=s.account_id "
        "WHERE s.slug=$1 AND s.status='published' AND a.status='active'", slug,
    )
    if not site:
        raise HTTPException(404, "Site not found")
    ent = await resolve_entitlements(site["owner_plan"], conn=conn)
    if not ent.has("shopper_accounts"):
        raise HTTPException(402, "Shopper accounts are not enabled for this store")
    return site


def code_hash(site_id, email, code):
    return hmac.new(get_settings().jwt_secret_key.encode(),
                    f"cappe_shopper|{site_id}|{email}|{code}".encode(), hashlib.sha256).hexdigest()


async def lock_email(conn, site_id, email):
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"shopper:{site_id}:{email}")


async def issue_login_code(conn, *, site, email):
    email = email.strip().lower()
    code = f"{secrets.randbelow(1000000):06d}"
    async with conn.transaction():
        await lock_email(conn, site["id"], email)
        await conn.execute(
            "UPDATE cappe_shopper_login_codes SET consumed_at=NOW() "
            "WHERE site_id=$1 AND email=$2 AND consumed_at IS NULL", site["id"], email,
        )
        await conn.execute(
            "INSERT INTO cappe_shopper_login_codes(site_id,email,code_hash,expires_at) "
            "VALUES($1,$2,$3,NOW()+interval '10 minutes')",
            site["id"], email, code_hash(site["id"], email, code),
        )
    return code


async def verify_login_code(conn, *, site, email, code):
    email = email.strip().lower()
    async with conn.transaction():
        await lock_email(conn, site["id"], email)
        row = await conn.fetchrow(
            "SELECT *, expires_at > NOW() AS valid FROM cappe_shopper_login_codes "
            "WHERE site_id=$1 AND email=$2 ORDER BY created_at DESC, id DESC LIMIT 1 FOR UPDATE",
            site["id"], email,
        )
        if not row or row["consumed_at"] or not row["valid"] or row["attempts"] >= 5:
            return None
        await conn.execute("UPDATE cappe_shopper_login_codes SET attempts=attempts+1 WHERE id=$1", row["id"])
        if not hmac.compare_digest(row["code_hash"], code_hash(site["id"], email, code)):
            return None  # Return, don't raise: failed attempts must commit.
        await conn.execute("UPDATE cappe_shopper_login_codes SET consumed_at=NOW() WHERE id=$1", row["id"])
        shopper = await conn.fetchrow(
            "INSERT INTO cappe_shoppers(site_id,email,last_login_at) VALUES($1,$2,NOW()) "
            "ON CONFLICT(site_id,email) DO UPDATE SET last_login_at=NOW(),updated_at=NOW() RETURNING *",
            site["id"], email,
        )
        await conn.execute(
            "UPDATE cappe_orders SET shopper_id=$1 WHERE site_id=$2 "
            "AND lower(customer_email)=$3 AND shopper_id IS NULL", shopper["id"], site["id"], email,
        )
        return await issue_session(conn, shopper)


def refresh_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_session(conn, shopper, *, sid=None, started=None):
    sid = sid or uuid4()
    helpers = token_helpers()
    claims = {"site_id": str(shopper["site_id"]), "sid": str(sid), "nonce": secrets.token_hex(16)}
    access = helpers.create_access_token(shopper["id"], shopper["email"], extra_claims=claims)
    refresh = helpers.create_refresh_token(shopper["id"], shopper["email"], started, extra_claims=claims)
    payload = helpers.decode_token(refresh, "refresh")
    await conn.execute(
        "INSERT INTO cappe_shopper_sessions(id,shopper_id,refresh_hash,expires_at) "
        "VALUES($1,$2,$3,to_timestamp($4)) ON CONFLICT(id) DO UPDATE SET "
        "refresh_hash=EXCLUDED.refresh_hash,expires_at=EXCLUDED.expires_at",
        sid, shopper["id"], refresh_hash(refresh), payload["exp"],
    )
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": 900, "shopper": Shopper.model_validate(dict(shopper)).model_dump(mode="json")}


async def resolve_shopper(conn, site, token, kind="access", *, lock=False):
    payload = token_helpers().decode_token(token, kind)
    try:
        if not payload or UUID(payload["site_id"]) != site["id"]:
            raise ValueError()
        shopper_id, sid = UUID(payload["sub"]), UUID(payload["sid"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(401, "Invalid shopper session") from None
    # Lock shopper first in every mutation, including refresh, logout and delete.
    row = await conn.fetchrow(
        "SELECT * FROM cappe_shoppers WHERE id=$1 AND site_id=$2" + (" FOR UPDATE" if lock else ""),
        shopper_id, site["id"],
    )
    if not row or is_token_revoked(payload.get("iat"), row["tokens_valid_after"], payload.get("iat_ms")):
        raise HTTPException(401, "Shopper session revoked")
    session = await conn.fetchrow(
        "SELECT refresh_hash FROM cappe_shopper_sessions WHERE id=$1 AND shopper_id=$2 AND expires_at>NOW()",
        sid, shopper_id,
    )
    if not session or (kind == "refresh" and not hmac.compare_digest(session["refresh_hash"], refresh_hash(token))):
        raise HTTPException(401, "Shopper session expired")
    return row, payload
