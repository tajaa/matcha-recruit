Updated plan
Wrote 342 lines to /Users/finch/.claude/plans/modular-sprouting-babbage.md

# Fix the 15 `/code-review xhigh` findings in `server/app/cappe/routes/`

## Context

An xhigh code review of all 33 modules under `server/app/cappe/routes/` returned 15
findings. Verifying each against the actual source (routes, models, migrations,
services, workers) confirmed 13 as written, corrected 2, and surfaced 3 adjacent
bugs of the same shape that the review missed.

The severe cluster is **money paths**: four read-then-write races with no
compare-and-swap on the UPDATE (collab checkout, deliverable revision, campaign
send), and one Stripe webhook that permanently strands a paid order because it
holds the dedupe claim while matching nothing. Money has already moved in every
one of those scenarios; the DB just disagrees.

Outcome: every money-mutating UPDATE becomes a guarded CAS, the webhook releases
its claim when it cannot match, uploads stop trusting the client's
`Content-Type`, `build_patch` stops writing `NULL` into `NOT NULL` columns, and
the two "only ever driven by an in-process background task" paths get worker
reconciliation.

### Two review claims corrected

| Review said                                             | Actual                                           |
| ------------------------------------------------------- | ------------------------------------------------ |
| `shop.py:425` (orders PATCH) 500s on `{"status": null}` | **Already guarded.** `CappeOrderStatusUpdate.\_v |

alidate_fields` (`models/shop.py:216-223`) rejects explicit-null `status`. The real exposure is the *other*
 7 `build_patch` callers — incl. 3 the review never named (`blog.py:67`, `shop.py:223`, `creators.py:142`).
 |
| `sites.py:296`—`tax_label`, `shipping_label`, `meta_config`can never be cleared | **Not bugs.** All th
ree are`NOT NULL` (`zzzzcappe17:27`, `zzzzcappe29:31`, `zzzzcappe01:86`), so `is not None`is correct ther
e. Only`receipt_prefix` (`VARCHAR(12)`, nullable) is real. |

---

## Phase 1 — money-path correctness

### 1.1 `collab.py:720` — CAS the post-Stripe payment UPDATE

`checkout_payment` releases the connection, does a ~1s Stripe round-trip, then
writes `status='processing' WHERE id=$1` unconditionally — reverting a payment
the Connect webhook (`payments.py:237`) may have already marked `paid`.

Add `AND status IN ('due','processing')` + `RETURNING id`; on `None`, log and
raise 409 rather than handing back a session URL for a settled installment.
(Add a module `logger` to `collab.py` if absent.)

### 1.2 `payments.py:206-215` — release the claim when the order does not match

The claim at line 145 blocks Stripe's retry; the no-match branch returns 200. Net
effect: charged customer, order stuck `pending`, no receipt, forever — the exact
failure the `release_stripe_event` wrapper's own comment says it prevents.

Replace the bare `logger.warning` with a disambiguating lookup:

```python
already = await conn.fetchval(
    """SELECT o.status FROM cappe_orders o
         JOIN cappe_sites s ON s.id = o.site_id
         JOIN cappe_accounts a ON a.id = s.account_id
        WHERE o.id = $1 AND a.stripe_account_id = $2""",
    oid, event_account_id,
)
```

- row found (`'paid'`/`'refunded'`/…) → genuinely idempotent, keep the claim, 200.
- `None` → raise (503). The `except Exception` at `payments.py:152` releases the
  claim and Stripe retries. Never silently 200.

Also log a warning when `event_account_id` is falsy — today that skips the whole
order branch with no signal.

### 1.3 `collab.py:664` — CAS + lock the revision request

`approve_deliverable` does a proper CAS (`AND status='submitted'`, in a
transaction, line 612); `request_deliverable_revision` does a read-then-write with
no transaction, no lock, and `WHERE id=$1` only. Two effects: it overwrites an
`approved` deliverable whose payment is already `due`, and two concurrent
requests both pass the `revision_count >= revision_rounds` check and both
increment.

