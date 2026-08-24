"""Offer minting and claim lifecycle for approved shoutout mentions."""
import secrets
from datetime import datetime, timezone
from uuid import UUID

from ....config import get_settings
from ..email import tellus_web_url
from .. import promo_service

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class OfferError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def _short_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _serialize(row: dict) -> dict:
    return {
        **row,
        "claim_url": tellus_web_url(f"/o/{row['offer_token']}"),
    }


async def mint_offer(
    conn, *, brand_id: UUID, store_id: UUID, mention_id: UUID, title: str,
    terms: str | None, expiry_days: int, client_request_id: UUID, created_by: UUID,
) -> dict:
    """Mint one store-bound promo campaign and offer inside the caller transaction."""
    existing = await conn.fetchrow(
        """SELECT o.*, s.name AS store_name
             FROM tellus_shoutout_offers o LEFT JOIN tellus_stores s ON s.id = o.store_id
            WHERE o.brand_id = $1 AND o.client_request_id = $2""",
        brand_id, client_request_id,
    )
    if existing is not None:
        return _serialize(dict(existing))
    mention = await conn.fetchrow(
        """SELECT id, status FROM tellus_shoutout_mentions
            WHERE id = $1 AND brand_id = $2 FOR UPDATE""", mention_id, brand_id,
    )
    if mention is None:
        raise OfferError(404, "not_found", "Shoutout mention not found.")
    existing = await conn.fetchrow(
        """SELECT o.*, s.name AS store_name FROM tellus_shoutout_offers o
             LEFT JOIN tellus_stores s ON s.id = o.store_id
            WHERE o.brand_id = $1 AND o.client_request_id = $2""",
        brand_id, client_request_id,
    )
    if existing is not None:
        return _serialize(dict(existing))
    if mention["status"] != "pending":
        raise OfferError(409, "already_decided", "This shoutout mention was already decided.")
    store = await conn.fetchrow(
        "SELECT id, name FROM tellus_stores WHERE id = $1 AND brand_id = $2", store_id, brand_id,
    )
    if store is None:
        raise OfferError(404, "store_not_found", "Choose one of your stores for this offer.")
    campaign_token = secrets.token_urlsafe(12)
    campaign = await conn.fetchrow(
        """INSERT INTO tellus_promo_campaigns
               (brand_id, title, reward_text, claim_token, max_claims, card_expiry_days,
                ends_at, campaign_type, store_id)
           VALUES ($1,$2,$3,$4,1,$5,NOW()+make_interval(days => $5),'shoutout',$6)
           RETURNING id, claim_token""",
        brand_id, title, title, campaign_token, expiry_days, store_id,
    )
    offer_token = secrets.token_urlsafe(12)
    offer = await conn.fetchrow(
        """INSERT INTO tellus_shoutout_offers
               (brand_id, mention_id, campaign_id, store_id, offer_token, short_code,
                reward_text, offer_terms, claim_expires_at, created_by, client_request_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW()+make_interval(days => $9),$10,$11)
           RETURNING *""",
        brand_id, mention_id, campaign["id"], store_id, offer_token, _short_code(),
        title, terms, expiry_days, created_by, client_request_id,
    )
    await conn.execute(
        """UPDATE tellus_shoutout_mentions SET status='approved', decided_at=NOW(), decided_by=$2,
               offer_id=$3, offer_store_id=$4 WHERE id=$1""",
        mention_id, created_by, offer["id"], store_id,
    )
    result = dict(offer)
    result["store_name"] = store["name"]
    return _serialize(result)


async def list_offers(conn, brand_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """SELECT o.*, s.name AS store_name FROM tellus_shoutout_offers o
           LEFT JOIN tellus_stores s ON s.id=o.store_id
           WHERE o.brand_id=$1 ORDER BY o.created_at DESC""", brand_id,
    )
    return [_serialize(dict(row)) for row in rows]


async def revoke_offer(conn, brand_id: UUID, offer_id: UUID) -> None:
    async with conn.transaction():
        offer = await conn.fetchrow(
            """SELECT id, campaign_id, status FROM tellus_shoutout_offers
                WHERE id=$1 AND brand_id=$2 FOR UPDATE""", offer_id, brand_id,
        )
        if offer is None:
            raise OfferError(404, "not_found", "Offer not found.")
        if offer["status"] == "revoked":
            return
        try:
            await promo_service.cancel_campaign(conn, brand_id, offer["campaign_id"])
        except promo_service.PromoError as error:
            raise OfferError(error.http_status, error.code, error.message, error.extra)
        await conn.execute("UPDATE tellus_shoutout_offers SET status='revoked' WHERE id=$1", offer_id)


