"""Read-only unified server/client error collection for silent autofix.

Runs inside the live backend container and emits grouped incidents plus collection
metadata. Server keys deliberately retain their original shape so existing bot
branches, PRs, and no-fix issues remain valid. Client reports use a distinct
``client|`` keyspace because they are raw rows rather than pre-aggregated rows.
"""
import asyncio
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlsplit

import asyncpg

AUTOFIXABLE_KINDS = {"exception", "unhandled", "celery_task", "background_task", "http_error"}
INFRA_EXCEPTION_TYPES = {
    "ConnectionDoesNotExistError",
    "InterfaceError",
    "TimeoutError",
    "CancelledError",
    "PostgresConnectionError",
    "ConnectionResetError",
    "ClientDisconnect",
}
CLIENT_KINDS = {"js_error", "promise_rejection", "api_error", "react_error"}
INFRA_CLIENT_STATUSES = {0, 502, 503, 504}
_NORMALIZE = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}", re.I), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<hexid>"),
    (re.compile(r"'[^']{0,120}'"), "'<s>'"),
    (re.compile(r'"[^"]{0,120}"'), '"<s>"'),
    (re.compile(r"\b\d+\b"), "<n>"),
]
_ASSET_HASH = re.compile(r"(-[0-9A-Za-z_-]{8,})(?=\.(?:js|mjs|css)(?:\?|:|$))")
_LINE_COLUMN = re.compile(r":\d+(?::\d+)?(?=\)?$|\s|$)")
_DYNAMIC_SEGMENT = re.compile(r"/(?:[0-9a-f]{8}-[0-9a-f-]{27,}|[A-Za-z0-9_-]{20,})(?=/|$)", re.I)


def _normalize(text):
    for pattern, repl in _NORMALIZE:
        text = pattern.sub(repl, text)
    return text


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_key(kind, exception_type, message, traceback_str):
    """The original server incident identity. Do not change its shape."""
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


def _path(value):
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
    except ValueError:
        path = value.split("?", 1)[0].split("#", 1)[0]
    # Browser API helpers use paths relative to /api, while FastAPI request
    # telemetry includes that mount prefix. Align only for correlation keys.
    if path == "/api":
        path = "/"
    elif path.startswith("/api/"):
        path = path[4:]
    path = _DYNAMIC_SEGMENT.sub("/<dynamic>", path)
    return _normalize(path)


def _client_frame(stack):
    for raw in (stack or "").splitlines():
        line = raw.strip()
        lower = line.lower()
        if "chrome-extension://" in lower or "moz-extension://" in lower:
            continue
        if ".ts" in line or ".js" in line or ".jsx" in line or ".tsx" in line:
            line = _ASSET_HASH.sub("-<asset>", line)
            return _LINE_COLUMN.sub(":<line>", line)
    return ""


