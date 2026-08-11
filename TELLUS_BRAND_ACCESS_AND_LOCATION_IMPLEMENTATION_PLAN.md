# Tell-Us Brand Access and Location Implementation Plan

## Status

Planning only. No schema or product code is implemented by this document.

## Objective

Allow multiple people to sign in and operate one brand, while ensuring all
customer-facing and operational work is tied to one physical store location.

The target model is:

```text
TellUs account (person)
  -> brand membership (role + capabilities)
    -> brand
      -> authorized stores
        -> feedback, Comms, promos, rewards, redemptions, scanners
```

An account can be a consumer and belong to multiple businesses. Brand access
comes from membership, rather than from `tellus_accounts.account_type` or the
single owner relationship on `tellus_brands`.

## Non-goals for the first delivery

- Per-location Boards. The existing Regulars Board remains brand-wide.
- Arbitrary customer-defined permission bundles. Roles provide defaults;
  capability overrides exist only to preserve existing moderator access safely.
- Deleting stores and their history. Stores will be archived instead.
- Encoding brand or role state in JWTs. Membership is checked on each request.

## Compatibility decisions

- Retain `tellus_brands.owner_account_id` during the rollout as a legacy
  ownership/billing pointer. It is not a source of authorization in new code.
- Retain `tellus_accounts.account_type`, `TellusAccount.brand_id`, and
  `can_manage_inbox` until legacy routes and mobile versions are retired.
- Preserve every existing moderator's exact Board and inbox rights using
  explicit capability grants. Do not convert moderators to `admin`.
- Keep old owner-only endpoints as temporary adapters through one mobile
  compatibility window; new web and iOS work uses canonical scoped routes.

## Data model

### Memberships

Modify `tellus_brand_members`:

```text
role             owner | admin | location_manager | staff
status           active | suspended | revoked
all_stores       boolean, default false
updated_at       timestamptz
suspended_at     timestamptz nullable
revoked_at       timestamptz nullable
```

Retain `UNIQUE (brand_id, account_id)` and the one-owner partial unique index.
`owner` and `admin` must have `all_stores = true`.

Role defaults:

| Role | Scope | Default access |
| --- | --- | --- |
| owner | all stores | all capabilities; ownership transfer |
| admin | all stores | billing, team, stores, and operations |
| location_manager | assigned stores | feedback, Comms, promos, listings, scanners, redemption |
| staff | assigned stores | feedback read, Comms read/reply, redemption |

Create `tellus_brand_member_stores`:

```text
member_id        FK tellus_brand_members(id) ON DELETE CASCADE
store_id         FK tellus_stores(id) ON DELETE CASCADE
created_at       timestamptz
PRIMARY KEY (member_id, store_id)
```

An empty assignment means no access, never all-store access.

Create `tellus_brand_member_capabilities`:

```text
member_id        FK tellus_brand_members(id) ON DELETE CASCADE
capability       text
effect           grant | deny
created_at       timestamptz
PRIMARY KEY (member_id, capability)
```

Capabilities:

```text
brand.update
billing.manage
team.manage
stores.manage
board.manage
feedback.read
feedback.manage
comms.read
comms.reply
comms.assign
comms.settings
promos.manage
scanners.manage
rewards.manage
redemptions.redeem
```

Effective capability calculation is `(role defaults + grants) - denies`.

### Invitations

Create:

```text
tellus_brand_invites
  id
  brand_id
  email
  role
  all_stores
  token_hash
  expires_at
  invited_by
  accepted_at
  accepted_by
  revoked_at
  created_at

tellus_brand_invite_stores
  invite_id
  store_id
  PRIMARY KEY (invite_id, store_id)
```

Constraints:

```sql
UNIQUE (token_hash);

UNIQUE (brand_id, lower(email))
WHERE accepted_at IS NULL AND revoked_at IS NULL;
```

Invite URLs are public only for preview. Acceptance requires an authenticated
Tell-Us account whose verified email matches the invite email.

### Store lifecycle and location ownership

Add to `tellus_stores`:

```text
status               active | archived
archived_at          timestamptz nullable
timezone             text nullable
messaging_enabled    boolean not null default false
```

