# Tell-Us Brand Loyalty: Technical Implementation Plan

## Scope

Add brand-authored loyalty programs to Tell-Us without changing the existing
global points economy or marketplace.

Locked product decisions:

- Loyalty balances and rewards are separate per brand.
- Programs are included in the existing paid brand plan.
- Brands self-serve program configuration.
- Counter earning uses exactly one mode per program: `visit` or `purchase`.
- An existing scanner device token can record visits only.
- Dollar amounts require an authenticated business member with
  `redemptions.redeem` and access to the selected store.
- V1 includes review, approved board reply, follow, and approved organic social
  post earning.
- Tiers are Bronze, Silver, and Gold based on lifetime brand points.
- Issued rewards remain redeemable after a plan lapse or program pause.
- Expired rewards forfeit spent points; no refund is issued.

The implementation must not write to or branch the following existing economy:

- `tellus_points_balances`
- `tellus_points_ledger`
- `tellus_reward_listings`
- `tellus_redemptions`

## File Map

### New backend files

| Path | Responsibility |
| --- | --- |
| `server/alembic/versions/tellus_app_29_brand_loyalty.py` | Additive schema migration, revises `tellus_app_28` |
| `server/app/tellus/models/loyalty.py` | Pydantic request and response models |
| `server/app/tellus/services/loyalty_service.py` | Validation, balance/ledger transactions, QR, rewards, social approval |
| `server/app/tellus/routes/loyalty.py` | Consumer and authenticated business routes |
| `server/app/tellus/routes/loyalty_public.py` | Public program and device-token visit routes |
| `server/tests/tellus/test_loyalty_models.py` | Pydantic and validation tests |
| `server/tests/tellus/test_loyalty_service.py` | Pure functions, fake connections, source guards |
| `server/tests/tellus/test_loyalty_routes.py` | Route dependency and request-shape tests |
| `server/tests/tellus/test_loyalty_hooks.py` | Review, board, and follow integration guards |
| `server/tests/tellus/test_loyalty_db_manual.py` | Explicit localhost-only concurrency tests |

### New web files

| Path | Responsibility |
| --- | --- |
| `client/tellus/src/api/loyalty.ts` | Typed API wrapper |
| `client/tellus/src/hooks/useBusinesses.tsx` | `/me/businesses` membership/capability state |
| `client/tellus/src/pages/consumer/Loyalty.tsx` | Consumer brand-program list |
| `client/tellus/src/pages/consumer/LoyaltyBrand.tsx` | One brand's balance, tiers, rewards, ledger |
| `client/tellus/src/pages/consumer/MemberCard.tsx` | Rotating member QR |
| `client/tellus/src/pages/consumer/LoyaltyRedemption.tsx` | Issued reward QR |
| `client/tellus/src/pages/brand/LoyaltyBuilder.tsx` | Self-serve configuration and rewards |
| `client/tellus/src/pages/brand/LoyaltyCounter.tsx` | Authenticated purchase and redemption counter |

### New iOS files

| Path | Responsibility |
| --- | --- |
| `platforms/ios/TellUs/Models/LoyaltyModels.swift` | Loyalty response models |
| `platforms/ios/TellUs/Models/BusinessAccessModels.swift` | Business membership/capability models |
| `platforms/ios/TellUs/Services/LoyaltyService.swift` | Consumer and counter API calls |
| `platforms/ios/TellUs/Services/BusinessAccessService.swift` | `/me/businesses` |
| `platforms/ios/TellUs/ViewModels/LoyaltyListViewModel.swift` | Consumer program list |
| `platforms/ios/TellUs/ViewModels/LoyaltyDetailViewModel.swift` | Program detail, rewards, submissions |
| `platforms/ios/TellUs/ViewModels/MemberCardViewModel.swift` | QR rotation and countdown |
| `platforms/ios/TellUs/ViewModels/LoyaltyCounterViewModel.swift` | Purchase and reward scanning |
| `platforms/ios/TellUs/Views/Consumer/Loyalty/` | Native loyalty consumer views |

### Existing backend files to modify

- `server/app/tellus/routes/__init__.py`: mount both loyalty routers.
- `server/app/tellus/services/feedback_service.py`: award brand review points.
- `server/app/tellus/services/board_service.py`: award brand board-reply points.
- `server/app/tellus/routes/places.py`: award brand follow points only on a new insert.
- `server/app/tellus/routes/community.py`: expose `has_loyalty` publicly.
- `server/app/tellus/models/tellus.py`: add `has_loyalty` to the public brand model.
- `server/app/tellus/models/promo.py`: extend scanner bootstrap response if needed.
- `server/app/tellus/routes/promo_public.py`: return loyalty scanner state if needed.
- `server/app/tellus/services/promo_service.py`: preserve existing promo behavior while sharing safe scanner resolution.
- `server/app/tellus/CLAUDE.md`: document loyalty invariants.

