#!/usr/bin/env python3
"""Create (or refresh) a published Cappe test tenant + site for local subdomain testing.

Makes a cappe_account, a PUBLISHED site whose subdomain = its slug, a few sample
pages, and one sample product — then prints how to view it on localhost.

Usage:
    cd server
    python3 scripts/cappe_make_test_tenant.py --subdomain demo
    python3 scripts/cappe_make_test_tenant.py --subdomain acme --email owner@example.com --password testpass123

Idempotent — re-running refreshes the same site (matched by slug).
Prereq: migrations zzzzcappe01 + zzzzcappe02 applied.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.core.services.auth import hash_password  # noqa: E402
from app.database import close_pool, get_connection, init_pool  # noqa: E402
from app.cappe.routes._shared import slugify  # noqa: E402

PAGES = [
    ("Home", "home", 0, {"blocks": [
        {"type": "hero", "heading": "Welcome to {name}", "subheading": "This site is served from its subdomain by Cappe.", "cta": "Get started"},
        {"type": "features", "items": [
            {"title": "Fast", "body": "Rendered server-side at the subdomain."},
            {"title": "Simple", "body": "Edit pages in the Cappe dashboard."},
            {"title": "Yours", "body": "Bring your own domain later."},
        ]},
        {"type": "text", "body": "This is a sample home page. Replace these blocks in the editor."},
    ]}),
    ("About", "about", 1, {"blocks": [
        {"type": "text", "body": "About {name}. A short bio or company description goes here."},
    ]}),
    ("Contact", "contact", 2, {"blocks": [
        {"type": "contact", "heading": "Get in touch", "fields": ["name", "email", "message"]},
    ]}),
]


def _fill(blocks_json: dict, name: str) -> str:
    raw = json.dumps(blocks_json)
    return raw.replace("{name}", name)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subdomain", default="demo", help="Site slug + subdomain")
    parser.add_argument("--name", default=None, help="Site display name")
    parser.add_argument("--email", default="owner@example.com")
    parser.add_argument("--password", default="testpass123")
    args = parser.parse_args()

    slug = slugify(args.subdomain)
    site_name = args.name or slug.replace("-", " ").title()
    email = args.email.strip().lower()

    settings = load_settings()
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    try:
        async with get_connection() as conn:
            account_id = await conn.fetchval(
                """INSERT INTO cappe_accounts (email, password_hash, name, status)
                   VALUES ($1, $2, $3, 'active')
                   ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
                   RETURNING id""",
                email, hash_password(args.password), "Test Owner",
            )

            site_id = await conn.fetchval(
                """INSERT INTO cappe_sites (account_id, name, slug, subdomain, source_type, status, published_at)
                   VALUES ($1, $2, $3, $3, 'blank', 'published', NOW())
                   ON CONFLICT (slug) DO UPDATE
                       SET account_id = EXCLUDED.account_id, name = EXCLUDED.name,
                           subdomain = EXCLUDED.subdomain, status = 'published',
                           published_at = NOW(), updated_at = NOW()
                   RETURNING id""",
                account_id, site_name, slug,
            )

            await conn.execute("DELETE FROM cappe_pages WHERE site_id = $1", site_id)
            for title, pslug, order, blocks in PAGES:
                await conn.execute(
                    """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                       VALUES ($1, $2, $3, $4, $5, 'published')""",
                    site_id, title, pslug, _fill(blocks, site_name), order,
                )

            has_product = await conn.fetchval("SELECT 1 FROM cappe_products WHERE site_id = $1 LIMIT 1", site_id)
            if not has_product:
                await conn.execute(
                    """INSERT INTO cappe_products (site_id, name, description, price_cents, status, inventory)
                       VALUES ($1, 'Sample tee', 'A demo product.', 1500, 'active', 25)""",
                    site_id,
                )

        port = os.getenv("CAPPE_TEST_PORT", "8001")
        print("\n✅ Test tenant ready.\n")
        print(f"  Account:   {email}  /  {args.password}   (sign in at the Cappe dashboard, /cappe/login)")
        print(f"  Site:      {site_name}   slug/subdomain = {slug}   (published)\n")
        print("View the rendered site on localhost:")
        print(f"  • Browser:  http://{slug}.localhost:{port}/        (*.localhost resolves to 127.0.0.1)")
        print(f"  • Browser:  http://{slug}.cappe.localhost:{port}/")
        print(f"  • curl:     curl -H 'Host: {slug}.cappe.localhost' http://localhost:{port}/")
        print(f"  • Sub-page: curl -H 'Host: {slug}.cappe.localhost' http://localhost:{port}/p/about")
        print("\nPublic JSON API (by slug):")
        print(f"  • curl http://localhost:{port}/api/cappe/public/sites/{slug}")
        print(f"  • curl http://localhost:{port}/api/cappe/public/sites/{slug}/products\n")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
