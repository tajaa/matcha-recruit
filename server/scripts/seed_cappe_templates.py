#!/usr/bin/env python3
"""Seed the Cappe template catalog (`cappe_templates`).

Each template ships a distinct *design* (its own palette, font pairing, hero
style, radius, light/dark mode — see `theme`) plus rich page content built from
the renderer's block vocabulary (hero / features / gallery / pricing /
testimonial / cta / menu / posts / text / contact). Cloning a template copies
this whole structure into a new site, so two templates look genuinely different
out of the box.

Token shape is consumed by `app/cappe/services/render.py`.

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

PIC = "https://picsum.photos/seed"  # deterministic placeholder photos


def _page(title, slug, order, blocks, status="published"):
    return {"title": title, "slug": slug, "sort_order": order, "content": {"blocks": blocks}}


# ── templates ───────────────────────────────────────────────────────────────

TEMPLATES = {
    # 1) Personal portfolio — dark, lime accent, split hero, geometric sans.
    "personal-portfolio": {
        "name": "Atelier — Portfolio",
        "category": "portfolio",
        "description": "A bold dark portfolio for designers, photographers, and makers.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#0b0b0f", "surface": "#15151d", "text": "#fafafa", "muted": "#9ca3af",
                    "border": "#262630", "brand": "#a3e635", "brandText": "#0b0b0f", "accent": "#a3e635",
                },
                "fonts": {"heading": "Space Grotesk", "body": "Inter"},
                "radius": "2xl", "heroStyle": "split", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "eyebrow": "Designer & Maker", "heading": "I build things people love to use.",
                     "subheading": "Independent product designer working across brand, web, and interface.",
                     "cta": "View work", "ctaHref": "/p/work", "cta2": "Get in touch", "cta2Href": "/p/contact",
                     "image": f"{PIC}/folio-hero/900/700"},
                    {"type": "features", "heading": "What I do",
                     "items": [
                         {"icon": "✦", "title": "Brand", "body": "Identity systems that scale from logo to product."},
                         {"icon": "◆", "title": "Web", "body": "Fast, accessible marketing sites and storefronts."},
                         {"icon": "▲", "title": "Product", "body": "End-to-end interface design for apps and tools."},
                     ]},
                    {"type": "gallery", "heading": "Selected work",
                     "images": [
                         {"url": f"{PIC}/folio1/600/600", "caption": "Helio — branding"},
                         {"url": f"{PIC}/folio2/600/600", "caption": "Northwind — web"},
                         {"url": f"{PIC}/folio3/600/600", "caption": "Cassette — app"},
                         {"url": f"{PIC}/folio4/600/600", "caption": "Field — identity"},
                         {"url": f"{PIC}/folio5/600/600", "caption": "Pace — product"},
                         {"url": f"{PIC}/folio6/600/600", "caption": "Mono — type"},
                     ]},
                ]),
                _page("Work", "work", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Work",
                     "subheading": "A selection of recent projects. Replace these with your own."},
                    {"type": "gallery",
                     "images": [
                         {"url": f"{PIC}/work1/800/800", "caption": "Project one"},
                         {"url": f"{PIC}/work2/800/800", "caption": "Project two"},
                         {"url": f"{PIC}/work3/800/800", "caption": "Project three"},
                     ]},
                ]),
                _page("Contact", "contact", 2, [
                    {"type": "contact", "heading": "Let's work together",
                     "subheading": "Tell me about your project and timeline.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 2) SaaS / business landing — light indigo, centered hero, conversion stack.
    "business-landing": {
        "name": "Launch — SaaS Landing",
        "category": "business",
        "description": "A conversion-focused landing page with features, pricing, and testimonials.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#0b1020", "surface": "#131a2e", "text": "#f1f5f9", "muted": "#94a3b8",
                    "border": "#1f2a44", "brand": "#6366f1", "brandText": "#ffffff", "accent": "#818cf8",
                },
                "fonts": {"heading": "Poppins", "body": "Inter"},
                "radius": "xl", "heroStyle": "centered", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "eyebrow": "New · v2.0 is here",
                     "heading": "Ship your product faster.",
                     "subheading": "Everything your team needs to plan, build, and launch — in one place.",
                     "cta": "Start free", "ctaHref": "/p/pricing", "cta2": "Book a demo", "cta2Href": "/p/contact"},
                    {"type": "features", "heading": "Built for momentum",
                     "subheading": "Powerful on its own, better together.",
                     "items": [
                         {"icon": "⚡", "title": "Fast", "body": "Realtime sync keeps everyone on the same page."},
                         {"icon": "🔒", "title": "Secure", "body": "SOC 2, SSO, and granular permissions."},
                         {"icon": "🔌", "title": "Connected", "body": "Integrations for the tools you already use."},
                     ]},
                    {"type": "testimonial",
                     "items": [
                         {"quote": "We cut our launch cycle in half within a month.", "author": "Jordan Lee", "role": "Head of Product"},
                         {"quote": "The one tool the whole team actually agrees on.", "author": "Sam Rivera", "role": "Engineering Lead"},
                     ]},
                    {"type": "pricing", "heading": "Simple pricing",
                     "plans": [
                         {"name": "Starter", "price": "$0", "period": "/mo", "cta": "Get started",
                          "features": ["Up to 3 projects", "Community support", "1 GB storage"]},
                         {"name": "Pro", "price": "$24", "period": "/mo", "highlighted": True, "cta": "Start free trial",
                          "features": ["Unlimited projects", "Priority support", "100 GB storage", "Advanced analytics"]},
                         {"name": "Team", "price": "$99", "period": "/mo", "cta": "Contact sales",
                          "features": ["Everything in Pro", "SSO + SAML", "Dedicated manager", "SLA"]},
                     ]},
                    {"type": "cta", "heading": "Ready to get started?",
                     "subheading": "Spin up your workspace in under a minute.",
                     "cta": "Start free", "ctaHref": "/p/pricing"},
                ]),
                _page("Pricing", "pricing", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Pricing",
                     "subheading": "Start free. Upgrade when you're ready."},
                    {"type": "pricing",
                     "plans": [
                         {"name": "Starter", "price": "$0", "period": "/mo", "cta": "Get started",
                          "features": ["Up to 3 projects", "Community support", "1 GB storage"]},
                         {"name": "Pro", "price": "$24", "period": "/mo", "highlighted": True, "cta": "Start trial",
                          "features": ["Unlimited projects", "Priority support", "100 GB storage", "Analytics"]},
                         {"name": "Team", "price": "$99", "period": "/mo", "cta": "Contact sales",
                          "features": ["Everything in Pro", "SSO + SAML", "Dedicated manager", "SLA"]},
                     ]},
                ]),
                _page("Contact", "contact", 2, [
                    {"type": "contact", "heading": "Talk to us",
                     "subheading": "Questions about plans or a demo? Send a note.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 3) Restaurant — warm cream, serif, full-bleed image hero, menu.
    "restaurant": {
        "name": "Saveur — Restaurant",
        "category": "food",
        "description": "An elegant page for a cafe or restaurant — menu, gallery, and hours.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#16100c", "surface": "#1f1813", "text": "#f5ece0", "muted": "#b9a892",
                    "border": "#322619", "brand": "#e0992f", "brandText": "#16100c", "accent": "#f59e0b",
                },
                "fonts": {"heading": "Playfair Display", "body": "Lora"},
                "radius": "md", "heroStyle": "image", "navStyle": "centered",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "image", "eyebrow": "Est. 2014",
                     "heading": "Fresh, local, made daily.",
                     "subheading": "A neighborhood kitchen serving seasonal plates and natural wine.",
                     "cta": "View menu", "ctaHref": "/p/menu",
                     "image": f"{PIC}/resto-hero/1600/900"},
                    {"type": "menu", "heading": "On the menu",
                     "sections": [
                         {"name": "Small plates", "items": [
                             {"name": "Burrata & peach", "description": "Stone fruit, basil, aged balsamic.", "price": "14"},
                             {"name": "Charred octopus", "description": "Salsa verde, fingerling potato.", "price": "18"},
                         ]},
                         {"name": "Mains", "items": [
                             {"name": "Wood-fired branzino", "description": "Fennel, citrus, olive.", "price": "29"},
                             {"name": "Tagliatelle", "description": "Brown butter, sage, parmesan.", "price": "24"},
                         ]},
                     ]},
                    {"type": "gallery",
                     "images": [
                         {"url": f"{PIC}/resto1/600/600"},
                         {"url": f"{PIC}/resto2/600/600"},
                         {"url": f"{PIC}/resto3/600/600"},
                     ]},
                ]),
                _page("Menu", "menu", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Menu",
                     "subheading": "Seasonal — changes with what's good."},
                    {"type": "menu",
                     "sections": [
                         {"name": "Starters", "items": [
                             {"name": "Market salad", "description": "Greens, herbs, lemon.", "price": "11"},
                             {"name": "Bread & cultured butter", "price": "6"},
                         ]},
                         {"name": "Plates", "items": [
                             {"name": "Roast chicken", "description": "For two, with jus.", "price": "38"},
                             {"name": "Mushroom risotto", "price": "22"},
                         ]},
                         {"name": "Dessert", "items": [
                             {"name": "Olive oil cake", "price": "9"},
                             {"name": "Affogato", "price": "7"},
                         ]},
                     ]},
                ]),
                _page("Visit", "visit", 2, [
                    {"type": "text", "heading": "Visit us",
                     "body": ["Open Tuesday–Sunday, 5pm–late.", "Walk-ins welcome; reservations for parties of six or more.", "Add your address and a map embed here."]},
                    {"type": "contact", "heading": "Reservations",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 4) Blog — minimal editorial, serif, generous whitespace, post list.
    "blog": {
        "name": "Margin — Blog",
        "category": "blog",
        "description": "A reading-first blog with elegant typography and a clean post list.",
        "preview_image_url": None,
        "is_premium": False,
        "price_cents": 0,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#0c0a09", "surface": "#171513", "text": "#f5f5f4", "muted": "#a8a29e",
                    "border": "#292524", "brand": "#f87171", "brandText": "#0c0a09", "accent": "#f87171",
                },
                "fonts": {"heading": "Fraunces", "body": "Source Serif 4"},
                "radius": "sm", "heroStyle": "minimal", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "minimal", "eyebrow": "Notes",
                     "heading": "Thoughts & writing.",
                     "subheading": "Occasional essays on design, craft, and the things in between."},
                    {"type": "posts", "items": [
                        {"date": "June 2026", "title": "On keeping a smaller surface area",
                         "excerpt": "Why I stopped adding features and started removing them — and what that did to the work."},
                        {"date": "May 2026", "title": "The case for slow tools",
                         "excerpt": "Fast software optimizes for the demo. Slow software optimizes for the decade."},
                        {"date": "April 2026", "title": "Notes from a quiet quarter",
                         "excerpt": "Three months offline, and what came back changed."},
                    ]},
                ]),
                _page("About", "about", 1, [
                    {"type": "hero", "style": "minimal", "heading": "About",
                     "subheading": "A sentence about who you are."},
                    {"type": "text",
                     "body": ["I write about making things — the craft, the doubt, the parts nobody puts in the case study.",
                              "Replace this with your own story. Tell readers what you write about and why they should subscribe."]},
                ]),
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
