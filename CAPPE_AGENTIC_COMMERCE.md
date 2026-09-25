# Cappe — making stores agentic-commerce ready

Gap analysis, 2026-09-25. Goal: make Gummfit (Cappe) stores purchasable by apps that shop on a user's behalf.

**Caveat:** agentic-commerce protocols are moving fast. Check the current specs before committing to a design. The main ones known at time of writing:

- **ACP** (Agentic Commerce Protocol, OpenAI + Stripe): checkout inside ChatGPT.
- **UCP** (Universal Commerce Protocol, Google): Gemini / AI Mode, alongside Google's AP2 payments protocol.
- **Visa and Mastercard agent programs**: verify that an agent is who it says it is.
- **MCP**: a generic "store as a tool" option for any agent.

The shape they all need is the same, so the gaps below apply to all of them.

## What we already have

- **Server-side pricing:** `server/app/cappe/routes/public/shop.py` recalculates totals from live product rows, and `POST /public/sites/{slug}/quote` returns lines, tax and shipping without creating an order.
- **Guest checkout:** `CappeCheckoutRequest` takes `customer_email` with no login needed.
- **Stock:** per-product and per-option inventory, taken off inside the order transaction (`services/commerce.py:create_public_order`).
- **Payments:** Stripe Connect Standard with direct charges (`services/stripe_connect.py`), so the store is the merchant of record. The agent protocols assume exactly that.
- **Order access:** a token for looking up orders and receipts after purchase (`GET /public/orders/{token}`).

## What's missing

### 1. Agents can't find or understand products

- **No page per product.** The tenant renderer only serves `/` and `/p/{page_slug}` (`routes/render.py`). Agents and product feeds need a stable URL for each product.
- **Wrong structured data.** The only JSON-LD we output is `LocalBusiness` (`services/render/page.py`). There's no `Product` or `Offer` data with price, availability and stock.
- **No `sitemap.xml`, no `robots.txt`, and no product feed.** ACP and Google Merchant each expect a feed.
- **Thin product fields.** Products only have name, description, one `image_url`, price, `sku` and `category`. Feeds want brand, GTIN/MPN, condition, several images, weight, shipping regions, and links to the return policy and terms.
- **Variants aren't real variants.** Options are groups with price add-ons (`cappe_product_options.price_delta_cents`). Feeds and checkout APIs expect each variant to have its own ID, SKU, price and stock, so every option combination would need to become its own item.

### 2. Checkout needs a person to finish it (the biggest gap)

- **One-shot flow ending in a hosted page.** Today `POST /public/sites/{slug}/orders` returns a Stripe Checkout URL, and someone has to click through it. Agents need a checkout session they can build up step by step: create it, update it (address, then shipping options and tax), complete it with a payment token, or cancel it.
- **No way to accept a payment token.** Completing a checkout means charging a token the agent platform hands us (for ACP, Stripe's Shared Payment Token) with a PaymentIntent on the store's Stripe account. We only create Checkout Sessions today.
  - Confirm these tokens work with Standard Connect direct charges.
  - Check whether Stripe's own agentic-commerce product can host the ACP endpoints for connected accounts, which could skip much of this work.
- **No idempotency key on order creation.** Agents retry, and today a retry can create a duplicate order and take stock twice.
- **Shipping and tax need a destination.** Both are flat per-store settings today (`cappe_sites.tax_rate_bps`, `shipping_flat_cents`). That's predictable, but the protocols expect options and totals worked out from the delivery address. At minimum, return shipping options per address and refuse unsupported countries or regions.

### 3. No order updates after purchase

- **No outbound webhooks to the agent platform.** The buyer asks the agent "where's my order?", so the platform needs status changes: confirmed, shipped with carrier and tracking, cancelled, refunded. We store `carrier` and `tracking_number` already but never push them anywhere.
- **No way to send refunds or cancellations** back to the platform.

### 4. Agent identity and abuse limits

- **Rate limits would throttle the platforms.** Order creation allows 10 per minute per IP (`cappe_order` rate limit). Agent platforms send traffic from a few IPs, so they'd hit this almost at once. We need:
  - Per-agent limits keyed on verified identity: an API key per platform, or signed-request verification (the approach the Visa/Mastercard/Cloudflare programs use).
  - Matching CloudFront/WAF rules so real agents aren't blocked.
- **Shopper login doesn't work for agents.** It's an email magic link. That's fine as long as agent orders stay guest orders, but saved addresses and order history won't carry over.

### 5. Store-owner controls and product types

- **An opt-in switch** per store and per product, plus required settings before agent sales go live: return policy, terms URL, shipping regions.
- **Leave out the hard product types at first:** bookings (need a time slot), service products with intake questions, `requires_approval` products, and subscriptions. Physical and digital products fit the protocols cleanly; the rest can come later.

## Suggested order

1. **Discovery:** product pages, Product/Offer JSON-LD, sitemap and robots, a feed endpoint, and the extra product fields. This is cheap and helps normal SEO even if agent checkout never ships.
2. **A protocol-neutral checkout-session service** under `server/app/cappe/services/`, reusing `price_cart` and the order transaction from `create_public_order`, with idempotency, updates by address, and completion with a payment token.
3. **An ACP adapter first**, since we already use Stripe. Then UCP and/or a per-store MCP endpoint on top of the same service.
4. **Outbound order webhooks, per-agent auth and limits, and the store-owner opt-in page.**
