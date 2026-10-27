"""Pydantic shapes — Cappe social growth (connected accounts, scheduled posts,
dropped videos, the reply inbox, caption drafting, per-site settings)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from ._validators import https_url

SocialNetwork = Literal["instagram", "facebook"]
# Where a downloadable file is made for (TikTok and YouTube can't be posted
# to yet; Instagram's file is for posting from the phone).
ExportPlatform = Literal["instagram", "tiktok", "youtube"]
ExportTarget = Literal["instagram", "tiktok", "youtube", "original", "captions"]
SocialPostStatus = Literal["draft", "scheduled", "rendering", "publishing", "published", "partial", "failed", "cancelled"]
SocialVideoType = Literal["video/mp4", "video/quicktime", "video/webm"]
SocialAutoreplyMode = Literal["off", "review", "auto"]
SocialTone = Literal["friendly", "professional", "playful", "minimal"]

# Instagram's caption limit; Facebook allows more, but one composer, one cap.
MAX_CAPTION_CHARS = 2200
# Instagram carousels take up to 10 items.
MAX_MEDIA_ITEMS = 10
MAX_HASHTAGS = 30
# YouTube: a title up to 100 characters, a description up to 5,000, and tags
# up to 500 characters together.
MAX_YOUTUBE_TITLE = 100
MAX_YOUTUBE_DESCRIPTION = 5000
MAX_YOUTUBE_TAG_CHARS = 500


class CappeSocialConnection(BaseModel):
    """A connected account. The access token is never in a response."""
    id: UUID
    platform: str
    external_id: str
    handle: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    status: str
    last_error: Optional[str] = None
    followers_count: Optional[int] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metrics_at: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    connected_at: datetime
    # Whether its comments and DMs reach the inbox (and the AI replies).
    inbox_enabled: bool = True


class CappeSocialConnectionUpdate(BaseModel):
    inbox_enabled: bool


class CappeSocialConnections(BaseModel):
    # False until the Meta app is configured on this server: the page shows a
    # setup note instead of a Connect button that 503s.
    configured: bool
    connections: list[CappeSocialConnection] = Field(default_factory=list)


class CappeSocialConnectStart(BaseModel):
    authorize_url: str


class CappeSocialMediaItem(BaseModel):
    """A photo (by its URL) or a dropped video (by its asset; the cut each
    network gets is chosen at publish time). `poster` is filled in on the
    way out, from the video's frames."""
    url: Optional[str] = Field(default=None, min_length=8, max_length=1000)
    kind: Literal["image", "video"] = "image"
    alt: Optional[str] = Field(default=None, max_length=500)
    asset_id: Optional[UUID] = None
    poster: Optional[str] = Field(default=None, max_length=1000)

    _url_https = field_validator("url", "poster")(https_url)

    @model_validator(mode="after")
    def _source(self) -> "CappeSocialMediaItem":
        if self.kind == "image" and not self.url:
            raise ValueError("A photo needs its url")
        if self.kind == "video" and not self.asset_id:
            raise ValueError("A video needs its asset_id")
        return self


def _clean_hashtags(tags: Optional[list[str]]) -> Optional[list[str]]:
    """`#Tag` or `tag` → `#tag`, letters/digits/underscore only, de-duplicated."""
    if tags is None:
        return None
    out: list[str] = []
    for raw in tags:
        word = "".join(ch for ch in str(raw).strip().lstrip("#") if ch.isalnum() or ch == "_")
        if not word:
            continue
        tag = f"#{word.lower()}"
        if tag not in out:
            out.append(tag)
    return out[:MAX_HASHTAGS]


class CappeSocialUpload(BaseModel):
    """A dropped photo after normalization. `padded` is true when bars were
    added to fit Instagram's 4:5–1.91:1 range."""
    url: str
    width: int
    height: int
    padded: bool


class CappeSocialAssetPresign(BaseModel):
    """Ask to upload one video straight to storage."""
    filename: str = Field(min_length=1, max_length=200)
    content_type: SocialVideoType
    size: int = Field(gt=0)


