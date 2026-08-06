# Tell-Us internal admin — user & business management (mechanical implementation plan)

## Context

The Tell-Us admin surface (this branch: `require_tellus_admin` allowlist gate + `/tellus/admin/updates`) gets real management tooling. Levers mostly exist without a surface: `tellus_accounts.status` never written after INSERT (suspension is free — login `auth.py:238`, refresh `:262-267`, bearer `dependencies.py:68` all refuse `status != 'active'` already); `tokens_valid_after` written only by self-logout (`auth.py:283`); ledger reason `'adjustment'` declared in CHECK, never used; `tellus_brands.claimed_at` dead schema; `plan_status` writable only by the Stripe webhook; cross-brand moderation gap flagged by `feedback.py:163-170`'s own docstring; `tellus_earning_rules` config table with no UI; Tell-Us has NO password-reset flow at all.

Scope (user-approved): accounts + brands + points/moderation + config editors + `tellus_admin_audit` audit trail.

Execution order = the 7 steps below, one commit each.

---

## STEP 1 — Migration `server/alembic/versions/tellus_app_08_admin_management.py`

Complete file (raw `op.execute` style, matches `tellus_app_06`):

```python
"""tellus_app_08 — internal admin management: audit trail, account status CHECK,
password reset tokens.

Revision ID: tellus_app_08
Revises: tellus_app_07
"""
from alembic import op

revision = "tellus_app_08"
down_revision = "tellus_app_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit trail: every admin mutation writes one row, same transaction.
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_admin_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            actor_email TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            detail JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_admin_audit_created ON tellus_admin_audit (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_admin_audit_target ON tellus_admin_audit (target_type, target_id)")

    # Account status vocabulary. status has DEFAULT 'active' and no writer since
    # tellus_app_01, so the UPDATE is a safety net, not a backfill.
    op.execute("UPDATE tellus_accounts SET status = 'active' WHERE status NOT IN ('active', 'suspended')")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_status
                CHECK (status IN ('active', 'suspended'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    # Password reset tokens — Tell-Us had no reset flow at all.
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_by_email TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_pw_reset_account ON tellus_password_reset_tokens (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_password_reset_tokens")
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_status")
    op.execute("DROP TABLE IF EXISTS tellus_admin_audit")
```

Commit FIRST, then `./scripts/migrate-dev.sh`. Prod later via `migrate-prod.sh` (user-run).

---

## STEP 2 — Services

### 2a. New file `server/app/tellus/services/admin_audit.py`

```python
"""Audit trail for Tell-Us internal admin mutations.

Call record_admin_action() inside the SAME transaction as the mutation so an
audit row never exists for a rolled-back write (and vice versa).
"""
import json
from typing import Any, Optional
from uuid import UUID

# Registry of every action name — the audit-viewer filter dropdown reads this.
ADMIN_ACTIONS = (
    "account.suspend", "account.unsuspend", "account.force_logout",
    "account.verify_email", "account.password_reset_issued", "account.points_adjust",
    "brand.plan_comp", "brand.plan_cancel", "brand.assign_owner",
    "report.moderate", "dm_thread.block", "dm_thread.unblock",
    "earning_rule.update", "badge.update", "listing.update",
)


def serialize_detail(detail: Optional[dict[str, Any]]) -> Optional[str]:
    """JSONB-safe serialization: UUID/datetime coerced via default=str.
    None passes through (NULL column). Pure — unit-tested."""
    if detail is None:
        return None
    return json.dumps(detail, default=str)


async def record_admin_action(
    conn, actor, action: str, target_type: str,
    target_id: Optional[str | UUID], detail: Optional[dict[str, Any]] = None,
) -> None:
    await conn.execute(
        """INSERT INTO tellus_admin_audit
               (actor_account_id, actor_email, action, target_type, target_id, detail)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
        actor.id, actor.email, action, target_type,
        str(target_id) if target_id is not None else None,
        serialize_detail(detail),
    )
```

### 2b. `points_service.py` — append after `redeem_points`

```python
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
    revoked on level-down (no removal path exists)."""
    async with conn.transaction():
        await _ensure_balance(conn, account_id)
        bal = await conn.fetchrow(
            "SELECT points_balance, lifetime_points, level FROM tellus_points_balances "
            "WHERE account_id = $1 FOR UPDATE", account_id,
        )
        plan = compute_adjustment(bal["points_balance"], bal["lifetime_points"], delta, clamp=clamp)
        try:
            await conn.execute(
                """INSERT INTO tellus_points_ledger
                       (account_id, delta, balance_after, reason, event_key,
                        reference_type, reference_id, description)
                   VALUES ($1, $2, $3, 'adjustment', NULL, 'admin_adjustment', $4, $5)""",
                account_id, plan["applied_delta"], plan["new_balance"], reference_id, description,
            )
        except asyncpg.UniqueViolationError:
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
            await _notify(conn, account_id, "points_adjustment",
                          f"{plan['applied_delta']:+d} points", description,
                          "admin_adjustment", reference_id)
        return {"adjusted": True, "applied_delta": plan["applied_delta"],
                "balance": plan["new_balance"], "lifetime": plan["new_lifetime"],
                "level": plan["new_level"]}
```