def stable_client_key(kind, message, stack, api_endpoint, url, component_stack=""):
    """Stable browser incident identity without build hashes or dynamic values."""
    raw = "|".join(
        (
            "client",
            kind or "",
            _normalize((message or "")[:200]),
            _path(api_endpoint) or _path(url),
            _normalize(_client_frame(stack)),
            _normalize((component_stack or "")[:500]),
        )
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _context(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _client_actionable(row):
    if row["kind"] not in CLIENT_KINDS:
        return False
    value = " ".join((row["message"] or "", row["stack"] or "", row["url"] or "")).lower()
    if "localhost" in value or "127.0.0.1" in value:
        return False
    if "chrome-extension://" in value or "moz-extension://" in value:
        return False
    if "failed to fetch dynamically imported module" in value or "vite:preloaderror" in value:
        return False
    return not (row["kind"] == "api_error" and row["api_status_code"] in INFRA_CLIENT_STATUSES)


def _excerpt(context):
    component_stack = context.get("component_stack")
    if isinstance(component_stack, str):
        return component_stack[:1000]
    body = context.get("body")
    if isinstance(body, str):
        return body[:1000]
    return None


def _incident_priority(item):
    """Newest actionable incident first; recurrence advances ``last_seen``."""
    return item["last_seen"], item["level"] == "CRITICAL", item["occurrences"]


async def _fetch_rows(conn, hours, limit):
    server_rows = await conn.fetch(
        """
        SELECT id::text, kind, level, message, exception_type, traceback, source,
               request_method, request_path, request_status, context::text AS context,
               occurrences, first_seen, last_seen, resolved_at IS NOT NULL AS resolved
        FROM server_error_reports
        WHERE level IN ('ERROR', 'CRITICAL')
          AND last_seen > NOW() - make_interval(hours => $1::int)
        ORDER BY last_seen DESC
        LIMIT $2::int
        """,
        hours,
        # Over-fetch: a resolved row no longer yields an incident (still
        # filtered out below) but its request_ids must stay in
        # request_pairs, or clicking Resolve just makes the correlated
        # client-side echo of the same failure reappear as a fresh incident.
        # The final incident list is still capped to `limit` in main().
        limit * 4,
    )
    client_rows = await conn.fetch(
        """
        SELECT id::text, kind, message, stack, url, api_endpoint, api_status_code,
               context::text AS context, occurred_at
        FROM client_error_reports
        WHERE occurred_at > NOW() - make_interval(hours => $1::int)
        ORDER BY occurred_at DESC
        LIMIT $2::int
        """,
        hours,
        limit * 20,
    )
    return server_rows, client_rows


def _group_server(rows):
    grouped = {}
    request_pairs = set()
    skipped = 0
    for row in rows:
        # Collect correlation pairs from every row up front — before the
        # actionable/infra/resolved filters below. The point of a pair is
        # "the server already saw this exact request fail"; that's true
        # whether or not the row is itself autofixable (e.g. a
        # ConnectionResetError that surfaces to the browser as an HTTP 500)
        # or has since been marked resolved by a human.
        context = _context(row["context"])
        request_path = row["request_path"] or ""
        path = _path(request_path) if request_path else ""
        if path:
            request_ids = context.get("request_ids")
            if not isinstance(request_ids, list):
                single = context.get("request_id")
                request_ids = [single] if single else []
            for rid in request_ids:
                if rid:
                    request_pairs.add((str(rid), path))

        if (
            row["resolved"]
            or row["kind"] not in AUTOFIXABLE_KINDS
            or (row["exception_type"] or "") in INFRA_EXCEPTION_TYPES
        ):
            skipped += 1
            continue
        key = stable_key(row["kind"], row["exception_type"], row["message"], row["traceback"])
        request_id = context.get("request_id")
        group = grouped.get(key)
        if group is None:
            grouped[key] = {
                "surface": "server", "stable_key": key, "error_id": row["id"],
                "kind": row["kind"], "level": row["level"], "exception_type": row["exception_type"],
                "message": row["message"] or "", "traceback": row["traceback"] or "",
                "source": row["source"], "request_method": row["request_method"],
                "request_path": request_path, "request_status": row["request_status"],
                "occurrences": row["occurrences"] or 0, "days_seen": 1,
                "first_seen": _ts(row["first_seen"]), "last_seen": _ts(row["last_seen"]),
                "request_id": request_id, "company_id": context.get("company_id"), "context_excerpt": None,
            }
            continue
        group["occurrences"] += row["occurrences"] or 0
        group["days_seen"] += 1
        group["first_seen"] = min(group["first_seen"], _ts(row["first_seen"]))
        if _ts(row["last_seen"]) > group["last_seen"]:
            group.update({
                "last_seen": _ts(row["last_seen"]), "error_id": row["id"],
                "traceback": row["traceback"] or group["traceback"], "request_id": request_id,
            })
    return grouped, request_pairs, skipped


def _group_client(rows, server_request_pairs):
    grouped = {}
    skipped = 0
    correlated = 0
    for row in rows:
        if not _client_actionable(row):
            skipped += 1
            continue
        context = _context(row["context"])
        request_id = context.get("request_id")
        endpoint = _path(row["api_endpoint"])
        if row["kind"] == "api_error" and request_id and endpoint and (str(request_id), endpoint) in server_request_pairs:
            correlated += 1
            continue
        component_stack = context.get("component_stack") if isinstance(context.get("component_stack"), str) else ""
        key = stable_client_key(row["kind"], row["message"], row["stack"], row["api_endpoint"], row["url"], component_stack)
        occurred = _ts(row["occurred_at"])
        group = grouped.get(key)
        if group is None:
            grouped[key] = {
                "surface": "client", "stable_key": key, "error_id": row["id"],
                "kind": row["kind"], "level": "ERROR", "exception_type": row["kind"],
                "message": row["message"] or "", "traceback": row["stack"] or "",
                "source": "browser", "request_method": None,
                "request_path": row["api_endpoint"] or _path(row["url"]),
                "request_status": row["api_status_code"], "occurrences": 1, "days_seen": 1,
                "first_seen": occurred, "last_seen": occurred, "request_id": request_id,
                "company_id": None, "context_excerpt": _excerpt(context), "_days": {occurred[:10]},
            }
            continue
        group["occurrences"] += 1
        group["_days"].add(occurred[:10])
        group["days_seen"] = len(group["_days"])
        group["first_seen"] = min(group["first_seen"], occurred)
        if occurred > group["last_seen"]:
            group.update({
                "last_seen": occurred, "error_id": row["id"], "traceback": row["stack"] or group["traceback"],
                "request_id": request_id, "context_excerpt": _excerpt(context),
            })
    for group in grouped.values():
        group.pop("_days", None)
    return grouped, skipped, correlated


async def main():
    hours = int(os.environ.get("AUTOFIX_HOURS", "24"))
    limit = int(os.environ.get("AUTOFIX_LIMIT", "25"))
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], server_settings={"default_transaction_read_only": "on"})
    try:
        await conn.execute("SET statement_timeout = '15s'")
        server_rows, client_rows = await _fetch_rows(conn, hours, limit)
    finally:
        await conn.close()

    server, request_pairs, skipped_infra = _group_server(server_rows)
    client, skipped_client, suppressed_correlated = _group_client(client_rows, request_pairs)
    incidents = sorted(
        [*server.values(), *client.values()],
        # This is an incident-response queue: a genuinely new production
        # failure must not sit behind a day-old high-count fingerprint (or be
        # pushed out of the final limit entirely). Hot recurring failures
        # still rise because every occurrence advances last_seen.
        key=_incident_priority,
        reverse=True,
    )[:limit]
    json.dump({
        "incidents": incidents,
        "skipped_infra": skipped_infra,
        "skipped_client": skipped_client,
        "suppressed_correlated": suppressed_correlated,
    }, sys.stdout)


if __name__ == "__main__":
    asyncio.run(main())
