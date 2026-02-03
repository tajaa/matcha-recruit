"""
Gemini API Rate Limiter

Database-backed rate limiter to prevent runaway Gemini API costs.
Uses rolling windows for hourly and daily limits.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from ...database import get_connection


class RateLimitExceeded(Exception):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, limit_type: str, current_count: int, limit: int):
        super().__init__(message)
        self.limit_type = limit_type  # "hourly" or "daily"
        self.current_count = current_count
        self.limit = limit


class GeminiRateLimiter:
    """
    Database-backed rate limiter for Gemini API calls.

    Enforces two rolling window limits:
    - hourly_limit: Max calls in any 1-hour window
    - daily_limit: Max calls in any 24-hour window
    """

    def __init__(self):
        from ...config import get_settings
        settings = get_settings()
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

            # Count calls in the last hour
            hourly_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1",
                one_hour_ago,
            )

            # Count calls in the last 24 hours
            daily_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1",
                one_day_ago,
            )

            # Check limits
            if hourly_count >= self.hourly_limit:
                print(f"[RateLimiter] BLOCKED {service_name}/{endpoint}: hourly limit ({hourly_count}/{self.hourly_limit})")
                raise RateLimitExceeded(
                    f"Gemini API hourly limit exceeded ({hourly_count}/{self.hourly_limit})",
                    limit_type="hourly",
                    current_count=hourly_count,
                    limit=self.hourly_limit,
                )

            if daily_count >= self.daily_limit:
                print(f"[RateLimiter] BLOCKED {service_name}/{endpoint}: daily limit ({daily_count}/{self.daily_limit})")
                raise RateLimitExceeded(
                    f"Gemini API daily limit exceeded ({daily_count}/{self.daily_limit})",
                    limit_type="daily",
                    current_count=daily_count,
                    limit=self.daily_limit,
                )

    async def record_call(self, service_name: str, endpoint: Optional[str] = None) -> None:
        """
        Record a Gemini API call. Call this after each actual API call (including retries).

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
                INSERT INTO api_rate_limits (service_name, endpoint, called_at)
                VALUES ($1, $2, $3)
                """,
                service_name,
                safe_endpoint,
                now,
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

            # Overall counts
            hourly_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1",
                one_hour_ago,
            )
            daily_count = await conn.fetchval(
                "SELECT COUNT(*) FROM api_rate_limits WHERE called_at > $1",
                one_day_ago,
            )

            # Breakdown by service (last 24h)
            service_breakdown = await conn.fetch(
                """
                SELECT service_name, endpoint, COUNT(*) as count
                FROM api_rate_limits
                WHERE called_at > $1
                GROUP BY service_name, endpoint
                ORDER BY count DESC
                """,
                one_day_ago,
            )

            # Recent calls (last 10)
            recent_calls = await conn.fetch(
                """
                SELECT service_name, endpoint, called_at
                FROM api_rate_limits
                ORDER BY called_at DESC
                LIMIT 10
                """
            )

            # Calculate time until limits reset (rough estimate)
            oldest_in_hour = await conn.fetchval(
                "SELECT MIN(called_at) FROM api_rate_limits WHERE called_at > $1",
                one_hour_ago,
            )
            hourly_reset_at = None
            if oldest_in_hour and hourly_count >= self.hourly_limit:
                hourly_reset_at = (oldest_in_hour + timedelta(hours=1)).isoformat()

            return {
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
_rate_limiter: Optional[GeminiRateLimiter] = None


def get_rate_limiter() -> GeminiRateLimiter:
    """Get the rate limiter singleton instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter
