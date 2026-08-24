"""Shoutout radar configuration and queue reads."""
from uuid import UUID

_COVERAGE = {"instagram": "partial", "tiktok": "poor", "youtube": "good", "facebook": "partial", "x": "good"}


async def get_config(conn, brand_id: UUID) -> dict:
    row = await conn.fetchrow("SELECT * FROM tellus_shoutout_configs WHERE brand_id = $1", brand_id)
    config = dict(row) if row else {
        "is_enabled": False, "brand_terms": [], "exclude_terms": [], "default_store_id": None,
        "offer_title": None, "offer_terms": None, "offer_expiry_days": 14, "min_confidence": 60,
        "lookback_days": 14, "require_app_install": False, "last_scanned_at": None, "next_scan_after": None,
    }
    handles = await conn.fetch(
        "SELECT platform, handle FROM tellus_shoutout_handles WHERE brand_id = $1 ORDER BY platform, handle", brand_id,
    )
    return {**config, "handles": [dict(row) for row in handles], "platform_coverage": _COVERAGE}


async def put_config(conn, brand_id: UUID, data) -> dict:
    if data.default_store_id is not None:
        store = await conn.fetchval(
            "SELECT 1 FROM tellus_stores WHERE id = $1 AND brand_id = $2", data.default_store_id, brand_id,
        )
        if not store:
            raise ValueError("default_store_id must belong to this business")
    current = await conn.fetchrow(
        "SELECT is_enabled FROM tellus_shoutout_configs WHERE brand_id = $1", brand_id,
    )
    if current and current["is_enabled"] and (data.default_store_id is None or not data.offer_title):
        raise ValueError("An enabled radar requires a default store and offer title")
    async with conn.transaction():
        await conn.execute(
            """INSERT INTO tellus_shoutout_configs
                   (brand_id, brand_terms, exclude_terms, default_store_id, offer_title, offer_terms,
                    offer_expiry_days, min_confidence, lookback_days, require_app_install)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (brand_id) DO UPDATE SET brand_terms=EXCLUDED.brand_terms,
                    exclude_terms=EXCLUDED.exclude_terms, default_store_id=EXCLUDED.default_store_id,
                    offer_title=EXCLUDED.offer_title, offer_terms=EXCLUDED.offer_terms,
                    offer_expiry_days=EXCLUDED.offer_expiry_days, min_confidence=EXCLUDED.min_confidence,
                    lookback_days=EXCLUDED.lookback_days, require_app_install=EXCLUDED.require_app_install,
                    updated_at=NOW()""",
            brand_id, data.brand_terms, data.exclude_terms, data.default_store_id, data.offer_title,
            data.offer_terms, data.offer_expiry_days, data.min_confidence, data.lookback_days,
            data.require_app_install,
        )
        await conn.execute("DELETE FROM tellus_shoutout_handles WHERE brand_id = $1", brand_id)
        seen_handles: set[tuple[str, str]] = set()
        for handle in data.handles:
            key = (handle.platform, handle.handle)
            if key in seen_handles:
                continue
            seen_handles.add(key)
            await conn.execute(
                "INSERT INTO tellus_shoutout_handles (brand_id, platform, handle) VALUES ($1,$2,$3)",
                brand_id, handle.platform, handle.handle,
            )
    return await get_config(conn, brand_id)


async def set_enabled(conn, brand_id: UUID, enabled: bool) -> dict:
    if enabled:
        config = await conn.fetchrow(
            "SELECT default_store_id, offer_title FROM tellus_shoutout_configs WHERE brand_id = $1", brand_id,
        )
        if config is None:
            raise ValueError("Save the radar configuration before enabling it")
        if config["default_store_id"] is None or not config["offer_title"]:
            raise ValueError("Choose a default store and offer title before enabling the radar")
    row = await conn.fetchrow(
        """UPDATE tellus_shoutout_configs SET is_enabled = $2, updated_at = NOW()
           WHERE brand_id = $1 RETURNING brand_id""", brand_id, enabled,
    )
    if row is None:
        raise ValueError("Save the radar configuration before enabling it")
    return await get_config(conn, brand_id)


async def list_mentions(conn, brand_id: UUID, status: str | None) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, platform, post_url, author_handle, excerpt, confidence, matched_terms,
                  corroborated, COALESCE(raw_payload->>'source', '') = 'brand_test' AS is_test,
                  status, seen_count, first_seen_at, last_seen_at, decided_at,
                  like_count, comment_count, author_followers, author_verified, posted_age, image_url,
                  stats_source, stats_status, stats_fetched_at
             FROM tellus_shoutout_mentions WHERE brand_id = $1 AND ($2::text IS NULL OR status = $2)
             ORDER BY last_seen_at DESC""", brand_id, status,
    )
    return [dict(row) for row in rows]


async def list_runs(conn, brand_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM tellus_shoutout_scan_runs WHERE brand_id = $1 ORDER BY started_at DESC LIMIT 50", brand_id,
    )
    return [dict(row) for row in rows]