class CappeSocialAssetUpload(BaseModel):
    """Where the browser posts the file: `upload_url` with `fields` first,
    then the file, as multipart form data. Then `POST …/assets/{id}/complete`."""
    asset_id: UUID
    upload_url: str
    fields: dict[str, str]
    max_bytes: int


class CappeSocialFrame(BaseModel):
    url: str
    t_ms: int


class CappeSocialRender(BaseModel):
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None


class CappeSocialAsset(BaseModel):
    """A dropped video: `rendering` while it is being cut, then `ready` (or
    `failed` with `error` saying why). `trimmed` when it ran past 90 s."""
    id: UUID
    kind: str
    status: str
    filename: Optional[str] = None
    bytes: int
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    trimmed: bool = False
    frames: list[CappeSocialFrame] = Field(default_factory=list)
    renders: dict[str, CappeSocialRender] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime


class CappeSocialPostInput(BaseModel):
    """A new post. With `scheduled_at` it is queued for then; without, it is a
    draft the owner publishes from the queue (or `POST …/publish`)."""
    caption: str = Field(default="", max_length=MAX_CAPTION_CHARS)
    media: list[CappeSocialMediaItem] = Field(default_factory=list, max_length=MAX_MEDIA_ITEMS)
    link_url: Optional[str] = Field(default=None, max_length=1000)
    product_id: Optional[UUID] = None
    connection_ids: list[UUID] = Field(default_factory=list, max_length=20)
    scheduled_at: Optional[datetime] = None
    alt_text: Optional[str] = Field(default=None, max_length=500)

    _link_https = field_validator("link_url")(https_url)


class CappeSocialPostUpdate(BaseModel):
    caption: Optional[str] = Field(default=None, max_length=MAX_CAPTION_CHARS)
    media: Optional[list[CappeSocialMediaItem]] = Field(default=None, max_length=MAX_MEDIA_ITEMS)
    link_url: Optional[str] = Field(default=None, max_length=1000)
    product_id: Optional[UUID] = None
    connection_ids: Optional[list[UUID]] = Field(default=None, max_length=20)
    scheduled_at: Optional[datetime] = None
    alt_text: Optional[str] = Field(default=None, max_length=500)

    _link_https = field_validator("link_url")(https_url)


class CappeSocialTarget(BaseModel):
    """The post on one connection."""
    id: UUID
    connection_id: UUID
    platform: str
    handle: Optional[str] = None
    status: str
    external_post_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    published_at: Optional[datetime] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    # While a video is with the network: "instagram_processing" /
    # "facebook_processing".
    phase: Optional[str] = None


class CappeSocialPost(BaseModel):
    id: UUID
    site_id: UUID
    caption: str
    media: list[CappeSocialMediaItem] = Field(default_factory=list)
    link_url: Optional[str] = None
    product_id: Optional[UUID] = None
    status: str
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    ai_meta: dict[str, Any] = Field(default_factory=dict)
    targets: list[CappeSocialTarget] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CappeSocialCaptionRequest(BaseModel):
    """Ask for caption options for the media in the composer."""
    media: list[CappeSocialMediaItem] = Field(default_factory=list, max_length=4)
    product_id: Optional[UUID] = None
    brief: Optional[str] = Field(default=None, max_length=500)
    tone: Optional[SocialTone] = None


class CappeSocialCaptionOption(BaseModel):
    text: str = Field(max_length=MAX_CAPTION_CHARS)
    hashtags: list[str] = Field(default_factory=list, max_length=MAX_HASHTAGS)

    _tags = field_validator("hashtags")(_clean_hashtags)


class CappeSocialCaptions(BaseModel):
    options: list[CappeSocialCaptionOption] = Field(default_factory=list)
    alt_text: Optional[str] = None
    model: str


def _clean_tags(tags: list[str]) -> list[str]:
    """YouTube tags: no `#`, trimmed, de-duplicated, 500 characters at most."""
    out: list[str] = []
    for raw in tags:
        tag = " ".join(str(raw).replace("#", " ").split())[:100]
        if tag and tag.lower() not in {t.lower() for t in out}:
            out.append(tag)
    if sum(len(t) for t in out) + max(0, len(out) - 1) > MAX_YOUTUBE_TAG_CHARS:
        raise ValueError(f"YouTube tags can be {MAX_YOUTUBE_TAG_CHARS} characters at most, together")
    return out


