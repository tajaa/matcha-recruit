"""
AI API rate limiter

Database-backed rate limiter to prevent runaway model spend. Rolling hourly and
daily windows, counted **per provider**.

The per-provider part is not cosmetic. Until 2026-09 this counted every row in
`api_rate_limits` with no filter and compared the total against the Gemini
limits — so once the Huume and Espresso loops moved to OpenAI (2026-08-25)
their calls spent the Gemini allowance, and a Gemini-heavy compliance sweep
could 429 a Huume turn. Each provider now has its own bucket and its own
configured ceiling.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

# connection_or_direct, not get_connection: EVERY Gemini call in the codebase
# passes through this limiter, including calls made from Celery tasks — and
# workers are pool-free by design (celery_app.py), so a hard `get_connection()`
# here meant no worker could ever call Gemini. It raised in check_limit, before
# the API call, and looked like a research pass that simply found nothing.
from ...database import connection_or_direct as get_connection


class RateLimitExceeded(Exception):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, limit_type: str, current_count: int, limit: int):
        super().__init__(message)
        self.limit_type = limit_type  # "hourly" or "daily"
        self.current_count = current_count
        self.limit = limit


class ApiRateLimiter:
    """
    Database-backed rate limiter for model API calls.

    Enforces two rolling window limits, within one provider's bucket:
    - hourly_limit: Max calls in any 1-hour window
    - daily_limit: Max calls in any 24-hour window

    `provider` defaults to "gemini" so every existing caller keeps the exact
    limits and the exact rows it had; OpenAI callers pass `provider="openai"`
    and get their own ceiling from `openai_hourly_limit`/`openai_daily_limit`.
    """

    def __init__(self, provider: str = "gemini"):
        from ...config import get_settings
        settings = get_settings()
        self.provider = provider
        if provider == "openai":
            self.hourly_limit = settings.openai_hourly_limit
            self.daily_limit = settings.openai_daily_limit
        else:
            self.hourly_limit = settings.gemini_hourly_limit
            self.daily_limit = settings.gemini_daily_limit

    async def check_limit(self, service_name: str, endpoint: Optional[str] = None) -> None:
        """
        Check if rate limit allows another call. Raises RateLimitExceeded if over limit.
        Does NOT record the call - use record_call() after the actual API call succeeds.

        Args:
            service_name: Name of the calling service (for logging)
            endpoint: Optional endpoint/operation label (for logging)

        Raises:
            RateLimitExceeded: If hourly or daily limit is exceeded
        """
        async with get_connection() as conn:
            now = datetime.now(timezone.utc)
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(hours=24)

            # Scoped to this provider: another provider's traffic must not
            # consume this one's allowance, in either direction.
            hourly_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1 AND provider = $2",
                one_hour_ago, self.provider,
            )
            daily_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1 AND provider = $2",
                one_day_ago, self.provider,
            )

            # Check limits
            if hourly_count >= self.hourly_limit:
                print(f"[RateLimiter] BLOCKED {service_name}/{endpoint}: hourly limit ({hourly_count}/{self.hourly_limit})")
                raise RateLimitExceeded(
                    f"{self.provider} API hourly limit exceeded ({hourly_count}/{self.hourly_limit})",
                    limit_type="hourly",
                    current_count=hourly_count,
                    limit=self.hourly_limit,
                )

            if daily_count >= self.daily_limit:
                print(f"[RateLimiter] BLOCKED {service_name}/{endpoint}: daily limit ({daily_count}/{self.daily_limit})")
                raise RateLimitExceeded(
                    f"{self.provider} API daily limit exceeded ({daily_count}/{self.daily_limit})",
                    limit_type="daily",
                    current_count=daily_count,
                    limit=self.daily_limit,
                )

    async def record_call(self, service_name: str, endpoint: Optional[str] = None) -> None:
        """
        Record one API call in this limiter's provider bucket. Call this after
        each actual API call (including retries).

        Args:
            service_name: Name of the calling service (e.g., "gemini_compliance")
            endpoint: Optional endpoint/operation label for monitoring
        """
        async with get_connection() as conn:
            now = datetime.now(timezone.utc)
            # Truncate endpoint to fit VARCHAR(100)
            safe_endpoint = endpoint[:100] if endpoint else None
            await conn.execute(
                """
                INSERT INTO api_rate_limits (service_name, endpoint, called_at, provider)
                VALUES ($1, $2, $3, $4)
                """,
                service_name,
                safe_endpoint,
                now,
                self.provider,
            )
            print(f"[RateLimiter] Recorded {service_name}/{safe_endpoint}")

    async def check_and_record(self, service_name: str, endpoint: Optional[str] = None) -> None:
        """
        Check limits and record the call. For single-call operations (no retries).
        For retry loops, use check_limit() before the loop and record_call() inside.

        Args:
            service_name: Name of the calling service
            endpoint: Optional endpoint/operation label

        Raises:
            RateLimitExceeded: If hourly or daily limit is exceeded
        """
        await self.check_limit(service_name, endpoint)
        await self.record_call(service_name, endpoint)

    async def get_usage(self) -> dict:
        """
        Return current usage stats for monitoring.

        Returns:
            Dict with hourly/daily counts, limits, and recent call breakdown by service.
        """
        async with get_connection() as conn:
            now = datetime.now(timezone.utc)
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(hours=24)

            # This bucket's counts — the numbers shown next to this bucket's
            # limits, so they must be scoped the same way check_limit is.
            hourly_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1 AND provider = $2",
                one_hour_ago, self.provider,
            )
            daily_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1 AND provider = $2",
                one_day_ago, self.provider,
            )

            # Breakdown by service (last 24h)
            service_breakdown = await conn.fetch(
                """
                SELECT service_name, endpoint, COUNT(*) as count
                FROM api_rate_limits
                WHERE called_at > $1 AND provider = $2
                GROUP BY service_name, endpoint
                ORDER BY count DESC
                """,
                one_day_ago, self.provider,
            )

            # Recent calls (last 10)
            recent_calls = await conn.fetch(
                """
                SELECT service_name, endpoint, called_at
                FROM api_rate_limits
                WHERE provider = $1
                ORDER BY called_at DESC
                LIMIT 10
                """,
                self.provider,
            )

            # Calculate time until limits reset (rough estimate)
            oldest_in_hour = await conn.fetchval(
                "SELECT MIN(called_at) FROM api_rate_limits WHERE called_at > $1 AND provider = $2",
                one_hour_ago, self.provider,
            )
            hourly_reset_at = None
            if oldest_in_hour and hourly_count >= self.hourly_limit:
                hourly_reset_at = (oldest_in_hour + timedelta(hours=1)).isoformat()

            return {
                "provider": self.provider,
                "hourly": {
                    "count": hourly_count,
                    "limit": self.hourly_limit,
                    "remaining": max(0, self.hourly_limit - hourly_count),
                    "reset_at": hourly_reset_at,
                },
                "daily": {
                    "count": daily_count,
                    "limit": self.daily_limit,
                    "remaining": max(0, self.daily_limit - daily_count),
                },
                "by_service": [
                    {
                        "service": row["service_name"],
                        "endpoint": row["endpoint"],
                        "count": row["count"],
                    }
                    for row in service_breakdown
                ],
                "recent_calls": [
                    {
                        "service": row["service_name"],
                        "endpoint": row["endpoint"],
                        "called_at": row["called_at"].isoformat() if row["called_at"] else None,
                    }
                    for row in recent_calls
                ],
                "checked_at": now.isoformat(),
            }

    async def cleanup_old_records(self, days: int = 7) -> int:
        """
        Delete records older than the specified number of days.

        Args:
            days: Number of days to keep (default 7)

        Returns:
            Number of records deleted
        """
        async with get_connection() as conn:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            result = await conn.execute(
                "DELETE FROM api_rate_limits WHERE called_at < $1",
                cutoff,
            )
            # Extract count from result string like "DELETE 42"
            deleted = int(result.split()[-1]) if result else 0
            if deleted > 0:
                print(f"[RateLimiter] Cleaned up {deleted} old records")
            return deleted


# Singleton instance
_rate_limiters: dict[str, ApiRateLimiter] = {}


def get_rate_limiter(provider: str = "gemini") -> ApiRateLimiter:
    """Get the rate limiter singleton for one provider's bucket."""
    limiter = _rate_limiters.get(provider)
    if limiter is None:
        limiter = _rate_limiters[provider] = ApiRateLimiter(provider)
    return limiter
