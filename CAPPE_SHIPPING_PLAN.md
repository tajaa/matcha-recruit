# Cappe: Physical-goods shipping via Stripe — mechanical execution spec

## Context

Cappe (Gummfit storefronts) has real Stripe Connect checkout (`services/stripe_connect.py`), inventory decrement, per-site tax, and an order status enum — but a `physical` product checks out identically to a digital one: no shipping address is collected anywhere, no shipping cost exists, fulfillment has no carrier/tracking. This spec completes the physical-goods loop.

**Locked decisions** (confirmed with user):
- Address collected **by Stripe** (`shipping_address_collection` on the Checkout Session), persisted from the webhook. No storefront form changes.
- Shipping priced as a **flat per-site rate** with optional free-shipping threshold — mirrors the tax pattern (`cappe_sites` columns + settings card).
- **Carrier + tracking number** on orders, editable in admin Orders page.
- Platform fee stays on **subtotal only** (shipping, like tax, passes through to the merchant).

**Verified codebase facts this spec is built on:**
- Order creation entry: `create_public_order(site, body, background)` at `server/app/cappe/services/commerce.py:339`.
- `line_rows` tuple shape (commerce.py:480-483): `(product_id, title, unit_price, qty, fulfillment, intake, booking_id, opt_snapshot, sel_ids)` — fulfillment is index 4.
- Site config fetch at commerce.py:499-501; tax math :502-506; order INSERT :507-516 (params `$1`-`$9`); Stripe branch :539-592; fallback :594-612.
- `create_checkout_session` at `stripe_connect.py:103-148` (kwargs-only signature, `_create()` closure at :128-143).
- Webhook `_handle_connect_event(etype, obj, event, background)` at `routes/payments.py:152`; order UPDATE :174-186 uses params `$1`=oid, `$2`=payment_intent, `$3`=fee, `$4`=event_account_id. `payments.py` has **no `json` import** — add one.
- Site update route is **`@router.put("/sites/{site_id}")`** at `routes/sites.py:248` (not PATCH); dynamic-SET `add()` helper at :260-262; `receipt_prefix` nulling pattern at :294-295; `_SITE_COLS` at :50-56.
- `models/shop.py` imports only `BaseModel, EmailStr, Field` from pydantic — **add `model_validator`**.
- `_ORDER_COLS` at `routes/shop.py:46-51`; `_order_row(row, items)` at :110-114 (decodes `metadata` via `loads`); order PATCH `update_order_status` at :394-422 with restock sets `_RESTOCK_FROM_STATUSES`/`_RESTOCK_TO_STATUSES` at :36-37.
- JSONB helpers: `services/common.py:60 loads()` (returns `{}` for None — so use `loads(x) or None` where None must survive), `:73 loads_list()`.
- Receipt: `render_order_receipt_pdf` SELECT at `services/receipt.py:149-156`; `build_receipt_html` :89-143 (tax_row :104-108, Billed-to block :121-124).
- Public buyer endpoint: `GET /public/orders/{token}` at `routes/public/shop.py:97-145`; response model `CappeOrderReceipt` at `models/shop.py:243-251`.
- Migration head for cappe chain: `zzzzcappe27` (`zzzzcappe27_merlin_setup_concierge.py`). Idempotency convention: `op.execute("... IF NOT EXISTS ...")` per `zzzzcappe18_inventory.py`.
- Tests: `server/tests/cappe/` is **pure-function only** (no DB, no app boot — see `test_cappe_commerce.py` preamble with `os.environ.setdefault`). Therefore all new logic that needs tests is extracted into pure helpers.
- Frontend: `client/src/cappe/types.ts` — `CappeSite` at :51, `CappeOrder` at :345. `TaxSettingsCard.tsx` saves via `cappeApi.put('/sites/{id}')`. `Shop.tsx` imports it at :6, renders at :133. `Orders.tsx` `setStatus` at :51-54 PATCHes `{status}`; expanded panel :126-177.

---

## Step 1 — Migration `server/alembic/versions/zzzzcappe28_shipping.py`

New file, exact shape of `zzzzcappe18_inventory.py`:

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

`shipping_address` is one JSONB written once verbatim from Stripe's `{name, address:{line1,line2,city,state,postal_code,country}}` — survives Stripe shape drift. `NOT NULL DEFAULT 0` cents columns keep pre-migration rows NULL-free.

