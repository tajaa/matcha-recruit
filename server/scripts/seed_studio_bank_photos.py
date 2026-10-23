"""Fill Gummfit Studio's photo bank (`cappe_studio_bank`, cappemag11) with
free stock photos, so every site's Photos tab opens on a library of its own.

The photos are CC0, from StockSnap.io, the WordPress Photo Directory and
Nappy, found through Openverse (`sources/stock.py`). CC0 lets us keep and
re-offer them (Unsplash's and Pexels' licences don't); each is still credited
to its creator and source. Each one is downloaded through the SSRF-guarded
fetcher, re-encoded with its sizes and no metadata (`media.process_image`),
stored under `cappe/bank/`, and added as a bank photo in its topic's
collection. Re-runs skip what the bank already has (by the photo's page).

Every site's Studio opens on this library, and Openverse's mature filter
doesn't flag these collections (a "people" search brought sensual photos), so
each photo is shown to Claude first (the Studio's model, surface
`gummfit.studio`, Haiku by default) and only one any business could publish
is kept. A photo that can't be checked isn't kept either; `--no-screen` turns
the check off (only for a library someone reviews by hand at /admin/cappe).

Anonymous Openverse allows 20 searches a minute and 200 a day; the script
waits between searches and uses a page of 20 at a time (searches are cached a
day, so a re-run doesn't spend them again).

    cd server
    venv/bin/python scripts/seed_studio_bank_photos.py --dry-run
    venv/bin/python scripts/seed_studio_bank_photos.py --per-topic 40
    venv/bin/python scripts/seed_studio_bank_photos.py --topics Coffee,City --per-topic 10

Point it at an environment with DATABASE_URL and the S3 settings in the env
(or server/.env): it uploads to that environment's bucket. Run `--dry-run`
first.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402

# Collection → what to search for. Interleaved by rank when stored, so the
# Photos tab's "All" opens on a mix.
TOPICS: dict[str, str] = {
    "Coffee": "coffee", "Food": "food", "City": "city street", "Nature": "nature landscape",
    "Beach": "beach ocean", "People": "people", "Portraits": "portrait", "Work": "office work",
    "Home": "home interior", "Travel": "travel", "Fashion": "fashion", "Fitness": "fitness",
    "Flowers": "flowers", "Animals": "animals", "Night": "night city lights", "Textures": "texture background",
}
PER_TOPIC = 40
MIN_SIDE = 1600
SEARCH_GAP = 3.5  # seconds between Openverse searches (20 a minute, anonymously)
TRIES = 3  # a slow Openverse search is tried again, then its topic is left for a re-run
SEEDER = "seed:stock-photos"
PREVIEW_SIDE = 768  # what Claude is shown
SCREEN = (
    "You check photos for Gummfit, which offers them as free stock photos to every customer's website and "
    "magazine. Reply with JSON only: {\"ok\": true or false, \"reason\": \"a few words\"}. ok only for a photo any "
    "business could publish: no nudity or partial nudity, no underwear, nothing sexual or suggestive; no violence, "
    "blood, weapons, drugs or hate symbols; no watermark, no large text, not a screenshot, no brand logo as the "
    "subject; sharp and well exposed. People in everyday clothes, food, places, nature and things are fine."
)


def pick(results: Iterable, taken: set[str], want: int, min_side: int = MIN_SIDE) -> list:
    """The results worth keeping, in order: big enough, each photo once
    (`taken` holds the pages already in the bank or picked; it grows)."""
    out = []
    for r in results:
        if len(out) >= want:
            break
        page = r.landing_url or r.image_url
        if not page or page in taken:
            continue
        if not (r.width and r.height) or max(r.width, r.height) < min_side:
            continue
        taken.add(page)
        out.append(r)
    return out


async def search(query: str, page: int) -> tuple[list, bool] | None:
    """A page of free photos, or None when Openverse didn't answer in time."""
    from app.cappe.services.magazine import sources

    for attempt in range(TRIES):
        try:
            return await sources.search_page("stock", query, page)
        except sources.SourceError as exc:
            then = "trying again" if attempt + 1 < TRIES else "skipping it"
            print(f"    Openverse didn't answer for “{query}” ({exc}); {then}")
            await asyncio.sleep(SEARCH_GAP * 3)
    return None