Add `store_id` to:

```text
tellus_promo_campaigns
tellus_reward_listings
tellus_redemptions
```

Existing store-linked tables:

```text
tellus_links
tellus_reports
tellus_dm_threads
tellus_scanner_devices
tellus_promo_cards.redeemed_store_id
```

Add `UNIQUE (brand_id, id)` to `tellus_stores`, then composite foreign keys on
tables that carry both brand and store IDs:

```sql
FOREIGN KEY (brand_id, store_id)
REFERENCES tellus_stores (brand_id, id);
```

This prevents cross-brand store references at the database layer.

Platform-curated marketplace listings may have no brand or store. Business
listings require both:

```sql
CHECK (
  (brand_id IS NULL AND store_id IS NULL)
  OR
  (brand_id IS NOT NULL AND store_id IS NOT NULL)
);
```

Redemptions copy the listing's store ID and use a composite listing/store
foreign key. Promo redemption must require `campaign.store_id == scanner.store_id`.

## Migrations

### `tellus_app_19_brand_access.py`

```python
revision = "tellus_app_19"
down_revision = "tellus_app_18"
```

Creates membership status, role changes, member-store grants, capability
overrides, invitations, invitation-store grants, and `tellus_brand_audit_events`.

Backfill rules:

- Owner row: `owner`, `active`, `all_stores=true`.
- Existing moderator: `staff`, `active`, `all_stores=true`, explicit
  `board.manage` grant.
- Inbox-enabled moderator: also grant `comms.read`, `comms.reply`, and
  `comms.assign`.

### `tellus_app_20_location_scope.py`

Adds store lifecycle fields, location fields on campaigns/listings/redemptions,
and all additive indexes and foreign keys.

Backfill rules:

- Brand with exactly one active store: assign null operational resources to it.
- Brand with no stores: do not synthesize a store; block new operations until
  onboarding creates the first store.
- Brand with multiple stores and a null location:
  - pause campaign;
  - deactivate listing;
  - revoke feedback link;
  - preserve historical report/Comms access only for owner/admin until assigned.

### `tellus_app_21_location_constraints.py`

Run manually only after remediation is complete:

- `tellus_promo_campaigns.store_id SET NOT NULL`
- Business-owned listing store constraint
- Store required for new general Comms
- Store required for new claimed-brand feedback links
- Remove null-store Comms uniqueness paths

Before this migration, run the new read-only script:

`server/scripts/audit_tellus_location_scope.py`

It must report zero unresolved active resources and zero cross-brand store
references.

## Backend implementation

### New models and services

Create `server/app/tellus/models/access.py`:

```python
BrandRole = Literal["owner", "admin", "location_manager", "staff"]
BrandCapability = Literal[...]  # capability list above

class TellusBusinessMembership(BaseModel): ...
class TellusBusinessStoreGrant(BaseModel): ...
class TellusBrandInviteCreate(BaseModel): ...
class TellusBrandMemberUpdate(BaseModel): ...
class TellusOwnerTransfer(BaseModel): ...
```

Create `server/app/tellus/services/access_service.py`:

```python
@dataclass(frozen=True)
class BrandAccessContext:
    account: TellusAccount
    brand_id: UUID
    membership_id: UUID
    role: BrandRole
    plan_status: str
    all_stores: bool
    store_ids: frozenset[UUID]
    capabilities: frozenset[BrandCapability]


@dataclass(frozen=True)
class StoreAccessContext:
    brand: BrandAccessContext
    store_id: UUID
    store_name: str


def default_capabilities(role: BrandRole) -> frozenset[BrandCapability]: ...
def apply_capability_overrides(defaults, overrides) -> frozenset[BrandCapability]: ...
async def resolve_brand_access(conn, account_id: UUID, brand_id: UUID) -> BrandAccessContext: ...
async def resolve_store_access(conn, brand: BrandAccessContext, store_id: UUID) -> StoreAccessContext: ...
def assert_capability(context: BrandAccessContext, capability: BrandCapability) -> None: ...
def assert_paid_brand(context: BrandAccessContext) -> None: ...
def assert_resource_store(context: BrandAccessContext, resource_store_id: UUID | None) -> None: ...
```