### Existing web/iOS files to modify

- `client/tellus/src/api/types.ts`: loyalty and business membership types.
- `client/tellus/src/main.tsx`: mount `BusinessProvider`.
- `client/tellus/src/App.tsx`: add routes and `BusinessCapabilityProtected`.
- `client/tellus/src/components/Layout.tsx`: add loyalty/counter navigation.
- `client/tellus/src/pages/Scan.tsx`: recognize member QR and record visit.
- `client/tellus/src/pages/PublicBrand.tsx`: add loyalty CTA.
- `platforms/ios/TellUs/App/AppState.swift`: load business memberships.
- `platforms/ios/TellUs/Models/BrandDetailModels.swift`: add `has_loyalty`.
- `platforms/ios/TellUs/Models/DeepLinkRoute.swift`: add loyalty destinations.
- `platforms/ios/TellUs/Views/Consumer/Market/MarketplaceHomeView.swift`: add loyalty section.
- `platforms/ios/TellUs/Views/Consumer/Brand/BrandDetailView.swift`: add loyalty CTA.
- `platforms/ios/TellUs/Views/Consumer/More/MoreView.swift`: add business counter access.
- `platforms/ios/TellUs/Views/Brand/Scan/BrandScanView.swift`: add loyalty modes.
- `platforms/ios/TellUs/ViewModels/BrandScanViewModel.swift`: dispatch loyalty payloads.

## Database Migration

Create `server/alembic/versions/tellus_app_29_brand_loyalty.py`:

```python
revision = "tellus_app_29"
down_revision = "tellus_app_28"
```

Create objects in this order:

1. Composite store index used by brand-scoped foreign keys.
2. `tellus_loyalty_programs`.
3. `tellus_loyalty_earning_rules`.
4. `tellus_loyalty_tiers`.
5. `tellus_loyalty_balances`.
6. `tellus_loyalty_member_qr_sessions`.
7. `tellus_loyalty_rewards`.
8. `tellus_loyalty_redemptions`.
9. `tellus_loyalty_social_submissions`.
10. `tellus_loyalty_ledger`.

### `tellus_loyalty_programs`

One row per brand. It is not created automatically for existing brands.

```sql
CREATE TABLE tellus_loyalty_programs (
    brand_id UUID PRIMARY KEY REFERENCES tellus_brands(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Rewards',
    point_singular TEXT NOT NULL DEFAULT 'point',
    point_plural TEXT NOT NULL DEFAULT 'points',
    terms TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused')),
    counter_mode TEXT NOT NULL DEFAULT 'purchase'
        CHECK (counter_mode IN ('visit', 'purchase')),
    activated_at TIMESTAMPTZ,
    created_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (status = 'draft' AND activated_at IS NULL)
        OR (status IN ('active', 'paused') AND activated_at IS NOT NULL)
    )
)
```

The service must require at least one active reward before publishing an
active program. The database does not need a cross-table trigger.

### `tellus_loyalty_earning_rules`

```sql
CREATE TABLE tellus_loyalty_earning_rules (
    brand_id UUID NOT NULL
        REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
    event_key TEXT NOT NULL CHECK (
        event_key IN (
            'visit', 'purchase', 'review',
            'board_reply', 'follow', 'social_post'
        )
    ),
    award_type TEXT NOT NULL CHECK (award_type IN ('fixed', 'per_dollar')),
    fixed_points INTEGER,
    points_per_dollar INTEGER,
    min_purchase_cents INTEGER,
    max_points_per_event INTEGER,
    daily_cap INTEGER,
    cooldown_seconds INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (brand_id, event_key),
    CHECK (daily_cap IS NULL OR daily_cap BETWEEN 1 AND 1000000),
    CHECK (cooldown_seconds IS NULL OR cooldown_seconds BETWEEN 0 AND 2592000)
)
```

Add a full shape check:

- `purchase` must be `per_dollar`, with `points_per_dollar`,
  `min_purchase_cents`, and `max_points_per_event` populated.
- Every other event must be `fixed`, with `fixed_points` populated.
- Unused fields must be null.

### `tellus_loyalty_tiers`

