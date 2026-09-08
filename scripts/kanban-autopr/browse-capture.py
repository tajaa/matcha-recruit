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
  into an internal one.

  Resolving the name here and letting Chromium resolve it again is not enough
  on its own — between the two lookups a short-TTL record can change answers,
  and the page is then already loaded by the time anything is re-checked. So
  the address this process validated is PINNED into Chromium
  (--host-resolver-rules), and every request the page makes, redirects and
  sub-resources included, is refused at the routing layer before it is issued
  rather than examined afterwards.
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


def address_is_internal(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed.is_unspecified
    )


def resolve_public_address(hostname: str) -> str | None:
    """The address to pin for this name, or None when it may not be browsed.

    Every resolved address is checked, not just the first: a name that returns
    one public and one loopback address is exactly the shape this is for. The
    address returned is the one Chromium is then pinned to, so the process that
    made the decision and the process that opens the socket cannot disagree.
    """
    if not hostname:
        return None
    lowered = hostname.lower()
    if lowered.endswith((".localhost", ".internal", ".local")):
        return None
    if lowered in {"localhost", "host.docker.internal"}:
        return None
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable is not internal; let navigation fail with a real error.
        return "unresolved"
    chosen = None
    for info in infos:
        address = info[4][0]
        if address_is_internal(address):
            return None
        if chosen is None:
            chosen = address
    return chosen


def host_is_internal(hostname: str) -> bool:
    """True when the name may not be browsed. Kept as the predicate the
    per-request guard uses, so one rule covers the page and its sub-resources."""
    return resolve_public_address(hostname) is None


def check_url(raw: str) -> tuple[str, str, str | None]:
    """Returns (url, hostname, pinned address). Refuses anything unbrowsable."""
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        fail(2, f"only http(s) URLs may be opened (got {parsed.scheme or 'no scheme'})")
    if parsed.username or parsed.password:
        fail(2, "credentials in a URL are refused")
    hostname = parsed.hostname or ""
    address = resolve_public_address(hostname)
    if address is None:
        fail(2, f"refusing an internal address: {hostname}")
    return raw, hostname, (None if address == "unresolved" else address)


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

    url, hostname, pinned_address = check_url(args.url)
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

    # Chromium resolves names itself, so without this it could reach an address
    # this process never saw and never approved. Pinning the validated one
    # closes the window between the two lookups for the page's own host.
    launch_args = []
    if pinned_address:
        # Chromium's MAP rule wants an IPv6 literal bracketed.
        literal = f"[{pinned_address}]" if ":" in pinned_address else pinned_address
        launch_args.append(f"--host-resolver-rules=MAP {hostname} {literal}")

    # One decision per host, so a page with fifty assets on one CDN costs one
    # lookup. Refusals are recorded rather than raised: aborting a sub-resource
    # is normal operation, and the run should still produce its screenshot.
    host_verdicts: dict[str, bool] = {hostname.lower(): False}
    refused_hosts: set[str] = set()

    def guard(route) -> None:
        target = urlparse(route.request.url)
        host = (target.hostname or "").lower()
        if target.scheme not in ("http", "https"):
            refused_hosts.add(host or target.scheme)
            route.abort()
            return
        if host not in host_verdicts:
            host_verdicts[host] = host_is_internal(host)
        if host_verdicts[host]:
            refused_hosts.add(host)
            route.abort()
            return
        route.continue_()

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True, args=launch_args)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                fail(3, f"no Chromium in this sandbox ({exc}); use web search instead")
            context = browser.new_context(viewport=VIEWPORT)
            page = context.new_page()
            # Every request the page makes passes through here BEFORE it is
            # issued — the document, each redirect hop, and every sub-resource.
            # This is the check that matters; the post-navigation one below is
            # a backstop, and by then the bytes have already arrived.
            page.route("**/*", guard)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(1500)
                final_url = page.url
                final = urlparse(final_url)
                if final.scheme not in ("http", "https") or host_is_internal(final.hostname or ""):
                    fail(2, f"refusing a redirect to an internal address: {final_url}")
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
    # page.url, not the argument: a 302 means the page you are looking at is
    # not the one you asked for, and this line is what the model cites as its
    # source. Printing the request URL made every redirected capture cite the
    # address it did not screenshot.
    print(f"final url: {final_url}")
    if refused_hosts:
        print(f"refused (internal): {', '.join(sorted(h for h in refused_hosts if h))}")
    print(f"title: {title}")
    print("--- page text ---")
    print(text[:MAX_TEXT_CHARS])
    if len(text) > MAX_TEXT_CHARS:
        print(f"\n… text truncated at {MAX_TEXT_CHARS} characters")


if __name__ == "__main__":
    main()
