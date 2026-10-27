"""Meta Graph API — Instagram business accounts and Facebook Pages.

One Facebook Login (Facebook Login for Business) covers both: the user grants
the app access to their Pages, each Page carries a long-lived Page token, and
an Instagram business account hangs off its Page and is addressed with that
same Page token. So the OAuth round-trip yields one `ConnectionDraft` per Page
and one per Instagram account found on it.

Everything here is a thin, typed wrapper over the documented endpoints:
  * publishing — `/{ig}/media` + `/{ig}/media_publish` (single image,
    carousel or Reel), `/{page}/photos` + `/{page}/feed` (one or several
    photos), `/{page}/video_reels` (a Reel) and `/{page}/videos` (a landscape
    video);
  * replies — `/{comment}/replies` (Instagram), `/{comment}/comments`
    (Facebook), `/{page|ig}/messages` for DMs;
  * webhooks — the `GET` challenge, the `X-Hub-Signature-256` HMAC, and the
    `instagram` / `page` payload shapes into `InboundEvent`s;
  * metrics — follower counts and per-post insights.

No call here retries by itself: the publisher decides from `retryable`.
Images and videos must be reachable by Meta's fetchers, which our CloudFront
URLs are.

Video takes Meta minutes to process, so a video publish is resumable: the
first call starts it and returns `Pending` with the container/video id, and
each later call (the publisher's next sweep, `state` passed back) checks on
it once — no call here waits.

A photo publish is resumable the same way, because the call that makes a post
live can't be repeated blind: Meta sometimes answers it with a timeout or an
"unknown error" after the post went out. So the handle is saved (`checkpoint`)
before that call, and a retry first asks whether it already went out — an
Instagram container's `status_code`, or the Page's recent posts for Facebook.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

import httpx

from app.config import get_settings

from .base import ConnectionDraft, InboundEvent, Pending, ProviderError, PublishResult

logger = logging.getLogger(__name__)

GRAPH_HOST = "https://graph.facebook.com"
LOGIN_HOST = "https://www.facebook.com"
RUPLOAD_HOST = "https://rupload.facebook.com"

# Meta asks for a container's status at most once a minute; processing a
# short clip usually takes well under that, so the first look is sooner.
FIRST_CHECK_SECONDS = 30
CHECK_SECONDS = 60
IG_MAX_CHECKS = 10
FB_MAX_CHECKS = 30

# The permissions one Connect asks for. Publishing + engagement on Pages, and
# the Instagram set (read, publish, comments/messages, post insights). With a
# Facebook Login for Business configuration (`login_config_id`) the dialog
# asks for the configuration's permissions instead, so it must list these.
SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "pages_manage_engagement",
    "pages_manage_metadata",
    "pages_messaging",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_messages",
    "instagram_manage_insights",
    "business_management",
)

# What each network can't post or answer without. A person can untick any of
# these in the dialog; Connect then says which are missing.
REQUIRED_SCOPES = {
    "facebook": ("pages_manage_posts", "pages_manage_engagement", "pages_messaging"),
    "instagram": ("instagram_content_publish", "instagram_manage_comments", "instagram_manage_messages"),
}

# Meta error codes worth another try later: unknown/transient, rate limits.
# 9007: the media container isn't ready to publish yet — a later try
# recreates it.
_RETRYABLE_CODES = frozenset({1, 2, 4, 17, 32, 341, 368, 613, 9007})
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# A Facebook post found among the Page's recent ones counts as ours when its
# text matches and it was made at most this long before the checkpoint.
_FB_MATCH_SLACK = timedelta(minutes=5)
MAYBE_POSTED = ("Facebook may already have this post. Check the Page before you retry, "
                "or it may post twice.")

Checkpoint = Callable[[dict[str, Any]], Awaitable[None]]


class MetaConfig:
    """App credentials. `from_settings()` is None until all of them are set,
    and every entry point treats None as "not configured" rather than failing
    deep inside a request."""

    def __init__(self, *, app_id: str, app_secret: str, verify_token: Optional[str], version: str = "v21.0",
                 login_config_id: Optional[str] = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verify_token = verify_token
        self.version = version
        self.login_config_id = login_config_id

    @classmethod
    def from_settings(cls) -> Optional["MetaConfig"]:
        try:
            s = get_settings()
        except RuntimeError:  # settings not loaded (a bare test process)
            return None
        if not (s.cappe_meta_app_id and s.cappe_meta_app_secret):
            return None
        return cls(
            app_id=s.cappe_meta_app_id, app_secret=s.cappe_meta_app_secret,
            verify_token=s.cappe_meta_verify_token, version=s.cappe_meta_graph_version or "v21.0",
            login_config_id=getattr(s, "cappe_meta_login_config_id", None) or None,
        )

    def graph(self, path: str) -> str:
        return f"{GRAPH_HOST}/{self.version}/{path.lstrip('/')}"


def configured() -> bool:
    return MetaConfig.from_settings() is not None


# ── HTTP ────────────────────────────────────────────────────────────────────

def _client(client: Optional[httpx.AsyncClient]) -> tuple[httpx.AsyncClient, bool]:
    if client is not None:
        return client, False
    return httpx.AsyncClient(timeout=_TIMEOUT), True


def _error_from(payload: Any, status: int) -> ProviderError:
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        code = err.get("code")
        message = str(err.get("message") or "Meta API error")[:300]
        retryable = status >= 500 or code in _RETRYABLE_CODES
        return ProviderError(f"Meta: {message}", retryable=retryable, code=code if isinstance(code, int) else None)
    return ProviderError(f"Meta API HTTP {status}", retryable=status >= 500 or status == 429)


async def call(
    cfg: MetaConfig, method: str, path: str, *, token: Optional[str] = None,
    params: Optional[dict[str, Any]] = None, data: Optional[dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    """One Graph call. Raises ProviderError on a non-2xx or a Meta error
    envelope; network failures are retryable."""
    query = dict(params or {})
    if token:
        query["access_token"] = token
    http, own = _client(client)
    try:
        try:
            response = await http.request(method, cfg.graph(path), params=query, data=data)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Meta unreachable: {exc.__class__.__name__}", retryable=True) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400 or (isinstance(payload, dict) and "error" in payload):
            raise _error_from(payload, response.status_code)
        return payload if isinstance(payload, dict) else {"data": payload}
    finally:
        if own:
            await http.aclose()


# ── OAuth ───────────────────────────────────────────────────────────────────

def authorize_url(cfg: MetaConfig, *, redirect_uri: str, state: str) -> str:
    """The login dialog. A Business-type app's Facebook Login for Business
    takes a configuration id in place of a scope list (Meta: scope "should
    not be used" with it); without one, the classic scope list."""
    params = {"client_id": cfg.app_id, "redirect_uri": redirect_uri, "state": state, "response_type": "code"}
    if cfg.login_config_id:
        params["config_id"] = cfg.login_config_id
    else:
        params["scope"] = ",".join(SCOPES)
    return f"{LOGIN_HOST}/{cfg.version}/dialog/oauth?{urlencode(params)}"


async def granted_scopes(cfg: MetaConfig, user_token: str, *, client=None) -> tuple[str, ...]:
    """The permissions the person actually granted (they can untick any).
    When Meta won't say, the ones asked for — the first publish or reply
    that needs a missing one reports it then."""
    try:
        out = await call(cfg, "GET", "me/permissions", token=user_token, client=client)
    except ProviderError as exc:
        logger.warning("meta: could not read granted permissions: %s", exc)
        return SCOPES
    granted = sorted({str(p.get("permission")) for p in out.get("data") or []
                      if isinstance(p, dict) and p.get("status") == "granted" and p.get("permission")})
    return tuple(granted)


def missing_scopes(draft: ConnectionDraft) -> list[str]:
    """What this account can't post or answer without, of what was granted."""
    return [s for s in REQUIRED_SCOPES.get(draft.platform, ()) if s not in draft.scopes]


async def exchange_code(
    cfg: MetaConfig, code: str, *, redirect_uri: str, client: Optional[httpx.AsyncClient] = None,
) -> list[ConnectionDraft]:
    """code → short-lived user token → long-lived user token → the Pages it
    manages (with their own tokens) and each Page's Instagram account."""
    short = await call(cfg, "GET", "oauth/access_token", params={
        "client_id": cfg.app_id, "client_secret": cfg.app_secret,
        "redirect_uri": redirect_uri, "code": code,
    }, client=client)
    user_token = str(short.get("access_token") or "")
    if not user_token:
        raise ProviderError("Meta returned no access token", retryable=False)
    long = await call(cfg, "GET", "oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": cfg.app_id,
        "client_secret": cfg.app_secret, "fb_exchange_token": user_token,
    }, client=client)
    long_token = str(long.get("access_token") or user_token)
    expires_in = long.get("expires_in")
    # A Page token minted from a long-lived user token does not expire; keep
    # the user token's horizon as the conservative "re-connect by" date.
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if isinstance(expires_in, (int, float)) and expires_in > 0 else None
    )
    scopes = await granted_scopes(cfg, long_token, client=client)
    pages = await call(cfg, "GET", "me/accounts", token=long_token, params={
        "fields": "id,name,access_token,picture{url},"
                  "instagram_business_account{id,username,profile_picture_url,followers_count}",
        "limit": 50,
    }, client=client)
    drafts: list[ConnectionDraft] = []
    for page in pages.get("data") or []:
        page_token = str(page.get("access_token") or "")
        page_id = str(page.get("id") or "")
        if not (page_token and page_id):
            continue
        picture = ((page.get("picture") or {}).get("data") or {}).get("url") if isinstance(page.get("picture"), dict) else None
        drafts.append(ConnectionDraft(
            platform="facebook", external_id=page_id, access_token=page_token,
            handle=None, display_name=page.get("name"), avatar_url=picture,
            token_expires_at=expires_at, scopes=scopes,
        ))
        ig = page.get("instagram_business_account")
        if isinstance(ig, dict) and ig.get("id"):
            followers = ig.get("followers_count")
            drafts.append(ConnectionDraft(
                platform="instagram", external_id=str(ig["id"]), access_token=page_token,
                handle=ig.get("username"), display_name=ig.get("username"),
                avatar_url=ig.get("profile_picture_url"), token_expires_at=expires_at, scopes=scopes,
                followers_count=int(followers) if isinstance(followers, int) else None,
            ))
    return drafts