```sql
CREATE TABLE tellus_loyalty_tiers (
    brand_id UUID NOT NULL
        REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
    tier_key TEXT NOT NULL CHECK (tier_key IN ('bronze', 'silver', 'gold')),
    threshold_points INTEGER NOT NULL CHECK (threshold_points >= 0),
    benefits TEXT,
    sort_order SMALLINT NOT NULL,
    PRIMARY KEY (brand_id, tier_key),
    UNIQUE (brand_id, threshold_points),
    UNIQUE (brand_id, sort_order)
)
```

The service validates exactly three rows, `bronze=0`, and
`0 < silver < gold`.

### Balances and ledger

```sql
CREATE TABLE tellus_loyalty_balances (
    brand_id UUID NOT NULL
        REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
    account_id UUID NOT NULL
        REFERENCES tellus_accounts(id) ON DELETE CASCADE,
    points_balance INTEGER NOT NULL DEFAULT 0 CHECK (points_balance >= 0),
    lifetime_points INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_points >= 0),
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (brand_id, account_id),
    CHECK (points_balance <= lifetime_points)
)
```

```sql
CREATE TABLE tellus_loyalty_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL,
    account_id UUID NOT NULL,
    delta INTEGER NOT NULL CHECK (delta <> 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    reason TEXT NOT NULL CHECK (
        reason IN (
            'earn_visit', 'earn_purchase', 'earn_review',
            'earn_board_reply', 'earn_follow', 'earn_social_post',
            'redeem'
        )
    ),
    event_key TEXT,
    reference_type TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    source_store_id UUID,
    actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
    scanner_device_id UUID REFERENCES tellus_scanner_devices(id) ON DELETE SET NULL,
    purchase_amount_cents INTEGER,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (brand_id, account_id)
        REFERENCES tellus_loyalty_balances(brand_id, account_id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_store_id, brand_id)
        REFERENCES tellus_stores(id, brand_id)
        ON DELETE SET NULL,
    UNIQUE (brand_id, account_id, reason, reference_id)
)
```

Add indexes for account history, event cap queries, store reporting, and actor
reporting. Ledger writes must always use:

```sql
ON CONFLICT (...) DO NOTHING RETURNING id
```

Never catch `asyncpg.UniqueViolationError`; the service is called inside nested
transactions and a caught unique violation can leave a savepoint aborted.

### Member QR sessions

Store opaque token hashes, never account IDs or signed JWTs in the QR.

Required fields:

- `brand_id`, `account_id`
- `token_hash` unique SHA-256 hex
- `expires_at`, `consumed_at`
- consumed brand/store/event
- consumed actor account or scanner device
- purchase cents, awarded points, balance after

Indexes:

```sql
CREATE UNIQUE INDEX ux_tellus_loyalty_qr_unconsumed
ON tellus_loyalty_member_qr_sessions (brand_id, account_id)
WHERE consumed_at IS NULL;

CREATE INDEX ix_tellus_loyalty_qr_token
ON tellus_loyalty_member_qr_sessions (token_hash);
```

The token is valid for 60 seconds. Minting rotates the current unconsumed row.

### Rewards and redemptions

`tellus_loyalty_rewards` contains title, description, terms, points cost,
expiry days, active window, active flag, creator, and timestamps.

`tellus_loyalty_redemptions` contains:

- `brand_id`, `account_id`, `reward_id`
- `client_request_id` for consumer retry idempotency
- opaque unique redemption token
- reward title snapshot and points spent
- `issued|redeemed` stored state
- issued/expiry/redeemed timestamps
- redeeming store and actor

The API derives `expired` when an issued redemption is past `expires_at`.
Expiration does not refund points.

Redemptions issued before a billing lapse remain redeemable. The redemption
route therefore uses `paid=False` while still requiring
`redemptions.redeem`.

### Social submissions

Create `tellus_loyalty_social_submissions` with:

- brand/account foreign keys
- platform and HTTPS URL
- canonical URL
- optional note
- `pending|approved|rejected|withdrawn`
- decision note, actor, timestamp
- awarded points

Add a unique `(brand_id, canonical_url)` index. Never fetch submitted URLs.

## Backend Models

Create `server/app/tellus/models/loyalty.py`.

```python
LoyaltyProgramStatus = Literal['draft', 'active', 'paused']
LoyaltyCounterMode = Literal['visit', 'purchase']
LoyaltyEventKey = Literal[
    'visit', 'purchase', 'review', 'board_reply', 'follow', 'social_post'
]
LoyaltyTierKey = Literal['bronze', 'silver', 'gold']
LoyaltySocialPlatform = Literal[
    'instagram', 'tiktok', 'youtube', 'facebook', 'x', 'other'
]
```

