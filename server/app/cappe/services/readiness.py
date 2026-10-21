"""Launch readiness — the checklist that decides whether a site can publish.

A site can't go live until the REQUIRED items are done (it has real content).
Recommended items are nudges, not blockers: having something to book or buy is
one of them, because a brochure, menu or portfolio site is a real site. The same
computation backs the GET /readiness endpoint and the publish gate, so the UI
and the server can never disagree about what's missing.

A store selling physical goods gets a commerce section: its refund and
shipping policies are REQUIRED (a buyer of a parcel is owed both, and the
starter text makes them a minute's work); shipping, tax, the seller's identity
on receipts, product pictures and card payments are nudges.

A writer's magazine site (`source_type='magazine'`) has its own short list: a
published story and a plan that includes magazines are required (the publish
route answers the missing plan with a 402 and the Writer plan first); an about
line and a logo are nudges. It has no shop, so none of the commerce items.
"""
from .common import loads
from .entitlements import resolve_entitlements
from .policies import REQUIRED_FOR_PHYSICAL

# One round trip for everything the commerce items look at.
_COMMERCE_SQL = """
SELECT
  (SELECT COUNT(*) FROM cappe_products
    WHERE site_id = $1 AND status = 'active' AND fulfillment = 'physical') AS physical,
  (SELECT COUNT(*) FROM cappe_products
    WHERE site_id = $1 AND status = 'active' AND fulfillment = 'physical'
      AND COALESCE(image_url, '') = '') AS physical_without_picture,
  (EXISTS (SELECT 1 FROM cappe_products WHERE site_id = $1 AND status = 'active' AND price_cents > 0)
   OR EXISTS (SELECT 1 FROM cappe_booking_types
               WHERE site_id = $1 AND status = 'active' AND COALESCE(price_cents, 0) > 0)) AS sells_paid,
  EXISTS (SELECT 1 FROM cappe_shipping_rates WHERE site_id = $1) AS has_rates,
  ARRAY(SELECT kind FROM cappe_site_policies WHERE site_id = $1) AS policy_kinds,
  (SELECT COALESCE(a.stripe_charges_enabled, false) FROM cappe_sites s
     JOIN cappe_accounts a ON a.id = s.account_id WHERE s.id = $1) AS takes_cards
"""


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _commerce_items(facts, site_row) -> list[dict]:
    items = []
    if _get(facts, "sells_paid"):
        items.append({
            "key": "payments", "required": False, "done": bool(_get(facts, "takes_cards")), "action": "payments",
            "label": "Take card payments",
            "hint": "Connect Stripe so buyers can pay by card at checkout.",
        })
    if not _get(facts, "physical"):
        return items
    kinds = set(_get(facts, "policy_kinds") or ())
    shipping_set = bool(
        int(_get(site_row, "shipping_flat_cents") or 0) > 0
        or _get(site_row, "shipping_free_threshold_cents") is not None
        or _get(facts, "has_rates")
    )
    items += [
        {
            "key": "policies", "required": True, "done": all(k in kinds for k in REQUIRED_FOR_PHYSICAL),
            "action": "policies",
            "label": "Publish your refund and shipping policies",
            "hint": "Buyers of physical goods are owed both. Start from our text and make it yours.",
        },
        {
            "key": "shipping", "required": False, "done": shipping_set, "action": "shipping",
            "label": "Set what shipping costs",
            "hint": "A flat rate, free over an amount, or delivery options. If it's always free, set Free over to 0.",
        },
        {
            "key": "tax", "required": False, "done": int(_get(site_row, "tax_rate_bps") or 0) > 0, "action": "tax",
            "label": "Set your tax rate",
            "hint": "Skip this if you don't charge tax where you sell.",
        },
        {
            "key": "identity", "required": False,
            "done": bool((_get(site_row, "legal_name") or "").strip() and (_get(site_row, "business_address") or "").strip()),
            "action": "identity",
            "label": "Add your business name and address",
            "hint": "They go on every receipt, with your tax number if you have one.",
        },
        {
            "key": "product_pictures", "required": False,
            "done": not _get(facts, "physical_without_picture"), "action": "shop",
            "label": "Give every product a picture",
            "hint": "Products without one look unfinished in your shop and in link previews.",
        },
    ]
    return items

# Blocks that count as real homepage content (an intro / about / sections).
_CONTENT_BLOCKS = {"hero", "text", "features", "menu", "gallery", "pricing", "testimonial"}
# Blocks that surface the storefront / booking widget on a page.
_SELL_BLOCKS = {"store", "booking"}
_CONTACT_BLOCKS = {"contact", "newsletter", "booking"}


