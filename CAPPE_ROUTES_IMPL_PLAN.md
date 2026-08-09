# CAPPE_ROUTES_REVIEW.md — Technical Implementation Plan

Companion to `CAPPE_ROUTES_REVIEW.md` (the *what/why*). This file is the
*where/how*: exact file paths, function signatures, SQL, test cases, and
registration points, verified against the current source (2026-08-09).

**Backend-only change.** No `client/` files are touched; no response shapes
change except new 400/409/422/503 statuses on paths that previously 500'd,
double-sent, or silently stranded money.

Line numbers below are anchors in the current tree, not contracts.

---

## Ground rules for the implementer

- Cappe rule (`server/app/cappe/CLAUDE.md`): **services/ must never import
  routes/**. Two changes in Phase 4 move code route→service; the only
  route-local helper they need (`invalidate_render_cache`) already has a
  service-side half — `services/render_cache.py:invalidate_site_render_cache`
  — use that, never `from ..routes.render import …`.
- Workers are pool-free (`server/app/workers/CLAUDE.md`). New tasks use
  `workers.utils.get_db_connection()` (raw asyncpg, closed in `finally`);
  code that must run in BOTH worlds uses `app.database.connection_or_direct()`
  (`app/database/pool.py:110`).
- Every money-mutating UPDATE gets a status predicate + `RETURNING id` +
  explicit `None` handling. Never a bare `WHERE id=$1` on a money row.
- The post-edit hook runs `py_compile` automatically. After all edits:
  `cd server && ./venv/bin/python -m pytest tests/cappe/ -q`.
- Migrations: repo runs `alembic upgrade heads` (multiple heads tolerated).
  New cappe migration continues the cappe chain: `revision = "zzzzcappe30"`,
  `down_revision = "zzzzcappe29"` (verified: nothing depends on zzzzcappe29).
  Apply to dev via `./scripts/migrate-dev.sh`; prod only per DB_WORKFLOW.md
  and only with explicit user approval.

Suggested commit split (one branch, reviewable per phase):
1. `Phase 1 — CAS the money paths` (collab, payments, newsletter, billing)
2. `Phase 2 — upload_guard` (new service + 4 endpoint wirings)
3. `Phase 3 — data integrity` (build_patch nullable, ledger re-point,
   bookings busy feed, sites page count / receipt_prefix, adjust_stock)
4. `Phase 4 — worker reconciliation` (service moves, 2 tasks, celery_app,
   migration zzzzcappe30)

---

## Phase 1 — money-path correctness

### 1.1 CAS the post-Stripe payment UPDATE

**File:** `server/app/cappe/routes/collab.py` — `checkout_payment`
(endpoint `POST /collab/offers/{offer_id}/payments/{payment_id}/checkout`,
UPDATE at lines 720-726).

`logger` already exists (`collab.py:53`) — no need to add one.

Replace the unconditional `conn.execute(...)` with:

```python
    async with get_connection() as conn:
        updated = await conn.fetchval(
            "UPDATE cappe_collab_payments SET status='processing', stripe_checkout_session_id=$2, "
            "fee_bps_snapshot=$3, fee_cents=$4, updated_at=NOW() "
            "WHERE id=$1 AND status IN ('due','processing') RETURNING id",
            payment_id, session.get("id"), fee_bps, fee,
        )
    if updated is None:
        # The Connect webhook marked this installment paid during the ~1s
        # Stripe round-trip above. Handing back a fresh session URL now
        # would let the brand pay a settled installment a second time.
        logger.warning(
            "cappe collab checkout: payment %s settled while the Stripe session "
            "was being created (webhook won the race) — refusing a new session",
            payment_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This payment was already settled",
        )
    return {"url": session.get("url")}
```

Note: the pre-read at 684-688 (`payment["status"] not in ("due","processing")`)
stays — it provides the fast 409 and the payouts-not-ready check; the CAS is
the race backstop.

### 1.2 Release the webhook claim when the order does not match

**File:** `server/app/cappe/routes/payments.py` — `_handle_connect_event`,
order branch (lines 190-215).

The `if row is not None / else` block sits OUTSIDE the
`async with get_connection()` block, so the disambiguating lookup opens its
own connection. Replace the bare `logger.warning` else-branch with:

```python
            else:
                # No row matched. Distinguish "already processed" (idempotent,
                # keep the claim, 200) from "order not found / not owned by
                # this connected account" (raise → the except in
                # payments_webhook releases the claim → Stripe retries).
                # Silently 200-ing here is the stranded-paid-order failure
                # release_stripe_event exists to prevent.
                async with get_connection() as conn:
                    already = await conn.fetchval(
                        """SELECT o.status FROM cappe_orders o
                             JOIN cappe_sites s ON s.id = o.site_id
                             JOIN cappe_accounts a ON a.id = s.account_id
                            WHERE o.id = $1 AND a.stripe_account_id = $2""",
                        oid, event_account_id,
                    )
                if already is None:
                    logger.error(
                        "cappe webhook: order %s not matched to event account %s — "
                        "releasing claim for Stripe retry",
                        order_id, event_account_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Order not matched; releasing event for retry",
                    )
                logger.info(
                    "cappe webhook: order %s already %s — idempotent skip",
                    order_id, already,
                )
```

Also, the branch condition at line 175 (`if oid is not None and event_account_id:`)
silently skips the whole order block when `event_account_id` is falsy. Add an
`elif` so that case leaves a signal:

```python
        if oid is not None and event_account_id:
            ...  # existing block
        elif oid is not None:
            logger.warning(
                "cappe webhook: checkout.session.completed for order %s carries no "
                "event account — order branch skipped", order_id,
            )
```

Caveat to accept (per review): an order that exists under a DIFFERENT
connected account also reads `already is None` → 503 → Stripe retries until
it gives up (~3 days), surfacing in `server_error_reports`. That is the
chosen trade over silently stranding a genuine match failure.

### 1.3 CAS + lock the revision request

**File:** `server/app/cappe/routes/collab.py` — `request_deliverable_revision`
(lines 643-673). `approve_deliverable` (609-616) is the in-repo reference.

Wrap the read→check→UPDATE span (651-668) in one transaction; lock the row;
add the status predicate + `offer_id` to the UPDATE:

```python
        async with conn.transaction():
            deliverable = await conn.fetchrow(
                "SELECT * FROM cappe_collab_deliverables WHERE id=$1 AND offer_id=$2 FOR UPDATE",
                deliverable_id, offer_id,
            )
            if deliverable is None or deliverable["status"] != "submitted":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Deliverable is not submitted")

            rev = await svc.accepted_revision(conn, offer_row)
            terms = svc.CollabTerms.model_validate(loads(rev["terms"])) if rev else None
            revision_rounds = terms.revision_rounds if terms else 1
            if deliverable["revision_count"] >= revision_rounds:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=f"Revision limit reached ({revision_rounds}) — approve or cancel")

            row = await conn.fetchrow(
                "UPDATE cappe_collab_deliverables SET status='revision_requested', review_note=$2, "
                "revision_count=revision_count+1, updated_at=NOW() "
                "WHERE id=$1 AND offer_id=$3 AND status='submitted' RETURNING *",
                deliverable_id, body.review_note, offer_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Deliverable is not submitted")
```

Everything after (email + `return DeliverableOut(...)`) stays outside the
transaction, unchanged.

### 1.4 CAS the campaign send (both directions)

**File:** `server/app/cappe/routes/newsletter.py` — `send_campaign`
(lines 170-209). `shop.py:415-422` is the in-repo `FOR UPDATE` reference;
here a status predicate suffices (single-statement CAS, no follow-up writes).

Send UPDATE (187-191) — add the predicate and a 409 on `None` (the pre-read
at 179-185 already handled 404, so `None` here means a racing send won):

```python
        row = await conn.fetchrow(
            f"""UPDATE cappe_campaigns SET status = 'sending', updated_at = NOW()
                WHERE id = $1 AND site_id = $2 AND status NOT IN ('sent', 'sending')
                RETURNING {_CAMPAIGN_COLS}""",
            campaign_id, site_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaign already sent")
```

Celery-failure revert (199-204) — add `AND status = 'sending'` so a revert
can never stomp a `sent` a racing worker wrote:

```python
            row = await conn.fetchrow(
                f"""UPDATE cappe_campaigns SET status = 'draft', updated_at = NOW()
                    WHERE id = $1 AND site_id = $2 AND status = 'sending'
                    RETURNING {_CAMPAIGN_COLS}""",
                campaign_id, site_id,
            )
```

(The reverted row is still unused — the 503 raise follows; keep as-is.)

### 1.5 Drop the amount equality from the collab match

**File:** `server/app/cappe/routes/payments.py` — collab branch UPDATE
(lines 237-249).

- Delete `AND cp.amount_cents = $5`; drop the 5th bind (`amount_total`).
- `RETURNING` already carries `cp.amount_cents` — keep it.
- After a match, compare against the Stripe total and WARN on drift (audit
  signal instead of a lost payment):

```python
                    crow = await conn.fetchrow(
                        """UPDATE cappe_collab_payments cp
                               SET status = 'paid', paid_at = NOW(),
                                   stripe_payment_intent = $2, stripe_checkout_session_id = $4,
                                   updated_at = NOW()
                              FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                             WHERE cp.id = $1 AND cp.status IN ('due', 'processing')
                               AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                               AND ca.id = p.account_id AND ca.stripe_account_id = $3
                         RETURNING cp.offer_id, cp.trigger, cp.label, cp.amount_cents""",
                        cpid, obj.get("payment_intent"), event_account_id, session_id,
                    )
                    if (
                        crow is not None
                        and amount_total is not None
                        and int(amount_total) != int(crow["amount_cents"])
                    ):
                        logger.warning(
                            "cappe collab webhook: payment %s matched but Stripe total %s != "
                            "stored %s cents (automatic tax / promo / shipping adjustment?) — audit",
                            collab_payment_id, amount_total, crow["amount_cents"],
                        )
```

Leave the `else: logger.error(...)` branch (263-276) as-is — with the
equality gone its only remaining cause is a genuinely cancelled payment.
Update its nearby comment (227-236) to drop the "plus amount" wording:
ownership is proved by `cp.id` (trusted event metadata) + the
`ca.stripe_account_id` join.

### 1.6 Guard the null `stripe_subscription_id` in set_addon_quantity

**File:** `server/app/cappe/routes/billing.py` — `set_addon_quantity`
(lines 275-281). Split the combined guard, mirroring `change_plan:393-397`:

```python
        sub = await billing_svc.current_subscription(conn, account.id)
        if not sub or sub["source"] != "stripe":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Add-ons require an active paid subscription.",
            )
        if not sub["stripe_subscription_id"]:
            # Mid-sync subscription: the Stripe id lands via webhook moments
            # later. 409 (retryable) instead of passing None to Stripe and
            # surfacing a 502 "Could not update add-on".
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subscription is still syncing — try again in a moment.",
            )
```

---

## Phase 2 — upload MIME is client-controlled

### 2.1 New `server/app/cappe/services/upload_guard.py`

Owns the allowlists (moved out of `routes/uploads.py:45-64` and
`routes/creators.py:38-39`, killing the duplication) + sniffing.

```python
"""Upload content-type verification for Cappe.

The multipart part `Content-Type` is attacker-authored; the S3 object's
ContentType must be backed by the file's actual leading bytes, or an
HTML/SVG payload rides a borrowed `image/png` label onto the tenant origin
(whose TENANT_CSP allows `script-src 'unsafe-inline'`) — stored XSS.
"""
from typing import Optional

from fastapi import HTTPException, status

ALLOWED_IMAGE: set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO: set[str] = {"video/mp4", "video/webm", "video/quicktime"}
ALLOWED_DELIVERABLE: set[str] = ALLOWED_IMAGE | {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}

# Declared type -> sniff results that BACK it. Empty set = textual format with
# no magic number: accepted but ALWAYS stored as text/plain, so a mislabelled
# SVG/HTML payload can never be served as an active type.
_EXPECTED: dict[str, set[str]] = {
    "image/jpeg": {"image/jpeg"},
    "image/png": {"image/png"},
    "image/gif": {"image/gif"},
    "image/webp": {"image/webp"},
    "video/mp4": {"video/mp4", "video/quicktime"},      # ISO-BMFF share 'ftyp'
    "video/quicktime": {"video/mp4", "video/quicktime"},
    "video/webm": {"video/webm"},
    "application/pdf": {"application/pdf"},
    "application/zip": {"application/zip"},
    "application/x-zip-compressed": {"application/zip"},
    "application/msword": {"application/vnd.ms-office"},          # OLE2
    "application/vnd.ms-excel": {"application/vnd.ms-office"},    # OLE2
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {"application/zip"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {"application/zip"},
    "text/plain": set(),
    "text/csv": set(),
}

_SNIFF_MIN_BYTES = 16


def sniff(data: bytes) -> Optional[str]:
    """Content type implied by the leading bytes; None when unrecognized or
    the format has no magic number (text/*)."""
    if len(data) < _SNIFF_MIN_BYTES:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/vnd.ms-office"  # OLE2 compound (doc/xls)
    if data[4:8] == b"ftyp":
        return "video/mp4"  # ISO-BMFF; mp4/mov distinguished only by brand
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"  # Matroska/WebM EBML
    return None


def verify_upload(data: bytes, declared: Optional[str], allowed: set[str]) -> str:
    """Return the content type to store (pass to storage.upload_file), or
    raise 400. Declared type must be in `allowed` AND backed by the bytes.
    Textual formats normalize to text/plain. Never returns an attacker-
    controlled string that wasn't validated against the bytes."""
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if declared not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    expected = _EXPECTED.get(declared)
    if expected is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    if not expected:
        return "text/plain"
    actual = sniff(data)
    if actual not in expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contents don't match the declared type",
        )
    return declared
```

Design notes:
- `sniff` returns a canonical vocab (`video/mp4` for any `ftyp`,
  `application/vnd.ms-office` for OLE) and `_EXPECTED` maps declared→accepted
  vocab, so mp4↔mov and doc↔xls share magic without false precision.
- On success the STORED type is the declared one (backed by bytes) — except
  textual, which stores `text/plain`.

### 2.2 Wire the four endpoints

Pattern for each: keep the cheap declared-type check BEFORE `read_capped`
(a bogus type still 400s without reading 25 MB), then verify bytes after,
and pass `verify_upload`'s RETURN to `upload_file` — never `file.content_type`.

**`server/app/cappe/routes/uploads.py`**
- Delete module sets `_ALLOWED`, `_ALLOWED_DELIVERABLE`, `_ALLOWED_VIDEO`
  (45-64); import `from ..services import upload_guard`.
- `upload_image` (67-97): pre-check `file.content_type not in upload_guard.ALLOWED_IMAGE`;
  after `read_capped` + empty check:
  `content_type = upload_guard.verify_upload(data, file.content_type, upload_guard.ALLOWED_IMAGE)`;
  `upload_file(..., content_type=content_type)`.
  The empty-file 400 at 81-82 can stay (verify_upload also guards it).
- `upload_deliverable` (162-186): same with `ALLOWED_DELIVERABLE`.
- `upload_video` (189-222): same with `ALLOWED_VIDEO`.

**`server/app/cappe/routes/creators.py`**
- Delete `_ALLOWED_IMAGE` / `_ALLOWED_VIDEO` (38-39); import upload_guard.
- `upload_creator_media` (292-315): keep the image/video branch for the size
  cap, then verify with the matching allowlist:

```python
    if file.content_type in upload_guard.ALLOWED_IMAGE:
        allowed = upload_guard.ALLOWED_IMAGE
        data = await read_capped(file, _MAX_IMAGE_BYTES, "Image too large (max 5 MB)")
    elif file.content_type in upload_guard.ALLOWED_VIDEO:
        allowed = upload_guard.ALLOWED_VIDEO
        data = await read_capped(file, _MAX_VIDEO_BYTES, "Video too large (max 50 MB)")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    content_type = upload_guard.verify_upload(data, file.content_type, allowed)
    url = await get_storage().upload_file(..., content_type=content_type)
```

---

## Phase 3 — data integrity

### 3.1 `build_patch` learns nullability

**File:** `server/app/cappe/routes/_shared.py` (105-122).

```python
def build_patch(
    body,
    cols: Sequence[str],
    start: int = 0,
    *,
    nullable: Optional[Collection[str]] = None,
) -> tuple[list[str], list[Any]]:
    """... (existing docstring) ...

    When `nullable` is given, an explicitly-sent null for any column OUTSIDE
    it raises 422 naming the field(s) — instead of building `col = NULL` for
    a NOT NULL column and surfacing a raw NotNullViolationError as a 500.
    `nullable=None` (default) keeps the legacy behavior.
    """
    sets: list[str] = []
    args: list[Any] = []
    bad: list[str] = []
    fields = body.model_fields_set
    for col in cols:
        if col in fields:
            val = getattr(body, col)
            if val is None and nullable is not None and col not in nullable:
                bad.append(col)
                continue
            args.append(val)
            sets.append(f"{col} = ${start + len(args)}")
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"These fields cannot be null: {', '.join(bad)}",
        )
    return sets, args
```

Add `Collection` to the `typing` import. `HTTPException` + `status` are
already imported in `_shared.py`.

**Callsite wiring** (allowlists derived from the migrations — re-verify each
against the table DDL while implementing; everything NOT listed is NOT NULL):

| callsite | table | `nullable=` |
|---|---|---|
| `newsletter.py:141` | `cappe_campaigns` | `{"body_html", "from_name", "scheduled_at"}` |
| `bookings.py:165` | `cappe_booking_types` | `{"description", "price_cents", "category", "location_id"}` |
| `staff.py:100` | `cappe_staff` | `{"bio", "image_url", "location_id"}` |
| `locations.py:148` | `cappe_locations` | `{"address", "lat", "lng", "timezone", "contact_phone", "contact_email"}` |
| `blog.py:67` | `cappe_posts` | `{"excerpt", "body", "cover_image_url"}` |
| `shop.py:223` | `cappe_products` | `{"description", "image_url", "sku", "inventory", "low_stock_threshold", "digital_file_url", "booking_type_id", "category"}` |
| `creators.py:142` | `cappe_creator_profiles` | `{"avatar_url", "cover_url", "bio", "location"}` |
| `shop.py:425` | `cappe_orders` | `{"carrier", "tracking_number"}` (already model-guarded at `models/shop.py:216-223`; pass for consistency) |

`collab.py:236-239` (campaigns PATCH) builds its SET list by hand — it is NOT
a `build_patch` caller; leave it (its columns are all NOT NULL and it already
422s on empty).

### 3.2 Stop orphaning the per-variant stock ledger

**File:** `server/app/cappe/routes/shop.py` — `_replace_option_groups`
(85-120). `cappe_inventory_adjustments.option_id` is `ON DELETE SET NULL`
(`zzzzcappe18:38`), so the DELETE at 100 unattributes history. Snapshot the
ledger before the DELETE, re-point after each option INSERT, keyed on the
same `(group name, option name)` key already used for inventory.

```python
async def _replace_option_groups(conn, site_id, product_id, groups) -> None:
    """... existing docstring ... Also re-points the inventory-adjustment
    ledger onto the recreated option ids (option_id is ON DELETE SET NULL,
    so without this any option_groups edit would silently unattribute every
    historical variant adjustment)."""
    if groups is None:
        return
    prior = await conn.fetch(
        "SELECT g.name AS gname, o.name AS oname, o.inventory, o.id AS oid "
        "FROM cappe_product_options o JOIN cappe_product_option_groups g ON g.id = o.group_id "
        "WHERE g.product_id = $1",
        product_id,
    )
    prior_inv = {(r["gname"], r["oname"]): r["inventory"] for r in prior}
    prior_oid = {(r["gname"], r["oname"]): r["oid"] for r in prior}

    # Snapshot the ledger rows bound to the about-to-be-deleted option ids.
    ledger: dict = {}
    old_ids = [r["oid"] for r in prior]
    if old_ids:
        for r in await conn.fetch(
            "SELECT id, option_id FROM cappe_inventory_adjustments WHERE option_id = ANY($1)",
            old_ids,
        ):
            ledger.setdefault(r["option_id"], []).append(r["id"])

    await conn.execute(
        "DELETE FROM cappe_product_option_groups WHERE product_id = $1 AND site_id = $2",
        product_id, site_id,
    )
    for gi, g in enumerate(groups):
        gid = await conn.fetchval(
            """INSERT INTO cappe_product_option_groups
                   (site_id, product_id, name, select_type, required, sort_order)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            site_id, product_id, g.name, g.select_type, g.required,
            g.sort_order if g.sort_order is not None else gi,
        )
        for oi, o in enumerate(g.options or []):
            inv = o.inventory if o.inventory is not None else prior_inv.get((g.name, o.name))
            new_oid = await conn.fetchval(
                """INSERT INTO cappe_product_options
                       (site_id, group_id, name, price_delta_cents, sort_order, inventory)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                site_id, gid, o.name, o.price_delta_cents,
                o.sort_order if o.sort_order is not None else oi, inv,
            )
            move = ledger.get(prior_oid.get((g.name, o.name)))
            if move:
                await conn.execute(
                    "UPDATE cappe_inventory_adjustments SET option_id = $1 WHERE id = ANY($2)",
                    new_oid, move,
                )
```

### 3.3 Busy feed must mirror the overlap rule

**File:** `server/app/cappe/routes/public/bookings.py` — `public_booking_slots`,
`booked` query (176-183). Must match `resolve_booking_slot`'s rule
(`services/commerce.py:317-331`): staffed → the person is busy anywhere
(no location narrowing); unstaffed → `(location, type)` slot via
`IS NOT DISTINCT FROM`.

```python
        booked = await conn.fetch(
            "SELECT starts_at, ends_at, staff_id FROM cappe_bookings "
            "WHERE site_id = $1 AND status IN ('pending', 'confirmed') "
            "AND (staff_id = ANY($4::uuid[]) "
            "     OR (staff_id IS NULL AND booking_type_id = $2 "
            "         AND location_id IS NOT DISTINCT FROM $3))",
            site["id"], type_id, location_id, list(offering_staff),
        )
```

(The old standalone `AND (location_id IS NULL OR location_id = $3)` line is
deleted — with `$3` NULL it evaluated NULL for every location-bound booking,
dropping them from `booked`.)

**Do NOT touch the `avail` query (164-168)** — its NULL-narrowing matches
`resolve_booking_slot`'s availability check (`commerce.py:295`). Add a
comment above it saying exactly that, so it doesn't get "fixed" later.

### 3.4 Real page count; never a zero-page site

**File:** `server/app/cappe/routes/sites.py` — `create_site_from_template`
(184-200).

```python
            inserted = 0
            for i, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                p_title = str(page.get("title") or f"Page {i + 1}")[:255]
                p_slug = slugify(page.get("slug") or p_title)
                page_id = await conn.fetchval(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, $2, $3, $4, $5, 'draft')
                       ON CONFLICT (site_id, slug) DO NOTHING
                       RETURNING id""",
                    site["id"], p_title, p_slug,
                    json.dumps(page.get("content") or {}),
                    int(page.get("sort_order", i)),
                )
                if page_id is not None:
                    inserted += 1
            if inserted == 0:
                # Same seed as create_site: a site with no cappe_pages row has
                # no homepage to edit (the exact problem create_site:138-146
                # exists to prevent).
                await conn.execute(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, 'Home', 'home', '{}', 0, 'draft')""",
                    site["id"],
                )
                inserted = 1

    return site_row_to_dict(site, page_count=inserted)
```

### 3.5 `receipt_prefix` is the one field that must clear

**File:** `server/app/cappe/routes/sites.py` — `update_site` (303-304).

```python
        if "receipt_prefix" in body.model_fields_set:
            # model_fields_set (like shipping_free_threshold_cents above) so an
            # explicit null CLEARS the prefix — it is the one nullable column
            # here (VARCHAR(12)). The neighbouring `is not None` gates are
            # CORRECT: tax_label / shipping_label / meta_config are NOT NULL
            # columns (zzzzcappe17:27, zzzzcappe29:31, zzzzcappe01:86) — do
            # not "fix" them.
            add("receipt_prefix", body.receipt_prefix or None)
```

### 3.6 404 vs 400 in `adjust_stock`

**File:** `server/app/cappe/routes/shop.py` — `adjust_stock` option branch
(281-300). `fetchval` conflates "no such variant" with "inventory IS NULL";
split exactly like the product branch (302-312):

```python
            if body.option_id is not None:
                vrow = await conn.fetchrow(
                    "SELECT o.id, o.inventory FROM cappe_product_options o "
                    "JOIN cappe_product_option_groups g ON g.id = o.group_id "
                    "WHERE o.id = $1 AND g.product_id = $2 AND o.site_id = $3 FOR UPDATE",
                    body.option_id, product_id, site_id,
                )
                if vrow is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
                if vrow["inventory"] is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="That variant isn't tracking stock — set a stock number on it first.",
                    )
                new_bal = max(0, vrow["inventory"] + body.delta)
                await conn.execute(
                    "UPDATE cappe_product_options SET inventory = $1 WHERE id = $2",
                    new_bal, body.option_id,
                )
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id, option_id=body.option_id,
                    delta=new_bal - vrow["inventory"], balance_after=new_bal,
                    reason=body.reason, note=body.note,
                )
```

---

## Phase 4 — write-on-read, and background-task-only paths

### 4.1 Take auto-approval off the list path

**`server/app/cappe/services/collab.py`** — add (bodies moved verbatim from
`routes/collab.py`, email imports added to the service module):

```python
async def resolve_contact(conn, offer_row, side: str) -> tuple[str, Optional[str]]:
    """(email, name) of the account OPPOSITE `side`. (Moved from
    routes/collab.py:_resolve_contact so worker tasks can notify without
    importing a router.)"""

async def notify_auto_approve(conn, offer_id: UUID, offer_row, result: dict) -> None:
    """Email the creator each approved deliverable and the brand each payment
    now due after an auto-approve — auto-approve must not fire payments in
    silence. (Moved from routes/collab.py:_notify_auto_approve; callers:
    routes' _offer_detail and the cappe_collab_auto_approve worker.)"""
```

Both use `dashboard_url` + the `send_cappe_*` senders from
`..services.email` (service→service import, fine). `offer_row` keys used:
`id`, `title`, `creator_profile_id`, `brand_account_id`, `brand_name`.

**`server/app/cappe/routes/collab.py`**:
- Delete `_notify_auto_approve` (91-115) and `_notify_auto_approve_bg`
  (118-125) bodies; keep thin wrappers where still referenced:

```python
async def _resolve_contact(conn, offer_row, side: str) -> tuple[str, Optional[str]]:
    return await svc.resolve_contact(conn, offer_row, side)
```

  (`_resolve_contact` has ~10 route callers — the wrapper avoids churning
  them. `_notify_auto_approve` keeps ONE caller, `_offer_detail:133` —
  switch that call to `await svc.notify_auto_approve(conn, offer_id, offer_row, result)`
  and drop the wrapper.)
- `list_offers` (317-398): delete the `background: BackgroundTasks` param,
  the `active_ids` loop (363-380) and the refresh block (381-392). What
  remains: fetch rows → `total` → build `OfferListItem`s → return.
- **Keep** `_offer_detail:131-134` unchanged (single-offer, bounded; this is
  what lets the sweep below ship disabled without regressing creator
  protection).

**New `server/app/workers/tasks/cappe_collab_auto_approve.py`** — modeled on
`cappe_booking_reminders.py` (scheduler row gate, `max_per_cycle` cap,
`get_db_connection()`, `asyncio.run`, `max_retries=1`):

```python
"""Celery task: Cappe collab auto-approve sweep.

Replaces the write-on-read auto-approve loop that used to run inside
GET /collab/offers (N active offers = N sequential money-mutating
transactions on a pooled connection shared with matcha + tellus).
The creator's own deal page (routes/collab.py:_offer_detail) still
auto-approves lazily on read — this sweep is the catch-up for offers
nobody opens. Gated by scheduler_settings['cappe_collab_auto_approve']
(default off).
"""
import asyncio
import logging

from app.cappe.services import collab as collab_svc

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_CYCLE = 50


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "cappe_collab_auto_approve")
        if not row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not row["enabled"]:
            print("[Cappe Collab Auto-Approve] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}
        cap = row["max_per_cycle"] or DEFAULT_MAX_PER_CYCLE
        if cap <= 0:
            cap = DEFAULT_MAX_PER_CYCLE

        offers = await conn.fetch(
            """SELECT o.*, ba.name AS brand_name
                 FROM cappe_collab_offers o
                 JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                WHERE o.status = 'active'
                ORDER BY o.last_action_at ASC
                LIMIT $1""",
            cap,
        )
        checked = len(offers)
        approved = 0
        for offer_row in offers:
            result = await collab_svc.auto_approve_overdue(conn, offer_row["id"])
            if result["deliverables"] or result["fired_payments"]:
                await collab_svc.notify_auto_approve(conn, offer_row["id"], offer_row, result)
                approved += 1
        return {"checked": checked, "auto_approved": approved}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_collab_auto_approve(self) -> dict:
    """Sweep active collab offers and auto-approve overdue deliverables."""
    print("[Cappe Collab Auto-Approve] Running scheduler...")
    try:
        result = asyncio.run(_run())
        print(f"[Cappe Collab Auto-Approve] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("[Cappe Collab Auto-Approve] Failed")
        raise self.retry(exc=exc, countdown=60)
```

(`auto_approve_overdue` opens its own `conn.transaction()` — valid on a raw
asyncpg connection. `SELECT o.*` + `ba.name AS brand_name` supplies every key
`notify_auto_approve` reads.)

### 4.2 Reconcile stranded `registering` domains

**New `server/app/cappe/services/domain_register.py`** — move
`finalize_domain_registration` (routes/domains.py:591-644) verbatim, with:
- imports: `logging`, `UUID`, `...database import connection_or_direct`,
  `..services.porkbun import PorkbunError, get_porkbun`,
  `..services.stripe_connect import CappeStripeError, get_cappe_stripe`,
  `..services.render_cache import invalidate_site_render_cache`;
- all three `async with get_connection()` → `async with connection_or_direct()`
  (worker is pool-free; `connection_or_direct` is the sanctioned both-worlds
  helper, `app/database/pool.py:110`);
- call `await invalidate_site_render_cache(row["site_id"])` (the Redis half)
  instead of the routes-level wrapper. Note in the docstring: the route-level
  `invalidate_render_cache` additionally clears the process-local
  `_host_cache`, but that cache only gates the trusted-host check with a 60s
  TTL (`routes/render.py:123-148`) — site resolution itself hits the DB, so
  a ≤60s host-gate lag on a freshly activated domain is acceptable and
  services/ must not import routes/.

Signature unchanged:

```python
async def finalize_domain_registration(domain_id: UUID) -> None:
```

**`server/app/cappe/routes/domains.py`**: delete the function body (591-644)
and the now-unused imports it exclusively used (check each: `PorkbunError`,
`get_porkbun`, `CappeStripeError`/`get_cappe_stripe` are still used elsewhere
in the file — `get_porkbun`/`PorkbunError` are, for search/connect/verify;
only drop what's truly orphaned). Add:

```python
from ..services.domain_register import finalize_domain_registration
```

The `background.add_task(finalize_domain_registration, did)` at 571 is the
only caller and keeps working.

**New `server/app/workers/tasks/cappe_domain_finalize.py`** — same template,
fail-closed, 15-minute grace so it never races the in-process task:

```python
"""Celery task: reconcile stranded Cappe domain registrations.

finalize_domain_registration is normally driven in-process from the Stripe
webhook's BackgroundTasks; a blue-green swap in that window leaves a PAID
domain in 'registering' forever (the event is claimed — Stripe won't retry;
nothing else sweeps that state). This task re-drives the finalizer for rows
stuck >15 minutes. Safe to repeat: pb.register is idempotent
(idempotency_key=str(domain_id)) and the finalizer self-terminates by
marking 'failed' + refunding on PorkbunError.
Gated by scheduler_settings['cappe_domain_finalize'] (default off).
"""
import asyncio
import logging

from app.cappe.services.domain_register import finalize_domain_registration

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_CYCLE = 20
STUCK_AFTER_MINUTES = 15


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "cappe_domain_finalize")
        if not row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not row["enabled"]:
            print("[Cappe Domain Finalize] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}
        cap = row["max_per_cycle"] or DEFAULT_MAX_PER_CYCLE
        if cap <= 0:
            cap = DEFAULT_MAX_PER_CYCLE

        stranded = await conn.fetch(
            "SELECT id FROM cappe_domains "
            "WHERE status = 'registering' AND updated_at < NOW() - ($1 * INTERVAL '1 minute') "
            "ORDER BY updated_at ASC LIMIT $2",
            STUCK_AFTER_MINUTES, cap,
        )
        redriven = 0
        for d in stranded:
            await finalize_domain_registration(d["id"])  # self-terminating
            redriven += 1
        return {"stranded": len(stranded), "redriven": redriven}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_domain_finalize(self) -> dict:
    """Re-drive finalization for domains stuck in 'registering'."""
    print("[Cappe Domain Finalize] Running scheduler...")
    try:
        result = asyncio.run(_run())
        print(f"[Cappe Domain Finalize] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("[Cappe Domain Finalize] Failed")
        raise self.retry(exc=exc, countdown=60)
```

(A leaked exception here is infra failure only — PorkbunError is caught
inside the finalizer. Task retry + `server_error_reports` capture via
`task_failure` is the right escalation.)

### 4.3 Registration + scheduler rows

**`server/app/workers/celery_app.py`**
- `include=` tuple (23-64): add
  `"app.workers.tasks.cappe_collab_auto_approve",` and
  `"app.workers.tasks.cappe_domain_finalize",` (next to the other cappe
  entries, line ~56). Do NOT copy the `cappe_domain_renewals` /
  `cappe_comp_expiry` pattern (they're missing from `include=` today and
  work only via dispatch-time importlib).
- `_SCHEDULED_TASKS` (148-186): add
  ```python
  ("cappe_collab_auto_approve", "app.workers.tasks.cappe_collab_auto_approve", "run_cappe_collab_auto_approve"),
  ("cappe_domain_finalize", "app.workers.tasks.cappe_domain_finalize", "run_cappe_domain_finalize"),
  ```

**New migration `server/alembic/versions/zzzzcappe30_cappe_worker_schedulers.py`**
(`revision = "zzzzcappe30"`, `down_revision = "zzzzcappe29"`, op.execute-only
like `zzzzcappe09:42-55`):

```python
def upgrade() -> None:
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES
            ('cappe_collab_auto_approve',
             'Cappe Collab Auto-Approve',
             'Auto-approves overdue collab deliverables and fires their payments (catch-up for the read-time path).',
             false, 50),
            ('cappe_domain_finalize',
             'Cappe Domain Finalize',
             'Re-drives domain registration for paid domains stuck in registering >15 minutes.',
             false, 20)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM scheduler_settings WHERE task_key IN ('cappe_collab_auto_approve', 'cappe_domain_finalize')")
```

Operator flips `enabled=true` after deploy; until then `_offer_detail`
covers auto-approval and domain finalization works on the happy path.

---

## Tests

Cappe tests are pure unit tests (no DB, no app boot) — follow the env-shim
pattern at `tests/cappe/test_cappe_route_helpers.py:10-23`.

### Extend `server/tests/cappe/test_cappe_route_helpers.py`

`build_patch(nullable=…)` (existing 5 tests must stay green — the default
`nullable=None` path is unchanged):

```python
def test_build_patch_nullable_allowlisted_null_passes():
    body = CappeStaffUpdate(bio=None)
    sets, args = build_patch(body, ("name", "bio", "location_id"), nullable={"bio"})
    assert sets == ["bio = $1"] and args == [None]

def test_build_patch_nullable_rejects_non_allowlisted_null():
    body = CappeStaffUpdate(name=None)
    with pytest.raises(HTTPException) as exc:
        build_patch(body, ("name", "bio"), nullable={"bio"})
    assert exc.value.status_code == 422
    assert "name" in exc.value.detail

def test_build_patch_nullable_names_every_bad_field():
    body = CappeStaffUpdate(name=None, active=None)  # active NOT NULL too
    with pytest.raises(HTTPException) as exc:
        build_patch(body, ("name", "bio", "active"), nullable={"bio"})
    assert "name" in exc.value.detail and "active" in exc.value.detail

def test_build_patch_nullable_none_keeps_legacy_null_clear():
    body = CappeStaffUpdate(name=None)
    sets, args = build_patch(body, ("name", "bio"))  # nullable omitted
    assert sets == ["name = $1"] and args == [None]
```

(Check `CappeStaffUpdate` field types first — if `active` isn't nullable-able
Optional, swap that test to another NOT NULL Optional field on the model.)

### New `server/tests/cappe/test_cappe_upload_guard.py`

The matrix that matters (pure functions, no mocks needed):

| case | declared | bytes | expect |
|---|---|---|---|
| svg-as-png | `image/png` | `b"<svg xmlns='http://www.w3.org/2000/svg'>..."` | 400 |
| html-as-jpeg | `image/jpeg` | `b"<!doctype html><script>..."` | 400 |
| real png | `image/png` | `b"\x89PNG\r\n\x1a\n" + b"\x00"*16` | returns `image/png` |
| real jpeg | `image/jpeg` | `b"\xff\xd8\xff\xe0" + ...` | `image/jpeg` |
| real gif | `image/gif` | `b"GIF89a" + ...` | `image/gif` |
| real webp | `image/webp` | `b"RIFF\x00\x00\x00\x00WEBP" + ...` | `image/webp` |
| real pdf | `application/pdf` | `b"%PDF-1.7\n..."` | `application/pdf` |
| real zip | `application/zip` | `b"PK\x03\x04" + ...` | `application/zip` |
| docx-as-zip-magic | docx MIME | `b"PK\x03\x04" + ...` | returns the docx MIME |
| real OLE doc | `application/msword` | `b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + ...` | `application/msword` |
| real mp4 | `video/mp4` | `b"\x00\x00\x00\x18ftypmp42" + ...` | `video/mp4` |
| mov declared mp4 | `video/mp4` | ftyp `qt  ` brand | accepted (`video/mp4`) |
| real webm | `video/webm` | `b"\x1aE\xdf\xa3" + ...` | `video/webm` |
| csv normalized | `text/csv` | `b"a,b\n1,2\n"` | returns `text/plain` |
| text/plain | `text/plain` | `b"hello"` | `text/plain` |
| empty | `image/png` | `b""` | 400 |
| truncated | `image/png` | `b"\x89"` | 400 |
| not in allowlist | `image/svg+xml` | anything | 400 |
| magic mismatch | `image/gif` | real PNG bytes | 400 |
| image allowlist rejects pdf | `application/pdf` w/ `ALLOWED_IMAGE` | real PDF | 400 |

Plus direct `sniff()` unit cases for each magic and `sniff(b"") is None`.

### New `server/tests/cappe/test_cappe_option_groups.py`

`_replace_option_groups` ledger re-pointing with a fake conn recording
statements:

```python
class _FakeConn:
    """Records execute/fetchval calls; serves canned prior-option and
    ledger rows. _replace_option_groups only uses fetch/fetchval/execute."""
    # fetch: prior-options query -> canned rows; ledger snapshot -> canned rows
    # fetchval: group INSERT -> uuid; option INSERT -> fresh uuid (recorded)
    # execute: record (sql, args)
```

Cases:
1. **Re-point fires**: prior option `("Grp","Opt")` with inventory and one
   adjustment row; incoming groups contain `("Grp","Opt")` → assert an
   `UPDATE cappe_inventory_adjustments SET option_id = $1 WHERE id = ANY($2)`
   was executed with the NEW option uuid and the adjustment id.
2. **Renamed option does not re-point**: incoming `("Grp","Opt2")` → no
   ledger UPDATE executed (old adjustments stay SET NULL — correct, the
   variant is gone).
3. **`groups=None` is a no-op**: zero statements.
4. **Inventory carry-over still works** (regression guard for the existing
   behavior): incoming option omits inventory → INSERT arg carries prior value.

### Not unit-testable (documented, manual)

The four CAS changes, the webhook claim release, and both worker tasks need
a DB/Stripe — covered by the manual checklist below.

---

## Verification

**Automated**

```bash
cd server && ./venv/bin/python -m pytest tests/cappe/ -q
```

All pre-existing tests must stay green (especially the 5 legacy
`build_patch` tests). Post-edit hook handles `py_compile` per file.

**Manual, against local dev** (`./scripts/dev-remote.sh`, `matcha-postgres`)

1. `PATCH /api/cappe/sites/{id}/staff/{sid}` with `{"name": null}` → **422**
   naming `name` (was 500).
2. `POST …/campaigns/{id}/send` twice in quick succession → one 200, one
   **409**; exactly one Celery dispatch in worker logs.
3. `POST /api/cappe/sites/{id}/upload` with an SVG renamed `.png`,
   `Content-Type: image/png` → **400**; a real PNG → 200 and the S3 object's
   ContentType is `image/png`.
4. Multi-location site, shared availability, a booking bound to a location:
   `GET /public/sites/{slug}/booking-types/{tid}/slots` with NO
   `location_id` → that time is ABSENT from `slots` (today it appears, then
   409s at booking).
5. `POST …/sites/from-template` with a template whose `structure.pages` is
   `[]` → site has one `Home` page, response `page_count == 1`.
6. `PUT /sites/{id}` with `{"receipt_prefix": null}` → prefix cleared
   (today only `""` clears it).
7. `POST …/products/{pid}/adjust` with a bogus `option_id` → **404**; with a
   real untracked variant → **400** "set a stock number".
8. Edit a product's option_groups on a variant that has inventory-log rows →
   `GET …/inventory-log` still attributes them (option_id not NULL).
9. Both new tasks: `UPDATE scheduler_settings SET enabled=true WHERE
   task_key IN ('cappe_collab_auto_approve','cappe_domain_finalize')` on dev,
   `docker restart matcha-worker`, confirm `[Worker] scheduler dispatch —
   dispatched=…` lists both and the tasks log `Completed: {...}`.

**Not verifiable without prod Stripe** — the four CAS changes and the webhook
claim release are read-and-reason plus the `stripe listen`/CLI replay path:
`stripe trigger checkout.session.completed` against dev with a bogus
`order_id` should now **503** (retryable) rather than 200.

---

## Out of scope (flagged in review, do NOT fix here)

- `cappe_inventory_adjustments`'s two `ON DELETE CASCADE` FKs (deleting a
  product still erases history).
- No `Content-Disposition: attachment` on deliverable downloads.
- `services/inventory.py:36` dead ternary.
