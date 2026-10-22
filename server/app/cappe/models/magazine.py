"""Pydantic shapes — a site's magazine (cappemag02) and story previews."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

MastheadStyle = Literal["classic", "literary", "modern", "elegant", "display"]


class CappeMagazine(BaseModel):
    """A site's magazine. `live` is whether its pages render now: turned on
    AND the owner's plan includes magazines."""
    site_id: UUID
    enabled: bool = False
    name: str
    tagline: Optional[str] = None
    about: Optional[str] = None
    masthead_style: MastheadStyle = "classic"
    accent: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    front_at_root: bool = False
    nav_label: str = "Magazine"
    cover_post_id: Optional[UUID] = None
    follow_enabled: bool = True
    paid_enabled: bool = False
    price_cents: Optional[int] = None
    paid_pitch: Optional[str] = None
    preview_blocks: int = 3
    lapsed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    live: bool = False
    plan_includes_magazine: bool = False
    # Paid subscriptions: whether the plan allows them, whether Stripe can take
    # the money yet, and Gummfit's share of each payment.
    plan_includes_paid: bool = False
    stripe_ready: bool = False
    currency: str = "USD"
    fee_bps: int = 3000


class CappeMagazineUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    tagline: Optional[str] = Field(default=None, max_length=200)
    about: Optional[str] = Field(default=None, max_length=4000)
    masthead_style: Optional[MastheadStyle] = None
    accent: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    topics: Optional[list[str]] = Field(default=None, max_length=5)
    front_at_root: Optional[bool] = None
    nav_label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    cover_post_id: Optional[UUID] = None
    follow_enabled: Optional[bool] = None
    paid_enabled: Optional[bool] = None
    price_cents: Optional[int] = Field(default=None, ge=100, le=100_000)
    paid_pitch: Optional[str] = Field(default=None, max_length=600)
    preview_blocks: Optional[int] = Field(default=None, ge=1, le=20)


class CappeMagazineCheckout(BaseModel):
    """Where Stripe Checkout returns the reader: the magazine's own pages, or
    their dashboard on gummfit.com when they subscribe from there."""
    success_url: str = Field(min_length=1, max_length=2000)
    cancel_url: str = Field(min_length=1, max_length=2000)


class CappeMagazineCompCreate(BaseModel):
    """A free subscription the writer gives. No `months` is for good, until
    revoked."""
    email: EmailStr
    months: Optional[int] = Field(default=None, ge=1, le=24)
    note: Optional[str] = Field(default=None, max_length=200)


class CappeStoryPreview(BaseModel):
    """An unsaved story to render as its page would look."""
    title: str = Field(default="", max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=600)
    kicker: Optional[str] = Field(default=None, max_length=60)
    topic: Optional[str] = Field(default=None, max_length=40)
    layout: Optional[str] = Field(default=None, max_length=20)
    byline: Optional[str] = Field(default=None, max_length=160)
    cover_asset_id: Optional[UUID] = None
    access: Literal["free", "paid"] = "free"
    content: dict[str, Any] = Field(default_factory=dict)
    # The owner's editor on the page: the story whole, marked for editing,
    # with the editor's script (services/magazine/story_render.py).
    edit: bool = False


class CappeStoryLayoutInfo(BaseModel):
    key: str
    label: str
    content: dict[str, Any]


class CappeStoryOptions(BaseModel):
    """What the story editor offers: layouts with their starter blocks, topics."""
    layouts: list[CappeStoryLayoutInfo]
    topics: list[dict[str, str]]





# ── Open imagery (cappemag03) ───────────────────────────────────────────────
StockSource = Literal["openverse", "smithsonian", "met", "nasa"]


class CappeStockResult(BaseModel):
    """A picture an archive offers. `thumb` is our own signed thumbnail link
    (routes/public/stock.py); `imported` says it's already in the library."""
    source: StockSource
    source_id: str
    title: str = ""
    creator: str = ""
    license: str
    license_version: str = ""
    license_url: str = ""
    provider_label: str = ""
    landing_url: str = ""
    credit_line: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    thumb: str = ""
    imported: bool = False


class CappeStockSearch(BaseModel):
    source: StockSource
    query: str
    page: int
    results: list[CappeStockResult]
    has_more: bool


class CappeStockKey(BaseModel):
    source: StockSource
    source_id: str = Field(min_length=1, max_length=200)


