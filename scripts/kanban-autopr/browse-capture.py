#!/usr/bin/env python3
"""Open one page in the sandbox's own Chromium, screenshot it, print its text.

Runs INSIDE msandbox, called by the model during a research run on a board
granted the `browse` capability. It is deliberately a fixed-shape tool rather
than "the model may drive Playwright": everything it can do is bounded here, so
the trusted bridge only has to police the artifacts that come back rather than
reason about arbitrary browser automation.

What it refuses, and why:

* Anything but http(s). `file://` would read the clone, and the whole point of
  the sandbox is that what the model can reach is enumerable.
* Loopback, link-local, and private address literals. The container can reach
  the host's dev stack on host.docker.internal; a research run has no business
  there, and a redirect into it is the classic way an "outside" fetch turns
  into an internal one. Redirects are re-checked after the fact for the same
  reason.
* More than a bounded number of captures per run, and any single image over a
  size cap. The publisher uploads these to a real ticket.

Exit codes: 0 captured · 2 refused (bad URL, cap reached) · 3 no browser
installed · 4 navigation failed. 3 is distinct because it is an operator
condition (the image was built without browsers), not a research failure — the
prompt tells the model to say so and carry on with web search alone.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_CAPTURES = 12
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
VIEWPORT = {"width": 1280, "height": 900}
NAV_TIMEOUT_MS = 30_000
_LABEL_RE = re.compile(r"[^a-z0-9-]+")


def fail(code: int, message: str) -> None:
    print(f"browse-capture: {message}", file=sys.stderr)
    raise SystemExit(code)


def safe_label(raw: str) -> str:
    label = _LABEL_RE.sub("-", (raw or "").strip().lower()).strip("-")
    return (label or "capture")[:60]


def host_is_internal(hostname: str) -> bool:
    """True when the name resolves anywhere we refuse to browse.

    Every resolved address is checked, not just the first: a name that returns
    one public and one loopback address is exactly the shape this is for.
    """
    if not hostname:
        return True
    if hostname.lower().endswith((".localhost", ".internal", ".local")):
        return True
    if hostname.lower() in {"localhost", "host.docker.internal"}:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable is not internal; let navigation fail with a real error.
        return False
    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            return True
    return False


def check_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        fail(2, f"only http(s) URLs may be opened (got {parsed.scheme or 'no scheme'})")
    if parsed.username or parsed.password:
        fail(2, "credentials in a URL are refused")
    if host_is_internal(parsed.hostname or ""):
        fail(2, f"refusing an internal address: {parsed.hostname}")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--label", required=True, help="Short name for the screenshot file")
    parser.add_argument(
        "--output-dir",
        default="/workspace/.git/autopr-io/output/artifacts",
        help="Where the trusted bridge collects artifacts from",
    )
    parser.add_argument("--full-page", action="store_true", help="Capture past the fold")
    args = parser.parse_args()

    url = check_url(args.url)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(p for p in out_dir.glob("*.png"))
    if len(existing) >= MAX_CAPTURES:
        fail(2, f"capture cap reached ({MAX_CAPTURES}); summarize what you already have")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail(3, "Playwright is not installed in this sandbox; use web search instead")

    destination = out_dir / f"{len(existing) + 1:02d}-{safe_label(args.label)}.png"

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                fail(3, f"no Chromium in this sandbox ({exc}); use web search instead")
            context = browser.new_context(viewport=VIEWPORT)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(1500)
                # A redirect can land somewhere the pre-flight check would have
                # refused, so the destination is checked again before anything
                # about it is written down.
                final = urlparse(page.url)
                if final.scheme not in ("http", "https") or host_is_internal(final.hostname or ""):
                    fail(2, f"refusing a redirect to an internal address: {page.url}")
                page.screenshot(path=str(destination), full_page=args.full_page)
                title = page.title()
                text = page.inner_text("body")
            finally:
                context.close()
                browser.close()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - the model needs the reason
        destination.unlink(missing_ok=True)
        fail(4, f"could not open {url}: {exc}")

    size = destination.stat().st_size
    if size > MAX_IMAGE_BYTES:
        destination.unlink(missing_ok=True)
        fail(2, f"screenshot is {size} bytes (max {MAX_IMAGE_BYTES}); try without --full-page")

    print(f"saved: {destination.name}  ({size} bytes)")
    print(f"final url: {url}")
    print(f"title: {title}")
    print("--- page text ---")
    print(text[:MAX_TEXT_CHARS])
    if len(text) > MAX_TEXT_CHARS:
        print(f"\n… text truncated at {MAX_TEXT_CHARS} characters")


if __name__ == "__main__":
    main()
