# Cappe Creator Marketplace — Transcription-Level Implementation Spec

Brand ↔ influencer collab marketplace on gummfit.com, inside the Cappe app. Creators build
profiles (media kit: socials, portfolio, rate card), get listed in a public directory after
admin review, and receive offers from brands. Offers carry structured negotiable terms,
deliverables, and a payment schedule paid through the existing Stripe Connect rails.

**Locked decisions:** all on-platform (both sides are `cappe_accounts`) · brands initiate
(no open campaign board) · platform fee admin-editable from matcha `/admin` · reach is
manually audited by us (verified badge) · profiles reviewed before listing · **creator-first:
the platform structurally sides with creators** — hard guardrails on what terms a brand can
even send (Part 9B), a deterministic Deal Check advisor rendered only to the creator, brand
track-record transparency, auto-approve on brand silence, and cancel rules where the brand
owes for approved work.

**Conventions this spec assumes (verified against the codebase):**
- asyncpg via `async with get_connection() as conn:`; parameterized SQL only; explicit
  `updated_at = NOW()` in UPDATEs (no triggers).
- JSONB columns come back as text — read through `_shared.loads`, write `json.dumps(...)`.
- Never hold a pooled connection across a Stripe round-trip (rule stated in
  `routes/payments.py:63`) — release, call, re-acquire.
- Cappe imports only `app/core/*`. The matcha-admin endpoints live in `app/core/routes/admin/`
  and use **raw SQL on `cappe_*` tables** (precedent `admin/research.py:2098`) — no cappe imports.
- Frontend uses the Cappe parallel stack: `cappeApi`/`cappePublicGet` (`client/src/cappe/api.ts`),
  `useCappeMe`, `ui`/`statusBadge` atoms (`components/ui.ts`), lucide icons, zinc-950 dark theme.
- Test data: RFC 2606 domains only.

---

# PART 1 — Migration

## File: `server/alembic/versions/zzzzcappe28_creator_marketplace.py`

`revision = "zzzzcappe28"`. `down_revision`: the alembic head at author time — currently
`"empavail01"` (verify with the newest file in `server/alembic/versions/` before writing;
chain is single-headed). Commit the migration before applying anywhere. Apply via
`./scripts/migrate-dev.sh`; prod only at ship time via `./scripts/migrate-prod.sh`.

All DDL `IF NOT EXISTS` style, matching `zzzzcappe10_reviews.py`. Full `upgrade()`:

```python
def upgrade() -> None:
    # 1. Third account type -------------------------------------------------
    op.execute("ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check")
    op.execute(
        "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
        "CHECK (account_type IN ('business', 'personal', 'creator'))"
    )

    # 2. Creator profile ----------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL UNIQUE REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            handle VARCHAR(30) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            avatar_url TEXT,
            cover_url TEXT,
            bio TEXT,
            location VARCHAR(120),
            niches TEXT[] NOT NULL DEFAULT '{}',
            languages TEXT[] NOT NULL DEFAULT '{}',
            open_to_offers BOOLEAN NOT NULL DEFAULT true,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'pending_review', 'published', 'rejected', 'suspended')),
            review_note TEXT,
            submitted_at TIMESTAMPTZ,
            reviewed_at TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            reach_verified BOOLEAN NOT NULL DEFAULT false,
            reach_audited_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_creator_profiles_handle "
        "ON cappe_creator_profiles (lower(handle))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_profiles_status "
        "ON cappe_creator_profiles (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_profiles_niches "
        "ON cappe_creator_profiles USING GIN (niches)"
    )

    # 3. Socials ------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_socials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            platform VARCHAR(20) NOT NULL CHECK (platform IN
                ('instagram', 'tiktok', 'youtube', 'x', 'twitch', 'facebook', 'linkedin', 'other')),
            handle VARCHAR(120) NOT NULL,
            url TEXT NOT NULL,
            follower_count INTEGER CHECK (follower_count IS NULL OR follower_count >= 0),
            engagement_rate NUMERIC(5,2),
            audit_status VARCHAR(16) NOT NULL DEFAULT 'unverified'
                CHECK (audit_status IN ('unverified', 'verified', 'flagged')),
            verified_follower_count INTEGER,
            audited_at TIMESTAMPTZ,
            audited_by VARCHAR(255),
            audit_note TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (profile_id, url)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_socials_profile "
        "ON cappe_creator_socials (profile_id, sort_order)"
    )

    # 4. Portfolio ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_portfolio_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            media_url TEXT,
            media_type VARCHAR(10) CHECK (media_type IS NULL OR media_type IN ('image', 'video')),
            external_url TEXT,
            brand_name VARCHAR(120),
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_portfolio_profile "
        "ON cappe_creator_portfolio_items (profile_id, sort_order)"
    )

    # 5. Rate cards ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_rate_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            deliverable_type VARCHAR(20) NOT NULL CHECK (deliverable_type IN
                ('post', 'reel', 'story', 'video', 'short', 'stream', 'ugc', 'blog', 'other')),
            platform VARCHAR(20) NOT NULL,
            price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            negotiable BOOLEAN NOT NULL DEFAULT true,
            notes VARCHAR(500),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (profile_id, deliverable_type, platform)
        )
        """
    )

    # 6. Campaigns (optional brand grouping) --------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            budget_min_cents INTEGER,
            budget_max_cents INTEGER,
            deliverable_notes TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_campaigns_brand "
        "ON cappe_collab_campaigns (brand_account_id, created_at DESC)"
    )

    # 7. Offers -------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_offers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID REFERENCES cappe_collab_campaigns(id) ON DELETE SET NULL,
            brand_account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            creator_profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'sent' CHECK (status IN
                ('sent', 'negotiating', 'accepted', 'active', 'completed',
                 'declined', 'withdrawn', 'cancelled')),
            payment_schedule VARCHAR(20) CHECK (payment_schedule IS NULL OR payment_schedule IN
                ('upfront', 'split_50_50', 'per_deliverable')),
            accepted_revision_id UUID,
            total_cents INTEGER,
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            accepted_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            declined_at TIMESTAMPTZ,
            declined_reason TEXT,
            cancelled_at TIMESTAMPTZ,
            cancelled_by VARCHAR(10) CHECK (cancelled_by IS NULL OR cancelled_by IN ('brand', 'creator')),
            cancel_reason TEXT,
            last_action_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_offers_creator "
        "ON cappe_collab_offers (creator_profile_id, status, last_action_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_offers_brand "
        "ON cappe_collab_offers (brand_account_id, status, last_action_at DESC)"
    )

    # 8. Revisions (immutable terms snapshots) ------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_offer_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            revision_no INTEGER NOT NULL,
            proposed_by VARCHAR(10) NOT NULL CHECK (proposed_by IN ('brand', 'creator')),
            terms JSONB NOT NULL,
            message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, revision_no)
        )
        """
    )
    # FK from offers.accepted_revision_id, added after the revisions table exists.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE cappe_collab_offers
                ADD CONSTRAINT fk_cappe_collab_offers_accepted_revision
                FOREIGN KEY (accepted_revision_id)
                REFERENCES cappe_collab_offer_revisions(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )

    # 9. Deliverables (materialized at accept) ------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_deliverables (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            type VARCHAR(20) NOT NULL,
            platform VARCHAR(20) NOT NULL,
            spec TEXT,
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN
                ('pending', 'submitted', 'revision_requested', 'approved')),
            submission_url TEXT,
            submission_note TEXT,
            proof_media_url TEXT,
            submitted_at TIMESTAMPTZ,
            revision_count INTEGER NOT NULL DEFAULT 0,
            review_note TEXT,
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, idx)
        )
        """
    )

    # 10. Payments (installments, materialized at accept) -------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            label VARCHAR(120) NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            trigger VARCHAR(20) NOT NULL CHECK (trigger IN
                ('on_accept', 'on_all_approved', 'on_deliverable')),
            deliverable_id UUID REFERENCES cappe_collab_deliverables(id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'scheduled' CHECK (status IN
                ('scheduled', 'due', 'processing', 'paid', 'failed', 'refunded', 'cancelled')),
            fee_bps_snapshot INTEGER,
            fee_cents INTEGER,
            stripe_checkout_session_id TEXT,
            stripe_payment_intent TEXT,
            due_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, idx)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_payments_offer "
        "ON cappe_collab_payments (offer_id, idx)"
    )

    # 11. Offer chat --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            sender VARCHAR(10) NOT NULL CHECK (sender IN ('brand', 'creator')),
            sender_account_id UUID REFERENCES cappe_accounts(id) ON DELETE SET NULL,
            body TEXT NOT NULL,
            revision_id UUID REFERENCES cappe_collab_offer_revisions(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_messages_offer "
        "ON cappe_collab_messages (offer_id, created_at)"
    )

    # 12. Marketplace settings (admin-editable knobs) -----------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_marketplace_settings (
            key VARCHAR(64) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO cappe_marketplace_settings (key, value) VALUES
            ('collab_fee_bps', '{"bps": 1500}'::jsonb),
            ('min_offer_cents', '{"cents": 5000}'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )
```

`downgrade()` — reverse order:

```python
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_marketplace_settings")
    op.execute("DROP TABLE IF EXISTS cappe_collab_messages")
    op.execute("DROP TABLE IF EXISTS cappe_collab_payments")
    op.execute("DROP TABLE IF EXISTS cappe_collab_deliverables")
    op.execute("ALTER TABLE cappe_collab_offers DROP CONSTRAINT IF EXISTS fk_cappe_collab_offers_accepted_revision")
    op.execute("DROP TABLE IF EXISTS cappe_collab_offer_revisions")
    op.execute("DROP TABLE IF EXISTS cappe_collab_offers")
    op.execute("DROP TABLE IF EXISTS cappe_collab_campaigns")
    op.execute("DROP TABLE IF EXISTS cappe_creator_rate_cards")
    op.execute("DROP TABLE IF EXISTS cappe_creator_portfolio_items")
    op.execute("DROP TABLE IF EXISTS cappe_creator_socials")
    op.execute("DROP TABLE IF EXISTS cappe_creator_profiles")
    op.execute("ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check")
    op.execute(
        "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
        "CHECK (account_type IN ('business', 'personal'))"
    )
```

