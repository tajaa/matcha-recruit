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

_CAMPAIGN_COLUMNS = (
    "id, brand_id, title, description, reward_text, claim_token, max_claims, "
    "claim_count, status, card_expiry_days, starts_at, ends_at, flyer_image_url, "
    "(design_json IS NOT NULL) AS has_design, cancelled_at, created_at, updated_at"
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
    token = secrets.token_urlsafe(12)
    row = await conn.fetchrow(
        f"""INSERT INTO tellus_promo_campaigns
                (brand_id, title, description, reward_text, claim_token,
                 max_claims, card_expiry_days, starts_at, ends_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING {_CAMPAIGN_COLUMNS}""",
        brand_id, data.title, data.description, data.reward_text, token,
        data.max_claims, data.card_expiry_days, data.starts_at, data.ends_at,
    )
    return _serialize_campaign(dict(row))


async def list_campaigns(conn, brand_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT c.id, c.brand_id, c.title, c.description, c.reward_text, c.claim_token,
                   c.max_claims, c.claim_count, c.status, c.card_expiry_days, c.starts_at,
                   c.ends_at, c.flyer_image_url, (c.design_json IS NOT NULL) AS has_design,
                   c.cancelled_at, c.created_at,
                   COUNT(pc.id) FILTER (WHERE pc.status IS NOT NULL) AS claimed,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'redeemed') AS redeemed,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'issued' AND pc.expires_at >  NOW()) AS outstanding,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'issued' AND pc.expires_at <= NOW()) AS expired,
                   COUNT(pc.id) FILTER (WHERE pc.status = 'cancelled') AS cancelled
            FROM tellus_promo_campaigns c
            LEFT JOIN tellus_promo_cards pc ON pc.campaign_id = c.id
            WHERE c.brand_id = $1
            GROUP BY c.id
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
        f"SELECT {_CAMPAIGN_COLUMNS} FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
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
            f"SELECT {_CAMPAIGN_COLUMNS} FROM tellus_promo_campaigns WHERE id = $1 AND brand_id = $2",
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
    return _serialize_campaign(dict(row))


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

async def resolve_claim_preview(conn, claim_token: str, viewer_account_id: Optional[UUID]) -> dict:
    campaign = await conn.fetchrow(
        """SELECT c.id, c.brand_id, c.title, c.description, c.reward_text, c.status,
                  c.starts_at, c.ends_at, c.claim_count, c.max_claims, c.flyer_image_url,
                  b.name AS brand_name, b.logo_url AS brand_logo_url, b.plan_status
           FROM tellus_promo_campaigns c
           JOIN tellus_brands b ON b.id = c.brand_id
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
                      c.card_expiry_days, b.plan_status
               FROM tellus_promo_campaigns c JOIN tellus_brands b ON b.id = c.brand_id
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