```python
class LoyaltyEarningRuleIn(BaseModel):
    event_key: LoyaltyEventKey
    award_type: Literal['fixed', 'per_dollar']
    fixed_points: int | None = Field(default=None, ge=1, le=100_000)
    points_per_dollar: int | None = Field(default=None, ge=1, le=100)
    min_purchase_cents: int | None = Field(default=None, ge=1, le=1_000_000)
    max_points_per_event: int | None = Field(default=None, ge=1, le=100_000)
    daily_cap: int | None = Field(default=None, ge=1, le=1_000_000)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=2_592_000)
    is_active: bool = True
```

```python
class LoyaltyTierIn(BaseModel):
    tier_key: LoyaltyTierKey
    threshold_points: int = Field(ge=0, le=100_000_000)
    benefits: str | None = Field(default=None, max_length=2_000)
```

```python
class LoyaltyProgramPut(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    point_singular: str = Field(min_length=1, max_length=40)
    point_plural: str = Field(min_length=1, max_length=40)
    terms: str | None = Field(default=None, max_length=10_000)
    status: LoyaltyProgramStatus
    counter_mode: LoyaltyCounterMode
    rules: list[LoyaltyEarningRuleIn] = Field(min_length=6, max_length=6)
    tiers: list[LoyaltyTierIn] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def validate_complete_config(self) -> 'LoyaltyProgramPut':
        ...
```

The validator enforces:

- six unique event keys
- three unique tier keys
- Bronze threshold zero
- `silver < gold`
- correct fixed/per-dollar shape
- only the selected counter mode active

Additional models:

```python
class LoyaltyVisitIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    member_token: str = Field(min_length=1, max_length=512)

class LoyaltyPurchaseIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    member_token: str = Field(min_length=1, max_length=512)
    amount_cents: int = Field(ge=1, le=1_000_000)

class LoyaltyRedemptionCreate(BaseModel):
    reward_id: UUID
    client_request_id: UUID

class LoyaltySocialSubmissionCreate(BaseModel):
    platform: LoyaltySocialPlatform
    post_url: str = Field(min_length=8, max_length=2_048)
    note: str | None = Field(default=None, max_length=1_000)
```

`LoyaltyEarnOut` must return `awarded`, `points`, `points_balance`,
`lifetime_points`, `tier_key`, and a result code such as `awarded`,
`cooldown`, or `daily_cap`.

## Service Signatures

Create `server/app/tellus/services/loyalty_service.py`.

```python
class LoyaltyError(Exception):
    def __init__(
        self,
        http_status: int,
        code: str,
        message: str,
        extra: dict | None = None,
    ): ...
```

Pure functions:

```python
    amount_cents: int,
    points_per_dollar: int,
    max_points_per_event: int | None,
) -> int: ...

def tier_for_lifetime(
    tiers: Sequence[Mapping[str, object]],
    lifetime_points: int,
) -> str: ...

def effective_redemption_status(
    status: str,
    expires_at: datetime,
    now: datetime | None = None,
) -> str: ...

def extract_member_token(raw: str) -> str: ...
def extract_redemption_token(raw: str) -> str: ...
def canonicalize_social_url(platform: str, raw_url: str) -> str: ...
```

Program operations:

```python
async def get_public_program(conn, slug: str) -> dict: ...
async def get_program_config(conn, brand_id: UUID) -> dict: ...

async def put_program_config(
    conn,
    *,
    brand_id: UUID,
    actor_account_id: UUID,
    data: LoyaltyProgramPut,
) -> dict: ...

async def list_consumer_programs(conn, account_id: UUID) -> list[dict]: ...
async def get_consumer_program(conn, *, account_id: UUID, brand_id: UUID) -> dict: ...
```

Central earning function:

```python
async def award_event(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    event_key: LoyaltyEventKey,
    reference_type: str,
    reference_id: str,
    source_store_id: UUID | None = None,
    actor_account_id: UUID | None = None,
    scanner_device_id: UUID | None = None,
    purchase_amount_cents: int | None = None,
    description: str | None = None,
    bypass_cooldown: bool = False,
) -> dict: ...
```

Transaction order is mandatory:

1. Load active paid brand, program, and rule.
2. Return a no-op if no program/rule is active.
3. Insert the balance with `ON CONFLICT DO NOTHING`.
4. Lock the balance with `FOR UPDATE`.
5. Pre-check the stable ledger reference.
6. Query cooldown and daily cap scoped by brand, account, and `event_key`.
7. Calculate and clamp the award.
8. Insert ledger with `ON CONFLICT ... DO NOTHING RETURNING id`.
9. Update balance only if the ledger insert returned an ID.
10. Derive tier and enqueue the notification.