class CappeStockImportRequest(BaseModel):
    items: list[CappeStockKey] = Field(min_length=1, max_length=24)
    post_id: Optional[UUID] = None


class CappeStockTopicRequest(BaseModel):
    topic: str = Field(max_length=40)
    count: int = Field(default=12, ge=1, le=24)
    post_id: Optional[UUID] = None


class CappeStockImport(BaseModel):
    id: UUID
    source: StockSource
    source_id: str
    status: Literal["pending", "working", "ready", "failed", "refused"]
    error: Optional[str] = None
    asset_id: Optional[UUID] = None
    asset: Optional[dict[str, Any]] = None
    created_at: datetime


class CappeStockImports(BaseModel):
    imports: list[CappeStockImport]
    remaining_today: Optional[int] = None



IllustrationAspect = Literal["16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16"]
AssistAction = Literal["draft", "headlines", "captions", "tighten", "search_terms"]


class CappeIllustrateRequest(BaseModel):
    """Describe the picture; it is drawn as a labeled AI illustration."""
    prompt: str = Field(min_length=3, max_length=1000)
    aspect: IllustrationAspect = "3:2"


class CappeStoryAssistRequest(BaseModel):
    """One Assist action. `content`/`title`/`excerpt` are the editor's
    unsaved state (the saved story is used without them); `asset_ids` picks
    the pictures for a draft or captions (else the story's own)."""
    action: AssistAction
    notes: str = Field(default="", max_length=2000)
    block: Optional[int] = Field(default=None, ge=0, le=119)
    asset_ids: list[UUID] = Field(default_factory=list, max_length=8)
    content: Optional[dict[str, Any]] = None
    title: Optional[str] = Field(default=None, max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=600)


class CappeStoryAssist(BaseModel):
    """A proposal; nothing is saved. Which fields are set depends on `action`."""
    action: AssistAction
    headlines: Optional[list[dict[str, str]]] = None
    captions: Optional[list[dict[str, str]]] = None
    md: Optional[str] = None
    block: Optional[int] = None
    terms: Optional[list[dict[str, str]]] = None
    draft: Optional[dict[str, Any]] = None


# A writer's handle is their magazine's address: <handle>.gummfit.com.
HANDLE_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$"


class CappeHandleCheck(BaseModel):
    handle: str
    available: bool
    reason: Optional[str] = None


class CappeMagazineSiteCreate(BaseModel):
    """A writer's magazine: a magazine-only site at <handle>.gummfit.com."""
    name: str = Field(min_length=1, max_length=120)
    handle: str = Field(min_length=3, max_length=30)
    tagline: Optional[str] = Field(default=None, max_length=200)
    topics: list[str] = Field(default_factory=list, max_length=3)
    masthead_style: MastheadStyle = "classic"
    accent: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CappeFollowRequest(BaseModel):
    """A reader following a magazine by email (double opt-in)."""
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)


class CappeIssueCreate(BaseModel):
    """Send a published story to the magazine's followers. `include_body`:
    the whole story (free stories only) instead of its opening."""
    subject: Optional[str] = Field(default=None, max_length=200)
    include_body: bool = False


class CappeIssue(BaseModel):
    id: UUID
    story_id: Optional[UUID] = None
    story_title: Optional[str] = None
    subject: str
    status: str
    include_body: bool = False
    recipient_count: int = 0
    failed_count: int = 0
    sent_at: Optional[datetime] = None
    created_at: datetime



# ── Issues: a designed cover and contents (cappemag07) ──────────────────────

class CappeIssueStoryRef(BaseModel):
    """A story in an issue, in the order sent: its section and contents line."""
    post_id: UUID
    section: Optional[str] = Field(default=None, max_length=40)
    contents_line: Optional[str] = Field(default=None, max_length=200)


class CappeMagazineIssueCreate(BaseModel):
    template: Optional[str] = Field(default=None, max_length=20)


class CappeMagazineIssueSave(BaseModel):
    """What changed. `cover` and `contents` are checked and reshaped by
    `services/magazine/issue_schema.py`; `stories` replaces the whole list."""
    title: Optional[str] = Field(default=None, max_length=120)
    number: Optional[int] = Field(default=None, ge=1, le=9999)
    cover: Optional[dict[str, Any]] = None
    contents: Optional[dict[str, Any]] = None
    stories: Optional[list[CappeIssueStoryRef]] = Field(default=None, max_length=40)


