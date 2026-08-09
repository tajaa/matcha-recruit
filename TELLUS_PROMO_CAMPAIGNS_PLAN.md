# Tellus Promo Campaigns — designer + QR reward cards (mechanical plan)

## Context

Brand designs promo flyer in-app (templates/fonts/stickers/logo) with campaign QR. Consumer scans → login/signup → unique single-use reward card with own QR. Staff scan card via per-store device-token scanner page → atomic redeem. Global claim cap; cancel → outstanding cards invalidate. Approved scope: full designer v1, scan-device tokens, consumer account required, single-use cards. Surfaces: web (`client/tellus/`) + iOS (`platforms/ios/TellUs/`).

Reused machinery: `tellus_links` atomic reserve-a-use (cap primitive), `public_intake.py` (rate-limit layers, token-route semantics), `qrcode.react`, `TicketPanel` paper ticket, `require_paid_brand` (billing gate — no new billing).

URLs: claim QR `{origin}/tellus/p/{claim_token}`; card QR `{origin}/tellus/card/{card_token}`; scanner `{origin}/tellus/scan/{device_token}`.

---

## 1. Migration — `server/alembic/versions/tellus_app_16_promo_campaigns.py`

`revision="tellus_app_16"`, `down_revision="oceanlab_app_01"` (branch head — NOT tellus_app_15). Raw `op.execute`, style of `tellus_app_15_likes.py`. Order: campaigns → scanner_devices → cards (FK dep). Real `downgrade()` drops reverse order. **Never run alembic anywhere without explicit user go** (migrate-dev.sh, later migrate-prod.sh).

```sql
CREATE TABLE IF NOT EXISTS tellus_promo_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    reward_text TEXT NOT NULL,
    claim_token TEXT NOT NULL UNIQUE,              -- secrets.token_urlsafe(12)
    max_claims INT NOT NULL CHECK (max_claims BETWEEN 1 AND 10000),
    claim_count INT NOT NULL DEFAULT 0,            -- monotone; never decremented
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','cancelled')),
    card_expiry_days INT NOT NULL DEFAULT 30 CHECK (card_expiry_days BETWEEN 1 AND 365),
    starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ,
    design_json JSONB,
    flyer_image_url TEXT,
    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tellus_promo_campaigns_brand ON tellus_promo_campaigns (brand_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tellus_scanner_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES tellus_stores(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,                    -- secrets.token_urlsafe(16)
    label TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tellus_scanner_devices_brand ON tellus_scanner_devices (brand_id);

CREATE TABLE IF NOT EXISTS tellus_promo_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES tellus_promo_campaigns(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
    card_token TEXT NOT NULL UNIQUE,               -- secrets.token_urlsafe(16); bearer credential
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','redeemed','cancelled')),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,               -- 'expired' derived at read, never stored
    redeemed_at TIMESTAMPTZ,
    redeemed_store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
    redeemed_scanner_id UUID REFERENCES tellus_scanner_devices(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_tellus_promo_cards_one_per_account UNIQUE (campaign_id, account_id)
);
CREATE INDEX IF NOT EXISTS ix_tellus_promo_cards_account ON tellus_promo_cards (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_tellus_promo_cards_campaign_status ON tellus_promo_cards (campaign_id, status);
```

---

## 2. `server/app/tellus/models/promo.py` (new)

```python
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field

CampaignStatus = Literal["active", "paused", "cancelled"]
EffectiveCardStatus = Literal["issued", "redeemed", "cancelled", "expired"]
ClaimUnavailableReason = Literal["ok", "cap_reached", "cancelled", "paused", "not_started", "ended"]

class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    reward_text: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    max_claims: int = Field(ge=1, le=10000)
    card_expiry_days: int = Field(default=30, ge=1, le=365)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

class CampaignPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    reward_text: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    ends_at: datetime | None = None
    status: Literal["active", "paused"] | None = None   # cancel only via /cancel

class CampaignStats(BaseModel):
    claimed: int
    redeemed: int
    outstanding: int      # issued & unexpired
    expired: int          # issued & past expires_at (derived)
    cancelled: int

class CampaignOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    reward_text: str
    claim_token: str
    claim_url: str        # f"/tellus/p/{claim_token}" (path only; client prefixes origin)
    max_claims: int
    claim_count: int
    status: CampaignStatus
    card_expiry_days: int
    starts_at: datetime | None
    ends_at: datetime | None
    flyer_image_url: str | None
    has_design: bool      # design_json IS NOT NULL (list view omits the blob)
    cancelled_at: datetime | None
    created_at: datetime
    stats: CampaignStats | None = None   # populated on GET /{id} and list

class DesignPut(BaseModel):
    design_json: dict[str, Any]          # route enforces 256KB serialized cap → 413

class CancelOut(BaseModel):
    invalidated_count: int

class ScannerCreate(BaseModel):
    store_id: UUID
    label: str | None = Field(default=None, max_length=80)

class ScannerOut(BaseModel):
    id: UUID
    store_id: UUID
    store_name: str
    label: str | None
    token: str
    scanner_url: str      # f"/tellus/scan/{token}"
    is_active: bool
    created_at: datetime

class ClaimPreviewOut(BaseModel):
    brand_name: str
    brand_logo_url: str | None
    title: str
    reward_text: str
    description: str | None
    flyer_image_url: str | None
    available: bool
    reason: ClaimUnavailableReason
    already_claimed: bool
    card_token: str | None    # set iff already_claimed (viewer identified)

class CardOut(BaseModel):
    id: UUID
    card_token: str
    card_url: str             # f"/tellus/card/{card_token}"
    status: EffectiveCardStatus
    campaign_title: str
    reward_text: str
    brand_name: str
    brand_logo_url: str | None
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None
    redeemed_store_name: str | None

class ClaimOut(CardOut):
    created: bool             # 201 vs idempotent 200 mirror

class RedeemIn(BaseModel):
    card_token: str = Field(min_length=1, max_length=512)   # bare token OR full URL

class RedeemOut(BaseModel):
    campaign_title: str
    reward_text: str
    redeemed_at: datetime
    store_name: str

class ScanBootstrapOut(BaseModel):
    store_name: str
    brand_name: str
    brand_logo_url: str | None
```