Note: downgrade of the CHECK fails if creator rows exist — acceptable; docstring says so.
`cappe_admin_audit.actor_account_id` is **already nullable** (`zzzzcappe26_billing.py:215`) —
no change needed for matcha-admin writes.

---

# PART 2 — Backend models

## File: `server/app/cappe/models/creators.py` (new)

```python
"""Pydantic shapes — Cappe creator marketplace (profiles, socials, portfolio, rates)."""
import re
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SocialPlatform = Literal["instagram", "tiktok", "youtube", "x", "twitch", "facebook", "linkedin", "other"]
DeliverableType = Literal["post", "reel", "story", "video", "short", "stream", "ugc", "blog", "other"]

_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,29}$")

# Directory facet vocab — the only niches the UI offers (free-text rejected).
CREATOR_NICHES = [
    "fitness", "beauty", "fashion", "food", "travel", "tech", "gaming",
    "music", "art", "parenting", "finance", "health", "sports", "comedy",
    "education", "lifestyle", "outdoors", "pets", "diy", "other",
]


class CreatorProfileCreate(BaseModel):
    handle: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("handle")
    @classmethod
    def _handle_shape(cls, v: str) -> str:
        v = v.strip().lower().lstrip("@")
        if not _HANDLE_RE.match(v):
            raise ValueError("Handle must be 3-30 chars: a-z, 0-9, - or _, starting with a letter or digit")
        return v


class CreatorProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = Field(default=None, max_length=2000)
    location: Optional[str] = Field(default=None, max_length=120)
    niches: Optional[list[str]] = Field(default=None, max_length=6)
    languages: Optional[list[str]] = Field(default=None, max_length=6)
    open_to_offers: Optional[bool] = None

    @field_validator("niches")
    @classmethod
    def _known_niches(cls, v):
        if v is None:
            return v
        bad = [n for n in v if n not in CREATOR_NICHES]
        if bad:
            raise ValueError(f"Unknown niches: {', '.join(bad)}")
        return v


class CreatorSocialUpsert(BaseModel):
    platform: SocialPlatform
    handle: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=500)   # https://… enforced below
    follower_count: Optional[int] = Field(default=None, ge=0, le=2_000_000_000)
    engagement_rate: Optional[float] = Field(default=None, ge=0, le=100)
    sort_order: int = 0

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Social URL must start with https://")
        return v


class CreatorSocial(BaseModel):
    id: UUID
    platform: str
    handle: str
    url: str
    follower_count: Optional[int] = None
    engagement_rate: Optional[float] = None
    audit_status: str
    verified_follower_count: Optional[int] = None
    audited_at: Optional[datetime] = None
    sort_order: int


class CreatorPortfolioUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    media_url: Optional[str] = None
    media_type: Optional[Literal["image", "video"]] = None
    external_url: Optional[str] = Field(default=None, max_length=500)
    brand_name: Optional[str] = Field(default=None, max_length=120)
    metrics: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class CreatorPortfolioItem(CreatorPortfolioUpsert):
    id: UUID
    created_at: datetime


class CreatorRateUpsert(BaseModel):
    deliverable_type: DeliverableType
    platform: SocialPlatform
    price_cents: int = Field(ge=0, le=100_000_000)
    negotiable: bool = True
    notes: Optional[str] = Field(default=None, max_length=500)
    sort_order: int = 0


class CreatorRate(CreatorRateUpsert):
    id: UUID


class CreatorProfileMe(BaseModel):
    """Own-profile response (any status)."""
    id: UUID
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    languages: list[str]
    open_to_offers: bool
    status: str
    review_note: Optional[str] = None
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    reach_verified: bool
    reach_audited_at: Optional[datetime] = None
    socials: list[CreatorSocial]
    portfolio: list[CreatorPortfolioItem]
    rates: list[CreatorRate]


class PublicCreatorCard(BaseModel):
    """Directory row."""
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    reach_verified: bool
    max_followers: int
    min_rate_cents: Optional[int] = None
    platforms: list[str]


class PublicCreatorProfile(BaseModel):
    """Full public profile page payload."""
    id: UUID                      # needed by the brand offer composer
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    languages: list[str]
    open_to_offers: bool
    reach_verified: bool
    reach_audited_at: Optional[datetime] = None
    socials: list[CreatorSocial]          # flagged socials excluded server-side
    portfolio: list[CreatorPortfolioItem]
    rates: list[CreatorRate]


class PublicCreatorPage(BaseModel):
    creators: list[PublicCreatorCard]
    total: int
```

## File: `server/app/cappe/models/collab.py` (new)

```python
"""Pydantic shapes — Cappe brand↔creator collabs (offers, terms, deliverables, payments)."""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .creators import DeliverableType, SocialPlatform

PaymentSchedule = Literal["upfront", "split_50_50", "per_deliverable"]
OfferStatus = Literal["sent", "negotiating", "accepted", "active", "completed",
                      "declined", "withdrawn", "cancelled"]


class TermsDeliverable(BaseModel):
    type: DeliverableType
    platform: SocialPlatform
    quantity: int = Field(ge=1, le=20)
    spec: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[date] = None


class TermsUsageRights(BaseModel):
    scope: Literal["organic", "paid"] = "organic"
    duration_months: Optional[int] = Field(default=None, ge=1, le=120)
    whitelisting: bool = False


class TermsExclusivity(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    duration_months: int = Field(ge=1, le=60)


class CollabTerms(BaseModel):
    """The negotiable object. One immutable snapshot per revision."""
    compensation_cents: int = Field(ge=0, le=1_000_000_000)
    payment_schedule: PaymentSchedule
    deliverables: list[TermsDeliverable] = Field(min_length=1, max_length=20)
    usage_rights: TermsUsageRights = Field(default_factory=TermsUsageRights)
    exclusivity: Optional[TermsExclusivity] = None
    revision_rounds: int = Field(default=1, ge=0, le=5)
    approval_required: bool = True
    ftc_disclosure: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        return self

    @property
    def deliverable_count(self) -> int:
        return sum(d.quantity for d in self.deliverables)


class CampaignUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    budget_min_cents: Optional[int] = Field(default=None, ge=0)
    budget_max_cents: Optional[int] = Field(default=None, ge=0)
    deliverable_notes: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["active", "archived"]] = None


class Campaign(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    budget_min_cents: Optional[int] = None
    budget_max_cents: Optional[int] = None
    deliverable_notes: Optional[str] = None
    status: str
    offer_count: int = 0
    created_at: datetime


class OfferCreate(BaseModel):
    creator_profile_id: UUID
    campaign_id: Optional[UUID] = None
    title: str = Field(min_length=1, max_length=200)
    terms: CollabTerms
    message: Optional[str] = Field(default=None, max_length=4000)


class OfferCounter(BaseModel):
    terms: CollabTerms
    message: Optional[str] = Field(default=None, max_length=4000)


class OfferDecline(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class OfferCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class OfferMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class DeliverableSubmit(BaseModel):
    submission_url: str = Field(min_length=8, max_length=500)
    submission_note: Optional[str] = Field(default=None, max_length=2000)
    proof_media_url: Optional[str] = None


class DeliverableRevision(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


# ── Response shapes ─────────────────────────────────────────────────────────

class OfferRevisionOut(BaseModel):
    id: UUID
    revision_no: int
    proposed_by: str
    terms: CollabTerms
    message: Optional[str] = None
    created_at: datetime


class OfferMessageOut(BaseModel):
    id: UUID
    sender: str
    body: str
    revision_id: Optional[UUID] = None
    created_at: datetime


class DeliverableOut(BaseModel):
    id: UUID
    idx: int
    type: str
    platform: str
    spec: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    submission_url: Optional[str] = None
    submission_note: Optional[str] = None
    proof_media_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    revision_count: int
    review_note: Optional[str] = None
    approved_at: Optional[datetime] = None


class PaymentOut(BaseModel):
    id: UUID
    idx: int
    label: str
    amount_cents: int
    currency: str
    trigger: str
    deliverable_id: Optional[UUID] = None
    status: str
    fee_cents: Optional[int] = None
    due_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None


class OfferListItem(BaseModel):
    id: UUID
    title: str
    status: str
    payment_schedule: Optional[str] = None
    total_cents: Optional[int] = None
    currency: str
    campaign_id: Optional[UUID] = None
    # counterpart display
    brand_name: Optional[str] = None
    creator_handle: str
    creator_display_name: str
    creator_avatar_url: Optional[str] = None
    last_action_at: datetime
    created_at: datetime


class OfferDetail(OfferListItem):
    side: Literal["brand", "creator"]        # the CALLER's side
    accepted_revision_id: Optional[UUID] = None
    declined_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    revisions: list[OfferRevisionOut]
    messages: list[OfferMessageOut]
    deliverables: list[DeliverableOut]
    payments: list[PaymentOut]
    creator_payouts_ready: bool              # brand UI: explains why accept may 409


class OfferPage(BaseModel):
    offers: list[OfferListItem]
    total: int


class EarningsRow(BaseModel):
    offer_id: UUID
    offer_title: str
    brand_name: Optional[str] = None
    label: str
    amount_cents: int
    fee_cents: Optional[int] = None
    status: str
    paid_at: Optional[datetime] = None
```

---

# PART 3 — Service: `server/app/cappe/services/collab.py` (new)

All money/state logic in one module; routes stay thin. Full function inventory:

```python
"""Cappe collab domain logic — fee resolution, offer state machine, materializers.

Single choke point: every offer status change goes through transition helpers
here (mirrors matcha discipline's transition_status pattern). Routes never
UPDATE cappe_collab_offers.status directly.
"""
import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..models.collab import CollabTerms
from ...config import get_settings

logger = logging.getLogger("cappe.collab")

TERMINAL_STATUSES = {"completed", "declined", "withdrawn", "cancelled"}
PRE_ACCEPT_STATUSES = {"sent", "negotiating"}
```

### `resolve_marketplace_int(conn, key, subkey, fallback) -> int`

