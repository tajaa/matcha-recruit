#!/usr/bin/env python3
"""Generate the hosted photos behind the Cappe site-template image slots.

Every image slot in `app/cappe/services/site_templates/imagery.py` is a KEY
with a prompt. Until this script has run for a key, the templates show the
self-hosted placeholder tile for it. This script fills the gap with the same
image model and S3/CloudFront storage the editor already uses for owners'
images (`core/services/image_gen.generate_image`), then records each URL in
`imagery_urls.json` beside the manifest — commit that file.

Usage (from `server/`, with the real `.env` so Gemini + S3 are reachable):

    ./venv/bin/python scripts/cappe_template_imagery.py --dry-run     # list what would run
    ./venv/bin/python scripts/cappe_template_imagery.py               # fill every empty key
    ./venv/bin/python scripts/cappe_template_imagery.py --only saveur-hero --force

Idempotent and resumable: keys that already have a URL are skipped unless
`--force`, and the JSON is rewritten after EVERY successful generation, so an
interrupted run keeps what it made. Nothing here touches the database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cappe.services.site_templates.imagery import (  # noqa: E402
    IMAGE_MANIFEST,
    PROMPT_SUFFIX,
)
from app.config import load_settings  # noqa: E402

URLS_FILE = pathlib.Path(__file__).resolve().parents[1] / "app/cappe/services/site_templates/imagery_urls.json"
STORAGE_PREFIX = "cappe/templates"
# Polite spacing between generations — this is a one-off catalogue fill, not a
# user waiting; a steady cadence keeps it well inside the image model's limits.
PAUSE_SECONDS = 2.0


def _load() -> dict[str, str]:
    if not URLS_FILE.exists():
        return {}
    data = json.loads(URLS_FILE.read_text())
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


def _save(urls: dict[str, str]) -> None:
    URLS_FILE.write_text(json.dumps(dict(sorted(urls.items())), indent=2) + "\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the plan, generate nothing")
    parser.add_argument("--only", action="append", default=[], metavar="KEY", help="limit to these manifest keys")
    parser.add_argument("--force", action="store_true", help="regenerate keys that already have a URL")
    args = parser.parse_args()

    unknown = [k for k in args.only if k not in IMAGE_MANIFEST]
    if unknown:
        print(f"ERROR: not in IMAGE_MANIFEST: {', '.join(unknown)}")
        return 2

    urls = _load()
    todo = [
        k for k in IMAGE_MANIFEST
        if (not args.only or k in args.only) and (args.force or not urls.get(k))
    ]
    print(f"{len(IMAGE_MANIFEST)} slots in the manifest, {len(urls)} already generated, {len(todo)} to do.")
    for k in todo:
        spec = IMAGE_MANIFEST[k]
        print(f"  {'[dry-run] ' if args.dry_run else ''}{k} ({spec.aspect}): {spec.prompt}")
    if args.dry_run or not todo:
        return 0

    load_settings()
    from app.core.services.image_gen import generate_image  # noqa: E402 — needs settings loaded

    failures = 0
    for i, k in enumerate(todo):
        spec = IMAGE_MANIFEST[k]
        try:
            url = await generate_image(spec.prompt + PROMPT_SUFFIX, prefix=STORAGE_PREFIX, aspect_ratio=spec.aspect)
        except Exception as exc:  # noqa: BLE001 — report and keep going; the JSON keeps what succeeded
            failures += 1
            print(f"  FAILED {k}: {exc}")
            continue
        if not isinstance(url, str) or not url.startswith("https://"):
            failures += 1
            print(f"  FAILED {k}: unexpected result {url!r}")
            continue
        urls[k] = url
        _save(urls)
        print(f"  ok {k} → {url}")
        if i < len(todo) - 1:
            await asyncio.sleep(PAUSE_SECONDS)

    print(f"\nDone. {len(todo) - failures} generated, {failures} failed. URLs in {URLS_FILE.relative_to(pathlib.Path.cwd())}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