---

## 3. `server/app/tellus/services/promo_service.py` (new)

```python
import re, secrets
from datetime import datetime, timezone
from uuid import UUID

CARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,64}$")

class PromoError(Exception):
    """Route maps .http_status/.detail; extra merged into response body."""
    def __init__(self, http_status: int, code: str, message: str, extra: dict | None = None): ...

# ---------- pure (unit-testable, no DB) ----------
def extract_card_token(raw: str) -> str:
    # bare token passes CARD_TOKEN_RE → return; URL → last non-empty path segment,
    # re-validate against CARD_TOKEN_RE; else PromoError(422, "bad_token", ...)

def effective_card_status(status: str, expires_at: datetime, now: datetime | None = None) -> str:
    # 'issued' + expires_at <= now → 'expired'; 'redeemed'/'cancelled' terminal (never flip)

def can_campaign_transition(current: str, new: str) -> bool:
    # active↔paused True; anything involving 'cancelled' False (cancel has own path)

def claim_reason(campaign: dict, now: datetime) -> str:
    # 'cancelled' → 'cancelled'; 'paused' → 'paused'; starts_at>now → 'not_started';
    # ends_at<=now → 'ended'; claim_count>=max_claims → 'cap_reached'; else 'ok'

def map_redeem_failure(card: dict | None, campaign_status: str | None, now: datetime) -> PromoError:
    # None/cross-brand → 404 not_found (no existence leak)
    # status=='redeemed' → 409 already_redeemed, extra={redeemed_at, redeemed_store_name}
    # status=='cancelled' or campaign cancelled → 410 cancelled
    # expires_at<=now → 410 expired

# ---------- brand CRUD ----------
async def create_campaign(conn, brand_id: UUID, data: "CampaignCreate") -> dict:
    # claim_token=secrets.token_urlsafe(12); INSERT ... RETURNING *

async def list_campaigns(conn, brand_id: UUID) -> list[dict]:
    # LEFT JOIN cards, one query:
    # COUNT(*) FILTER (WHERE pc.status='redeemed')                              AS redeemed,
    # COUNT(*) FILTER (WHERE pc.status='issued' AND pc.expires_at >  NOW())    AS outstanding,
    # COUNT(*) FILTER (WHERE pc.status='issued' AND pc.expires_at <= NOW())    AS expired,
    # COUNT(*) FILTER (WHERE pc.status='cancelled')                            AS cancelled
    # GROUP BY c.id ORDER BY c.created_at DESC; design_json excluded from SELECT

async def get_campaign_owned(conn, brand_id: UUID, campaign_id: UUID, *, with_design: bool = False) -> dict:
    # WHERE id=$1 AND brand_id=$2; None → PromoError(404)

async def update_campaign(conn, brand_id: UUID, campaign_id: UUID, patch: "CampaignPatch") -> dict:
    # fetch owned → status change validated via can_campaign_transition (else 409)
    # dynamic SET from exclude_unset fields + updated_at=NOW()

async def cancel_campaign(conn, brand_id: UUID, campaign_id: UUID) -> int:
    # one conn.transaction():
    # UPDATE tellus_promo_campaigns SET status='cancelled', cancelled_at=NOW(), updated_at=NOW()
    #   WHERE id=$1 AND brand_id=$2 AND status <> 'cancelled' RETURNING id
    #   -- NULL → owned-check: 404 if not owned, 409 if already cancelled
    # UPDATE tellus_promo_cards SET status='cancelled' WHERE campaign_id=$1 AND status='issued'
    #   -- invalidated_count from status tag "UPDATE n"

async def save_design(conn, brand_id: UUID, campaign_id: UUID, design_json: dict) -> None
async def set_flyer_url(conn, brand_id: UUID, campaign_id: UUID, url: str) -> str | None  # returns old for delete

# ---------- claim ----------
async def resolve_claim_preview(conn, claim_token: str, viewer_account_id: UUID | None) -> dict:
    # campaign JOIN brands (name, logo_url); None → 404
    # reason=claim_reason(...); available = reason=='ok'
    # viewer → SELECT card by (campaign_id, account_id) → already_claimed/card_token

async def claim_card(conn, claim_token: str, account_id: UUID) -> tuple[dict, bool]:
    # ONE conn.transaction() (savepoint-safe):
    # 1. resolve campaign by token → 404; reason not in ('ok',) AND no existing card → 410 w/ reason
    # 2. pre-check SELECT (campaign_id, account_id) → return (existing, False)
    #    [pre-check NOT except-UniqueViolation — savepoint-abort rule, points_service.py:435]
    # 3. INSERT INTO tellus_promo_cards (campaign_id, account_id, card_token, expires_at)
    #    VALUES ($1,$2,$3, NOW() + make_interval(days => $4))
    #    ON CONFLICT (campaign_id, account_id) DO NOTHING RETURNING *
    #    -- card_token=secrets.token_urlsafe(16); NULL → raced: re-SELECT, return (row, False)
    # 4. iff inserted:
    #    UPDATE tellus_promo_campaigns
    #    SET claim_count = claim_count + 1, updated_at = NOW()
    #    WHERE id=$1 AND status='active'
    #      AND (starts_at IS NULL OR starts_at <= NOW())
    #      AND (ends_at   IS NULL OR ends_at   >  NOW())
    #      AND claim_count < max_claims
    #    RETURNING id
    #    -- NULL → PromoError(410) → txn rollback undoes card INSERT. No cap overshoot:
    #    -- campaign row-lock serializes claimers, predicate re-evaluates post-lock.
    # 5. notify_account(conn, account_id, ...) reuse from points_service

# ---------- scanner ----------
async def resolve_scanner(conn, device_token: str) -> dict:
    # JOIN stores + brands; token unknown OR is_active=FALSE → 404
    # brand.plan_status != 'active' → 410 (lapsed brand goes dark)

async def redeem_card(conn, scanner: dict, raw_card_token: str) -> dict:
    # token = extract_card_token(raw_card_token)
    # UPDATE tellus_promo_cards pc
    # SET status='redeemed', redeemed_at=NOW(), redeemed_store_id=$2, redeemed_scanner_id=$3
    # FROM tellus_promo_campaigns c
    # WHERE pc.card_token=$1 AND pc.status='issued' AND pc.expires_at > NOW()
    #   AND c.id=pc.campaign_id AND c.brand_id=$4 AND c.status <> 'cancelled'
    # RETURNING pc.redeemed_at, c.title, c.reward_text
    # -- single UPDATE = no double-redeem (2nd scanner blocks on row lock, predicate fails)
    # NULL → diagnostic SELECT (card JOIN campaign, brand-scoped) → raise map_redeem_failure(...)

async def create_scanner(conn, brand_id: UUID, store_id: UUID, label: str | None) -> dict
    # store ownership via routes' get_owned_store BEFORE calling; token_urlsafe(16)
async def list_scanners(conn, brand_id: UUID) -> list[dict]      # JOIN store_name
async def revoke_scanner(conn, brand_id: UUID, scanner_id: UUID) -> None
    # UPDATE ... SET is_active=FALSE, revoked_at=NOW() WHERE id AND brand_id; 0 rows → 404

# ---------- consumer ----------
async def list_my_cards(conn, account_id: UUID) -> list[dict]
    # cards JOIN campaigns JOIN brands JOIN stores(redeemed) ORDER BY issued_at DESC
async def get_my_card(conn, account_id: UUID, card_token: str) -> dict   # owner-scoped; None → 404
```

