# Cappe: Physical-goods shipping via Stripe — implementation spec

Transcription-grade: every edit gives the anchor (exact existing code to locate) and the complete final code (no ellipses). Execute steps in order; each step compiles independently (post-edit hook runs `py_compile`). Repo mirror of this spec: `CAPPE_SHIPPING_PLAN.md` (update the mirror when this changes).

## Context

Cappe (Gummfit storefronts) has real Stripe Connect checkout, inventory decrement, per-site tax, and an order status enum — but a `physical` product checks out identically to a digital one: no shipping address collected, no shipping cost, no carrier/tracking. This spec completes the physical-goods loop.

**Locked decisions** (confirmed with user):
- Address collected **by Stripe** (`shipping_address_collection` on the Checkout Session), persisted from the webhook. No storefront form changes.
- Shipping is a **flat per-site rate** with optional free-shipping threshold — mirrors the tax pattern (`cappe_sites` columns + settings card).
- **Carrier + tracking number** on orders, editable in admin Orders page.
- Platform fee stays on **subtotal only** (shipping, like tax, passes through to the merchant).

## Verified codebase facts

- Order creation entry: `create_public_order(site, body, background)` at `server/app/cappe/services/commerce.py:339`. `line_rows` tuple (:480-483): `(product_id, title, unit_price, qty, fulfillment, intake, booking_id, opt_snapshot, sel_ids)` — fulfillment index 4. Site-config fetch :499-501; tax math :502-506; order INSERT :507-516 (`$1`-`$9`); Stripe branch :539-592 (`pay_total = order["subtotal_cents"]` :539, fee :550, session call :574-583, `CappeStripeError` fallback :591-592); manual fallback :594-612.
- `create_checkout_session` at `services/stripe_connect.py:103-148` (kwargs-only, `_create()` closure :128-143). `retrieve_account` :90-100 is the retrieve-helper pattern.
- Webhook `_handle_connect_event(etype, obj, event, background)` at `routes/payments.py:152`; order UPDATE :174-186 (`$1`=oid, `$2`=payment_intent, `$3`=fee, `$4`=event_account_id). **`payments.py` has no `json` import** — add one. Event claim/release dedupe :135-149 must stay untouched. Webhook route: `@router.post("/payments/webhook")` at :112, mounted under `/api/cappe`.
- **`build_patch(body, cols, start=0)` at `routes/_shared.py:105`** — the repo's `model_fields_set`-driven dynamic-SET helper (explicit `null` clears, absent leaves untouched). Already used by `shop.py:209`, `blog.py:67`, `bookings.py:165`, `locations.py:148`, `newsletter.py:141`. Order-PATCH rewrite uses it (Step 5e).
- Site update route is `@router.put("/sites/{site_id}")` at `routes/sites.py:248` (PUT, not PATCH — `TaxSettingsCard` calls `cappeApi.put`). Hand-rolled `add()` helper :260-262 is that function's local convention — extend it, don't switch it to `build_patch`. `receipt_prefix` branch :294-295. `_SITE_COLS` :50-56.
- `site_row_to_dict` at `routes/_shared.py:88-95` is a generic `dict(row)` + theme/meta JSONB decode — new `_SITE_COLS` entries flow through with **no edit needed**.
- `models/shop.py` pydantic import (:7): `BaseModel, EmailStr, Field` only — add `field_validator, model_validator`. `CappeOrderStatusUpdate` :196-197. `CappeOrder` :157-176. `CappeOrderReceipt` :243-251.
- `routes/shop.py`: `_ORDER_COLS` :46-51; `_ITEM_COLS` :52-55; `_order_row` :110-114 (decodes `metadata` via `loads`); `update_order_status` :394-422; restock sets `_RESTOCK_FROM_STATUSES`/`_RESTOCK_TO_STATUSES` :36-37.
- JSONB helpers `services/common.py`: `loads()` :60 (NULL→`{}` — use `loads(x) or None` where None must survive), `loads_list()` :73.
- Receipt `services/receipt.py`: `import json` already present (:12); `render_order_receipt_pdf` SELECT :149-156; `build_receipt_html` :89-143.
- Public buyer endpoint `GET /public/orders/{token}` at `routes/public/shop.py:97-145`; SELECT :104-108.
- Migration head of cappe chain: `zzzzcappe27` (`zzzzcappe27_merlin_setup_concierge.py`). Idempotent-DDL convention per `zzzzcappe18_inventory.py`.
- Tests `server/tests/cappe/`: **pure-function only** (no DB/app boot; `os.environ.setdefault` preamble per `test_cappe_commerce.py`). All new logic that needs tests is extracted into pure helpers. `build_receipt_html` import pulls WeasyPrint via `core/services/pdf` — installed in the server venv, import-safe.
- Frontend `client/src/cappe/`: `types.ts` `CappeSite` :51-77 (`tax_rate_bps` :65), `CappeOrder` :345-365 (`tax_cents` :352). `TaxSettingsCard.tsx` is the settings-card template. `Shop.tsx` imports it :6, renders :133. `Orders.tsx`: lucide import :3, `setStatus` :51-54, expanded panel `{openId === o.id && (` :126, panel div :127.
- Storefront widget `server/app/cappe/services/render/assets/store.js` (76 lines): buy panel `info.innerHTML` built at :34-42.

## File-touch manifest

| # | File | Change |
|---|---|---|
| 1 | `server/alembic/versions/zzzzcappe28_shipping.py` | **new** — 7 columns |
| 2 | `server/app/cappe/services/commerce.py` | `compute_shipping_cents` + shipping math + INSERT + session kwargs |
| 3 | `server/app/cappe/services/stripe_connect.py` | countries const, `build_shipping_options`, session params, `retrieve_checkout_session` |
| 4 | `server/app/cappe/routes/payments.py` | `import json`, `extract_shipping_details`, address persist in webhook |
| 5 | `server/app/cappe/models/shop.py` + `routes/shop.py` | order model fields, PATCH model + rewrite via `build_patch` |
| 6 | `server/app/cappe/services/receipt.py` | shipping row + Ship-to block in PDF |
| 7 | `server/app/cappe/routes/public/shop.py` + `models/shop.py` | tracking in public status (no address) |
| 8 | `server/app/cappe/models/sites.py` + `routes/sites.py` | site shipping settings |
| 9 | `client/src/cappe/` | `types.ts`, **new** `ShippingSettingsCard.tsx`, `Shop.tsx`, `Orders.tsx` (+ optional `store.js` hint) |
| 10 | `server/tests/cappe/test_cappe_shipping.py` | **new** — full listing below |