Wrap 651-668 in `async with conn.transaction():`, make the read
`... WHERE id=$1 AND offer_id=$2 FOR UPDATE`, and add `AND offer_id=$2 AND
status='submitted'` to the UPDATE with a 409 on `None`.

### 1.4 `newsletter.py:187` — CAS the campaign send (both directions)

`WHERE id=$1 AND site_id=$2` with no status predicate: a double-click dispatches
`run_cappe_campaign_send.delay()` twice and every subscriber gets the campaign
twice. `shop.py:415-422` is the in-repo reference (`FOR UPDATE` inside a
transaction).

- Send UPDATE: `AND status NOT IN ('sent','sending')`, 409 on `None`.
- The Celery-failure revert at 199-203 has the same hole — add `AND
status='sending'` so it can't stomp a `sent` written by a racing worker.

### 1.5 `payments.py:244` — drop `cp.amount_cents = $5` from the collab match

`cp.id` comes from this event's own trusted metadata and the `ca.stripe_account_id`
join already proves ownership; the amount equality adds no authorization and
converts any Stripe-side total adjustment (automatic tax, promo code, shipping
line) into an unrecoverable "charged but not matched" ERROR.

Remove the predicate (renumber params), add `cp.amount_cents` to `RETURNING`, and
after a match log a WARNING when it differs from `amount_total` — an audit
signal instead of a lost payment. Leave the `else` ERROR branch as-is; with the
equality gone its only remaining cause is a genuinely cancelled payment.

### 1.6 `billing.py:277` — guard the null `stripe_subscription_id`

`change_plan` (line 355) and `cancel` (line 445) both check
`not sub["stripe_subscription_id"]`; `set_addon_quantity` does not, so a
mid-sync subscription passes `None` to Stripe and the customer gets a 502
"Could not update add-on" instead of the actionable 409.

Split the guard: keep the 402 for `not sub or source != 'stripe'`, add a 409
`"Subscription is still syncing — try again in a moment."` mirroring
`change_plan:393-397`.

**Files:** `routes/collab.py`, `routes/payments.py`, `routes/newsletter.py`,
`routes/billing.py`.

---

## Phase 2 — upload MIME is client-controlled (security)

`uploads.py:77` validates `file.content_type` (an attacker-authored multipart
part header) against `_ALLOWED`, then `uploads.py:84` hands that _same_ string to
`storage.upload_file` as the S3 object's `ContentType`. So an HTML/SVG body sent
as `Content-Type: image/png` is stored and served as `image/png` from the tenant
origin, whose `TENANT_CSP` (`render.py:45`) allows `script-src 'unsafe-inline'`.
The comment at `uploads.py:42-44` reasons explicitly about SVG being a stored-XSS
vector and then blocks it only by the header the attacker controls.
`creators.py:304` has the same hole and duplicates the allowlists.

Repo has **no** image-sniffing helper to reuse (the only magic-byte check is the
RIFF/WAVE one in `ir_incidents/_shared.py:120`, audio-only).

**New `server/app/cappe/services/upload_guard.py`** — owns the allowlists
(moved out of `uploads.py` / `creators.py`, killing the duplication) plus:

```python
def sniff(data: bytes) -> Optional[str]:
    """Content type implied by the leading bytes; None when the format has no
    magic number (text/*) or the bytes are unrecognized."""
    # RIFF....WEBP; ISO-BMFF 'ftyp' at offset 4 (mp4/mov); then a prefix table:
    #   jpeg ff d8 ff | png 89 PNG\r\n\x1a\n | gif GIF87a/GIF89a | pdf %PDF-
    #   zip PK\x03\x04 (also docx/xlsx) | ole \xd0\xcf\x11\xe0 (doc/xls)
    #   webm/matroska \x1aE\xdf\xa3

def verify_upload(data: bytes, declared: Optional[str], allowed: set[str]) -> str:
    """Return the content type to store, or raise 400. Declared type must be in
    `allowed` AND be backed by the bytes. Textual formats have no magic number,
    so they are normalized to text/plain — a mislabelled SVG/HTML payload can
    then never be served as an active type."""
```