Guard: file never touches `tellus_points_ledger` / `tellus_points_balances`.

---

## 4. Routes

### `server/app/tellus/routes/promo.py` (new) — `router = APIRouter()`

Brand routes ALL `Depends(require_paid_brand)`; consumer routes `Depends(require_consumer)`:

```python
@router.post("/promo/campaigns", status_code=201, response_model=CampaignOut)
async def create_campaign(body: CampaignCreate, account: TellusAccount = Depends(require_paid_brand))

@router.get("/promo/campaigns", response_model=list[CampaignOut])
@router.get("/promo/campaigns/{campaign_id}", response_model=CampaignOut)       # includes design_json? NO — separate:
@router.get("/promo/campaigns/{campaign_id}/design")                            # → {"design_json": dict|None}
@router.patch("/promo/campaigns/{campaign_id}", response_model=CampaignOut)     # 409 bad transition
@router.post("/promo/campaigns/{campaign_id}/cancel", response_model=CancelOut) # 409 already cancelled
@router.put("/promo/campaigns/{campaign_id}/design", status_code=204)
    # len(json.dumps(body.design_json)) > 262_144 → HTTPException(413)
@router.post("/promo/campaigns/{campaign_id}/flyer")                            # → {"flyer_image_url": str}
    # UploadFile; content_type in {image/png,image/jpeg,image/webp} else 415; >5MB → 413
    # storage.upload_file(data, f"flyer.{ext}", prefix=f"tellus/promo/{account.brand_id}/{campaign_id}")
    # PUBLIC bucket (unauth claim page renders it); delete old if "/tellus/promo/" in old (links.py:65 pattern)
@router.post("/promo/scanners", status_code=201, response_model=ScannerOut)
    # get_owned_store(conn, account.brand_id, body.store_id) first (routes/_shared.py:47)
@router.get("/promo/scanners", response_model=list[ScannerOut])
@router.post("/promo/scanners/{scanner_id}/revoke", status_code=204)

@router.post("/promo/redeem", response_model=RedeemOut)                         # require_paid_brand
    # iOS brand-app path: brand owner's phone is the scanner, no device token.
    # body: RedeemIn + optional store_id (validated via get_owned_store when given).
    # calls redeem_card(conn, {"brand_id": account.brand_id, "store_id": body.store_id, "id": None}, ...)
    # → redeem SQL sets redeemed_store_id/redeemed_scanner_id to NULL when absent.

@router.get("/me/promo-cards", response_model=list[CardOut])                    # require_consumer
@router.get("/me/promo-cards/{card_token}", response_model=CardOut)             # require_consumer
```

Handler body pattern: `async with get_pool().acquire() as conn:` then service call; `except PromoError as e: raise HTTPException(e.http_status, {"code": e.code, "message": e.message, **e.extra})` — one shared `_raise(e)` helper.

