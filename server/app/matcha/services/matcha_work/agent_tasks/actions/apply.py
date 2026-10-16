"""Apply: take the person to a home's application.

Espresso never applies, pays an application fee or signs anything, and fills
nothing in: an application asks for things only the person should give. What
it does is find the application the listing's own page links to (an "Apply
now" button, often on the building's leasing portal) and open it there.

* The listing's page is loaded now (SSRF-guarded), and its links are read for
  one that says "apply" (in its words, or in its path). A link with the words
  beats one with only the path; the listing's own site beats a leasing portal
  (RentCafe, Entrata, AppFolio, ...), which beats anything else. Job and
  career links are skipped, and so is fine print ("Restrictions apply").
* None found, or the page couldn't be read: the listing's page, so the person
  applies or contacts the leasing office there. A page that's gone (404/410)
  is refused: the home may be off the market.

The link is read from the finding's own page (provenance-gated when it was
found), never from a model.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlsplit

from app.core.services.safe_fetch import UnsafeURL, fetch_public
from app.database import decode_jsonb
from app.matcha.services.matcha_work.agent_card.page_extract import anchors, site_of

from ..research import providers
from .base import ActionContext, ActionError, ItemAction, Line, Proposal, outcome

logger = logging.getLogger(__name__)

PAGE_BYTES = 2_000_000
PAGE_SECONDS = 15.0
MAX_LINKS = 400
_APPLY_TEXT = re.compile(r"\bapply\b|\bapplication\b|\blease\s+(?:now|online|today)\b", re.I)
_APPLY_PATH = re.compile(r"(?:^|[/_.-])(?:apply|application|applicant|onlineleasing)(?:[/_.?-]|$)", re.I)
_NOT_A_HOME = re.compile(r"\b(?:jobs?|careers?|employment|hiring)\b", re.I)
# Fine print says "apply" too ("Restrictions apply", "Terms and conditions may
# apply"): it is dropped before the words are read, so a specials banner's
# terms link never passes for the application.
_FINE_PRINT = re.compile(
    r"\b(?:restrictions?|terms|conditions|fees?|limitations?|exclusions?|exceptions?|rules?|charges?"
    r"|requirements?|criteria|details)\b(?:\s+\w+){0,3}?\s+apply\b", re.I)
# Where buildings send their applications.
PORTALS = (
    "securecafe.com", "rentcafe.com", "entrata.com", "appfolio.com", "realpage.com", "on-site.com",
    "rentmanager.com", "managebuilding.com", "buildium.com", "rentspree.com", "turbotenant.com",
    "avail.co", "zillow.com", "apartments.com", "knockrentals.com", "yardibreeze.com",
)


def page_of(item: dict) -> str | None:
    """The listing's own page: an http(s) link that isn't one of Google's."""
    return providers.store_link(item.get("url"))


def available(ctx: ActionContext) -> str | None:
    if ctx.item.get("kind") != "listing":
        return "Only homes can be applied to."
    if page_of(ctx.item) is None:
        return "Espresso only has Google's page for this one, not the building's own."
    if ctx.item.get("status") == "unavailable":
        return "It looked off the market when Espresso checked."
    return None