Update `server/app/tellus/dependencies.py`:

```python
async def require_brand_context(
    brand_id: UUID,
    account: TellusAccount = Depends(require_tellus_account),
) -> BrandAccessContext: ...


def require_brand_capability(
    capability: BrandCapability,
    *,
    paid: bool = True,
) -> Callable[..., Awaitable[BrandAccessContext]]: ...


async def require_store_context(
    store_id: UUID,
    brand: BrandAccessContext = Depends(require_brand_context),
) -> StoreAccessContext: ...
```

No new business route may rely on `account.account_type` or `account.brand_id`.

Failure contract:

| Condition | Status |
| --- | --- |
| No active membership or foreign store/resource | 404 |
| Active membership lacks capability | 403 |
| Paid operation on inactive subscription | 402 |
| Legacy resource without location | 409, `location_required` |

### Team router

Create `server/app/tellus/routes/team.py` and register it in
`server/app/tellus/routes/__init__.py`.

```text
GET    /me/businesses

GET    /brands/{brand_id}/members
PATCH  /brands/{brand_id}/members/{member_id}
POST   /brands/{brand_id}/members/{member_id}/revoke
POST   /brands/{brand_id}/owner-transfer

GET    /brands/{brand_id}/invites
POST   /brands/{brand_id}/invites
POST   /brands/{brand_id}/invites/{invite_id}/resend
POST   /brands/{brand_id}/invites/{invite_id}/revoke

GET    /brand-invites/{token}
POST   /brand-invites/{token}/accept
```

Key signatures:

```python
async def invite_member(
    brand_id: UUID,
    body: TellusBrandInviteCreate,
    request: Request,
    background: BackgroundTasks,
    context: BrandAccessContext = Depends(require_brand_capability("team.manage", paid=False)),
) -> TellusBrandInvite: ...


async def update_member(
    brand_id: UUID,
    member_id: UUID,
    body: TellusBrandMemberUpdate,
    context: BrandAccessContext = Depends(require_brand_capability("team.manage", paid=False)),
) -> TellusBrandTeamMember: ...


async def accept_invite(
    token: str,
    account: TellusAccount = Depends(require_tellus_account),
) -> TellusBusinessMembership: ...
```

All access mutations and their audit event must be in the same transaction.

### Canonical business routes

| Area | Canonical route | Capability |
| --- | --- | --- |
| Brand profile | `/brands/{brand_id}` | `brand.update` for mutations |
| Billing | `/brands/{brand_id}/billing/*` | `billing.manage` |
| Stores | `/brands/{brand_id}/stores/*` | `stores.manage` |
| Prompts | `/brands/{brand_id}/prompts` | `brand.update` |
| Board | `/brands/{brand_id}/board/*` | `board.manage` |
| Feedback | `/brands/{brand_id}/stores/{store_id}/feedback/*` | `feedback.*` |
| Links | `/brands/{brand_id}/stores/{store_id}/links/*` | `stores.manage` |
| Comms | `/brands/{brand_id}/stores/{store_id}/comms/*` | `comms.*` |
| Promos | `/brands/{brand_id}/stores/{store_id}/promo/*` | `promos.manage` |
| Scanners | `/brands/{brand_id}/stores/{store_id}/scanners/*` | `scanners.manage` |
| Listings | `/brands/{brand_id}/stores/{store_id}/listings/*` | `rewards.manage` |
| Redemption verification | `/brands/{brand_id}/stores/{store_id}/redemptions/*` | `redemptions.redeem` |

Owner/admin aggregate reads can use brand-wide collection paths and require
`all_stores=true`. All mutations remain store-specific.

Existing files to convert:

```text
server/app/tellus/routes/links.py
server/app/tellus/routes/billing.py
server/app/tellus/routes/prompts.py
server/app/tellus/routes/feedback.py
server/app/tellus/routes/grants.py
server/app/tellus/routes/dms.py
server/app/tellus/routes/comms.py
server/app/tellus/routes/promo.py
server/app/tellus/routes/flyer_ai.py
server/app/tellus/routes/marketplace.py
server/app/tellus/routes/board.py
```