async def subscribe_page(cfg: MetaConfig, page_id: str, page_token: str, *, client=None) -> bool:
    """Subscribe the app to the Page's feed + messages so webhooks arrive.
    Best-effort: a failure here means no inbox for that Page, not a failed
    connect."""
    try:
        out = await call(cfg, "POST", f"{page_id}/subscribed_apps", token=page_token,
                         data={"subscribed_fields": "feed,messages"}, client=client)
    except ProviderError as exc:
        logger.warning("meta: could not subscribe page %s to webhooks: %s", page_id, exc)
        return False
    return bool(out.get("success"))


# ── Publishing ──────────────────────────────────────────────────────────────

def _with_link(caption: str, link_url: Optional[str]) -> str:
    text = (caption or "").strip()
    if link_url and link_url not in text:
        text = f"{text}\n\n{link_url}".strip()
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _save(checkpoint: Optional[Checkpoint], state: dict[str, Any]) -> None:
    """Record where a publish got to, before a call that can't be repeated."""
    if checkpoint is not None:
        await checkpoint(state)


async def _ig_permalink(cfg, media_id: str, token: str, client) -> Optional[str]:
    try:
        out = await call(cfg, "GET", media_id, token=token, params={"fields": "permalink"}, client=client)
    except ProviderError:
        return None
    return out.get("permalink")