### `server/app/tellus/routes/promo_public.py` (new) — no auth deps except claim POST

```python
@router.get("/p/{claim_token}", response_model=ClaimPreviewOut)
async def claim_preview(claim_token: str, request: Request, authorization: str | None = Header(None)):
    # await check_rate_limit(client_ip(request), "tellus_promo_preview", 60, 3600)
    # viewer = await optional_consumer_account_id(authorization)   (dependencies.py:24)

@router.post("/p/{claim_token}/claim", response_model=ClaimOut)
async def claim(claim_token: str, request: Request, response: Response,
                account: TellusAccount = Depends(require_consumer)):
    # 401 from missing JWT (drives FE login redirect); brand account → require_consumer 403
    # rate limits: (ip,"tellus_promo_claim_burst",5,60), (ip,"tellus_promo_claim",20,3600),
    #              (claim_token,"tellus_promo_claim_token",120,3600)
    # card, created = claim_card(...); response.status_code = 201 if created else 200

@router.get("/scan/{device_token}", response_model=ScanBootstrapOut)
    # check_rate_limit(ip, "tellus_scan_boot", 120, 3600); resolve_scanner → 404/410

@router.post("/scan/{device_token}/redeem", response_model=RedeemOut)
async def scan_redeem(device_token: str, body: RedeemIn, request: Request):
    # limits: (ip,"tellus_scan_redeem_burst",30,60), (device_token,"tellus_scan_redeem",600,3600)
    # scanner = resolve_scanner(conn, device_token); redeem_card(conn, scanner, body.card_token)
    # 200 / 404 / 409(extra: already_redeemed=True, redeemed_at, redeemed_store_name) / 410 / 422
```

### `server/app/tellus/routes/__init__.py` (modify)

Import `promo_router`, `promo_public_router`; `include_router(promo_router)` in authed block, `include_router(promo_public_router)` beside `public_intake_router`.

---

## 5. Backend tests — `server/tests/tellus/test_promo_cards.py` (new)

Pure + source-guard style (`test_points_math.py` model; zero live DB):

```python
class TestEffectiveCardStatus:
    def test_issued_future_stays_issued(self)
    def test_issued_past_derives_expired(self)
    def test_redeemed_past_expiry_stays_redeemed(self)     # terminal never flips
    def test_cancelled_terminal(self)

class TestCampaignTransitions:
    def test_active_to_paused_ok(self); def test_paused_to_active_ok(self)
    def test_any_to_cancelled_forbidden(self)              # only /cancel path
    def test_cancelled_to_anything_forbidden(self)

class TestClaimReason:
    def test_ok(self); def test_cap_reached(self); def test_cancelled(self)
    def test_paused(self); def test_not_started(self); def test_ended(self)
    def test_cap_checked_last_after_window(self)           # precedence pinned

class TestExtractCardToken:
    def test_bare_token(self)
    def test_full_url(self)                                # https://host/tellus/card/<tok>
    def test_url_trailing_slash(self)
    def test_garbage_raises_422(self); def test_too_short_raises_422(self)

class TestMapRedeemFailure:
    def test_none_card_404(self)                           # incl. cross-brand: same 404
    def test_redeemed_409_with_context(self)               # extra has redeemed_at + store
    def test_cancelled_card_410(self); def test_campaign_cancelled_410(self)
    def test_expired_410(self)

class TestAtomicSourceGuards:                              # inspect.getsource(promo_service)
    def test_claim_uses_on_conflict_do_nothing(self)       # "ON CONFLICT (campaign_id, account_id) DO NOTHING"
    def test_claim_never_catches_unique_violation(self)    # "UniqueViolationError" absent
    def test_cap_update_single_statement(self)             # "claim_count < max_claims" AND
                                                           # "claim_count = claim_count + 1" in same SQL literal
    def test_redeem_single_update_predicates(self)         # status='issued', expires_at > NOW(),
                                                           # c.brand_id =, c.status <> 'cancelled'
    def test_no_points_economy_writes(self)                # "tellus_points_ledger"/"_balances" absent
    def test_cancel_never_decrements_claim_count(self)     # "claim_count - " absent

class TestBrandGateSweep:                                  # clone TestAdminGateSweep
    def test_every_brand_route_requires_paid_brand(self)   # walk promo.router.routes, skip /me/*
    def test_me_routes_require_consumer(self)

class TestPublicRouterShape:
    def test_public_routes_have_no_auth_dependency(self)   # GET /p, GET/POST /scan
    def test_claim_post_requires_consumer(self)
```

Run: `cd server && python3 -m pytest tests/tellus/test_promo_cards.py -v`.

---

## 6. Web client (`client/tellus/`)

### Setup

```bash
cd client/tellus && npm i konva@^9 react-konva@^19 jsqr@^1
mkdir -p public/designer/{fonts,stickers,templates/thumbs}
```
react-konva MUST be 19.x (React 19 reconciler). `public/` doesn't exist yet — Vite serves verbatim, same-origin ⇒ no canvas taint for repo assets.

### `src/api/types.ts` (append)

