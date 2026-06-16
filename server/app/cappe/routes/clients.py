"""Cappe clients — a directory of everyone who has interacted with a site
(ordered, booked, subscribed, messaged) PLUS clients a business ports in itself
(CSV import / manual add via the `cappe_clients` table). It's a live roll-up
keyed by email, so organic and imported clients merge and never drift. Each
client can be mapped to a branch (`location_id`): explicit on import, else
derived from their most recent booking's location.
"""
import csv
import io
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ...core.services.email._shared import _is_reserved_test_domain
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeClient,
    CappeClientCreate,
    CappeClientImportError,
    CappeClientImportResult,
)
from ._shared import get_owned_site

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_IMPORT_ROWS = 5000
_MAX_IMPORT_BYTES = 5_000_000

# CSV header aliases → canonical column. Lets a business hand us their existing
# export with slightly different headings without re-typing it.
_COL_ALIASES = {
    "email": "email", "e-mail": "email", "email address": "email", "emailaddress": "email",
    "name": "name", "full name": "name", "fullname": "name", "client name": "name", "customer name": "name",
    "phone": "phone", "phone number": "phone", "mobile": "phone", "tel": "phone", "telephone": "phone",
    "branch": "branch", "location": "branch", "branch name": "branch", "store": "branch", "site": "branch",
    "notes": "notes", "note": "notes",
    "tags": "tags", "tag": "tags",
}

# Union every touchpoint into (email, name, kind, amount, ts), then aggregate.
# Branch comes from the explicit cappe_clients row, falling back to the most
# recent booking's location.
_CLIENTS_SQL = """
WITH touch AS (
    SELECT lower(customer_email) AS email, customer_name AS name, 'order' AS kind,
           subtotal_cents AS amount, created_at AS ts
    FROM cappe_orders WHERE site_id = $1 AND customer_email IS NOT NULL
      AND status IN ('paid', 'fulfilled')
    UNION ALL
    SELECT lower(customer_email), customer_name, 'order_pending', 0, created_at
    FROM cappe_orders WHERE site_id = $1 AND customer_email IS NOT NULL
      AND status NOT IN ('paid', 'fulfilled')
    UNION ALL
    SELECT lower(customer_email), customer_name, 'booking', 0, created_at
    FROM cappe_bookings WHERE site_id = $1 AND customer_email IS NOT NULL
    UNION ALL
    SELECT lower(email), name, 'subscriber', 0, created_at
    FROM cappe_subscribers WHERE site_id = $1 AND status = 'subscribed'
    UNION ALL
    SELECT lower(client_email), client_name, 'thread', 0, last_message_at
    FROM cappe_threads WHERE site_id = $1
    UNION ALL
    SELECT lower(email), name, 'client', 0, created_at
    FROM cappe_clients WHERE site_id = $1
),
cl AS (
    SELECT lower(email) AS email, location_id, phone
    FROM cappe_clients WHERE site_id = $1
),
bl AS (
    SELECT DISTINCT ON (lower(customer_email)) lower(customer_email) AS email, location_id
    FROM cappe_bookings
    WHERE site_id = $1 AND customer_email IS NOT NULL AND location_id IS NOT NULL
    ORDER BY lower(customer_email), starts_at DESC
)
SELECT t.email,
       (array_agg(t.name ORDER BY t.ts DESC) FILTER (WHERE t.name IS NOT NULL))[1] AS name,
       COUNT(*) FILTER (WHERE t.kind = 'order') AS orders_count,
       COUNT(*) FILTER (WHERE t.kind = 'booking') AS bookings_count,
       bool_or(t.kind = 'subscriber') AS is_subscriber,
       bool_or(t.kind = 'thread') AS has_thread,
       bool_or(t.kind = 'client') AS is_imported,
       COALESCE(SUM(t.amount), 0) AS total_spent_cents,
       MAX(t.ts) AS last_activity,
       COALESCE(cl.location_id, bl.location_id) AS location_id,
       cl.phone AS phone,
       loc.name AS location_name
FROM touch t
LEFT JOIN cl ON cl.email = t.email
LEFT JOIN bl ON bl.email = t.email
LEFT JOIN cappe_locations loc ON loc.id = COALESCE(cl.location_id, bl.location_id)
GROUP BY t.email, cl.location_id, bl.location_id, cl.phone, loc.name
ORDER BY last_activity DESC
"""


def _client_from_row(r) -> CappeClient:
    return CappeClient(
        email=r["email"], name=r["name"], phone=r["phone"],
        orders_count=r["orders_count"], bookings_count=r["bookings_count"],
        is_subscriber=r["is_subscriber"], has_thread=r["has_thread"], is_imported=r["is_imported"],
        total_spent_cents=int(r["total_spent_cents"] or 0), last_activity=r["last_activity"],
        location_id=r["location_id"], location_name=r["location_name"],
    )