async def _ig_published(cfg, ig_id: str, token: str, container_id: str, caption: str, client) -> PublishResult:
    """A container Meta reports PUBLISHED: an earlier call published it and
    the outcome was never recorded. Its media id is found among the account's
    latest posts by the caption; failing that the container id stands in —
    the post is live either way."""
    want = (caption or "").strip()
    if want:
        try:
            out = await call(cfg, "GET", f"{ig_id}/media", token=token,
                             params={"fields": "id,caption,permalink", "limit": 10}, client=client)
        except ProviderError:
            out = {}
        for item in out.get("data") or []:
            if isinstance(item, dict) and item.get("id") and (item.get("caption") or "").strip() == want:
                return PublishResult(external_post_id=str(item["id"]), permalink=item.get("permalink"))
    return PublishResult(external_post_id=container_id)


async def _publish_ig_reel(cfg, ig_id: str, token: str, caption: str, video: dict, state: dict,
                           client) -> PublishResult | Pending:
    """A Reel: create the container from the hosted video, then — on later
    calls — check whether Meta has finished processing it and publish."""
    container_id = state.get("container_id")
    if not container_id:
        data = {"media_type": "REELS", "video_url": video["url"], "caption": caption, "share_to_feed": "true"}
        if isinstance(video.get("thumb_offset_ms"), int):
            data["thumb_offset"] = str(video["thumb_offset_ms"])
        container = await call(cfg, "POST", f"{ig_id}/media", token=token, data=data, client=client)
        container_id = str(container.get("id") or "")
        if not container_id:
            raise ProviderError("Instagram returned no media container", retryable=True)
        return Pending("instagram_processing", {"container_id": container_id, "checks": 0}, FIRST_CHECK_SECONDS)
    out = await call(cfg, "GET", container_id, token=token, params={"fields": "status_code,status"}, client=client)
    code = out.get("status_code")
    if code in ("ERROR", "EXPIRED"):
        detail = str(out.get("status") or code)[:200]
        raise ProviderError(f"Instagram couldn't process the video ({detail})", retryable=False)
    if code == "PUBLISHED":
        return await _ig_published(cfg, ig_id, token, str(container_id), caption, client)
    if code != "FINISHED":
        checks = int(state.get("checks") or 0) + 1
        if checks >= IG_MAX_CHECKS:
            raise ProviderError("Instagram was still processing the video after 10 minutes", retryable=False)
        return Pending("instagram_processing", {**state, "checks": checks}, CHECK_SECONDS)
    published = await call(cfg, "POST", f"{ig_id}/media_publish", token=token,
                           data={"creation_id": container_id}, client=client)
    media_id = str(published.get("id") or "")
    if not media_id:
        raise ProviderError("Instagram returned no media id", retryable=True)
    return PublishResult(external_post_id=media_id, permalink=await _ig_permalink(cfg, media_id, token, client))