class CappeSocialTikTokWords(BaseModel):
    caption: str = Field(default="", max_length=MAX_CAPTION_CHARS)
    hashtags: list[str] = Field(default_factory=list, max_length=MAX_HASHTAGS)

    _tags = field_validator("hashtags")(_clean_hashtags)


class CappeSocialYouTubeWords(BaseModel):
    title: str = Field(default="", max_length=MAX_YOUTUBE_TITLE)
    description: str = Field(default="", max_length=MAX_YOUTUBE_DESCRIPTION)
    tags: list[str] = Field(default_factory=list, max_length=60)

    _tags = field_validator("tags")(_clean_tags)


class CappeSocialExportCreate(BaseModel):
    """Prepare a dropped video for download, one file per platform."""
    asset_id: UUID
    platforms: list[ExportPlatform] = Field(default_factory=lambda: ["instagram", "tiktok", "youtube"],
                                            min_length=1, max_length=3)
    captions: bool = False


class CappeSocialExportFile(BaseModel):
    url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    bytes: Optional[int] = None
    trimmed: Optional[bool] = None
    error: Optional[str] = None


class CappeSocialExportProgress(BaseModel):
    done: int = 0
    total: int = 0
    step: Optional[str] = None


class CappeSocialExport(BaseModel):
    """A video's downloadable files: `files[platform]` once each is made,
    `texts[platform]` the words to paste, `srt` when a captions file exists.
    `status`: queued / working → ready | partial | failed."""
    id: UUID
    asset_id: UUID
    status: str
    platforms: list[str]
    captions: bool
    files: dict[str, Optional[CappeSocialExportFile]] = Field(default_factory=dict)
    progress: CappeSocialExportProgress = Field(default_factory=CappeSocialExportProgress)
    srt: bool = False
    texts: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    filename: Optional[str] = None
    poster: Optional[str] = None
    duration_ms: Optional[int] = None
    original: bool = True
    created_at: datetime
    updated_at: datetime


class CappeSocialExportDownload(BaseModel):
    """A short-lived link that saves the file as `filename`."""
    url: str
    filename: str
    expires_in: int


class CappeSocialChatAttachment(BaseModel):
    """Something dropped into the chat: a photo already uploaded through
    `…/social/media` (by URL) or a video (by its asset)."""
    kind: Literal["image", "video"]
    url: Optional[str] = Field(default=None, max_length=1000)
    asset_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, max_length=200)

    _url_https = field_validator("url")(https_url)

    @model_validator(mode="after")
    def _source(self) -> "CappeSocialChatAttachment":
        if self.kind == "image" and not self.url:
            raise ValueError("A photo needs its url")
        if self.kind == "video" and not self.asset_id:
            raise ValueError("A video needs its asset_id")
        return self


class CappeSocialChatTurnInput(BaseModel):
    """The owner's message, with anything dropped alongside it. No
    `conversation_id` starts a new chat."""
    conversation_id: Optional[UUID] = None
    message: str = Field(default="", max_length=4000)
    attachments: list[CappeSocialChatAttachment] = Field(default_factory=list, max_length=10)


class CappeSocialChatMessage(BaseModel):
    id: UUID
    role: str
    content: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class CappeSocialPlanCard(BaseModel):
    """The plan the owner confirms. `plan` is what `services/social/chat/
    plan.py:resolve` built (when, accounts, link, posts, warnings, needs);
    `revision` is what a confirm must name."""
    id: str
    status: str
    revision: int
    plan: dict[str, Any]
    post_ids: list[UUID] = Field(default_factory=list)
    export_ids: list[UUID] = Field(default_factory=list)
    model: Optional[str] = None
    created_at: Optional[str] = None