def _within(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def apply_links(html: bytes, base: str) -> list[dict]:
    """Links on the page that lead to an application, best first:
    `[{"url", "text", "site"}]`."""
    home = site_of(urlsplit(base).hostname)
    found: list[tuple[tuple[int, int], int, dict]] = []
    seen: set[str] = set()
    for n, (anchor, href, parts, site) in enumerate(anchors(html, base, limit=MAX_LINKS)):
        # The person's browser opens it: https, or the listing's own site as it is served.
        if not site or not (parts.scheme == "https" or (parts.scheme == "http" and site == home)):
            continue
        text = " ".join((anchor.get_text(" ", strip=True) or anchor.get("aria-label") or anchor.get("title") or "").split())[:80]
        if href in seen or _NOT_A_HOME.search(f"{text} {parts.path}"):
            continue
        by_text = bool(_APPLY_TEXT.search(_FINE_PRINT.sub(" ", text)))
        by_path = bool(_APPLY_PATH.search(parts.path))
        if not (by_text or by_path):
            continue
        seen.add(href)
        where = 0 if site == home else 1 if _within(site, PORTALS) else 2
        found.append(((0 if by_text else 1, where), n, {"url": href, "text": text, "site": site}))
    return [link for _, _, link in sorted(found, key=lambda f: (f[0], f[1]))]


async def _application(url: str, fetch) -> tuple[list[dict], int | None]:
    """(the page's application links, its HTTP status); ([], None) when it couldn't be read."""
    try:
        fetched = await fetch(url, max_bytes=PAGE_BYTES, accept="text/html,application/xhtml+xml",
                              total_timeout=PAGE_SECONDS)
    except (UnsafeURL, TimeoutError, OSError):
        return [], None
    except Exception:
        logger.info("apply: listing page fetch failed", exc_info=True)
        return [], None
    if fetched.status != 200 or "html" not in (fetched.content_type or ""):
        return [], fetched.status
    try:
        return await asyncio.to_thread(apply_links, fetched.body, fetched.final_url or url), 200
    except Exception:
        logger.info("apply: reading the listing page failed", exc_info=True)
        return [], 200


def _facts(item: dict) -> list[Line]:
    """What the person is applying to, as found."""
    fields = decode_jsonb(item.get("fields"), {}) or {}
    out = []
    for key, label in (("price", "Rent"), ("specials", "Specials"), ("address", "Address"), ("phone", "Leasing office")):
        entry = fields.get(key)
        if isinstance(entry, dict) and entry.get("display"):
            out.append(Line(label, str(entry["display"])))
    return out


async def prepare(ctx: ActionContext, params: dict, *, fetch=fetch_public) -> Proposal:
    url = page_of(ctx.item)
    if url is None:
        raise ActionError(available(ctx) or "There's no listing page to apply from.")
    title = ctx.item.get("title") or "this home"
    listed_at = site_of(urlsplit(url).hostname)
    links, status = await _application(url, fetch)
    if status in (404, 410):
        raise ActionError(f"{title}'s page is gone ({status}): it may be off the market.")
    lines = [Line("Home", title), *_facts(ctx.item)]
    never = "You fill it in and pay any application fee there; Espresso doesn't apply, pay or sign anything."
    if links:
        link = links[0]
        lines.append(Line("Application", link["site"]))
        return Proposal(
            frozen={"kind": "application", "url": link["url"], "title": title, "site": link["site"], "listing": url},
            title=f"Apply to {title}",
            lines=tuple(lines),
            note=f"Opens the application its page links to, at {link['site']}. {never}",
            confirm="Open the application",
        )
    lines.append(Line("Listed at", listed_at))
    return Proposal(
        frozen={"kind": "listing", "url": url, "title": title, "site": listed_at},
        title=f"Apply to {title}",
        lines=tuple(lines),
        note=f"Espresso didn't find an application link on its page, so this opens the listing at {listed_at}: "
             f"apply or contact the leasing office there. {never}",
        confirm=f"Open {listed_at}",
    )


async def perform(ctx: ActionContext, frozen: dict) -> dict:
    """Nothing to do on the server: the link is the hand-off."""
    site = frozen.get("site") or "the site"
    headline = f"Opened the application at {site}" if frozen.get("kind") == "application" else f"Opened the listing at {site}"
    return outcome(headline, (Line("Home", frozen.get("title") or ""),), url=frozen.get("url"))


ACTION = ItemAction(
    key="apply",
    label="Apply",
    icon="link",
    description="Opens the application the listing's page links to (or the listing, when it has none). "
                "You fill it in there; Espresso never applies, pays a fee or signs.",
    item_kinds=("listing",),
    confirm_label="Open the application",
    available=available,
    prepare=prepare,
    perform=perform,
    per_day=30,
)