async def _ig_photo_container(cfg, ig_id: str, token: str, caption: str, images: list[dict], client) -> str:
    """One photo's container, or a carousel's (its children first)."""
    if len(images) == 1:
        container = await call(cfg, "POST", f"{ig_id}/media", token=token,
                               data={"image_url": images[0]["url"], "caption": caption}, client=client)
    else:
        children = []
        for item in images[:10]:
            child = await call(cfg, "POST", f"{ig_id}/media", token=token,
                               data={"image_url": item["url"], "is_carousel_item": "true"}, client=client)
            child_id = str(child.get("id") or "")
            if not child_id:
                raise ProviderError("Instagram returned no media container", retryable=True)
            children.append(child_id)
        container = await call(cfg, "POST", f"{ig_id}/media", token=token, data={
            "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption,
        }, client=client)
    creation_id = str(container.get("id") or "")
    if not creation_id:
        raise ProviderError("Instagram returned no media container", retryable=True)
    return creation_id


async def _publish_ig_photos(cfg, ig_id: str, token: str, caption: str, images: list[dict], state: dict,
                             client, checkpoint: Optional[Checkpoint]) -> PublishResult | Pending:
    """One photo or a carousel. The container is checkpointed before
    `media_publish`, so a retry after an answer that never came (a timeout,
    an "unknown error" Meta gives for a post that went live) asks the
    container whether it went out instead of posting it again."""
    container_id = state.get("container_id")
    if container_id:
        out = await call(cfg, "GET", container_id, token=token, params={"fields": "status_code,status"}, client=client)
        code = out.get("status_code")
        if code == "PUBLISHED":
            return await _ig_published(cfg, ig_id, token, str(container_id), caption, client)
        if code == "ERROR":
            detail = str(out.get("status") or code)[:200]
            raise ProviderError(f"Instagram couldn't use the photo ({detail})", retryable=False)
        if code == "EXPIRED":
            container_id = None  # it never went out; make it again
        elif code == "IN_PROGRESS":
            checks = int(state.get("checks") or 0) + 1
            if checks >= IG_MAX_CHECKS:
                raise ProviderError("Instagram was still preparing the photo after 10 minutes", retryable=False)
            return Pending("instagram_publishing", {**state, "checks": checks}, CHECK_SECONDS)
    if not container_id:
        container_id = await _ig_photo_container(cfg, ig_id, token, caption, images, client)
        await _save(checkpoint, {"container_id": container_id, "phase": "instagram_publishing"})
    published = await call(cfg, "POST", f"{ig_id}/media_publish", token=token,
                           data={"creation_id": container_id}, client=client)
    media_id = str(published.get("id") or "")
    if not media_id:
        raise ProviderError("Instagram returned no media id", retryable=True)
    return PublishResult(external_post_id=media_id, permalink=await _ig_permalink(cfg, media_id, token, client))


async def _publish_instagram(cfg, ig_id: str, token: str, caption: str, media: list[dict], state: dict,
                             client, checkpoint: Optional[Checkpoint] = None) -> PublishResult | Pending:
    videos = [m for m in media if m.get("kind") == "video" and m.get("url")]
    if videos:
        return await _publish_ig_reel(cfg, ig_id, token, caption, videos[0], state, client)
    images = [m for m in media if (m.get("kind") or "image") == "image" and m.get("url")]
    if not images:
        raise ProviderError("Instagram needs a photo or a video", retryable=False)
    return await _publish_ig_photos(cfg, ig_id, token, caption, images, state, client, checkpoint)


