"""Follower counts and per-post reach, refreshed by `cappe_social_metrics`.

Read-only against the networks. A connection whose token the network now
refuses is marked `expired`, which is what the page shows as "reconnect".
"""
from __future__ import annotations

import json
import logging
from typing import Any

from . import connections as conn_store
from .providers import provider_for
from .providers.base import ProviderError
from .providers.meta import MetaConfig

logger = logging.getLogger(__name__)

RECENT_POST_DAYS = 30
RECENT_POST_LIMIT = 20
# Meta's "invalid OAuth token" family: the token is gone, not the network.
_TOKEN_CODES = frozenset({190, 102})


async def refresh_connection(conn, cfg: MetaConfig, cred: dict[str, Any]) -> dict[str, Any]:
    provider = provider_for(cred["platform"])
    try:
        metrics = await provider.account_metrics(
            cfg, platform=cred["platform"], external_id=cred["external_id"], token=cred["token"],
        )
    except ProviderError as exc:
        # Only a dead token demotes the account. A read-only metrics call
        # failing (a field this Page type lacks, a blip) must not stop
        # publishing and replies, so it is noted and the account stays live.
        if exc.code in _TOKEN_CODES:
            await conn_store.mark_status(conn, cred["id"], "expired", str(exc))
        else:
            await conn_store.mark_status(conn, cred["id"], "connected", str(exc))
        return {"ok": False, "error": str(exc)}
    await conn_store.record_metrics(conn, cred["id"], metrics)
    return {"ok": True, **metrics}


async def refresh_recent_posts(conn, cfg: MetaConfig, cred: dict[str, Any]) -> int:
    provider = provider_for(cred["platform"])
    rows = await conn.fetch(
        f"""SELECT id, external_post_id FROM cappe_social_post_targets
            WHERE connection_id = $1 AND status = 'published' AND external_post_id IS NOT NULL
              AND published_at > NOW() - INTERVAL '{RECENT_POST_DAYS} days'
            ORDER BY published_at DESC LIMIT {RECENT_POST_LIMIT}""",
        cred["id"],
    )
    refreshed = 0
    for row in rows:
        try:
            metrics = await provider.post_metrics(
                cfg, platform=cred["platform"], external_post_id=row["external_post_id"], token=cred["token"],
            )
        except ProviderError as exc:
            logger.info("cappe social metrics: post %s skipped (%s)", row["external_post_id"], exc)
            continue
        await conn.execute(
            "UPDATE cappe_social_post_targets SET metrics = $2::jsonb, metrics_at = NOW() WHERE id = $1",
            row["id"], json.dumps(metrics),
        )
        refreshed += 1
    return refreshed


async def refresh_all(conn, cfg: MetaConfig, *, limit: int) -> dict[str, int]:
    """Oldest-refreshed connections first, so every one gets its turn."""
    rows = await conn.fetch(
        "SELECT id FROM cappe_social_connections WHERE status = 'connected' "
        "ORDER BY metrics_at NULLS FIRST, connected_at LIMIT $1",
        limit,
    )
    accounts = posts = 0
    for row in rows:
        cred = await conn_store.credentials(conn, row["id"])
        if not cred or not cred["token"]:
            continue
        result = await refresh_connection(conn, cfg, cred)
        if result.get("ok"):
            accounts += 1
            posts += await refresh_recent_posts(conn, cfg, cred)
    return {"connections": len(rows), "accounts": accounts, "posts": posts}


__all__ = ["RECENT_POST_DAYS", "RECENT_POST_LIMIT", "refresh_connection", "refresh_recent_posts", "refresh_all"]