class CappeSocialChatSummary(BaseModel):
    """A row in the chat list: its last message, and where its latest plan
    stands (`proposed` means it is waiting on the owner)."""
    id: UUID
    title: str
    created_at: Optional[datetime] = None
    updated_at: datetime
    last: Optional[str] = None
    plan_status: Optional[str] = None


class CappeSocialChatRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CappeSocialChat(BaseModel):
    id: UUID
    title: str
    messages: list[CappeSocialChatMessage] = Field(default_factory=list)
    plan: Optional[CappeSocialPlanCard] = None


class CappeSocialChatTurn(BaseModel):
    conversation_id: UUID
    message: CappeSocialChatMessage
    plan: Optional[CappeSocialPlanCard] = None


class CappeSocialInstagramWords(BaseModel):
    caption: str = Field(default="", max_length=MAX_CAPTION_CHARS)
    hashtags: list[str] = Field(default_factory=list, max_length=MAX_HASHTAGS)

    _tags = field_validator("hashtags")(_clean_hashtags)


class CappeSocialFacebookWords(BaseModel):
    text: str = Field(default="", max_length=MAX_CAPTION_CHARS)


class CappeSocialPlanPostEdit(BaseModel):
    instagram: CappeSocialInstagramWords
    facebook: CappeSocialFacebookWords
    alt_text: Optional[str] = Field(default=None, max_length=500)
    tiktok: Optional[CappeSocialTikTokWords] = None
    youtube: Optional[CappeSocialYouTubeWords] = None


class CappeSocialPlanExportsEdit(BaseModel):
    """Which downloadable files to make for the plan's videos."""
    platforms: list[ExportPlatform] = Field(default_factory=list, max_length=3)
    captions: bool = False


class CappeSocialPlanConfirm(BaseModel):
    """Post the plan as shown, with the owner's edits. `mode`: `at` needs
    `when_local` (the store's wall clock, `YYYY-MM-DDTHH:MM`); `now` posts at
    once; `draft` saves without scheduling; `export` posts nothing and only
    makes the downloadable files. `exports` (any mode) says which files."""
    revision: int
    mode: Literal["now", "at", "draft", "export"]
    when_local: Optional[str] = Field(default=None, max_length=32)
    connection_ids: list[UUID] = Field(default_factory=list, max_length=20)
    keep_link: bool = True
    posts: Optional[list[CappeSocialPlanPostEdit]] = Field(default=None, max_length=20)
    exports: Optional[CappeSocialPlanExportsEdit] = None


class CappeSocialPlanConfirmed(BaseModel):
    plan: CappeSocialPlanCard
    posts: list["CappeSocialPost"] = Field(default_factory=list)
    exports: list[CappeSocialExport] = Field(default_factory=list)


class CappeSocialSettings(BaseModel):
    autoreply_mode: SocialAutoreplyMode = "off"
    reply_to_comments: bool = True
    reply_to_messages: bool = True
    tone: SocialTone = "friendly"
    # The owner's own notes: shipping times, return policy, what's not on the
    # site. The one thing the model may say beyond the catalog.
    business_facts: str = Field(default="", max_length=4000)
    signature: Optional[str] = Field(default=None, max_length=120)
    default_hashtags: list[str] = Field(default_factory=list, max_length=MAX_HASHTAGS)
    max_auto_per_hour: int = Field(default=20, ge=0, le=200)
    # Words that always route to the owner, on top of the built-in list.
    escalate_words: list[str] = Field(default_factory=list, max_length=50)
    # Whether this plan may turn the AI inbox on (`social_autoreply`) and post
    # video (`social_video`).
    autoreply_available: bool = True
    video_available: bool = False
    ai_available: bool = True

    _tags = field_validator("default_hashtags")(_clean_hashtags)

    @field_validator("escalate_words")
    @classmethod
    def _trim_words(cls, v: list[str]) -> list[str]:
        return [w.strip().lower()[:60] for w in v if w and w.strip()]