```ts
export type FlyerDesign = {
  version: 1
  artboard: { preset: 'flyer_letter' | 'reward_card' | 'social_square' | 'story'; w: number; h: number }
  background: { kind: 'color'; color: string } | { kind: 'image'; src: string; fit: 'cover' }
  layers: DesignLayer[]                       // z-order = array order
}
type LayerBase = { id: string; x: number; y: number; rotation: number; opacity: number; locked?: boolean }
export type DesignLayer =
  | (LayerBase & { type: 'text'; text: string; fontFamily: string; fontSize: number
      fontStyle: 'normal' | 'bold' | 'italic'; fill: string; align: 'left' | 'center' | 'right'
      width: number; lineHeight: number; letterSpacing: number })
  | (LayerBase & { type: 'image'; src: string; width: number; height: number; slot?: 'logo' })
  | (LayerBase & { type: 'sticker'; assetId: string; width: number; height: number })
  | (LayerBase & { type: 'shape'; shape: 'rect' | 'circle' | 'line'; width: number; height: number
      fill: string; stroke?: string; strokeWidth?: number; cornerRadius?: number })
  | (LayerBase & { type: 'qr'; size: number; fg: string; bg: string })   // NO url — resolved at render

export type PromoCampaign = {
  id: string; title: string; description: string | null; reward_text: string
  claim_token: string; claim_url: string
  max_claims: number; claim_count: number
  status: 'active' | 'paused' | 'cancelled'
  card_expiry_days: number
  starts_at: string | null; ends_at: string | null
  flyer_image_url: string | null; has_design: boolean
  cancelled_at: string | null; created_at: string
  stats: { claimed: number; redeemed: number; outstanding: number; expired: number; cancelled: number } | null
}
export type PromoCard = {
  id: string; card_token: string; card_url: string
  status: 'issued' | 'redeemed' | 'cancelled' | 'expired'
  campaign_title: string; reward_text: string
  brand_name: string; brand_logo_url: string | null
  issued_at: string; expires_at: string
  redeemed_at: string | null; redeemed_store_name: string | null
}
export type ClaimPreview = {
  brand_name: string; brand_logo_url: string | null
  title: string; reward_text: string; description: string | null
  flyer_image_url: string | null
  available: boolean
  reason: 'ok' | 'cap_reached' | 'cancelled' | 'paused' | 'not_started' | 'ended'
  already_claimed: boolean; card_token: string | null
}
export type ScannerDevice = {
  id: string; store_id: string; store_name: string; label: string | null
  token: string; scanner_url: string; is_active: boolean; created_at: string
}
export type RedeemResult = { campaign_title: string; reward_text: string; redeemed_at: string; store_name: string }
export type FontManifestEntry = { family: string; file: string; weight: number; preview: string }
export type StickerManifestEntry = { id: string; file: string; thumb: string; w: number; h: number }
export type TemplateManifestEntry = { id: string; name: string; preset: FlyerDesign['artboard']['preset']; file: string; thumb: string }
```

### `src/api/promo.ts` (new, ~50 lines)

```ts
export const promoApi = {
  listCampaigns: () => tellusApi.get<PromoCampaign[]>('/promo/campaigns'),
  createCampaign: (b: {title: string; reward_text: string; description?: string; max_claims: number;
                       card_expiry_days?: number; starts_at?: string; ends_at?: string}) =>
    tellusApi.post<PromoCampaign>('/promo/campaigns', b),
  getCampaign: (id: string) => tellusApi.get<PromoCampaign>(`/promo/campaigns/${id}`),
  getDesign: (id: string) => tellusApi.get<{design_json: FlyerDesign | null}>(`/promo/campaigns/${id}/design`),
  patchCampaign: (id: string, b: Partial<Pick<PromoCampaign,'title'|'reward_text'|'description'|'ends_at'|'status'>>) =>
    tellusApi.patch<PromoCampaign>(`/promo/campaigns/${id}`, b),
  cancelCampaign: (id: string) => tellusApi.post<{invalidated_count: number}>(`/promo/campaigns/${id}/cancel`, {}),
  saveDesign: (id: string, design_json: FlyerDesign) => tellusApi.put(`/promo/campaigns/${id}/design`, {design_json}),
  uploadFlyer: (id: string, fd: FormData) => tellusApi.upload<{flyer_image_url: string}>(`/promo/campaigns/${id}/flyer`, fd),
  listScanners: () => tellusApi.get<ScannerDevice[]>('/promo/scanners'),
  createScanner: (b: {store_id: string; label?: string}) => tellusApi.post<ScannerDevice>('/promo/scanners', b),
  revokeScanner: (id: string) => tellusApi.post(`/promo/scanners/${id}/revoke`, {}),
  myCards: () => tellusApi.get<PromoCard[]>('/me/promo-cards'),
  myCard: (cardToken: string) => tellusApi.get<PromoCard>(`/me/promo-cards/${cardToken}`),
  claimPreview: (token: string) => tellusMaybeAuthGet<ClaimPreview>(`/p/${token}`),
  claim: (token: string) => tellusApi.post<PromoCard & {created: boolean}>(`/p/${token}/claim`, {}),
  scanBootstrap: (deviceToken: string) =>
    tellusPublicGet<{store_name: string; brand_name: string; brand_logo_url: string | null}>(`/scan/${deviceToken}`),
  scanRedeem: (deviceToken: string, card_token: string) =>
    tellusPublicPost<RedeemResult>(`/scan/${deviceToken}/redeem`, {card_token}),
}
```

### Hooks