**⚠️ Author + commit only. Do NOT run `alembic upgrade` — user applies via `migrate-dev.sh`/`migrate-prod.sh` per root CLAUDE.md.** (Commit-before-apply rule from `server/CLAUDE.md` migration section.)

## Step 2 — Order creation: `server/app/cappe/services/commerce.py`

**2a. New pure function** (module level, near `order_subtotal` at :42 — this is the unit-testable core):

```python
def compute_shipping_cents(
    *, has_physical: bool, subtotal_cents: int, flat_cents: int,
    free_threshold_cents: int | None,
) -> int:
    """Flat per-site shipping for carts with a physical line; zero when the
    free-shipping threshold is met. Threshold compares the GOODS subtotal
    (pre-tax), matching what the buyer sees advertised ("free over $50")."""
    if not has_physical or flat_cents <= 0:
        return 0
    if free_threshold_cents is not None and subtotal_cents >= free_threshold_cents:
        return 0
    return flat_cents
```

**2b. Site-config fetch (:499-506)** — extend the existing `fetchrow` and compute:

```python
tax_cfg = await conn.fetchrow(
    "SELECT tax_rate_bps, tax_label, shipping_flat_cents, "
    "shipping_free_threshold_cents, shipping_label "
    "FROM cappe_sites WHERE id = $1", site["id"]
)
# ... existing tax_rate_bps / tax_label / taxable / tax_cents lines unchanged ...
has_physical = any(f == "physical" for (_p, _t, _u, _q, f, *_r) in line_rows)
shipping_cents = compute_shipping_cents(
    has_physical=has_physical,
    subtotal_cents=subtotal,
    flat_cents=int(tax_cfg["shipping_flat_cents"]) if tax_cfg else 0,
    free_threshold_cents=tax_cfg["shipping_free_threshold_cents"] if tax_cfg else None,
)
shipping_label = (tax_cfg["shipping_label"] if tax_cfg else None) or "Shipping"
total_cents = subtotal + tax_cents + shipping_cents
```

**2c. Order INSERT (:507-516)** — add the column + param (`$1`-`$9` becomes `$1`-`$10`) and RETURNING:

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

**2d. Stripe branch (:573-583)** — two new kwargs on the `create_checkout_session` call. Shipping is **not** a line item — it rides Stripe `shipping_options` (renders as a real shipping row, "Free" at 0, included in `amount_total`; charge equals `total_cents` by construction). `fee = entitlement_fee_cents(pay_total, …)` at :550 stays on `pay_total = order["subtotal_cents"]` (:539) — **unchanged**.

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

**2e. Fallback path (:594-612)** — no change. `shipping_cents` is already persisted inside `total_cents`; no address exists because no Stripe session ran (same existing quirk as tax in the fallback receipt email, which reads `subtotal_cents`).

## Step 3 — Stripe wrapper: `server/app/cappe/services/stripe_connect.py`

**3a. Module constant** (near `platform_fee_cents` at :33):

```python
# Gummfit storefronts are US-facing. Per-site country config is a deliberate
# later one-column follow-up, not scope here.
CAPPE_SHIPPING_COUNTRIES = ["US"]
```

**3b. Pure helper** (module level — unit-testable):

```python
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

**3c. `create_checkout_session` (:103-148)** — two new keyword params, threaded into `_create()`:

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
```

Inside `_create()` (docstring gains one line noting shipping kwargs; existing body otherwise intact):

```python
def _create():
    extra: dict[str, Any] = {}
    if collect_shipping_address:
        extra["shipping_address_collection"] = {"allowed_countries": CAPPE_SHIPPING_COUNTRIES}
        opts = build_shipping_options(shipping_option, currency)
        if opts:
            extra["shipping_options"] = opts
    return stripe.checkout.Session.create(
        mode="payment",
        ...existing args unchanged...,
        stripe_account=account_id,
        **extra,
    )
```

Digital/service/booking-only carts pass `collect_shipping_address=False` → `extra` empty → checkout byte-identical to today.

**3d. New helper `retrieve_checkout_session`** (place after `create_checkout_session`, same pattern as `retrieve_account` :90-100):

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

## Step 4 — Webhook: `server/app/cappe/routes/payments.py`

**4a.** Add `import json` to the stdlib import block (currently absent).

**4b. Pure extractor** (module level — unit-testable; StripeObject is dict-like so it works on both raw event payloads and retrieved sessions):

