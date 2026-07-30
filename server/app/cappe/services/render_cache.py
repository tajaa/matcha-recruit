"""Redis-side half of the rendered-HTML cache invalidation.

`routes/render.py:invalidate_render_cache` is the historical entry point (10+
existing callers: owner CRUD, publish, delete) and also resets `_host_cache`,
a process-local dict that lives in that route module — so it stays the public
name and now just delegates the Redis part here.

This module exists so a services/ caller (`services/merlin/setup_agent.py`'s
chat-confirmed staged-action execute) can invalidate the Redis cache without
importing routes/ — services/ must never import routes/. It intentionally
does NOT touch `_host_cache`: that cache only affects custom-domain HOST
lookups, not rendered page content, and a setup-concierge action never
changes a site's subdomain/custom_domain.
"""
from ...core.services.redis_cache import cache_delete_pattern, get_redis_cache


async def invalidate_site_render_cache(site_id) -> None:
    """Drop cached rendered HTML for a site."""
    redis = get_redis_cache()
    if redis:
        await cache_delete_pattern(redis, f"cappe:render:{site_id}:")
