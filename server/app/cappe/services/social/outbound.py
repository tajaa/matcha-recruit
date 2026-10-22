"""The two network writes: publish a claimed target, send a reply.

Both load the connection's token here and nowhere else, call the provider,
and record the outcome on the row that was written before the call. A video
is swapped for the cut its network takes (`variants.media_for`), and a
publish Meta is still processing comes back `Pending` and is checked on by a
later sweep.
"""
from __future__ import annotations

import logging
from typing import Any

from ..common import loads, loads_list
from . import assets as asset_store
from . import connections as conn_store
from . import posts as post_store
from . import variants
from .providers import provider_for
from .providers.base import Pending, ProviderError
from .providers.meta import MetaConfig

logger = logging.getLogger(__name__)

# Meta's "invalid OAuth token" family: the connection, not the post, is broken.
_TOKEN_CODES = frozenset({190, 102})


async def publish_target(conn, cfg: MetaConfig, claim: dict[str, Any]) -> str:
    """Publish one claimed target. Returns the status it ended in
    (published / pending / failed) after rolling the post up; `pending`
    also covers a video the network is still processing."""
    target_id, post_id, attempts = claim["id"], claim["post_id"], int(claim.get("attempts") or 1)
    post = await conn.fetchrow(
        "SELECT id, site_id, caption, media, link_url, status FROM cappe_social_posts WHERE id = $1", post_id,
    )
    cred = await conn_store.credentials(conn, claim["connection_id"])
    try:
        if post is None:
            raise ProviderError("Post no longer exists", retryable=False)
        if post["status"] == "cancelled":
            raise ProviderError("Post was cancelled", retryable=False)
        if cred is None or not cred["token"]:
            raise ProviderError("Account is no longer connected", retryable=False)
        if cred["status"] != "connected":
            raise ProviderError(f"Account needs reconnecting ({cred['status']})", retryable=False)
        media = loads_list(post["media"]) or []
        reason = post_store.validate_for_targets(post["caption"] or "", media, [cred["platform"]])
        if reason:
            raise ProviderError(reason, retryable=False)
        video_ids = [m["asset_id"] for m in media if m.get("kind") == "video" and m.get("asset_id")]
        if video_ids:
            media = variants.media_for(cred["platform"], media, await asset_store.load_many(conn, video_ids))
        # The chat composer writes each network its own copy; the form's posts
        # share the post's caption and link.
        content = loads(claim.get("content"))
        result = await provider_for(cred["platform"]).publish(
            cfg, platform=cred["platform"], external_id=cred["external_id"], token=cred["token"],
            caption=content.get("text") or post["caption"] or "", media=media,
            link_url=content.get("link_url") or post["link_url"], state=loads(claim.get("state")),
        )
    except ProviderError as exc:
        if exc.code in _TOKEN_CODES and cred:
            await conn_store.mark_status(conn, cred["id"], "expired", str(exc))
        ended = await post_store.record_failure(conn, target_id, attempts, exc)
        logger.warning("cappe social: target %s %s (%s)", target_id, ended, exc)
    except Exception as exc:  # noqa: BLE001 — never let one bad target stop the sweep
        logger.exception("cappe social: target %s crashed", target_id)
        ended = await post_store.record_failure(conn, target_id, attempts, exc)
    else:
        if isinstance(result, Pending):
            await post_store.record_pending(conn, target_id, result)
            ended = "pending"
        else:
            await post_store.record_success(conn, target_id, result)
            ended = "published"
    await post_store.rollup_post(conn, post_id)
    return ended


async def reply_credentials(conn, item: dict[str, Any]) -> dict[str, Any]:
    """The connection an inbox item is answered from. Raises ProviderError
    when it can't be used."""
    cred = await conn_store.credentials(conn, item["connection_id"])
    if cred is None or not cred["token"]:
        raise ProviderError("Account is no longer connected", retryable=False)
    if cred["status"] != "connected":
        raise ProviderError(f"Account needs reconnecting ({cred['status']})", retryable=False)
    return cred


async def send_with(cfg: MetaConfig, cred: dict[str, Any], item: dict[str, Any], body: str) -> str:
    """The network call alone — no database, so a route can make it without
    holding a pooled connection."""
    return await provider_for(cred["platform"]).reply(
        cfg, platform=cred["platform"], external_id=cred["external_id"], token=cred["token"],
        kind=item["kind"], target_external_id=item["external_id"],
        author_external_id=item.get("author_external_id"), text=body,
    )


async def note_send_failure(conn, cred: dict[str, Any], exc: ProviderError) -> None:
    """A refused token marks the connection for reconnecting."""
    if exc.code in _TOKEN_CODES:
        await conn_store.mark_status(conn, cred["id"], "expired", str(exc))


async def send_reply(conn, cfg: MetaConfig, item: dict[str, Any], body: str) -> str:
    """Send `body` as the answer to an inbox item. Raises ProviderError."""
    cred = await reply_credentials(conn, item)
    try:
        return await send_with(cfg, cred, item, body)
    except ProviderError as exc:
        await note_send_failure(conn, cred, exc)
        raise


__all__ = ["publish_target", "reply_credentials", "send_with", "note_send_failure", "send_reply"]
