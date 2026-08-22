"""Per-brand Tell-Us loyalty economy.

This module is intentionally separate from ``points_service``. A brand loyalty
balance is not spendable in the Tell-Us marketplace and never writes to the
global points tables.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from ..models.loyalty import (
    LoyaltyEarningRuleIn,
    LoyaltyEventKey,
    LoyaltyProgramPut,
    LoyaltyRewardCreate,
    LoyaltyRewardPatch,
    LoyaltySocialSubmissionCreate,
)
from ..services.points_service import notify_account


EVENT_REASONS = {
    "visit": "earn_visit",
    "purchase": "earn_purchase",
    "review": "earn_review",
    "board_reply": "earn_board_reply",
    "follow": "earn_follow",
    "social_post": "earn_social_post",
}
EVENT_KEYS = set(EVENT_REASONS)


class LoyaltyError(Exception):
    def __init__(self, http_status: int, code: str, message: str, extra: Optional[dict] = None):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.extra = extra or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def points_for_purchase(
    amount_cents: int,
    points_per_dollar: int,
    max_points_per_event: Optional[int],
) -> int:
    if amount_cents < 1 or points_per_dollar < 1:
        return 0
    points = (amount_cents * points_per_dollar) // 100
    if max_points_per_event is not None:
        points = min(points, max_points_per_event)
    return max(0, points)


def tier_for_lifetime(tiers: Sequence[Mapping[str, object]], lifetime_points: int) -> str:
    ordered = sorted(tiers, key=lambda row: int(row["threshold_points"]))
    selected = "bronze"
    for tier in ordered:
        if int(tier["threshold_points"]) <= lifetime_points:
            selected = str(tier["tier_key"])
    return selected


def effective_redemption_status(
    status: str,
    expires_at: datetime,
    now: Optional[datetime] = None,
) -> str:
    if status == "issued" and expires_at <= (now or _now()):
        return "expired"
    return status


def _extract_prefixed_token(raw: str, prefix: str) -> str:
    value = raw.strip()
    if prefix and value.startswith(prefix):
        value = value[len(prefix):]
    elif "/" in value:
        parts = value.rstrip("/").rsplit("/", 1)
        value = parts[-1]
        if prefix and value.startswith(prefix):
            value = value[len(prefix):]
    if not value or len(value) > 512 or any(c.isspace() for c in value):
        raise LoyaltyError(422, "bad_token", "That does not look like a valid loyalty code.")
    return value


def extract_member_token(raw: str) -> str:
    value = raw.strip()
    if value.startswith("TU-LR1:"):
        raise LoyaltyError(422, "wrong_token_type", "That is a reward code, not a member card.")
    token = _extract_prefixed_token(value, "TU-LM1:")
    if token.startswith("TU-LR1:"):
        raise LoyaltyError(422, "wrong_token_type", "That is a reward code, not a member card.")
    return token


def extract_redemption_token(raw: str) -> str:
    value = raw.strip()
    if value.startswith("TU-LM1:"):
        raise LoyaltyError(422, "wrong_token_type", "That is a member card, not a reward code.")
    token = _extract_prefixed_token(value, "TU-LR1:")
    if token.startswith("TU-LM1:"):
        raise LoyaltyError(422, "wrong_token_type", "That is a member card, not a reward code.")
    return token


_SOCIAL_HOSTS = {
    "instagram": {"instagram.com"},
    "tiktok": {"tiktok.com"},
    "youtube": {"youtube.com", "youtu.be"},
    "facebook": {"facebook.com", "fb.com"},
    "x": {"x.com", "twitter.com"},
}
_TRACKING_PARAMS = {"fbclid", "gclid"}


def canonicalize_social_url(platform: str, raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme.lower() != "https" or not host:
        raise LoyaltyError(422, "bad_social_url", "Social links must use HTTPS.")
    allowed = _SOCIAL_HOSTS.get(platform)
    if allowed and host not in allowed:
        raise LoyaltyError(422, "bad_social_url", "That URL does not match the selected platform.")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    return urlunsplit(("https", host, parsed.path.rstrip("/") or "/", urlencode(query), ""))


def _empty_result() -> dict:
    return {
        "awarded": False,
        "points": 0,
        "points_balance": 0,
        "lifetime_points": 0,
        "tier_key": "bronze",
        "result_code": "inactive",
    }


async def _current_balance(conn, brand_id: UUID, account_id: UUID) -> dict:
    row = await conn.fetchrow(
        """SELECT points_balance, lifetime_points
             FROM tellus_loyalty_balances
            WHERE brand_id = $1 AND account_id = $2""",
        brand_id,
        account_id,
    )
    return _row_dict(row) if row else {"points_balance": 0, "lifetime_points": 0}


async def _inactive_result(conn, brand_id: UUID, account_id: UUID) -> dict:
    balance = await _current_balance(conn, brand_id, account_id)
    lifetime_points = balance.get("lifetime_points", 0)
    return {
        **_empty_result(),
        "points_balance": balance.get("points_balance", 0),
        "lifetime_points": lifetime_points,
        "tier_key": await _tier_for_balance(conn, brand_id, lifetime_points),
    }


async def _tier_for_balance(conn, brand_id: UUID, lifetime_points: int) -> str:
    rows = await conn.fetch(
        "SELECT tier_key, threshold_points FROM tellus_loyalty_tiers "
        "WHERE brand_id = $1 ORDER BY threshold_points",
        brand_id,
    )
    return tier_for_lifetime(rows or [{"tier_key": "bronze", "threshold_points": 0}], lifetime_points)


async def award_event(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    event_key: LoyaltyEventKey,
    reference_type: str,
    reference_id: str,
    source_store_id: Optional[UUID] = None,
    actor_account_id: Optional[UUID] = None,
    scanner_device_id: Optional[UUID] = None,
    purchase_amount_cents: Optional[int] = None,
    description: Optional[str] = None,
    bypass_cooldown: bool = False,
) -> dict:
    """Award one brand event atomically and idempotently."""
    if event_key not in EVENT_KEYS:
        raise ValueError(f"Unknown loyalty event: {event_key}")

    async with conn.transaction():
        program = await conn.fetchrow(
            """SELECT p.status, p.counter_mode, b.plan_status
                 FROM tellus_loyalty_programs p
                 JOIN tellus_brands b ON b.id = p.brand_id
                WHERE p.brand_id = $1""",
            brand_id,
        )
        if program is None or program["status"] != "active" or program["plan_status"] != "active":
            return await _inactive_result(conn, brand_id, account_id)

        rule = await conn.fetchrow(
            """SELECT award_type, fixed_points, points_per_dollar,
                      min_purchase_cents, max_points_per_event,
                      daily_cap, cooldown_seconds, is_active
                 FROM tellus_loyalty_earning_rules
                WHERE brand_id = $1 AND event_key = $2""",
            brand_id,
            event_key,
        )
        if rule is None or not rule["is_active"]:
            return await _inactive_result(conn, brand_id, account_id)

        await conn.execute(
            """INSERT INTO tellus_loyalty_balances (brand_id, account_id)
               VALUES ($1, $2) ON CONFLICT (brand_id, account_id) DO NOTHING""",
            brand_id,
            account_id,
        )
        balance = await conn.fetchrow(
            """SELECT points_balance, lifetime_points
                 FROM tellus_loyalty_balances
                WHERE brand_id = $1 AND account_id = $2
                FOR UPDATE""",
            brand_id,
            account_id,
        )

        duplicate = await conn.fetchval(
            """SELECT 1 FROM tellus_loyalty_ledger
                WHERE brand_id = $1 AND account_id = $2
                  AND reason = $3 AND reference_id = $4""",
            brand_id,
            account_id,
            EVENT_REASONS[event_key],
            reference_id,
        )
        if duplicate:
            tier = await _tier_for_balance(conn, brand_id, balance["lifetime_points"])
            return {
                "awarded": False,
                "points": 0,
                "points_balance": balance["points_balance"],
                "lifetime_points": balance["lifetime_points"],
                "tier_key": tier,
                "result_code": "awarded",
            }

        if event_key == "purchase":
            if purchase_amount_cents is None or purchase_amount_cents < int(rule["min_purchase_cents"]):
                return {
                    **_empty_result(),
                    "points_balance": balance["points_balance"],
                    "lifetime_points": balance["lifetime_points"],
                    "tier_key": await _tier_for_balance(conn, brand_id, balance["lifetime_points"]),
                    "result_code": "below_minimum",
                }
            points = points_for_purchase(
                purchase_amount_cents,
                int(rule["points_per_dollar"]),
                int(rule["max_points_per_event"]),
            )
        else:
            points = int(rule["fixed_points"])

        if rule["cooldown_seconds"] and not bypass_cooldown:
            recent = await conn.fetchval(
                """SELECT 1 FROM tellus_loyalty_ledger
                    WHERE brand_id = $1 AND account_id = $2 AND event_key = $3
                      AND delta > 0
                      AND created_at > NOW() - ($4 || ' seconds')::interval
                    LIMIT 1""",
                brand_id,
                account_id,
                event_key,
                str(int(rule["cooldown_seconds"])),
            )
            if recent:
                tier = await _tier_for_balance(conn, brand_id, balance["lifetime_points"])
                return {
                    "awarded": False,
                    "points": 0,
                    "points_balance": balance["points_balance"],
                    "lifetime_points": balance["lifetime_points"],
                    "tier_key": tier,
                    "result_code": "cooldown",
                }

        if rule["daily_cap"]:
            earned_today = await conn.fetchval(
                """SELECT COALESCE(SUM(delta), 0)
                     FROM tellus_loyalty_ledger
                    WHERE brand_id = $1 AND account_id = $2 AND event_key = $3
                      AND delta > 0 AND created_at::date = CURRENT_DATE""",
                brand_id,
                account_id,
                event_key,
            ) or 0
            points = min(points, max(0, int(rule["daily_cap"]) - int(earned_today)))
            if points <= 0:
                tier = await _tier_for_balance(conn, brand_id, balance["lifetime_points"])
                return {
                    "awarded": False,
                    "points": 0,
                    "points_balance": balance["points_balance"],
                    "lifetime_points": balance["lifetime_points"],
                    "tier_key": tier,
                    "result_code": "daily_cap",
                }

        new_balance = int(balance["points_balance"]) + points
        new_lifetime = int(balance["lifetime_points"]) + points
        inserted = await conn.fetchval(
            """INSERT INTO tellus_loyalty_ledger
                   (brand_id, account_id, delta, balance_after, reason, event_key,
                    reference_type, reference_id, source_store_id, actor_account_id,
                    scanner_device_id, purchase_amount_cents, description)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               ON CONFLICT (brand_id, account_id, reason, reference_id)
               DO NOTHING RETURNING id""",
            brand_id,
            account_id,
            points,
            new_balance,
            EVENT_REASONS[event_key],
            event_key,
            reference_type,
            reference_id,
            source_store_id,
            actor_account_id,
            scanner_device_id,
            purchase_amount_cents,
            description,
        )
        if inserted is None:
            current = await _current_balance(conn, brand_id, account_id)
            return {
                "awarded": False,
                "points": 0,
                "points_balance": current["points_balance"],
                "lifetime_points": current["lifetime_points"],
                "tier_key": await _tier_for_balance(conn, brand_id, current["lifetime_points"]),
                "result_code": "awarded",
            }

        await conn.execute(
            """UPDATE tellus_loyalty_balances
                  SET points_balance = $3, lifetime_points = $4, updated_at = NOW()
                WHERE brand_id = $1 AND account_id = $2""",
            brand_id,
            account_id,
            new_balance,
            new_lifetime,
        )
        tier = await _tier_for_balance(conn, brand_id, new_lifetime)
        await notify_account(
            conn,
            account_id,
            "loyalty_points_earned",
            f"+{points} {('point' if points == 1 else 'points')}",
            description or "You earned brand loyalty points.",
            "loyalty_brand",
            str(brand_id),
        )
        return {
            "awarded": True,
            "points": points,
            "points_balance": new_balance,
            "lifetime_points": new_lifetime,
            "tier_key": tier,
            "result_code": "awarded",
        }


async def mint_member_qr(conn, *, brand_id: UUID, account_id: UUID) -> dict:
    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    async with conn.transaction():
        program = await conn.fetchrow(
            """SELECT p.status, b.name AS brand_name, b.plan_status
                 FROM tellus_loyalty_programs p
                 JOIN tellus_brands b ON b.id = p.brand_id
                WHERE p.brand_id = $1""",
            brand_id,
        )
        if program is None:
            raise LoyaltyError(404, "not_found", "Loyalty program not found.")
        if program["status"] != "active" or program["plan_status"] != "active":
            raise LoyaltyError(409, "inactive", "This loyalty program is not currently active.")
        row = await conn.fetchrow(
            """INSERT INTO tellus_loyalty_member_qr_sessions
                   (brand_id, account_id, token_hash, expires_at)
               VALUES ($1, $2, $3, NOW() + interval '60 seconds')
               ON CONFLICT (brand_id, account_id) WHERE consumed_at IS NULL
               DO UPDATE SET token_hash = EXCLUDED.token_hash,
                              expires_at = EXCLUDED.expires_at,
                              created_at = NOW()
               RETURNING expires_at""",
            brand_id,
            account_id,
            token_hash,
        )
    return {
        "token": token,
        "qr_payload": f"TU-LM1:{token}",
        "expires_at": row["expires_at"],
    }


async def _load_member_session(conn, raw_token: str) -> dict:
    token = extract_member_token(raw_token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = await conn.fetchrow(
        """SELECT q.*, p.status AS program_status, p.counter_mode,
                  b.plan_status, b.name AS brand_name
             FROM tellus_loyalty_member_qr_sessions q
             JOIN tellus_loyalty_programs p ON p.brand_id = q.brand_id
             JOIN tellus_brands b ON b.id = q.brand_id
            WHERE q.token_hash = $1
            FOR UPDATE""",
        token_hash,
    )
    if row is None:
        raise LoyaltyError(404, "not_found", "Member card not found.")
    return _row_dict(row)


async def _check_replayed_session(
    conn,
    session: dict,
    *,
    brand_id: UUID,
    store_id: UUID,
    event_key: str,
    actor_account_id: UUID | None,
    scanner_device_id: UUID | None,
    amount_cents: int | None,
) -> dict:
    same_context = (
        session["brand_id"] == brand_id
        and session["consumed_store_id"] == store_id
        and session["consumed_event_key"] == event_key
        and session["consumed_by_account_id"] == actor_account_id
        and session["consumed_scanner_id"] == scanner_device_id
        and session["purchase_amount_cents"] == amount_cents
    )
    if not same_context:
        raise LoyaltyError(409, "qr_replayed", "That member card was already used in another transaction.")
    balance = await _current_balance(conn, brand_id, session["account_id"])
    return {
        "awarded": session["awarded_points"] > 0,
        "points": session["awarded_points"],
        "points_balance": balance["points_balance"],
        "lifetime_points": balance["lifetime_points"],
        "tier_key": await _tier_for_balance(conn, brand_id, balance["lifetime_points"]),
        "result_code": "awarded",
    }


async def _record_counter_event(
    conn,
    *,
    brand_id: UUID,
    store_id: UUID,
    raw_member_token: str,
    event_key: LoyaltyEventKey,
    actor_account_id: UUID | None,
    scanner_device_id: UUID | None,
    amount_cents: int | None,
) -> dict:
    async with conn.transaction():
        session = await _load_member_session(conn, raw_member_token)
        if session["brand_id"] != brand_id:
            raise LoyaltyError(404, "not_found", "Member card not found.")
        if session["expires_at"] <= _now() and session["consumed_at"] is None:
            raise LoyaltyError(410, "qr_expired", "That member card has expired.")
        if session["consumed_at"] is not None:
            return await _check_replayed_session(
                conn,
                session,
                brand_id=brand_id,
                store_id=store_id,
                event_key=event_key,
                actor_account_id=actor_account_id,
                scanner_device_id=scanner_device_id,
                amount_cents=amount_cents,
            )
        if session["program_status"] != "active" or session["plan_status"] != "active":
            raise LoyaltyError(409, "inactive", "This loyalty program is not currently active.")
        if session["counter_mode"] != event_key:
            raise LoyaltyError(409, "wrong_counter_mode", "This program uses a different counter action.")

        result = await award_event(
            conn,
            brand_id=brand_id,
            account_id=session["account_id"],
            event_key=event_key,
            reference_type="member_qr",
            reference_id=f"member_qr:{session['id']}",
            source_store_id=store_id,
            actor_account_id=actor_account_id,
            scanner_device_id=scanner_device_id,
            purchase_amount_cents=amount_cents,
            description="Visit recorded" if event_key == "visit" else "Purchase recorded",
        )
        await conn.execute(
            """UPDATE tellus_loyalty_member_qr_sessions
                  SET consumed_at = NOW(), consumed_store_id = $2,
                      consumed_event_key = $3, consumed_by_account_id = $4,
                      consumed_scanner_id = $5, purchase_amount_cents = $6,
                      awarded_points = $7, balance_after = $8
                WHERE id = $1""",
            session["id"],
            store_id,
            event_key,
            actor_account_id,
            scanner_device_id,
            amount_cents,
            result["points"],
            result["points_balance"],
        )
        return result


async def record_visit(conn, *, scanner: Mapping[str, object], raw_member_token: str) -> dict:
    return await _record_counter_event(
        conn,
        brand_id=scanner["brand_id"],
        store_id=scanner["store_id"],
        raw_member_token=raw_member_token,
        event_key="visit",
        actor_account_id=None,
        scanner_device_id=scanner["id"],
        amount_cents=None,
    )


async def record_purchase(
    conn,
    *,
    brand,
    store,
    raw_member_token: str,
    amount_cents: int,
) -> dict:
    return await _record_counter_event(
        conn,
        brand_id=brand.brand_id,
        store_id=store.store_id,
        raw_member_token=raw_member_token,
        event_key="purchase",
        actor_account_id=brand.account.id,
        scanner_device_id=None,
        amount_cents=amount_cents,
    )


async def create_reward(conn, *, brand_id: UUID, actor_account_id: UUID, data: LoyaltyRewardCreate) -> dict:
    row = await conn.fetchrow(
        """INSERT INTO tellus_loyalty_rewards
               (brand_id, title, description, terms, points_cost,
                redemption_expiry_days, active_from, active_to, is_active, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
           RETURNING *""",
        brand_id, data.title, data.description, data.terms, data.points_cost,
        data.redemption_expiry_days, data.active_from, data.active_to,
        data.is_active, actor_account_id,
    )
    return _row_dict(row)


async def list_rewards(conn, brand_id: UUID, *, include_inactive: bool) -> list[dict]:
    rows = await conn.fetch(
        """SELECT * FROM tellus_loyalty_rewards
            WHERE brand_id = $1 AND ($2 OR is_active)
            ORDER BY created_at DESC""",
        brand_id,
        include_inactive,
    )
    return [_row_dict(row) for row in rows]


_REWARD_PATCH_COLUMNS = (
    "title", "description", "terms", "points_cost", "redemption_expiry_days",
    "active_from", "active_to", "is_active",
)


async def patch_reward(conn, *, brand_id: UUID, reward_id: UUID, actor_account_id: UUID, data: LoyaltyRewardPatch) -> dict:
    values = []
    sets = []
    for column in _REWARD_PATCH_COLUMNS:
        if column not in data.model_fields_set:
            continue
        values.append(getattr(data, column))
        sets.append(f"{column} = ${len(values) + 2}")
    if not sets:
        row = await conn.fetchrow(
            "SELECT * FROM tellus_loyalty_rewards WHERE id = $1 AND brand_id = $2",
            reward_id, brand_id,
        )
        if row is None:
            raise LoyaltyError(404, "not_found", "Reward not found.")
        return _row_dict(row)
    row = await conn.fetchrow(
        f"""UPDATE tellus_loyalty_rewards
               SET {', '.join(sets)}, updated_at = NOW()
             WHERE id = $1 AND brand_id = $2
             RETURNING *""",
        reward_id, brand_id, *values,
    )
    if row is None:
        raise LoyaltyError(404, "not_found", "Reward not found.")
    return _row_dict(row)


async def issue_redemption(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    reward_id: UUID,
    client_request_id: UUID,
) -> dict:
    async with conn.transaction():
        existing = await conn.fetchrow(
            """SELECT r.*, b.name AS brand_name
                 FROM tellus_loyalty_redemptions r
                 JOIN tellus_brands b ON b.id = r.brand_id
                WHERE r.brand_id = $1 AND r.account_id = $2 AND r.client_request_id = $3""",
            brand_id, account_id, client_request_id,
        )
        if existing is not None:
            item = _row_dict(existing)
            item["effective_status"] = effective_redemption_status(item["status"], item["expires_at"])
            item["qr_payload"] = f"TU-LR1:{item['token']}"
            return item

        program = await conn.fetchrow(
            """SELECT p.status, b.plan_status, b.name AS brand_name
                 FROM tellus_loyalty_programs p JOIN tellus_brands b ON b.id = p.brand_id
                WHERE p.brand_id = $1 FOR UPDATE OF p""",
            brand_id,
        )
        if program is None or program["status"] != "active" or program["plan_status"] != "active":
            raise LoyaltyError(409, "inactive", "This loyalty program is not currently active.")
        reward = await conn.fetchrow(
            """SELECT * FROM tellus_loyalty_rewards
                WHERE id = $1 AND brand_id = $2 AND is_active
                  AND (active_from IS NULL OR active_from <= NOW())
                  AND (active_to IS NULL OR active_to > NOW())
                FOR UPDATE""",
            reward_id, brand_id,
        )
        if reward is None:
            raise LoyaltyError(404, "not_found", "Reward not found or unavailable.")
        balance = await conn.fetchrow(
            """SELECT points_balance FROM tellus_loyalty_balances
                WHERE brand_id = $1 AND account_id = $2 FOR UPDATE""",
            brand_id, account_id,
        )
        if balance is None or balance["points_balance"] < reward["points_cost"]:
            raise LoyaltyError(409, "insufficient_points", "You do not have enough loyalty points.")

        token = secrets.token_urlsafe(24)
        redemption = await conn.fetchrow(
            """INSERT INTO tellus_loyalty_redemptions
                   (brand_id, account_id, reward_id, client_request_id, token,
                    reward_title, points_spent, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7,
                       NOW() + make_interval(days => $8))
               RETURNING *""",
            brand_id, account_id, reward_id, client_request_id, token,
            reward["title"], reward["points_cost"], reward["redemption_expiry_days"],
        )
        new_balance = balance["points_balance"] - reward["points_cost"]
        await conn.execute(
            """INSERT INTO tellus_loyalty_ledger
                   (brand_id, account_id, delta, balance_after, reason,
                    reference_type, reference_id, description)
               VALUES ($1, $2, $3, $4, 'redeem', 'loyalty_redemption', $5, $6)""",
            brand_id, account_id, -reward["points_cost"], new_balance,
            str(redemption["id"]), f"Redeemed: {reward['title']}",
        )
        await conn.execute(
            """UPDATE tellus_loyalty_balances
                  SET points_balance = $3, updated_at = NOW()
                WHERE brand_id = $1 AND account_id = $2""",
            brand_id, account_id, new_balance,
        )
        item = _row_dict(redemption)
        item["brand_name"] = program["brand_name"]
        item["effective_status"] = effective_redemption_status(item["status"], item["expires_at"])
        item["qr_payload"] = f"TU-LR1:{item['token']}"
        return item


async def redeem_reward(conn, *, brand, store, raw_redemption_token: str) -> dict:
    token = extract_redemption_token(raw_redemption_token)
    row = await conn.fetchrow(
        """UPDATE tellus_loyalty_redemptions
              SET status = 'redeemed', redeemed_at = NOW(),
                  redeemed_store_id = $2, redeemed_by_account_id = $3
            WHERE token = $1 AND brand_id = $4 AND status = 'issued'
              AND expires_at > NOW()
            RETURNING reward_title, redeemed_at""",
        token,
        store.store_id,
        brand.account.id,
        brand.brand_id,
    )
    if row is None:
        raise LoyaltyError(409, "unavailable", "This loyalty reward is expired, used, or unavailable.")
    return {"reward_title": row["reward_title"], "redeemed_at": row["redeemed_at"], "store_name": store.store_name}


async def submit_social_post(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    data: LoyaltySocialSubmissionCreate,
) -> dict:
    program = await conn.fetchrow(
        """SELECT p.status, b.plan_status
             FROM tellus_loyalty_programs p JOIN tellus_brands b ON b.id = p.brand_id
            WHERE p.brand_id = $1""",
        brand_id,
    )
    if program is None:
        raise LoyaltyError(404, "not_found", "This brand does not have a loyalty program.")
    if program["status"] != "active" or program["plan_status"] != "active":
        raise LoyaltyError(409, "inactive", "This loyalty program is not currently active.")

    canonical = canonicalize_social_url(data.platform, data.post_url)
    row = await conn.fetchrow(
        """INSERT INTO tellus_loyalty_social_submissions
               (brand_id, account_id, platform, post_url, canonical_url, note)
           VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
           RETURNING *""",
        brand_id, account_id, data.platform, data.post_url, canonical, data.note,
    )
    if row is None:
        raise LoyaltyError(409, "duplicate_social_url", "That post has already been submitted.")
    return _row_dict(row)


async def list_social_submissions(conn, *, brand_id: UUID, account_id: UUID | None = None) -> list[dict]:
    if account_id is None:
        rows = await conn.fetch(
            """SELECT s.*, a.display_name
                 FROM tellus_loyalty_social_submissions s
                 JOIN tellus_accounts a ON a.id = s.account_id
                WHERE s.brand_id = $1 ORDER BY s.created_at DESC""",
            brand_id,
        )
    else:
        rows = await conn.fetch(
            """SELECT * FROM tellus_loyalty_social_submissions
                WHERE brand_id = $1 AND account_id = $2
                ORDER BY created_at DESC""",
            brand_id, account_id,
        )
    return [_row_dict(row) for row in rows]


async def withdraw_social_submission(conn, *, submission_id: UUID, account_id: UUID) -> None:
    row = await conn.fetchrow(
        """UPDATE tellus_loyalty_social_submissions
              SET status = 'withdrawn', updated_at = NOW()
            WHERE id = $1 AND account_id = $2 AND status = 'pending'
            RETURNING id""",
        submission_id, account_id,
    )
    if row is None:
        raise LoyaltyError(404, "not_found", "Pending social submission not found.")


async def decide_social_submission(
    conn,
    *,
    brand_id: UUID,
    submission_id: UUID,
    actor_account_id: UUID,
    decision: str,
    note: str | None,
) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Invalid social decision")
    async with conn.transaction():
        row = await conn.fetchrow(
            """SELECT * FROM tellus_loyalty_social_submissions
                WHERE id = $1 AND brand_id = $2 AND status = 'pending'
                FOR UPDATE""",
            submission_id, brand_id,
        )
        if row is None:
            raise LoyaltyError(404, "not_found", "Pending social submission not found.")
        updated = await conn.fetchrow(
            """UPDATE tellus_loyalty_social_submissions
                  SET status = $3, decision_note = $4, decided_at = NOW(),
                      decided_by = $5,
                      awarded_points = CASE WHEN $3 = 'approved' THEN awarded_points ELSE 0 END,
                      updated_at = NOW()
                WHERE id = $1 AND brand_id = $2 AND status = 'pending'
                RETURNING *""",
            submission_id, brand_id, decision, note, actor_account_id,
        )
        if decision == "approved":
            result = await award_event(
                conn,
                brand_id=brand_id,
                account_id=row["account_id"],
                event_key="social_post",
                reference_type="social_submission",
                reference_id=f"social_submission:{submission_id}",
                actor_account_id=actor_account_id,
                description="Social post approved",
                bypass_cooldown=True,
            )
            await conn.execute(
                """UPDATE tellus_loyalty_social_submissions
                      SET awarded_points = $2, updated_at = NOW()
                    WHERE id = $1""",
                submission_id, result["points"],
            )
            updated = await conn.fetchrow(
                "SELECT * FROM tellus_loyalty_social_submissions WHERE id = $1",
                submission_id,
            )
        return _row_dict(updated)


async def get_program_config(conn, brand_id: UUID) -> dict:
    program = await conn.fetchrow(
        """SELECT p.*, b.name AS brand_name, b.slug AS brand_slug, b.plan_status
             FROM tellus_loyalty_programs p JOIN tellus_brands b ON b.id = p.brand_id
            WHERE p.brand_id = $1""",
        brand_id,
    )
    if program is None:
        raise LoyaltyError(404, "not_found", "Loyalty program not found.")
    rules = await conn.fetch(
        "SELECT * FROM tellus_loyalty_earning_rules WHERE brand_id = $1 ORDER BY event_key",
        brand_id,
    )
    tiers = await conn.fetch(
        "SELECT * FROM tellus_loyalty_tiers WHERE brand_id = $1 ORDER BY sort_order",
        brand_id,
    )
    rewards = await list_rewards(conn, brand_id, include_inactive=True)
    return {**_row_dict(program), "rules": [_row_dict(row) for row in rules], "tiers": [_row_dict(row) for row in tiers], "rewards": rewards}


async def get_public_program(conn, slug: str) -> dict:
    brand_id = await conn.fetchval(
        """SELECT p.brand_id
             FROM tellus_loyalty_programs p
             JOIN tellus_brands b ON b.id = p.brand_id
            WHERE b.slug = $1 AND p.status = 'active' AND b.plan_status = 'active'""",
        slug,
    )
    if brand_id is None:
        raise LoyaltyError(404, "not_found", "Loyalty program not found.")
    program = await get_program_config(conn, brand_id)
    program["rewards"] = [reward for reward in program["rewards"] if reward["is_active"]]
    return program


async def list_ledger(conn, *, brand_id: UUID, account_id: UUID, limit: int, offset: int) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, delta, balance_after, reason, event_key, reference_type,
                  reference_id, source_store_id, purchase_amount_cents,
                  description, created_at
             FROM tellus_loyalty_ledger
            WHERE brand_id = $1 AND account_id = $2
            ORDER BY created_at DESC LIMIT $3 OFFSET $4""",
        brand_id, account_id, limit, offset,
    )
    return [_row_dict(row) for row in rows]