### 2c. Tests for step 2 — start `server/tests/tellus/test_admin_management.py`

`TestComputeAdjustment` (8 cases): credit raises balance+lifetime equally, level recomputes (`0,99,+1 → level 2`); debit drops level (`lifetime=300 L3, −201 → lifetime 99 L1`); lifetime floors 0 (`lifetime=10, balance=50, −20 → new_lifetime 0`); overdraw no-clamp → `AdjustError` (message contains both numbers); overdraw clamp → applied `-balance`, ends 0; clamp at balance 0 → `AdjustError`; `delta=0` → `ValueError`; grid invariant sweep (`new_balance == balance+applied >= 0`, `new_level == level_for_points(new_lifetime)`).
`TestSerializeDetail` (2): `None→None`; dict w/ UUID+datetime round-trips `json.loads` as strings.

---

## STEP 3 — Backend part 1: package restructure, models, accounts, reset-consume

### 3a. Restructure

```bash
mkdir server/app/tellus/routes/admin
git mv server/app/tellus/routes/admin.py server/app/tellus/routes/admin/updates.py
```

Fix `updates.py` relative imports (one level deeper): `from ...database` → `from ....database`; `from ..dependencies` → `from ...dependencies`.

New `routes/admin/__init__.py`:

```python
"""Tell-Us internal admin package. Every sub-router carries a router-level
Depends(require_tellus_admin); mutating endpoints ALSO take the dep as a
parameter to identify the actor for tellus_admin_audit (FastAPI caches the
dependency — one resolution per request)."""
from fastapi import APIRouter

from .accounts import router as accounts_router
from .audit import router as audit_router
from .brands import router as brands_router
from .economy import router as economy_router
from .moderation import router as moderation_router
from .updates import router as updates_router

router = APIRouter()
for _r in (updates_router, accounts_router, brands_router, moderation_router,
           economy_router, audit_router):
    router.include_router(_r)
```

`routes/__init__.py` unchanged (`from .admin import router as admin_router` resolves to the package).

**Every sub-router file starts:** `router = APIRouter(dependencies=[Depends(require_tellus_admin)])` — updates.py switches to this too (drop its per-route dependencies list).

### 3b. New `routes/admin/_shared.py` — pure filter builders

```python
from ..._shared import escape_like          # adjust relative depth: routes/_shared.py

def account_filter_sql(*, q=None, account_type=None, status=None, verified=None,
                       start_idx: int = 1) -> tuple[str, list]:
    """WHERE fragment (starting ' WHERE ' or '') + params, placeholders from
    start_idx. q ILIKEs email + display_name via escape_like."""
    clauses, params, i = [], [], start_idx
    if q:
        clauses.append(f"(a.email ILIKE ${i} OR a.display_name ILIKE ${i})")
        params.append(f"%{escape_like(q)}%"); i += 1
    if account_type:
        clauses.append(f"a.account_type = ${i}"); params.append(account_type); i += 1
    if status:
        clauses.append(f"a.status = ${i}"); params.append(status); i += 1
    if verified is not None:
        clauses.append("a.email_verified_at IS NOT NULL" if verified
                       else "a.email_verified_at IS NULL")
    return ((" WHERE " + " AND ".join(clauses)) if clauses else "", params)

def report_filter_sql(*, moderation_status=None, review_state=None, brand_id=None,
                      q=None, start_idx: int = 1) -> tuple[str, list]:
    """review_state filters the EFFECTIVE state (mirror of effective_review_state):
       published → r.review_state='held' AND r.publish_at IS NOT NULL AND r.publish_at <= NOW()
       held      → r.review_state='held' AND (r.publish_at IS NULL OR r.publish_at > NOW())
       withdrawn → r.review_state='withdrawn'"""
```

(Same clause/params/i pattern; `q` ILIKEs `r.title` + `r.description`; `brand_id` equality.)

### 3c. New `server/app/tellus/models/admin.py`

Pydantic v2. Full inventory (shapes compressed here — field lists as in the endpoint SQL below):

