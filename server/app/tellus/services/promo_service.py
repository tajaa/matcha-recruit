"""Tell-Us promo campaigns / QR reward cards.

Brand mints a campaign with a global claim cap; a consumer scanning the
campaign QR claims exactly one single-use card; staff redeem it at the
counter through a per-store scanner device token. Deliberately separate from
the points economy (points_service.py) — free cards never touch
tellus_points_ledger/tellus_points_balances, and claim_count is a monotone
issuance counter that expiry/cancellation never decrement (unlike
reclaim_expired_redemptions' quantity_claimed restore, which is wrong here).

Concurrency invariants:
  - claim_card: card INSERT (ON CONFLICT DO NOTHING) happens BEFORE the cap
    UPDATE, and the cap UPDATE's WHERE re-checks status/window/claim_count
    under the campaign row's lock — so a raced dedup never double-counts the
    cap, and a cap miss rolls back the card insert via the enclosing
    transaction.
  - redeem_card: a single UPDATE carries every predicate (issued, unexpired,
    right brand, campaign not cancelled) — the second scanner to reach an
    already-redeemed card blocks on the row lock and then fails the
    predicate, so double-redeem is structurally impossible.
  - Idempotency checks are pre-checks (SELECT before INSERT), never a caught
    UniqueViolationError — these functions are routinely called inside an
    already-open transaction, and a caught error there leaves the enclosing
    SAVEPOINT aborted (see points_service.py's adjust_points docstring for
    the same rule).
"""
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from .points_service import notify_account

CARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")
LOCATION_FRESHNESS_HOURS = 6
MILES_TO_KM = 1.60934

_DEVICE_DISTANCE_SQL = """
    6371.0 * acos(least(1.0, greatest(-1.0,
        sin(radians($2)) * sin(radians(dt.latitude)) +
        cos(radians($2)) * cos(radians(dt.latitude)) *
        cos(radians(dt.longitude - $3))
    )))
"""

_CAMPAIGN_COLUMNS = (
    "id, brand_id, title, description, reward_text, claim_token, max_claims, "
    "claim_count, status, card_expiry_days, starts_at, ends_at, flyer_image_url, "
    "(design_json IS NOT NULL) AS has_design, cancelled_at, created_at, updated_at, "
    "campaign_type, store_id, radius_miles, push_sent_at, push_sent_count"
)
_CAMPAIGN_COLUMNS_QUALIFIED = (
    "c.id, c.brand_id, c.title, c.description, c.reward_text, c.claim_token, "
    "c.max_claims, c.claim_count, c.status, c.card_expiry_days, c.starts_at, c.ends_at, "
    "c.flyer_image_url, (c.design_json IS NOT NULL) AS has_design, c.cancelled_at, "
    "c.created_at, c.updated_at, c.campaign_type, c.store_id, c.radius_miles, "
    "c.push_sent_at, c.push_sent_count"
)

_CARD_SELECT_SQL = """
    SELECT pc.id, pc.card_token, pc.status, pc.issued_at, pc.expires_at, pc.redeemed_at,
           pc.campaign_id, pc.account_id, c.brand_id, c.status AS campaign_status,
           c.title AS campaign_title, c.reward_text,
           b.name AS brand_name, b.logo_url AS brand_logo_url,
           s.name AS redeemed_store_name
    FROM tellus_promo_cards pc
    JOIN tellus_promo_campaigns c ON c.id = pc.campaign_id
    JOIN tellus_brands b ON b.id = c.brand_id
    LEFT JOIN tellus_stores s ON s.id = pc.redeemed_store_id
"""