The balance lock must occur before cap/cooldown queries so concurrent distinct
events cannot exceed a daily cap.

QR functions:

```python
async def mint_member_qr(conn, *, brand_id: UUID, account_id: UUID) -> dict: ...

async def record_visit(
    conn,
    *,
    scanner: Mapping[str, object],
    raw_member_token: str,
) -> dict: ...

async def record_purchase(
    conn,
    *,
    brand: BrandAccessContext,
    store: StoreAccessContext,
    raw_member_token: str,
    amount_cents: int,
) -> dict: ...
```

QR payloads:

- Member: `TU-LM1:<opaque-token>`.
- Loyalty reward: `TU-LR1:<opaque-token>`.

Same-context retries return the stored outcome. Different store, actor, event,
or purchase amount returns `409 qr_replayed`. Expired tokens return `410`.
Cross-brand tokens return `404`.

Rewards:

```python
async def list_rewards(conn, brand_id: UUID, *, include_inactive: bool) -> list[dict]: ...

async def create_reward(
    conn,
    *,
    brand_id: UUID,
    actor_account_id: UUID,
    data: LoyaltyRewardCreate,
) -> dict: ...

async def patch_reward(
    conn,
    *,
    brand_id: UUID,
    reward_id: UUID,
    actor_account_id: UUID,
    data: LoyaltyRewardPatch,
) -> dict: ...

async def issue_redemption(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    reward_id: UUID,
    client_request_id: UUID,
) -> dict: ...

async def redeem_reward(
    conn,
    *,
    brand: BrandAccessContext,
    store: StoreAccessContext,
    raw_redemption_token: str,
) -> dict: ...
```

`issue_redemption()` locks reward then balance and performs debit, redemption
insert, ledger insert, and balance update atomically.

`redeem_reward()` uses one predicate-bearing update requiring issued status,
unexpired timestamp, and matching brand. It does not require an active billing
plan for already-issued rewards.

Social operations:

```python
async def submit_social_post(
    conn,
    *,
    brand_id: UUID,
    account_id: UUID,
    data: LoyaltySocialSubmissionCreate,
) -> dict: ...

async def list_consumer_social_submissions(
    conn, *, brand_id: UUID, account_id: UUID
) -> list[dict]: ...

async def list_brand_social_submissions(
    conn, *, brand_id: UUID, status_filter: str | None
) -> list[dict]: ...

async def withdraw_social_submission(
    conn, *, submission_id: UUID, account_id: UUID
) -> None: ...

async def decide_social_submission(
    conn,
    *,
    brand_id: UUID,
    submission_id: UUID,
    actor_account_id: UUID,
    decision: Literal['approved', 'rejected'],
    note: str | None,
) -> dict: ...
```

Approval and the brand-points award share one transaction. Social URLs are
parsed and canonicalized locally only.

## Routes

Define module-level dependencies in `routes/loyalty.py`:

```python
LOYALTY_MANAGER = require_brand_capability('rewards.manage')
LOYALTY_OPERATOR = require_brand_capability('redemptions.redeem')
LOYALTY_REDEEMER = require_brand_capability('redemptions.redeem', paid=False)
```

### Consumer routes

All consumer routes use `require_verified_consumer`:

```text
GET    /me/loyalty/programs
GET    /me/loyalty/programs/{brand_id}
POST   /me/loyalty/programs/{brand_id}/member-qr
GET    /me/loyalty/programs/{brand_id}/ledger
POST   /me/loyalty/programs/{brand_id}/redemptions
GET    /me/loyalty/redemptions
POST   /me/loyalty/programs/{brand_id}/social-submissions
GET    /me/loyalty/programs/{brand_id}/social-submissions
DELETE /me/loyalty/social-submissions/{submission_id}
```

### Builder routes

All use `LOYALTY_MANAGER`:

```text
GET   /businesses/{brand_id}/loyalty/program
PUT   /businesses/{brand_id}/loyalty/program
GET   /businesses/{brand_id}/loyalty/rewards
POST  /businesses/{brand_id}/loyalty/rewards
PATCH /businesses/{brand_id}/loyalty/rewards/{reward_id}
GET   /businesses/{brand_id}/loyalty/social-submissions
POST  /businesses/{brand_id}/loyalty/social-submissions/{id}/approve
POST  /businesses/{brand_id}/loyalty/social-submissions/{id}/reject
GET   /businesses/{brand_id}/loyalty/summary
```