async def _load_offer(conn, *, token: str | None = None, short_code: str | None = None) -> dict:
    if bool(token) == bool(short_code):
        raise OfferError(404, "not_found", "This offer link is not available.")
    row = await conn.fetchrow(
        """SELECT o.*, o.created_at AS offer_created_at, s.name AS store_name, c.status AS campaign_status,
                  c.claim_token, c.starts_at, c.ends_at, c.claim_count, c.max_claims,
                  b.name AS brand_name, b.logo_url AS brand_logo_url, b.plan_status,
                  cfg.require_app_install
             FROM tellus_shoutout_offers o
             JOIN tellus_promo_campaigns c ON c.id=o.campaign_id
             JOIN tellus_brands b ON b.id=o.brand_id
             LEFT JOIN tellus_shoutout_configs cfg ON cfg.brand_id=o.brand_id
             LEFT JOIN tellus_stores s ON s.id=o.store_id
            WHERE (($1::text IS NOT NULL AND o.offer_token=$1) OR ($2::text IS NOT NULL AND o.short_code=$2))""",
        token, short_code,
    )
    if row is None:
        raise OfferError(404, "not_found", "This offer link is not available.")
    return dict(row)


def _offer_available(offer: dict) -> bool:
    return (
        offer["status"] in {"sent", "claimed"}
        and promo_service.claim_reason({
            "status": offer["campaign_status"], "starts_at": offer["starts_at"],
            "ends_at": offer["ends_at"], "claim_count": offer["claim_count"],
            "max_claims": offer["max_claims"], "plan_status": offer["plan_status"],
        }) == "ok"
        and offer["claim_expires_at"] > datetime.now(timezone.utc)
    )


async def preview_offer(
    conn, *, token: str | None = None, short_code: str | None = None, account_id: UUID | None,
) -> dict:
    offer = await _load_offer(conn, token=token, short_code=short_code)
    existing = None
    web_claim_allowed = not bool(offer.get("require_app_install"))
    if account_id:
        existing = await conn.fetchrow(
            "SELECT card_token FROM tellus_promo_cards WHERE campaign_id=$1 AND account_id=$2",
            offer["campaign_id"], account_id,
        )
        if offer.get("require_app_install"):
            web_claim_allowed = bool(await conn.fetchval(
                "SELECT created_at <= $2 FROM tellus_accounts WHERE id=$1", account_id, offer["offer_created_at"],
            ))
    return {
        "brand_name": offer["brand_name"], "brand_logo_url": offer["brand_logo_url"],
        "store_name": offer["store_name"], "reward_text": offer["reward_text"],
        "offer_terms": offer.get("offer_terms"), "short_code": offer["short_code"],
        "claim_expires_at": offer["claim_expires_at"],
        "require_app_install": bool(offer.get("require_app_install")),
        "web_claim_allowed": web_claim_allowed,
        "available": _offer_available(offer) and existing is None,
        "already_claimed": existing is not None, "card_token": existing["card_token"] if existing else None,
    }


async def claim_offer(
    conn, *, token: str | None = None, short_code: str | None = None, account_id: UUID,
) -> dict:
    async with conn.transaction():
        offer = await _load_offer(conn, token=token, short_code=short_code)
        existing = await conn.fetchrow(
            "SELECT card_token FROM tellus_promo_cards WHERE campaign_id=$1 AND account_id=$2",
            offer["campaign_id"], account_id,
        )
        if existing is not None:
            card, created = await promo_service.claim_card(conn, offer["claim_token"], account_id)
            return {
                "offer_id": offer["id"], "card_token": card["card_token"], "reward_text": offer["reward_text"],
                "store_name": offer["store_name"], "claim_expires_at": offer["claim_expires_at"], "created": created,
            }
        if offer.get("require_app_install"):
            existed_when_offered = await conn.fetchval(
                "SELECT created_at <= $2 FROM tellus_accounts WHERE id=$1", account_id, offer["offer_created_at"],
            )
            has_ios_install = await conn.fetchval(
                """SELECT 1 FROM tellus_device_tokens
                   WHERE account_id=$1 AND platform='ios' AND bundle_id=$2
                   LIMIT 1""",
                account_id, get_settings().apns_bundle_id_tellus,
            )
            if not existed_when_offered and not has_ios_install:
                raise OfferError(409, "app_install_required", "Install the Tell-Us iPhone app to claim this offer.")
        if not _offer_available(offer):
            raise OfferError(410, "unavailable", "This offer is expired, revoked, or unavailable.")
        card, created = await promo_service.claim_card(conn, offer["claim_token"], account_id)
        await conn.execute(
            """UPDATE tellus_shoutout_offers SET status='claimed', claimed_account_id=$2,
               claimed_at=COALESCE(claimed_at,NOW()), card_token=$3 WHERE id=$1""",
            offer["id"], account_id, card["card_token"],
        )
        return {
            "offer_id": offer["id"], "card_token": card["card_token"], "reward_text": offer["reward_text"],
            "store_name": offer["store_name"], "claim_expires_at": offer["claim_expires_at"], "created": created,
        }