### Comms implementation

Public creation becomes:

```python
@router.post("/comms/brands/{slug}/stores/{store_id}/threads")
async def start_comms(
    slug: str,
    store_id: UUID,
    body: TellusCommsStart,
    account: TellusAccount = Depends(require_verified_consumer),
): ...
```

`TellusCommsStart.store_id` is removed. Validate the store against the public
brand slug, check `tellus_stores.messaging_enabled`, and notify only members
with access to that store and the needed Comms capability.

Replace the special-case owner/moderator functions in
`server/app/tellus/services/comms_service.py` with context-aware access.

### Promo implementation

Update `server/app/tellus/models/promo.py` and
`server/app/tellus/services/promo_service.py`:

```python
async def create_campaign(
    conn,
    brand_id: UUID,
    store_id: UUID,
    data: CampaignCreate,
) -> dict: ...

async def list_campaigns(
    conn,
    brand_id: UUID,
    store_id: UUID | None,
) -> list[dict]: ...

async def redeem_card(conn, scanner: dict, raw_card_token: str) -> dict: ...
```

`CampaignOut` and consumer card responses include `store_id` and `store_name`.
The authenticated brand redemption path requires a store. During compatibility,
one-store businesses may infer it; multi-store businesses receive
`422 location_required` until their app is updated.

### Marketplace implementation

Remove client-controlled city/state from listing create/update. Listings copy
city and state from the selected store as a display snapshot. Redemption copies
the listing store ID. Cross-store redemption verification returns 404.

### Store archival

Replace physical deletion with:

```python
@router.post("/brands/{brand_id}/stores/{store_id}/archive")
async def archive_store(...): ...
```

Return 409 with dependency counts when active campaigns, listings, open Comms,
or active scanners must be closed, moved, or revoked first.

## Web implementation

New files:

```text
client/tellus/src/hooks/useBusinessContext.tsx
client/tellus/src/api/business.ts
client/tellus/src/components/BusinessSwitcher.tsx
client/tellus/src/components/StoreSwitcher.tsx
client/tellus/src/pages/brand/Team.tsx
client/tellus/src/pages/brand/BusinessChooser.tsx
client/tellus/src/pages/InviteAccept.tsx
```

Context contract:

```ts
interface BusinessContextValue {
  businesses: BusinessMembership[]
  activeBusiness: BusinessMembership | null
  activeStoreId: string | null
  loading: boolean

  selectBusiness(brandId: string | null): void
  selectStore(storeId: string | null): void
  hasCapability(capability: BrandCapability): boolean
  canAccessStore(storeId: string): boolean
  refreshBusinesses(): Promise<void>
}
```

Persist selection only as IDs:

```text
tellus_active_brand_id
tellus_active_store_id
tellus_active_mode = consumer | business
```

Validate saved IDs against `/me/businesses` after every login or refresh.

Update:

```text
client/tellus/src/api/types.ts
client/tellus/src/api/promo.ts
client/tellus/src/hooks/useAccount.tsx
client/tellus/src/App.tsx
client/tellus/src/components/Layout.tsx
client/tellus/src/pages/brand/Feedback.tsx
client/tellus/src/pages/brand/Stores.tsx
client/tellus/src/pages/brand/Listings.tsx
client/tellus/src/pages/brand/Campaigns.tsx
client/tellus/src/pages/brand/Board.tsx
client/tellus/src/pages/Messages.tsx
client/tellus/src/pages/PublicBrand.tsx
client/tellus/src/components/BusinessMessageComposer.tsx
```

The Team UI moves out of Board management. Board stays brand-wide. Business and
store switching replaces the existing consumer-moderator and inbox-brand
exceptions.

## iOS implementation

New files:

```text
platforms/ios/TellUs/Models/BusinessAccessModels.swift
platforms/ios/TellUs/Views/Shared/BusinessSwitcher.swift
platforms/ios/TellUs/Views/Shared/StoreSwitcher.swift
platforms/ios/TellUs/Views/Brand/Team/TeamAccessView.swift
platforms/ios/TellUs/Views/Brand/Team/InviteMemberSheet.swift
platforms/ios/TellUs/Views/Auth/InviteAcceptView.swift
```

