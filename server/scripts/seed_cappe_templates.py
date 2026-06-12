#!/usr/bin/env python3
"""Seed the Cappe template catalog (`cappe_templates`).

Cappe sites are created by cloning one of these templates: each `structure`
holds a theme plus an ordered list of pages, every page carrying a simple
block list that the editor/renderer consumes.

Usage:
    cd server
    python3 scripts/seed_cappe_templates.py
    python3 scripts/seed_cappe_templates.py --dry-run

Idempotent — upserts by slug, so re-running refreshes the catalog in place.

Prereq: alembic upgrade head  (cappe_templates must exist).
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.database import close_pool, get_connection, init_pool  # noqa: E402


def _hero(heading, subheading, cta="Get started"):
    return {"type": "hero", "heading": heading, "subheading": subheading, "cta": cta}


def _text(body):
    return {"type": "text", "body": body}


def _features(items):
    return {"type": "features", "items": items}


def _contact():
    return {"type": "contact", "heading": "Get in touch", "fields": ["name", "email", "message"]}


# slug -> template spec. Keep emails/domains out of seed copy.
TEMPLATES = {
    "personal-portfolio": {
        "name": "Personal Portfolio",
        "category": "portfolio",
        "description": "A clean one-pager to show your work, bio, and contact.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {"primaryColor": "#10b981", "font": "Inter", "mode": "light"},
            "pages": [
                {
                    "title": "Home",
                    "slug": "home",
                    "sort_order": 0,
                    "content": {
                        "blocks": [
                            _hero("Hi, I'm —", "Designer & maker. Welcome to my corner of the web.", "See my work"),
                            _features([
                                {"title": "Selected work", "body": "A few projects I'm proud of."},
                                {"title": "About", "body": "A short bio goes here."},
                                {"title": "Contact", "body": "Let's build something."},
                            ]),
                        ]
                    },
                },
                {
                    "title": "Work",
                    "slug": "work",
                    "sort_order": 1,
                    "content": {"blocks": [_text("Add your projects here — images, links, and short write-ups.")]},
                },
                {
                    "title": "Contact",
                    "slug": "contact",
                    "sort_order": 2,
                    "content": {"blocks": [_contact()]},
                },
            ],
        },
    },
    "business-landing": {
        "name": "Business Landing",
        "category": "business",
        "description": "A conversion-focused landing page for a product or service.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {"primaryColor": "#2563eb", "font": "Inter", "mode": "light"},
            "pages": [
                {
                    "title": "Home",
                    "slug": "home",
                    "sort_order": 0,
                    "content": {
                        "blocks": [
                            _hero("Your product, front and center", "Explain the value in one sentence.", "Start free"),
                            _features([
                                {"title": "Fast", "body": "Why it's quick."},
                                {"title": "Simple", "body": "Why it's easy."},
                                {"title": "Trusted", "body": "Why people rely on it."},
                            ]),
                            _text("Add testimonials, pricing, and an FAQ as you grow."),
                        ]
                    },
                },
                {
                    "title": "Pricing",
                    "slug": "pricing",
                    "sort_order": 1,
                    "content": {"blocks": [_text("List your plans and what each includes.")]},
                },
                {
                    "title": "Contact",
                    "slug": "contact",
                    "sort_order": 2,
                    "content": {"blocks": [_contact()]},
                },
            ],
        },
    },
    "restaurant": {
        "name": "Restaurant",
        "category": "food",
        "description": "Menu, hours, and location for a cafe or restaurant.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {"primaryColor": "#b45309", "font": "Playfair Display", "mode": "light"},
            "pages": [
                {
                    "title": "Home",
                    "slug": "home",
                    "sort_order": 0,
                    "content": {
                        "blocks": [
                            _hero("Welcome", "Fresh, local, made daily.", "View menu"),
                            _text("Hours: Mon–Sun. Add your address and a map here."),
                        ]
                    },
                },
                {
                    "title": "Menu",
                    "slug": "menu",
                    "sort_order": 1,
                    "content": {"blocks": [_text("List dishes, sections, and prices.")]},
                },
                {
                    "title": "Visit",
                    "slug": "visit",
                    "sort_order": 2,
                    "content": {"blocks": [_contact()]},
                },
            ],
        },
    },
    "blog": {
        "name": "Blog",
        "category": "blog",
        "description": "A simple writing-first blog with an about page.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {"primaryColor": "#7c3aed", "font": "Source Serif Pro", "mode": "light"},
            "pages": [
                {
                    "title": "Home",
                    "slug": "home",
                    "sort_order": 0,
                    "content": {"blocks": [_hero("Thoughts & writing", "New posts, occasionally.", "Read latest")]},
                },
                {
                    "title": "About",
                    "slug": "about",
                    "sort_order": 1,
                    "content": {"blocks": [_text("Who you are and what you write about.")]},
                },
            ],
        },
    },
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()

    settings = load_settings()
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    try:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='cappe_templates')"
            )
            if not exists:
                print("ERROR: cappe_templates does not exist — run `alembic upgrade head` first.")
                sys.exit(1)

            for slug, spec in TEMPLATES.items():
                if args.dry_run:
                    pages = spec["structure"]["pages"]
                    print(f"  [dry-run] {slug}: {spec['name']} ({len(pages)} pages)")
                    continue
                await conn.execute(
                    """INSERT INTO cappe_templates
                           (name, slug, category, description, preview_image_url,
                            structure, is_premium, price_cents, is_active)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true)
                       ON CONFLICT (slug) DO UPDATE SET
                           name = EXCLUDED.name,
                           category = EXCLUDED.category,
                           description = EXCLUDED.description,
                           preview_image_url = EXCLUDED.preview_image_url,
                           structure = EXCLUDED.structure,
                           is_premium = EXCLUDED.is_premium,
                           price_cents = EXCLUDED.price_cents,
                           is_active = true""",
                    spec["name"],
                    slug,
                    spec["category"],
                    spec["description"],
                    spec["preview_image_url"],
                    json.dumps(spec["structure"]),
                    spec["is_premium"],
                    spec["price_cents"],
                )
                print(f"  upserted {slug}: {spec['name']}")

        print(f"\nDone. {len(TEMPLATES)} templates {'previewed' if args.dry_run else 'seeded'}.")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
