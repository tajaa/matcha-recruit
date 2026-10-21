"""Posts and their per-connection targets.

A post is what the owner composed; a target is that post on one connected
account, with its own lifecycle. The publisher works on targets: it claims
the due ones (`FOR UPDATE SKIP LOCKED`, so two sweeps never double-post),
publishes, and records each outcome; the post's status is then rolled up
from its targets. Retries are per target with a short backoff, capped, and
only for failures the provider called retryable.

A video makes two things slower. Before: a scheduled post whose video is
still being cut waits as `rendering` and is never claimed; the render flips
it to `scheduled` (`release_rendered`). During: Meta processes a video for a
minute or more, so the provider returns `Pending` and the target goes back to
`pending` with its `state` (`record_pending`) — a check, not an attempt, so
it doesn't count against the retries.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from ..common import loads, loads_list
from .assets import poster
from .providers.base import Pending, ProviderError, PublishResult

MAX_ATTEMPTS = 3
_BACKOFF = (timedelta(minutes=2), timedelta(minutes=10), timedelta(minutes=30))

POST_COLUMNS = ("id, site_id, caption, media, link_url, product_id, status, scheduled_at, published_at, "
                "ai_meta, created_at, updated_at")
TARGET_COLUMNS = ("t.id, t.post_id, t.connection_id, c.platform, c.handle, t.status, t.external_post_id, "
                  "t.permalink, t.error, t.attempts, t.next_attempt_at, t.published_at, t.metrics, t.state")
# Statuses an owner may still change (edit, reschedule, cancel, delete).
OPEN_STATUSES = ("draft", "scheduled", "rendering", "failed")


def backoff_after(attempts: int) -> timedelta:
    """How long after the `attempts`-th failure the next try waits."""
    return _BACKOFF[min(max(attempts, 1), len(_BACKOFF)) - 1]


def validate_for_targets(caption: str, media: list[dict], platforms: list[str]) -> Optional[str]:
    """Why this post can't go to these platforms, or None. Instagram needs a
    photo or a video; a video goes out on its own (a Reel can't carry
    photos)."""
    videos = [m for m in media if m.get("kind") == "video"]
    if not caption.strip() and not media:
        return "Add a caption, a photo or a video"
    if videos and len(media) > 1:
        return "A video goes out on its own — put the photos in a separate post"
    if "instagram" in platforms and not media:
        return "Instagram posts need a photo or a video"
    return None


def _row_to_post(row) -> dict[str, Any]:
    d = dict(row)
    d["media"] = loads_list(d.get("media")) or []
    d["ai_meta"] = loads(d.get("ai_meta")) or {}
    return d


def _row_to_target(row) -> dict[str, Any]:
    d = dict(row)
    d["metrics"] = loads(d.get("metrics")) or {}
    state = loads(d.pop("state", None)) or {}
    d["phase"] = state.get("phase") if d.get("status") in ("pending", "publishing") else None
    return d


async def create_post(
    conn, *, site_id: UUID, caption: str, media: list[dict], link_url: Optional[str],
    product_id: Optional[UUID], scheduled_at: Optional[datetime], ai_meta: Optional[dict] = None,
) -> dict:
    status = "scheduled" if scheduled_at else "draft"
    row = await conn.fetchrow(
        f"""INSERT INTO cappe_social_posts (site_id, caption, media, link_url, product_id, status, scheduled_at, ai_meta)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8::jsonb)
            RETURNING {POST_COLUMNS}""",
        site_id, caption, json.dumps(media), link_url, product_id, status, scheduled_at, json.dumps(ai_meta or {}),
    )
    post = _row_to_post(row)
    has_video = any(m.get("kind") == "video" for m in media)
    if scheduled_at and has_video and await hold_for_renders(conn, post["id"]):
        post["status"] = "rendering"
    return post


async def set_targets(conn, post_id: UUID, connection_ids: list[UUID], *, due_at: Optional[datetime]) -> None:
    """Replace the post's targets. Rows already published stay; a connection
    dropped from the list is removed only while nothing went out on it."""
    await conn.execute(
        "DELETE FROM cappe_social_post_targets WHERE post_id = $1 AND status IN ('pending', 'cancelled', 'failed') "
        "AND NOT (connection_id = ANY($2::uuid[]))",
        post_id, list(connection_ids),
    )
    for connection_id in connection_ids:
        await conn.execute(
            """INSERT INTO cappe_social_post_targets (post_id, connection_id, status, next_attempt_at)
               VALUES ($1, $2, 'pending', $3)
               ON CONFLICT (post_id, connection_id) DO UPDATE SET
                   status = CASE WHEN cappe_social_post_targets.status IN ('published', 'publishing')
                                 THEN cappe_social_post_targets.status ELSE 'pending' END,
                   next_attempt_at = CASE WHEN cappe_social_post_targets.status IN ('published', 'publishing')
                                          THEN cappe_social_post_targets.next_attempt_at ELSE EXCLUDED.next_attempt_at END,
                   state = CASE WHEN cappe_social_post_targets.status IN ('published', 'publishing')
                                THEN cappe_social_post_targets.state ELSE '{}'::jsonb END,
                   error = NULL, attempts = 0""",
            post_id, connection_id, due_at,
        )


async def attach_posters(conn, posts: list[dict]) -> None:
    """Give each video in these posts its poster frame, for the queue. One
    query, and none at all when there's no video."""
    ids = {m["asset_id"] for p in posts for m in p["media"] if m.get("kind") == "video" and m.get("asset_id")}
    if not ids:
        return
    rows = await conn.fetch("SELECT id, frames FROM cappe_social_assets WHERE id = ANY($1::uuid[])", list(ids))
    frames = {str(r["id"]): {"frames": loads_list(r["frames"]) or []} for r in rows}
    for p in posts:
        for m in p["media"]:
            if m.get("kind") == "video":
                m["poster"] = poster(frames.get(str(m.get("asset_id"))))