```python
async def resolve_marketplace_int(conn, key: str, subkey: str, fallback: int) -> int:
    """Read an int knob from cappe_marketplace_settings; fall back on missing/garbage."""
    raw = await conn.fetchval("SELECT value FROM cappe_marketplace_settings WHERE key = $1", key)
    if raw is None:
        return fallback
    try:
        val = json.loads(raw) if isinstance(raw, str) else raw
        return int(val[subkey])
    except (KeyError, TypeError, ValueError):
        logger.warning("cappe collab: bad settings row %s=%r, using fallback", key, raw)
        return fallback


async def resolve_collab_fee_bps(conn) -> int:
    return await resolve_marketplace_int(
        conn, "collab_fee_bps", "bps", get_settings().cappe_platform_fee_bps
    )


async def resolve_min_offer_cents(conn) -> int:
    return await resolve_marketplace_int(conn, "min_offer_cents", "cents", 5000)
```

### `expand_deliverables(terms) -> list[dict]`

Quantity-expanded deliverable rows (a `quantity: 3` line → 3 rows), `idx` 0-based
across the whole list:

```python
def expand_deliverables(terms: CollabTerms) -> list[dict]:
    rows, idx = [], 0
    for d in terms.deliverables:
        for _ in range(d.quantity):
            rows.append({"idx": idx, "type": d.type, "platform": d.platform,
                         "spec": d.spec, "due_date": d.due_date})
            idx += 1
    return rows
```

### `build_payment_rows(terms, deliverable_count) -> list[dict]`

```python
def build_payment_rows(terms: CollabTerms, deliverable_count: int) -> list[dict]:
    """Installment plan for the accepted terms. amount sums exactly to
    compensation_cents; remainders land on the LAST row."""
    total = terms.compensation_cents
    if terms.payment_schedule == "upfront":
        return [{"idx": 0, "label": "Full payment", "trigger": "on_accept",
                 "amount_cents": total, "deliverable_idx": None}]
    if terms.payment_schedule == "split_50_50":
        first = total // 2
        return [
            {"idx": 0, "label": "50% on acceptance", "trigger": "on_accept",
             "amount_cents": first, "deliverable_idx": None},
            {"idx": 1, "label": "50% on completion", "trigger": "on_all_approved",
             "amount_cents": total - first, "deliverable_idx": None},
        ]
    # per_deliverable
    n = max(1, deliverable_count)
    base = total // n
    rows = []
    for i in range(n):
        amount = base if i < n - 1 else total - base * (n - 1)
        rows.append({"idx": i, "label": f"Deliverable {i + 1} of {n}",
                     "trigger": "on_deliverable", "amount_cents": amount,
                     "deliverable_idx": i})
    return rows
```

Zero-compensation offers (`compensation_cents == 0`, gifting-only): **skip payment rows
entirely** at accept; completion check then only requires deliverable approval.
`build_payment_rows` is not called when total is 0 (the payments CHECK requires > 0).

### `get_offer_side(conn, offer_id, account_id) -> tuple[record, str]`

```python
async def get_offer_side(conn, offer_id: UUID, account_id: UUID):
    """Load the offer + resolve which side the caller is. 404 on missing or
    non-participant (existence not leaked)."""
    row = await conn.fetchrow(
        """SELECT o.*, p.account_id AS creator_account_id, p.handle AS creator_handle,
                  p.display_name AS creator_display_name, p.avatar_url AS creator_avatar_url,
                  ba.name AS brand_name, ca.stripe_account_id AS creator_stripe_account_id,
                  ca.stripe_charges_enabled AS creator_charges_enabled
             FROM cappe_collab_offers o
             JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
             JOIN cappe_accounts ba ON ba.id = o.brand_account_id
             JOIN cappe_accounts ca ON ca.id = p.account_id
            WHERE o.id = $1""",
        offer_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    if row["brand_account_id"] == account_id:
        return row, "brand"
    if row["creator_account_id"] == account_id:
        return row, "creator"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
```

### `latest_revision(conn, offer_id) -> record`

`SELECT * FROM cappe_collab_offer_revisions WHERE offer_id = $1 ORDER BY revision_no DESC LIMIT 1`.

### `accept_offer(conn, offer_row, side) -> None`

Called inside `async with conn.transaction():` by the route. Steps, in order:

1. Guards (raise `HTTPException` with these exact codes):
   - offer status in `PRE_ACCEPT_STATUSES` else `409 "Offer is not open for acceptance"`.
   - `rev = await latest_revision(...)`; `rev["proposed_by"] != side` else
     `409 "You proposed the latest terms — the other side must accept"`.
   - Parse `terms = CollabTerms.model_validate(loads(rev["terms"]))`.
   - If `terms.compensation_cents > 0`: require `offer_row["creator_stripe_account_id"]`
     AND `offer_row["creator_charges_enabled"]` else
     `409 {"code": "payouts_not_ready", "message": "Creator must finish Stripe payout setup before accepting"}`
     (detail as dict — frontend keys on `code`).
2. `UPDATE cappe_collab_offers SET status='accepted', accepted_revision_id=$rev,
   payment_schedule=$sched, total_cents=$total, accepted_at=NOW(),
   last_action_at=NOW(), updated_at=NOW() WHERE id=$1 AND status = ANY($pre)` —
   re-checks status in the WHERE (concurrency); 0 rows → same 409.
3. Materialize deliverables: `expand_deliverables(terms)` → executemany INSERT into
   `cappe_collab_deliverables (offer_id, idx, type, platform, spec, due_date)`.
   Fetch back `id, idx` for the payment link step.
4. If `terms.compensation_cents > 0`: `build_payment_rows(...)` → INSERT each into
   `cappe_collab_payments`, mapping `deliverable_idx` → deliverable id;
   `on_accept` rows get `status='due', due_at=NOW()`, others `status='scheduled'`.
5. If there are NO payment rows (gifting): offer goes straight
   `accepted → active` (`UPDATE ... SET status='active'`) — active means "underway",
   and with nothing to fund there is nothing to wait for.

### `fire_deliverable_payment(conn, offer_id, deliverable_id) -> Optional[UUID]`

On deliverable approval: `UPDATE cappe_collab_payments SET status='due', due_at=NOW(),
updated_at=NOW() WHERE offer_id=$1 AND deliverable_id=$2 AND trigger='on_deliverable'
AND status='scheduled' RETURNING id`.

### `fire_all_approved_payments(conn, offer_id) -> list[UUID]`

If every deliverable of the offer is `approved`: flip all `on_all_approved` +
`scheduled` payments to `due`. Returns flipped ids (route emails the brand per id).

### `check_completion(conn, offer_id) -> bool`

```sql
SELECT (SELECT COUNT(*) FROM cappe_collab_deliverables
         WHERE offer_id = $1 AND status != 'approved') = 0
   AND (SELECT COUNT(*) FROM cappe_collab_payments
         WHERE offer_id = $1 AND status NOT IN ('paid', 'cancelled')) = 0
```

If true and offer status is `active`:
`UPDATE cappe_collab_offers SET status='completed', completed_at=NOW(),
last_action_at=NOW(), updated_at=NOW() WHERE id=$1 AND status='active'`. Return whether
it flipped (route emails both sides on completion).

### `cancel_offer(conn, offer_row, side, reason) -> None`

Guard: status in `('accepted', 'active')` else 409. Then:
- `UPDATE cappe_collab_offers SET status='cancelled', cancelled_at=NOW(), cancelled_by=$side,
  cancel_reason=$reason, last_action_at=NOW(), updated_at=NOW() WHERE id=$1 AND status IN ('accepted','active')`.
- `UPDATE cappe_collab_payments SET status='cancelled', updated_at=NOW()
  WHERE offer_id=$1 AND status IN ('scheduled', 'due', 'processing')`.
- Paid installments stay `paid` — milestone money is earned; refunds are a manual
  admin action in Stripe, out of scope.

### `touch(conn, offer_id)`

`UPDATE cappe_collab_offers SET last_action_at=NOW(), updated_at=NOW() WHERE id=$1` —
called by message/counter/deliverable routes.

---

# PART 4 — Routes

## 4.1 File: `server/app/cappe/routes/creators.py` (new — authed creator self-service)

Header block:

```python
"""Cappe creator self-service — profile (media kit), socials, portfolio, rates,
review submission, media upload, earnings. The public directory lives in
routes/public/creators.py; offers live in routes/collab.py."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeUploadResponse
from ..models.creators import (...)
from ._shared import loads, read_capped

router = APIRouter()
```

Shared guard used by every route here:

```python
def _require_creator(account: CappeAccount) -> None:
    if account.account_type != "creator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Creator account required")
```

Fetch helper (used by `/creators/me` + returned after mutations):

```python
_PROFILE_COLS = (
    "id, handle, display_name, avatar_url, cover_url, bio, location, niches, languages, "
    "open_to_offers, status, review_note, submitted_at, published_at, "
    "reach_verified, reach_audited_at"
)

async def _load_me(conn, account_id: UUID) -> dict:
    prof = await conn.fetchrow(
        f"SELECT {_PROFILE_COLS} FROM cappe_creator_profiles WHERE account_id = $1", account_id)
    if prof is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No creator profile yet")
    d = dict(prof)
    d["socials"] = [dict(r) for r in await conn.fetch(
        "SELECT id, platform, handle, url, follower_count, engagement_rate, audit_status, "
        "verified_follower_count, audited_at, sort_order FROM cappe_creator_socials "
        "WHERE profile_id = $1 ORDER BY sort_order, created_at", prof["id"])]
    d["portfolio"] = [...]   # same shape: SELECT ... FROM cappe_creator_portfolio_items ORDER BY sort_order, created_at
    d["rates"] = [...]       # SELECT ... FROM cappe_creator_rate_cards ORDER BY sort_order, created_at
    # metrics JSONB → loads() per row
    return d
```

### Endpoints (all `Depends(require_cappe_account)` + `_require_creator`)