`_EXPECTED` maps each declared type to the sniff result(s) that back it
(`docx`/`xlsx` → `application/zip`; `doc`/`xls` → OLE; `mp4`↔`quicktime` share
`ftyp`; `text/plain`/`text/csv` → empty set → stored as `text/plain`).

Wire into all four upload endpoints — `uploads.py` `upload_image` /
`upload_deliverable` / `upload_video`, and `creators.py:292` — keeping the cheap
declared-type check before `read_capped` (so a bogus type still 400s without
reading 25 MB) and passing the **returned** type to `upload_file`, never
`file.content_type`.

---

## Phase 3 — data integrity

### 3.1 `_shared.py:105` — teach `build_patch` about nullability

`model_fields_set` semantics mean an explicit JSON `null` becomes `col = NULL`.
Across the 8 callers that reaches 28 `NOT NULL` columns → raw
`NotNullViolationError` → unhandled 500. `admin_billing.py:43-48` already solved
this with a `_NULLABLE_FIELDS` allowlist + 422; generalize that rather than
copying it 8 times.

```python
def build_patch(body, cols, start=0, *, nullable: Optional[Collection[str]] = None):
```

When `nullable` is given, any sent-null column outside it raises 422
`"These fields cannot be null: …"`. Default `None` keeps today's behavior so the
existing tests in `tests/cappe/test_cappe_route_helpers.py:26-66` stay valid.

Allowlists (derived from the migrations; everything else on each table is `NOT NULL`):

| callsite                             | table                    | `nullable=`                                                              |
| ------------------------------------ | ------------------------ | ------------------------------------------------------------------------ |
| `newsletter.py:141`                  | `cappe_campaigns`        | `body_html, from_name, scheduled_at`                                     |
| `bookings.py:165`                    | `cappe_booking_types`    | `description, price_cents, category, location_id`                        |
| `staff.py:100`                       | `cappe_staff`            | `bio, image_url, location_id`                                            |
| `locations.py:148`                   | `cappe_locations`        | `address, lat, lng, timezone, contact_phone, contact_email`              |
| `blog.py:67`                         | `cappe_posts`            | `excerpt, body, cover_image_url`                                         |
| `shop.py:223`                        | `cappe_products`         | `description, image*url, sku, inventory, low_stock_threshold, digital*   |
| file_url, booking_type_id, category` |
| `creators.py:142`                    | `cappe_creator_profiles` | `avatar_url, cover_url, bio, location`                                   |
| `shop.py:425`                        | `cappe_orders`           | `carrier, tracking_number` (already model-guarded; pass for consistency) |
|                                      |

### 3.2 `shop.py:100` — stop orphaning the per-variant stock ledger

`_replace_option_groups` DELETEs every option group on any edit that sends
`option_groups`; `cappe_inventory_adjustments.option_id` is `ON DELETE SET NULL`
(`zzzzcappe18:38`), so a price edit silently unattributes every historical
variant adjustment. The function already carries `inventory` across the replace
keyed on `(group name, option name)` — reuse that key for the ledger.

Extend the `prior` fetch to also select `o.id`; before the DELETE, snapshot
`SELECT id, option_id FROM cappe_inventory_adjustments WHERE option_id = ANY($1)`
into `old_option_id -> [adjustment ids]`. Make the option INSERT `RETURNING id`
and re-point the snapshotted rows onto the new id.

### 3.3 `public/bookings.py:176-183` — busy feed must mirror the overlap rule

`(location_id IS NULL OR location_id = $3)` with `$3` NULL evaluates to NULL for
every location-bound booking, so they drop out of `booked` and render as open
chips that then 409 at `resolve_booking_slot`. Match that function's actual rule
(`services/commerce.py:317-331`) per branch instead:

```sql
AND ( staff_id = ANY($4::uuid[])                    -- a person is busy anywhere
   OR (staff_id IS NULL AND booking_type_id = $2
       AND location_id IS NOT DISTINCT FROM $3) )   -- unstaffed: (location, type) slot
```

**Do not** apply the same change to the `avail` query at line 164-168 — its
NULL-narrowing matches `resolve_booking_slot`'s own availability check
(`commerce.py:295`), so widening it would generate slots that then fail to book.
Add a comment saying so.

### 3.4 `sites.py:184-200` — real page count, and never a zero-page site

`page_count=len(pages)` over-reports whenever the loop `continue`s on a non-dict
entry or `ON CONFLICT DO NOTHING` swallows a duplicate slug; a template with an
empty/malformed `pages` list creates a site with no `cappe_pages` row at all —
the missing-homepage problem `create_site:138-146` exists to prevent.

Add `RETURNING id` to the page INSERT, count actual insertions, and when the
count is 0 seed the same `'Home'` page `create_site` does. Return the real count.

### 3.5 `sites.py:303` — `receipt_prefix` is the one field that must clear

Switch it to `"receipt_prefix" in body.model_fields_set` (like
`shipping_free_threshold_cents` at line 298). Today `body.receipt_prefix or None`
means empty-string clears it but explicit `null` does not. Add a comment stating
that the neighbouring `is not None` gates are correct because those columns are
`NOT NULL` — so nobody "fixes" them later.

### 3.6 `shop.py:282-292` — 404 vs 400 in `adjust_stock`

`fetchval` conflates "no such variant / not this product's" with
"`inventory IS NULL`", so an owner told to "set a stock number on it first"
follows the instruction and hits the same error forever. Switch to `fetchrow`
selecting `o.id, o.inventory` and split the two cases — exactly what the product
branch at 302-312 already does.

---

## Phase 4 — write-on-read, and paths only a background task drives

### 4.1 `collab.py:363-392` — take auto-approval off the list path

A brand with 100 active offers turns `GET /collab/offers` into 100+ sequential
money-mutating transactions plus a re-read, all holding one of the ten pooled
connections shared with matcha and tellus.

- **Remove** the `active_ids` loop and the refresh block from `list_offers`
  (and its now-unused `background` param).
- **Keep** `_offer_detail:131-134` — single offer, bounded, and it is the
  creator's own deal page. This is deliberate: it means the sweep below can ship
  disabled without regressing the creator protection.
- **Move** `_resolve_contact` and `_notify_auto_approve` from `routes/collab.py`
  into `services/collab.py` (next to `auto_approve_overdue`) so a worker can call
  them without importing a router. Route keeps thin wrappers.
- **New** `server/app/workers/tasks/cappe_collab_auto_approve.py` — modeled on
  `cappe_booking_reminders.py` (`scheduler_settings_row` + `max_per_cycle` cap,
  `get_db_connection()`, `asyncio.run`, `max_retries=1`): select active offers
  oldest-`last_action_at` first, call `auto_approve_overdue(conn, id)`, notify on
  a non-empty result.

### 4.2 `domains.py:571` — reconcile stranded `registering` domains

`finalize_domain_registration` is driven from exactly one place, a
`BackgroundTasks.add_task` after the webhook 200. A blue-green swap in that
window (routine) leaves a paid domain in `registering` forever: Stripe will not
retry (the event is claimed), and nothing sweeps that state
(`cappe_domain_renewals` only touches `active`/`expired`).

- **Move** `finalize_domain_registration` out of the router into
  `server/app/cappe/services/domain_register.py` (per
  `server/CLAUDE.md`: no helpers in route files when a service exists);
  `routes/domains.py` imports it.