### Authenticated counter routes

Use `LOYALTY_OPERATOR` and `resolve_store_access()`:

```text
POST /businesses/{brand_id}/stores/{store_id}/loyalty/purchase
POST /businesses/{brand_id}/stores/{store_id}/loyalty/redemptions/redeem
```

The purchase body accepts only `member_token` and integer `amount_cents`.

The redemption route uses `LOYALTY_REDEEMER`, allowing issued reward redemption
through a paused/lapsed brand while still requiring an authorized member and
store grant.

### Public routes

```text
GET  /b/{slug}/loyalty
POST /scan/{device_token}/loyalty/visit
```

The device-token visit route has no bearer dependency and must never accept an
amount field. Its response contains no consumer identity or purchase details.

Mount both routers in `server/app/tellus/routes/__init__.py`.

## Existing Activity Hooks

### Reviews

In `server/app/tellus/services/feedback_service.py:create_report()`:

- Keep existing global points behavior unchanged.
- For an identified `public_review`, call `award_event()` inside the existing
  transaction.
- Reference: `report:{report_id}`.
- Do not depend on `tellus_brands.reward_mode`.
- Private feedback and anonymous reviews do not receive brand points.

### Board replies

In `server/app/tellus/services/board_service.py:approve_reply_and_award()`:

- Return `brand_id` from the board/post join.
- Preserve the existing global award.
- Call `award_event()` with reference `board_reply:{reply_id}`.
- Keep `bypass_cooldown=True` for moderator approval.
- Admin force-approval must use the same stable reference.

### Follows

In `server/app/tellus/routes/places.py:follow_place()`:

- Change the follow insert to `RETURNING brand_id`.
- Award only when the insert returns a row.
- Reference: `brand_follow:{brand_id}`.
- Unfollow does not claw back points.

## Web Client

### Types

Add loyalty enums/interfaces to `client/tellus/src/api/types.ts`, including:

- `LoyaltyProgramStatus`
- `LoyaltyCounterMode`
- `LoyaltyEventKey`
- `LoyaltyTierKey`
- `BusinessMembership`
- `BusinessStoreGrant`
- all program, balance, ledger, reward, redemption, QR, social, and summary responses

### API wrapper

`client/tellus/src/api/loyalty.ts` exports:

```typescript
export const loyaltyApi = {
  listPrograms: () => Promise<LoyaltyProgramSummary[]>
  getProgram: (brandId: string) => Promise<LoyaltyProgramDetail>
  mintMemberQr: (brandId: string) => Promise<LoyaltyMemberQr>
  listLedger: (brandId: string, limit?: number, offset?: number) => Promise<LoyaltyLedgerEntry[]>
  issueRedemption: (brandId: string, rewardId: string, clientRequestId: string) => Promise<LoyaltyRedemption>
  listRedemptions: () => Promise<LoyaltyRedemption[]>
  submitSocial: (brandId: string, body: LoyaltySocialCreate) => Promise<LoyaltySocialSubmission>
  listMySocial: (brandId: string) => Promise<LoyaltySocialSubmission[]>
  withdrawSocial: (submissionId: string) => Promise<void>
  getBuilder: (brandId: string) => Promise<LoyaltyProgramDetail>
  saveBuilder: (brandId: string, body: LoyaltyProgramPut) => Promise<LoyaltyProgramDetail>
  listRewards: (brandId: string) => Promise<LoyaltyReward[]>
  createReward: (brandId: string, body: LoyaltyRewardCreate) => Promise<LoyaltyReward>
  patchReward: (brandId: string, rewardId: string, body: LoyaltyRewardPatch) => Promise<LoyaltyReward>
  listSocialQueue: (brandId: string, status?: string) => Promise<LoyaltySocialSubmission[]>
  approveSocial: (brandId: string, submissionId: string, note?: string) => Promise<LoyaltySocialSubmission>
  rejectSocial: (brandId: string, submissionId: string, note?: string) => Promise<LoyaltySocialSubmission>
  summary: (brandId: string) => Promise<LoyaltySummary>
  purchase: (brandId: string, storeId: string, memberToken: string, amountCents: number) => Promise<LoyaltyEarnResult>
  redeem: (brandId: string, storeId: string, redemptionToken: string) => Promise<LoyaltyRedeemResult>
  scannerVisit: (deviceToken: string, memberToken: string) => Promise<LoyaltyEarnResult>
}
```

### Business capability state

`useBusinesses.tsx` fetches `/me/businesses` after authentication and exposes:

