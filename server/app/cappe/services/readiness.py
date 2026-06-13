"""Launch readiness — the checklist that decides whether a site can publish.

A site can't go live until the REQUIRED items are done (it has real content and
something to book or buy). Recommended items are nudges, not blockers. The same
computation backs the GET /readiness endpoint and the publish gate, so the UI
and the server can never disagree about what's missing.
"""
from ..routes._shared import loads

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


async def compute_readiness(conn, site_id, site_row) -> dict:
    """Return {ready, items} for a site. `site_row` is the cappe_sites record."""
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
            "key": "offering", "required": True, "done": has_offering, "action": "shop",
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
    ready = all(i["done"] for i in items if i["required"])
    return {"ready": ready, "items": items}