def _block_has_text(block: dict) -> bool:
    """True if a block carries any non-empty human copy (so a placeholder-only
    block doesn't count as 'has content')."""
    for v in block.values():
        if isinstance(v, str) and v.strip():
            # ignore the type discriminator + style keys
            return True
    return False


async def plan_has_magazine(conn, account_id) -> bool:
    plan = await conn.fetchval("SELECT plan FROM cappe_accounts WHERE id = $1", account_id)
    return (await resolve_entitlements(plan, conn=conn)).has("magazine")


async def _magazine_readiness(conn, site_id, site_row) -> dict:
    facts = await conn.fetchrow(
        """SELECT EXISTS (SELECT 1 FROM cappe_posts WHERE site_id = $1 AND format = 'blocks'
                            AND status = 'published' AND hidden_at IS NULL AND word_count > 0) AS has_story,
                  (SELECT COALESCE(about, '') <> '' OR COALESCE(tagline, '') <> ''
                     FROM cappe_magazines WHERE site_id = $1) AS has_about""",
        site_id,
    )
    has_logo = bool((loads(site_row["meta_config"]).get("logo_url") or "").strip())
    items = [
        {
            "key": "story", "required": True, "done": bool(facts["has_story"]), "action": "stories",
            "label": "Publish your first story",
            "hint": "Your magazine opens with its stories: publish one with words and a cover.",
        },
        {
            "key": "magazine_plan", "required": True, "done": await plan_has_magazine(conn, site_row["account_id"]),
            "action": "billing", "label": "Choose the Writer plan",
            "hint": "Your magazine goes live on a plan that includes magazines.",
        },
        {
            "key": "about", "required": False, "done": bool(facts["has_about"]), "action": "magazine",
            "label": "Say what your magazine is about",
            "hint": "A tagline or a few lines about you, in Magazine settings.",
        },
        {
            "key": "branding", "required": False, "done": has_logo, "action": "settings",
            "label": "Add your logo",
            "hint": "Upload a logo so your header looks like you.",
        },
    ]
    return {"ready": all(i["done"] for i in items if i["required"]), "items": items}


async def compute_readiness(conn, site_id, site_row) -> dict:
    """Return {ready, items} for a site. `site_row` is the cappe_sites record."""
    if _get(site_row, "source_type") == "magazine":
        return await _magazine_readiness(conn, site_id, site_row)
    # Gather every block across the site's pages.
    page_rows = await conn.fetch("SELECT content FROM cappe_pages WHERE site_id = $1", site_id)
    block_types: set[str] = set()
    has_content_block = False
    for r in page_rows:
        content = loads(r["content"])
        for b in content.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t:
                block_types.add(t)
            if t in _CONTENT_BLOCKS and _block_has_text({k: v for k, v in b.items() if k != "type"}):
                has_content_block = True

    products = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_products WHERE site_id = $1 AND status = 'active'", site_id
    )
    booking_types = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND status = 'active'", site_id
    )
    forms = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_forms WHERE site_id = $1 AND status = 'active'", site_id
    )
    has_offering = (products or 0) > 0 or (booking_types or 0) > 0
    sells_on_page = bool(block_types & _SELL_BLOCKS)
    has_contact = bool(block_types & _CONTACT_BLOCKS) or (forms or 0) > 0

    meta = loads(site_row["meta_config"])
    has_logo = bool((meta.get("logo_url") or "").strip())

    items = [
        {
            "key": "content", "required": True, "done": has_content_block, "action": "pages",
            "label": "Add an intro / about section",
            "hint": "Tell visitors who you are — add a hero or text section to your homepage.",
        },
        {
            "key": "offering", "required": False, "done": has_offering, "action": "shop",
            "label": "Add something to book or buy",
            "hint": "A product, service, or a bookable session — what people pay you for.",
        },
        {
            "key": "sell_on_page", "required": False, "done": sells_on_page, "action": "pages",
            "label": "Show your shop or booking on a page",
            "hint": "Add a Storefront or Booking block so visitors can actually purchase.",
        },
        {
            "key": "contact", "required": False, "done": has_contact, "action": "pages",
            "label": "Give people a way to reach you",
            "hint": "Add a contact form, booking, or newsletter block.",
        },
        {
            "key": "branding", "required": False, "done": has_logo, "action": "settings",
            "label": "Add your logo",
            "hint": "Upload a logo so your header looks like you.",
        },
    ]
    items += _commerce_items(await conn.fetchrow(_COMMERCE_SQL, site_id), site_row)
    ready = all(i["done"] for i in items if i["required"])
    return {"ready": ready, "items": items}