| Route | Behavior |
|---|---|
| `GET /creators/me` → `CreatorProfileMe` | `_load_me`. 404 if none (frontend shows create form). |
| `POST /creators/me` (201) → `CreatorProfileMe` | Body `CreatorProfileCreate`. INSERT `(account_id, handle, display_name)`; on `UniqueViolationError` for the handle index → `409 "Handle is taken"`; account_id unique violation → `409 "Profile already exists"`. |
| `PATCH /creators/me` → `CreatorProfileMe` | Body `CreatorProfileUpdate`. Build SET clause from `model_dump(exclude_unset=True)`; always `+ updated_at=NOW()`. No status change — a published profile stays live on edit. |
| `POST /creators/me/submit` → `CreatorProfileMe` | Guard status in `('draft','rejected')` else `409 "Profile is not in a submittable state"`. Quality gate: require ≥1 social AND (bio non-empty OR ≥1 portfolio item) else `422 "Add at least one social account and a bio or portfolio item first"`. `UPDATE ... SET status='pending_review', submitted_at=NOW(), review_note=NULL`. |
| `PUT /creators/me/socials` → `list[CreatorSocial]` | Body `list[CreatorSocialUpsert]` (max 12). **Replace-all inside one transaction**: DELETE existing for profile, INSERT the list, `audit_status='unverified'` on every row (any social edit resets audits — simplest correct rule), then recompute `reach_verified` (goes false unless some row is still verified — after replace-all it is always false) + `updated_at=NOW()` on the profile. |
| `PUT /creators/me/portfolio` → `list[CreatorPortfolioItem]` | Replace-all, max 24 items. `metrics` → `json.dumps`. Require `media_url or external_url` per item else 422. |
| `PUT /creators/me/rates` → `list[CreatorRate]` | Replace-all, max 20. The UNIQUE(profile_id, type, platform) dedupes — catch UniqueViolation → `422 "Duplicate rate for the same deliverable and platform"`. |
| `POST /creators/me/upload` → `CappeUploadResponse` | Multipart `file`. Images (`image/jpeg,png,gif,webp`, 5 MB via `read_capped`) or video (`video/mp4,webm,quicktime`, 50 MB). `get_storage().upload_file(file_bytes=data, filename=..., prefix="cappe", content_type=...)`. No `cappe_assets` record (that catalog is site-scoped). Used for avatar, cover, portfolio media, deliverable proof. |
| `GET /creators/me/earnings` → `list[EarningsRow]` | `SELECT p.offer_id, o.title AS offer_title, ba.name AS brand_name, p.label, p.amount_cents, p.fee_cents, p.status, p.paid_at FROM cappe_collab_payments p JOIN cappe_collab_offers o ON o.id=p.offer_id JOIN cappe_creator_profiles cp ON cp.id=o.creator_profile_id JOIN cappe_accounts ba ON ba.id=o.brand_account_id WHERE cp.account_id=$1 ORDER BY COALESCE(p.paid_at, p.due_at, p.created_at) DESC` |

Replace-all PUTs: socials replace-all deliberately nukes audit state; the admin re-audits.
Portfolio/rates replace-all regenerate ids — acceptable, nothing FKs them (offers denorm
terms; rate card is prefill-only).

## 4.2 File: `server/app/cappe/routes/public/creators.py` (new — anonymous directory)

Mirrors `routes/public/directory.py`: per-IP rate limit, capped limit, published-only.

```python
"""Public creator directory + profile pages. Anonymous; published profiles only.
Flagged socials are hidden everywhere public."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, status

from ....core.services.redis_cache import check_rate_limit
from ....database import get_connection
from ...models.creators import PublicCreatorPage, PublicCreatorProfile, CREATOR_NICHES
from ._common import client_ip     # same helper directory.py uses
from .._shared import loads

router = APIRouter()
_MAX_LIMIT = 24


async def _rate(request: Request) -> None:
    await check_rate_limit(client_ip(request), "cappe_pub_creators", 30, 60)
```

### `GET /public/creators` → `PublicCreatorPage`

Query params: `niche: Optional[str]`, `platform: Optional[str]`,
`min_followers: Optional[int] (ge=0)`, `max_rate_cents: Optional[int] (ge=0)`,
`location: Optional[str]`, `q: Optional[str]`, `verified_only: bool = False`,
`limit: int = Query(12, ge=1, le=_MAX_LIMIT)`, `offset: int = Query(0, ge=0, le=500)`.

One query (build WHERE parts + params list; every filter `IS NULL OR` guarded):

```sql
WITH base AS (
    SELECT p.id, p.handle, p.display_name, p.avatar_url, p.cover_url, p.bio,
           p.location, p.niches, p.reach_verified,
           COALESCE((SELECT MAX(COALESCE(s.verified_follower_count, s.follower_count))
                       FROM cappe_creator_socials s
                      WHERE s.profile_id = p.id AND s.audit_status != 'flagged'), 0) AS max_followers,
           (SELECT MIN(r.price_cents) FROM cappe_creator_rate_cards r
             WHERE r.profile_id = p.id) AS min_rate_cents,
           ARRAY(SELECT DISTINCT s.platform FROM cappe_creator_socials s
                  WHERE s.profile_id = p.id AND s.audit_status != 'flagged') AS platforms
      FROM cappe_creator_profiles p
     WHERE p.status = 'published' AND p.open_to_offers = true
       AND ($1::text IS NULL OR $1 = ANY(p.niches))
       AND ($2::text IS NULL OR EXISTS (SELECT 1 FROM cappe_creator_socials s2
                WHERE s2.profile_id = p.id AND s2.platform = $2 AND s2.audit_status != 'flagged'))
       AND ($3::text IS NULL OR p.location ILIKE '%' || $3 || '%')
       AND ($4::text IS NULL OR p.display_name ILIKE '%' || $4 || '%'
            OR p.handle ILIKE '%' || $4 || '%' OR p.bio ILIKE '%' || $4 || '%')
       AND ($5::bool = false OR p.reach_verified = true)
)
SELECT *, COUNT(*) OVER() AS total FROM base
 WHERE ($6::int IS NULL OR max_followers >= $6)
   AND ($7::int IS NULL OR (min_rate_cents IS NOT NULL AND min_rate_cents <= $7))
 ORDER BY reach_verified DESC, max_followers DESC, handle
 LIMIT $8 OFFSET $9
```

Truncate `bio` to 200 chars server-side for cards. `total` from the window (0 rows → 0).

### `GET /public/creators/{handle}` → `PublicCreatorProfile`

`handle.lstrip('@').lower()`. Profile `WHERE lower(handle) = $1 AND status = 'published'`
else 404. Socials `WHERE profile_id = $1 AND audit_status != 'flagged' ORDER BY sort_order`;
portfolio + rates full lists. Include profile `id` (offer composer needs it).
Also `_rate(request)` on both endpoints.

### Wiring: `routes/public/__init__.py`

Add `creators` to the `from . import (...)` tuple + `router.include_router(creators.router)`
after `directory`.

## 4.3 File: `server/app/cappe/routes/collab.py` (new — offers, both sides)

One role-aware router. Every endpoint: `require_cappe_account` →
`services.collab.get_offer_side(conn, offer_id, account.id)` (or brand-only guard for
create/campaigns). Brand-only actions check `side == "brand"` else
`403 "Only the brand can do this"`; creator-only likewise.

```python
"""Cappe collabs — brand↔creator offers: negotiation (immutable terms revisions),
chat, deliverables, installment payments via Stripe Connect direct charges.
State machine + money logic live in services/collab.py; routes stay thin."""
```

Imports: `get_connection`, `require_cappe_account`, models from `..models.collab`,
`from ..services import collab as svc`, `from ..services.stripe_connect import
CappeStripeError, get_cappe_stripe`, `from ..services.email import (...)`,
`from ...core.services.redis_cache import check_rate_limit`, `from ._shared import loads`.

Rate limit on creation/counter/message: `await check_rate_limit(str(account.id),
"cappe_collab_write", 60, 3600)` (mirrors `_owner_msg_request_ok`).

### Campaigns (brand-only; guard `account.account_type == 'business'` else 403)

| Route | SQL |
|---|---|
| `GET /collab/campaigns` → `list[Campaign]` | `SELECT c.*, (SELECT COUNT(*) FROM cappe_collab_offers o WHERE o.campaign_id = c.id) AS offer_count FROM cappe_collab_campaigns c WHERE brand_account_id = $1 ORDER BY created_at DESC` |
| `POST /collab/campaigns` (201) | INSERT from `CampaignUpsert` (status defaults active) |
| `PATCH /collab/campaigns/{id}` | exclude_unset SET; `WHERE id = $1 AND brand_account_id = $2`; 404 on 0 rows |

### `POST /collab/offers` (201) → `OfferDetail` — brand composes + sends

1. Guard `account.account_type == "business"` else `403 "Only business accounts can send offers"`.
2. Rate limit (above).
3. Load target: `SELECT id, status, open_to_offers, account_id FROM cappe_creator_profiles
   WHERE id = $1`; require `status='published'` AND `open_to_offers` else
   `409 "This creator is not accepting offers"`. Require `account_id != account.id`
   (a creator-owned business paying itself — reject 422).
4. If `campaign_id`: verify `brand_account_id = account.id` else 404.
5. `min_cents = await svc.resolve_min_offer_cents(conn)`; if
   `0 < terms.compensation_cents < min_cents` → `422 f"Minimum offer is ${min_cents/100:.0f}"`
   (0 allowed = gifting-only).
6. Transaction: INSERT offer (`status='sent'`, title, campaign_id, brand_account_id,
   creator_profile_id) → INSERT revision `(offer_id, revision_no=1, proposed_by='brand',
   terms=json.dumps(body.terms.model_dump(mode="json")), message)` → if `body.message`,
   INSERT `cappe_collab_messages (offer_id, sender='brand', sender_account_id, body,
   revision_id)`.
7. `background.add_task(send_cappe_offer_received_email, creator_email, creator_name,
   brand_name, offer_title, deep_link)` — creator email via
   `SELECT email, name FROM cappe_accounts WHERE id = profile.account_id`.
8. Return assembled detail (shared `_offer_detail(conn, offer_id, account_id)` helper — below).

### `GET /collab/offers?side=&status=&limit=&offset=` → `OfferPage`

`side: Literal['brand','creator']` **required** (explicit — one account can be only one
side today, but the param keeps the query index-aligned). `status` optional CSV filter.