async def _fb_permalink(cfg, post_id: str, token: str, client) -> Optional[str]:
    try:
        out = await call(cfg, "GET", post_id, token=token, params={"fields": "permalink_url"}, client=client)
    except ProviderError:
        return None
    return out.get("permalink_url")


async def _rupload(cfg, video_id: str, token: str, file_url: str, client) -> None:
    """Hand Facebook the hosted file for a Reel upload session. This host
    takes `Authorization: OAuth <token>` (not Bearer) and the file's URL as a
    header."""
    url = f"{RUPLOAD_HOST}/video-upload/{cfg.version}/{video_id}"
    try:
        response = await client.post(url, headers={"Authorization": f"OAuth {token}", "file_url": file_url})
    except httpx.HTTPError as exc:
        raise ProviderError(f"Meta unreachable: {exc.__class__.__name__}", retryable=True) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or (isinstance(payload, dict) and "error" in payload):
        raise _error_from(payload, response.status_code)
    if not (isinstance(payload, dict) and payload.get("success")):
        raise ProviderError("Facebook didn't take the video upload", retryable=True)


def _absolute_fb_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return f"https://www.facebook.com{path}" if path.startswith("/") else path


def _fb_video_failure(status: dict) -> Optional[str]:
    """Why Facebook gave up on a video, or None while it hasn't."""
    video_status = status.get("video_status")
    for phase in ("uploading_phase", "processing_phase", "publishing_phase"):
        info = status.get(phase) or {}
        if isinstance(info, dict) and (info.get("status") == "error" or info.get("publish_status") == "error"):
            err = info.get("error")
            message = err.get("message") if isinstance(err, dict) else None
            return str(message) if message else f"{phase.split('_')[0]} failed"
    if video_status in ("error", "upload_failed", "expired"):
        return str(video_status)
    return None


async def _fb_already_posted(cfg, page_id: str, token: str, text: str, state: dict, client, *,
                             edge: str = "published_posts", field: str = "message") -> Optional[PublishResult]:
    """On a retry after a checkpointed write (`final_write_at`): what that
    write left on the Page — a post (or video) with exactly this text, made
    since — or None. A write with no text can't be told apart from the
    Page's other posts, so it fails asking the owner to check."""
    since = state.get("final_write_at")
    if not since:
        return None
    if not text:
        raise ProviderError(MAYBE_POSTED, retryable=False)
    try:
        out = await call(cfg, "GET", f"{page_id}/{edge}", token=token, params={
            "fields": f"id,{field},created_time,permalink_url", "limit": 10,
        }, client=client)
    except ProviderError as exc:
        raise ProviderError(f"{MAYBE_POSTED} ({exc})", retryable=exc.retryable, code=exc.code) from exc
    started = _ts(since)
    for item in out.get("data") or []:
        if not isinstance(item, dict) or not item.get("id") or (item.get(field) or "").strip() != text:
            continue
        made = _ts(item.get("created_time"))
        if started and made and made < started - _FB_MATCH_SLACK:
            continue
        return PublishResult(external_post_id=str(item["id"]), permalink=_absolute_fb_url(item.get("permalink_url")))
    return None


def _fb_video_done(status: dict) -> bool:
    if status.get("video_status") != "ready":
        return False
    publishing = status.get("publishing_phase")
    if not isinstance(publishing, dict) or not publishing:
        return True  # a Page video reports no publishing phase
    return publishing.get("status") in ("complete", "completed") or publishing.get("publish_status") == "published"