```python
ACCOUNT_STATUSES = ("active", "suspended")   # must match ck_tellus_accounts_status

class TellusAdminAccountSummary(BaseModel):
    id: UUID; email: str; display_name: Optional[str] = None
    account_type: Literal["consumer", "brand"]; status: str
    email_verified: bool; city: Optional[str] = None; state: Optional[str] = None
    created_at: datetime; points_balance: int = 0; report_count: int = 0
    brand_id: Optional[UUID] = None; brand_name: Optional[str] = None

class TellusAdminAccountList(BaseModel):
    items: list[TellusAdminAccountSummary]; total: int; limit: int; offset: int

class TellusAdminLedgerEntry(BaseModel):
    id: UUID; delta: int; balance_after: int; reason: str
    event_key: Optional[str] = None; reference_type: Optional[str] = None
    reference_id: Optional[str] = None; description: Optional[str] = None
    created_at: datetime

class TellusAdminAuditEntry(BaseModel):
    id: UUID; actor_email: str; action: str; target_type: str
    target_id: Optional[str] = None; detail: Optional[dict] = None; created_at: datetime

class TellusAdminAccountDetail(BaseModel):
    account: TellusAdminAccountSummary
    lifetime_points: int = 0; level: int = 1; current_streak: int = 0
    ledger: list[TellusAdminLedgerEntry] = []
    recent_reports: list[dict] = []; redemptions: list[dict] = []
    dm_threads: list[dict] = []; audit: list[TellusAdminAuditEntry] = []

class TellusAdminSuspendRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)

class TellusAdminPasswordResetResponse(BaseModel):
    reset_url: str; expires_in_minutes: int = 60

class TellusAdminPointsAdjust(BaseModel):
    delta: int
    description: str = Field(..., min_length=3, max_length=300)
    idempotency_key: Optional[str] = Field(None, max_length=80)
    clamp: bool = False
    @field_validator("delta")
    @classmethod
    def _nonzero_bounded(cls, v):
        if v == 0: raise ValueError("delta must be non-zero")
        if abs(v) > 100_000: raise ValueError("delta out of range")
        return v

class TellusAdminBrandSummary(BaseModel):
    id: UUID; name: str; slug: str
    plan_status: Literal["pending", "active", "past_due", "canceled"]
    source: Literal["signup", "consumer_added"]
    owner_account_id: Optional[UUID] = None; owner_email: Optional[str] = None
    location_count: int; store_count: int
    has_stripe_subscription: bool = False; created_at: datetime

class TellusAdminBrandList(BaseModel):
    items: list[TellusAdminBrandSummary]; total: int; limit: int; offset: int

class TellusAdminBrandDetail(BaseModel):
    brand: TellusAdminBrandSummary
    activated_at: Optional[datetime] = None; claimed_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None; stripe_subscription_id: Optional[str] = None
    stores: list[dict] = []; links: list[dict] = []; prompts: list[dict] = []
    report_stats: dict = {}; audit: list[TellusAdminAuditEntry] = []

class TellusAdminPlanAction(BaseModel):
    action: Literal["comp", "cancel"]; note: Optional[str] = Field(None, max_length=500)

class TellusAdminAssignOwner(BaseModel):
    account_id: UUID

class TellusAdminModerationUpdate(BaseModel):
    moderation_status: Literal["visible", "flagged", "removed"]
    note: Optional[str] = Field(None, max_length=500)

class TellusAdminDmThreadSummary(BaseModel):
    id: UUID; report_id: UUID; brand_name: str; consumer_email: str
    blocked: bool; message_count: int
    last_message_at: Optional[datetime] = None; created_at: datetime

class TellusAdminEarningRule(BaseModel):
    event_key: str; points: int; daily_cap: Optional[int] = None
    cooldown_seconds: Optional[int] = None; is_active: bool
    # NOTE: tellus_earning_rules has NO updated_at column — don't add one here.

class TellusAdminEarningRuleUpdate(BaseModel):
    # PATCH semantics via model_dump(exclude_unset=True): explicit null CLEARS
    # daily_cap/cooldown_seconds, absent leaves alone.
    points: Optional[int] = Field(None, ge=0, le=10_000)
    daily_cap: Optional[int] = Field(None, ge=0, le=100_000)
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=604_800)
    is_active: Optional[bool] = None

class TellusAdminBadge(BaseModel):
    key: str; name: str; description: Optional[str] = None
    icon: Optional[str] = None; criteria: dict = {}; sort_order: int = 0
    award_count: int = 0

class TellusAdminBadgeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=300)
    threshold: Optional[int] = Field(None, ge=1, le=100_000)   # jsonb_set on criteria

class TellusAdminListingUpdate(BaseModel):
    is_active: bool

class TellusPasswordResetConfirm(BaseModel):    # public consume endpoint
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)
```

### 3d. `routes/admin/accounts.py`

Structural template for EVERY mutating endpoint in this plan:

```python
@router.post("/admin/accounts/{account_id}/suspend")
async def suspend_account(
    account_id: UUID, body: TellusAdminSuspendRequest,
    admin: TellusAccount = Depends(require_tellus_admin),
):
    if account_id == admin.id:
        raise HTTPException(400, "You can't suspend your own account.")
    async with get_connection() as conn:
        async with conn.transaction():
            old = await conn.fetchrow("SELECT status FROM tellus_accounts WHERE id = $1", account_id)
            if old is None:
                raise HTTPException(404, "Account not found")
            await conn.execute(
                "UPDATE tellus_accounts SET status = 'suspended', updated_at = NOW() WHERE id = $1",
                account_id,
            )
            await record_admin_action(conn, admin, "account.suspend", "account", account_id,
                                      {"reason": body.reason, "previous_status": old["status"]})
    return {"status": "suspended"}
```

Endpoints + their core SQL:

**GET `/admin/accounts`** — query params `q, account_type, status, verified, limit (≤100, default 50), offset`:
```sql
SELECT a.id, a.email, a.display_name, a.account_type, a.status,
       (a.email_verified_at IS NOT NULL) AS email_verified, a.city, a.state, a.created_at,
       COALESCE(pb.points_balance, 0) AS points_balance,
       (SELECT COUNT(*) FROM tellus_reports r WHERE r.reporter_account_id = a.id) AS report_count,
       b.id AS brand_id, b.name AS brand_name
FROM tellus_accounts a
LEFT JOIN tellus_points_balances pb ON pb.account_id = a.id
LEFT JOIN tellus_brands b ON b.owner_account_id = a.id
{where}
ORDER BY a.created_at DESC LIMIT ${n} OFFSET ${n+1}
```
Plus `SELECT COUNT(*) FROM tellus_accounts a {where}` with the same params.

**GET `/admin/accounts/{id}`** — summary row (same SELECT, WHERE id) + balances row (lifetime/level/streak) + ledger `LIMIT 20 ORDER BY created_at DESC` + reports `LIMIT 10` (JOIN brands for name; fields id/brand_name/title/rating/review_state via `effective_review_state`/moderation_status/created_at) + redemptions `LIMIT 10` (JOIN listings for title) + dm_threads (JOIN brands; blocked = `blocked_at IS NOT NULL`) + audit `WHERE target_type='account' AND target_id=$1 LIMIT 10`.

**POST `/suspend`** (above) · **POST `/unsuspend`** (`SET status='active'`; audit `account.unsuspend`) · **POST `/force-logout`** (`SET tokens_valid_after = NOW(), updated_at = NOW()`; audit) · **POST `/verify-email`** (`SET email_verified_at = COALESCE(email_verified_at, NOW()), verification_token = NULL`; audit).

**POST `/password-reset`**:
```python
token = secrets.token_urlsafe(48)
await conn.execute(
    """INSERT INTO tellus_password_reset_tokens (account_id, token, expires_at, created_by_email)
       VALUES ($1, $2, NOW() + INTERVAL '1 hour', $3)""",
    account_id, token, admin.email)
await record_admin_action(conn, admin, "account.password_reset_issued", "account", account_id, None)
return TellusAdminPasswordResetResponse(reset_url=app_url(f"/reset-password?token={token}"))
```
`app_url` from `...services.email` (builds `https://{TELLUS_BASE_DOMAIN}/tellus{path}`, `email.py:23-25`). Token NEVER in the audit detail.

**POST `/points-adjust`** — body `TellusAdminPointsAdjust`; `reference_id = f"adm:{body.idempotency_key}" if body.idempotency_key else None`; call `adjust_points(...)`; `except AdjustError as e: raise HTTPException(409, str(e))` (`ValueError` → FastAPI 422 happens at the model already for delta bounds; keep a 422 mapping for safety); audit `account.points_adjust` w/ `{delta, applied_delta, description, balance_after}`. NOTE: `adjust_points` opens `conn.transaction()` itself (savepoint when nested) — call it inside the same `async with conn.transaction():` as the audit write so the two commit together.

### 3e. Public reset-consume — append to `routes/auth.py`

```python
@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: TellusPasswordResetConfirm):
    """Consume an admin-issued reset token: set the new password, burn the
    token, revoke all existing sessions."""
    password_hash = hash_password(body.new_password)   # sync bcrypt — same as signup (auth.py:85)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, account_id, expires_at, used_at FROM tellus_password_reset_tokens "
                "WHERE token = $1 FOR UPDATE", body.token)
            if row is None:
                raise HTTPException(400, "Invalid reset link.")
            if row["used_at"] is not None or row["expires_at"] < datetime.now(timezone.utc):
                raise HTTPException(410, "This reset link has expired or was already used.")
            await conn.execute(
                "UPDATE tellus_accounts SET password_hash = $2, tokens_valid_after = NOW(), "
                "updated_at = NOW() WHERE id = $1", row["account_id"], password_hash)
            await conn.execute(
                "UPDATE tellus_password_reset_tokens SET used_at = NOW() WHERE id = $1", row["id"])
```
No audit row (public endpoint, no actor — the mint is audited).

### 3f. Tests for step 3 (extend `test_admin_management.py`)

`TestFilterSql`: published/held/withdrawn fragments exact; placeholder numbering sequential from `start_idx` w/ params in order; `q="50%_off"` → `\%`/`\_` in the PARAM not the SQL; no filters → `("", [])`.
`TestAdminModels`: `TellusAdminPointsAdjust` rejects delta 0 / 100_001 / 2-char description, accepts valid clawback; `TellusAdminPlanAction` rejects `"pending"`; `TellusPasswordResetConfirm` rejects 7-char password + short token; `TellusAdminEarningRuleUpdate.model_dump(exclude_unset=True)` distinguishes absent vs explicit-null `daily_cap`; `ACCOUNT_STATUSES == ("active","suspended")` tripwire.

---

## STEP 4 — Backend part 2: brands, moderation, economy, audit

### 4a. `routes/admin/brands.py`