- side=brand: `WHERE o.brand_account_id = $1` (guard account_type business).
- side=creator: join profile `WHERE p.account_id = $1` (guard account_type creator).
- SELECT the `OfferListItem` columns (join accounts + profiles for display fields),
  `ORDER BY o.last_action_at DESC LIMIT $n OFFSET $m`, `COUNT(*) OVER() AS total`.

### `GET /collab/offers/{offer_id}` → `OfferDetail`

`_offer_detail` helper: `get_offer_side` → four child fetches ordered by
`revision_no` / `created_at` / `idx` / `idx`; parse each revision's `terms` through
`CollabTerms.model_validate(loads(...))` (garbage rows 500 loudly — they can't exist
except by bug); `creator_payouts_ready = bool(stripe_account_id and charges_enabled)`;
`side` from resolver.

### `POST /collab/offers/{offer_id}/counter` → `OfferDetail`

1. `get_offer_side`; guard status in `svc.PRE_ACCEPT_STATUSES` else
   `409 "Offer is no longer negotiable"`. Rate limit.
2. Same min-offer check as create.
3. Transaction: `rev_no = (SELECT COALESCE(MAX(revision_no),0)+1 ...)`; INSERT revision
   `proposed_by=side`; if first counter (`rev_no == 2`) or already negotiating:
   `UPDATE cappe_collab_offers SET status='negotiating' WHERE id=$1 AND status IN ('sent','negotiating')`;
   optional message row (`revision_id` set); `svc.touch`.
4. Email counterparty: `send_cappe_offer_counter_email`.

### `POST /collab/offers/{offer_id}/accept` → `OfferDetail`

Transaction → `svc.accept_offer(conn, offer_row, side)`. After commit: email both
(`send_cappe_offer_accepted_email` ×2 — one includes "fund the first installment"
CTA to the brand when an `on_accept` payment exists).

### `POST /collab/offers/{offer_id}/decline` (creator-only) / `withdraw` (brand-only)

Guard status pre-accept else 409. decline: body `OfferDecline`;
`SET status='declined', declined_at=NOW(), declined_reason=$r`. withdraw:
`SET status='withdrawn'` (reuse `declined_at/declined_reason`? **no** — leave null;
withdrawn needs no reason). Both `last_action_at=NOW()`. Email counterparty.

### `POST /collab/offers/{offer_id}/cancel`

Body `OfferCancel` (reason required). Either side. → `svc.cancel_offer`. Email counterparty.

### `POST /collab/offers/{offer_id}/messages` (201) → `OfferMessageOut`

Guard status NOT in `svc.TERMINAL_STATUSES` else `409 "Conversation is closed"`.
Rate limit. INSERT (`sender=side`); `svc.touch`. Email counterparty
(`send_cappe_collab_message_email`) — reuse the per-recipient send-budget pattern from
`messages.py:_recipient_send_ok` (bucket `"cappe_collab_msg_to"`, 20/hr) so chat spam
can't storm inboxes; message row always written, only the email is skipped.

### Deliverables

| Route | Rules |
|---|---|
| `POST .../deliverables/{did}/submit` (creator) → `DeliverableOut` | Offer status `active` else 409. Deliverable status in `('pending','revision_requested')` else `409 "Already submitted or approved"`. `SET status='submitted', submission_url, submission_note, proof_media_url, submitted_at=NOW()`. `svc.touch`. Email brand. |
| `POST .../deliverables/{did}/approve` (brand) → `OfferDetail` | Deliverable status `submitted` else 409. Transaction: `SET status='approved', approved_at=NOW()`; `svc.fire_deliverable_payment` (email brand "payment due" per fired id); if all approved → `svc.fire_all_approved_payments` (email per id); `svc.check_completion` (flip → email both "collab completed"). Email creator "deliverable approved". |
| `POST .../deliverables/{did}/request-revision` (brand) → `DeliverableOut` | Body `DeliverableRevision`. Deliverable `submitted` else 409. Load accepted terms → `revision_rounds`; if `revision_count >= revision_rounds` → `422 f"Revision limit reached ({revision_rounds}) — approve or cancel"`. `SET status='revision_requested', review_note=$n, revision_count=revision_count+1`. Email creator. |

### `POST /collab/offers/{offer_id}/payments/{payment_id}/checkout` (brand) → `{url: str}`

1. `get_offer_side`, side=brand. Load payment `WHERE id=$pid AND offer_id=$oid`;
   status in `('due','processing')` else `409 "Payment is not due"` (processing allowed —
   re-click after abandoned checkout mints a fresh session; old one just expires).
2. `fee_bps = await svc.resolve_collab_fee_bps(conn)`;
   `fee = max(0, amount_cents * fee_bps // 10_000)`.
3. **Release the connection** (exit the ctx) before Stripe:
   `get_cappe_stripe().create_checkout_session(account_id=offer["creator_stripe_account_id"],
   currency=payment["currency"], line_items=[{"price_data": {"currency": ...,
   "unit_amount": amount_cents, "product_data": {"name": f"{offer_title} — {label}"}},
   "quantity": 1}], application_fee_cents=fee,
   success_url=f"{dashboard_url(f'/collabs/{offer_id}')}?paid=1",
   cancel_url=dashboard_url(f'/collabs/{offer_id}'),
   metadata={"collab_payment_id": str(pid), "offer_id": str(oid),
             "platform_fee_cents": str(fee)},
   customer_email=account.email)` — direct charge ON the creator's connected account
   with the fee swept to the platform, exactly like storefront orders.
   `CappeStripeError` → 502.
4. Re-acquire conn: `UPDATE cappe_collab_payments SET status='processing',
   stripe_checkout_session_id=$s, fee_bps_snapshot=$bps, fee_cents=$fee,
   updated_at=NOW() WHERE id=$pid`.
5. Return `{"url": session["url"]}` — frontend does `window.location.href = url`.

## 4.4 Webhook branch — edit `server/app/cappe/routes/payments.py`

In `_handle_connect_event`, inside the existing `checkout.session.completed` arm, after
the order branch (the dedupe + release-on-exception wrapper already covers this):

```python
        collab_payment_id = meta.get("collab_payment_id")
        if collab_payment_id and event_account_id:
            try:
                cpid = UUID(str(collab_payment_id))
            except (ValueError, TypeError):
                cpid = None
            if cpid is not None:
                async with get_connection() as conn:
                    row = await conn.fetchrow(
                        """UPDATE cappe_collab_payments cp
                              SET status = 'paid', paid_at = NOW(),
                                  stripe_payment_intent = $2, updated_at = NOW()
                             FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                            WHERE cp.id = $1 AND cp.status IN ('due', 'processing')
                              AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                              AND ca.id = p.account_id AND ca.stripe_account_id = $3
                        RETURNING cp.offer_id, cp.trigger, cp.label, cp.amount_cents""",
                        cpid, obj.get("payment_intent"), event_account_id,
                    )
                    if row is not None:
                        if row["trigger"] == "on_accept":
                            await conn.execute(
                                "UPDATE cappe_collab_offers SET status = 'active', "
                                "last_action_at = NOW(), updated_at = NOW() "
                                "WHERE id = $1 AND status = 'accepted'", row["offer_id"])
                        from ..services.collab import check_completion
                        await check_completion(conn, row["offer_id"])
                if row is not None:
                    background.add_task(_notify_collab_paid, row["offer_id"], row["label"], row["amount_cents"])
                else:
                    logger.warning("cappe collab webhook: payment %s not matched to account %s",
                                   collab_payment_id, event_account_id)
```

`_notify_collab_paid` (module-level helper in payments.py): loads creator email +
offer title, sends `send_cappe_collab_paid_email`. The ownership join mirrors the order
branch's defense — a connected account can't mark another creator's installment paid.

## 4.5 Wiring: `server/app/cappe/routes/__init__.py`

```python
from .collab import router as collab_router
from .creators import router as creators_router
```
Include after `messages_router`:
```python
cappe_router.include_router(creators_router)
cappe_router.include_router(collab_router)
```
(Public creators router rides the existing `public_router` mount.)

---

# PART 5 — Emails (edit `server/app/cappe/services/email.py`)

All use `_email_shell(heading, body_html, cta_label=..., cta_url=...)` + `_send(...)`;
`escape()` every interpolated value; plain-text fallback string per sender (existing
pattern). `dashboard_url(path)` builds links. New senders — signatures:

```python
async def send_cappe_offer_received_email(to_email, to_name, brand_name, offer_title, link)
    # subj: f"New brand offer: {offer_title}"       cta: "View offer"
async def send_cappe_offer_counter_email(to_email, to_name, counterpart_name, offer_title, link)
    # subj: f"New terms proposed on {offer_title}"  cta: "Review terms"
async def send_cappe_offer_accepted_email(to_email, to_name, offer_title, link, *, funding_due: bool)
    # subj: f"Offer accepted: {offer_title}"; funding_due=True variant appends
    # "The first installment is now due." cta: "Fund now" / "View collab"
async def send_cappe_offer_closed_email(to_email, to_name, offer_title, verb, reason, link)
    # verb in {"declined","withdrawn","cancelled"}; subj: f"Offer {verb}: {offer_title}"
async def send_cappe_collab_message_email(to_email, to_name, from_name, offer_title, body, link)
    # subj: f"{from_name} on {offer_title}"; body truncated 300 chars; cta "Reply"
async def send_cappe_deliverable_submitted_email(to_email, to_name, offer_title, deliverable_label, link)
    # subj: f"Deliverable submitted — {offer_title}"  cta "Review"
async def send_cappe_deliverable_decision_email(to_email, to_name, offer_title, deliverable_label, approved: bool, note, link)
    # approved → "Deliverable approved 🎉"; else "Changes requested" + note
async def send_cappe_collab_payment_due_email(to_email, to_name, offer_title, label, amount_cents, link)
    # to BRAND; subj: f"Payment due — {offer_title}"; fmt_money(amount_cents); cta "Pay now"
async def send_cappe_collab_paid_email(to_email, to_name, offer_title, label, amount_cents, link)
    # to CREATOR; subj: f"You got paid — {offer_title}"
async def send_cappe_collab_completed_email(to_email, to_name, offer_title, link)
    # both sides; subj: f"Collab completed: {offer_title}"
async def send_cappe_profile_review_email(to_email, to_name, approved: bool, note, link)
    # approved → "Your creator profile is live on Gummfit" (link = public profile URL);
    # rejected → "Your profile needs changes" + escaped note, cta "Edit profile"
```