class PromoError(Exception):
    """Route maps .http_status/.code/.message; .extra is merged into the
    response detail body (e.g. already_redeemed context).

    .extra values MUST be JSON primitives (str/int/bool/None) — the routes
    splat them into HTTPException(detail=...) and Starlette serializes that
    with json.dumps, so a datetime/UUID/Decimal in here is a 500."""

    def __init__(self, http_status: int, code: str, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.extra = extra or {}


# ── pure (unit-testable, no DB) ──────────────────────────────────────────────

def extract_card_token(raw: str) -> str:
    """Accept a bare card token or a full card URL; return the bare token.
    Raises PromoError(422) on anything that doesn't look like a token."""
    candidate = raw.strip()
    if not CARD_TOKEN_RE.match(candidate):
        segment = candidate.rstrip("/").rsplit("/", 1)[-1]
        candidate = segment
    if not CARD_TOKEN_RE.match(candidate):
        raise PromoError(422, "bad_token", "That doesn't look like a valid reward card code.")
    return candidate


def effective_card_status(status: str, expires_at: datetime, now: Optional[datetime] = None) -> str:
    """'issued' past expiry derives to 'expired' (never stored). Terminal
    states ('redeemed', 'cancelled') never flip, mirroring
    marketplace_service.effective_redemption_status."""
    if status == "issued":
        now = now or datetime.now(timezone.utc)
        if expires_at is not None and expires_at <= now:
            return "expired"
    return status


def can_campaign_transition(current: str, new: str) -> bool:
    """Only active<->paused via the generic PATCH. Cancel is a one-way door
    with its own endpoint (invalidates outstanding cards); nothing un-cancels."""
    if current == "cancelled" or new == "cancelled":
        return False
    return {current, new} <= {"active", "paused"}


def claim_reason(campaign: dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if campaign["status"] == "cancelled":
        return "cancelled"
    if campaign.get("plan_status", "active") != "active":
        return "brand_inactive"
    if campaign["status"] == "paused":
        return "paused"
    starts_at = campaign.get("starts_at")
    if starts_at is not None and starts_at > now:
        return "not_started"
    ends_at = campaign.get("ends_at")
    if ends_at is not None and ends_at <= now:
        return "ended"
    if campaign["claim_count"] >= campaign["max_claims"]:
        return "cap_reached"
    return "ok"


def map_redeem_failure(card: Optional[dict], now: Optional[datetime] = None) -> PromoError:
    """card is None (unknown token, or a diagnostic re-query scoped to the
    wrong brand — same 404 either way so a scanner can't probe for another
    brand's card tokens)."""
    if card is None:
        return PromoError(404, "not_found", "That reward card wasn't found.")
    now = now or datetime.now(timezone.utc)
    if card["status"] == "redeemed":
        redeemed_at = card["redeemed_at"]
        return PromoError(
            409, "already_redeemed", "This card was already redeemed.",
            # .isoformat() is load-bearing: the routes splat .extra straight
            # into HTTPException(detail=...), and Starlette's JSONResponse uses
            # json.dumps (not jsonable_encoder) — a raw datetime here turns the
            # single most common scan failure into a 500.
            extra={
                "redeemed_at": redeemed_at.isoformat() if redeemed_at is not None else None,
                "redeemed_store_name": card.get("redeemed_store_name"),
            },
        )
    if card["status"] == "cancelled" or card["campaign_status"] == "cancelled":
        return PromoError(410, "cancelled", "This promo was cancelled.")
    if card["expires_at"] is not None and card["expires_at"] <= now:
        return PromoError(410, "expired", "This reward card has expired.")
    # status == 'issued' but the UPDATE still didn't match — only remaining
    # cause is a wrong-brand scan, kept as 404 (no cross-brand existence leak).
    return PromoError(404, "not_found", "That reward card wasn't found.")


# ── serialization ────────────────────────────────────────────────────────────

def _serialize_campaign(row: dict, stats: Optional[dict] = None) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "reward_text": row["reward_text"],
        "claim_token": row["claim_token"],
        "claim_url": f"/tellus/p/{row['claim_token']}",
        "max_claims": row["max_claims"],
        "claim_count": row["claim_count"],
        "status": row["status"],
        "card_expiry_days": row["card_expiry_days"],
        "starts_at": row["starts_at"],
        "ends_at": row["ends_at"],
        "flyer_image_url": row["flyer_image_url"],
        "has_design": row["has_design"],
        "cancelled_at": row["cancelled_at"],
        "created_at": row["created_at"],
        "campaign_type": row.get("campaign_type", "qr"),
        "store_id": row.get("store_id"),
        "store_name": row.get("store_name"),
        "radius_miles": row.get("radius_miles"),
        "push_sent_at": row.get("push_sent_at"),
        "push_sent_count": row.get("push_sent_count", 0),
        "stats": stats,
    }


def _serialize_card(row: dict) -> dict:
    return {
        "id": row["id"],
        "card_token": row["card_token"],
        "card_url": f"/tellus/card/{row['card_token']}",
        "status": effective_card_status(row["status"], row["expires_at"]),
        "campaign_title": row["campaign_title"],
        "reward_text": row["reward_text"],
        "brand_name": row["brand_name"],
        "brand_logo_url": row["brand_logo_url"],
        "issued_at": row["issued_at"],
        "expires_at": row["expires_at"],
        "redeemed_at": row["redeemed_at"],
        "redeemed_store_name": row["redeemed_store_name"],
    }


def _serialize_scanner(row: dict) -> dict:
    return {
        "id": row["id"],
        "store_id": row["store_id"],
        "store_name": row["store_name"],
        "label": row["label"],
        "token": row["token"],
        "scanner_url": f"/tellus/scan/{row['token']}",
        "is_active": row["is_active"],
        "created_at": row["created_at"],
    }


# ── brand CRUD ────────────────────────────────────────────────────────────────

async def create_campaign(conn, brand_id: UUID, data) -> dict:
    if data.campaign_type == "location":
        store = await conn.fetchrow(
            "SELECT id, name, lat, lng FROM tellus_stores WHERE id = $1 AND brand_id = $2",
            data.store_id, brand_id,
        )
        if store is None:
            raise PromoError(404, "store_not_found", "Choose one of your stores for this campaign.")
        if store["lat"] is None or store["lng"] is None:
            raise PromoError(409, "store_location_missing", "The selected store needs a valid address first.")
    token = secrets.token_urlsafe(12)
    row = await conn.fetchrow(
        f"""INSERT INTO tellus_promo_campaigns
                (brand_id, title, description, reward_text, claim_token,
                 max_claims, card_expiry_days, starts_at, ends_at,
                 campaign_type, store_id, radius_miles)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING {_CAMPAIGN_COLUMNS}""",
        brand_id, data.title, data.description, data.reward_text, token,
        data.max_claims, data.card_expiry_days, data.starts_at, data.ends_at,
        data.campaign_type, data.store_id, data.radius_miles,
    )
    result = dict(row)
    result["store_name"] = (
        await conn.fetchval("SELECT name FROM tellus_stores WHERE id = $1", data.store_id)
        if data.store_id else None
    )
    if data.campaign_type == "qr":
        await notify_campaign_followers(conn, brand_id, result)
    return _serialize_campaign(result)


async def notify_campaign_followers(conn, brand_id: UUID, campaign: dict) -> None:
    """Fan a "campaign starts" notification out to every consumer following the
    brand, in one statement. Skipped entirely for a future-dated campaign
    (`starts_at` in the future) — there is no scheduler to fire this later, so
    a campaign that isn't claimable yet (see `claim_reason`'s "not_started")
    simply gets no start notification rather than a false "just started" push.
    Followers get the brand slug/name in the push payload so the client can
    deep-link to the brand's screen."""
    starts_at = campaign.get("starts_at")
    if starts_at is not None and starts_at > datetime.now(timezone.utc):
        return
    brand = await conn.fetchrow("SELECT name, slug FROM tellus_brands WHERE id = $1", brand_id)
    if brand is None:
        return
    title = f"{brand['name']}: {campaign['title']}"
    body = campaign.get("description") or "A business you follow just started a new promo."
    rows = await conn.fetch(
        """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
           SELECT consumer_account_id, $2::text, $3::text, $4::text, 'brand', $5::text
           FROM tellus_brand_follows WHERE brand_id = $1
           RETURNING account_id""",
        brand_id, "promo_campaign", title, body, str(brand_id),
    )
    from . import push
    push.schedule_push(
        [r["account_id"] for r in rows], "promo_campaign", title, body,
        reference_type="brand", reference_id=str(brand_id),
        slug=brand["slug"], name=brand["name"], claim_token=campaign.get("claim_token"),
    )


async def list_campaigns(conn, brand_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT c.id, c.brand_id, c.title, c.description, c.reward_text, c.claim_token,
                   c.max_claims, c.claim_count, c.status, c.card_expiry_days, c.starts_at,
                   c.ends_at, c.flyer_image_url, (c.design_json IS NOT NULL) AS has_design,
                   c.cancelled_at, c.created_at, c.campaign_type, c.store_id, c.radius_miles,
                   c.push_sent_at, c.push_sent_count, s.name AS store_name,
                   COUNT(pc.id) FILTER (WHERE pc.status IS NOT NULL) AS claimed,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'redeemed') AS redeemed,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'issued' AND pc.expires_at >  NOW()) AS outstanding,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'issued' AND pc.expires_at <= NOW()) AS expired,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'cancelled') AS cancelled
             FROM tellus_promo_campaigns c
             LEFT JOIN tellus_promo_cards pc ON pc.campaign_id = c.id
             LEFT JOIN tellus_stores s ON s.id = c.store_id
             WHERE c.brand_id = $1
             GROUP BY c.id, s.name
            ORDER BY c.created_at DESC""",
        brand_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        stats = {
            "claimed": d.pop("claimed"), "redeemed": d.pop("redeemed"),
            "outstanding": d.pop("outstanding"), "expired": d.pop("expired"),
            "cancelled": d.pop("cancelled"),
        }
        out.append(_serialize_campaign(d, stats=stats))
    return out


async def get_campaign_owned(conn, brand_id: UUID, campaign_id: UUID) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_CAMPAIGN_COLUMNS_QUALIFIED}, s.name AS store_name "
        "FROM tellus_promo_campaigns c LEFT JOIN tellus_stores s ON s.id = c.store_id "
        "WHERE c.id = $1 AND c.brand_id = $2",
        campaign_id, brand_id,
    )
    if row is None:
        raise PromoError(404, "not_found", "Campaign not found.")
    d = dict(row)
    stats_row = await conn.fetchrow(
        """SELECT COUNT(*) FILTER (WHERE status IS NOT NULL) AS claimed,
                  COUNT(*) FILTER (WHERE status = 'redeemed') AS redeemed,
                  COUNT(*) FILTER (WHERE status = 'issued' AND expires_at >  NOW()) AS outstanding,
                  COUNT(*) FILTER (WHERE status = 'issued' AND expires_at <= NOW()) AS expired,
                  COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
           FROM tellus_promo_cards WHERE campaign_id = $1""",
        campaign_id,
    )
    return _serialize_campaign(d, stats=dict(stats_row))


async def get_campaign_design(conn, brand_id: UUID, campaign_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT design_json FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
        campaign_id, brand_id,
    )
    if row is None:
        raise PromoError(404, "not_found", "Campaign not found.")
    raw = row["design_json"]
    # No asyncpg JSON codec is registered on this pool — asyncpg hands back
    # the raw JSONB text (same trap tellus_admin_audit.detail has; see
    # routes/admin/_shared.py:decode_audit_rows). isinstance guard keeps this
    # correct if a codec is ever added later.
    return json.loads(raw) if isinstance(raw, str) else raw


_PATCH_COLUMNS = ("title", "reward_text", "description", "ends_at", "status")
_NULLABLE_PATCH_COLUMNS = {"description", "ends_at"}  # the rest are NOT NULL


async def update_campaign(conn, brand_id: UUID, campaign_id: UUID, patch) -> dict:
    current = await conn.fetchrow(
        "SELECT status FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
        campaign_id, brand_id,
    )
    if current is None:
        raise PromoError(404, "not_found", "Campaign not found.")
    if current["status"] == "cancelled":
        raise PromoError(409, "already_cancelled", "This campaign is cancelled and can no longer be edited.")
    if patch.status is not None and not can_campaign_transition(current["status"], patch.status):
        raise PromoError(409, "bad_transition", f"Can't move campaign from {current['status']} to {patch.status}.")

    # model_fields_set-driven SET clause so an explicit null on a nullable
    # field actually clears it (COALESCE previously made that impossible),
    # while an unsent field is left untouched. Column names come from the
    # _PATCH_COLUMNS whitelist above, never from request text.
    sets: list[str] = []
    values: list = []
    for col in _PATCH_COLUMNS:
        if col not in patch.model_fields_set:
            continue
        val = getattr(patch, col)
        if val is None and col not in _NULLABLE_PATCH_COLUMNS:
            continue
        values.append(val)
        sets.append(f"{col} = ${len(values) + 2}")  # $1 = id, $2 = brand_id

    if not sets:
        row = await conn.fetchrow(
            f"SELECT {_CAMPAIGN_COLUMNS_QUALIFIED}, s.name AS store_name "
            "FROM tellus_promo_campaigns c LEFT JOIN tellus_stores s ON s.id = c.store_id "
            "WHERE c.id = $1 AND c.brand_id = $2",
            campaign_id, brand_id,
        )
        return _serialize_campaign(dict(row))

    row = await conn.fetchrow(
        f"""UPDATE tellus_promo_campaigns SET {', '.join(sets)}, updated_at = NOW()
            WHERE id = $1 AND brand_id = $2 AND status <> 'cancelled'
            RETURNING {_CAMPAIGN_COLUMNS}""",
        campaign_id, brand_id, *values,
    )
    if row is None:
        # Closes the window where a concurrent cancel lands between the
        # pre-check above and this UPDATE.
        raise PromoError(409, "already_cancelled", "This campaign is cancelled and can no longer be edited.")
    result = dict(row)
    result["store_name"] = await conn.fetchval(
        "SELECT name FROM tellus_stores WHERE id = $1", result.get("store_id")
    ) if result.get("store_id") else None
    return _serialize_campaign(result)


async def push_campaign(conn, brand_id: UUID, campaign_id: UUID) -> dict:
    """Push a location campaign once to fresh, in-radius follower devices."""
    async with conn.transaction():
        campaign = await conn.fetchrow(
            f"""SELECT {_CAMPAIGN_COLUMNS_QUALIFIED}, s.name AS store_name, s.lat AS store_lat,
                       s.lng AS store_lng, b.name AS brand_name, b.slug AS brand_slug,
                       b.plan_status
                  FROM tellus_promo_campaigns c
                  JOIN tellus_brands b ON b.id = c.brand_id
                  LEFT JOIN tellus_stores s ON s.id = c.store_id
                 WHERE c.id = $1 AND c.brand_id = $2
                 FOR UPDATE OF c""",
            campaign_id, brand_id,
        )
        if campaign is None:
            raise PromoError(404, "not_found", "Campaign not found.")
        if campaign["campaign_type"] != "location":
            raise PromoError(409, "not_location", "Only location campaigns can be pushed this way.")
        if campaign["push_sent_at"] is not None:
            raise PromoError(409, "already_pushed", "This location campaign was already pushed.")
        if campaign["status"] != "active":
            raise PromoError(409, "not_active", "Only active campaigns can be pushed.")
        if campaign["plan_status"] != "active":
            raise PromoError(402, "brand_inactive", "This brand's account is not active.")
        now = datetime.now(timezone.utc)
        if campaign["starts_at"] is not None and campaign["starts_at"] > now:
            raise PromoError(409, "not_started", "This campaign has not started yet.")
        if campaign["ends_at"] is not None and campaign["ends_at"] <= now:
            raise PromoError(409, "ended", "This campaign has ended.")
        if (
            campaign["radius_miles"] is None
            or campaign["store_lat"] is None
            or campaign["store_lng"] is None
        ):
            raise PromoError(409, "store_location_missing", "The selected store needs a valid address first.")

        radius_km = campaign["radius_miles"] * MILES_TO_KM
        rows = await conn.fetch(
            f"""SELECT DISTINCT ON (dt.token) dt.token, dt.account_id
                  FROM tellus_brand_follows f
                  JOIN tellus_device_tokens dt ON dt.account_id = f.consumer_account_id
                 WHERE f.brand_id = $1
                   AND dt.platform = 'ios'
                   AND dt.latitude IS NOT NULL AND dt.longitude IS NOT NULL
                   AND dt.location_updated_at > NOW() - INTERVAL '{LOCATION_FRESHNESS_HOURS} hours'
                   AND dt.latitude BETWEEN $2 - ($4 / 111.045)
                                       AND $2 + ($4 / 111.045)
                   AND dt.longitude BETWEEN $3 - ($4 / (111.045 * greatest(cos(radians($2)), 0.01)))
                                        AND $3 + ($4 / (111.045 * greatest(cos(radians($2)), 0.01)))
                   AND ({_DEVICE_DISTANCE_SQL}) <= $4
                 ORDER BY dt.token, dt.location_updated_at DESC""",
            brand_id, campaign["store_lat"], campaign["store_lng"], radius_km,
        )
        tokens = [r["token"] for r in rows]
        account_ids = list(dict.fromkeys(r["account_id"] for r in rows))
        brand_title = f"{campaign['brand_name']}: {campaign['title']}"
        body = campaign["description"] or "A location-only promo is available near you."
        if account_ids:
            await conn.execute(
                """INSERT INTO tellus_notifications
                           (account_id, kind, title, body, reference_type, reference_id)
                    SELECT unnest($1::uuid[]), $2, $3, $4, 'promo_campaign', $5""",
                account_ids, "promo_campaign", brand_title, body, str(campaign_id),
            )
            # Only burn the one-shot push when it actually reached someone —
            # the already_pushed guard above is permanent, so stamping this
            # on a zero-recipient send would make the campaign unretryable.
            await conn.execute(
                """UPDATE tellus_promo_campaigns
                      SET push_sent_at = NOW(), push_sent_count = $3, updated_at = NOW()
                    WHERE id = $1 AND brand_id = $2""",
                campaign_id, brand_id, len(account_ids),
            )

    if tokens:
        from . import push
        push.schedule_token_push(
            tokens, "promo_campaign", brand_title, body,
            reference_type="promo_campaign", reference_id=str(campaign_id),
            slug=campaign["brand_slug"], name=campaign["brand_name"],
            claim_token=campaign["claim_token"],
        )
    return {
        "sent_count": len(account_ids),
        "pushed": bool(account_ids),
        "store_name": campaign["store_name"],
        "radius_miles": campaign["radius_miles"],
    }


async def cancel_campaign(conn, brand_id: UUID, campaign_id: UUID) -> int:
    async with conn.transaction():
        cancelled = await conn.fetchrow(
            """UPDATE tellus_promo_campaigns
               SET status = 'cancelled', cancelled_at = NOW(), updated_at = NOW()
               WHERE id = $1 AND brand_id = $2 AND status <> 'cancelled'
               RETURNING id""",
            campaign_id, brand_id,
        )
        if cancelled is None:
            owned = await conn.fetchval(
                "SELECT 1 FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
                campaign_id, brand_id,
            )
            if not owned:
                raise PromoError(404, "not_found", "Campaign not found.")
            raise PromoError(409, "already_cancelled", "This campaign is already cancelled.")

        result = await conn.execute(
            "UPDATE tellus_promo_cards SET status = 'cancelled' WHERE campaign_id = $1 AND status = 'issued'",
            campaign_id,
        )
        # asyncpg execute() returns a tag like "UPDATE 3".
        invalidated = int(result.split()[-1])
        return invalidated


async def save_design(conn, brand_id: UUID, campaign_id: UUID, design_json_text: str) -> None:
    """design_json_text is a pre-serialized JSON string (see routes/promo.py:
    put_campaign_design) — no asyncpg JSON codec is registered on this pool,
    so a raw dict here fails as 'invalid input for query argument $3'."""
    row = await conn.fetchrow(
        "UPDATE tellus_promo_campaigns SET design_json = $3::jsonb, updated_at = NOW() "
        "WHERE id = $1 AND brand_id = $2 RETURNING id",
        campaign_id, brand_id, design_json_text,
    )
    if row is None:
        raise PromoError(404, "not_found", "Campaign not found.")


async def assert_campaign_owned(conn, brand_id: UUID, campaign_id: UUID) -> None:
    """Cheap ownership check for callsites that don't need the row itself —
    e.g. upload_flyer, which must verify ownership BEFORE writing to S3."""
    owned = await conn.fetchval(
        "SELECT 1 FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
        campaign_id, brand_id,
    )
    if not owned:
        raise PromoError(404, "not_found", "Campaign not found.")


async def set_flyer_url(conn, brand_id: UUID, campaign_id: UUID, url: str) -> Optional[str]:
    """Sets flyer_image_url, returns the OLD url (caller deletes the managed
    object if it was ours) — mirrors links.py:upload_brand_logo."""
    row = await conn.fetchrow(
        "SELECT flyer_image_url FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
        campaign_id, brand_id,
    )
    if row is None:
        raise PromoError(404, "not_found", "Campaign not found.")
    old = row["flyer_image_url"]
    await conn.execute(
        "UPDATE tellus_promo_campaigns SET flyer_image_url = $3, updated_at = NOW() "
        "WHERE id = $1 AND brand_id = $2",
        campaign_id, brand_id, url,
    )
    return old


# ── claim ─────────────────────────────────────────────────────────────────────

async def _location_claim_allowed(conn, campaign: dict, account_id: UUID) -> bool:
    if campaign.get("campaign_type", "qr") != "location":
        return True
    if (
        campaign.get("radius_miles") is None
        or campaign.get("store_lat") is None
        or campaign.get("store_lng") is None
    ):
        return False
    radius_km = campaign["radius_miles"] * MILES_TO_KM
    return bool(await conn.fetchval(
        f"""SELECT EXISTS (
                 SELECT 1
                   FROM tellus_device_tokens dt
                  WHERE dt.account_id = $1
                    AND dt.platform = 'ios'
                    AND dt.latitude IS NOT NULL AND dt.longitude IS NOT NULL
                    AND dt.location_updated_at > NOW() - INTERVAL '{LOCATION_FRESHNESS_HOURS} hours'
                    AND dt.latitude BETWEEN $2 - ($4 / 111.045)
                                        AND $2 + ($4 / 111.045)
                    AND dt.longitude BETWEEN $3 - ($4 / (111.045 * greatest(cos(radians($2)), 0.01)))
                                         AND $3 + ($4 / (111.045 * greatest(cos(radians($2)), 0.01)))
                    AND ({_DEVICE_DISTANCE_SQL}) <= $4
             )""",
        account_id, campaign["store_lat"], campaign["store_lng"], radius_km,
    ))


async def resolve_claim_preview(conn, claim_token: str, viewer_account_id: Optional[UUID]) -> dict:
    campaign = await conn.fetchrow(
        """SELECT c.id, c.brand_id, c.title, c.description, c.reward_text, c.status,
                   c.starts_at, c.ends_at, c.claim_count, c.max_claims, c.flyer_image_url,
                   c.campaign_type, c.radius_miles, c.push_sent_at,
                   s.lat AS store_lat, s.lng AS store_lng,
                   b.name AS brand_name, b.logo_url AS brand_logo_url, b.plan_status
            FROM tellus_promo_campaigns c
            JOIN tellus_brands b ON b.id = c.brand_id
            LEFT JOIN tellus_stores s ON s.id = c.store_id
            WHERE c.claim_token = $1""",
        claim_token,
    )
    if campaign is None:
        raise PromoError(404, "not_found", "This promo link isn't available.")

    reason = claim_reason(dict(campaign))
    already_claimed = False
    card_token = None
    if viewer_account_id is not None:
        existing = await conn.fetchrow(
            "SELECT card_token FROM tellus_promo_cards WHERE campaign_id = $1 AND account_id = $2",
            campaign["id"], viewer_account_id,
        )
        if existing is not None:
            already_claimed = True
            card_token = existing["card_token"]
    if not already_claimed and reason == "ok" and campaign["campaign_type"] == "location":
        if campaign["push_sent_at"] is None:
            reason = "not_pushed"
        elif viewer_account_id is None:
            reason = "location_required"
        elif not await _location_claim_allowed(conn, dict(campaign), viewer_account_id):
            reason = "outside_radius"

    return {
        "brand_name": campaign["brand_name"],
        "brand_logo_url": campaign["brand_logo_url"],
        "title": campaign["title"],
        "reward_text": campaign["reward_text"],
        "description": campaign["description"],
        "flyer_image_url": campaign["flyer_image_url"],
        "available": reason == "ok" and not already_claimed,
        "reason": reason,
        "already_claimed": already_claimed,
        "card_token": card_token,
    }


async def claim_card(conn, claim_token: str, account_id: UUID) -> tuple[dict, bool]:
    """Returns (CardOut-shaped dict, created). created=False means an
    idempotent replay of an existing claim (200, not 201)."""
    async with conn.transaction():
        # FOR UPDATE OF c only — locking tellus_brands here would serialize
        # every campaign belonging to the same brand on one row.
        campaign = await conn.fetchrow(
            """SELECT c.id, c.status, c.starts_at, c.ends_at, c.claim_count, c.max_claims,
                       c.card_expiry_days, c.campaign_type, c.radius_miles, c.push_sent_at,
                       s.lat AS store_lat, s.lng AS store_lng, b.plan_status
               FROM tellus_promo_campaigns c JOIN tellus_brands b ON b.id = c.brand_id
               LEFT JOIN tellus_stores s ON s.id = c.store_id
               WHERE c.claim_token = $1 FOR UPDATE OF c""",
            claim_token,
        )
        if campaign is None:
            raise PromoError(404, "not_found", "This promo link isn't available.")

        existing = await conn.fetchrow(
            "SELECT id FROM tellus_promo_cards WHERE campaign_id = $1 AND account_id = $2",
            campaign["id"], account_id,
        )
        if existing is not None:
            card = await conn.fetchrow(_CARD_SELECT_SQL + " WHERE pc.id = $1", existing["id"])
            return _serialize_card(dict(card)), False

        reason = claim_reason(dict(campaign))
        if reason != "ok":
            raise PromoError(410, reason, _CLAIM_UNAVAILABLE_MESSAGES.get(reason, "This promo isn't available."))
        if campaign["campaign_type"] == "location":
            if campaign["push_sent_at"] is None:
                raise PromoError(410, "not_pushed", _CLAIM_UNAVAILABLE_MESSAGES["not_pushed"])
            if not await _location_claim_allowed(conn, dict(campaign), account_id):
                raise PromoError(410, "outside_radius", _CLAIM_UNAVAILABLE_MESSAGES["outside_radius"])

        card_token = secrets.token_urlsafe(16)
        inserted = await conn.fetchrow(
            """INSERT INTO tellus_promo_cards (campaign_id, account_id, card_token, expires_at)
               VALUES ($1, $2, $3, NOW() + make_interval(days => $4))
               ON CONFLICT (campaign_id, account_id) DO NOTHING
               RETURNING id""",
            campaign["id"], account_id, card_token, campaign["card_expiry_days"],
        )
        if inserted is None:
            # Raced with a concurrent claim from the same account.
            row = await conn.fetchrow(
                "SELECT id FROM tellus_promo_cards WHERE campaign_id = $1 AND account_id = $2",
                campaign["id"], account_id,
            )
            card = await conn.fetchrow(_CARD_SELECT_SQL + " WHERE pc.id = $1", row["id"])
            return _serialize_card(dict(card)), False

        capped = await conn.fetchrow(
            """UPDATE tellus_promo_campaigns
               SET claim_count = claim_count + 1, updated_at = NOW()
               WHERE id = $1 AND status = 'active'
                 AND (starts_at IS NULL OR starts_at <= NOW())
                 AND (ends_at   IS NULL OR ends_at   >  NOW())
                 AND claim_count < max_claims
               RETURNING id""",
            campaign["id"],
        )
        if capped is None:
            # Rollback (enclosing transaction) undoes the card insert above.
            raise PromoError(410, "cap_reached", "This promo has reached its claim limit.")

        card = await conn.fetchrow(_CARD_SELECT_SQL + " WHERE pc.id = $1", inserted["id"])
        await notify_account(
            conn, account_id, "promo_card", "Your reward card is ready",
            # reference_id is card_token, not the row id: every consumer surface
            # addresses a card by token (/card/:cardToken, GET /me/promo-cards/
            # {card_token}), so the UUID could not build the deep link.
            card["reward_text"], "promo_card", card["card_token"],
        )
        return _serialize_card(dict(card)), True


_CLAIM_UNAVAILABLE_MESSAGES = {
    "cancelled": "This promo was cancelled.",
    "brand_inactive": "This brand's account is no longer active.",
    "paused": "This promo isn't currently active.",
    "not_started": "This promo hasn't started yet.",
    "ended": "This promo has ended.",
    "cap_reached": "This promo has reached its claim limit.",
    "location_required": "Sign in and enable location to claim this local offer.",
    "outside_radius": "This offer is only available while you are near the store.",
    "not_pushed": "This local offer has not been sent yet.",
}


# ── scanner ───────────────────────────────────────────────────────────────────

async def resolve_scanner(conn, device_token: str) -> dict:
    row = await conn.fetchrow(
        """SELECT sd.id, sd.brand_id, sd.store_id, sd.is_active, s.name AS store_name,
                  b.name AS brand_name, b.logo_url AS brand_logo_url, b.plan_status
           FROM tellus_scanner_devices sd
           JOIN tellus_stores s ON s.id = sd.store_id
           JOIN tellus_brands b ON b.id = sd.brand_id
           WHERE sd.token = $1""",
        device_token,
    )
    if row is None or not row["is_active"]:
        raise PromoError(404, "not_found", "This scanner link isn't available.")
    if row["plan_status"] != "active":
        raise PromoError(410, "brand_inactive", "This brand's account is no longer active.")
    return dict(row)


async def redeem_card(conn, scanner: dict, raw_card_token: str) -> dict:
    token = extract_card_token(raw_card_token)
    row = await conn.fetchrow(
        """UPDATE tellus_promo_cards pc
           SET status = 'redeemed', redeemed_at = NOW(),
               redeemed_store_id = $2, redeemed_scanner_id = $3
           FROM tellus_promo_campaigns c
           WHERE pc.card_token = $1 AND pc.status = 'issued' AND pc.expires_at > NOW()
             AND c.id = pc.campaign_id AND c.brand_id = $4 AND c.status <> 'cancelled'
           RETURNING pc.redeemed_at, c.title AS campaign_title, c.reward_text""",
        token, scanner.get("store_id"), scanner.get("id"), scanner["brand_id"],
    )
    if row is not None:
        # resolve_scanner already fetched this — None on the brand-app path
        # (store_id is None there), the real name on a device-token scanner.
        return {
            "campaign_title": row["campaign_title"],
            "reward_text": row["reward_text"],
            "redeemed_at": row["redeemed_at"],
            "store_name": scanner.get("store_name"),
        }

    diagnostic = await conn.fetchrow(
        _CARD_SELECT_SQL + " WHERE pc.card_token = $1 AND c.brand_id = $2",
        token, scanner["brand_id"],
    )
    raise map_redeem_failure(dict(diagnostic) if diagnostic is not None else None)


async def create_scanner(conn, brand_id: UUID, store_id: UUID, label: Optional[str], store_name: str) -> dict:
    """Caller MUST have already verified store ownership (get_owned_store) and
    pass its name through — the caller's SELECT * already has it, no need
    for a second round-trip here."""
    token = secrets.token_urlsafe(16)
    row = await conn.fetchrow(
        """INSERT INTO tellus_scanner_devices (brand_id, store_id, token, label)
           VALUES ($1, $2, $3, $4)
           RETURNING id, store_id, label, token, is_active, created_at""",
        brand_id, store_id, token, label,
    )
    d = dict(row)
    d["store_name"] = store_name
    return _serialize_scanner(d)


async def list_scanners(conn, brand_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """SELECT sd.id, sd.store_id, s.name AS store_name, sd.label, sd.token,
                  sd.is_active, sd.created_at
           FROM tellus_scanner_devices sd
           JOIN tellus_stores s ON s.id = sd.store_id
           WHERE sd.brand_id = $1
           ORDER BY sd.created_at DESC""",
        brand_id,
    )
    return [_serialize_scanner(dict(r)) for r in rows]


async def revoke_scanner(conn, brand_id: UUID, scanner_id: UUID) -> None:
    row = await conn.fetchrow(
        """UPDATE tellus_scanner_devices SET is_active = FALSE, revoked_at = NOW()
           WHERE id = $1 AND brand_id = $2 RETURNING id""",
        scanner_id, brand_id,
    )
    if row is None:
        raise PromoError(404, "not_found", "Scanner not found.")


# ── consumer ──────────────────────────────────────────────────────────────────

async def list_my_cards(conn, account_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        _CARD_SELECT_SQL + " WHERE pc.account_id = $1 ORDER BY pc.issued_at DESC",
        account_id,
    )
    return [_serialize_card(dict(r)) for r in rows]


async def get_my_card(conn, account_id: UUID, card_token: str) -> dict:
    row = await conn.fetchrow(
        _CARD_SELECT_SQL + " WHERE pc.card_token = $1 AND pc.account_id = $2",
        card_token, account_id,
    )
    if row is None:
        raise PromoError(404, "not_found", "Reward card not found.")
    return _serialize_card(dict(row))
