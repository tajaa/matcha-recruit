"""Meta's two unauthenticated entry points: the OAuth callback and the webhook.

The callback is a browser redirect, so what ties it to a site is the signed
state (`services/social/oauth.py`), never a bearer. The webhook is verified
with the app secret's HMAC over the raw body; its events are handed to the
worker (`cappe_social_inbound`) and the request returns 200 at once — Meta
retries and eventually disables a subscription that keeps failing.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...services.email import dashboard_url
from ...services.social import connections as conn_store
from ...services.social import oauth
from ...services.social.providers import meta
from ...services.social.providers.base import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_WEBHOOK_BYTES = 256 * 1024
_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _back(site_id, **params) -> RedirectResponse:
    """Back to the Social page, the one-time nonce cookie spent."""
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    response = RedirectResponse(url=f"{dashboard_url(f'/sites/{site_id}/social')}?{query}",
                                status_code=status.HTTP_302_FOUND, headers=_NO_STORE)
    response.delete_cookie(oauth.NONCE_COOKIE, path=oauth.NONCE_COOKIE_PATH, secure=True, httponly=True, samesite="lax")
    return response


@router.get("/public/social/meta/callback")
async def meta_callback(request: Request):
    """Meta sends the browser here with `code` + `state` (or `error`)."""
    await check_rate_limit(client_ip(request), "cappe_social_oauth", 20, 60)
    params = request.query_params
    state = oauth.read_state(params.get("state"), nonce_cookie=request.cookies.get(oauth.NONCE_COOKIE))
    if state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This connect link has expired or was started in another browser — start again")
    site_id, account_id = state["site_id"], state["account_id"]
    if params.get("error"):
        return _back(site_id, social_error=params.get("error_description") or params.get("error"))
    code = params.get("code")
    cfg = meta.MetaConfig.from_settings()
    if not code or cfg is None:
        return _back(site_id, social_error="Instagram and Facebook aren't set up on this server yet")

    from ...routes.social import oauth_redirect_uri

    try:
        drafts = await meta.exchange_code(cfg, code, redirect_uri=oauth_redirect_uri())
    except ProviderError as exc:
        logger.warning("cappe social: meta code exchange failed: %s", exc)
        return _back(site_id, social_error=str(exc))
    if not drafts:
        return _back(site_id, social_error="No Facebook Page was shared. Pick at least one Page (with its Instagram account) when connecting.")

    async with get_connection() as conn:
        site = await conn.fetchrow("SELECT id FROM cappe_sites WHERE id = $1 AND account_id = $2", site_id, account_id)
        if site is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
        rows = await conn_store.save_drafts(conn, site_id=site_id, account_id=account_id, drafts=drafts)
    for draft in drafts:
        if draft.platform == "facebook":
            await meta.subscribe_page(cfg, draft.external_id, draft.access_token)
    return _back(site_id, connected=",".join(sorted({r["platform"] for r in rows})))


@router.get("/public/social/meta/webhook")
async def meta_webhook_verify(request: Request):
    cfg = meta.MetaConfig.from_settings()
    challenge = meta.verify_challenge(cfg, dict(request.query_params)) if cfg else None
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")
    return PlainTextResponse(challenge)


@router.post("/public/social/meta/webhook")
async def meta_webhook(request: Request):
    cfg = meta.MetaConfig.from_settings()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Not configured")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Too large")
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Too large")
    if not meta.verify_signature(cfg.app_secret, body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad signature")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad JSON")
    events = meta.parse_webhook(payload if isinstance(payload, dict) else {})
    if events:
        try:
            from app.workers.tasks.cappe_social_inbound import run_cappe_social_inbound

            run_cappe_social_inbound.delay([e.as_dict() for e in events])
        except Exception:  # noqa: BLE001 — a dead broker must not make Meta disable the subscription
            logger.exception("cappe social: could not enqueue %d inbound events", len(events))
    return JSONResponse({"received": len(events)}, headers=_NO_STORE)


__all__ = ["router", "MAX_WEBHOOK_BYTES"]