```typescript
interface BusinessContextValue {
  memberships: BusinessMembership[]
  loading: boolean
  refresh: () => Promise<void>
  membershipFor: (brandId: string) => BusinessMembership | null
  can: (brandId: string, capability: BrandCapability) => boolean
}
```

`BusinessCapabilityProtected` checks navigation access only. Backend
dependencies remain authoritative.

### Routes

```text
/loyalty
/loyalty/:brandId
/loyalty/:brandId/card
/loyalty/redemptions/:token
/brand/:brandId/loyalty
/brand/:brandId/counter
```

`MemberCard.tsx` mints a QR on mount, refreshes 10 seconds before expiry, and
does not persist tokens. `LoyaltyCounter.tsx` selects accessible stores and
accepts decimal money as a string, converting to integer cents without
`parseFloat()`.

`Scan.tsx` keeps promo-card behavior unchanged. It recognizes `TU-LM1` and
calls the visit endpoint only; it never renders an amount field.

## iOS Client

`LoyaltyService.swift`:

```swift
final class LoyaltyService {
    static let shared = LoyaltyService()

    func programs() async throws -> [LoyaltyProgramSummary]
    func program(brandID: String) async throws -> LoyaltyProgramDetail
    func mintMemberQR(brandID: String) async throws -> LoyaltyMemberQR
    func ledger(brandID: String, limit: Int = 50, offset: Int = 0) async throws -> [LoyaltyLedgerEntry]
    func issueRedemption(brandID: String, rewardID: String, clientRequestID: UUID) async throws -> LoyaltyRedemption
    func redemptions() async throws -> [LoyaltyRedemption]
    func submitSocial(brandID: String, platform: String, postURL: String, note: String?) async throws -> LoyaltySocialSubmission
    func purchase(brandID: String, storeID: String, memberToken: String, amountCents: Int) async throws -> LoyaltyEarnResult
    func redeem(brandID: String, storeID: String, redemptionToken: String) async throws -> LoyaltyRedeemResult
}
```

`BusinessAccessService.swift`:

```swift
final class BusinessAccessService {
    static let shared = BusinessAccessService()
    func memberships() async throws -> [BusinessMembership]
}
```

`MemberCardViewModel` owns QR refresh and countdown. Reuse the existing
`QRCodeView`; no QR dependency is needed.

`LoyaltyCounterViewModel` recognizes:

```swift
    case member(String)
    case redemption(String)
    case unsupported
}

func loyaltyPayload(from raw: String) -> LoyaltyScannedPayload
```

Update `AppState` to load `/me/businesses`. Add loyalty to the consumer Rewards
section and expose the authenticated counter to consumer-typed staff with the
required capability.

## Test Plan

### `server/tests/tellus/test_loyalty_models.py`

- `test_program_requires_all_six_event_keys`
- `test_program_rejects_duplicate_event_key`
- `test_program_requires_exactly_three_tiers`
- `test_bronze_threshold_must_be_zero`
- `test_silver_must_be_below_gold`
- `test_purchase_rule_requires_per_dollar`
- `test_non_purchase_rule_rejects_per_dollar`
- `test_visit_mode_disables_purchase_rule`
- `test_purchase_mode_disables_visit_rule`
- `test_visit_body_rejects_amount_cents`
- `test_purchase_body_rejects_unknown_fields`
- `test_purchase_amount_rejects_zero`
- `test_purchase_amount_rejects_over_limit`

### `server/tests/tellus/test_loyalty_service.py`

Pure tests:

- `test_purchase_points_floor_partial_dollar`
- `test_purchase_points_apply_per_event_cap`
- `test_tier_below_silver_is_bronze`
- `test_tier_exact_silver_boundary`
- `test_tier_exact_gold_boundary`
- `test_issued_future_redemption_stays_issued`
- `test_issued_past_redemption_derives_expired`
- `test_redeemed_never_derives_expired`
- `test_extract_member_token_accepts_prefixed_payload`
- `test_extract_member_token_rejects_reward_payload`
- `test_social_url_rejects_http`
- `test_social_url_rejects_platform_host_mismatch`
- `test_social_url_strips_fragment_and_tracking_parameters`

Source/fake-connection guards:

- `test_award_locks_balance_before_cap_query`
- `test_award_caps_by_event_key_not_reason`
- `test_award_scopes_cap_by_brand_and_account`
- `test_award_uses_on_conflict_do_nothing_returning`
- `test_award_never_catches_unique_violation`
- `test_lost_idempotency_race_does_not_update_balance`
- `test_qr_replay_same_context_returns_stored_result`
- `test_qr_replay_changed_amount_returns_409`
- `test_qr_replay_changed_store_returns_409`
- `test_reward_redeem_is_one_predicate_bearing_update`
- `test_loyalty_service_never_mentions_global_points_tables`
- `test_loyalty_service_never_mentions_marketplace_tables`
- `test_jsonb_writes_use_json_dumps_and_cast`

### `server/tests/tellus/test_loyalty_routes.py`

- `test_consumer_routes_require_verified_consumer`
- `test_builder_routes_require_loyalty_manager`
- `test_purchase_route_requires_loyalty_operator`
- `test_redeem_route_uses_unpaid_loyalty_redeemer`
- `test_public_program_has_no_required_auth`
- `test_scanner_visit_has_no_bearer_dependency`
- `test_scanner_visit_request_cannot_carry_amount`
- `test_cross_brand_store_resolves_as_404`
- `test_suspended_member_resolves_as_404`

### `server/tests/tellus/test_loyalty_hooks.py`

- `test_review_hook_requires_identified_public_review`
- `test_private_feedback_does_not_award_brand_points`
- `test_review_hook_does_not_depend_on_reward_mode`
- `test_board_approval_returns_brand_id`
- `test_admin_reapproval_uses_same_stable_reference`
- `test_follow_insert_uses_returning`
- `test_follow_replay_does_not_award`
- `test_unfollow_has_no_clawback`
- `test_social_approval_and_award_share_transaction`

### Manual DB tests

Create `server/tests/tellus/test_loyalty_db_manual.py` with an explicit
environment guard:

```python
pytestmark = pytest.mark.skipif(
    os.getenv('TELLUS_LOYALTY_DB_TEST') != '1',
    reason='manual DB test; set TELLUS_LOYALTY_DB_TEST=1 explicitly',
)
```

Require localhost Postgres, reserved-domain accounts, and a rollback
transaction. Cases:

- concurrent same-QR consumption awards once
- changed amount replay is rejected
- concurrent distinct events do not exceed daily cap
- concurrent redemption issue cannot overdraw balance
- two staff cannot redeem one reward twice
- plan lapse blocks new earning but allows issued redemption
- pause preserves balance and history
- balance equals ledger delta sum
- global points and marketplace rows remain unchanged

### Web tests/checks

- `LoyaltyPayloadTests` for member/reward QR formats.
- Amount parsing rejects more than two decimals.
- `BusinessCapabilityProtected` hides unauthorized memberships.
- Member card refreshes before expiry and does not persist token.

### iOS tests

- `LoyaltyModelDecodeTests.testProgramDetailFixture`
- `LoyaltyModelDecodeTests.testExpiredRedemptionFixture`
- `LoyaltyPayloadTests.testMemberPayload`
- `LoyaltyPayloadTests.testRedemptionPayload`
- `LoyaltyPayloadTests.testPromoPayloadIsUnsupported`
- `LoyaltyAmountTests.testWholeDollarToCents`
- `LoyaltyAmountTests.testTwoDecimalPlaces`
- `LoyaltyAmountTests.testRejectsMoreThanTwoDecimals`
- `MemberCardViewModelTests.testRefreshesBeforeExpiry`
- `MemberCardViewModelTests.testStopsWhenDismissed`
- `BusinessCapabilityTests.testStaffCounterVisibility`
- `BusinessCapabilityTests.testSuspendedMembershipHidden`

## Delivery Order

1. Add migration, models, pure validation, and service primitives.
2. Add consumer and business routes with route gate tests.
3. Add QR scanner and redemption transaction paths.
4. Add review, board, follow, and social approval hooks.
5. Add web consumer wallet, member card, builder, and counter.
6. Add native iOS consumer and counter parity.
7. Run manual local-DB concurrency tests and migration rehearsal.
8. Update Tell-Us documentation with final invariants.

## Verification Commands

```bash
cd server && python3 -m pytest \
  tests/tellus/test_loyalty_models.py \
  tests/tellus/test_loyalty_service.py \
  tests/tellus/test_loyalty_routes.py \
  tests/tellus/test_loyalty_hooks.py -v
```

```bash
cd client/tellus && npx tsc -p tsconfig.app.json --noEmit
cd client/tellus && npm run build
```

```bash
cd platforms/ios/TellUs && make test
```

Apply the migration only to local development first:

```bash
./scripts/migrate-dev.sh
```

Do not apply `tellus_app_29` to production until the dev migration, manual
concurrency suite, backend tests, web build, and iOS tests pass.