def preview(data: bytes) -> bytes:
    """The photo as a small JPEG, to show Claude."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
    return out.getvalue()


async def suitable(model: str, data: bytes) -> tuple[bool, str]:
    """Whether any business could publish this photo, and why not. A photo
    that couldn't be checked is not suitable."""
    from app.core.services import anthropic_messages

    try:
        reply = await anthropic_messages.generate_text(
            "Check this photo.", model=model, system=SCREEN,
            attachments=[anthropic_messages.image_block(preview(data), "image/jpeg")],
            json_output=True, effort="low", max_tokens=200, timeout_seconds=60, deadline=60,
        )
        verdict = anthropic_messages.parse_json_object(reply)
    except (RuntimeError, ValueError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        return False, f"couldn't be checked ({type(exc).__name__})"
    return verdict.get("ok") is True, str(verdict.get("reason") or "")[:120]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "photo"


async def store(conn, r, collection: str, query: str, rank: int, model: str | None) -> dict | None:
    """Download, check (with `model`; None: no check), re-encode and add one
    photo; None when it couldn't be, or shouldn't."""
    from app.cappe.services import media
    from app.cappe.services.magazine import imports
    from app.cappe.services.magazine.sources.base import IMAGE_ACCEPT
    from app.cappe.services.magazine.studio import bank
    from app.core.services.safe_fetch import fetch_public

    try:
        got = await fetch_public(r.image_url, max_bytes=imports.MAX_IMAGE_BYTES, accept=IMAGE_ACCEPT,
                                 total_timeout=imports.DOWNLOAD_SECONDS)
    except Exception as exc:  # noqa: BLE001 — unsafe host, network: skip this one
        print(f"    skip {r.landing_url}: {type(exc).__name__}")
        return None
    mime = got.content_type.split(";")[0].strip().lower().replace("image/jpg", "image/jpeg")
    if got.status != 200 or got.truncated or mime not in ("image/jpeg", "image/png", "image/webp"):
        print(f"    skip {r.landing_url}: HTTP {got.status} {mime}")
        return None
    if model:
        ok, why = await suitable(model, got.body)
        if not ok:
            print(f"    leave out {r.landing_url}: {why}")
            return None
    try:
        image = await asyncio.to_thread(media.process_image, got.body, mime, derivatives=True)
    except media.ImageRejected as exc:
        print(f"    skip {r.landing_url}: {exc}")
        return None
    stored = await media.store_processed(image, prefix="cappe/bank", filename=f"{slug(collection)}.jpg")
    item = await bank.add_photo(
        conn, url=stored.url, variants=stored.variants, width=stored.width, height=stored.height,
        size_bytes=stored.bytes, mime=stored.mime, name=bank.clean_name(r.title) or collection,
        tags=bank.clean_tags([*r.tags, *query.split(), collection]), collection=collection,
        creator=r.creator or None, credit_line=r.credit_line, license=r.license,
        source_url=r.landing_url or None, email=SEEDER, sort_order=rank,
    )
    return item


async def main(topics: list[str], per_topic: int, min_side: int, dry_run: bool, screen: bool) -> int:
    settings = load_settings()
    from app.cappe.services.magazine import sources
    from app.core.services import agent_surfaces, anthropic_messages
    from app.database import close_pool, get_connection, init_pool

    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    added = skipped = 0
    try:
        model = await anthropic_messages.claude_default(agent_surfaces.GUMMFIT_STUDIO) if screen else None
        if screen and not model:
            print("No Claude model is configured here, so photos can't be checked. Set ANTHROPIC_API_KEY, "
                  "or pass --no-screen and review the library by hand.")
            return 1
        async with get_connection() as conn:
            taken = {r["source_url"] for r in await conn.fetch(
                "SELECT source_url FROM cappe_studio_bank WHERE kind = 'photo' AND source_url IS NOT NULL")}
            for collection in topics:
                query = TOPICS[collection]
                chosen: list = []
                page = 0
                while len(chosen) < per_topic and page < sources.MAX_PAGE:
                    found = await search(query, page)
                    if found is None:
                        break
                    results, more = found
                    chosen += pick(results, taken, per_topic - len(chosen), min_side)
                    page += 1
                    if not more:
                        break
                    await asyncio.sleep(SEARCH_GAP)
                print(f"{collection}: {len(chosen)} photos for “{query}”")
                for rank, r in enumerate(chosen):
                    if dry_run:
                        print(f"    would add {r.title!r} — {r.credit_line} ({r.width}×{r.height})")
                        continue
                    if await store(conn, r, collection, query, rank, model):
                        added += 1
                    else:
                        skipped += 1
                await asyncio.sleep(SEARCH_GAP)
    finally:
        await close_pool()
    print("dry run: nothing downloaded or added" if dry_run else f"added {added} photos, skipped {skipped}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", default=",".join(TOPICS), help="collections to fill (comma-separated)")
    ap.add_argument("--per-topic", type=int, default=PER_TOPIC)
    ap.add_argument("--min-side", type=int, default=MIN_SIDE, help="smallest long side kept, in pixels")
    ap.add_argument("--dry-run", action="store_true", help="say what would be added; download nothing")
    ap.add_argument("--no-screen", action="store_true", help="keep photos without showing them to Claude first")
    args = ap.parse_args()
    names = [t.strip() for t in args.topics.split(",") if t.strip()]
    unknown = [t for t in names if t not in TOPICS]
    if unknown:
        sys.exit(f"unknown topics: {', '.join(unknown)} (known: {', '.join(TOPICS)})")
    sys.exit(asyncio.run(main(names, max(1, args.per_topic), args.min_side, args.dry_run, not args.no_screen)))