```ts
// src/hooks/useDesignHistory.ts (~120)
export function useDesignHistory(initial: FlyerDesign): {
  design: FlyerDesign
  set: (next: FlyerDesign, opts?: { commit?: boolean }) => void  // commit=true snapshots into past (cap 50)
  undo: () => void; redo: () => void
  canUndo: boolean; canRedo: boolean
  dirty: boolean; markSaved: () => void
}
// commits ONLY on: drag-end, transform-end, text blur, add/delete/reorder, style change. Never per-keystroke.
// keyboard in one useEffect: ⌘Z/⌘⇧Z, Delete, arrows(⇧=×10), ⌘D — suppressed while text overlay open.

// src/hooks/useDesignerFonts.ts (~80)
export function useDesignerFonts(): {
  fonts: FontManifestEntry[]
  ready: boolean                                  // manifest fetched + brand families loaded
  ensureLoaded: (families: string[]) => Promise<void>
}
// FontFace(family, url(...)) → document.fonts.add → await document.fonts.load(`16px "${family}"`)
// GATE: called for every family in doc before first Stage draw AND inside every export path.

// src/hooks/useTextEditOverlay.ts (~100)
export function useTextEditOverlay(stageScale: number): {
  editing: { layerId: string; style: CSSProperties; value: string } | null
  begin: (layer: Extract<DesignLayer,{type:'text'}>, node: Konva.Text) => void
  onChange: (v: string) => void
  commit: () => { layerId: string; text: string } | null   // caller applies via history.set(commit:true)
  cancel: () => void
}
// textarea absolutely positioned at node.getAbsolutePosition() × stageScale; rotation reset during edit (v1).

// src/hooks/useQrScanner.ts (~150)
export function useQrScanner(opts: { onDecode: (text: string) => void; paused: boolean }): {
  videoRef: RefObject<HTMLVideoElement>
  start: () => Promise<void>                       // must be called from user gesture (iOS)
  stop: () => void
  state: 'idle' | 'starting' | 'scanning' | 'denied' | 'unsupported' | 'error'
}
// getUserMedia({video:{facingMode:'environment'}}); <video playsInline>; 150ms loop → offscreen canvas
// → BarcodeDetector({formats:['qr_code']}) if 'BarcodeDetector' in window else (await import('jsqr')).default
// dedupe: skip if decoded === lastDecoded within 3s. stop() releases tracks on unmount.
```

### Designer components (`src/components/designer/`)

```ts
// DesignerCanvas.tsx (~300)
type Props = {
  design: FlyerDesign
  selectedId: string | null
  onSelect: (id: string | null) => void
  onLayerChange: (id: string, patch: Partial<DesignLayer>, commit: boolean) => void  // drag=false, dragend=true
  claimUrl: string                    // absolute; feeds QR layers
  stageRef: RefObject<Konva.Stage>
  editingLayerId: string | null       // hide node while textarea overlay open
}
// Stage scaled to fit container (scale = min(cw/w, ch/h)); Layer[content] + Layer[overlay: Transformer,
// snap guides (center/edges, 8px threshold)]. Click empty → onSelect(null). dblclick text → begin edit.

// LayerRenderer.tsx (~150)
type Props = { layer: DesignLayer; claimUrl: string; assetBase: string; draggable: boolean; ... }
// text→Konva.Text; image/sticker→Konva.Image (use-image pattern via own tiny hook, crossOrigin='anonymous');
// shape→Rect/Circle/Line; qr→Konva.Image from qrToCanvas(claimUrl, size × MAX_EXPORT_RATIO)

// qrToCanvas.tsx (~60)
export function qrToCanvas(value: string, pixelSize: number, fg: string, bg: string): Promise<HTMLCanvasElement>
// hidden mounted QRCodeCanvas (qrcode.react) at pixelSize → copy canvas → resolve. Cached by (value,size,fg,bg).

// Toolbar.tsx (~150): add text/shape/sticker/qr/image(logo), undo/redo (canUndo/canRedo), zoom, Save, Export
// AssetPanel.tsx (~200): tabs templates|stickers|logo|fonts; template click → instantiateTemplate()
// InspectorPanel.tsx (~250): props editor for selected layer (font Select from manifest, size, fill, align,
//   opacity slider, z-order up/down, delete, lock)
// ExportMenu.tsx (~120):
//   async function exportPng(stage: Konva.Stage, design: FlyerDesign, dpi: 150|300): Promise<Blob>
//   // await ensureLoaded(all families) → hide overlay layer → stage.toDataURL({pixelRatio: dpi/150})
//   // → restore → dataURL→Blob. Artboard already at print px (1275×1650@150dpi etc) — ratio 1 = 150dpi.
//   "Save flyer to campaign" → exportPng(...,150) → FormData → promoApi.uploadFlyer
// utils/designer.ts: newLayerId() (crypto.randomUUID), instantiateTemplate(t: FlyerDesign, logoUrl: string|null)
//   — deep-copy, regen ids, swap slot:'logo' src; ARTBOARD_PRESETS const:
//   flyer_letter 1275×1650, reward_card 1050×600, social_square 1080×1080, story 1080×1920
```

### Pages + routes (`App.tsx` diff)

```tsx
// public
<Route path="/p/:token" element={<Claim />} />
<Route path="/scan/:deviceToken" element={<Scan />} />
// consumer
<Route path="/card/:cardToken" element={<Protected requireType="consumer"><CardView /></Protected>} />
// brand
<Route path="/brand/campaigns" element={<Protected requireType="brand"><Campaigns /></Protected>} />
<Route path="/brand/campaigns/:id/design" element={<Protected requireType="brand"><CampaignDesigner /></Protected>} />
```
`CampaignDesigner` imported via `React.lazy` (konva chunk); `BRAND_NAV` (Layout.tsx:28-36) += `{ to: '/brand/campaigns', label: 'Campaigns', icon: Megaphone }`.