```python
def extract_shipping_details(obj: dict) -> Optional[dict]:
    """Newer Stripe API versions nest the address under
    collected_information.shipping_details; older ones put it at top level.
    Read both; None when absent either way."""
    collected = obj.get("collected_information") or {}
    return collected.get("shipping_details") or obj.get("shipping_details") or None
```

**4c. In `_handle_connect_event`**, inside the `if oid is not None and event_account_id:` branch (:165), **before** `async with get_connection()` (:173) — respects the existing no-pooled-conn-held-across-Stripe-call ordering:

```python
ship = extract_shipping_details(obj)
if ship is None and obj.get("id"):
    try:
        sess = await get_cappe_stripe().retrieve_checkout_session(event_account_id, obj["id"])
        ship = extract_shipping_details(sess)
    except CappeStripeError:
        ship = None  # best-effort; never block marking the order paid
```

**4d. Extend the UPDATE (:174-186)** — new `$5`:

```python
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

(`dict(ship)` because a retrieved-session StripeObject isn't guaranteed plain-dict for `json.dumps`.)

## Step 5 — Admin API: `routes/shop.py` + `models/shop.py`

**5a. `models/shop.py`** — add `model_validator` to the pydantic import at :7. Replace `CappeOrderStatusUpdate` (:196-197):

```python
class CappeOrderStatusUpdate(BaseModel):
    """Order PATCH body — status transition and/or tracking edit. At least one
    field must be present; a tracking-only PATCH must not touch status/stock."""
    status: Optional[Literal["pending", "paid", "fulfilled", "cancelled", "refunded"]] = None
    carrier: Optional[str] = Field(default=None, max_length=40)
    tracking_number: Optional[str] = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if self.status is None and not ({"carrier", "tracking_number"} & self.model_fields_set):
            raise ValueError("Provide status, carrier, or tracking_number")
        return self
```

(`model_fields_set` check — not `is None` — so `{"carrier": null}` is a valid explicit clear.)

**5b. `CappeOrder` (:157-176)** — add after `tax_cents`:

```python
shipping_cents: int = 0
shipping_address: Optional[dict[str, Any]] = None
carrier: Optional[str] = None
tracking_number: Optional[str] = None
```

**5c. `routes/shop.py` `_ORDER_COLS` (:46-51)** — add `shipping_cents, shipping_address, carrier, tracking_number` (insert after `tax_cents, total_cents,`). This flows the new fields into every order list/detail/accept/decline endpoint automatically (they all `RETURNING/SELECT {_ORDER_COLS}`).

**5d. `_order_row` (:110-114)** — JSONB decode, same treatment as `metadata`:

```python
def _order_row(row, items=None) -> dict:
    d = dict(row)
    d["metadata"] = loads(row["metadata"])
    d["shipping_address"] = loads(row["shipping_address"]) or None   # loads() maps NULL→{}; keep None
    d["items"] = items or []
    return d