**GET `/admin/brands`** (`q` ILIKE name+slug, `plan_status`, `source`, paging):
```sql
SELECT b.id, b.name, b.slug, b.plan_status, b.source, b.owner_account_id,
       a.email AS owner_email, b.location_count,
       (SELECT COUNT(*) FROM tellus_stores s WHERE s.brand_id = b.id) AS store_count,
       (b.stripe_subscription_id IS NOT NULL) AS has_stripe_subscription, b.created_at
FROM tellus_brands b LEFT JOIN tellus_accounts a ON a.id = b.owner_account_id
{where} ORDER BY b.created_at DESC LIMIT $n OFFSET $n+1
```

**GET `/admin/brands/{id}`** — summary + `activated_at/claimed_at/stripe_customer_id/stripe_subscription_id`; stores (`id,name,city,state`); links (`id, is_active, revoked_at, created_at`); prompts (`id, prompt, position ORDER BY position`); report_stats:
```sql
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS last_30d,
       ROUND(AVG(rating) FILTER (WHERE moderation_status <> 'removed')::numeric, 2) AS avg_rating
FROM tellus_reports WHERE brand_id = $1
```
+ audit `target_type='brand' LIMIT 10`.

**POST `/admin/brands/{id}/plan`** — body `TellusAdminPlanAction`:
- `comp`: `UPDATE tellus_brands SET plan_status='active', activated_at=COALESCE(activated_at, NOW()), updated_at=NOW() WHERE id=$1`. Stripe fields untouched (webhook writes match on subscription id, can't clobber a comp).
- `cancel`: `SET plan_status='canceled'`; response `stripe_warning = f"Stripe subscription {sub_id} still exists — cancel it in the Stripe dashboard"` when `stripe_subscription_id IS NOT NULL`, else `None`. **This endpoint NEVER calls Stripe** — `stripe_webhook.py` stays the sole Stripe-state writer; billing continues until dashboard action (accepted trade-off).
- Audit `brand.plan_comp`/`brand.plan_cancel` w/ `{previous_status, note, stripe_subscription_id}`.

**POST `/admin/brands/{id}/assign-owner`** — body `{account_id}`. Guard sequence (each its own HTTPException):
1. brand exists, else 404;
2. `brand.owner_account_id IS NOT NULL` → 409 "already owned — reassignment not supported";
3. account exists, else 404;
4. `SELECT 1 FROM tellus_brands WHERE owner_account_id = $1` → 409 "account already owns a brand" (the `require_tellus_account` LEFT JOIN assumes ≤1 brand per account);
then in one transaction: `UPDATE tellus_accounts SET account_type='brand', updated_at=NOW() WHERE id=$1 AND account_type='consumer'` (capture whether it flipped); `UPDATE tellus_brands SET owner_account_id=$1, claimed_at=NOW(), updated_at=NOW() WHERE id=$2` (`source` unchanged — first-ever writer of `claimed_at`); audit `brand.assign_owner` w/ `{account_id, account_email, flipped_type}`.

### 4b. `routes/admin/moderation.py`

**GET `/admin/reports`** — `report_filter_sql` from `_shared`; `SELECT r.* FROM tellus_reports r {where} ORDER BY r.created_at DESC LIMIT/OFFSET` + COUNT; serialize via `serialize_reports(conn, rows)` (routes/_shared.py:160 — batched, mints presigned media URLs); zip in `brand_name` from one `SELECT id, name FROM tellus_brands WHERE id = ANY($1::uuid[])`. Response `{items: [{**report.model_dump(), "brand_name": ...}], total, limit, offset}`.

**PATCH `/admin/reports/{id}/moderation`** — mirror `feedback.py:174-190` WITHOUT the brand scoping: fetch row (404), `UPDATE tellus_reports SET moderation_status=$2, updated_at=NOW() WHERE id=$1 RETURNING *`; notify reporter via `points_service._notify` on transition **to** `removed` (msg "A Tell-Us admin removed your public review for a policy violation.") AND on `removed → visible` restore ("Your review was restored."); both only when `review_state IS NOT NULL AND reporter_account_id IS NOT NULL`. Audit `report.moderate` w/ `{from, to, note, brand_id}`. Return `serialize_report(conn, updated)`.

**GET `/admin/dm-threads`** (`brand_id`, `blocked` bool, paging):
```sql
SELECT t.id, t.report_id, b.name AS brand_name, a.email AS consumer_email,
       (t.blocked_at IS NOT NULL) AS blocked,
       (SELECT COUNT(*) FROM tellus_dm_messages m WHERE m.thread_id = t.id) AS message_count,
       t.last_message_at, t.created_at
FROM tellus_dm_threads t
JOIN tellus_brands b ON b.id = t.brand_id
JOIN tellus_accounts a ON a.id = t.consumer_account_id
{where} ORDER BY t.last_message_at DESC NULLS LAST LIMIT $n OFFSET $n+1
```

**GET `/admin/dm-threads/{id}/messages`** — `SELECT id, thread_id, sender_role, body, created_at, read_at FROM tellus_dm_messages WHERE thread_id=$1 ORDER BY created_at` — read-only, does NOT touch `read_at`.

**POST `/block`** — `SET blocked_at = COALESCE(blocked_at, NOW())` (idempotent, same shape as `dms.py:280`); **POST `/unblock`** — `SET blocked_at = NULL`. Audit both. Docstring on unblock: overrides a consumer's own block (no `blocked_by` column — UI confirm covers it).

### 4c. `routes/admin/economy.py`

**GET `/admin/earning-rules`** — `SELECT event_key, points, daily_cap, cooldown_seconds, is_active FROM tellus_earning_rules ORDER BY event_key` (NO updated_at column).
**PATCH `/admin/earning-rules/{event_key}`** — `body.model_dump(exclude_unset=True)`; build `SET` clause from present keys only (explicit null clears cap/cooldown); 404 unknown key; audit w/ before/after dicts. No create/delete (code references fixed event_keys — a new key is dead config).
**GET `/admin/badges`**:
```sql
SELECT d.key, d.name, d.description, d.icon, d.criteria, d.sort_order,
       (SELECT COUNT(*) FROM tellus_user_badges ub WHERE ub.badge_key = d.key) AS award_count
FROM tellus_badge_definitions d ORDER BY d.sort_order, d.key
```
(criteria decoded defensively: `json.loads` if str — same asyncpg-JSONB note as `points_service.py:86`.)
**PATCH `/admin/badges/{key}`** — name/description plain SET; threshold via `criteria = jsonb_set(criteria, '{threshold}', to_jsonb($n::int))`. Audit.
**GET `/admin/listings`** (`brand_id`, `active`, paging) — include platform listings (`brand_id IS NULL`); LEFT JOIN brand name; return points_cost, quantity_claimed/total, is_active, redemption_type.
**PATCH `/admin/listings/{id}`** — `SET is_active=$2, updated_at=NOW()`; `redeem_points` already refuses inactive (:305). Audit.

### 4d. `routes/admin/audit.py`

**GET `/admin/audit`** — filters `target_type/target_id/action`, `limit ≤100 default 50`, offset; `ORDER BY created_at DESC`; decode `detail` defensively (`json.loads` if str). Also expose `GET /admin/audit/actions` returning `ADMIN_ACTIONS` for the filter dropdown (or embed the constant client-side — implementer's pick; embedding avoids an endpoint).

### 4e. Gate-sweep test (append to `test_admin_management.py`)

```python
def test_every_admin_route_is_gated():
    from app.tellus.routes.admin import router
    from app.tellus.dependencies import require_tellus_admin
    for route in router.routes:
        deps = [d.call for d in route.dependant.dependencies]
        assert require_tellus_admin in deps, f"{route.path} is not admin-gated"
```
(Router-level `dependencies=[...]` land in `route.dependant.dependencies` — verify attribute path while writing; fallback is checking `route.dependencies`.)

---

## STEP 5 — Frontend part 1: types, routing, nav, accounts pages, reset page

### 5a. `client/tellus/src/api/types.ts` — append mirrors

`AdminAccountSummary`, `AdminAccountList`, `AdminLedgerEntry`, `AdminAccountDetail`, `AdminBrandSummary`, `AdminBrandList`, `AdminBrandDetail`, `AdminDmThreadSummary`, `AdminEarningRule`, `AdminBadge`, `AdminListing`, `AdminAuditEntry`, `AdminPasswordResetResponse{reset_url, expires_in_minutes}`, `AdminPointsAdjustResult{adjusted, applied_delta, balance, lifetime, level}`, `AdminReportItem = TellusReport & { brand_name: string | null }`. Strict TS, snake_case fields to match API.

### 5b. `App.tsx`

- Import `ResetPassword from './pages/ResetPassword'` + 6 admin pages.
- Public block (after `/verify`): `<Route path="/reset-password" element={<ResetPassword />} />`.
- Admin block (replace the single updates route, before `*` catch-all):
```tsx
<Route path="/admin/accounts" element={<AdminOnly><AdminAccounts /></AdminOnly>} />
<Route path="/admin/accounts/:id" element={<AdminOnly><AdminAccountDetail /></AdminOnly>} />
<Route path="/admin/brands" element={<AdminOnly><AdminBrands /></AdminOnly>} />
<Route path="/admin/brands/:id" element={<AdminOnly><AdminBrandDetail /></AdminOnly>} />
<Route path="/admin/moderation" element={<AdminOnly><AdminModeration /></AdminOnly>} />
<Route path="/admin/economy" element={<AdminOnly><AdminEconomy /></AdminOnly>} />
<Route path="/admin/updates" element={<AdminOnly><TellusAdminUpdates /></AdminOnly>} />
```

### 5c. `Layout.tsx`

```tsx
import { ..., Users, Building2, ShieldAlert, Coins, Sparkles } from 'lucide-react'

const ADMIN_NAV: NavItem[] = [
  { to: '/admin/accounts', label: 'Accounts', icon: Users },
  { to: '/admin/brands', label: 'Brands', icon: Building2 },
  { to: '/admin/moderation', label: 'Moderation', icon: ShieldAlert },
  { to: '/admin/economy', label: 'Economy', icon: Coins },
  { to: '/admin/updates', label: 'Updates', icon: Sparkles },
]
```
Desktop sidebar: render `baseNav`; if `account?.is_admin`, then divider `border-t border-tu-border my-2` + label `<div className="px-3 pb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-tu-faint">Internal</div>` + `ADMIN_NAV` links (same `navLinkClass`). Mobile bar: flat `const nav = account?.is_admin ? [...baseNav, ...ADMIN_NAV] : baseNav`. Remove the old single-item append (:53-55). NavLink prefix matching keeps `/admin/accounts` lit on `/admin/accounts/:id` (no `end` prop on admin items).

### 5d. `pages/admin/Accounts.tsx`

State: `q` (debounced 300ms via useEffect timer), `accountType/status/verified` Selects, `offset`; fetch `tellusApi.get<AdminAccountList>('/admin/accounts?' + new URLSearchParams(...))`. Render: filter row (Input + 3 Selects from ui.tsx) → `Card` list rows (email, display_name, type `Chip`, status `Chip` — suspended gets `tone="negative"` styling path, points tabular-nums, created date) → Prev/Next buttons gated on offset/total. Row `onClick={() => navigate(\`/admin/accounts/\${a.id}\`)}`.

### 5e. `pages/admin/AccountDetail.tsx`

`useParams` id, fetch `AdminAccountDetail`, `refresh()` helper re-fetches after every action. Cards:
1. **Header** — email + chips (type/status/verified).
2. **Actions** (`Card` w/ Button rows):
   - Suspend: `window.prompt('Reason (optional)')` → confirm → POST `/suspend`; Unsuspend plain confirm.
   - Force sign-out → confirm → POST.
   - Verify email (hidden when verified) → POST.
   - Generate reset link → POST, response URL into a readonly `<Input value={url} />` + Copy button (`navigator.clipboard.writeText`).
   - Adjust points: inline mini-form (delta number input, description Input, Clamp checkbox appears when delta<0); mint `crypto.randomUUID()` into a ref ON FORM OPEN (not per submit — that's the idempotency point); confirm on negative; on 409 show error text.
3. **Points** — balance/lifetime/level/streak stat row.
4. **Ledger** — 20 rows, delta rendered `text-tu-good`/`text-tu-bad` with `+`/`−`, reason `Chip`, description, date.
5. **Reviews / Redemptions / DM threads** — compact lists (reviews link nowhere v1; DM threads show blocked chip).
6. **Audit history** — action, actor_email, date, `<details>` for the JSON detail.

### 5f. `pages/ResetPassword.tsx` (public)

`useSearchParams` token; missing token → error state. Two password inputs (min 8, must match, inline validation), submit → `tellusPublicPost('/auth/reset-password', {token, new_password})`; 400/410 → error message from thrown Error; success state → "Password updated" + `<Link to="/login">`. Wrap in the same shell/layout Login.tsx uses (check its structure — reuse `AuthShell` if one exists, else copy Login's wrapper markup).

---

## STEP 6 — Frontend part 2: brands, moderation, economy pages

### 6a. `pages/admin/Brands.tsx`
Same list skeleton as Accounts: q + plan_status/source Selects; rows: name, slug mono, plan `Chip` (active→positive, past_due/canceled→negative, pending→neutral), source, `stores {store_count} / billed {location_count}` — mismatch wrapped `text-tu-bad`, owner_email or italic "unclaimed". Row click → detail.

### 6b. `pages/admin/BrandDetail.tsx`
1. **Info card** — slug, source, owner (link `/admin/accounts/{owner_account_id}` when present), activated_at/claimed_at, Stripe ids `font-mono text-xs`.
2. **Plan card** — status chip + buttons: Comp (shown unless active; confirm "Grant active plan without payment?") / Cancel (shown when active/past_due; confirm; if response `stripe_warning` → render warning banner `text-tu-accent` after).
3. **Assign owner** (rendered ONLY when `owner_account_id === null`) — Input searching `GET /admin/accounts?q=&account_type=consumer` (also brand-type accounts without brands are valid — search both, filter client-side on `brand_id === null`), result rows w/ pick button → confirm "This will convert the consumer account to a brand account and hand it this brand." → POST → refresh.
4. **Stores** (list + `billed: N` note) · **Links** (id short, active/revoked chip) · **Prompts** read-only.
5. **Report stats** — total / last 30d / avg rating.
6. **Audit history** — same component pattern as AccountDetail (worth extracting a tiny shared `AuditList` component in `pages/admin/` if trivial).

### 6c. `pages/admin/Moderation.tsx`
Local `tab: 'reviews' | 'dms'`.
- **Reviews tab**: filters (moderation_status Select, review_state Select incl. published/held/withdrawn, brand q Input) → fetch `/admin/reports?...`. Row: title, rating stars or dash, brand_name, chips (moderation_status, effective review_state), created. Expand row → summary/description + media thumbnails (presigned URLs from response) + per-row moderation `Select` + Apply Button (confirm when target is `removed`).
- **DMs tab**: fetch `/admin/dm-threads`; rows `brand_name ↔ consumer_email`, blocked `Chip`, message_count, last_message_at. Expand → lazy `GET /admin/dm-threads/{id}/messages` (once, cache in state), read-only bubbles (sender_role labels). Block/Unblock buttons (unblock confirm: "This may override a block the consumer set themselves.").

### 6d. `pages/admin/Economy.tsx`
Three stacked sections:
- **Earning rules** — row per rule: event_key mono label, points/daily_cap/cooldown number Inputs, Active toggle (checkbox); local dirty tracking (compare to fetched); per-row Save button enabled when dirty → PATCH with only changed fields; empty-string cap/cooldown input sends explicit `null` (clears).
- **Badges** — row per badge: icon, name Input, threshold Input (from `criteria.threshold`), award_count text; per-row Save → PATCH.
- **Listings** — rows: title, brand_name or "Platform", points_cost, `claimed/total`, active chip; Activate/Deactivate button (confirm on deactivate) → PATCH `{is_active}`.

---

## STEP 7 — Docs + wrap

- `server/app/tellus/CLAUDE.md`: layout section — `routes/admin/` package (accounts/brands/moderation/economy/audit/updates), `services/admin_audit.py`, `adjust_points` in points_service, password-reset flow, `tellus_admin_audit` semantics (audit row = same transaction as mutation).
- Root/server CLAUDE.md "Tell-Us internal admin" symbol-map entry: no longer "changelog only" — list the admin package + TELLUS_ADMIN_EMAILS note (already there).
- `AUTO_CHANGELOG_PLAN.md` untouched.

## Verification

1. `cd server && ./venv/bin/python -m pytest tests/tellus/ tests/changelog/ -q` — all green.
2. `cd client/tellus && npx tsc -p tsconfig.app.json --noEmit` clean.
3. Migration: commit → `./scripts/migrate-dev.sh` (rehearse via `MIGRATE_REHEARSAL=1` first if desired).
4. Manual sweep on dev (backend restart to load code; admin login = TELLUS_ADMIN_EMAILS member):
   - Gate: non-admin → redirect + API 403; every `/admin/*` route.
   - Suspend blocks login/refresh/bearer; self-suspend 400; unsuspend restores.
   - Force sign-out 401s a pre-existing session ("Session has been revoked").
   - Verify-email unblocks login for an unverified account.
   - Password reset loop: mint → copy URL → logged-out consume → old password dead, old sessions dead, token single-use (2nd → 410), garbage → 400.
   - Points: credit (+ledger row reason=adjustment, balance+lifetime+level up, notification); clawback level-drop; overdraw 409; clamp → exact 0; same idempotency_key twice → `adjusted:false`, one ledger row.
   - Brand comp → owner's dashboard unlocks (`require_paid_brand`); cancel returns stripe_warning when sub exists.
   - Assign owner: consumer flips to brand + claimed_at set; 409 on owned brand; 409 on account that owns one.
   - Moderation: removed hides review from `/tellus/b/{slug}` + notifies; restore notifies; effective-state filters correct vs future publish_at.
   - DM block refuses sends both sides; messages read doesn't flip participants' read_at.
   - Economy: rule points edit changes a real award amount; rule deactivate stops awards; listing deactivate hides from marketplace + redeem refuses.
   - Audit: one row per mutation, correct actor/action/target/detail; filters work.
5. Prod (user-run): `migrate-prod.sh` + normal deploy.

## Files touched

| File | Change |
|---|---|
| `server/alembic/versions/tellus_app_08_admin_management.py` | new — 3 schema items |
| `server/app/tellus/services/admin_audit.py` | new |
| `server/app/tellus/services/points_service.py` | +AdjustError, compute_adjustment, adjust_points |
| `server/app/tellus/models/admin.py` | new — all admin shapes |
| `server/app/tellus/routes/admin/` | new package: `__init__ _shared updates(moved) accounts brands moderation economy audit` |
| `server/app/tellus/routes/auth.py` | +POST /auth/reset-password |
| `server/tests/tellus/test_admin_management.py` | new — ~20 pure cases + gate sweep |
| `client/tellus/src/api/types.ts` | +admin mirrors |
| `client/tellus/src/App.tsx` | +7 admin routes, +/reset-password, imports |
| `client/tellus/src/components/Layout.tsx` | ADMIN_NAV section |
| `client/tellus/src/pages/ResetPassword.tsx` | new — public |
| `client/tellus/src/pages/admin/{Accounts,AccountDetail,Brands,BrandDetail,Moderation,Economy}.tsx` | new — 6 pages |
| `server/app/tellus/CLAUDE.md` + symbol map | docs |

## Locked design decisions (flag if wrong, else implement as stated)

1. Clawback reduces `lifetime_points` → level CAN drop (differs from redeem; badges never revoked).
2. Balances never negative; overdraw 409 unless `clamp`.
3. Status vocab = `active|suspended` CHECK; no soft-delete state.
4. Admin plan endpoints NEVER call Stripe; cancel with live sub returns warning only.
5. Assign-owner: unowned brands only, target must own no brand; no reassign/unassign.
6. Earning rules edit-only (no create/delete).
7. Admin DM unblock can override a consumer's own block (confirm covers; `blocked_by` column excluded).
8. `tellus_earning_rules` has no `updated_at` — models/SQL must not reference one.
