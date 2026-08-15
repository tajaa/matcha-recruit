"""Tell-Us rewards & gamification engine.

Everything that touches the points economy — earning, redeeming, streaks,
levels, badges — funnels through here so the invariants (idempotent ledger,
atomic debit under FOR UPDATE, balance == sum of ledger) live in one place.

Level curve: threshold(L) = 50·L·(L-1) cumulative lifetime points.
  L1=0  L2=100  L3=300  L4=600  L5=1000  L6=1500 …
"""
import json
import logging
import math
import secrets
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# reason values must match the tellus_points_ledger CHECK constraint.
EARN_REASONS = {"earn_feedback", "earn_engagement", "earn_grant"}


def level_for_points(lifetime: int) -> int:
    """Largest level L with threshold(L) <= lifetime. Always >= 1."""
    if lifetime <= 0:
        return 1
    # Solve 50L² - 50L - lifetime <= 0 → L = (50 + sqrt(2500 + 200·lifetime)) / 100
    lvl = int((50 + math.sqrt(2500 + 200 * lifetime)) // 100)
    return max(1, lvl)


def level_threshold(level: int) -> int:
    """Cumulative lifetime points required to reach `level`."""
    return 50 * level * (level - 1)


def level_progress(lifetime: int) -> dict:
    lvl = level_for_points(lifetime)
    floor = level_threshold(lvl)
    ceiling = level_threshold(lvl + 1)
    return {
        "level": lvl,
        "level_floor": floor,
        "level_ceiling": ceiling,
        "points_to_next_level": max(0, ceiling - lifetime),
    }


async def _ensure_balance(conn, account_id: UUID) -> None:
    await conn.execute(
        "INSERT INTO tellus_points_balances (account_id) VALUES ($1) ON CONFLICT DO NOTHING",
        account_id,
    )


async def check_and_award_badges(conn, account_id: UUID) -> list[str]:
    """Evaluate every badge criterion against the account's current stats and
    award any newly-earned ones. Returns the keys awarded this pass.

    Cheap enough to run after each earn/redeem: a handful of COUNT queries +
    ON CONFLICT DO NOTHING inserts. Idempotent."""
    defs = await conn.fetch("SELECT key, criteria FROM tellus_badge_definitions")
    if not defs:
        return []

    bal = await conn.fetchrow(
        "SELECT level, current_streak, longest_streak FROM tellus_points_balances WHERE account_id = $1",
        account_id,
    )
    feedback_count = await conn.fetchval(
        "SELECT COUNT(*) FROM tellus_reports WHERE reporter_account_id = $1", account_id
    ) or 0
    redeem_count = await conn.fetchval(
        "SELECT COUNT(*) FROM tellus_redemptions WHERE account_id = $1", account_id
    ) or 0

    level = bal["level"] if bal else 1
    streak = max(bal["current_streak"], bal["longest_streak"]) if bal else 0

    newly: list[str] = []
    for d in defs:
        crit = d["criteria"] or {}
        # asyncpg returns JSONB as a string unless a codec is registered on the
        # pool — decode defensively so both shapes work.
        if isinstance(crit, str):
            try:
                crit = json.loads(crit)
            except ValueError:
                continue
        ctype, threshold = crit.get("type"), crit.get("threshold", 0)
        met = (
            (ctype == "feedback_count" and feedback_count >= threshold)
            or (ctype == "streak" and streak >= threshold)
            or (ctype == "redeem_count" and redeem_count >= threshold)
            or (ctype == "level" and level >= threshold)
        )
        if not met:
            continue
        inserted = await conn.fetchval(
            """INSERT INTO tellus_user_badges (account_id, badge_key)
               VALUES ($1, $2) ON CONFLICT (account_id, badge_key) DO NOTHING
               RETURNING badge_key""",
            account_id,
            d["key"],
        )
        if inserted:
            newly.append(inserted)
    return newly


async def notify_account(conn, account_id: UUID, kind: str, title: str, body: str | None,
                  reference_type: str | None = None, reference_id: str | None = None,
                  slug: str | None = None, name: str | None = None,
                  suppress_push: bool = False) -> None:
    """Insert an in-app notification and (queue a) push it to the account's
    iOS devices. `slug`/`name` ride in the push payload so a tapped
    board-post / campaign push can deep-link to the right brand screen.
    `suppress_push=True` keeps the bell row but skips the device push — for
    notifications whose recipient is the acting user themselves (e.g. taking
    a conversation notifies the taker for the in-app bell, but shouldn't also
    buzz their own phone)."""
    await conn.execute(
        """INSERT INTO tellus_notifications (account_id, kind, title, body, reference_type, reference_id)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        account_id, kind, title, body, reference_type, reference_id,
    )
    if suppress_push:
        return
    from . import push
    push.schedule_push(
        [account_id], kind, title, body,
        reference_type=reference_type, reference_id=reference_id,
        slug=slug, name=name,
    )


async def award_points(
    conn,
    account_id: UUID,
    reason: str,
    *,
    event_key: Optional[str] = None,
    amount: Optional[int] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    notify: bool = True,
    bypass_cooldown: bool = False,
) -> dict:
    """Credit points to an account. Atomic + idempotent.

    Either `event_key` (looks up points + daily_cap + cooldown from
    tellus_earning_rules) OR an explicit `amount` must be given. `reason` must be
    one of the earn reasons (matches the ledger CHECK). Wrapped in a transaction
    (a savepoint if the caller is already in one), so a cap/cooldown/idempotency
    skip leaves no partial write.

    Returns {awarded, points, balance, lifetime, level, leveled_up, new_badges}.
    """
    if reason not in EARN_REASONS:
        raise ValueError(f"award_points reason must be an earn reason, got {reason!r}")

    result = {"awarded": False, "points": 0, "balance": 0, "lifetime": 0,
              "level": 1, "leveled_up": False, "new_badges": []}

    async with conn.transaction():
        await _ensure_balance(conn, account_id)

        # Resolve points + caps.
        rule = None
        if event_key is not None:
            rule = await conn.fetchrow(
                "SELECT points, daily_cap, cooldown_seconds, is_active "
                "FROM tellus_earning_rules WHERE event_key = $1",
                event_key,
            )
            if rule is None or not rule["is_active"]:
                return result  # unknown/inactive rule → no-op
            points = int(rule["points"])
        elif amount is not None:
            points = int(amount)
        else:
            raise ValueError("award_points needs event_key or amount")

        if points <= 0:
            return result

        # Idempotency pre-check (the partial unique index is the hard guarantee).
        if reference_id is not None:
            dup = await conn.fetchval(
                "SELECT 1 FROM tellus_points_ledger "
                "WHERE account_id = $1 AND reason = $2 AND reference_id = $3",
                account_id, reason, reference_id,
            )
            if dup:
                return result

        # Cooldown / daily cap — scoped by EVENT KEY, not reason. Several rules
        # share one reason ('earn_feedback'), and a single submission awards
        # more than one of them back-to-back in the same transaction; scoping
        # by reason made the earlier award trip the later rule's cooldown.
        # bypass_cooldown: a brand's explicit manual approval is itself the
        # anti-abuse gate — a rapid-fire cooldown must not eat the credit the
        # brand just granted. Daily cap + ledger idempotency still apply.
        if rule is not None:
            if rule["cooldown_seconds"] and not bypass_cooldown:
                recent = await conn.fetchval(
                    "SELECT 1 FROM tellus_points_ledger "
                    "WHERE account_id = $1 AND event_key = $2 AND delta > 0 "
                    "AND created_at > NOW() - ($3 || ' seconds')::interval LIMIT 1",
                    account_id, event_key, str(int(rule["cooldown_seconds"])),
                )
                if recent:
                    return result
            if rule["daily_cap"]:
                earned_today = await conn.fetchval(
                    "SELECT COALESCE(SUM(delta), 0) FROM tellus_points_ledger "
                    "WHERE account_id = $1 AND event_key = $2 AND delta > 0 "
                    "AND created_at::date = CURRENT_DATE",
                    account_id, event_key,
                ) or 0
                if earned_today >= rule["daily_cap"]:
                    return result
                # Clamp this award so we don't blow past the cap.
                points = min(points, int(rule["daily_cap"]) - int(earned_today))
                if points <= 0:
                    return result

        # Lock + debit/credit the balance atomically.
        bal = await conn.fetchrow(
            "SELECT points_balance, lifetime_points, level, current_streak, "
            "longest_streak, last_activity_date FROM tellus_points_balances "
            "WHERE account_id = $1 FOR UPDATE",
            account_id,
        )
        old_level = bal["level"]
        new_balance = bal["points_balance"] + points
        new_lifetime = bal["lifetime_points"] + points
        new_level = level_for_points(new_lifetime)

        # Streak: advance on a new UTC day, reset on a gap.
        last = bal["last_activity_date"]
        streak = bal["current_streak"]
        streak_sql = await conn.fetchrow(
            "SELECT CURRENT_DATE AS today, (CURRENT_DATE - 1) AS yday"
        )
        today, yday = streak_sql["today"], streak_sql["yday"]
        if last == today:
            new_streak = streak
        elif last == yday:
            new_streak = streak + 1
        else:
            new_streak = 1
        new_longest = max(bal["longest_streak"], new_streak)

        inserted = await conn.fetchval(
            """INSERT INTO tellus_points_ledger
                   (account_id, delta, balance_after, reason, event_key,
                    reference_type, reference_id, description)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (account_id, reason, reference_id) WHERE reference_id IS NOT NULL
               DO NOTHING
               RETURNING id""",
            account_id, points, new_balance, reason, event_key,
            reference_type, reference_id, description,
        )
        if inserted is None:
            return result  # race lost the idempotency check — no double credit

        await conn.execute(
            """UPDATE tellus_points_balances
               SET points_balance = $2, lifetime_points = $3, level = $4,
                   current_streak = $5, longest_streak = $6, last_activity_date = CURRENT_DATE,
                   updated_at = NOW()
               WHERE account_id = $1""",
            account_id, new_balance, new_lifetime, new_level, new_streak, new_longest,
        )

        new_badges = await check_and_award_badges(conn, account_id)

        if notify:
            await notify_account(
                conn, account_id, "points_earned", f"+{points} points",
                description or "You earned points.", reference_type, reference_id,
            )
            if new_level > old_level:
                await notify_account(conn, account_id, "level_up", f"Level {new_level}!",
                              f"You reached level {new_level}.")
            for bk in new_badges:
                await notify_account(conn, account_id, "badge", "New badge unlocked", bk,
                              "badge", bk)

        result.update(
            awarded=True, points=points, balance=new_balance, lifetime=new_lifetime,
            level=new_level, leveled_up=new_level > old_level, new_badges=new_badges,
        )
        return result


def _gen_code() -> str:
    """Short human-readable redemption code, e.g. 'TU-7F3K9Q2A'."""
    return "TU-" + secrets.token_hex(4).upper()


async def reclaim_expired_redemptions(conn, listing_id: Optional[UUID] = None) -> int:
    """Flip overdue 'issued' redemptions to terminal 'expired' and return their
    inventory to the listing. Points are forfeited by design (no ledger credit).
    Read-time derivation (effective_redemption_status) already shows these as
    expired; this makes it durable so quantity_claimed stops counting them."""
    row = await conn.fetchrow(
        """WITH flipped AS (
               UPDATE tellus_redemptions
               SET status = 'expired'
               WHERE status = 'issued' AND expires_at IS NOT NULL AND expires_at <= NOW()
                 AND ($1::uuid IS NULL OR listing_id = $1)
               RETURNING listing_id
           ), restored AS (
               UPDATE tellus_reward_listings l
               SET quantity_claimed = GREATEST(0, l.quantity_claimed - f.n), updated_at = NOW()
               FROM (SELECT listing_id, count(*) AS n FROM flipped GROUP BY listing_id) f
               WHERE l.id = f.listing_id
               RETURNING f.n
           )
           SELECT COALESCE(SUM(n), 0) AS n FROM restored""",
        listing_id,
    )
    return int(row["n"])


async def redeem_points(conn, account_id: UUID, listing_id: UUID) -> dict:
    """Atomically redeem a marketplace listing for points.

    Verifies balance and inventory under FOR UPDATE, debits, bumps
    quantity_claimed, and issues a redemption with a code. Raises RedeemError on
    insufficient balance / sold out / inactive listing. Returns the redemption
    row dict.
    """
    async with conn.transaction():
        await _ensure_balance(conn, account_id)
        await reclaim_expired_redemptions(conn, listing_id)

        listing = await conn.fetchrow(
            """SELECT id, title, points_cost, quantity_total, quantity_claimed,
                      redemption_type, is_active, active_from, active_to, expiry_days,
                      visibility, brand_id
               FROM tellus_reward_listings WHERE id = $1 FOR UPDATE""",
            listing_id,
        )
        if listing is None or not listing["is_active"]:
            raise RedeemError("This reward is not available.")

        if listing["visibility"] == "board":
            # Board-gated: approved membership required, checked inside the
            # same FOR-UPDATE transaction. A membership revoked mid-redeem is
            # benign — worst case one final redemption by a just-removed regular.
            # plan_status='active' too — a lapsed brand has no live dashboard to
            # counter-verify a redemption code, matching has_board on the public
            # page (see routes/community.py:public_brand_page).
            member = await conn.fetchval(
                """SELECT 1 FROM tellus_board_memberships m
                   JOIN tellus_boards bo ON bo.id = m.board_id
                   JOIN tellus_brands br ON br.id = bo.brand_id
                   WHERE bo.brand_id = $1 AND m.account_id = $2 AND m.status = 'approved'
                     AND bo.is_active AND br.plan_status = 'active'""",
                listing["brand_id"], account_id,
            )
            if not member:
                raise RedeemError("This reward is for board members.")

        # Active window.
        window_ok = await conn.fetchval(
            "SELECT (($1::timestamptz IS NULL OR NOW() >= $1) "
            "AND ($2::timestamptz IS NULL OR NOW() <= $2))",
            listing["active_from"], listing["active_to"],
        )
        if not window_ok:
            raise RedeemError("This reward is not currently active.")

        total = listing["quantity_total"]
        if total is not None and listing["quantity_claimed"] >= total:
            raise RedeemError("This reward is sold out.")

        cost = int(listing["points_cost"])
        bal = await conn.fetchrow(
            "SELECT points_balance FROM tellus_points_balances WHERE account_id = $1 FOR UPDATE",
            account_id,
        )
        if bal["points_balance"] < cost:
            raise RedeemError("You don't have enough points for this reward.")

        await conn.execute(
            "UPDATE tellus_reward_listings SET quantity_claimed = quantity_claimed + 1, "
            "updated_at = NOW() WHERE id = $1",
            listing_id,
        )

        code = _gen_code() if listing["redemption_type"] in ("code", "qr") else None
        expiry_days = int(listing["expiry_days"] or 30)
        redemption = await conn.fetchrow(
            """INSERT INTO tellus_redemptions
                   (account_id, listing_id, points_spent, status, code, issued_at, expires_at)
               VALUES ($1, $2, $3, 'issued', $4, NOW(), NOW() + make_interval(days => $5))
               RETURNING id, account_id, listing_id, points_spent, status, code,
                         issued_at, redeemed_at, expires_at, created_at""",
            account_id, listing_id, cost, code, expiry_days,
        )

        new_balance = bal["points_balance"] - cost
        await conn.execute(
            """INSERT INTO tellus_points_ledger
                   (account_id, delta, balance_after, reason, reference_type, reference_id, description)
               VALUES ($1, $2, $3, 'redeem', 'redemption', $4, $5)""",
            account_id, -cost, new_balance, str(redemption["id"]),
            f"Redeemed: {listing['title']}",
        )
        await conn.execute(
            "UPDATE tellus_points_balances SET points_balance = $2, updated_at = NOW() "
            "WHERE account_id = $1",
            account_id, new_balance,
        )

        await check_and_award_badges(conn, account_id)
        await notify_account(
            conn, account_id, "redemption", "Reward redeemed",
            f"You redeemed {listing['title']}.", "redemption", str(redemption["id"]),
        )
        return dict(redemption)


class RedeemError(Exception):
    """Raised when a redemption can't proceed (funds / inventory / window)."""


class AdjustError(Exception):
    """Manual adjustment can't proceed (overdraw / nothing to claw back)."""


def compute_adjustment(balance: int, lifetime: int, delta: int, *, clamp: bool = False) -> dict:
    """Pure math for an admin ledger adjustment. Credits mirror award_points
    (balance += delta, lifetime += delta). Debits reverse erroneous credits, so
    they reduce lifetime too (floored at 0) and level is recomputed — it CAN
    drop. Deliberately unlike 'redeem', which spends balance but leaves
    lifetime standing."""
    if delta == 0:
        raise ValueError("adjustment delta must be non-zero")
    applied = delta
    if delta < 0 and balance + delta < 0:
        if not clamp:
            raise AdjustError(f"Clawback of {-delta} exceeds balance of {balance}.")
        applied = -balance
        if applied == 0:
            raise AdjustError("Nothing to claw back — balance is already 0.")
    new_balance = balance + applied
    new_lifetime = max(0, lifetime + applied) if applied < 0 else lifetime + applied
    return {
        "applied_delta": applied,
        "new_balance": new_balance,
        "new_lifetime": new_lifetime,
        "new_level": level_for_points(new_lifetime),
    }


async def adjust_points(
    conn, account_id: UUID, delta: int, *,
    description: str, reference_id: Optional[str] = None,
    clamp: bool = False, notify: bool = True,
) -> dict:
    """Manual admin credit or clawback. reason='adjustment' (in the ledger
    CHECK since tellus_app_01, unused until now). Streaks NOT touched (an
    adjustment is not user activity); badges only checked on credit, never
    revoked on level-down (no removal path exists).

    Idempotency is checked up front (mirrors award_points) rather than caught
    as a UniqueViolationError: this is routinely called inside an already-open
    transaction (routes/admin/accounts.py), where a caught error leaves the
    enclosing SAVEPOINT aborted and the request 500s instead of returning
    adjusted=False."""
    async with conn.transaction():
        await _ensure_balance(conn, account_id)

        if reference_id is not None:
            dup = await conn.fetchval(
                "SELECT 1 FROM tellus_points_ledger "
                "WHERE account_id = $1 AND reason = 'adjustment' AND reference_id = $2",
                account_id, reference_id,
            )
            if dup:
                bal = await conn.fetchrow(
                    "SELECT points_balance, lifetime_points, level FROM tellus_points_balances "
                    "WHERE account_id = $1", account_id,
                )
                return {"adjusted": False, "applied_delta": 0,
                        "balance": bal["points_balance"], "lifetime": bal["lifetime_points"],
                        "level": bal["level"]}

        bal = await conn.fetchrow(
            "SELECT points_balance, lifetime_points, level FROM tellus_points_balances "
            "WHERE account_id = $1 FOR UPDATE", account_id,
        )
        plan = compute_adjustment(bal["points_balance"], bal["lifetime_points"], delta, clamp=clamp)
        inserted = await conn.fetchval(
            """INSERT INTO tellus_points_ledger
                   (account_id, delta, balance_after, reason, event_key,
                    reference_type, reference_id, description)
               VALUES ($1, $2, $3, 'adjustment', NULL, 'admin_adjustment', $4, $5)
               ON CONFLICT (account_id, reason, reference_id) WHERE reference_id IS NOT NULL
               DO NOTHING
               RETURNING id""",
            account_id, plan["applied_delta"], plan["new_balance"], reference_id, description,
        )
        if inserted is None:
            return {"adjusted": False, "applied_delta": 0,
                    "balance": bal["points_balance"], "lifetime": bal["lifetime_points"],
                    "level": bal["level"]}
        await conn.execute(
            """UPDATE tellus_points_balances
               SET points_balance = $2, lifetime_points = $3, level = $4, updated_at = NOW()
               WHERE account_id = $1""",
            account_id, plan["new_balance"], plan["new_lifetime"], plan["new_level"],
        )
        if plan["applied_delta"] > 0:
            await check_and_award_badges(conn, account_id)
        if notify:
            await notify_account(conn, account_id, "points_adjustment",
                          f"{plan['applied_delta']:+d} points", description,
                          "admin_adjustment", reference_id)
        return {"adjusted": True, "applied_delta": plan["applied_delta"],
                "balance": plan["new_balance"], "lifetime": plan["new_lifetime"],
                "level": plan["new_level"]}
