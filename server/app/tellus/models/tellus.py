"""Pydantic request/response shapes for Tell-Us."""
from datetime import datetime
from typing import Annotated, Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

AccountType = Literal["consumer", "brand"]
ConsumerTier = Literal["free", "paid"]
ReportCategory = Literal["service", "cleanliness", "facilities", "safety", "compliment", "other"]
Sentiment = Literal["positive", "neutral", "negative"]
ReportStatus = Literal["new", "reviewing", "resolved", "archived"]
MediaType = Literal["photo", "video"]
RedemptionType = Literal["code", "qr", "manual"]
RedemptionStatus = Literal["pending", "issued", "redeemed", "expired", "cancelled"]
# Effective review state — 'published' is derived at read time (held +
# publish_at <= NOW()) and never stored; see tellus_app_05.
ReviewState = Literal["held", "published", "withdrawn"]
DmSenderRole = Literal["brand", "consumer"]
DmKind = Literal["feedback", "general"]
DmTopic = Literal["hours", "availability", "inventory", "order", "service", "accessibility", "other"]
DmStatus = Literal["waiting_brand", "waiting_consumer", "closed"]
BoardPostKind = Literal["update", "deal", "event", "question"]
BoardReplyStatus = Literal["held", "approved", "rejected", "removed"]
BoardModerationStatus = Literal["visible", "flagged", "removed"]
BoardMembershipStatus = Literal["pending", "approved", "declined", "removed", "left", "cancelled"]
ListingVisibility = Literal["public", "board"]


# ── Auth ────────────────────────────────────────────────────────────────────

class TellusSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: Optional[str] = Field(default=None, max_length=255)
    account_type: AccountType = "consumer"
    # Brand-only: name of the brand to create on signup + how many stores it
    # bills for (tellus_brands.location_count — paid per-location, see
    # routes/billing.py). Not used for consumer signups.
    brand_name: Optional[str] = Field(default=None, max_length=255)
    location_count: Optional[int] = Field(default=None, ge=1, le=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _require_brand_fields(self) -> "TellusSignup":
        if self.account_type == "brand":
            if not self.brand_name or not self.brand_name.strip():
                raise ValueError("brand_name is required for brand signups")
            if self.location_count is None:
                raise ValueError("location_count is required for brand signups")
        return self


class TellusLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class TellusRefreshRequest(BaseModel):
    refresh_token: str


class TellusVerifyRequest(BaseModel):
    token: str


class TellusResendRequest(BaseModel):
    email: EmailStr


class TellusGoogleAuth(BaseModel):
    id_token: str = Field(min_length=16, max_length=8192)


class TellusAccount(BaseModel):
    """The authenticated Tell-Us identity (returned by require_tellus_account)."""
    id: UUID
    email: str
    display_name: Optional[str] = None
    account_type: str = "consumer"
    status: str = "active"
    city: Optional[str] = None
    state: Optional[str] = None
    leaderboard_opt_in: bool = True
    consumer_tier: ConsumerTier = "free"
    consumer_tier_expires_at: Optional[datetime] = None
    # Populated for brand accounts (the brand they own).
    brand_id: Optional[UUID] = None
    # Brand billing state — null for consumer accounts.
    plan_status: Optional[str] = None
    location_count: Optional[int] = None
    # Public review-page slug (brand accounts only) — /tellus/b/{brand_slug}.
    brand_slug: Optional[str] = None
    # True when the account email is in TELLUS_ADMIN_EMAILS — internal changelog access.
    is_admin: bool = False


class TellusTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    account: TellusAccount


class TellusSignupResponse(BaseModel):
    verification_required: bool
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    account: Optional[TellusAccount] = None


class TellusLocationUpdate(BaseModel):
    """Consumer sets/updates their city — geocoded to power the marketplace."""
    city: str = Field(min_length=1, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=255)
    leaderboard_opt_in: Optional[bool] = None


# ── Brands & stores ───────────────────────────────────────────────────────────

class TellusBrand(BaseModel):
    id: UUID
    owner_account_id: Optional[UUID] = None
    name: str
    logo_url: Optional[str] = None
    # auto = useful feedback credits points immediately; manual = the brand
    # approves/rejects each submission before points credit.
    reward_mode: Literal["auto", "manual"] = "auto"
    created_at: datetime
    messaging_enabled: bool = False


class TellusBrandUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    # logo_url is intentionally NOT settable here — POST /brand/logo (multipart
    # upload to S3) is the only writer, closing the arbitrary-URL-that-doesn't-
    # render bug the old free-text field had.
    reward_mode: Optional[Literal["auto", "manual"]] = None


class TellusBrandPrompt(BaseModel):
    id: UUID
    prompt: str
    position: int = 0


class TellusPromptItem(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class TellusBrandPromptsUpdate(BaseModel):
    prompts: list[TellusPromptItem] = Field(default_factory=list, max_length=5)


class TellusPlaceSearchResult(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    claimed: bool
    intake_token: Optional[str] = None   # only ever set for unclaimed places
    review_count: int = 0
    google_place_id: Optional[str] = None   # lets the client dedupe vs live Google suggestions
    messaging_enabled: bool = False
    followed: bool = False


class TellusFollowedBrand(BaseModel):
    slug: str
    name: str
    logo_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    messaging_enabled: bool = False


class TellusPlaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Optional when google_place_id is set (Place Details supplies it); the
    # route 422s if neither source yields a city.
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    # When set, the server re-resolves name/city/state/address/lat/lng from
    # Google Place Details — the submitted name/city above are only the
    # fallback if that lookup fails, never trusted directly for a place_id
    # submission (a squatter could pair a real place_id with a fake name).
    google_place_id: Optional[str] = Field(default=None, max_length=300)
    # Places API (New) session token — pairs the autocomplete keystrokes with
    # this Details lookup for session-based billing instead of per-call.
    session_token: Optional[str] = Field(default=None, max_length=64)
    website: Optional[str] = None  # honeypot


class TellusPlaceCreateResponse(BaseModel):
    slug: str
    name: str
    claimed: bool = False
    intake_token: Optional[str] = None
    existing: bool = False


class TellusPlaceAutocompleteResult(BaseModel):
    place_id: str
    name: str
    secondary_text: Optional[str] = None   # e.g. "123 Main St, Springfield, IL"


class TellusStoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusStoreUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    zipcode: Optional[str] = Field(default=None, max_length=20)


class TellusStore(BaseModel):
    id: UUID
    brand_id: UUID
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    created_at: datetime


# ── Links (QR) ────────────────────────────────────────────────────────────────

class TellusLinkCreate(BaseModel):
    store_id: Optional[UUID] = None
    label: Optional[str] = Field(default=None, max_length=200)
    max_uses: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None


class TellusLink(BaseModel):
    id: UUID
    brand_id: UUID
    store_id: Optional[UUID] = None
    token: str
    label: Optional[str] = None
    is_active: bool = True
    use_count: int = 0
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    store_name: Optional[str] = None


# ── Public intake ─────────────────────────────────────────────────────────────

class TellusIntakePrompt(BaseModel):
    id: UUID
    prompt: str


class TellusSubmittedAnswer(BaseModel):
    prompt_id: UUID
    answer: str = Field(min_length=1, max_length=2000)


class TellusReportAnswer(BaseModel):
    id: UUID
    prompt_text: str
    answer: str
    position: int = 0


class TellusIntakeConfig(BaseModel):
    """What the public feedback form needs to render (resolved from token)."""
    brand_name: str
    brand_logo_url: Optional[str] = None
    store_name: Optional[str] = None
    categories: list[str] = Field(default_factory=lambda: list(ReportCategory.__args__))
    prompts: list[TellusIntakePrompt] = Field(default_factory=list)
    # False for a consumer-added (unclaimed) place — lets the intake form allow
    # anonymous public reviews there (create_report / public_intake mirror this).
    claimed: bool = True


class TellusFeedbackSubmit(BaseModel):
    category: ReportCategory = "other"
    sentiment: Sentiment = "neutral"
    title: Optional[str] = Field(default=None, max_length=255)
    description: str = Field(min_length=1, max_length=8000)
    occurred_at: Optional[datetime] = None
    reporter_contact: Optional[str] = Field(default=None, max_length=320)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    # Default OFF — older clients that don't send this field would otherwise
    # hit the rating-required 422 in public_intake.py when submitting a
    # rating-less report. Anonymous submissions are forced private regardless.
    post_as_review: bool = False
    # Presigned media keys (storage paths returned by /media/presign).
    media_keys: list["TellusSubmittedMedia"] = Field(default_factory=list, max_length=10)
    answers: list[TellusSubmittedAnswer] = Field(default_factory=list, max_length=20)
    # Honeypot — bots fill hidden fields; humans leave them empty.
    website: Optional[str] = None


class TellusSubmittedMedia(BaseModel):
    storage_path: str = Field(max_length=1000)
    media_type: MediaType
    mime_type: Optional[str] = Field(default=None, max_length=120)
    file_size: Optional[int] = Field(default=None, ge=0)
    original_filename: Optional[str] = Field(default=None, max_length=400)


class TellusMediaPresignRequest(BaseModel):
    media_type: MediaType
    mime_type: str = Field(max_length=120)
    file_size: int = Field(ge=1)
    original_filename: Optional[str] = Field(default=None, max_length=400)


class TellusMediaPresignResponse(BaseModel):
    upload_url: str
    storage_path: str
    expires_in: int


class TellusFeedbackSubmitResponse(BaseModel):
    report_id: UUID
    report_number: Optional[str] = None
    points_awarded: int = 0
    # True when a logged-in consumer earned points; False for anonymous.
    earned: bool = False
    # True when the brand reviews manually — points credit on their approval.
    reward_pending: bool = False
    # True when the submission became a public review (anonymous is never
    # public regardless of the requested post_as_review flag).
    public_review: bool = False
    publish_at: Optional[datetime] = None


# ── Reports (brand dashboard) ──────────────────────────────────────────────────

class TellusReportMedia(BaseModel):
    id: UUID
    media_type: str
    mime_type: Optional[str] = None
    original_filename: Optional[str] = None
    # Presigned download/playback URL, minted at read time (never stored).
    url: Optional[str] = None


class TellusReport(BaseModel):
    id: UUID
    brand_id: UUID
    store_id: Optional[UUID] = None
    store_name: Optional[str] = None
    report_number: Optional[str] = None
    category: str
    sentiment: str
    title: Optional[str] = None
    description: Optional[str] = None
    occurred_at: Optional[datetime] = None
    reporter_contact: Optional[str] = None
    usefulness_score: int = 0
    status: str
    ai_summary: Optional[str] = None
    ai_category: Optional[str] = None
    ai_sentiment: Optional[str] = None
    moderation_status: str = "visible"
    # NULL = anonymous (nothing to credit); pending/approved/rejected otherwise.
    reward_status: Optional[str] = None
    points_awarded: int = 0
    created_at: datetime
    media: list[TellusReportMedia] = Field(default_factory=list)
    rating: Optional[int] = None
    # NULL = private feedback, never a review. 'published' is derived, not stored.
    review_state: Optional[ReviewState] = None
    # Set only when a brand used publish-now to waive the remainder of the 48h hold.
    published_early_at: Optional[datetime] = None
    publish_at: Optional[datetime] = None
    hearted_at: Optional[datetime] = None
    brand_public_reply: Optional[str] = None
    brand_public_reply_at: Optional[datetime] = None
    # Derived (reporter_account_id IS NOT NULL) — lets the brand UI show/hide
    # "Message reviewer" without ever exposing the reporter's identity here.
    is_identified: bool = False
    has_dm_thread: bool = False
    answers: list[TellusReportAnswer] = Field(default_factory=list)
    # Consumer likes (tellus_likes) — distinct from hearted_at above, which is
    # the brand's own one-bit acknowledgment. No liked_by_me here: this is the
    # brand-dashboard model and brands can't like, so pairing it with
    # hearted_at would invite exactly the confusion this field must avoid.
    like_count: int = 0


class TellusReportStatusUpdate(BaseModel):
    status: ReportStatus


class TellusRewardDecision(BaseModel):
    """Brand approves (points credit) or rejects a pending reward."""
    approve: bool


class TellusReportModerate(BaseModel):
    moderation_status: Literal["visible", "flagged", "removed"]


class TellusFeedbackStats(BaseModel):
    total: int = 0
    new: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)


# ── Rewards economy ────────────────────────────────────────────────────────────

class TellusPointsBalance(BaseModel):
    account_id: UUID
    points_balance: int = 0
    lifetime_points: int = 0
    level: int = 1
    current_streak: int = 0
    longest_streak: int = 0
    last_activity_date: Optional[Any] = None
    # Derived level progress for the UI.
    points_to_next_level: int = 0
    level_floor: int = 0
    level_ceiling: int = 0


class TellusLedgerEntry(BaseModel):
    id: UUID
    delta: int
    balance_after: int
    reason: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


class TellusRedeemRequest(BaseModel):
    listing_id: UUID


# ── Marketplace ────────────────────────────────────────────────────────────────

class TellusListingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    points_cost: int = Field(ge=0)
    quantity_total: Optional[int] = Field(default=None, ge=1)
    redemption_type: RedemptionType = "code"
    terms: Optional[str] = Field(default=None, max_length=4000)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: bool = True
    expiry_days: int = Field(default=30, ge=1, le=365)
    visibility: ListingVisibility = "public"


class TellusListingUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    points_cost: Optional[int] = Field(default=None, ge=0)
    quantity_total: Optional[int] = Field(default=None, ge=0)
    redemption_type: Optional[RedemptionType] = None
    terms: Optional[str] = Field(default=None, max_length=4000)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=60)
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: Optional[bool] = None
    expiry_days: Optional[int] = Field(default=None, ge=1, le=365)
    visibility: Optional[ListingVisibility] = None


class TellusListing(BaseModel):
    id: UUID
    brand_id: Optional[UUID] = None
    brand_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    points_cost: int
    quantity_total: Optional[int] = None
    quantity_claimed: int = 0
    quantity_remaining: Optional[int] = None
    redemption_type: str = "code"
    terms: Optional[str] = None
    active_from: Optional[datetime] = None
    active_to: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    expiry_days: int = 30   # days a redeemed code stays valid (ck 1..365)
    visibility: ListingVisibility = "public"
    like_count: int = 0
    liked_by_me: bool = False


class TellusRedemption(BaseModel):
    id: UUID
    account_id: UUID
    listing_id: UUID
    listing_title: Optional[str] = None
    brand_name: Optional[str] = None      # NULL for platform-curated listings
    listing_city: Optional[str] = None
    listing_state: Optional[str] = None
    points_spent: int
    status: str
    code: Optional[str] = None
    issued_at: Optional[datetime] = None
    redeemed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


class TellusRedemptionStatusUpdate(BaseModel):
    status: Literal["redeemed", "cancelled", "expired"]


# ── Gamification ───────────────────────────────────────────────────────────────

class TellusBadge(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    earned: bool = False
    awarded_at: Optional[datetime] = None


class TellusLeaderboardEntry(BaseModel):
    rank: int
    account_id: UUID
    display_name: str
    lifetime_points: int
    level: int
    is_you: bool = False


# ── Likes ──────────────────────────────────────────────────────────────────────

class TellusLikeState(BaseModel):
    """Response for POST/DELETE /likes/{target_type}/{target_id} — authoritative
    post-write state so a client can reconcile an optimistic toggle without a refetch."""
    like_count: int = 0
    liked_by_me: bool = False


# ── Grants ─────────────────────────────────────────────────────────────────────

class TellusGrantRequest(BaseModel):
    """Brand awards bonus points to a consumer for useful feedback."""
    report_id: UUID
    points: int = Field(ge=1, le=5000)
    description: Optional[str] = Field(default=None, max_length=500)


# ── Reviews (consumer "My Reviews" + brand public reply) ──────────────────────

class TellusBrandReplyUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class TellusMyReview(BaseModel):
    id: UUID
    brand_name: str
    brand_slug: str
    store_name: Optional[str] = None
    rating: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    review_state: ReviewState
    publish_at: datetime
    created_at: datetime
    points_awarded: int = 0
    hearted: bool = False
    brand_public_reply: Optional[str] = None
    brand_public_reply_at: Optional[datetime] = None
    dm_thread_id: Optional[UUID] = None
    media: list[TellusReportMedia] = Field(default_factory=list)
    answers: list[TellusReportAnswer] = Field(default_factory=list)
    like_count: int = 0
    liked_by_me: bool = False


class TellusMyReviewUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, min_length=1, max_length=8000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


# ── Public brand community page ────────────────────────────────────────────────

class TellusPublicReview(BaseModel):
    id: UUID
    rating: int
    title: Optional[str] = None
    description: Optional[str] = None
    # The ONLY identity field ever exposed publicly.
    reviewer_name: str
    store_name: Optional[str] = None
    created_at: datetime
    publish_at: datetime
    hearted: bool = False
    brand_reply: Optional[str] = None
    brand_reply_at: Optional[datetime] = None
    media: list[TellusReportMedia] = Field(default_factory=list)
    answers: list[TellusReportAnswer] = Field(default_factory=list)
    like_count: int = 0
    liked_by_me: bool = False


class TellusPublicBrandPage(BaseModel):
    brand_name: str
    slug: str
    logo_url: Optional[str] = None
    review_count: int = 0
    avg_rating: Optional[float] = None
    reviews: list[TellusPublicReview] = Field(default_factory=list)
    total: int = 0
    claimed: bool = True
    intake_token: Optional[str] = None
    address: Optional[str] = None   # primary store (first by created_at)
    city: Optional[str] = None
    state: Optional[str] = None
    # Published reviews older than the 12-month rating window — the UI renders
    # a "Show older reviews" toggle from this; they never count toward avg_rating.
    older_count: int = 0
    has_board: bool = False
    messaging_enabled: bool = False
    stores: list["TellusMessagingStore"] = Field(default_factory=list)


class TellusClaimResponse(BaseModel):
    """Response for POST /b/{slug}/claim — files a PENDING claim only, no
    ownership flip. status is always 'pending' here; the account is unchanged
    until an admin approves via routes/admin/claims.py."""
    ok: bool = True
    claim_id: UUID
    status: str = "pending"
    slug: str


class TellusMyClaim(BaseModel):
    id: UUID
    brand_id: UUID
    brand_slug: str
    brand_name: str
    status: str
    created_at: datetime
    decision_note: Optional[str] = None


class TellusAdminClaim(TellusMyClaim):
    account_id: UUID
    account_email: str
    account_display_name: Optional[str] = None
    claimant_ip: Optional[str] = None
    note: Optional[str] = None


class TellusClaimDecision(BaseModel):
    decision_note: Optional[str] = Field(default=None, max_length=1000)


# ── DMs (brand <-> reviewer) ────────────────────────────────────────────────────

class TellusMessagingStore(BaseModel):
    id: UUID
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None

class TellusDmSend(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: Optional[UUID] = None


class TellusCommsStart(BaseModel):
    store_id: Optional[UUID] = None
    topic: DmTopic = "other"
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID


class TellusDmAssign(BaseModel):
    member_id: Optional[UUID] = None


class TellusInboxToggle(BaseModel):
    enabled: bool


class TellusDmMessage(BaseModel):
    id: UUID
    thread_id: UUID
    sender_role: DmSenderRole
    body: str
    created_at: datetime
    is_mine: bool = False


class TellusDmThread(BaseModel):
    id: UUID
    report_id: Optional[UUID] = None
    # Brand view: reviewer's display_name (or 'Reviewer') — never email.
    # Consumer view: the brand's name.
    counterparty_name: str
    report_title: Optional[str] = None
    report_number: Optional[str] = None
    # Underlying report's derived review state — None = private feedback.
    # Brand side renders "publishes in Nh" urgency off these two.
    review_state: Optional[ReviewState] = None
    publish_at: Optional[datetime] = None
    blocked: bool = False
    unread_count: int = 0
    last_message_at: datetime
    created_at: datetime
    kind: DmKind = "feedback"
    topic: Optional[DmTopic] = None
    status: DmStatus = "waiting_consumer"
    store_id: Optional[UUID] = None
    store_name: Optional[str] = None
    store_city: Optional[str] = None
    assigned_member_id: Optional[UUID] = None
    assigned_member_name: Optional[str] = None
    viewer_role: DmSenderRole = "consumer"
    first_brand_response_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


# ── Notifications ──────────────────────────────────────────────────────────────

class TellusNotification(BaseModel):
    id: UUID
    kind: str
    title: str
    body: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime


# ── Regulars board ────────────────────────────────────────────────────────────

class TellusBoardUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_active: Optional[bool] = None


class TellusBoardJoin(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class TellusBoardPostCreate(BaseModel):
    kind: BoardPostKind = "update"
    title: str = Field(min_length=1, max_length=255)
    body: Optional[str] = Field(default=None, max_length=8000)
    listing_id: Optional[UUID] = None
    event_starts_at: Optional[datetime] = None
    event_ends_at: Optional[datetime] = None
    is_pinned: bool = False

    @model_validator(mode="after")
    def _deal_needs_listing(self):
        if self.kind == "deal" and self.listing_id is None:
            raise ValueError("A deal post needs a listing_id")
        return self


class TellusBoardPostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    body: Optional[str] = Field(default=None, max_length=8000)
    is_pinned: Optional[bool] = None
    event_starts_at: Optional[datetime] = None
    event_ends_at: Optional[datetime] = None


class TellusBoardReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TellusBoardReply(BaseModel):
    id: UUID
    post_id: UUID
    author_name: str                       # display_name fallback 'Tell-Us member'
    is_mine: bool = False
    status: BoardReplyStatus               # author sees own held/rejected; members only ever get 'approved'
    body: str
    created_at: datetime
    like_count: int = 0
    liked_by_me: bool = False


class TellusBoardPost(BaseModel):
    id: UUID
    kind: BoardPostKind
    title: str
    body: Optional[str] = None
    listing: Optional[TellusListing] = None     # embedded for kind='deal'
    event_starts_at: Optional[datetime] = None
    event_ends_at: Optional[datetime] = None
    is_pinned: bool = False
    moderation_status: str = "visible"          # mods see flagged; members only get visible
    approved_reply_count: int = 0
    held_reply_count: Optional[int] = None      # mods only, else None
    created_at: datetime
    like_count: int = 0
    liked_by_me: bool = False


class TellusBoardPage(BaseModel):               # GET /boards/{slug}
    board_id: UUID
    brand_id: UUID
    brand_name: str
    brand_slug: str
    logo_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    plan_paused: bool                           # plan lapsed → composer disabled client-side
    viewer_role: Literal["member", "moderator", "owner", "admin", "location_manager", "staff"]
    can_manage_board: bool = False
    posts: list[TellusBoardPost]
    total: int


class TellusBoardMembership(BaseModel):         # consumer's own view
    id: UUID
    brand_id: UUID
    brand_name: str
    brand_slug: str
    logo_url: Optional[str] = None
    status: BoardMembershipStatus
    requested_at: datetime
    decided_at: Optional[datetime] = None


class TellusBoardJoinRequest(BaseModel):        # brand queue view
    id: UUID
    account_display_name: str
    note: Optional[str] = None
    requested_at: datetime
    review_count: int = 0                       # loyalty signals — identified activity only
    hearted: bool = False
    redemption_count: int = 0


class TellusBoardManageReplyRow(BaseModel):     # GET /board/manage/replies
    id: UUID
    post_id: UUID
    post_title: str
    author_name: str
    body: str
    status: BoardReplyStatus
    created_at: datetime


class TellusBoardMemberEntry(BaseModel):
    id: UUID                                    # membership id
    account_display_name: str
    joined_at: datetime


class TellusBrandTeamMember(BaseModel):
    id: UUID                                    # member row id
    account_display_name: str
    email: str                                  # team page is brand-internal; email OK here
    role: Literal["owner", "moderator", "admin", "location_manager", "staff"]
    created_at: datetime
    can_manage_inbox: bool = False


class TellusTeamMemberAdd(BaseModel):
    email: EmailStr


class TellusBoardManageSummary(BaseModel):
    board_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    pending_requests: int
    held_replies: int
    member_count: int
    viewer_role: Literal["owner", "moderator", "admin", "location_manager", "staff"]


class TellusModeratedBrand(BaseModel):           # GET /me/moderated-brands
    brand_id: UUID
    name: str
    slug: str
    role: Literal["owner", "moderator", "admin", "location_manager", "staff"]


TellusFeedbackSubmit.model_rebuild()