Deep-link paths used by routes: creator side `dashboard_url(f"/creator/deals/{offer_id}")`,
brand side `dashboard_url(f"/collabs/{offer_id}")`, profile editor `dashboard_url("/creator")`.
`dashboard_url` prefixes `/cappe` (verify its existing output; it already builds
`{base}/cappe{path}` for site links — reuse as-is).

All sends are `background.add_task(...)` from routes — never inline.

---

# PART 6 — Matcha admin (backend)

## File: `server/app/core/routes/admin/cappe_creators.py` (new)

Style-match `admin/research.py` cappe section: `require_admin` per-route deps, raw SQL,
no cappe imports. `from app.core.dependencies import require_admin` etc. (absolute
imports, per admin package convention). Audit every mutation:

```python
async def _audit(conn, admin_user, action: str, target: str, payload: dict) -> None:
    await conn.execute(
        "INSERT INTO cappe_admin_audit (actor_account_id, action, target, payload) "
        "VALUES (NULL, $1, $2, $3::jsonb)",
        f"matcha:{action}", target,
        json.dumps({**payload, "admin_email": admin_user.email}),
    )
```
(`actor_account_id` NULL is legal — column is nullable; `matcha:` prefix + email in
payload identify the actor.)

### Endpoints (all `dependencies=[Depends(require_admin)]` or param-injected admin user)

**`GET /admin/cappe/creators?status=`** — full roster for the admin table:

```sql
SELECT p.id, p.handle, p.display_name, p.avatar_url, p.status, p.review_note,
       p.niches, p.location, p.open_to_offers, p.reach_verified, p.reach_audited_at,
       p.submitted_at, p.published_at, p.created_at,
       a.email, a.name AS account_name,
       COALESCE(json_agg(json_build_object(
           'id', s.id, 'platform', s.platform, 'handle', s.handle, 'url', s.url,
           'follower_count', s.follower_count,
           'verified_follower_count', s.verified_follower_count,
           'audit_status', s.audit_status, 'audited_at', s.audited_at,
           'audit_note', s.audit_note
       ) ORDER BY s.sort_order) FILTER (WHERE s.id IS NOT NULL), '[]') AS socials
  FROM cappe_creator_profiles p
  JOIN cappe_accounts a ON a.id = p.account_id
  LEFT JOIN cappe_creator_socials s ON s.profile_id = p.id
 WHERE ($1::text IS NULL OR p.status = $1)
 GROUP BY p.id, a.email, a.name
 ORDER BY (p.status = 'pending_review') DESC, p.submitted_at DESC NULLS LAST, p.created_at DESC
```

Plus a `reaudit_due` computed bool per row: `reach_audited_at IS NOT NULL AND
reach_audited_at < NOW() - INTERVAL '90 days'`.

**`POST /admin/cappe/creators/{profile_id}/approve`** — guard current status
`pending_review` else 409. `SET status='published', reviewed_at=NOW(),
published_at=COALESCE(published_at, NOW()), review_note=NULL, updated_at=NOW()`.
Audit `creators.approve`. Background email `send_cappe_profile_review_email(approved=True,
link=f"https://gummfit.com/creators/{handle}")` — email import: the ONE place core would
import cappe. **Don't** — instead inline the send here via
`app.core.services.email.get_email_service()` with a minimal HTML body, or (preferred,
zero-boundary-noise) do it cappe-side: add tiny public-of-core helper? Resolution:
**core admin sends via `get_email_service().send_email_with_fallback` directly with an
inline template** (approve/reject only — 2 short emails; keeps `core → cappe` at 0 edges).

**`POST /admin/cappe/creators/{profile_id}/reject`** — body `{note: str}` (required,
1–2000). Guard `pending_review`. `SET status='rejected', reviewed_at=NOW(),
review_note=$note`. Audit + email (inline, as above).

**`POST /admin/cappe/creators/{profile_id}/suspend`** — body `{note: Optional[str]}`.
Guard `published`. `SET status='suspended', review_note=$note`. Audit. (Un-suspend =
approve endpoint? No — guard blocks it. Add **`POST .../restore`**: guard `suspended` →
`SET status='published'`. Audit.)

**`POST /admin/cappe/creators/socials/{social_id}/audit`** — body
`{audit_status: Literal['verified','flagged','unverified'], verified_follower_count:
Optional[int] (required when verified), note: Optional[str]}`. Transaction:

```sql
UPDATE cappe_creator_socials SET audit_status=$2, verified_follower_count=$3,
       audit_note=$4, audited_at=NOW(), audited_by=$5, updated_at=NOW()
 WHERE id = $1 RETURNING profile_id;
-- recompute profile badge:
UPDATE cappe_creator_profiles p SET
    reach_verified = EXISTS (SELECT 1 FROM cappe_creator_socials s
                              WHERE s.profile_id = p.id AND s.audit_status='verified')
               AND NOT EXISTS (SELECT 1 FROM cappe_creator_socials s
                              WHERE s.profile_id = p.id AND s.audit_status='flagged'),
    reach_audited_at = NOW(), updated_at = NOW()
 WHERE p.id = $profile_id;
```

`audited_by` = admin email. Audit log `creators.social_audit`.

**`GET /admin/cappe/marketplace-settings`** → `{collab_fee_bps: int, min_offer_cents: int}`
(resolved with the same fallbacks as the service).
**`PATCH /admin/cappe/marketplace-settings`** — body `{collab_fee_bps?: int (0..5000),
min_offer_cents?: int (0..10_000_000)}`. Whitelisted keys only; UPSERT
`INSERT ... ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=NOW()` per provided key.
Audit `creators.settings` with old+new in payload.

**`GET /admin/cappe/collab-overview`** — ops stats:

```sql
SELECT status, COUNT(*) AS n, COALESCE(SUM(total_cents),0) AS total_cents
  FROM cappe_collab_offers GROUP BY status;
SELECT COALESCE(SUM(amount_cents),0) AS gmv_cents, COALESCE(SUM(fee_cents),0) AS fees_cents
  FROM cappe_collab_payments WHERE status='paid';
```

### Wiring: `server/app/core/routes/admin/__init__.py`

`from app.core.routes.admin.cappe_creators import router as _cappe_creators` + add
`_cappe_creators` to the include loop tuple.

---

# PART 7 — Frontend (Cappe app)

## 7.1 Types — append to `client/src/cappe/types.ts`

TS mirrors of Part 2 response models (snake_case fields, `type` aliases):
`CappeAccountType = 'business' | 'personal' | 'creator'` (**edit existing alias**),
`CreatorSocial`, `CreatorPortfolioItem`, `CreatorRate`, `CreatorProfileMe`,
`PublicCreatorCard`, `PublicCreatorProfile`, `PublicCreatorPage`, `CollabTerms`,
`TermsDeliverable`, `OfferListItem`, `OfferDetail`, `OfferRevision`, `OfferMessage`,
`Deliverable`, `CollabPayment`, `Campaign`, `EarningsRow`, plus:

```ts
export const CREATOR_NICHES = ['fitness','beauty','fashion','food','travel','tech','gaming','music','art','parenting','finance','health','sports','comedy','education','lifestyle','outdoors','pets','diy','other'] as const
export const SOCIAL_PLATFORMS = ['instagram','tiktok','youtube','x','twitch','facebook','linkedin','other'] as const
export const DELIVERABLE_TYPES = ['post','reel','story','video','short','stream','ugc','blog','other'] as const
export const PAYMENT_SCHEDULES = [
  { value: 'upfront',        label: 'Upfront',         blurb: '100% when the offer is accepted' },
  { value: 'split_50_50',    label: '50 / 50',         blurb: 'Half on acceptance, half when all deliverables are approved' },
  { value: 'per_deliverable',label: 'Per deliverable', blurb: 'Each deliverable pays out on approval' },
] as const
export const fmtCents = (c: number, currency = 'usd') =>
  (c / 100).toLocaleString('en-US', { style: 'currency', currency: currency.toUpperCase() })
```

## 7.2 Status badges — edit `client/src/cappe/components/ui.ts`

Add to `statusBadge`: `negotiating: 'bg-amber-500/15 text-amber-400'`,
`accepted: 'bg-sky-500/15 text-sky-400'`, `completed: 'bg-sky-500/15 text-sky-400'`,
`declined/withdrawn: 'bg-zinc-800 text-zinc-500'`, `submitted: 'bg-amber-500/15 text-amber-400'`,
`revision_requested: 'bg-orange-500/15 text-orange-400'`, `approved: 'bg-emerald-500/15 text-emerald-400'`,
`due: 'bg-amber-500/15 text-amber-400'`, `processing: 'bg-amber-500/15 text-amber-400'`,
`failed: 'bg-red-500/15 text-red-400'`, `pending_review: 'bg-amber-500/15 text-amber-400'`,
`rejected/suspended/flagged: 'bg-red-500/15 text-red-400'`,
`verified: 'bg-emerald-500/15 text-emerald-400'`, `unverified: 'bg-zinc-800 text-zinc-400'`.

## 7.3 New folder `client/src/cappe/creators/` — files