class CappeSocialSettingsUpdate(BaseModel):
    autoreply_mode: Optional[SocialAutoreplyMode] = None
    reply_to_comments: Optional[bool] = None
    reply_to_messages: Optional[bool] = None
    tone: Optional[SocialTone] = None
    business_facts: Optional[str] = Field(default=None, max_length=4000)
    signature: Optional[str] = Field(default=None, max_length=120)
    default_hashtags: Optional[list[str]] = Field(default=None, max_length=MAX_HASHTAGS)
    max_auto_per_hour: Optional[int] = Field(default=None, ge=0, le=200)
    escalate_words: Optional[list[str]] = Field(default=None, max_length=50)

    _tags = field_validator("default_hashtags")(_clean_hashtags)

    @field_validator("escalate_words")
    @classmethod
    def _trim_words(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return [w.strip().lower()[:60] for w in v if w and w.strip()]


class CappeSocialReply(BaseModel):
    id: UUID
    body: str
    mode: str
    status: str
    model: Optional[str] = None
    grounding: dict[str, Any] = Field(default_factory=dict)
    external_reply_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class CappeSocialInboxItem(BaseModel):
    id: UUID
    connection_id: UUID
    platform: str
    handle: Optional[str] = None
    kind: str
    external_id: str
    external_parent_id: Optional[str] = None
    author_name: Optional[str] = None
    text: str
    received_at: datetime
    status: str
    classification: dict[str, Any] = Field(default_factory=dict)
    replies: list[CappeSocialReply] = Field(default_factory=list)


class CappeSocialReplyInput(BaseModel):
    """Send a reply: the owner's own words, or an approved draft (`reply_id`)
    possibly edited."""
    body: str = Field(min_length=1, max_length=2000)
    reply_id: Optional[UUID] = None


class CappeSocialFollowers(BaseModel):
    platform: str
    handle: Optional[str] = None
    followers_count: Optional[int] = None


class CappeSocialOverview(BaseModel):
    connections: int
    scheduled: int
    published_30d: int
    inbox_new: int
    drafts_waiting: int
    followers: list[CappeSocialFollowers] = Field(default_factory=list)
    autoreply_mode: str
    meta_configured: bool
    ai_available: bool


__all__ = [
    "SocialNetwork", "SocialPostStatus", "SocialAutoreplyMode", "SocialTone", "SocialVideoType",
    "ExportPlatform", "ExportTarget", "MAX_CAPTION_CHARS", "MAX_MEDIA_ITEMS", "MAX_HASHTAGS",
    "MAX_YOUTUBE_TITLE", "MAX_YOUTUBE_DESCRIPTION", "MAX_YOUTUBE_TAG_CHARS",
    "CappeSocialTikTokWords", "CappeSocialYouTubeWords", "CappeSocialExportCreate", "CappeSocialExportFile",
    "CappeSocialExportProgress", "CappeSocialExport", "CappeSocialExportDownload", "CappeSocialPlanExportsEdit",
    "CappeSocialConnection", "CappeSocialConnectionUpdate", "CappeSocialConnections", "CappeSocialConnectStart",
    "CappeSocialMediaItem", "CappeSocialUpload", "CappeSocialPostInput", "CappeSocialPostUpdate",
    "CappeSocialAssetPresign", "CappeSocialAssetUpload", "CappeSocialFrame", "CappeSocialRender", "CappeSocialAsset",
    "CappeSocialChatAttachment", "CappeSocialChatTurnInput", "CappeSocialChatMessage", "CappeSocialPlanCard",
    "CappeSocialChatSummary", "CappeSocialChatRename", "CappeSocialChat", "CappeSocialChatTurn", "CappeSocialInstagramWords",
    "CappeSocialFacebookWords", "CappeSocialPlanPostEdit", "CappeSocialPlanConfirm", "CappeSocialPlanConfirmed",
    "CappeSocialTarget", "CappeSocialPost",
    "CappeSocialCaptionRequest", "CappeSocialCaptionOption", "CappeSocialCaptions",
    "CappeSocialSettings", "CappeSocialSettingsUpdate",
    "CappeSocialReply", "CappeSocialInboxItem", "CappeSocialReplyInput",
    "CappeSocialFollowers", "CappeSocialOverview",
]