- `pages/brand/Campaigns.tsx` (~200): list w/ stats chips (claimed x/max, redeemed), flyer thumb, status Chip, pause/resume/cancel actions (cancel → confirm Modal showing invalidated count after), scanners section (per-store mint w/ `QRCodeCanvas` of scanner_url + copy + revoke — Stores.tsx:132 pattern), create Modal (title, reward_text, max_claims, card_expiry_days, window) → POST → `navigate(\`/brand/campaigns/${id}/design\`)`.
- `pages/brand/CampaignDesigner.tsx` (~150): load campaign + design + fonts (block Stage until `ready`), compose canvas/panels/toolbar, autosave: `useEffect` on `dirty` → 2s debounce → `promoApi.saveDesign` → `markSaved()`; `beforeunload` guard when dirty.
- `pages/Claim.tsx` (~250): copy Intake.tsx skeleton. `promoApi.claimPreview(token)`; states: claimable (big reward panel + Claim button) / `already_claimed` (→ `/card/{card_token}`) / cap_reached/ended/cancelled (dim state) / brand-account (preview + "consumers only"). Claim click: no token in localStorage → `navigate('/login?returnTo=' + encodeURIComponent('/p/'+token))`; on mount w/ token + `?claim=1` flag → auto-POST. 401 from POST → same redirect.
- `pages/consumer/CardView.tsx` (~150): `promoApi.myCard(cardToken)`; full-screen `TicketPanel` paper card — colors remapped `tu-ink`/`tu-paper` (HeroTicket.tsx:23-25 gotcha); `QRCodeCanvas value={origin + card_url} size={280}` on white pad; status states: issued (QR) / redeemed (stamp overlay + when/where) / expired / cancelled (dim, no QR); mono token fallback text (Redemptions.tsx:39 style).
- `pages/consumer/Redemptions.tsx` (modify): "Reward cards" section above listings via `promoApi.myCards()` → link rows to `/card/{card_token}`.
- `pages/Scan.tsx` (~250): no Layout chrome. Bootstrap → store/brand header; invalid token state. "Start camera" button → `useQrScanner.start()`; onDecode → `setPaused(true)` → `promoApi.scanRedeem` → full-screen result: success (tu-good bg, reward_text, check icon) / 409 (amber, "Already used {time} at {store}") / 410 expired/cancelled / 404 invalid → "Scan next" resumes. `navigator.wakeLock?.request('screen')` best-effort.
- `components/ui.tsx` (+~50): `Modal({open, onClose, title, children, footer}: ...)` — fixed backdrop, Escape close, stopPropagation panel.

### Assets (`public/designer/`)

- `fonts/index.json`: 8 entries `{family, file, weight, preview}` — Bricolage Grotesque, Inter, Space Mono (brand trio) + Archivo Black, Bebas Neue, Playfair Display, Caveat, Permanent Marker; self-subset woff2 (Google Fonts OFL).
- `stickers/index.json` + webp ≥2× largest placed size; `templates/index.json` + 4–6 hand-authored FlyerDesign JSONs (2 flyer, 2 card, 1–2 social) + thumbs.
- All fetches via `const ASSET_BASE = '/tellus/designer'` — S3 move later = one-line change.

---

## 7. iOS — Beetlejuse (`platforms/ios/TellUs/`)

App facts (verified): XcodeGen — `project.yml` is source of truth, **never hand-edit pbxproj/Info.plist**; new `.swift` files dropped into `App/ Models/ Services/ ViewModels/ Views/` are auto-globbed on `make generate`. iOS 17, bundle `com.beetlejuse.app`, one binary serving consumer + brand (`AppState.Phase` routes on `account_type`, `App/AppState.swift:47-59`). MVVM: one Service singleton per backend router, `@Observable` VM per screen over `ViewModels/Support/LoadableVM.swift`. Dark-only `TU` theme (`Views/Shared/Theme.swift`) — no paper/tear motif on iOS; v1 card uses `.glassCard` + `TU.ember`, torn-ticket `Shape` is polish-later.

**Scope decision: universal links OUT of v1.** Entitlements are empty; no AASA anywhere (repo-wide grep zero). Flyer QR opens the web claim page in Safari — works for everyone. App users additionally get the in-app scan path (Scan tab). v2 note: associated-domains entitlement + AASA at `hey-matcha.com/.well-known/apple-app-site-association` + `onOpenURL` routing + pending-deeplink slot in `AppState` surviving loggedOut→login transition.

### New files (each auto-included by `make generate`)