class CappeIssueStoryDraft(BaseModel):
    """A story's unsaved words in the issue editor, previewed in the issue."""
    title: str = Field(default="", max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=600)
    kicker: Optional[str] = Field(default=None, max_length=60)
    byline: Optional[str] = Field(default=None, max_length=160)
    layout: Optional[str] = Field(default=None, max_length=20)
    content: dict[str, Any] = Field(default_factory=dict)


class CappeMagazineIssuePreview(BaseModel):
    """An unsaved issue to render as its book would look. `edit`: the owner's
    editor on the page; `stories_content`: the stories' unsaved words."""
    issue_id: Optional[UUID] = None
    edit: bool = False
    stories_content: dict[UUID, CappeIssueStoryDraft] = Field(default_factory=dict, max_length=40)
    number: int = Field(default=1, ge=1, le=9999)
    title: Optional[str] = Field(default=None, max_length=120)
    cover: dict[str, Any] = Field(default_factory=dict)
    contents: dict[str, Any] = Field(default_factory=dict)
    stories: list[CappeIssueStoryRef] = Field(default_factory=list, max_length=40)


class CappeMagazineIssueStory(BaseModel):
    post_id: UUID
    title: str
    slug: str
    status: str
    access: str = "free"
    hidden: bool = False
    excerpt: Optional[str] = None
    section: Optional[str] = None
    contents_line: Optional[str] = None
    picture: Optional[dict[str, Any]] = None


class CappeMagazineIssue(BaseModel):
    """An issue as its editor needs it. `published`: the drafts this save or
    release just published."""
    id: UUID
    number: int
    title: Optional[str] = None
    status: Literal["draft", "released"]
    released_at: Optional[datetime] = None
    cover: dict[str, Any]
    contents: dict[str, Any]
    stories: list[CappeMagazineIssueStory] = Field(default_factory=list)
    cover_picture: Optional[dict[str, Any]] = None
    hidden: bool = False
    published: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CappeMagazineIssueSummary(BaseModel):
    id: UUID
    number: int
    title: Optional[str] = None
    status: Literal["draft", "released"]
    released_at: Optional[datetime] = None
    story_count: int = 0
    cover: dict[str, Any]
    cover_picture: Optional[dict[str, Any]] = None
    hidden: bool = False
    updated_at: datetime


class CappeMagazineIssueTemplate(BaseModel):
    key: str
    label: str
    cover: dict[str, Any]


class CappeMagazineIssueTaken(BaseModel):
    post_id: UUID
    issue_id: UUID
    number: int


class CappeMagazineIssueOptions(BaseModel):
    """What the issue editor offers: the cover templates, the limits, and
    which stories are already in an issue."""
    templates: list[CappeMagazineIssueTemplate]
    max_lines: int
    max_stories: int
    next_number: int
    taken: list[CappeMagazineIssueTaken]

__all__ = [
    "MastheadStyle",
    "CappeMagazine",
    "CappeMagazineUpdate",
    "CappeStoryPreview",
    "CappeStoryLayoutInfo",
    "CappeStoryOptions",
    "StockSource",
    "CappeStockResult",
    "CappeStockSearch",
    "CappeStockKey",
    "CappeStockImportRequest",
    "CappeStockTopicRequest",
    "CappeStockImport",
    "CappeStockImports",
    "IllustrationAspect",
    "AssistAction",
    "CappeIllustrateRequest",
    "CappeStoryAssistRequest",
    "CappeStoryAssist",
    "HANDLE_PATTERN",
    "CappeHandleCheck",
    "CappeMagazineSiteCreate",
    "CappeFollowRequest",
    "CappeIssueCreate",
    "CappeIssue",
    "CappeMagazineCheckout",
    "CappeMagazineCompCreate",
    "CappeIssueStoryRef",
    "CappeIssueStoryDraft",
    "CappeMagazineIssueCreate",
    "CappeMagazineIssueSave",
    "CappeMagazineIssuePreview",
    "CappeMagazineIssueStory",
    "CappeMagazineIssue",
    "CappeMagazineIssueSummary",
    "CappeMagazineIssueTemplate",
    "CappeMagazineIssueTaken",
    "CappeMagazineIssueOptions",
]