async def list_redemptions(conn, *, account_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """SELECT r.*, b.name AS brand_name, b.slug AS brand_slug
             FROM tellus_loyalty_redemptions r
             JOIN tellus_brands b ON b.id = r.brand_id
            WHERE r.account_id = $1
            ORDER BY r.created_at DESC""",
        account_id,
    )
    result = []
    for row in rows:
        item = _row_dict(row)
        item["effective_status"] = effective_redemption_status(item["status"], item["expires_at"])
        item["qr_payload"] = f"TU-LR1:{item['token']}"
        result.append(item)
    return result


async def loyalty_summary(conn, brand_id: UUID) -> dict:
    row = await conn.fetchrow(
        """SELECT COUNT(*) AS members,
                  COALESCE(SUM(lb.lifetime_points), 0) AS points_issued,
                  COALESCE(SUM(lb.points_balance), 0) AS points_outstanding,
                  COUNT(*) FILTER (WHERE lb.lifetime_points >= t_gold.threshold_points) AS gold_members,
                  COUNT(*) FILTER (WHERE lb.lifetime_points >= t_silver.threshold_points
                                    AND lb.lifetime_points < t_gold.threshold_points) AS silver_members,
                  COUNT(*) FILTER (WHERE lb.lifetime_points < t_silver.threshold_points) AS bronze_members
             FROM tellus_loyalty_balances lb
             JOIN tellus_loyalty_tiers t_silver
               ON t_silver.brand_id = lb.brand_id AND t_silver.tier_key = 'silver'
             JOIN tellus_loyalty_tiers t_gold
               ON t_gold.brand_id = lb.brand_id AND t_gold.tier_key = 'gold'
            WHERE lb.brand_id = $1""",
        brand_id,
    )
    return _row_dict(row)