- Swap its three `async with get_connection()` for
  `async with connection_or_direct()` — the sanctioned both-worlds helper
  (`app/database/pool.py:110`), since the worker is pool-free.
- **New** `server/app/workers/tasks/cappe_domain_finalize.py` — same template,
  fail-closed, selecting `status='registering' AND updated_at < NOW() -
INTERVAL '15 minutes'` (grace so it never races the in-process task) and
  re-driving the finalizer. Safe to repeat: `pb.register` already passes
  `idempotency_key=str(domain_id)`, and the finalizer self-terminates by marking
  `failed` + refunding on `PorkbunError`.

### 4.3 Registration + scheduler rows

Both tasks go in **both** lists in `app/workers/celery_app.py` — the `include=`
tuple (23-64) and `_SCHEDULED_TASKS` (148-186). Note `cappe_domain_renewals` and
`cappe_comp_expiry` are missing from `include=` today and work only via the
dispatch-time `importlib`; do not copy that.

Small Alembic migration seeding two `scheduler_settings` rows
(`cappe_collab_auto_approve`, `cappe_domain_finalize`) with `enabled=false`,
`INSERT … ON CONFLICT DO NOTHING`. Operator flips them on after deploy — until
then `_offer_detail` still covers auto-approval and domain finalization still
works on the happy path.

---

## Verification

Cappe tests are pure unit tests (no DB), so coverage splits:

**Automated**

```bash
cd server && ./venv/bin/python -m pytest tests/cappe/ -q
```

- `tests/cappe/test_cappe_route_helpers.py` — new `build_patch(nullable=…)` cases:
  allowlisted null passes; non-allowlisted null raises 422 naming the field;
  `nullable=None` unchanged (the 5 existing tests must stay green).
- **new** `tests/cappe/test_cappe_upload_guard.py` — the matrix that matters:
  SVG bytes declared `image/png` → 400; HTML declared `image/jpeg` → 400; real
  PNG/JPEG/GIF/WEBP/PDF/ZIP/OLE/mp4/webm headers → accepted with the right stored
  type; `text/csv` → stored as `text/plain`; empty/truncated bytes → 400.
- `_replace_option_groups` ledger re-pointing with a fake conn recording
  statements (assert the `UPDATE cappe_inventory_adjustments` fires with the new
  option id).

**Manual, against local dev** (`./scripts/dev-remote.sh`, `matcha-postgres`)

- `PATCH /api/cappe/sites/{id}/staff/{sid}` with `{"name": null}` → 422, not 500.
- `POST …/campaigns/{id}/send` twice in quick succession → one 200, one 409; one
  Celery dispatch.
- `POST /api/cappe/sites/{id}/upload` with an SVG renamed `.png` and
  `Content-Type: image/png` → 400.
- Multi-location site, shared availability, a booking bound to a location:
  `GET /public/sites/{slug}/booking-types/{tid}/slots` with **no** `location_id`
  → that time is absent from `slots` (it appears today, then 409s).
- `POST …/from-template` with a template whose `structure.pages` is `[]` → site
  has one `Home` page and `page_count == 1`.
- Both new tasks: seed the `scheduler_settings` row enabled on dev, then
  `docker restart matcha-worker` and confirm `[Worker]` dispatch lines plus the
  expected DB transitions.

**Not verifiable without prod Stripe** — the four CAS changes and the webhook
claim release are read-and-reason plus the `stripe listen`/CLI replay path;
`stripe trigger checkout.session.completed` against dev with a bogus `order_id`
should now 503 (retryable) rather than 200.

## Out of scope (flagged, not fixed)

- `cappe_inventory_adjustments`'s two `ON DELETE CASCADE` FKs undercut the
  "append-only audit" docstring — deleting a product still erases its history.
- No `Content-Disposition: attachment` on deliverable downloads.
- `services/inventory.py:36`'s `(note or None) if note is None else note[:1000]`
  is a dead ternary (empty string stores `""`, not `NULL`).
