"""Read-only query of server_error_reports, run inside the live backend
container via `docker exec -i <container> python -`. Emits one JSON array to
stdout: unresolved ERROR/CRITICAL rows from the last AUTOFIX_HOURS hours,
grouped by a date-and-value-free stable_key so the same bug — across UTC-day
boundaries, and across occurrences carrying different interpolated ids —
collapses into one incident.

Never writes. server_settings enforces read-only at the connection level, not
by convention — any INSERT/UPDATE in this session is rejected by Postgres
with 25006 read_only_sql_transaction.

WHERE resolved_at IS NULL doubles as the human "stop bothering me" switch:
the only writer of resolved_at is a person clicking Resolve in
/admin/server-errors (server/app/core/routes/telemetry/server_errors.py) —
nothing in the deploy path resolves anything automatically.
"""
import asyncio
import hashlib
import json
import os
import re
import sys

import asyncpg

# kind is CHECK-constrained (server_error_reports migration) to these 8
# values. startup/db_error are usually infra (pool exhaustion, RDS failover,
# a bad deploy) rather than an app bug a code diff can fix — investigating
# them burns a run on a PR that can't be right.
AUTOFIXABLE_KINDS = {"exception", "unhandled", "celery_task", "background_task", "http_error"}

# Exception types that are almost always infra/environment, not app code.
INFRA_EXCEPTION_TYPES = {
    "ConnectionDoesNotExistError",
    "InterfaceError",
    "TimeoutError",
    "CancelledError",
    "PostgresConnectionError",
    "ConnectionResetError",
    "ClientDisconnect",
}

_NORMALIZE = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}", re.I), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<hexid>"),
    (re.compile(r"'[^']{0,120}'"), "'<s>'"),
    (re.compile(r'"[^"]{0,120}"'), '"<s>"'),
    (re.compile(r"\b\d+\b"), "<n>"),
]


def _normalize(text):
    """Strip interpolated values (ids, counts, quoted strings) before
    hashing. Without this, two occurrences of the SAME bug with different
    bound values (an id, a malformed date literal) hash to different keys —
    this is exactly how #242-#247 became five PRs for two bugs."""
    for pattern, repl in _NORMALIZE:
        text = pattern.sub(repl, text)
    return text


def stable_key(kind, exception_type, message, traceback_str):
    """Deterministic incident identity, computed once, here. Does not need to
    match error_reporter._fingerprint (server/app/core/services/
    error_reporter.py:72-82) exactly — that fingerprint embeds a daily UTC
    bucket and hashes the raw, unnormalized message, so it is unusable as a
    durable cross-day, cross-occurrence identity."""
    top_frame = ""
    for line in (traceback_str or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("File "):
            top_frame = stripped
            break
    head = _normalize((message or "")[:200])
    frame = _normalize(top_frame)
    raw = f"{kind}|{exception_type or ''}|{head}|{frame}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


async def main():
    hours = int(os.environ.get("AUTOFIX_HOURS", "24"))
    limit = int(os.environ.get("AUTOFIX_LIMIT", "25"))

    conn = await asyncpg.connect(
        os.environ["DATABASE_URL"],
        server_settings={"default_transaction_read_only": "on"},
    )
    try:
        await conn.execute("SET statement_timeout = '15s'")
        rows = await conn.fetch(
            """
            SELECT id::text, fingerprint, kind, level, logger_name, message,
                   exception_type, traceback, source, hostname,
                   request_method, request_path, request_status,
                   context::text AS context,
                   occurrences, first_seen, last_seen
            FROM server_error_reports
            WHERE resolved_at IS NULL
              AND level IN ('ERROR', 'CRITICAL')
              AND last_seen > NOW() - make_interval(hours => $1::int)
            ORDER BY last_seen DESC
            LIMIT $2::int
            """,
            hours,
            limit,
        )
    finally:
        await conn.close()

    grouped = {}
    skipped_infra = 0
    for r in rows:
        if r["kind"] not in AUTOFIXABLE_KINDS:
            skipped_infra += 1
            continue
        if (r["exception_type"] or "") in INFRA_EXCEPTION_TYPES:
            skipped_infra += 1
            continue

        key = stable_key(r["kind"], r["exception_type"], r["message"], r["traceback"])
        ctx = {}
        if r["context"]:
            try:
                ctx = json.loads(r["context"])
            except (json.JSONDecodeError, TypeError):
                ctx = {}
        g = grouped.get(key)
        if g is None:
            grouped[key] = {
                "stable_key": key,
                "error_id": r["id"],
                "kind": r["kind"],
                "level": r["level"],
                "exception_type": r["exception_type"],
                "message": r["message"] or "",
                "traceback": r["traceback"] or "",
                "source": r["source"],
                "request_method": r["request_method"],
                "request_path": r["request_path"],
                "request_status": r["request_status"],
                "occurrences": r["occurrences"] or 0,
                "days_seen": 1,
                "first_seen": r["first_seen"].isoformat(),
                "last_seen": r["last_seen"].isoformat(),
                "request_id": ctx.get("request_id"),
                "company_id": ctx.get("company_id"),
            }
        else:
            g["occurrences"] += r["occurrences"] or 0
            g["days_seen"] += 1
            if r["first_seen"].isoformat() < g["first_seen"]:
                g["first_seen"] = r["first_seen"].isoformat()
            if r["last_seen"].isoformat() > g["last_seen"]:
                # Keep the newest row as the exemplar: newest error_id (for
                # the admin link) and newest traceback (most likely current).
                g["last_seen"] = r["last_seen"].isoformat()
                g["error_id"] = r["id"]
                g["traceback"] = r["traceback"] or g["traceback"]

    # Persistence (seen across more days) is a better bug signal than a
    # one-day spike, which is more often an outage than a bug an autofix
    # can address.
    out = sorted(
        grouped.values(),
        key=lambda g: (g["days_seen"], g["occurrences"]),
        reverse=True,
    )
    json.dump({"incidents": out, "skipped_infra": skipped_infra}, sys.stdout)


if __name__ == "__main__":
    asyncio.run(main())
