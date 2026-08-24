"""On-demand exact engagement stats for a single Instagram mention via SerpApi's profile API."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx

from ....config import get_settings
from .grounding import instagram_shortcode

_CACHE_WINDOW_HOURS = 24


class StatsError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class ProfileStats:
    liked_by_count: int | None
    comments_count: int | None
    comments_disabled: bool
    followers: int | None
    is_verified: bool
    counts_hidden: bool
    image_url: str | None


async def fetch_profile_posts(handle: str) -> dict:
    """One GET to serpapi.com — engine=instagram_profile. No pagination (1 credit)."""
    settings = get_settings()
    if not settings.serp_api_key:
        raise RuntimeError("SERP_API_KEY is required for shoutout stats.")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                "https://serpapi.com/search",
                params={"engine": "instagram_profile", "profile_id": handle, "api_key": settings.serp_api_key},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StatsError(502, "stats_provider_error", f"Could not reach the stats provider: {error}") from error
    return response.json()


def match_post(payload: dict, shortcode: str) -> ProfileStats | None:
    posts = (payload.get("profile_results") or {}).get("posts")
    if not isinstance(posts, list):
        return None
    for post in posts:
        if not isinstance(post, dict) or post.get("shortcode") != shortcode:
            continue
        followers = (payload.get("profile_results") or {}).get("followers")
        image_url = post.get("serpapi_display_url")
        return ProfileStats(
            liked_by_count=post.get("liked_by_count") if isinstance(post.get("liked_by_count"), int) else None,
            comments_count=post.get("comments_count") if isinstance(post.get("comments_count"), int) else None,
            comments_disabled=bool(post.get("comments_disabled")),
            followers=followers if isinstance(followers, int) else None,
            is_verified=bool((payload.get("profile_results") or {}).get("is_verified")),
            counts_hidden=bool(post.get("like_and_view_counts_disabled")),
            image_url=image_url if isinstance(image_url, str) else None,
        )
    return None


async def fetch_mention_stats(conn, *, brand_id: UUID, mention_id: UUID) -> dict:
    mention = await conn.fetchrow(
        """SELECT platform, canonical_url, author_handle, stats_source, stats_fetched_at
             FROM tellus_shoutout_mentions WHERE id=$1 AND brand_id=$2""",
        mention_id, brand_id,
    )
    if mention is None:
        raise StatsError(404, "mention_not_found", "That mention does not exist for this brand.")

    if (
        mention["stats_source"] == "profile_api"
        and mention["stats_fetched_at"] is not None
        and mention["stats_fetched_at"] > datetime.now(timezone.utc) - timedelta(hours=_CACHE_WINDOW_HOURS)
    ):
        return dict(await conn.fetchrow(
            """SELECT like_count, comment_count, author_followers, author_verified,
                      posted_age, image_url, stats_source, stats_status, stats_fetched_at
                 FROM tellus_shoutout_mentions WHERE id=$1""",
            mention_id,
        ))

    shortcode = None
    if mention["platform"] == "instagram" and mention["author_handle"]:
        shortcode = instagram_shortcode(mention["canonical_url"])

    if mention["platform"] != "instagram" or not mention["author_handle"] or shortcode is None:
        await conn.execute(
            "UPDATE tellus_shoutout_mentions SET stats_status='unsupported' WHERE id=$1", mention_id,
        )
        return dict(await conn.fetchrow(
            """SELECT like_count, comment_count, author_followers, author_verified,
                      posted_age, image_url, stats_source, stats_status, stats_fetched_at
                 FROM tellus_shoutout_mentions WHERE id=$1""",
            mention_id,
        ))

    payload = await fetch_profile_posts(mention["author_handle"])
    stats = match_post(payload, shortcode)

    if stats is None:
        await conn.execute(
            "UPDATE tellus_shoutout_mentions SET stats_status='not_found' WHERE id=$1", mention_id,
        )
    else:
        like_count = None if stats.counts_hidden else stats.liked_by_count
        comment_count = None if (stats.counts_hidden or stats.comments_disabled) else stats.comments_count
        await conn.execute(
            """UPDATE tellus_shoutout_mentions
                  SET like_count=$2, comment_count=$3, author_followers=$4, author_verified=$5, image_url=$6,
                      stats_source='profile_api', stats_fetched_at=NOW(), stats_status='ok'
                WHERE id=$1""",
            mention_id, like_count, comment_count, stats.followers, stats.is_verified, stats.image_url,
        )

    return dict(await conn.fetchrow(
        """SELECT like_count, comment_count, author_followers, author_verified,
                  posted_age, image_url, stats_source, stats_status, stats_fetched_at
             FROM tellus_shoutout_mentions WHERE id=$1""",
        mention_id,
    ))