async def put_program_config(conn, *, brand_id: UUID, actor_account_id: UUID, data: LoyaltyProgramPut) -> dict:
    if data.status == "active":
        active_reward = await conn.fetchval(
            """SELECT 1 FROM tellus_loyalty_rewards
                WHERE brand_id = $1 AND is_active
                  AND (active_from IS NULL OR active_from <= NOW())
                  AND (active_to IS NULL OR active_to > NOW())""",
            brand_id,
        )
        if not active_reward:
            raise LoyaltyError(409, "reward_required", "Add an active reward before publishing the program.")

    async with conn.transaction():
        previous = await conn.fetchrow(
            "SELECT status, activated_at FROM tellus_loyalty_programs WHERE brand_id = $1 FOR UPDATE",
            brand_id,
        )
        activated_at = None
        if data.status in {"active", "paused"}:
            activated_at = previous["activated_at"] if previous else None
            if activated_at is None:
                activated_at = _now()
        await conn.execute(
            """INSERT INTO tellus_loyalty_programs
                   (brand_id, name, point_singular, point_plural, terms, status,
                    counter_mode, activated_at, created_by, updated_by)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (brand_id) DO UPDATE SET
                   name = EXCLUDED.name, point_singular = EXCLUDED.point_singular,
                   point_plural = EXCLUDED.point_plural, terms = EXCLUDED.terms,
                   status = EXCLUDED.status, counter_mode = EXCLUDED.counter_mode,
                   activated_at = EXCLUDED.activated_at, updated_by = EXCLUDED.updated_by,
                   updated_at = NOW()""",
            brand_id, data.name, data.point_singular, data.point_plural, data.terms,
            data.status, data.counter_mode, activated_at, actor_account_id, actor_account_id,
        )
        await conn.execute("DELETE FROM tellus_loyalty_earning_rules WHERE brand_id = $1", brand_id)
        for rule in data.rules:
            await conn.execute(
                """INSERT INTO tellus_loyalty_earning_rules
                       (brand_id, event_key, award_type, fixed_points, points_per_dollar,
                        min_purchase_cents, max_points_per_event, daily_cap,
                        cooldown_seconds, is_active)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                brand_id, rule.event_key, rule.award_type, rule.fixed_points,
                rule.points_per_dollar, rule.min_purchase_cents,
                rule.max_points_per_event, rule.daily_cap,
                rule.cooldown_seconds, rule.is_active,
            )
        await conn.execute("DELETE FROM tellus_loyalty_tiers WHERE brand_id = $1", brand_id)
        for index, tier in enumerate(sorted(data.tiers, key=lambda item: {"bronze": 1, "silver": 2, "gold": 3}[item.tier_key]), start=1):
            await conn.execute(
                """INSERT INTO tellus_loyalty_tiers
                       (brand_id, tier_key, threshold_points, benefits, sort_order)
                   VALUES ($1, $2, $3, $4, $5)""",
                brand_id, tier.tier_key, tier.threshold_points, tier.benefits, index,
            )
        await conn.execute(
            """INSERT INTO tellus_brand_audit_events
                   (brand_id, actor_account_id, action, target_type, target_id, detail)
               VALUES ($1, $2, 'loyalty.program_updated', 'loyalty_program', $4, $3::jsonb)""",
            brand_id,
            actor_account_id,
            json.dumps({"status": data.status, "counter_mode": data.counter_mode}),
            str(brand_id),
        )
    return await get_program_config(conn, brand_id)


async def list_consumer_programs(conn, account_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """SELECT p.brand_id, b.name AS brand_name, b.slug AS brand_slug,
                  p.name, p.point_plural, p.status,
                  COALESCE(lb.points_balance, 0) AS points_balance,
                  COALESCE(lb.lifetime_points, 0) AS lifetime_points
             FROM tellus_loyalty_programs p
             JOIN tellus_brands b ON b.id = p.brand_id
             LEFT JOIN tellus_loyalty_balances lb
                    ON lb.brand_id = p.brand_id AND lb.account_id = $1
            WHERE p.status = 'active' AND b.plan_status = 'active'
            ORDER BY b.name""",
        account_id,
    )
    result = []
    for row in rows:
        item = _row_dict(row)
        item["tier_key"] = await _tier_for_balance(conn, row["brand_id"], row["lifetime_points"])
        result.append(item)
    return result


async def get_consumer_program(conn, *, account_id: UUID, brand_id: UUID) -> dict:
    program = await get_program_config(conn, brand_id)
    if program["status"] != "active" or program["plan_status"] != "active":
        raise LoyaltyError(404, "not_found", "Loyalty program not found.")
    balance = await _current_balance(conn, brand_id, account_id)
    program["balance"] = {
        **balance,
        "tier_key": await _tier_for_balance(conn, brand_id, balance["lifetime_points"]),
    }
    program["rewards"] = [reward for reward in program["rewards"] if reward["is_active"]]
    return program