async def set_content(conn, post_id: UUID, by_platform: dict[str, dict[str, Any]]) -> None:
    """Each network's own copy for this post (`{"text", "link_url"}`), on
    its targets. A target with none uses the post's caption and link."""
    for platform, content in by_platform.items():
        await conn.execute(
            """UPDATE cappe_social_post_targets t SET content = $3::jsonb
               FROM cappe_social_connections c
               WHERE t.post_id = $1 AND c.id = t.connection_id AND c.platform = $2""",
            post_id, platform, json.dumps(content),
        )


async def get_post(conn, site_id: UUID, post_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {POST_COLUMNS} FROM cappe_social_posts WHERE id = $1 AND site_id = $2", post_id, site_id,
    )
    if row is None:
        return None
    post = _row_to_post(row)
    post["targets"] = await targets_for(conn, [post["id"]])
    await attach_posters(conn, [post])
    return post


async def targets_for(conn, post_ids: list[UUID]) -> list[dict]:
    if not post_ids:
        return []
    rows = await conn.fetch(
        f"""SELECT {TARGET_COLUMNS} FROM cappe_social_post_targets t
            JOIN cappe_social_connections c ON c.id = t.connection_id
            WHERE t.post_id = ANY($1::uuid[]) ORDER BY c.platform, c.handle""",
        list(post_ids),
    )
    return [_row_to_target(r) for r in rows]


async def list_posts(conn, site_id: UUID, *, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """Newest-scheduled first: the queue reads top-down as "what goes next"."""
    rows = await conn.fetch(
        f"""SELECT {POST_COLUMNS} FROM cappe_social_posts
            WHERE site_id = $1 AND ($2::text IS NULL OR status = $2)
            ORDER BY COALESCE(scheduled_at, created_at) DESC, created_at DESC
            LIMIT $3 OFFSET $4""",
        site_id, status, limit, offset,
    )
    posts = [_row_to_post(r) for r in rows]
    targets = await targets_for(conn, [p["id"] for p in posts])
    by_post: dict[Any, list[dict]] = {}
    for t in targets:
        by_post.setdefault(t["post_id"], []).append(t)
    for p in posts:
        p["targets"] = by_post.get(p["id"], [])
    await attach_posters(conn, posts)
    return posts


async def update_post(conn, site_id: UUID, post_id: UUID, fields: dict[str, Any]) -> Optional[dict]:
    """Edit a draft or scheduled post. `fields` is already filtered to the
    columns the caller may set; media/ai_meta are JSON-encoded here."""
    if not fields:
        return await get_post(conn, site_id, post_id)
    sets, args = [], [post_id, site_id, list(OPEN_STATUSES)]
    for col, value in fields.items():
        args.append(json.dumps(value) if col in ("media", "ai_meta") else value)
        cast = "::jsonb" if col in ("media", "ai_meta") else ""
        sets.append(f"{col} = ${len(args)}{cast}")
    row = await conn.fetchrow(
        f"""UPDATE cappe_social_posts SET {', '.join(sets)}, updated_at = NOW()
            WHERE id = $1 AND site_id = $2 AND status = ANY($3::text[])
            RETURNING {POST_COLUMNS}""",
        *args,
    )
    if row is None:
        return None
    if "media" in fields:
        # New media may wait on a different video, or none: hold again from
        # scratch, then settle (release, or fail on a broken video).
        await conn.execute(
            "UPDATE cappe_social_posts SET status = 'scheduled' WHERE id = $1 AND status = 'rendering'", post_id,
        )
        await hold_for_renders(conn, post_id)
        await settle_renders(conn, post_ids=[post_id])
    post = _row_to_post(row)
    if "media" in fields:
        post["status"] = await conn.fetchval("SELECT status FROM cappe_social_posts WHERE id = $1", post_id) or post["status"]
    post["targets"] = await targets_for(conn, [post["id"]])
    return post


async def set_schedule(conn, site_id: UUID, post_id: UUID, when: Optional[datetime], *, retry: bool = False) -> bool:
    """`when` in the future → scheduled; None → back to draft. Targets follow;
    a published target never does, so nothing goes out twice. `retry` also
    takes a `partial` post (one network took it, another didn't) and re-tries
    just the targets that didn't go out."""
    status = "scheduled" if when else "draft"
    allowed = list(OPEN_STATUSES) + (["partial"] if retry else [])
    row = await conn.fetchrow(
        """UPDATE cappe_social_posts SET status = $3, scheduled_at = $4, updated_at = NOW()
           WHERE id = $1 AND site_id = $2 AND status = ANY($5::text[])
           RETURNING id""",
        post_id, site_id, status, when, allowed,
    )
    if row is None:
        return False
    await conn.execute(
        "UPDATE cappe_social_post_targets SET status = 'pending', next_attempt_at = $2, error = NULL, attempts = 0, "
        "state = '{}'::jsonb WHERE post_id = $1 AND status IN ('pending', 'failed', 'cancelled')",
        post_id, when,
    )
    if when:
        # A retry of a post whose video failed (or is gone) fails again with
        # the reason instead of waiting on a render nobody will run.
        if await hold_for_renders(conn, post_id):
            await settle_renders(conn, post_ids=[post_id])
    return True


async def publish_now(conn, site_id: UUID, post_id: UUID) -> bool:
    now = datetime.now(timezone.utc)
    return await set_schedule(conn, site_id, post_id, now, retry=True)


async def cancel_post(conn, site_id: UUID, post_id: UUID) -> bool:
    row = await conn.fetchrow(
        """UPDATE cappe_social_posts SET status = 'cancelled', updated_at = NOW()
           WHERE id = $1 AND site_id = $2 AND status = ANY($3::text[])
           RETURNING id""",
        post_id, site_id, list(OPEN_STATUSES),
    )
    if row is None:
        return False
    await conn.execute(
        "UPDATE cappe_social_post_targets SET status = 'cancelled' WHERE post_id = $1 AND status = 'pending'",
        post_id,
    )
    return True


async def delete_post(conn, site_id: UUID, post_id: UUID) -> bool:
    """Only a post that never went out. A published one stays as the record
    of what was posted where."""
    row = await conn.fetchrow(
        "DELETE FROM cappe_social_posts WHERE id = $1 AND site_id = $2 "
        "AND status = ANY($3::text[]) RETURNING id",
        post_id, site_id, [*OPEN_STATUSES, "cancelled"],
    )
    return row is not None


# ── the publisher's side ────────────────────────────────────────────────────

async def claim_due_targets(conn, limit: int, *, post_id: Optional[UUID | str] = None) -> list[dict]:
    """Take up to `limit` targets that are due, marking them `publishing` and
    counting the attempt, inside the caller's transaction. SKIP LOCKED keeps a
    concurrent sweep off the same rows. `post_id` narrows to one post ("Post
    now")."""
    rows = await conn.fetch(
        """UPDATE cappe_social_post_targets t SET status = 'publishing', attempts = t.attempts + 1, claimed_at = NOW()
             WHERE t.id IN (
                 SELECT x.id FROM cappe_social_post_targets x
                 JOIN cappe_social_posts p ON p.id = x.post_id
                 WHERE x.status = 'pending' AND x.next_attempt_at IS NOT NULL AND x.next_attempt_at <= NOW()
                   AND p.status IN ('scheduled', 'publishing', 'partial', 'failed')
                   AND ($2::uuid IS NULL OR p.id = $2::uuid)
                 ORDER BY x.next_attempt_at
                 LIMIT $1 FOR UPDATE SKIP LOCKED)
             RETURNING t.id, t.post_id, t.connection_id, t.attempts, t.state, t.content""",
        limit, UUID(str(post_id)) if post_id else None,
    )
    claimed = [{**dict(r), "state": loads(r["state"]) if "state" in r.keys() else {},
                "content": loads(r["content"]) if "content" in r.keys() else {}} for r in rows]
    if claimed:
        await conn.execute(
            "UPDATE cappe_social_posts SET status = 'publishing', updated_at = NOW() "
            "WHERE id = ANY($1::uuid[]) AND status = 'scheduled'",
            list({c["post_id"] for c in claimed}),
        )
    return claimed


async def record_success(conn, target_id: UUID, result: PublishResult) -> None:
    await conn.execute(
        """UPDATE cappe_social_post_targets SET status = 'published', external_post_id = $2, permalink = $3,
                  error = NULL, published_at = NOW(), next_attempt_at = NULL, state = '{}'::jsonb WHERE id = $1""",
        target_id, result.external_post_id, result.permalink,
    )


async def record_failure(conn, target_id: UUID, attempts: int, error: ProviderError | Exception) -> str:
    """Schedule another try or fail the target for good. Returns the status
    it ended in."""
    retryable = isinstance(error, ProviderError) and error.retryable
    message = str(error)[:500]
    if retryable and attempts < MAX_ATTEMPTS:
        await conn.execute(
            "UPDATE cappe_social_post_targets SET status = 'pending', error = $2, next_attempt_at = NOW() + $3::interval "
            "WHERE id = $1",
            target_id, message, backoff_after(attempts),
        )
        return "pending"
    await conn.execute(
        "UPDATE cappe_social_post_targets SET status = 'failed', error = $2, next_attempt_at = NULL, "
        "state = '{}'::jsonb WHERE id = $1",
        target_id, message,
    )
    return "failed"


async def record_pending(conn, target_id: UUID, pending: Pending) -> None:
    """The network is still working on it: keep where it got to and look
    again later. Hands back the attempt the claim counted — a check isn't a
    try."""
    state = {**pending.state, "phase": pending.phase}
    await conn.execute(
        """UPDATE cappe_social_post_targets SET status = 'pending', state = $2::jsonb, error = NULL,
                  attempts = GREATEST(attempts - 1, 0), next_attempt_at = NOW() + make_interval(secs => $3)
           WHERE id = $1""",
        target_id, json.dumps(state), max(5, int(pending.retry_after_s)),
    )


INTERRUPTED = ("Publishing was interrupted, so it may have gone out. Check the account before you retry, "
               "or it may post twice.")


async def recover_stale_claims(conn, older_than_minutes: int = 20) -> list[UUID]:
    """Targets a killed worker left `publishing` go back to `pending` when
    they carry a handle to resume from (`state`: a video already handed to
    Meta is checked on, not uploaded again). One with no handle may already
    have gone out — the network took it and the worker died before saying
    so — so it fails with that said rather than being posted twice; the
    owner checks and retries. Returns the posts touched."""
    rows = await conn.fetch(
        """UPDATE cappe_social_post_targets SET
                  status = CASE WHEN attempts >= $2 OR state = '{}'::jsonb THEN 'failed' ELSE 'pending' END,
                  error = CASE WHEN attempts >= $2 THEN 'Publishing was interrupted too many times'
                               WHEN state = '{}'::jsonb THEN $3 ELSE error END,
                  next_attempt_at = CASE WHEN attempts >= $2 OR state = '{}'::jsonb THEN NULL ELSE NOW() END
           WHERE status = 'publishing' AND claimed_at < NOW() - make_interval(mins => $1)
           RETURNING post_id""",
        older_than_minutes, MAX_ATTEMPTS, INTERRUPTED,
    )
    return list({r["post_id"] for r in rows})


# ── posts waiting on a video ────────────────────────────────────────────────

_PENDING_RENDER = """EXISTS (
    SELECT 1 FROM jsonb_array_elements(p.media) item
    LEFT JOIN cappe_social_assets a ON a.id = (item->>'asset_id')::uuid
    WHERE item->>'kind' = 'video' AND (a.id IS NULL OR a.status <> 'ready'))"""


async def hold_for_renders(conn, post_id: UUID) -> bool:
    """A scheduled post whose video isn't cut yet waits as `rendering`."""
    row = await conn.fetchrow(
        f"""UPDATE cappe_social_posts p SET status = 'rendering', updated_at = NOW()
            WHERE p.id = $1 AND p.status = 'scheduled' AND {_PENDING_RENDER}
            RETURNING p.id""",
        post_id,
    )
    return row is not None


async def release_rendered(conn, asset_id: UUID) -> list[dict[str, Any]]:
    """Posts that were waiting only on this video go back to `scheduled`.
    Returns them (id, scheduled_at) so the caller can publish the overdue
    ones right away."""
    rows = await conn.fetch(
        f"""UPDATE cappe_social_posts p SET status = 'scheduled', updated_at = NOW()
            WHERE p.status = 'rendering'
              AND p.media @> jsonb_build_array(jsonb_build_object('asset_id', $1::text))
              AND NOT {_PENDING_RENDER}
            RETURNING p.id, p.scheduled_at""",
        str(asset_id),
    )
    return [dict(r) for r in rows]


_BROKEN_RENDER = """EXISTS (
    SELECT 1 FROM jsonb_array_elements(p.media) item
    LEFT JOIN cappe_social_assets a ON a.id = (item->>'asset_id')::uuid
    WHERE item->>'kind' = 'video' AND (a.id IS NULL OR a.status IN ('failed', 'deleted')))"""
BROKEN_VIDEO = "Video: the video couldn't be prepared or is gone. Upload it again."


async def settle_renders(conn, *, post_ids: Optional[list[UUID]] = None, limit: int = 200) -> dict[str, list]:
    """Put `rendering` posts right from their videos' current state, not
    from the event that should have moved them: every video ready →
    `scheduled` (returned with `scheduled_at` so the caller can publish the
    overdue ones); any video failed or gone → `failed`. The media sweep runs
    this over everything, so a post held a moment after its render finished,
    or one whose video failed while it was a draft, never waits for good."""
    scope = "AND p.id = ANY($2::uuid[])" if post_ids is not None else ""
    args: list[Any] = [limit] + ([list(post_ids)] if post_ids is not None else [])
    failed = await conn.fetch(
        f"""UPDATE cappe_social_posts p SET status = 'failed', updated_at = NOW()
            WHERE p.id IN (SELECT p.id FROM cappe_social_posts p WHERE p.status = 'rendering' AND {_BROKEN_RENDER}
                           {scope} LIMIT $1)
            RETURNING p.id""",
        *args,
    )
    failed_ids = [r["id"] for r in failed]
    if failed_ids:
        await conn.execute(
            "UPDATE cappe_social_post_targets SET status = 'failed', error = $2, next_attempt_at = NULL "
            "WHERE post_id = ANY($1::uuid[]) AND status = 'pending'",
            failed_ids, BROKEN_VIDEO,
        )
    released = await conn.fetch(
        f"""UPDATE cappe_social_posts p SET status = 'scheduled', updated_at = NOW()
            WHERE p.id IN (SELECT p.id FROM cappe_social_posts p WHERE p.status = 'rendering'
                           AND NOT {_PENDING_RENDER} {scope} LIMIT $1)
            RETURNING p.id, p.scheduled_at""",
        *args,
    )
    return {"released": [dict(r) for r in released], "failed": failed_ids}


async def fail_rendering(conn, asset_id: UUID, error: str) -> list[UUID]:
    """The video couldn't be prepared: the posts waiting on it fail with the
    reason, and nothing of theirs is left to publish."""
    rows = await conn.fetch(
        """UPDATE cappe_social_posts p SET status = 'failed', updated_at = NOW()
           WHERE p.status = 'rendering'
             AND p.media @> jsonb_build_array(jsonb_build_object('asset_id', $1::text))
           RETURNING p.id""",
        str(asset_id),
    )
    post_ids = [r["id"] for r in rows]
    if post_ids:
        await conn.execute(
            "UPDATE cappe_social_post_targets SET status = 'failed', error = $2, next_attempt_at = NULL "
            "WHERE post_id = ANY($1::uuid[]) AND status = 'pending'",
            post_ids, f"Video: {error}"[:500],
        )
    return post_ids


def rollup_status(target_statuses: list[str]) -> str:
    """The post's status from its targets' — pure, so it is testable without
    a database."""
    if not target_statuses:
        return "failed"
    live = [s for s in target_statuses if s != "cancelled"]
    if not live:
        return "cancelled"
    if any(s in ("pending", "publishing") for s in live):
        return "publishing"
    published = sum(1 for s in live if s == "published")
    if published == len(live):
        return "published"
    return "partial" if published else "failed"


async def rollup_post(conn, post_id: UUID) -> str:
    rows = await conn.fetch("SELECT status FROM cappe_social_post_targets WHERE post_id = $1", post_id)
    status = rollup_status([r["status"] for r in rows])
    await conn.execute(
        """UPDATE cappe_social_posts SET status = $2,
                  published_at = CASE WHEN $2 IN ('published', 'partial') THEN COALESCE(published_at, NOW()) ELSE published_at END,
                  updated_at = NOW()
           WHERE id = $1""",
        post_id, status,
    )
    return status


__all__ = [
    "MAX_ATTEMPTS", "OPEN_STATUSES", "INTERRUPTED", "BROKEN_VIDEO", "settle_renders", "backoff_after",
    "validate_for_targets", "create_post", "set_targets", "set_content",
    "attach_posters", "get_post",
    "targets_for", "list_posts", "update_post", "set_schedule", "publish_now", "cancel_post", "delete_post",
    "claim_due_targets", "record_success", "record_failure", "record_pending", "recover_stale_claims",
    "hold_for_renders", "release_rendered", "fail_rendering", "rollup_status", "rollup_post",
]
