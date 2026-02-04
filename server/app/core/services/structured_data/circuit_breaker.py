"""Circuit breaker pattern for Tier 1 structured data sources."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import asyncpg


class CircuitBreaker:
    """
    Circuit breaker for managing source failures.

    When a source fails too many times consecutively, the circuit "opens"
    and the source is skipped for a recovery period. After the recovery
    period, the circuit "closes" and the source can be tried again.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 3600,  # 1 hour
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout_seconds: How long to wait before retrying a failed source
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout_seconds)

    async def is_open(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> bool:
        """
        Check if circuit is open for a source (should be skipped).

        Args:
            conn: Database connection
            source_id: Source to check

        Returns:
            True if circuit is open (skip this source), False otherwise
        """
        row = await conn.fetchrow(
            """
            SELECT circuit_open_until, consecutive_failures
            FROM structured_data_sources
            WHERE id = $1
            """,
            source_id,
        )

        if not row:
            return False

        circuit_open_until = row["circuit_open_until"]

        if circuit_open_until is None:
            return False

        # Check if recovery period has passed
        if datetime.now(timezone.utc) > circuit_open_until:
            # Circuit can close, reset the state
            await self._close_circuit(conn, source_id)
            return False

        return True

    async def record_success(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> None:
        """
        Record a successful fetch, resetting failure count.

        Args:
            conn: Database connection
            source_id: Source that succeeded
        """
        await conn.execute(
            """
            UPDATE structured_data_sources
            SET consecutive_failures = 0,
                circuit_open_until = NULL
            WHERE id = $1
            """,
            source_id,
        )

    async def record_failure(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> bool:
        """
        Record a failed fetch, potentially opening the circuit.

        Args:
            conn: Database connection
            source_id: Source that failed

        Returns:
            True if circuit is now open, False otherwise
        """
        # Increment failure count
        row = await conn.fetchrow(
            """
            UPDATE structured_data_sources
            SET consecutive_failures = consecutive_failures + 1
            WHERE id = $1
            RETURNING consecutive_failures
            """,
            source_id,
        )

        if not row:
            return False

        consecutive_failures = row["consecutive_failures"]

        # Check if threshold reached
        if consecutive_failures >= self.failure_threshold:
            await self._open_circuit(conn, source_id)
            return True

        return False

    async def _open_circuit(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> None:
        """Open the circuit for a source."""
        open_until = datetime.now(timezone.utc) + self.recovery_timeout

        await conn.execute(
            """
            UPDATE structured_data_sources
            SET circuit_open_until = $2
            WHERE id = $1
            """,
            source_id, open_until,
        )

        # Log the event
        from .audit import log_circuit_open
        row = await conn.fetchrow(
            "SELECT consecutive_failures FROM structured_data_sources WHERE id = $1",
            source_id,
        )
        if row:
            await log_circuit_open(conn, source_id, row["consecutive_failures"], open_until)

    async def _close_circuit(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> None:
        """Close the circuit for a source (allow retrying)."""
        await conn.execute(
            """
            UPDATE structured_data_sources
            SET consecutive_failures = 0,
                circuit_open_until = NULL
            WHERE id = $1
            """,
            source_id,
        )

        # Log the event
        from .audit import log_circuit_close
        await log_circuit_close(conn, source_id)

    async def get_circuit_status(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> dict:
        """
        Get circuit breaker status for a source.

        Args:
            conn: Database connection
            source_id: Source to check

        Returns:
            Dict with circuit status info
        """
        row = await conn.fetchrow(
            """
            SELECT consecutive_failures, circuit_open_until
            FROM structured_data_sources
            WHERE id = $1
            """,
            source_id,
        )

        if not row:
            return {"status": "unknown", "source_id": str(source_id)}

        is_open = await self.is_open(conn, source_id)

        return {
            "source_id": str(source_id),
            "status": "open" if is_open else "closed",
            "consecutive_failures": row["consecutive_failures"],
            "circuit_open_until": row["circuit_open_until"].isoformat() if row["circuit_open_until"] else None,
            "failure_threshold": self.failure_threshold,
        }


# Shared instance
circuit_breaker = CircuitBreaker()
