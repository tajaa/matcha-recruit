#!/usr/bin/env python3
"""Capture bounded UI evidence with approved production test-tenant credentials.

The trusted harness owns credentials and the browser. The coding model receives
only a screenshot plus sanitized console/network status; cookies, tokens,
headers, response bodies, and credentials never cross into msandbox.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse


MAX_SIGNALS = 30


def write_result(path: Path, result: dict) -> None:
    path.write_text(json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")


def safe_base_url(raw: str) -> str | None:
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.hostname not in {"hey-matcha.com", "www.hey-matcha.com"}:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return f"https://{parsed.hostname}"


def safe_route(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    route = raw.strip()
    if (
        not route.startswith("/")
        or route.startswith("//")
        or "://" in route
        or ".." in route
        or "?" in route
        or "#" in route
        or any(char.isspace() for char in route)
        or len(route) > 500
    ):
        return None
    return route


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--screenshot", required=True)
    args = parser.parse_args()

    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    output = Path(args.output)
    screenshot = Path(args.screenshot)
    directives = policy.get("directives") or []
    route = safe_route(policy.get("test_route"))
    result = {
        "status": "not_requested",
        "route": route,
        "reason": "No force/retry directive requested an evidence replay.",
        "console_errors": [],
        "failed_requests": [],
        "http_errors": [],
        "screenshot_path": None,
    }
    if not ({"draft_pr", "trust_still_broken"} & set(directives)):
        write_result(output, result)
        return
    if route is None:
        result.update({
            "status": "needs_route",
            "reason": "No safe --test-route=/app/... was supplied; request the exact screen or a screenshot.",
        })
        write_result(output, result)
        return

    email = os.environ.get("AUTOPR_TEST_TENANT_EMAIL", "").strip()
    password = os.environ.get("AUTOPR_TEST_TENANT_PASSWORD", "")
    base_url = safe_base_url(os.environ.get("AUTOPR_TEST_TENANT_BASE_URL", "https://hey-matcha.com"))
    if not email or not password or base_url is None:
        result.update({
            "status": "not_configured",
            "reason": "Approved test-tenant credentials are unavailable to the trusted harness; request a screenshot.",
        })
        write_result(output, result)
        return

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        result.update({
            "status": "unavailable",
            "reason": "Playwright is not installed on the trusted runner; request a screenshot.",
        })
        write_result(output, result)
        return

    console_errors: list[str] = []
    failed_requests: list[dict] = []
    http_errors: list[dict] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                ignore_https_errors=False,
            )
            page = context.new_page()

            def on_console(message) -> None:
                if message.type == "error" and len(console_errors) < MAX_SIGNALS:
                    console_errors.append(message.text[:500])

            def on_request_failed(request) -> None:
                if len(failed_requests) >= MAX_SIGNALS:
                    return
                parsed = urlparse(request.url)
                if parsed.hostname in {"hey-matcha.com", "www.hey-matcha.com"}:
                    failed_requests.append({
                        "method": request.method,
                        "path": parsed.path[:500],
                        "failure": (request.failure or "request failed")[:300],
                    })

            def on_response(response) -> None:
                if response.status < 400 or len(http_errors) >= MAX_SIGNALS:
                    return
                parsed = urlparse(response.url)
                if parsed.hostname in {"hey-matcha.com", "www.hey-matcha.com"}:
                    http_errors.append({
                        "method": response.request.method,
                        "path": parsed.path[:500],
                        "status": response.status,
                    })

            page.on("console", on_console)
            page.on("requestfailed", on_request_failed)
            page.on("response", on_response)
            page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=30_000)
            page.locator("#email").fill(email)
            page.locator("#password").fill(password)
            page.locator('button[type="submit"]').click()
            try:
                page.wait_for_url(lambda url: urlparse(url).path != "/login", timeout=20_000)
            except PlaywrightTimeoutError:
                result.update({
                    "status": "login_failed",
                    "reason": "The approved test-tenant login did not leave the login screen; request a screenshot.",
                })
                browser.close()
                write_result(output, result)
                return

            page.goto(f"{base_url}{route}", wait_until="networkidle", timeout=30_000)
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            parsed_final = urlparse(page.url)
            result.update({
                "status": "captured",
                "reason": "The trusted browser replay completed with approved test-tenant credentials.",
                "final_path": parsed_final.path[:500],
                "page_title": page.title()[:300],
                "console_errors": console_errors,
                "failed_requests": failed_requests,
                "http_errors": http_errors,
                "screenshot_path": str(screenshot),
            })
            browser.close()
    except Exception as exc:
        result.update({
            "status": "unavailable",
            "reason": f"Trusted test-tenant replay failed ({type(exc).__name__}); request a screenshot.",
            "console_errors": console_errors,
            "failed_requests": failed_requests,
            "http_errors": http_errors,
        })
    write_result(output, result)


if __name__ == "__main__":
    main()