---

## Step 1 — Migration (new file `server/alembic/versions/zzzzcappe28_shipping.py`)

Complete file:

```python
"""cappe: physical-goods shipping — per-site flat rate, order address + tracking

- cappe_sites.shipping_flat_cents / shipping_free_threshold_cents / shipping_label:
  flat per-site shipping applied to carts containing physical lines
  (NULL threshold = no free-shipping threshold).
- cappe_orders.shipping_cents: charged shipping, folded into total_cents.
- cappe_orders.shipping_address: Stripe shipping_details persisted verbatim
  (JSONB; read only for display — nothing filters/joins on it).
- cappe_orders.carrier / tracking_number: fulfillment tracking, owner-edited.

Revision ID: zzzzcappe28
Revises: zzzzcappe27
Create Date: 2026-08-02
"""
from alembic import op

revision = "zzzzcappe28"
down_revision = "zzzzcappe27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_flat_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_free_threshold_cents INTEGER")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_label VARCHAR(40) NOT NULL DEFAULT 'Shipping'")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS shipping_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS shipping_address JSONB")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS carrier VARCHAR(40)")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS tracking_number VARCHAR(120)")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS tracking_number")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS carrier")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_address")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_cents")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_label")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_free_threshold_cents")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_flat_cents")
```

**⚠️ Author + commit only. Do NOT run `alembic upgrade` — user applies via `migrate-dev.sh`/`migrate-prod.sh`.** Commit the migration before applying to ANY database (server/CLAUDE.md rule). Migration must be applied before the code deploys (code INSERTs/SELECTs the new columns) — and the blast radius is bigger than shipping alone: `_SITE_COLS` (Step 8c) gains three columns that flow through every `GET`/`PUT /sites/{site_id}`, so an unmigrated DB 500s on the **whole Cappe site-settings surface**, not just the shop tab.

## Step 2 — `server/app/cappe/services/commerce.py`

**2a — new pure function.** Anchor: insert directly after `order_subtotal` (ends :44). Add:

```python
def compute_shipping_cents(
    *, has_physical: bool, goods_subtotal_cents: int, flat_cents: int,
    free_threshold_cents: int | None,
) -> int:
    """Flat per-site shipping for carts with a paid physical line; zero when the
    free-shipping threshold is met. Both the gate and the threshold compare the
    GOODS subtotal (physical lines, pre-tax) — the same base the tax math uses,
    and what "free shipping over $50" means to a buyer. A goods subtotal of 0
    (giveaway item, or a cart Stripe will never charge for) never ships paid."""
    if not has_physical or flat_cents <= 0 or goods_subtotal_cents <= 0:
        return 0
    if free_threshold_cents is not None and goods_subtotal_cents >= free_threshold_cents:
        return 0
    return flat_cents
```

**2b — site config + totals.** Anchor: block :499-506 starting `tax_cfg = await conn.fetchrow(` and ending `total_cents = subtotal + tax_cents`. Replace with:

```python
            tax_cfg = await conn.fetchrow(
                "SELECT tax_rate_bps, tax_label, shipping_flat_cents, "
                "shipping_free_threshold_cents, shipping_label "
                "FROM cappe_sites WHERE id = $1", site["id"]
            )
            tax_rate_bps = int(tax_cfg["tax_rate_bps"]) if tax_cfg else 0
            tax_label = (tax_cfg["tax_label"] if tax_cfg else None) or "Tax"
            taxable = sum(unit * qty for (_p, _t, unit, qty, f, *_r) in line_rows if f == "physical")
            tax_cents = (taxable * tax_rate_bps) // 10000 if tax_rate_bps > 0 else 0
            has_physical = any(f == "physical" for (_p, _t, _u, _q, f, *_r) in line_rows)
            shipping_cents = compute_shipping_cents(
                has_physical=has_physical,
                goods_subtotal_cents=taxable,
                flat_cents=int(tax_cfg["shipping_flat_cents"]) if tax_cfg else 0,
                free_threshold_cents=tax_cfg["shipping_free_threshold_cents"] if tax_cfg else None,
            )
            shipping_label = (tax_cfg["shipping_label"] if tax_cfg else None) or "Shipping"
            total_cents = subtotal + tax_cents + shipping_cents
```