```swift
// Models/Promo.swift — Codable structs matching §2 JSON; follow existing Models/ CodingKeys convention
struct PromoCard: Codable, Identifiable, Hashable {
    let id: String; let card_token: String; let card_url: String
    let status: String            // "issued"|"redeemed"|"cancelled"|"expired"
    let campaign_title: String; let reward_text: String
    let brand_name: String; let brand_logo_url: String?
    let issued_at: Date; let expires_at: Date
    let redeemed_at: Date?; let redeemed_store_name: String?
}
struct ClaimPreview: Codable { ... }      // mirrors ClaimPreviewOut
struct PromoCampaign: Codable, Identifiable { ... }   // mirrors CampaignOut (stats included)
struct RedeemResult: Codable { let campaign_title: String; let reward_text: String
                               let redeemed_at: Date; let store_name: String? }

// Services/PromoService.swift — singleton over APIClient (pattern: AuthService)
final class PromoService {
    static let shared = PromoService()
    func myCards() async throws -> [PromoCard]                 // GET /me/promo-cards
    func card(token: String) async throws -> PromoCard         // GET /me/promo-cards/{token}
    func claimPreview(token: String) async throws -> ClaimPreview   // GET /p/{token}
    func claim(token: String) async throws -> PromoCard        // POST /p/{token}/claim (retryOnUnauthorized default)
    func campaigns() async throws -> [PromoCampaign]           // GET /promo/campaigns (brand)
    func redeem(cardToken: String, storeId: String?) async throws -> RedeemResult
        // POST /promo/redeem — brand-authed; APIClient.request(method:"POST", path:"/promo/redeem", body:...)
}

// ViewModels/PromoCardsViewModel.swift — LoadableVM; cards: [PromoCard]; load() via withLoad
// ViewModels/PromoClaimViewModel.swift — states .loading/.preview(ClaimPreview)/.claimed(PromoCard)/.unavailable(reason)
// ViewModels/BrandScanViewModel.swift — result enum { success(RedeemResult), alreadyRedeemed(at:store:),
//   expired, cancelled, invalid }; maps 409 extra payload / 410 / 404 from APIClient error

// Views/Consumer/Cards/CardWalletView.swift — list of PromoCards (status chip, brand, expiry) → detail
// Views/Consumer/Cards/CardDetailView.swift — full-screen: QRCodeView(content: APIClient.webOrigin + card.card_url)
//   on white pad (QRCodeView = existing CoreImage renderer, Views/Shared/QRCodeView.swift; usage model:
//   Views/Brand/Stores/LinkQRSheet.swift), reward_text large, status states (redeemed→stamp + when/where,
//   expired/cancelled→dim no QR), brightness bump while visible (UIScreen.main.brightness save/restore)
// Views/Brand/Scan/BrandScanView.swift — reuses Views/Consumer/Scan/QRScannerView.swift (VisionKit
//   DataScannerViewController wrapper, isActive re-arm + didFire single-shot latch) + manual paste fallback
//   (simulator); on decode → vm.redeem → full-screen result card → "Scan next" re-arms
```

### Modified files

- `Views/Consumer/Scan/ScanView.swift:7-17` — generalize `intakeToken(from:)` → `enum ScannedTarget { case intake(String), promoClaim(String) }` + `scannedTarget(from raw: String) -> ScannedTarget?` recognizing `/i/{token}` and `/p/{token}` (full URL / bare path); `.promoClaim` presents `ClaimSheet` (preview → Claim button → success → link to CardDetailView).
- `Tests/IntakeTokenTests.swift` — extend for `scannedTarget`: promo URL, promo bare path, intake regression, garbage nil.
- `Views/Consumer/Market/MarketplaceHomeView.swift` (or More) — "My cards" entry → CardWalletView. Cheapest v1: third segment in existing Market segmented control.
- `Views/Brand/BrandTabView.swift` — add Scan tab (or BrandMoreView row) → BrandScanView.
- `project.yml:48` — reword `NSCameraUsageDescription` to cover reward scanning ("scan feedback and reward QR codes…"); then `make generate` (regenerates Info.plist + pbxproj).

### iOS verification

`make generate && make build` (SIM default iPhone 17 Pro); `make test` (IntakeTokenTests extension); manual: paste-fallback claim in simulator (no camera), real-device scan of web CardView QR via BrandScanView → 200 then 409 on rescan. Version bump NOT manual — `release-appstore.sh` sed-bumps `CURRENT_PROJECT_VERSION` + auto-commits project.yml + pbxproj together. Commits: `feat(tellus-ios): …`.

---

## 8. Implementation order

1. Migration + models/promo.py + promo_service.py + routes + `__init__.py` mount + tests (backend complete, testable).
2. Web types + promoApi + Modal.
3. Campaigns list/create + scanners UI (no konva).
4. Claim page + CardView + Redemptions section (loop shippable end-to-end w/ Canva-made flyer).
5. Scan page + useQrScanner.
6. Designer: DesignerCanvas + LayerRenderer + Toolbar → Inspector/AssetPanel → export → templates/fonts/stickers assets.
7. Undo/autosave polish.
8. iOS surface.

## 9. Risks

1. **Canvas taint**: brand logo from public bucket must load `crossOrigin='anonymous'` AND bucket CORS must allow origin — else `toDataURL` throws, export dead. Verify CORS GET rule early (memory: tellus S3 CORS PUT rule was open question).
2. Font readiness — every export path awaits `document.fonts.load` per family or metrics bake wrong.
3. iOS Safari camera: HTTPS + user gesture + `playsInline` + no BarcodeDetector → jsQR path; test on real iPhone.
4. react-konva pin 19.x.
5. Textarea-overlay editing (rotation/scale math) — time-boxed, rotation-reset during edit acceptable.

## 10. Verification

- Backend: `cd server && python3 -m pytest tests/tellus/test_promo_cards.py -v`; full `tests/tellus/` suite still green; py_compile hook on every edit.
- Web: `cd client/tellus && npx tsc -p tsconfig.json --noEmit && npm run build` (tellus's own tsconfig — root repo no-op gotcha doesn't apply here but never use bare root tsc).
- Migration: author only; user runs `./scripts/migrate-dev.sh`; prod later via `./scripts/migrate-prod.sh`.
- E2E dev loop (`dev-remote.sh` up): create campaign (paid brand) → designer: template → text edit → QR → export 300dpi PNG (open, check QR scans from print preview) → save flyer → open `/tellus/p/{token}` logged out → signup → card issued → `/tellus/card/{token}` on phone → mint scanner → `/tellus/scan/{token}` second device → scan phone → success → rescan → 409 already-used → cancel campaign → second account's card shows cancelled → claim at cap → exhausted state.