Update `platforms/ios/TellUs/App/AppState.swift`:

```swift
enum AppMode: Equatable {
    case consumer
    case business(brandID: String)
}

enum Phase: Equatable {
    case restoring
    case loggedOut
    case verifyPending(email: String)
    case ready
}

var businesses: [BusinessMembership] = []
var mode: AppMode = .consumer
var selectedStoreID: String?

func refreshBusinesses() async
func selectBusiness(_ brandID: String)
func selectConsumerMode()
func selectStore(_ storeID: String?)
func hasCapability(_ capability: BrandCapability) -> Bool
```

Update `RootView.swift` to derive consumer/brand UI from `mode`, not
`account_type`.

Update service signatures:

```swift
func stores(brandID: String) async throws -> [Store]
func archiveStore(brandID: String, storeID: String) async throws -> Store
func list(brandID: String, storeID: String?, ...) async throws -> [Report]
func threads(brandID: String, storeID: String?, ...) async throws -> [DmThread]
func campaigns(brandID: String, storeID: String?) async throws -> [PromoCampaign]
func redeem(brandID: String, storeID: String, cardToken: String) async throws -> PromoRedeemResult
```

`BrandScanViewModel` receives immutable `brandID` and `storeID`, and its scan
view cannot open without a store selection.

## Tests

New backend tests:

```text
server/tests/tellus/test_brand_access.py
server/tests/tellus/test_brand_team.py
server/tests/tellus/test_location_scope.py
server/tests/tellus/test_marketplace_location.py
```

Required cases:

- Role defaults, grants, and denies.
- Suspended/revoked membership is denied immediately.
- Cross-brand and cross-store access fails closed.
- Restricted users only see assigned stores.
- Invite token hashing, expiry, revoke, email matching, and idempotent accept.
- Last-owner and ownership-transfer transaction safety.
- Store archival dependency checks.
- Single-store and multi-store location backfill outcomes.
- Store-matched promo redemption and `wrong_store` failure.
- Listing/redemption location propagation.

Extend:

```text
server/tests/tellus/test_comms_logic.py
server/tests/tellus/test_promo_cards.py
server/tests/tellus/test_board_logic.py
```

The web app has no test runner today. Add Vitest, jsdom, and Testing Library,
then add:

```text
client/tellus/src/hooks/useBusinessContext.test.tsx
client/tellus/src/components/BusinessSwitcher.test.tsx
client/tellus/src/components/StoreSwitcher.test.tsx
client/tellus/src/api/business.test.ts
client/tellus/src/pages/brand/Team.test.tsx
```

iOS tests:

```text
platforms/ios/TellUs/Tests/BusinessAccessModelDecodeTests.swift
platforms/ios/TellUs/Tests/WorkspaceSelectionTests.swift
platforms/ios/TellUs/Tests/BusinessPathTests.swift
platforms/ios/TellUs/Tests/LocationScopedPromoTests.swift
```

## Delivery sequence

1. Access schema, backfill, capability resolver, and backend tests.
2. Invitations/team API, audit events, and web/iOS business switching.
3. Canonical brand-scoped routes for brand profile, billing, stores, prompts,
   and Board; preserve old owner adapters.
4. Location schema, store lifecycle, audit script, public location selection,
   and remediation UI.
5. Feedback and Comms store scope, including assignment and notifications.
6. Promo, scanner, listing, and redemption store scope.
7. Run the location audit, apply final constraints manually, remove adapters,
   remove `can_manage_inbox`, and stop using `account_type` for authorization.

## Completion criteria

- No new business route authorizes through `account_type` or `account.brand_id`.
- Every new operational resource has one store.
- A user can switch between consumer mode and multiple businesses.
- Location-limited members cannot access aggregate or foreign-store data.
- Promo redemption only succeeds at the campaign's location.
- Stores archive rather than deleting historical records.
- Existing moderators retain precisely their prior access with no privilege escalation.
- Backend, web, and iOS test suites pass.
- The location audit reports no unresolved active records before final constraints.