async def _publish_fb_video(cfg, page_id: str, token: str, caption: str, video: dict, state: dict,
                            client, checkpoint: Optional[Checkpoint] = None) -> PublishResult | Pending:
    """A Reel (vertical cut) or a Page video (landscape cut). Both are pulled
    by Facebook from our URL; later calls check on processing."""
    video_id = state.get("video_id")
    if not video_id:
        if video.get("format") == "video":
            # A Page video is live from this one call, so it is checkpointed
            # and a retry looks for it among the Page's videos first.
            found = await _fb_already_posted(cfg, page_id, token, caption, state, client,
                                             edge="videos", field="description")
            if found:
                return Pending("facebook_processing", {"video_id": found.external_post_id, "checks": 0},
                               FIRST_CHECK_SECONDS)
            await _save(checkpoint, {"final_write_at": _now_iso(), "phase": "facebook_uploading"})
            out = await call(cfg, "POST", f"{page_id}/videos", token=token,
                             data={"file_url": video["url"], "description": caption, "published": "true"}, client=client)
            video_id = str(out.get("id") or "")
        else:
            # The Reel's id is kept before anything is uploaded, so a retry
            # (a lost response, a killed worker) finishes this same Reel
            # instead of starting a second one.
            start = await call(cfg, "POST", f"{page_id}/video_reels", token=token,
                               data={"upload_phase": "start"}, client=client)
            video_id = str(start.get("video_id") or "")
            if not video_id:
                raise ProviderError("Facebook returned no video id", retryable=True)
            return Pending("facebook_uploading", {"video_id": video_id, "upload": True, "checks": 0}, 0)
        if not video_id:
            raise ProviderError("Facebook returned no video id", retryable=True)
        return Pending("facebook_processing", {"video_id": video_id, "checks": 0}, FIRST_CHECK_SECONDS)
    if state.get("upload"):
        await _rupload(cfg, video_id, token, video["url"], client)
        done = await call(cfg, "POST", f"{page_id}/video_reels", token=token, data={
            "video_id": video_id, "upload_phase": "finish", "video_state": "PUBLISHED", "description": caption,
        }, client=client)
        if not done.get("success"):
            raise ProviderError("Facebook didn't publish the Reel", retryable=True)
        return Pending("facebook_processing", {"video_id": video_id, "checks": 0}, FIRST_CHECK_SECONDS)
    out = await call(cfg, "GET", video_id, token=token, params={"fields": "status,permalink_url"}, client=client)
    status = out.get("status") if isinstance(out.get("status"), dict) else {}
    failure = _fb_video_failure(status)
    if failure:
        raise ProviderError(f"Facebook couldn't process the video ({failure[:200]})", retryable=False)
    if not _fb_video_done(status):
        checks = int(state.get("checks") or 0) + 1
        if checks >= FB_MAX_CHECKS:
            raise ProviderError("Facebook was still processing the video after 30 minutes", retryable=False)
        return Pending("facebook_processing", {**state, "checks": checks}, CHECK_SECONDS)
    return PublishResult(external_post_id=str(video_id), permalink=_absolute_fb_url(out.get("permalink_url")))


async def _publish_facebook(cfg, page_id: str, token: str, caption: str, media: list[dict],
                            link_url: Optional[str], state: dict, client,
                            checkpoint: Optional[Checkpoint] = None) -> PublishResult | Pending:
    videos = [m for m in media if m.get("kind") == "video" and m.get("url")]
    if videos:
        return await _publish_fb_video(cfg, page_id, token, caption, videos[0], state, client, checkpoint)
    images = [m for m in media if (m.get("kind") or "image") == "image" and m.get("url")]
    if not images and not caption:
        raise ProviderError("A Facebook post needs a caption or a photo", retryable=False)
    # The write that makes the post live happens once: checkpointed first,
    # and a retry looks for it among the Page's latest posts before writing.
    found = await _fb_already_posted(cfg, page_id, token, caption, state, client)
    if found:
        if found.permalink:
            return found
        return PublishResult(external_post_id=found.external_post_id,
                             permalink=await _fb_permalink(cfg, found.external_post_id, token, client))
    attached = []
    if len(images) > 1:
        # Unpublished uploads first: repeating them posts nothing.
        for item in images[:10]:
            photo = await call(cfg, "POST", f"{page_id}/photos", token=token,
                               data={"url": item["url"], "published": "false"}, client=client)
            attached.append({"media_fbid": str(photo.get("id"))})
    await _save(checkpoint, {"final_write_at": _now_iso(), "phase": "facebook_publishing"})
    if len(images) == 1:
        out = await call(cfg, "POST", f"{page_id}/photos", token=token,
                         data={"url": images[0]["url"], "message": caption, "published": "true"}, client=client)
        post_id = str(out.get("post_id") or out.get("id") or "")
    elif images:
        out = await call(cfg, "POST", f"{page_id}/feed", token=token,
                         data={"message": caption, "attached_media": json.dumps(attached)}, client=client)
        post_id = str(out.get("id") or "")
    else:
        data: dict[str, Any] = {"message": caption}
        if link_url:
            data["link"] = link_url
        out = await call(cfg, "POST", f"{page_id}/feed", token=token, data=data, client=client)
        post_id = str(out.get("id") or "")
    if not post_id:
        raise ProviderError("Facebook returned no post id", retryable=True)
    return PublishResult(external_post_id=post_id, permalink=await _fb_permalink(cfg, post_id, token, client))