(`goods_subtotal_cents=taxable`, not `subtotal` — `taxable` is the physical-only sum computed two lines above for tax; a mixed cart's digital/service/booking lines must not count toward the shipping gate or threshold, and `taxable <= 0` covers the free-item edge case in one guard — see the risk bullet below.)

(`has_physical` / `shipping_label` are function-scope — still visible in the Stripe branch below the transaction.)

**2c — order INSERT.** Anchor: `order = await conn.fetchrow(` :507-516. Replace with (`$9` → `$10`; column + RETURNING added):

```python
            order = await conn.fetchrow(
                """INSERT INTO cappe_orders
                       (site_id, customer_email, customer_name, status, subtotal_cents, tax_cents,
                        shipping_cents, total_cents, currency, note, requires_approval)
                   VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8, $9, $10)
                   RETURNING id, status, subtotal_cents, tax_cents, shipping_cents, total_cents,
                             currency, access_token, requires_approval""",
                site["id"], email, body.customer_name, subtotal, tax_cents, shipping_cents,
                total_cents, order_currency or "USD", body.note, order_requires_approval,
            )
```

**2d — checkout-session call.** Anchor: `sess = await get_cappe_stripe().create_checkout_session(` :574-583. Replace the call with:

```python
            sess = await get_cappe_stripe().create_checkout_session(
                account_id=owner["stripe_account_id"],
                currency=cur,
                line_items=line_items,
                application_fee_cents=fee,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
                metadata={"order_id": str(order["id"]), "platform_fee_cents": str(fee)},
                customer_email=email or None,
                collect_shipping_address=has_physical,
                shipping_option=(
                    {
                        "label": shipping_label if order["shipping_cents"] > 0 else "Free shipping",
                        "amount_cents": order["shipping_cents"],
                    }
                    if has_physical else None
                ),
            )
```

Shipping is **not** a line item — it rides Stripe `shipping_options` (real shipping row in Checkout, "Free" at 0, included in `amount_total`; charge equals `total_cents` by construction). `fee` stays on `pay_total = order["subtotal_cents"]` — **no change** to :539/:550.

**2e — fallback path (:594-612): notify with `order["total_cents"]`.** `shipping_cents` is already inside `total_cents`; no address exists because no Stripe session ran. `send_cappe_order_receipt_email`/`send_cappe_order_alert_email` take a `total_cents` parameter — pass `order["total_cents"]`, not `order["subtotal_cents"]` (the original tax-only version of this line under-reported by tax; shipping made the gap larger, so both are fixed together here).

**2f — line-items extraction.** The Stripe `line_items` build (cart lines + tax line) is a pure function of `(line_rows, currency, tax_cents, tax_label)` with no I/O — pull it out as `build_stripe_line_items` next to `compute_shipping_cents` so the money invariant (`sum(line_items) + shipping_cents == total_cents`) is unit-testable without a DB. The Stripe-branch call site becomes `line_items = build_stripe_line_items(line_rows, cur, order["tax_cents"], tax_label)`.

## Step 3 — `server/app/cappe/services/stripe_connect.py`

**3a — constant + pure helper.** Anchor: insert after `platform_fee_cents` (ends :41), before `class CappeStripe`:

```python
# Gummfit storefronts are US-facing. Per-site country config is a deliberate
# later one-column follow-up, not scope here.
CAPPE_SHIPPING_COUNTRIES = ["US"]


def build_shipping_options(shipping_option: Optional[dict], currency: str) -> Optional[list[dict]]:
    """Translate {label, amount_cents} into Stripe's shipping_options shape.
    A 0-amount option is still emitted so the buyer sees the 'Free shipping' row."""
    if shipping_option is None:
        return None
    return [{
        "shipping_rate_data": {
            "type": "fixed_amount",
            "display_name": (shipping_option.get("label") or "Shipping")[:100],
            "fixed_amount": {
                "amount": max(0, int(shipping_option["amount_cents"])),
                "currency": (currency or "usd").lower(),
            },
        }
    }]
```

**3b — `create_checkout_session`.** Anchor: :103-148. Complete replacement (docstring keeps its fee paragraph, gains the shipping note):

```python
    async def create_checkout_session(
        self,
        *,
        account_id: str,
        currency: str,
        line_items: list[dict[str, Any]],
        application_fee_cents: int,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: Optional[str] = None,
        collect_shipping_address: bool = False,
        shipping_option: Optional[dict] = None,
    ):
        """Create a Checkout Session ON the connected account (direct charge),
        taking a platform `application_fee_amount`. Returns the Session.

        The fee is passed in, never recomputed here. It used to be derived from
        an `amount_cents` argument, which meant the caller computed the fee once
        for persistence (`cappe_orders.platform_fee_cents`) and this method
        computed it again for the actual charge. Both read the same global
        setting, so they agreed by luck; with a per-plan rate they could
        diverge, and the persisted number would be a lie about money.

        With `collect_shipping_address`, Stripe collects the buyer's address
        (US only) and `shipping_option` renders as a real shipping row included
        in amount_total; the fee stays on the goods subtotal.
        """
        self._ensure_key()
        fee = max(0, int(application_fee_cents))

        def _create():
            extra: dict[str, Any] = {}
            if collect_shipping_address:
                extra["shipping_address_collection"] = {"allowed_countries": CAPPE_SHIPPING_COUNTRIES}
                opts = build_shipping_options(shipping_option, currency)
                if opts:
                    extra["shipping_options"] = opts
            return stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                line_items=line_items,
                customer_email=customer_email or None,
                metadata=metadata,
                payment_intent_data={
                    "application_fee_amount": fee,
                    "metadata": metadata,
                },
                # stripe_account header → the charge happens on the business's
                # connected account; the fee is swept to the platform.
                stripe_account=account_id,
                **extra,
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create checkout session: {exc}") from exc
```

Digital/service/booking-only carts pass `collect_shipping_address=False` → `extra` empty → checkout byte-identical to today.

**3c — retrieve helper.** Anchor: insert directly after `create_checkout_session`, before `create_platform_checkout_session` (:151). Pattern of `retrieve_account` :90-100:

```python
    async def retrieve_checkout_session(self, account_id: str, session_id: str):
        """Fetch a Checkout Session from the connected account (webhook fallback
        when the event payload omits shipping details)."""
        self._ensure_key()

        def _get():
            return stripe.checkout.Session.retrieve(session_id, stripe_account=account_id)

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve checkout session: {exc}") from exc
```

## Step 4 — `server/app/cappe/routes/payments.py`

**4a.** Anchor: `import logging` (:11). Add `import json` above it (stdlib block).

**4b — pure extractor.** Anchor: insert after `router = APIRouter()` (:33), before `class ConnectLinkRequest`:

```python
def extract_shipping_details(obj: dict) -> Optional[dict]:
    """Newer Stripe API versions nest the buyer's address under
    collected_information.shipping_details; older ones put it at top level.
    Read both; None when absent either way. Works on raw event payloads and
    retrieved StripeObject sessions alike (both are dict-like)."""
    collected = obj.get("collected_information") or {}
    return collected.get("shipping_details") or obj.get("shipping_details") or None
```

**4c — webhook branch.** Anchor: inside `_handle_connect_event`, the block from `if oid is not None and event_account_id:` (:165) through the `row = await conn.fetchrow(...)` UPDATE (:174-186). Final form (fee parsing :166-172 unchanged; shipping fetch inserted **before** `async with get_connection()` so no pooled conn is held across a Stripe call; UPDATE gains `$5`):

```python
        if oid is not None and event_account_id:
            payment_intent = obj.get("payment_intent")
            fee = None
            try:
                fee = meta.get("platform_fee_cents")
                fee = int(fee) if fee is not None else None
            except (TypeError, ValueError):
                fee = None
            ship = extract_shipping_details(obj)
            # `shipping_cost` is only set on sessions that had a shipping_options
            # entry attached, i.e. physical orders (see build_shipping_options) —
            # gate the retrieve on it so a digital/service webhook, the common
            # case, never makes a synchronous Stripe round-trip it can't use.
            if ship is None and obj.get("shipping_cost") and obj.get("id"):
                try:
                    sess = await get_cappe_stripe().retrieve_checkout_session(event_account_id, obj["id"])
                    ship = extract_shipping_details(sess)
                except CappeStripeError:
                    ship = None  # best-effort; never block marking the order paid
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """UPDATE cappe_orders o
                          SET status = 'paid', paid_at = NOW(),
                              stripe_payment_intent = $2, payment_ref = $2,
                              platform_fee_cents = COALESCE($3, platform_fee_cents),
                              shipping_address = COALESCE($5::jsonb, o.shipping_address),
                              updated_at = NOW()
                        FROM cappe_sites s, cappe_accounts a
                        WHERE o.id = $1 AND o.status = 'pending'
                          AND s.id = o.site_id AND a.id = s.account_id
                          AND a.stripe_account_id = $4
                        RETURNING o.id, o.site_id, o.customer_email, o.customer_name""",
                    oid, payment_intent, fee, event_account_id,
                    json.dumps(dict(ship)) if ship else None,
                )
```

(`dict(ship)` because a retrieved-session StripeObject isn't guaranteed plain-dict for `json.dumps`.) Everything after the UPDATE (:187-196 receipt background task + log lines) and the claim/release dedupe (:135-149) stays untouched.

## Step 5 — Admin API: `models/shop.py` + `routes/shop.py`

**5a — imports.** Anchor `models/shop.py:7`:

```python
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
```

**5b — `CappeOrder` (:157-176).** After the `tax_cents: int = 0` line add:

```python
    shipping_cents: int = 0
    shipping_address: Optional[dict[str, Any]] = None
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
```

**5c — replace `CappeOrderStatusUpdate` (:196-197)** entirely:

```python
class CappeOrderStatusUpdate(BaseModel):
    """Order PATCH body — status transition and/or tracking edit. All fields
    optional so a tracking-only PATCH never touches status (and so never
    triggers restock); at least one field must be present. Explicit null
    carrier/tracking clears the column (build_patch semantics)."""
    status: Optional[Literal["pending", "paid", "fulfilled", "cancelled", "refunded"]] = None
    carrier: Optional[str] = Field(default=None, max_length=40)
    tracking_number: Optional[str] = Field(default=None, max_length=120)

    @field_validator("carrier", "tracking_number")
    @classmethod
    def _strip_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def _validate_fields(self):
        # status=None-explicit would SET status = NULL via build_patch → reject.
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        if self.status is None and not ({"carrier", "tracking_number"} & self.model_fields_set):
            raise ValueError("Provide status, carrier, or tracking_number")
        return self
```

**5d — `_ORDER_COLS` (routes/shop.py:46-51).** Final form:

```python
_ORDER_COLS = (
    "id, site_id, customer_email, customer_name, status, subtotal_cents, "
    "tax_cents, shipping_cents, total_cents, receipt_number, "
    "shipping_address, carrier, tracking_number, "
    "currency, payment_ref, note, requires_approval, approved_at, decline_reason, "
    "metadata, created_at, updated_at"
)
```

This flows the new fields into every order list/detail/accept/decline endpoint automatically (all use `{_ORDER_COLS}`).

**5e — `_order_row` (:110-114).** Final form:

```python
def _order_row(row, items=None) -> dict:
    d = dict(row)
    d["metadata"] = loads(row["metadata"])
    d["shipping_address"] = loads(row["shipping_address"]) or None  # loads() maps NULL→{}; keep None
    d["items"] = items or []
    return d
```

**5f — replace `update_order_status` (:394-422)** entirely. Uses `build_patch` (already imported at shop.py:26). FOR-UPDATE read stays unconditional — it is the 404 existence check and serializes concurrent PATCHes; restock stays gated on the actual FROM→TO status transition:

```python
@router.patch("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def update_order_status(
    site_id: UUID, order_id: UUID, body: CappeOrderStatusUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            # Lock + read the CURRENT status first: whether this transition
            # reverses a stock decrement depends on what it's transitioning
            # FROM, and locking makes a concurrent double-click restock once.
            current = await conn.fetchrow(
                "SELECT status FROM cappe_orders WHERE id = $1 AND site_id = $2 FOR UPDATE",
                order_id, site_id,
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
            sets, args = build_patch(body, ("status", "carrier", "tracking_number"))
            sets.append("updated_at = NOW()")
            args.extend([order_id, site_id])
            order = await conn.fetchrow(
                f"""UPDATE cappe_orders SET {', '.join(sets)}
                    WHERE id = ${len(args) - 1} AND site_id = ${len(args)}
                    RETURNING {_ORDER_COLS}""",
                *args,
            )
            if (
                body.status is not None
                and current["status"] in _RESTOCK_FROM_STATUSES
                and body.status in _RESTOCK_TO_STATUSES
            ):
                await restock_order(conn, site_id=site_id, order_id=order_id, reason="restock")
            items = await conn.fetch(
                f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
                order_id,
            )
    return _order_row(order, [_item_row(i) for i in items])
```

(`sets` never empty: the model validator guarantees ≥1 field, and `updated_at = NOW()` is appended regardless.)

## Step 6 — Receipt PDF: `services/receipt.py`

**6a — order SELECT.** Anchor :149-156. Final SELECT:

```python
    order = await conn.fetchrow(
        """SELECT o.id, o.customer_email, o.customer_name, o.currency, o.subtotal_cents,
                  o.tax_cents, o.shipping_cents, o.shipping_address, o.total_cents,
                  o.receipt_number, o.payment_ref,
                  o.stripe_payment_intent, o.paid_at, o.created_at, o.site_id,
                  s.name AS business_name, s.tax_label, s.shipping_label
             FROM cappe_orders o JOIN cappe_sites s ON s.id = o.site_id
            WHERE o.id = $1""",
        order_id,
    )
```

**6b — new module-level helper.** Anchor: insert before `build_receipt_html` (:89):

```python
def _ship_to_html(shipping_address) -> str:
    """Render the Ship-to block from the persisted Stripe shipping_details.
    Accepts str-or-dict (asyncpg JSONB); every field HTML-escaped."""
    addr = shipping_address
    if isinstance(addr, str):
        try:
            addr = json.loads(addr)
        except ValueError:
            addr = None
    if not isinstance(addr, dict):
        return ""
    a = addr.get("address")
    if not isinstance(a, dict):  # JSONB is caller-controlled; never trust its shape
        a = {}
    city_line = ", ".join(str(x) for x in [a.get("city"), a.get("state")] if x)
    if a.get("postal_code"):
        city_line = f"{city_line} {a['postal_code']}".strip()
    lines = [addr.get("name"), a.get("line1"), a.get("line2"), city_line, a.get("country")]
    rows = "".join(f"<div>{escape(str(x))}</div>" for x in lines if x)
    if not rows:
        return ""
    return (
        '<div style="margin:20px 0 8px;font-size:13px;color:#3f3f46;">'
        '<div style="color:#71717a;">Ship to</div>' + rows + "</div>"
    )
```

**6c — `build_receipt_html` (:89-143).** Three edits inside the existing function:

1. Money block — replace :98-101 with:

```python
    subtotal = int(order.get("subtotal_cents") or 0)
    tax = int(order.get("tax_cents") or 0)
    shipping = int(order.get("shipping_cents") or 0)
    total = int(order.get("total_cents") or (subtotal + tax + shipping))
    tax_label = escape(str(order.get("tax_label") or "Tax"))
    shipping_label = escape(str(order.get("shipping_label") or "Shipping"))
```

2. After the `tax_row = (...)` assignment (:104-108) add:

```python
    shipping_row = (
        f'<tr><td style="padding:4px 0;text-align:right;color:#71717a;">{shipping_label}</td>'
        f'<td style="padding:4px 0;text-align:right;width:120px;">{_fmt(shipping, cur)}</td></tr>'
        if shipping > 0 else ""
    )
    ship_to = _ship_to_html(order.get("shipping_address"))
```

3. In the returned f-string: append `{ship_to}` immediately after the Billed-to `</div>` (line :124), and change the totals tbody line `{tax_row}` (:137) to `{tax_row}\n    {shipping_row}`.

## Step 7 — Public order status: `routes/public/shop.py` + `models/shop.py`

**7a — `CappeOrderReceipt` (models/shop.py:243-251).** After `currency: str` add:

```python
    shipping_cents: int = 0
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
```

**7b — endpoint (routes/public/shop.py:104-129).** SELECT (:104-108) becomes:

```python
        order = await conn.fetchrow(
            "SELECT id, status, customer_email, customer_name, subtotal_cents, "
            "shipping_cents, carrier, tracking_number, currency, created_at "
            "FROM cappe_orders WHERE access_token = $1",
            token,
        )
```

Response construction (:122-129): after `subtotal_cents=order["subtotal_cents"],` add:

```python
        shipping_cents=order["shipping_cents"],
        carrier=order["carrier"],
        tracking_number=order["tracking_number"],
```

**Deliberately omit `shipping_address` from the public payload** — the access token is shareable/leakable; a tracking number is low-blast-radius, a home address is not. (Endpoint already omits `tax_cents`/`total_cents`; pre-existing, not scope.)

## Step 8 — Site settings: `models/sites.py` + `routes/sites.py`

**8a — `CappeSiteUpdate` (models/sites.py:57-72).** After `tax_label` (:71) add:

```python
    shipping_flat_cents: Optional[int] = Field(default=None, ge=0)
    # Explicit null clears the threshold (model_fields_set gate in the route).
    shipping_free_threshold_cents: Optional[int] = Field(default=None, ge=0)
    shipping_label: Optional[str] = Field(default=None, max_length=40)
```

**8b — `CappeSite` (models/sites.py:91-119).** After `tax_label: str = "Tax"` (:106) add:

```python
    shipping_flat_cents: int = 0
    shipping_free_threshold_cents: Optional[int] = None
    shipping_label: str = "Shipping"
```

**8c — `_SITE_COLS` (routes/sites.py:50-56).** In the string, after `"tax_rate_bps, tax_label, receipt_prefix, "` add the line:

```python
    "shipping_flat_cents, shipping_free_threshold_cents, shipping_label, "
```

(`site_row_to_dict` is a generic pass-through — no further edit; the new columns flow into every `CappeSite` response.)

**8d — PUT handler.** Anchor: the `receipt_prefix` branch (:294-295). Directly after it add:

```python
        if body.shipping_flat_cents is not None:
            add("shipping_flat_cents", body.shipping_flat_cents)
        if "shipping_free_threshold_cents" in body.model_fields_set:
            # model_fields_set (not `is not None`) so explicit null CLEARS the threshold
            add("shipping_free_threshold_cents", body.shipping_free_threshold_cents)
        if body.shipping_label is not None:
            add("shipping_label", body.shipping_label.strip() or "Shipping")
```

## Step 9 — Frontend (`client/src/cappe/` only — cappeApi + own ui stack, never Matcha's)

**9a — `types.ts`.**

`CappeSite` — after `receipt_prefix?: string | null` (:67) add:

```ts
  shipping_flat_cents?: number | null
  shipping_free_threshold_cents?: number | null
  shipping_label?: string | null
```

Above `CappeOrder` (:345) add:

```ts
export type CappeShippingAddress = {
  name?: string | null
  address?: {
    line1?: string | null
    line2?: string | null
    city?: string | null
    state?: string | null
    postal_code?: string | null
    country?: string | null
  } | null
}
```

`CappeOrder` — after `tax_cents: number` (:352) add:

```ts
  shipping_cents: number
  shipping_address?: CappeShippingAddress | null
  carrier?: string | null
  tracking_number?: string | null
```

**9b — new `components/ShippingSettingsCard.tsx`.** Complete file (structural clone of `TaxSettingsCard.tsx` — same load/save/state pattern, same zinc classes):

```tsx
import { useEffect, useState } from 'react'
import { Loader2, Check, Truck } from 'lucide-react'
import { cappeApi } from '../api'
import type { CappeSite } from '../types'

// Flat per-order shipping for storefronts selling physical goods. Applied at
// checkout when the cart contains a physical line; free once the goods subtotal
// clears the optional threshold. Stripe collects the shipping address.
export default function ShippingSettingsCard({ siteId }: { siteId: string }) {
  const [flat, setFlat] = useState('') // dollars, as typed
  const [freeOver, setFreeOver] = useState('') // dollars; '' = no threshold
  const [label, setLabel] = useState('Shipping')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<CappeSite>(`/sites/${siteId}`).then((s) => {
      setFlat(s.shipping_flat_cents ? (s.shipping_flat_cents / 100).toString() : '')
      setFreeOver(s.shipping_free_threshold_cents != null ? (s.shipping_free_threshold_cents / 100).toString() : '')
      setLabel(s.shipping_label || 'Shipping')
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [siteId])

  async function save() {
    setSaving(true); setError(null); setSaved(false)
    const flatN = parseFloat(flat)
    const freeN = parseFloat(freeOver)
    try {
      await cappeApi.put(`/sites/${siteId}`, {
        shipping_flat_cents: Number.isFinite(flatN) ? Math.max(0, Math.round(flatN * 100)) : 0,
        shipping_free_threshold_cents:
          freeOver.trim() !== '' && Number.isFinite(freeN) ? Math.max(0, Math.round(freeN * 100)) : null,
        shipping_label: label.trim() || 'Shipping',
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return null

  return (
    <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-200">
        <Truck className="h-4 w-4 text-lime-400" /> Shipping
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="text-xs text-zinc-400">
          Flat rate ($)
          <input
            value={flat}
            onChange={(e) => setFlat(e.target.value)}
            inputMode="decimal"
            placeholder="0"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Free over ($)
          <input
            value={freeOver}
            onChange={(e) => setFreeOver(e.target.value)}
            inputMode="decimal"
            placeholder="No threshold"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Label
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={40}
            placeholder="Shipping"
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500"
          />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-white disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Save
        </button>
        {saved && <span className="text-xs text-lime-400">Saved</span>}
        {error && <span className="text-xs text-red-400">{error}</span>}
        <span className="ml-auto text-[11px] text-zinc-500">Applies once per order with a physical item. Address collected by Stripe.</span>
      </div>
    </div>
  )
}
```

**9c — `pages/site/Shop.tsx`.** Anchor: import line :6 and render line :133:

```tsx
import ShippingSettingsCard from '../../components/ShippingSettingsCard'
// ...
      <TaxSettingsCard siteId={siteId || ''} />
      <ShippingSettingsCard siteId={siteId || ''} />
```

**9d — `pages/site/Orders.tsx`.** Three edits:

1. Lucide import (:3): add `Truck`:

```tsx
import { Loader2, Receipt, ChevronDown, ChevronRight, Calendar, Check, X, Clock, Truck } from 'lucide-react'
```

2. Expanded panel. Anchor: `<div className="space-y-2 bg-zinc-950 px-12 py-3">` (:127). Insert immediately after it, before the `{o.items.length === 0 ? (` ternary:

```tsx
                  {o.shipping_address && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-300">
                      <div className="mb-1 flex items-center gap-1.5 font-medium text-zinc-400"><Truck className="h-3.5 w-3.5" /> Ship to</div>
                      {o.shipping_address.name && <div>{o.shipping_address.name}</div>}
                      {o.shipping_address.address?.line1 && <div>{o.shipping_address.address.line1}</div>}
                      {o.shipping_address.address?.line2 && <div>{o.shipping_address.address.line2}</div>}
                      <div>
                        {[o.shipping_address.address?.city, o.shipping_address.address?.state].filter(Boolean).join(', ')}{' '}
                        {o.shipping_address.address?.postal_code || ''}
                      </div>
                      {o.shipping_address.address?.country && <div>{o.shipping_address.address.country}</div>}
                    </div>
                  )}
                  {(o.shipping_address != null || o.items.some((i) => i.fulfillment === 'physical')) && (
                    <TrackingEditor
                      siteId={siteId || ''}
                      order={o}
                      onSaved={(u) => setOrders((os) => (os || []).map((x) => (x.id === o.id ? u : x)))}
                    />
                  )}
```

3. New component at the bottom of the file (after the `Orders` default export closes):

```tsx
function TrackingEditor({ siteId, order, onSaved }: {
  siteId: string
  order: CappeOrder
  onSaved: (o: CappeOrder) => void
}) {
  const [carrier, setCarrier] = useState(order.carrier || '')
  const [tracking, setTracking] = useState(order.tracking_number || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setSaving(true); setError(null)
    try {
      const updated = await cappeApi.patch<CappeOrder>(
        `/sites/${siteId}/orders/${order.id}`,
        { carrier: carrier.trim() || null, tracking_number: tracking.trim() || null },
      )
      onSaved({ ...updated, items: order.items })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save tracking')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 p-3">
      <input
        value={carrier}
        onChange={(e) => setCarrier(e.target.value)}
        maxLength={40}
        placeholder="Carrier — e.g. USPS"
        className="w-36 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500"
      />
      <input
        value={tracking}
        onChange={(e) => setTracking(e.target.value)}
        maxLength={120}
        placeholder="Tracking number"
        className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500"
      />
      <button
        onClick={save}
        disabled={saving}
        className="flex items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
      >
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
      </button>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
```

(`{ ...updated, items: order.items }` — keeps the file's established local-merge idiom (:53) so an in-flight item edit isn't clobbered. Existing `setStatus` (:51-54) keeps sending `{status}` only — still valid against the all-optional model.)

**9e — `server/app/cappe/services/render/assets/store.js` (optional, skippable).** Anchor: `openDetail` template, line :37 `(p.description?'<p class="cz-pd__desc">'+RT.esc(p.description)+'</p>':'')+`. Insert after that concatenation term:

```js
(p.fulfillment==='physical'?'<p class="cz-msg">Shipping calculated at checkout.</p>':'')+
```

No other storefront change — Stripe collects the address.

## Step 10 — Tests: new `server/tests/cappe/test_cappe_shipping.py`

Complete file:

```python
"""Cappe shipping pure-function tests — no DB, no app boot.

Covers the shipping money math, the Stripe shipping_options translation, the
webhook address extraction (both API shapes), the order-PATCH model contract,
and the receipt HTML (shipping row + escaped Ship-to block). Run from server/.
"""
import json
import os
from datetime import datetime, timezone

# Defensive: some transitive imports read settings at import time.
os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.shop import CappeOrderStatusUpdate  # noqa: E402
from app.cappe.routes._shared import build_patch  # noqa: E402
from app.cappe.routes.payments import extract_shipping_details  # noqa: E402
from app.cappe.routes.shop import should_restock  # noqa: E402
from app.cappe.services.commerce import build_stripe_line_items, compute_shipping_cents  # noqa: E402
from app.cappe.services.receipt import _ship_to_html, build_receipt_html  # noqa: E402
from app.cappe.services.stripe_connect import build_shipping_options  # noqa: E402


# --- compute_shipping_cents --------------------------------------------------

def test_shipping_zero_without_physical():
    assert compute_shipping_cents(
        has_physical=False, goods_subtotal_cents=5000, flat_cents=700, free_threshold_cents=None
    ) == 0


def test_shipping_flat_applied_to_physical():
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=5000, flat_cents=700, free_threshold_cents=None
    ) == 700


def test_shipping_zero_when_rate_unset():
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=5000, flat_cents=0, free_threshold_cents=None
    ) == 0


def test_shipping_threshold_met_exactly():
    # Boundary: >= not >
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=5000, flat_cents=700, free_threshold_cents=5000
    ) == 0


def test_shipping_threshold_not_met():
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=4999, flat_cents=700, free_threshold_cents=5000
    ) == 700


def test_shipping_threshold_zero_means_always_free():
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=1, flat_cents=700, free_threshold_cents=0
    ) == 0


def test_shipping_zero_when_goods_subtotal_zero():
    # A free-item physical cart never ships paid, even with no threshold set —
    # otherwise an order could persist shipping_cents > 0 with no payable amount.
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=0, flat_cents=700, free_threshold_cents=None
    ) == 0


def test_shipping_threshold_ignores_non_physical_lines():
    # Threshold compares the GOODS subtotal only — a $60 booking shouldn't earn
    # free shipping on a $10 physical line against a $50 threshold.
    assert compute_shipping_cents(
        has_physical=True, goods_subtotal_cents=1000, flat_cents=700, free_threshold_cents=5000
    ) == 700


# --- build_shipping_options --------------------------------------------------

def test_shipping_options_none_passthrough():
    assert build_shipping_options(None, "usd") is None


def test_shipping_options_shape():
    [opt] = build_shipping_options({"label": "Shipping", "amount_cents": 700}, "USD")
    rate = opt["shipping_rate_data"]
    assert rate["type"] == "fixed_amount"
    assert rate["display_name"] == "Shipping"
    assert rate["fixed_amount"] == {"amount": 700, "currency": "usd"}


def test_shipping_options_free_and_label_fallbacks():
    [opt] = build_shipping_options({"label": None, "amount_cents": 0}, "usd")
    assert opt["shipping_rate_data"]["display_name"] == "Shipping"
    # 0-amount row still emitted so the buyer sees "Free shipping".
    assert opt["shipping_rate_data"]["fixed_amount"]["amount"] == 0


# --- extract_shipping_details ------------------------------------------------

_ADDR = {"name": "Jane Doe", "address": {"line1": "1 Main St", "city": "Reno",
                                         "state": "NV", "postal_code": "89501", "country": "US"}}


def test_extract_shipping_new_api_shape():
    assert extract_shipping_details({"collected_information": {"shipping_details": _ADDR}}) == _ADDR


def test_extract_shipping_legacy_shape():
    assert extract_shipping_details({"shipping_details": _ADDR}) == _ADDR


def test_extract_shipping_prefers_collected():
    obj = {"collected_information": {"shipping_details": {"name": "new"}},
           "shipping_details": {"name": "old"}}
    assert extract_shipping_details(obj)["name"] == "new"


def test_extract_shipping_absent_returns_none():
    assert extract_shipping_details({}) is None
    assert extract_shipping_details({"collected_information": {}}) is None
    assert extract_shipping_details({"collected_information": None}) is None


# --- should_restock -----------------------------------------------------------

def test_should_restock_tracking_only_patch_never_restocks():
    # new_status=None is what a tracking-only PATCH passes — must be a no-op
    # regardless of current status, or a carrier/tracking edit would credit stock.
    assert should_restock("paid", None) is False
    assert should_restock("pending", None) is False


def test_should_restock_on_reversing_transition():
    assert should_restock("paid", "cancelled") is True
    assert should_restock("fulfilled", "refunded") is True


def test_should_restock_false_when_nothing_to_reverse():
    # Already cancelled/declined: no decrement outstanding to reverse.
    assert should_restock("cancelled", "cancelled") is False


def test_should_restock_false_for_non_reversing_transition():
    assert should_restock("pending", "fulfilled") is False


# --- build_patch placeholder numbering (routes/shop.py update_order_status) --

def test_build_patch_numbering_matches_route_append_of_two_args():
    # update_order_status appends exactly [order_id, site_id] after build_patch's
    # own args, then closes the WHERE clause with ${len(args)-1}/${len(args)}.
    # That arithmetic is only correct if build_patch's own placeholders are
    # sequential starting at $1 with no gaps — assert that directly.
    body = CappeOrderStatusUpdate.model_validate({"carrier": "USPS", "tracking_number": "123"})
    sets, args = build_patch(body, ("status", "carrier", "tracking_number"))
    assert args == ["USPS", "123"]
    assert sets == ["carrier = $1", "tracking_number = $2"]
    args_with_route_tail = [*args, "order-id", "site-id"]
    assert f"${len(args_with_route_tail) - 1}" == "$3"  # order_id placeholder
    assert f"${len(args_with_route_tail)}" == "$4"       # site_id placeholder


def test_build_patch_single_field_numbering():
    body = CappeOrderStatusUpdate.model_validate({"status": "paid"})
    sets, args = build_patch(body, ("status", "carrier", "tracking_number"))
    assert sets == ["status = $1"] and args == ["paid"]


# --- build_stripe_line_items / total invariant --------------------------------

def test_line_items_sum_plus_shipping_equals_total():
    # The invariant Stripe must charge: sum(line_items) + shipping_cents ==
    # subtotal_cents + tax_cents + shipping_cents == total_cents.
    line_rows = [
        (None, "Shirt", 2500, 2, "physical", {}, None, [], []),
        (None, "Consult", 6000, 1, "service", {}, None, [], []),
    ]
    subtotal = sum(unit * qty for (_p, _t, unit, qty, *_r) in line_rows)
    tax_cents = 400
    shipping_cents = 700
    total_cents = subtotal + tax_cents + shipping_cents
    line_items = build_stripe_line_items(line_rows, "usd", tax_cents, "Tax")
    charged = sum(li["price_data"]["unit_amount"] * li["quantity"] for li in line_items)
    assert charged + shipping_cents == total_cents


def test_line_items_omit_tax_line_when_zero():
    line_rows = [(None, "Widget", 1000, 1, "physical", {}, None, [], [])]
    line_items = build_stripe_line_items(line_rows, "usd", 0, "Tax")
    assert len(line_items) == 1


# --- _ship_to_html robustness --------------------------------------------------

def test_ship_to_html_non_dict_address_field_does_not_raise():
    # Guards against a JSONB payload where "address" isn't itself a dict —
    # must degrade gracefully, not AttributeError inside the receipt render.
    html = _ship_to_html({"name": "Jane Doe", "address": "not-a-dict"})
    assert "Jane Doe" in html


def test_ship_to_html_non_dict_top_level_returns_empty():
    assert _ship_to_html("garbage") == ""
    assert _ship_to_html(None) == ""


# --- CappeOrderStatusUpdate --------------------------------------------------

def test_order_update_requires_a_field():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate()


def test_order_update_status_only_ok():
    m = CappeOrderStatusUpdate(status="paid")
    assert m.status == "paid" and m.carrier is None


def test_order_update_tracking_only_ok():
    m = CappeOrderStatusUpdate(carrier="USPS")
    assert m.status is None and m.carrier == "USPS"


def test_order_update_explicit_null_carrier_ok():
    m = CappeOrderStatusUpdate.model_validate({"carrier": None})
    assert m.carrier is None and "carrier" in m.model_fields_set


def test_order_update_explicit_null_status_rejected():
    # build_patch would SET status = NULL — the model must refuse it.
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate.model_validate({"status": None})


def test_order_update_rejects_bad_status():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(status="shipped")


def test_order_update_length_caps():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(carrier="x" * 41)
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(tracking_number="x" * 121)


def test_order_update_strips_whitespace_to_none():
    m = CappeOrderStatusUpdate.model_validate({"carrier": "  ", "tracking_number": " 940011 "})
    assert m.carrier is None and m.tracking_number == "940011"


# --- build_receipt_html ------------------------------------------------------

_BASE_ORDER = {
    "currency": "USD", "business_name": "Store", "receipt_number": "INV-00001",
    "customer_name": "Buyer", "customer_email": "buyer@example.com",
    "subtotal_cents": 5000, "tax_cents": 0, "total_cents": None,
    "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
}


def test_receipt_shipping_row_rendered():
    html = build_receipt_html(
        {**_BASE_ORDER, "shipping_cents": 700, "shipping_label": "Shipping", "total_cents": 5700}, []
    )
    assert "Shipping" in html and "$7.00" in html


def test_receipt_no_shipping_row_when_zero():
    html = build_receipt_html({**_BASE_ORDER, "shipping_cents": 0}, [])
    assert "Shipping" not in html and "Ship to" not in html


def test_receipt_ship_to_block_and_escaping():
    addr = {"name": "<script>x</script>", "address": _ADDR["address"]}
    html = build_receipt_html({**_BASE_ORDER, "shipping_address": addr}, [])
    assert "Ship to" in html
    assert "&lt;script&gt;" in html and "<script>x" not in html
    assert "1 Main St" in html and "Reno, NV 89501" in html


def test_receipt_ship_to_handles_str_jsonb():
    html = build_receipt_html({**_BASE_ORDER, "shipping_address": json.dumps(_ADDR)}, [])
    assert "Ship to" in html and "Jane Doe" in html


def test_receipt_total_fallback_includes_shipping():
    # total_cents=None → subtotal + tax + shipping
    html = build_receipt_html({**_BASE_ORDER, "shipping_cents": 700}, [])
    assert "$57.00" in html
```

(Buyer email uses `@example.com` — RFC 2606 reserved, per repo test-data rule.)

## Verification

1. **Tests**: `cd server && ./venv/bin/python -m pytest tests/cappe/ -q` — new file plus existing cappe suite green.
2. **Static**: post-edit hook runs `py_compile` per file; `cd client && npx tsc -p tsconfig.app.json --noEmit` (never bare `npx tsc --noEmit` — checks nothing).
3. **Manual (user-run, Stripe test mode)**: apply migration via `./scripts/migrate-dev.sh`; `stripe listen --forward-to localhost:8001/api/cappe/payments/webhook`; buy a physical item on a dev storefront → Checkout shows address form + shipping row ("Free shipping" when threshold met) → webhook lands → order row has `shipping_address` → receipt PDF shows Ship-to + shipping line → set carrier/tracking in Orders page → tokened `/public/orders/{token}` payload shows `carrier`/`tracking_number` but **no address** → digital-only order still checks out with no address form, and its webhook does **not** call `retrieve_checkout_session` (check logs/breakpoint — `shipping_cost` gate). Also: a cart mixing a $60 non-physical line with a $10 physical line against a $50 free-shipping threshold still charges shipping (threshold is goods-only, not whole-cart); a $0 physical item never persists `shipping_cents > 0`.
4. After approval of any spec change: re-copy this file to repo-root `CAPPE_SHIPPING_PLAN.md` and commit.

## Risks / edge cases

- **Mixed carts** (physical + digital): `has_physical` any-match → shipping applies once per order.
- **Pre-migration pending orders paid after deploy**: `shipping_cents` defaults 0; `COALESCE($5::jsonb, o.shipping_address)` leaves address NULL when Stripe collected none.
- **`taxable == 0` physical carts** (free item, or a cart whose only physical line is a giveaway): `compute_shipping_cents`'s `goods_subtotal_cents <= 0` guard returns 0 — no shipping is persisted even though `can_pay` is also false (:540-543) → no Stripe session → no address either. (Corrected from an earlier draft of this bullet, which claimed "no shipping" while the shipped code actually still charged it — see the fix pass's F1/F4.)
- **Tracking-only PATCH must not touch stock**: restock gated on `body.status is not None` + FROM/TO transition sets (Step 5f, extracted into the pure `should_restock(current_status, new_status)` for unit testing); `{"status": null}` rejected at the model so `build_patch` can never SET status NULL.
- **Threshold clearing**: `model_fields_set` gate (Step 8d); ShippingSettingsCard sends `null` for an emptied "Free over" input.
- **`shipping_options` on direct-charge (connected-account) sessions**: confirmed against Stripe docs — inline `shipping_rate_data`, a `fixed_amount.amount = 0` free-shipping row, and `application_fee_amount` via `payment_intent_data` on a `Stripe-Account`-scoped session are all documented and composable; payment mode only (this code hardcodes `mode="payment"`). A `CappeStripeError` still degrades to the manual pending flow at commerce.py:591 (order still created, shipping in total).
- **Stripe retrieve fallback**: fires only when the event payload lacks shipping details AND `shipping_cost` shows the session had a shipping option attached (i.e. only for physical orders) — a digital/service webhook never triggers the extra round-trip. Failure swallowed (`ship = None`) so paid-marking + receipt never block. Claim/release dedupe (:135-149) untouched.
- **Threshold base**: compares the physical-goods subtotal (`taxable`), not the whole-cart `subtotal` — a $60 booking + $10 shirt does NOT get free shipping at a $50 threshold, matching the tax base and the docstring's "goods subtotal" claim.
- **`loads()` None-collapse**: `common.loads()` maps NULL→`{}`; `_order_row` uses `loads(...) or None` so Pydantic serializes `null`, not `{}`.
- **Deploy order**: migration before code (user's normal migrate-then-deploy flow).