```

**5e. Rewrite `update_order_status` (:394-422)** as dynamic SET. Restock logic preserved verbatim and gated on `body.status is not None`. FOR-UPDATE lock read stays unconditional (it doubles as the 404 existence check and serializes concurrent PATCHes):

```python
@router.patch("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def update_order_status(
    site_id: UUID, order_id: UUID, body: CappeOrderStatusUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            current = await conn.fetchrow(
                "SELECT status FROM cappe_orders WHERE id = $1 AND site_id = $2 FOR UPDATE",
                order_id, site_id,
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

            sets = ["updated_at = NOW()"]
            args: list = []

            def add(col: str, val):
                args.append(val)
                sets.append(f"{col} = ${len(args)}")

            if body.status is not None:
                add("status", body.status)
            if "carrier" in body.model_fields_set:
                add("carrier", (body.carrier or "").strip() or None)
            if "tracking_number" in body.model_fields_set:
                add("tracking_number", (body.tracking_number or "").strip() or None)

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

## Step 6 — Receipt PDF: `services/receipt.py`

**6a. Order SELECT (:149-156)** — add `o.shipping_cents, o.shipping_address,` and `s.shipping_label` to the column list (site is already joined).

**6b. `build_receipt_html` (:89-143)**:

- Money block (:98-102): `shipping = int(order.get("shipping_cents") or 0)`; `total` fallback becomes `subtotal + tax + shipping`; `shipping_label = escape(str(order.get("shipping_label") or "Shipping"))`.
- Shipping row mirroring `tax_row` (:104-108), rendered between subtotal and total:

```python
shipping_row = (
    f'<tr><td style="padding:4px 0;text-align:right;color:#71717a;">{shipping_label}</td>'
    f'<td style="padding:4px 0;text-align:right;width:120px;">{_fmt(shipping, cur)}</td></tr>'
    if shipping > 0 else ""
)
```

- Ship-to block beside "Billed to" (:121-124). Address arrives as str-or-dict (asyncpg JSONB) — normalize like `_items_rows_html` does for `selected_options` (:66-70), or import `loads` from `.common`. **HTML-escape every field**:

```python
def _ship_to_html(shipping_address) -> str:
    addr = shipping_address
    if isinstance(addr, str):
        try:
            addr = json.loads(addr)
        except ValueError:
            addr = None
    if not isinstance(addr, dict):
        return ""
    a = addr.get("address") or {}
    city_line = ", ".join(x for x in [a.get("city"), a.get("state")] if x)
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

Render `{_ship_to_html(order.get("shipping_address"))}` directly after the Billed-to `</div>` and interpolate `{shipping_row}` above the Total row (next to `{tax_row}`).

## Step 7 — Public order status: `routes/public/shop.py:97-145` + `models/shop.py:243-251`

- SELECT (:104-108): add `shipping_cents, carrier, tracking_number`.
- Response construction (:122-129): pass the three through.
- `CappeOrderReceipt` (models/shop.py:243-251): add

```python
shipping_cents: int = 0
carrier: Optional[str] = None
tracking_number: Optional[str] = None
```

**Deliberately omit `shipping_address` from the public payload** — the access token is shareable/leakable; tracking number is low-blast-radius, a home address is not. (The endpoint already omits `tax_cents`/`total_cents`; leaving that as-is, not scope here.)

## Step 8 — Site settings (tax pattern, 4 edit points)

**8a. `models/sites.py` `CappeSiteUpdate` (:57-72)** — after `tax_label`:

```python
shipping_flat_cents: Optional[int] = Field(default=None, ge=0)
# None = clear the threshold (explicit-null via model_fields_set in the route)
shipping_free_threshold_cents: Optional[int] = Field(default=None, ge=0)
shipping_label: Optional[str] = Field(default=None, max_length=40)
```

**8b. `CappeSite` response (:91-119)** — after `tax_label`:

```python
shipping_flat_cents: int = 0
shipping_free_threshold_cents: Optional[int] = None
shipping_label: str = "Shipping"
```

**8c. `routes/sites.py` `_SITE_COLS` (:50-56)** — add `shipping_flat_cents, shipping_free_threshold_cents, shipping_label,` after `tax_rate_bps, tax_label, receipt_prefix,`.

**8d. PUT handler `add()` block (:290-295)** — after the `tax_label` branch:

```python
if body.shipping_flat_cents is not None:
    add("shipping_flat_cents", body.shipping_flat_cents)
if "shipping_free_threshold_cents" in body.model_fields_set:
    # model_fields_set (not `is not None`) so an explicit null CLEARS the threshold
    add("shipping_free_threshold_cents", body.shipping_free_threshold_cents)
if body.shipping_label is not None:
    add("shipping_label", body.shipping_label.strip() or "Shipping")
```

Check `site_row_to_dict` in the sites route-helpers module — it should be a generic `dict(row)` pass-through so the new `_SITE_COLS` entries flow; if it whitelists columns, add the three there too.

## Step 9 — Frontend (`client/src/cappe/` only — cappeApi + its own ui stack, never Matcha's)

**9a. `types.ts`**:

- `CappeSite` (:51): add `shipping_flat_cents?: number | null`, `shipping_free_threshold_cents?: number | null`, `shipping_label?: string | null` (next to `tax_rate_bps` at :65).
- New exported type + `CappeOrder` (:345) additions (next to `tax_cents` :352):

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

// on CappeOrder:
shipping_cents: number
shipping_address?: CappeShippingAddress | null
carrier?: string | null
tracking_number?: string | null
```

**9b. New `components/ShippingSettingsCard.tsx`** — clone `TaxSettingsCard.tsx` structurally (same load-on-mount `cappeApi.get<CappeSite>`, same save via `cappeApi.put('/sites/{siteId}', …)`, same saving/saved/error state, `Truck` icon from lucide):

- Fields: "Flat rate ($)" (decimal input → `Math.max(0, Math.round(parseFloat(v) * 100))`, empty/NaN → 0), "Free over ($)" (empty string → `null`, else cents), "Label" (default "Shipping", maxLength 40).
- Save body: `{ shipping_flat_cents, shipping_free_threshold_cents, shipping_label }`.
- Footer hint: "Applies once per order when the cart contains a physical product. Address is collected by Stripe at checkout."

**9c. `pages/site/Shop.tsx`** — import next to `TaxSettingsCard` (:6), render `<ShippingSettingsCard siteId={siteId || ''} />` next to :133.

**9d. `pages/site/Orders.tsx`** — in the expanded panel (:126-177):

- Ship-to block, before the items list, when `o.shipping_address` present: render name/line1/line2/city-state-postal/country as small zinc text (JSX auto-escapes).
- Inline `TrackingEditor` component (defined in the same file, below `Orders`) rendered when `o.shipping_address != null || o.items.some((i) => i.fulfillment === 'physical')`:

```tsx
function TrackingEditor({ siteId, order, onSaved }: {
  siteId: string
  order: CappeOrder
  onSaved: (o: CappeOrder) => void
}) {
  const [carrier, setCarrier] = useState(order.carrier || '')
  const [tracking, setTracking] = useState(order.tracking_number || '')
  const [saving, setSaving] = useState(false)
  // save():
  //   const updated = await cappeApi.patch<CappeOrder>(
  //     `/sites/${siteId}/orders/${order.id}`,
  //     { carrier: carrier.trim() || null, tracking_number: tracking.trim() || null },
  //   )
  //   onSaved({ ...updated, items: order.items })
}
```

Two small inputs (carrier placeholder "USPS", tracking placeholder "9400 1000 0000 …") + Save button, matching the zinc input classes already in the file (:117-123). `onSaved` merges via the existing `setOrders` map pattern (:53). **Note the `{ ...updated, items: order.items }` merge** — the PATCH response carries items, but keeping the established local-merge idiom avoids clobbering in-flight item edits.

- Existing `setStatus` (:51-54) keeps sending `{status}` only — still valid against the new optional model.

**9e. `server/app/cappe/services/render/assets/store.js`** — no functional change (Stripe collects the address). Optional one-line "Shipping calculated at checkout" hint on physical product cards; skip if it doesn't drop in cleanly.

## Step 10 — Tests: new `server/tests/cappe/test_cappe_shipping.py`

Pure-function style per `test_cappe_commerce.py` (same `os.environ.setdefault` preamble for `LIVE_API`/`DATABASE_URL`/`JWT_SECRET_KEY`; no DB, no app boot). Cases:

```python
# --- compute_shipping_cents (app.cappe.services.commerce) ---
def test_shipping_zero_without_physical():        # digital-only cart
    assert compute_shipping_cents(has_physical=False, subtotal_cents=5000, flat_cents=700, free_threshold_cents=None) == 0

def test_shipping_flat_applied_to_physical():
    assert compute_shipping_cents(has_physical=True, subtotal_cents=5000, flat_cents=700, free_threshold_cents=None) == 700

def test_shipping_zero_when_rate_unset():         # site never configured shipping
    assert compute_shipping_cents(has_physical=True, subtotal_cents=5000, flat_cents=0, free_threshold_cents=None) == 0

def test_shipping_threshold_met_exactly():        # boundary: >= not >
    assert compute_shipping_cents(has_physical=True, subtotal_cents=5000, flat_cents=700, free_threshold_cents=5000) == 0

def test_shipping_threshold_not_met():
    assert compute_shipping_cents(has_physical=True, subtotal_cents=4999, flat_cents=700, free_threshold_cents=5000) == 700

def test_shipping_threshold_zero_means_always_free():
    assert compute_shipping_cents(has_physical=True, subtotal_cents=1, flat_cents=700, free_threshold_cents=0) == 0

# --- build_shipping_options (app.cappe.services.stripe_connect) ---
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
    assert opt["shipping_rate_data"]["fixed_amount"]["amount"] == 0   # 0-amount row still emitted

# --- extract_shipping_details (app.cappe.routes.payments) ---
def test_extract_shipping_new_api_shape():        # collected_information.shipping_details
def test_extract_shipping_legacy_shape():         # top-level shipping_details
def test_extract_shipping_prefers_collected():    # both present → collected_information wins
def test_extract_shipping_absent_returns_none():  # {} and {"collected_information": {}} → None

# --- CappeOrderStatusUpdate (app.cappe.models.shop) ---
def test_order_update_requires_a_field():         # {} → pydantic.ValidationError
def test_order_update_status_only_ok():
def test_order_update_tracking_only_ok():         # {"carrier": "USPS"} valid; status stays None
def test_order_update_explicit_null_carrier_ok(): # {"carrier": None} valid (explicit clear)
def test_order_update_rejects_bad_status():       # {"status": "shipped"} → ValidationError
def test_order_update_length_caps():              # carrier 41 chars / tracking 121 chars → ValidationError

# --- build_receipt_html (app.cappe.services.receipt) ---
def test_receipt_shipping_row_rendered():
    html = build_receipt_html({..., "shipping_cents": 700, "shipping_label": "Shipping", "total_cents": 5700}, [])
    assert "Shipping" in html and "$7.00" in html

def test_receipt_no_shipping_row_when_zero():
def test_receipt_ship_to_block_and_escaping():
    addr = {"name": "<script>x</script>", "address": {"line1": "1 Main St", "city": "Reno", "state": "NV", "postal_code": "89501", "country": "US"}}
    html = build_receipt_html({..., "shipping_address": addr}, [])
    assert "Ship to" in html and "&lt;script&gt;" in html and "<script>x" not in html

def test_receipt_ship_to_handles_str_jsonb():     # shipping_address passed as json string (asyncpg)
def test_receipt_total_fallback_includes_shipping():  # total_cents=None → subtotal+tax+shipping
```

Run: `cd server && ./venv/bin/python -m pytest tests/cappe/ -q` — new file plus the existing cappe suite must stay green.

## Verification

1. **Tests** — command above.
2. **Static** — post-edit hook runs `py_compile` per file; `cd client && npx tsc -p tsconfig.app.json --noEmit` (never bare `npx tsc --noEmit` — it checks nothing).
3. **Manual (user-run, Stripe test mode)** — apply migration via `./scripts/migrate-dev.sh`; `stripe listen --forward-to localhost:8001/api/cappe/payments/webhook` (verified: `@router.post("/payments/webhook")` at payments.py:112, mounted under `/api/cappe`); buy a physical item on a dev storefront → Checkout shows address form + shipping row ("Free shipping" when threshold hit) → webhook lands → order row has `shipping_address` → receipt PDF shows Ship-to + shipping line → set carrier/tracking in Orders page → tokened `/public/orders/{token}` payload shows `carrier`/`tracking_number` but **no address** → digital-only order still checks out with no address form.

## Risks / edge cases

- **Mixed carts** (physical + digital): `has_physical` any-match → shipping applies once per order, correct.
- **Pre-migration pending orders paid after deploy**: `shipping_cents` defaults 0; webhook UPDATE's `COALESCE($5::jsonb, o.shipping_address)` leaves address NULL when Stripe collected none. Fine.
- **`subtotal == 0` physical carts** (free item): `can_pay` false (:540-543) → no Stripe session → no address collected, no shipping charged. Accepted — matches existing free-cart behavior; note only.
- **Tracking-only PATCH must not touch stock**: restock gated on `body.status is not None` + the FROM/TO transition sets — preserved exactly (Step 5e).
- **Threshold clearing**: `model_fields_set` gate in Step 8d; the frontend sends `null` for an emptied "Free over" input.
- **`shipping_options` on direct-charge (connected-account) sessions**: supported by Stripe, but smoke-test in test mode before calling done — if a connected account ever rejects it, the `CappeStripeError` catch at commerce.py:591 degrades to the manual pending flow (order still created, shipping in total).
- **Stripe retrieve fallback**: only fires when the event payload lacks shipping details AND the event is otherwise valid; failure is swallowed (`ship = None`) so the paid-marking + receipt flow never blocks on it. The event-claim/release dedupe (:135-149) is untouched.
- **Deploy order**: code INSERTs/SELECTs the new columns — migration must be applied before the code deploys (user's normal migrate-then-deploy flow).
- **`loads()` None-collapse**: `common.loads()` maps NULL→`{}`; every read site that must distinguish "no address" uses `loads(...) or None` (Step 5d) so Pydantic serializes `null`, not `{}`.