async def publish(
    cfg: MetaConfig, *, platform: str, external_id: str, token: str,
    caption: str, media: list[dict], link_url: Optional[str] = None,
    state: Optional[dict[str, Any]] = None, client: Optional[httpx.AsyncClient] = None,
    checkpoint: Optional[Checkpoint] = None,
) -> PublishResult | Pending:
    """Publish, or for a video start/continue publishing: `state` is what the
    previous call's `Pending` (or `checkpoint`) carried. `checkpoint(state)`
    is called before a write that makes a post live, so the next call can
    tell whether it already went out.

    The link goes into Facebook's text only: Instagram doesn't make a link in
    a caption clickable, and it would count against the 2,200 characters."""
    http, own = _client(client)
    try:
        if platform == "instagram":
            return await _publish_instagram(cfg, external_id, token, (caption or "").strip(), media,
                                            dict(state or {}), http, checkpoint)
        if platform == "facebook":
            return await _publish_facebook(cfg, external_id, token, _with_link(caption, link_url), media,
                                           link_url, dict(state or {}), http, checkpoint)
        raise ProviderError(f"Unknown platform {platform!r}", retryable=False)
    finally:
        if own:
            await http.aclose()


# ── Replies ─────────────────────────────────────────────────────────────────

async def reply(
    cfg: MetaConfig, *, platform: str, external_id: str, token: str,
    kind: str, target_external_id: str, author_external_id: Optional[str], text: str,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Answer a comment (threaded under it) or a message (as a DM). Returns the
    network's id for what was sent."""
    body = (text or "").strip()
    if not body:
        raise ProviderError("Nothing to send", retryable=False)
    if kind == "comment":
        if platform == "instagram":
            out = await call(cfg, "POST", f"{target_external_id}/replies", token=token,
                             data={"message": body}, client=client)
        else:
            out = await call(cfg, "POST", f"{target_external_id}/comments", token=token,
                             data={"message": body}, client=client)
    elif kind == "message":
        if not author_external_id:
            raise ProviderError("No recipient for this message", retryable=False)
        payload = {
            "recipient": json.dumps({"id": author_external_id}),
            "message": json.dumps({"text": body}),
            "messaging_type": "RESPONSE",
        }
        # `me` with a Page token is the Page; the same send reaches Messenger
        # and Instagram DMs (Instagram messaging rides the Page).
        out = await call(cfg, "POST", "me/messages", token=token, data=payload, client=client)
    else:
        raise ProviderError(f"Unknown inbox kind {kind!r}", retryable=False)
    sent_id = out.get("id") or out.get("message_id")
    if not sent_id:
        raise ProviderError("Meta accepted the reply but returned no id", retryable=False)
    return str(sent_id)


# ── Metrics ─────────────────────────────────────────────────────────────────

async def account_metrics(cfg: MetaConfig, *, platform: str, external_id: str, token: str, client=None) -> dict[str, Any]:
    """`{"followers_count": n, ...}` for a connection."""
    if platform == "instagram":
        out = await call(cfg, "GET", external_id, token=token,
                         params={"fields": "followers_count,media_count"}, client=client)
        return {k: out[k] for k in ("followers_count", "media_count") if isinstance(out.get(k), int)}
    out = await call(cfg, "GET", external_id, token=token, params={"fields": "followers_count,fan_count"}, client=client)
    metrics: dict[str, Any] = {}
    followers = out.get("followers_count", out.get("fan_count"))
    if isinstance(followers, int):
        metrics["followers_count"] = followers
    return metrics


def _insight_value(row: dict[str, Any]) -> Any:
    """An insights row's number: `values[0].value`, or `total_value.value` on
    the newer metrics that report a total."""
    values = row.get("values")
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return values[0].get("value")
    total = row.get("total_value")
    return total.get("value") if isinstance(total, dict) else None


async def post_metrics(cfg: MetaConfig, *, platform: str, external_post_id: str, token: str, client=None) -> dict[str, Any]:
    """Likes / comments / reach for one published post, as far as the network
    reports them."""
    if platform == "instagram":
        out = await call(cfg, "GET", f"{external_post_id}/insights", token=token,
                         params={"metric": "reach,likes,comments,saved,shares"}, client=client)
        metrics: dict[str, Any] = {}
        for row in out.get("data") or []:
            if isinstance(row, dict) and row.get("name"):
                value = _insight_value(row)
                if isinstance(value, int):
                    metrics[str(row["name"])] = value
        return metrics
    out = await call(cfg, "GET", external_post_id, token=token, params={
        "fields": "likes.summary(true).limit(0),comments.summary(true).limit(0),shares",
    }, client=client)
    metrics = {}
    likes = ((out.get("likes") or {}).get("summary") or {}).get("total_count")
    comments = ((out.get("comments") or {}).get("summary") or {}).get("total_count")
    shares = (out.get("shares") or {}).get("count")
    for name, value in (("likes", likes), ("comments", comments), ("shares", shares)):
        if isinstance(value, int):
            metrics[name] = value
    return metrics


# ── Webhooks ────────────────────────────────────────────────────────────────

def verify_challenge(cfg: MetaConfig, params: dict[str, str]) -> Optional[str]:
    """The subscription handshake: echo `hub.challenge` only for our verify
    token."""
    if not cfg.verify_token:
        return None
    if params.get("hub.mode") != "subscribe":
        return None
    if not hmac.compare_digest(str(params.get("hub.verify_token") or ""), cfg.verify_token):
        return None
    return params.get("hub.challenge")


def verify_signature(app_secret: str, body: bytes, header: Optional[str]) -> bool:
    """`X-Hub-Signature-256: sha256=<hmac of the raw body with the app secret>`."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[len("sha256="):].strip(), expected)


def _ts(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("+0000", "+00:00"))
        except ValueError:
            return None
    return None


def _messaging_events(platform: str, entry_id: str, entry: dict) -> list[InboundEvent]:
    events: list[InboundEvent] = []
    for msg in entry.get("messaging") or []:
        if not isinstance(msg, dict):
            continue
        message = msg.get("message") or {}
        if not isinstance(message, dict) or message.get("is_echo"):
            continue
        text = str(message.get("text") or "").strip()
        mid = message.get("mid")
        if not (text and mid):
            continue
        sender = (msg.get("sender") or {}).get("id")
        if sender and str(sender) == entry_id:
            continue  # our own side of the conversation
        events.append(InboundEvent(
            platform=platform, recipient_external_id=entry_id, kind="message",
            external_id=str(mid), text=text, parent_external_id=str(sender) if sender else None,
            author_external_id=str(sender) if sender else None, author_name=None,
            received_at=_ts(msg.get("timestamp")), raw=msg,
        ))
    return events


def parse_webhook(payload: dict[str, Any]) -> list[InboundEvent]:
    """Every comment or message in a webhook body, our own activity left out."""
    events: list[InboundEvent] = []
    obj = payload.get("object")
    if obj not in ("instagram", "page"):
        return events
    platform = "instagram" if obj == "instagram" else "facebook"
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            field = change.get("field")
            if platform == "instagram" and field == "comments":
                author = value.get("from") or {}
                author_id = str(author.get("id")) if author.get("id") else None
                if author_id == entry_id:
                    continue
                text = str(value.get("text") or "").strip()
                comment_id = value.get("id")
                if not (text and comment_id):
                    continue
                events.append(InboundEvent(
                    platform=platform, recipient_external_id=entry_id, kind="comment",
                    external_id=str(comment_id), text=text,
                    parent_external_id=str((value.get("media") or {}).get("id") or "") or None,
                    author_external_id=author_id, author_name=author.get("username"),
                    received_at=_ts(entry.get("time")), raw=value,
                ))
            elif platform == "facebook" and field == "feed":
                if value.get("item") != "comment" or value.get("verb") != "add":
                    continue
                author = value.get("from") or {}
                author_id = str(author.get("id")) if author.get("id") else None
                if author_id == entry_id:
                    continue
                text = str(value.get("message") or "").strip()
                comment_id = value.get("comment_id")
                if not (text and comment_id):
                    continue
                events.append(InboundEvent(
                    platform=platform, recipient_external_id=entry_id, kind="comment",
                    external_id=str(comment_id), text=text,
                    parent_external_id=str(value.get("post_id") or "") or None,
                    author_external_id=author_id, author_name=author.get("name"),
                    received_at=_ts(value.get("created_time")), raw=value,
                ))
        events.extend(_messaging_events(platform, entry_id, entry))
    return events


__all__ = [
    "MetaConfig", "SCOPES", "REQUIRED_SCOPES", "MAYBE_POSTED", "configured", "call", "authorize_url",
    "granted_scopes", "missing_scopes", "exchange_code", "subscribe_page",
    "publish", "reply", "account_metrics", "post_metrics",
    "verify_challenge", "verify_signature", "parse_webhook",
]