@router.get("/sites/{site_id}/clients", response_model=list[CappeClient])
async def list_clients(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(_CLIENTS_SQL, site_id)
    return [_client_from_row(r) for r in rows]


async def _add_to_newsletter(conn, site_id: UUID, email: str, name: str | None) -> bool:
    """Subscribe an imported client — but never a reserved test domain (those
    bounce and trigger send-storms; see the global test-data rule)."""
    if _is_reserved_test_domain(email):
        return False
    added = await conn.fetchval(
        """INSERT INTO cappe_subscribers (site_id, email, name, source, status)
           VALUES ($1, $2, $3, 'import', 'subscribed')
           ON CONFLICT (site_id, email) DO NOTHING
           RETURNING 1""",
        site_id, email, name,
    )
    return bool(added)


@router.post("/sites/{site_id}/clients", response_model=CappeClient, status_code=status.HTTP_201_CREATED)
async def add_client(
    site_id: UUID,
    body: CappeClientCreate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Add or update a single managed client (upsert by email)."""
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid email address.")
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if body.location_id is not None:
            ok = await conn.fetchval(
                "SELECT 1 FROM cappe_locations WHERE id = $1 AND site_id = $2", body.location_id, site_id
            )
            if not ok:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "That branch doesn't belong to this site.")
        await conn.execute(
            """INSERT INTO cappe_clients (site_id, email, name, phone, location_id, notes, tags, source)
               VALUES ($1, $2, $3, $4, $5, $6, $7, 'manual')
               ON CONFLICT (site_id, email) DO UPDATE SET
                   name = COALESCE(EXCLUDED.name, cappe_clients.name),
                   phone = COALESCE(EXCLUDED.phone, cappe_clients.phone),
                   location_id = EXCLUDED.location_id,
                   notes = COALESCE(EXCLUDED.notes, cappe_clients.notes),
                   tags = EXCLUDED.tags,
                   updated_at = NOW()""",
            site_id, email, body.name, body.phone, body.location_id, body.notes, body.tags,
        )
        if body.add_to_newsletter:
            await _add_to_newsletter(conn, site_id, email, body.name)
        rows = await conn.fetch(_CLIENTS_SQL, site_id)
    for r in rows:
        if r["email"] == email:
            return _client_from_row(r)
    return CappeClient(email=email, name=body.name, phone=body.phone, is_imported=True, location_id=body.location_id)


@router.delete("/sites/{site_id}/clients/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(site_id: UUID, email: str, account: CappeAccount = Depends(require_cappe_account)):
    """Remove a *managed* client row (CSV/manual). Derived touchpoints (orders,
    bookings, subscriptions) are untouched, so the person may still appear if
    they've otherwise interacted with the site."""
    em = email.strip().lower()
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await conn.execute("DELETE FROM cappe_clients WHERE site_id = $1 AND email = $2", site_id, em)
    return None


@router.post("/sites/{site_id}/clients/import", response_model=CappeClientImportResult)
async def import_clients(
    site_id: UUID,
    file: UploadFile = File(...),
    add_to_newsletter: bool = Form(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Bulk-import a client CSV. Columns (header row, case-insensitive, aliases
    accepted): email (required), name, phone, branch, notes, tags. `branch` is
    matched to one of the site's location names (case-insensitive); blank = main
    / all locations. Upserts by email; returns a per-row outcome summary.

    `add_to_newsletter` defaults False — importing a contact list does NOT email
    anyone unless the business explicitly opts in (and reserved test domains are
    always skipped from the newsletter)."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 5 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couldn't read the file — please save it as a UTF-8 CSV.")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file has no rows.")
    header = [_COL_ALIASES.get((h or "").strip().lower(), (h or "").strip().lower()) for h in rows[0]]
    if "email" not in header:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Couldn't find an 'email' column. Download the template to see the expected columns.",
        )
    col_idx = {name: header.index(name) for name in set(header)}
    data_rows = rows[1:]
    if len(data_rows) > _MAX_IMPORT_ROWS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"That's {len(data_rows)} rows — please split into files of {_MAX_IMPORT_ROWS} or fewer.",
        )

    result = CappeClientImportResult()
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        loc_rows = await conn.fetch(
            "SELECT id, lower(name) AS lname FROM cappe_locations WHERE site_id = $1", site_id
        )
        loc_by_name = {r["lname"]: r["id"] for r in loc_rows}
        has_locations = bool(loc_rows)
        seen: set[str] = set()

        for i, row in enumerate(data_rows, start=1):
            def cell(col: str) -> str:
                j = col_idx.get(col)
                return row[j].strip() if (j is not None and j < len(row)) else ""

            email = cell("email").lower()
            if not email and not any((c or "").strip() for c in row):
                continue  # wholly blank line — ignore, don't count
            result.total += 1
            if not _EMAIL_RE.match(email):
                result.errors.append(CappeClientImportError(row=i, email=email or None, reason="Invalid or missing email"))
                result.skipped += 1
                continue
            if email in seen:
                result.skipped += 1
                continue
            seen.add(email)

            location_id = None
            branch = cell("branch")
            if branch and has_locations:
                location_id = loc_by_name.get(branch.lower())
                if location_id is None:
                    result.errors.append(CappeClientImportError(row=i, email=email, reason=f"Unknown branch '{branch}'"))
                    result.skipped += 1
                    continue
                result.branches_matched += 1

            name = cell("name") or None
            phone = cell("phone") or None
            notes = cell("notes") or None
            tags_raw = cell("tags")
            tags = [t.strip() for t in re.split(r"[;|]", tags_raw) if t.strip()] if tags_raw else []

            inserted = await conn.fetchval(
                """INSERT INTO cappe_clients (site_id, email, name, phone, location_id, notes, tags, source)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, 'import')
                   ON CONFLICT (site_id, email) DO UPDATE SET
                       name = COALESCE(EXCLUDED.name, cappe_clients.name),
                       phone = COALESCE(EXCLUDED.phone, cappe_clients.phone),
                       location_id = COALESCE(EXCLUDED.location_id, cappe_clients.location_id),
                       notes = COALESCE(EXCLUDED.notes, cappe_clients.notes),
                       tags = CASE WHEN cardinality(EXCLUDED.tags) > 0 THEN EXCLUDED.tags ELSE cappe_clients.tags END,
                       updated_at = NOW()
                   RETURNING (xmax = 0)""",
                site_id, email, name, phone, location_id, notes, tags,
            )
            if inserted:
                result.created += 1
            else:
                result.updated += 1
            if add_to_newsletter and await _add_to_newsletter(conn, site_id, email, name):
                result.newsletter_added += 1

    return result