All pages use `ui.*` atoms, `cappeApi` / `cappePublicGet`, lucide icons, controlled
inputs, `useState`+`useEffect` (no query lib). Lazy-load everything authed (mirror
routes.tsx's existing lazy block).

### `CreatorsLanding.tsx` — public `/for-creators`
Marketing page: hero ("Get paid to create for brands you love"), 3 value cards
(Build your media kit / Get verified reach / Negotiate + get paid), CTA button →
`/cappe/website-setup?type=creator`. Static, no API.

### `CreatorDirectory.tsx` — public `/creators`
- State: `filters {niche, platform, minFollowers, maxRateCents, location, q, verifiedOnly}`,
  `page`, `data: PublicCreatorPage | null`, `loading`.
- Fetch `cappePublicGet<PublicCreatorPage>('/public/creators?...')` (URLSearchParams,
  skip empty — copy `cappeDirectoryQueryString` helper pattern; add
  `fetchPublicCreators(query)` + `fetchPublicCreator(handle)` helpers at the bottom of
  `api.ts` next to the existing directory helpers, same `cappePublicGet` rationale comment).
- Filter bar: niche `<select>` (CREATOR_NICHES), platform `<select>`, min-followers
  `<select>` (1k/10k/50k/100k/500k), max-rate `<select>` ($100/$250/$500/$1k/$5k),
  text input `q`, "Verified reach only" checkbox. Debounce text 300ms.
- Grid of cards (`ui.cardHover`): cover strip (h-24, cover_url or zinc-800), avatar circle
  overlapping, display_name + `@handle`, verified badge (`<BadgeCheck>` lucide, emerald)
  when `reach_verified`, follower count (`Intl.NumberFormat` compact), niches as chips,
  `min_rate_cents` → "From $X", platform icons row. Card → `/cappe/creators/{handle}`
  (relative link works on both mounts — use `to={\`/cappe/creators/${c.handle}\`}` matching
  sidebar's hardcoded-/cappe convention).
- Pagination: Prev/Next off `total`.
- If `useCappeMe().account?.account_type === 'business'`: header CTA hint "Click a creator
  to send an offer".

### `CreatorPublicProfile.tsx` — public `/creators/:handle`
- Fetch `fetchPublicCreator(handle)`. 404 → "Creator not found".
- Layout: cover (h-48), avatar (h-24 w-24 rounded-full ring), name + @handle + location +
  niches chips; **verified block**: when `reach_verified`, emerald card "Reach verified by
  Gummfit on {date(reach_audited_at)}".
- Socials list: platform icon + handle link (`target="_blank" rel="noopener"`) + count —
  show `verified_follower_count` with ✓ when `audit_status==='verified'`, else
  self-reported count in `ui.muted` with "(self-reported)".
- Portfolio grid: media (img / video tag) or external link card; title, brand_name chip,
  description.
- Rate card table: type × platform → `fmtCents(price_cents)`, "negotiable" tag.
- **Offer CTA** (right-aligned sticky header button): visible when
  `account?.account_type === 'business'` → opens `<SendOfferSheet profile={...} />`.
  When unauthenticated: button "Work with {name}" → `/cappe/login`. When creator/personal:
  hidden.

### `SendOfferSheet.tsx` — component (brand offer composer)
Props: `{ profile: PublicCreatorProfile, onClose(), onSent(offerId: string) }`. Modal/sheet
(`fixed inset-0` overlay + right panel, matching existing cappe modal patterns e.g.
`StockAdjustModal`).
- Form state = `title`, `campaign_id` (select from `GET /collab/campaigns` + "New campaign"
  inline create), and a `CollabTerms` object.
- **Deliverables builder**: rows of {type select, platform select, quantity number 1–20,
  due_date date, spec textarea}; add/remove row. Prefill: clicking a rate-card row in the
  sheet's "Their rates" sidebar appends a deliverable of that type/platform and adds
  `price_cents` to a running suggested total.
- Compensation: dollar input → cents; `payment_schedule` radio group from
  `PAYMENT_SCHEDULES`; live **installment preview** box computing the exact split with the
  same remainder rule as the backend (first = floor for 50/50; last row absorbs remainder
  per-deliverable) so the brand sees "$500 now · $500 on completion".
- Usage rights (scope radio organic/paid + months + whitelisting checkbox), exclusivity
  (toggle + category + months), revision_rounds (0–5 select), approval_required +
  ftc_disclosure checkboxes, start/end dates, notes, cover message textarea.
- Submit: `cappeApi.post<OfferDetail>('/collab/offers', {creator_profile_id: profile.id,
  campaign_id, title, terms, message})` → `onSent(id)` → navigate `/cappe/collabs/{id}`.
  Error string shown inline (min-offer / not-accepting 409s come as `Error.message`).

### `TermSheet.tsx` — component (shared renderer)
Props: `{ terms: CollabTerms, previous?: CollabTerms | null }`. Definition-list of every
term (compensation via `fmtCents`, schedule label, deliverables table, usage rights
sentence, exclusivity sentence or "None", revision rounds, approval/FTC yes-no, dates,
notes). When `previous` given, any changed field gets
`bg-amber-500/10 ring-1 ring-amber-500/30 rounded px-1` highlight — diff by
`JSON.stringify` comparison per field.

### `OfferDetailPage.tsx` — authed, shared both sides (`/cappe/collabs/:offerId` and `/cappe/creator/deals/:offerId` both render this)
- Fetch `cappeApi.get<OfferDetail>('/collab/offers/{id}')`; `side` comes from the payload.
- Header: title, status badge (`badgeFor`), counterpart identity (brand sees creator
  avatar/handle → link to public profile; creator sees brand_name), total + schedule.
- 3-column-ish layout (stack on mobile):
  1. **Term sheet panel**: `<TermSheet terms={latestRevision.terms}
     previous={revisions[n-2]?.terms} />` + revision history accordion (rev N by side,
     date, message). Action row by state:
     - pre-accept + caller ≠ proposer of latest: **Accept** (primary) — on
       `code==='payouts_not_ready'` 409 (creator side sees this before accepting), render
       amber card embedding `<StripeConnectCard />` (reused as-is — account-level).
     - pre-accept both sides: **Counter** → `<CounterSheet>` = SendOfferSheet's terms form
       seeded from latest terms, POST `/counter`.
     - creator pre-accept: **Decline** (reason prompt); brand pre-accept: **Withdraw**.
     - accepted/active: **Cancel** (reason required, confirm dialog warning "paid
       installments are not refunded automatically").
  2. **Deliverables panel**: list of `DeliverableOut` rows — type/platform/idx, due date,
     status badge, spec collapse. Creator on `pending`/`revision_requested`: **Submit**
     inline form (URL input, note, optional proof upload via
     `cappeApi.upload('/creators/me/upload', fd)` → sets proof_media_url). Brand on
     `submitted`: **Approve** / **Request changes** (note textarea; disabled with tooltip
     when `revision_count >= terms.revision_rounds`). Show `review_note` when
     revision_requested.
  3. **Payments panel**: timeline rows — label, `fmtCents(amount)`, trigger text, status
     badge, paid_at. Brand on `due`/`processing`: **Pay** button →
     `cappeApi.post<{url}>('.../checkout')` → `window.location.href = url`. Creator sees
     fee line "Gummfit fee {fmtCents(fee_cents)}" on paid rows. `?paid=1` in URL → green
     toast strip "Payment received — it can take a few seconds to reflect" + refetch after
     3s.
- **Chat panel** (bottom, full-width): messages list (sender-side alignment), composer
  POST `/messages`, disabled with "Conversation closed" note in terminal statuses.
  Counter-linked messages get a "proposed new terms" tag linking the accordion open.

### `BrandCollabs.tsx` — authed `/cappe/collabs` (business only)
- Tabs: Offers | Campaigns.
- Offers tab: status filter chips (all/sent/negotiating/accepted/active/completed/closed),
  fetch `GET /collab/offers?side=brand&status=...`; table rows → creator avatar+handle,
  title, campaign, total, schedule, status badge, last_action_at relative — row click →
  `/cappe/collabs/{id}`. Empty state: "Find creators to work with" → `/cappe/creators`.
- Campaigns tab: card list + create/edit inline form (`CampaignUpsert` fields), archive
  action, offer_count shown.
- Guard: if `account.account_type !== 'business'` render nothing (route also gated by
  sidebar visibility).

### `CreatorHome.tsx` — authed `/cappe/creator` (profile editor)
- Fetch `GET /creators/me`; 404 → **claim form** (handle + display_name, live
  availability hint on 409, POST then reload).
- **Status banner** (top, full width): draft → zinc "Your profile is a draft — submit it
  for review to get listed" + Submit button; pending_review → amber "In review — we'll
  email you"; rejected → red card with `review_note` + "Edit and resubmit" (Submit button
  again); published → emerald "Live on Gummfit" + link `/cappe/creators/{handle}` +
  `open_to_offers` toggle (PATCH); suspended → red + note.
- Sections (each `ui.card`, own Save button, PATCH/PUT on save):
  1. Basics: avatar + cover upload (`cappeApi.upload('/creators/me/upload', fd)` → URL →
     PATCH), display_name, bio textarea, location, niches multi-chip picker
     (CREATOR_NICHES, max 6), languages chips.
  2. Socials: editable rows {platform select, handle, url, follower_count, engagement %},
     PUT replace-all. Audited rows show ✓ verified/⚑ flagged badge + "editing resets
     verification" warning line.
  3. Portfolio: card grid, add/edit modal {title, description, media upload OR external
     URL, brand_name, sort}, PUT replace-all.
  4. Rates: table editor {type, platform, price $, negotiable, notes}, PUT replace-all.
  5. **Payouts**: `<StripeConnectCard />` verbatim reuse + caption "Brands can only pay
     you after Stripe payouts are enabled."

### `CreatorDeals.tsx` — authed `/cappe/creator/deals`
Same table shape as BrandCollabs offers tab with `side=creator`; columns swap counterpart
→ brand_name. Status chips include declined. Row → `/cappe/creator/deals/{id}`.

### `CreatorEarnings.tsx` — authed `/cappe/creator/earnings`
`GET /creators/me/earnings`. Summary tiles: Paid out (`sum paid amount - fee`), Upcoming
(`due+scheduled+processing sum`). Table: offer title, brand, label, amount, fee, status
badge, paid_at.

## 7.4 Routing — edit `client/src/cappe/routes.tsx`

Eager import `CreatorsLanding`; lazy the rest:

```tsx
const CreatorDirectory = lazy(() => import('./creators/CreatorDirectory'))
const CreatorPublicProfile = lazy(() => import('./creators/CreatorPublicProfile'))
const CreatorHome = lazy(() => import('./creators/CreatorHome'))
const CreatorDeals = lazy(() => import('./creators/CreatorDeals'))
const CreatorEarnings = lazy(() => import('./creators/CreatorEarnings'))
const BrandCollabs = lazy(() => import('./creators/BrandCollabs'))
const OfferDetailPage = lazy(() => import('./creators/OfferDetailPage'))
import CreatorsLanding from './creators/CreatorsLanding'
```

Public block (next to `discover`):

```tsx
<Route path="for-creators" element={<CreatorsLanding />} />
<Route path="creators" element={<CreatorDirectory />} />
<Route path="creators/:handle" element={<CreatorPublicProfile />} />
```

Authed block (inside `<Route element={<CappeLayout />}>`):

```tsx
<Route path="creator" element={<CreatorHome />} />
<Route path="creator/deals" element={<CreatorDeals />} />
<Route path="creator/deals/:offerId" element={<OfferDetailPage />} />
<Route path="creator/earnings" element={<CreatorEarnings />} />
<Route path="collabs" element={<BrandCollabs />} />
<Route path="collabs/:offerId" element={<OfferDetailPage />} />
```

## 7.5 Sidebar — edit `client/src/cappe/components/CappeSidebar.tsx`

In the `!siteId` branch, dispatch on `account?.account_type`:

```tsx
) : account?.account_type === 'creator' ? (
  <>
    <Item to="/cappe/creator" icon={UserCircle} label="My Profile" end />
    <Item to="/cappe/creator/deals" icon={Handshake} label="Deals" />
    <Item to="/cappe/creator/earnings" icon={Wallet} label="Earnings" />
    <Item to="/cappe/creators" icon={Compass} label="Directory" />
  </>
) : (
  <>
    <Item to="/cappe/sites" icon={LayoutGrid} label="My Sites" end />
    <Item to="/cappe/templates" icon={LayoutTemplate} label="Templates" />
    {account?.account_type === 'business' && (
      <>
        <div className="mt-3 px-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-600">Creators</div>
        <Item to="/cappe/creators" icon={Compass} label="Find creators" />
        <Item to="/cappe/collabs" icon={Handshake} label="Collabs" />
      </>
    )}
  </>
)}
```

Also: when `siteId` is set the site nav renders as today (unchanged). Import
`Handshake, Wallet, Compass` from lucide. Creator accounts never see My Sites (they can
still visit /cappe/sites by URL — harmless).

`CappeLayout` — check its post-auth redirect (if it bounces authed users to `/cappe/sites`
anywhere, creator accounts must go to `/cappe/creator` instead; grep
`navigate('/cappe/sites')` across `CappeLogin.tsx`, `CappeVerify.tsx`, `CappeSignup.tsx`,
`CappeLayout.tsx` and replace each with:

```ts
const postAuthHome = (t?: string) => (t === 'creator' ? '/cappe/creator' : '/cappe/sites')
```

using the account_type from the auth response / refreshed `useCappeMe`).

## 7.6 Signup — edit `client/src/cappe/pages/CappeSignup.tsx`

- Extend the options array with
  `{ value: 'creator', icon: Sparkles, title: 'A creator', blurb: 'Influencer or content creator — get discovered, get brand deals, get paid.' }`
  (import `Sparkles`).
- `CappeAccountType` union already extended in types.ts (7.1).
- Preselect from query: `const [params] = useSearchParams()` →
  `useState<CappeAccountType>(params.get('type') === 'creator' ? 'creator' : 'business')`.
- Post-signup/verify navigation → `postAuthHome(accountType)`.

Backend `models/auth.py`: `CappeSignup.account_type: Literal["business", "personal", "creator"]`
(edit the existing Literal + its comment). No other auth change — signup INSERT already
passes `body.account_type` through.

---

# PART 8 — Matcha admin UI

## File: `client/src/pages/admin/CappeCreators.tsx` (new; matcha stack — `api` from `../../api/client`, matcha ui components)

Structure mirrors `pages/admin/Cappe.tsx` (self-contained types + fetch on mount).
Tabs (local state): **Review queue** · **All creators** · **Re-audit due** · **Settings** · **Collabs**.

- Data: `api.get('/admin/cappe/creators')` once; client-side partition:
  queue = `status==='pending_review'`; re-audit = `reaudit_due`; all = everything.
- **Review queue tab**: table (handle, name, email, submitted_at, socials count, niches).
  Row expand → full preview (bio, socials with links + self-reported counts, portfolio
  links) + **Approve** button (`api.post('/admin/cappe/creators/{id}/approve')`) +
  **Reject** (textarea note required → `/reject`). Optimistic row removal on success.
- **All creators tab**: status filter select; per-row actions Suspend (note prompt) /
  Restore; **Audit** button per social → drawer/inline editor: shows platform, handle,
  url (external link), self-reported count; inputs: audit_status select
  (verified/flagged/unverified), verified_follower_count number (required when verified —
  disable Save otherwise), note. Save →
  `api.post('/admin/cappe/creators/socials/{sid}/audit', body)` → refetch row.
  Profile-level `reach_verified` chip rendered from response.
- **Re-audit due tab**: same table filtered, sorted by `reach_audited_at` asc.
- **Settings tab**: two number inputs — Collab fee (rendered as %, stored bps:
  input `value = bps/100`, step 0.25, save `bps = round(x*100)`; range 0–50%) and Minimum
  offer ($, cents conversion). Load `GET /admin/cappe/marketplace-settings`, save `PATCH`.
  Caption: "Fee applies to new checkout sessions immediately; paid installments keep their
  snapshotted fee."
- **Collabs tab**: `GET /admin/cappe/collab-overview` → status count/total table + GMV +
  fees-collected stat tiles.

## Wiring

- `client/src/routes/AdminRoutes.tsx`: `import CappeCreators from '../pages/admin/CappeCreators'`
  + `<Route path="cappe-creators" element={<CappeCreators />} />` next to the existing
  `cappe` route (line ~68).
- `client/src/components/sidebars/AdminSidebar.tsx`: after the existing Cappe entry
  (line 22): `{ to: '/admin/cappe-creators', icon: Users, label: 'Cappe Creators' }`
  (icon already imported there or add).

---

# PART 9 — State machine reference (server-enforced truth)

```
                       brand sends (rev 1)
                              │
                            sent ──either counters (rev n+1)──▶ negotiating ◀─┐
                              │                                     │         │ counter
                              │                                     └─────────┘
   accept: allowed only for the side that did NOT propose the latest revision
                              │
                          accepted ── first installment paid (webhook) ──▶ active
                              │            (gifting/zero-comp offers skip straight to active)
                              │
   active ── all deliverables approved AND all payments paid/cancelled ──▶ completed
```

Terminal: `declined` (creator, pre-accept, optional reason) · `withdrawn` (brand,
pre-accept) · `cancelled` (either, post-accept, reason required; unpaid installments →
`cancelled`, paid ones stay `paid`).

Deliverable: `pending → submitted → approved` | `submitted → revision_requested →
submitted` (bounded by `terms.revision_rounds`, counted in `revision_count`).

Payment: `scheduled → due → processing → paid`; `cancelled` on offer cancel; `failed`
reserved (checkout abandon just stays processing/re-mints); `refunded` reserved for
manual admin action.

Fee: resolved at **checkout time** from `cappe_marketplace_settings.collab_fee_bps`
(fallback `settings.cappe_platform_fee_bps`), snapshotted to
`fee_bps_snapshot`/`fee_cents` on the payment row, passed as `application_fee_cents` to
the direct charge on the creator's connected account. Admin edits affect only future
checkouts.

---

# PART 10 — Deferred (v2 — do NOT build now)

- Open campaign board / creator applications (brands initiate only).
- OAuth social verification (Instagram Graph / TikTok / YouTube APIs) — manual audit v1.
- Saved-card off-session auto-charge, net-30 schedule (`charge_off_session` exists when wanted).
- Auto-refund / clawback on cancellation; disputes.
- Mutual post-collab reviews (`cappe_reviews` is site-scoped — needs own design).
- Unread badges on deals inbox; realtime/websocket anything (email + refetch v1).
- Re-review of published profiles on edit (only social edits reset audit state v1).
- Pretty share cards / OG tags for public profiles (SPA — needs renderer work).

# PART 11 — Build order + verification

1. **Migration + models** (Parts 1–2). Verify: `alembic` rehearsal against dev
   (`MIGRATE_REHEARSAL=1`), then `./scripts/migrate-dev.sh`. Commit migration first.
2. **Service** (`services/collab.py`) — pure logic; py_compile via post-edit hook.
3. **Creator self-service + public directory routes** (4.1, 4.2) + mount. Manual smoke:
   signup creator (RFC 2606 email), claim handle, PUT socials/portfolio/rates, submit.
4. **Admin backend** (Part 6) + mount — approve the test profile; audit a social; confirm
   `reach_verified` recompute + directory shows it.
5. **Collab routes + webhook branch** (4.3, 4.4) + emails (Part 5).
6. **Frontend** in order: types/badges (7.1–7.2) → signup + sidebar + routes (7.4–7.6) →
   CreatorHome → Directory/PublicProfile → SendOfferSheet/TermSheet → OfferDetailPage →
   BrandCollabs/Deals/Earnings. Typecheck after each page:
   `cd client && npx tsc -p tsconfig.app.json --noEmit` (NOT bare `tsc --noEmit`).
7. **Admin UI** (Part 8).
8. **End-to-end in Stripe test mode** (dev): business account + creator account
  (`@example.com` emails) → submit → admin approve + audit → brand sends per-deliverable
  offer (2 deliverables) → creator counters (price up) → brand accepts → creator connects
  Stripe (test) → brand pays installment 1 (4242 card) → webhook flips paid + offer
  active → creator submits deliverable 1 → brand requests revision → resubmit → approve →
  payment 2 due → pay → approve deliverable 2 → completed. Check `fee_cents` matches the
  admin-set bps and shows in Earnings.
9. Prod: `./scripts/migrate-prod.sh` at ship time, normal deploy after.

No feature flag: the marketplace is structurally gated by `account_type` + profile review
(nothing to hide behind a flag; Cappe has no feature-flag system by design).
