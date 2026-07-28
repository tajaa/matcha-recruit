"""Cappe Discover — the public directory's taxonomy, inference, and search index.

Three responsibilities, deliberately in one module because they share the
taxonomy constant:

1. ``DIRECTORY_CATEGORIES`` — a FIXED taxonomy. Fixed so browse-by-category is
   possible at all, and so the tag space can't fragment into cafe / café /
   coffeeshop / coffee-shop, which is what kills free-text directory search.
2. ``infer_listing`` — one Gemini call that reads a site and proposes a
   category, tags, and a one-line blurb. **Its output is validated against the
   whitelist and dropped if unknown**, the same authorization-boundary idiom as
   ``core/services/product_definitions.ALLOWED_PRODUCT_FEATURES`` and
   ``legal_defense.validate_citations``: a model that invents a category must
   not be able to write one into the directory.
3. ``refresh_site_search`` — recomputes ``cappe_sites.search_vector``.

Why inference is load-bearing rather than a nicety: listing is OPT-OUT, so a
site is listed the moment it publishes. But the directory has a quality gate
(category + blurb must both be present) so the first screen is never six
"Untitled Site" cards. Without automatic inference at publish time, that gate
silently turns opt-out back into opt-in and the directory stays empty.

``infer_listing`` NEVER raises into a request — a Gemini outage means the site
publishes without a listing and the tenant can fill it in (or press "Suggest
for me") later.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import UUID

from google.genai import types

from ...core.services.genai_client import get_genai_client
from ...core.services.rate_limiter import GeminiRateLimiter

logger = logging.getLogger(__name__)

# Fixed taxonomy: (slug, label). Adding a row is a deliberate product decision —
# it changes what every visitor can browse by. Do NOT let this become
# model-writable.
DIRECTORY_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("food-drink", "Food & Drink"),
    ("beauty-grooming", "Beauty & Grooming"),
    ("fitness", "Fitness & Training"),
    ("wellness", "Health & Wellness"),
    ("photo-video", "Photography & Video"),
    ("art-design", "Art & Design"),
    ("music-audio", "Music & Audio"),
    ("events", "Events & Entertainment"),
    ("trades-home", "Trades & Home Services"),
    ("professional", "Professional Services"),
    ("education", "Education & Tutoring"),
    ("retail", "Retail & Goods"),
    ("pets", "Pets & Animals"),
    ("automotive", "Automotive"),
    ("tech", "Tech & Digital"),
    ("other", "Other"),
)

CATEGORY_SLUGS: frozenset[str] = frozenset(slug for slug, _ in DIRECTORY_CATEGORIES)
CATEGORY_LABELS: dict[str, str] = dict(DIRECTORY_CATEGORIES)

MAX_TAGS = 8
MAX_TAG_LEN = 32
MAX_BLURB_LEN = 200

# Cheapest tier: this is a short classification over text we already hold, not a
# reasoning task. It runs on every publish, so cost per call matters.
_MODEL = "gemini-3.5-flash-lite"
_TIMEOUT_S = 30

_rate_limiter: Optional[GeminiRateLimiter] = None


def _get_rate_limiter() -> GeminiRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter


# ---------------------------------------------------------------------------
# Validation (pure — unit-testable without a DB or Gemini)
# ---------------------------------------------------------------------------

def normalize_category(value: Any) -> Optional[str]:
    """A category the model (or a client) proposed → a whitelisted slug or None.

    Accepts the label as well as the slug, because the model reads labels in the
    prompt and will sometimes echo one back. Anything unrecognized returns None
    rather than being stored — an invented category would be unbrowsable and
    would quietly split the taxonomy.
    """
    if not isinstance(value, str):
        return None
    v = value.strip().lower().replace("_", "-").replace(" & ", "-").replace(" ", "-")
    if v in CATEGORY_SLUGS:
        return v
    for slug, label in DIRECTORY_CATEGORIES:
        if value.strip().lower() == label.lower():
            return slug
    return None


def normalize_tags(value: Any) -> list[str]:
    """Free-form tag list → deduped, lowercased, length- and count-capped.

    Tags are intentionally NOT whitelisted (they are the long tail the fixed
    taxonomy can't cover), but they are normalized hard so 'Cold Brew' and
    'cold brew ' collapse to one token.
    """
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            continue
        tag = " ".join(raw.strip().lower().split())[:MAX_TAG_LEN].strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= MAX_TAGS:
            break
    return out


def normalize_blurb(value: Any) -> Optional[str]:
    """One-line description → trimmed, single-spaced, length-capped, or None."""
    if not isinstance(value, str):
        return None
    blurb = " ".join(value.strip().split())[:MAX_BLURB_LEN].strip()
    return blurb or None


def category_options() -> list[dict[str, str]]:
    """The taxonomy as the frontend consumes it."""
    return [{"slug": slug, "label": label} for slug, label in DIRECTORY_CATEGORIES]


# ---------------------------------------------------------------------------
# Search vector
# ---------------------------------------------------------------------------

# Weighted so a name match outranks a tag match outranks a stray product name.
# D deliberately holds the noisy sources (every product a shop sells, every city
# it operates in) — they should make a site FINDABLE without letting a shop with
# 200 products outrank an exact name match.
#
# Writes to `cappe_site_search`, NOT a column on `cappe_sites` — see the
# migration: `get_owned_site` is `SELECT *`, so a tsvector on the sites table
# would ride along on every owner-side read that never uses it.
_SEARCH_SQL = """
INSERT INTO cappe_site_search (site_id, search_vector, updated_at)
SELECT s.id,
        setweight(to_tsvector('english', coalesce(s.name, '')), 'A') ||
        setweight(to_tsvector('english',
            coalesce($2::text, '') || ' ' || coalesce(array_to_string(s.directory_tags, ' '), '')), 'B') ||
        setweight(to_tsvector('english', coalesce(s.directory_blurb, '')), 'C') ||
        setweight(to_tsvector('english', coalesce((
            SELECT string_agg(DISTINCT concat_ws(' ', p.name, p.category), ' ')
              FROM cappe_products p
             WHERE p.site_id = s.id AND p.status = 'active'
        ), '')), 'D') ||
        setweight(to_tsvector('english', coalesce((
            SELECT string_agg(DISTINCT concat_ws(' ', l.city, l.region), ' ')
              FROM cappe_locations l
             WHERE l.site_id = s.id AND l.active
        ), '')), 'D'),
       NOW()
  FROM cappe_sites s
 WHERE s.id = $1
ON CONFLICT (site_id) DO UPDATE
   SET search_vector = EXCLUDED.search_vector, updated_at = NOW()
"""


async def refresh_site_search(conn, site_id: UUID) -> None:
    """Recompute one site's ``search_vector``.

    Called from the paths that mean "this site's discoverable content changed":
    publish, the listing save, and product writes. Those are the same call sites
    that already invalidate the render cache, because that is the same event.

    Best-effort: a failure here must not fail the write that triggered it — a
    stale search vector is a bad search result, not a lost sale.
    """
    try:
        category_label = await conn.fetchval(
            "SELECT directory_category FROM cappe_sites WHERE id = $1", site_id
        )
        # Index the human label too, so a search for "photography" hits a site
        # categorized `photo-video`.
        label_text = CATEGORY_LABELS.get(category_label or "", "") + " " + (category_label or "")
        await conn.execute(_SEARCH_SQL, site_id, label_text.strip())
    except Exception as exc:  # noqa: BLE001 - never fail the caller's write
        logger.warning("directory: refresh_site_search failed for %s: %s", site_id, exc)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _collect_text(content: Any, out: list[str], budget: int = 40) -> None:
    """Pull human-readable strings out of a page's block JSON, depth-first.

    The page content shape is the block catalog's, but this must not depend on
    it — a directory listing is not worth coupling to every block type, and an
    unknown block should still contribute its text.
    """
    if len(out) >= budget:
        return
    if isinstance(content, str):
        text = " ".join(content.split())
        # Skip URLs, colors, and other machine values.
        if 2 < len(text) <= 300 and not text.startswith(("http://", "https://", "#", "data:")):
            out.append(text)
    elif isinstance(content, dict):
        for key, val in content.items():
            if key in ("url", "href", "src", "image", "image_url", "color", "bg", "id", "type"):
                continue
            _collect_text(val, out, budget)
    elif isinstance(content, list):
        for item in content:
            _collect_text(item, out, budget)


async def gather_site_context(conn, site_id: UUID) -> Optional[dict[str, Any]]:
    """Everything ``infer_listing`` reads, in one round trip each. None if gone."""
    site = await conn.fetchrow(
        """SELECT s.id, s.name, s.meta_config, a.account_type
             FROM cappe_sites s JOIN cappe_accounts a ON a.id = s.account_id
            WHERE s.id = $1""",
        site_id,
    )
    if site is None:
        return None

    pages = await conn.fetch(
        "SELECT title, content FROM cappe_pages WHERE site_id = $1 AND status = 'published' "
        "ORDER BY sort_order, created_at LIMIT 5",
        site_id,
    )
    products = await conn.fetch(
        "SELECT name, category, fulfillment FROM cappe_products "
        "WHERE site_id = $1 AND status = 'active' ORDER BY sort_order, created_at LIMIT 25",
        site_id,
    )
    booking_types = await conn.fetch(
        "SELECT name FROM cappe_booking_types WHERE site_id = $1 AND status = 'active' LIMIT 15",
        site_id,
    )
    locations = await conn.fetch(
        "SELECT city, region FROM cappe_locations WHERE site_id = $1 AND active LIMIT 5", site_id
    )

    meta = site["meta_config"]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (TypeError, ValueError):
            meta = {}
    meta = meta if isinstance(meta, dict) else {}

    page_text: list[str] = []
    for page in pages:
        page_text.append(page["title"] or "")
        content = page["content"]
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (TypeError, ValueError):
                content = None
        _collect_text(content, page_text)

    return {
        "name": site["name"],
        "account_type": site["account_type"],
        "seo_description": ((meta.get("seo") or {}).get("description") if isinstance(meta.get("seo"), dict) else None),
        "tagline": meta.get("tagline"),
        "page_text": page_text[:40],
        "products": [
            {"name": p["name"], "category": p["category"], "fulfillment": p["fulfillment"]}
            for p in products
        ],
        "booking_types": [b["name"] for b in booking_types],
        "locations": [
            {"city": loc["city"], "region": loc["region"]}
            for loc in locations if loc["city"] or loc["region"]
        ],
    }


def _build_prompt(ctx: dict[str, Any]) -> str:
    catalog = "\n".join(f"  {slug} — {label}" for slug, label in DIRECTORY_CATEGORIES)
    kind = (
        "a SOLO PROFESSIONAL who gets hired or booked (a business of one)"
        if ctx.get("account_type") == "personal"
        else "an ORGANIZATION with a storefront"
    )
    return f"""You are classifying a business for a public directory of small businesses.

This listing is {kind}.

Business name: {ctx.get('name') or '(unnamed)'}
Tagline: {ctx.get('tagline') or '(none)'}
SEO description: {ctx.get('seo_description') or '(none)'}
Locations: {json.dumps(ctx.get('locations') or [], separators=(',', ':'))}
Products/services offered: {json.dumps(ctx.get('products') or [], separators=(',', ':'))}
Bookable services: {json.dumps(ctx.get('booking_types') or [], separators=(',', ':'))}
Text from their website:
{json.dumps(ctx.get('page_text') or [], separators=(',', ':'))}

Choose EXACTLY ONE category slug from this fixed list. You may not invent one —
if nothing fits, use "other":
{catalog}

Then write:
- tags: up to {MAX_TAGS} short lowercase search keywords a customer would
  actually type to find this business (e.g. "espresso", "wedding photography",
  "dog grooming"). Concrete things they offer, not adjectives. No hashtags.
- blurb: ONE sentence, at most {MAX_BLURB_LEN} characters, describing what this
  business does, in plain language, as a directory card subtitle. No marketing
  superlatives, no exclamation marks, do not repeat the business name.

Ground everything in the material above. If the site is nearly empty, say so by
returning "other" with an empty tag list rather than guessing a business type.

Respond with JSON only:
{{"category": "<slug>", "tags": ["..."], "blurb": "..."}}"""


def _parse_json_response(text: str) -> Any:
    """Strip markdown fences (Gemini sometimes wraps JSON in ```json) and parse."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


async def infer_listing(conn, site_id: UUID) -> Optional[dict[str, Any]]:
    """Propose {category, tags, blurb} for a site. None on any failure.

    NEVER raises: this runs as a background task off the publish path, and a
    Gemini outage must not turn into a failed publish. The caller treats None as
    "leave the listing alone".
    """
    ctx = await gather_site_context(conn, site_id)
    if ctx is None:
        return None

    try:
        rate_limiter = _get_rate_limiter()
        await rate_limiter.check_limit("cappe_directory", "infer")
    except Exception as exc:  # noqa: BLE001 - includes RateLimitExceeded
        logger.info("directory: inference skipped for %s: %s", site_id, exc)
        return None

    try:
        client = get_genai_client()
        try:
            # Bounded: this runs in a fire-and-forget background task, so a hung
            # call would hold a DB connection with nothing watching it.
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_MODEL,
                    contents=_build_prompt(ctx),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                    ),
                ),
                timeout=_TIMEOUT_S,
            )
        finally:
            # Record even on failure — the request was issued and billed.
            await rate_limiter.record_call("cappe_directory", "infer")

        payload = _parse_json_response(getattr(response, "text", None) or "")
        if not isinstance(payload, dict):
            raise ValueError("payload was not a JSON object")
    except Exception as exc:  # noqa: BLE001 - best-effort classification
        logger.warning("directory: infer_listing failed for %s: %s", site_id, exc)
        return None

    # The authorization boundary: whatever the model said, only whitelisted
    # values reach the database.
    return {
        "category": normalize_category(payload.get("category")) or "other",
        "tags": normalize_tags(payload.get("tags")),
        "blurb": normalize_blurb(payload.get("blurb")),
    }


async def apply_inferred_listing(conn, site_id: UUID, *, overwrite: bool = False) -> bool:
    """Infer and persist a listing. Returns True if anything was written.

    ``overwrite=False`` (the publish path) fills only the fields that are still
    empty, so re-publishing never clobbers a listing the tenant edited by hand.
    ``overwrite=True`` is the explicit "Suggest for me" button.
    """
    proposal = await infer_listing(conn, site_id)
    if proposal is None:
        return False

    if overwrite:
        await conn.execute(
            """UPDATE cappe_sites
                  SET directory_category = $2::varchar, directory_tags = $3::text[],
                      directory_blurb = $4::varchar,
                      updated_at = NOW()
                WHERE id = $1""",
            site_id, proposal["category"], proposal["tags"], proposal["blurb"],
        )
    else:
        await conn.execute(
            """UPDATE cappe_sites
                  SET directory_category = COALESCE(directory_category, $2::varchar),
                      directory_tags = CASE
                          WHEN directory_tags IS NULL OR cardinality(directory_tags) = 0
                          THEN $3::text[] ELSE directory_tags END,
                      directory_blurb = COALESCE(directory_blurb, $4::varchar),
                      updated_at = NOW()
                WHERE id = $1""",
            site_id, proposal["category"], proposal["tags"], proposal["blurb"],
        )

    await refresh_site_search(conn, site_id)
    return True
