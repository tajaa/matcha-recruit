"""Seed a full demo BUSINESS site: Lumière Skincare Spa.

A skincare spa that books services online (with multiple estheticians) AND sells
skincare products — exercising every SMB surface end-to-end:
  - Phase A: products with categories + option groups (size) + price deltas
  - Phase B: staff/stylists, per-service staff mapping, per-staff availability
  - Phase C: structured hours + "open now", map/find-us, LocalBusiness SEO
  - plus the premium theme layer, reviews, a discount, and a multi-page site.

Idempotent: re-running wipes the demo account (cascades) and recreates it.

Run from server/ (dev tunnel up):  ./venv/bin/python scripts/seed_cappe_spa_demo.py
Add --prod to target PROD_DATABASE_URL instead (asks nothing — be sure).
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import time as dtime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_settings  # noqa: E402
from app.core.services.auth import hash_password  # noqa: E402
from app.database import close_pool, get_connection, init_pool  # noqa: E402

EMAIL = "lumiere@example.com"          # reserved domain → auto-verifies, safe
PASSWORD = "spademo123"
PIC = "https://picsum.photos/seed"

THEME = {
    "mode": "light", "preset": "editorial", "premium": True,
    "fonts": {"heading": "Fraunces", "body": "Inter"}, "radius": "md",
    "heroStyle": "image", "navStyle": "simple",
    "colors": {"bg": "#fdfbf7", "surface": "#f4efe7", "text": "#1f1a16", "muted": "#6f6357",
               "border": "#e7dccb", "brand": "#a8623f", "brandText": "#ffffff", "accent": "#a8623f"},
}

# Hours: open Tue(1)–Sat(5) 10–18; closed Sun(6) + Mon(0).
HOURS = [
    {"day": 0, "open": "", "close": "", "closed": True},
    {"day": 1, "open": "10:00", "close": "18:00", "closed": False},
    {"day": 2, "open": "10:00", "close": "18:00", "closed": False},
    {"day": 3, "open": "10:00", "close": "20:00", "closed": False},
    {"day": 4, "open": "10:00", "close": "20:00", "closed": False},
    {"day": 5, "open": "09:00", "close": "17:00", "closed": False},
    {"day": 6, "open": "", "close": "", "closed": True},
]

META = {
    "contact_email": "hello@lumiere.test",
    "contact_phone": "+1 415 555 0142",
    "contact_address": "742 Valencia St, San Francisco, CA 94110",
    "business_hours": "Tue–Sat, by appointment",
    "geo": {"lat": 37.7599, "lng": -122.4214},
    "hours": HOURS,
    "social": {"instagram": "https://instagram.com/lumiere.skin", "website": "https://lumiere.test"},
    "seo": {
        "title": "Lumière Skincare Spa — Facials, Massage & Clean Skincare",
        "description": "A boutique skincare spa in the Mission. Book a facial or massage with our "
                       "licensed estheticians, and shop our curated clean-ingredient skincare.",
        "og_image": f"{PIC}/lumiere-og/1200/630",
    },
}

# (name, bio, image-seed)
STAFF = [
    ("Maria Alvarez", "Lead esthetician · 10 yrs · acne & anti-aging", "maria-spa"),
    ("Priya Nair", "Esthetician & massage therapist · holistic facials", "priya-spa"),
    ("Jade Okafor", "Body treatments & microdermabrasion specialist", "jade-spa"),
]

# (name, desc, minutes, price_cents, category, buffer, staff-indexes who offer it)
SERVICES = [
    ("Signature Glow Facial", "Our most-loved 60-minute custom facial — cleanse, exfoliate, mask, massage.", 60, 12000, "Facials", 15, [0, 1]),
    ("Deep-Cleanse Acne Facial", "Targeted extractions + LED for congested skin.", 75, 14500, "Facials", 15, [0]),
    ("Hot Stone Massage", "90 minutes of warm basalt-stone relaxation.", 90, 16000, "Massage", 20, [1, 2]),
    ("Microdermabrasion", "Resurfacing treatment for texture + glow.", 45, 11000, "Body", 10, [2]),
]

# (name, desc, price_cents, inventory, category, image-seed, [(group, single, required, [(opt, delta_cents)])])
PRODUCTS = [
    ("Vitamin C Brightening Serum", "15% vitamin C + ferulic for radiance.", 6800, 40, "Serums", "lumiere-vitc",
     [("Size", True, True, [("30 ml", 0), ("50 ml", 2500)])]),
    ("Gentle Gel Cleanser", "Sulfate-free daily cleanser for all skin types.", 3200, 60, "Cleansers", "lumiere-cleanser", []),
    ("Hydra-Plump Moisturizer", "Hyaluronic + squalane day/night cream.", 5400, 50, "Moisturizers", "lumiere-moist",
     [("Size", True, True, [("50 ml", 0), ("100 ml", 2000)])]),
    ("Retinol Renewal Night Cream", "0.3% encapsulated retinol; smooths fine lines.", 7200, 35, "Moisturizers", "lumiere-retinol",
     [("Strength", True, True, [("0.3% (start here)", 0), ("0.5% (experienced)", 800)])]),
    ("The Glow Kit", "Cleanser + serum + moisturizer, gift-boxed.", 14000, 25, "Kits", "lumiere-kit", []),
]

REVIEWS = [
    ("Sofia R.", 5, "Best facial I've had in the city. Maria completely cleared up my skin over three visits."),
    ("Daniel K.", 5, "The hot stone massage with Priya is unreal. Booked my next one on the way out."),
    ("Amara T.", 4, "Lovely space, great products. The vitamin C serum is now a staple."),
]


def _blocks(home: bool):
    if home:
        return [
            {"type": "hero", "style": "image", "overlay": "dark", "align": "left",
             "eyebrow": "Boutique skincare · since 2016",
             "heading": "Skin that glows.",
             "subheading": "Custom facials, massage, and clean skincare in the heart of the Mission.",
             "cta": "Book a treatment", "ctaHref": "/p/book", "cta2": "Shop skincare", "cta2Href": "/p/shop",
             "image": f"{PIC}/lumiere-hero/1600/1000"},
            {"type": "features", "heading": "Why Lumière",
             "items": [
                 {"icon": "✦", "title": "Licensed estheticians", "body": "Every treatment is performed by a trained, licensed pro."},
                 {"icon": "◆", "title": "Clean ingredients", "body": "We use and sell skincare we actually believe in."},
                 {"icon": "▲", "title": "Personalized plans", "body": "A routine built around your skin, not a one-size mask."},
             ]},
            {"type": "stats", "items": [
                {"value": "2,000+", "label": "Facials given"}, {"value": "4.9★", "label": "Average rating"},
                {"value": "8 yrs", "label": "In the Mission"}]},
            {"type": "booking", "heading": "Book your treatment", "subheading": "Pick a service, choose your esthetician, and grab a time."},
            {"type": "store", "heading": "Shop skincare", "subheading": "Take the glow home."},
            {"type": "reviews", "heading": "Loved by our clients", "allowSubmissions": True},
            {"type": "hours", "heading": "Hours"},
            {"type": "map", "heading": "Find us"},
            {"type": "cta", "heading": "Ready for your best skin?", "subheading": "New clients get 10% off their first facial.",
             "cta": "Book now", "ctaHref": "/p/book"},
        ]
    return None


async def _wipe(conn):
    acct = await conn.fetchval("SELECT id FROM cappe_accounts WHERE lower(email) = $1", EMAIL)
    if acct:
        await conn.execute("DELETE FROM cappe_sites WHERE account_id = $1", acct)  # cascades children
        await conn.execute("DELETE FROM cappe_accounts WHERE id = $1", acct)


async def seed(conn):
    await _wipe(conn)

    acct_id = await conn.fetchval(
        """INSERT INTO cappe_accounts (email, password_hash, name, account_type, plan, status, email_verified_at)
           VALUES ($1, $2, $3, 'business', 'pro', 'active', NOW()) RETURNING id""",
        EMAIL, hash_password(PASSWORD), "Lumière Skincare Spa",
    )

    site_id = await conn.fetchval(
        """INSERT INTO cappe_sites (account_id, name, slug, subdomain, source_type, status,
                                    theme_config, meta_config, timezone, published_at)
           VALUES ($1, $2, $3, $3, 'blank', 'published', $4, $5, 'America/Los_Angeles', NOW()) RETURNING id""",
        acct_id, "Lumière Skincare Spa", "lumiere-spa", json.dumps(THEME), json.dumps(META),
    )

    # Staff
    staff_ids = []
    for i, (name, bio, seed) in enumerate(STAFF):
        sid = await conn.fetchval(
            """INSERT INTO cappe_staff (site_id, name, bio, image_url, active, sort_order)
               VALUES ($1, $2, $3, $4, true, $5) RETURNING id""",
            site_id, name, bio, f"{PIC}/{seed}/400/400", i,
        )
        staff_ids.append(sid)

    # Services (booking types) + staff mapping + per-staff availability
    for name, desc, mins, price, cat, buf, who in SERVICES:
        bt_id = await conn.fetchval(
            """INSERT INTO cappe_booking_types
                   (site_id, name, description, duration_minutes, price_cents, status,
                    requires_approval, pricing_mode, category, buffer_minutes)
               VALUES ($1, $2, $3, $4, $5, 'active', false, 'flat', $6, $7) RETURNING id""",
            site_id, name, desc, mins, price, cat, buf,
        )
        for idx in who:
            await conn.execute(
                "INSERT INTO cappe_staff_services (staff_id, booking_type_id, site_id) VALUES ($1, $2, $3)",
                staff_ids[idx], bt_id, site_id,
            )

    # Per-staff availability (Tue–Sat). Maria/Priya 10–18; Jade Wed–Sat 11–19.
    for idx, sid in enumerate(staff_ids):
        days = range(1, 6) if idx < 2 else range(2, 6)
        o, c = (dtime(10, 0), dtime(18, 0)) if idx < 2 else (dtime(11, 0), dtime(19, 0))
        for wd in days:
            await conn.execute(
                """INSERT INTO cappe_availability (site_id, weekday, start_time, end_time, booking_type_id, staff_id)
                   VALUES ($1, $2, $3, $4, NULL, $5)""",
                site_id, wd, o, c, sid,
            )

    # Products + option groups
    for i, (name, desc, price, inv, cat, seed, groups) in enumerate(PRODUCTS):
        p_id = await conn.fetchval(
            """INSERT INTO cappe_products
                   (site_id, name, description, price_cents, currency, image_url, sku, inventory,
                    status, sort_order, fulfillment, requires_approval, intake_fields, category)
               VALUES ($1, $2, $3, $4, 'USD', $5, $6, $7, 'active', $8, 'physical', false, '[]'::jsonb, $9) RETURNING id""",
            site_id, name, desc, price, f"{PIC}/{seed}/600/600", f"LUM-{i+1:03d}", inv, i, cat,
        )
        for gi, (gname, single, required, opts) in enumerate(groups):
            g_id = await conn.fetchval(
                """INSERT INTO cappe_product_option_groups (site_id, product_id, name, select_type, required, sort_order)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                site_id, p_id, gname, "single" if single else "multi", required, gi,
            )
            for oi, (oname, delta) in enumerate(opts):
                await conn.execute(
                    """INSERT INTO cappe_product_options (site_id, group_id, name, price_delta_cents, sort_order)
                       VALUES ($1, $2, $3, $4, $5)""",
                    site_id, g_id, oname, delta, oi,
                )

    # A standing new-client discount on facials (best-single, no stacking).
    await conn.execute(
        """INSERT INTO cappe_discounts (site_id, label, percent_off, scope, target_id, active)
           VALUES ($1, 'New-client facial special', 10, 'all', NULL, true)""",
        site_id,
    )

    # Approved reviews
    for author, rating, body in REVIEWS:
        await conn.execute(
            """INSERT INTO cappe_reviews (site_id, author_name, rating, body, status)
               VALUES ($1, $2, $3, $4, 'approved')""",
            site_id, author, rating, body,
        )

    # Pages
    pages = [("Home", "home", 0, _blocks(True)),
             ("Book", "book", 1, [{"type": "booking", "heading": "Book your treatment"}]),
             ("Shop", "shop", 2, [{"type": "store", "heading": "Shop skincare"}]),
             ("About", "about", 3, [
                 {"type": "text", "heading": "About Lumière", "body": "We're a small skincare studio in San Francisco's "
                  "Mission district. Since 2016 we've helped thousands of clients build skin they feel good in — with "
                  "honest advice, licensed estheticians, and products we'd use ourselves."},
                 {"type": "credentials", "heading": "Licensed & certified", "items": [
                     {"title": "Licensed Esthetician (CA)", "issuer": "CA Board of Barbering & Cosmetology", "year": "2016"},
                     {"title": "Certified in LED & Microneedling", "issuer": "Dermalogica", "year": "2021"}]},
                 {"type": "map", "heading": "Visit the studio"}])]
    for title, slug, order, blocks in pages:
        await conn.execute(
            """INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
               VALUES ($1, $2, $3, $4, $5, 'published')""",
            site_id, title, slug, json.dumps({"blocks": blocks}), order,
        )

    return acct_id, site_id


async def main(prod: bool):
    if prod:
        url = os.getenv("PROD_DATABASE_URL")
        if not url:
            print("PROD_DATABASE_URL not set"); return
        os.environ["DATABASE_URL"] = url
    settings = load_settings()
    await init_pool(settings.database_url, ssl_mode=settings.database_ssl)
    try:
        async with get_connection() as conn:
            acct_id, site_id = await seed(conn)
            staff = await conn.fetchval("SELECT count(*) FROM cappe_staff WHERE site_id=$1", site_id)
            svc = await conn.fetchval("SELECT count(*) FROM cappe_booking_types WHERE site_id=$1", site_id)
            prod_n = await conn.fetchval("SELECT count(*) FROM cappe_products WHERE site_id=$1", site_id)
            opts = await conn.fetchval("SELECT count(*) FROM cappe_product_options WHERE site_id=$1", site_id)
            avail = await conn.fetchval("SELECT count(*) FROM cappe_availability WHERE site_id=$1", site_id)
            host = settings.database_url.split("@")[-1]
    finally:
        await close_pool()

    print("\n=== Lumière Skincare Spa seeded ===")
    print(f"db            {host}")
    print(f"account_id    {acct_id}")
    print(f"site_id       {site_id}")
    print(f"login         {EMAIL}  /  {PASSWORD}")
    print(f"counts        {staff} staff · {svc} services · {prod_n} products ({opts} options) · {avail} availability windows")
    print("dashboard     /cappe/login → /cappe/sites")
    print("public dev    http://lumiere-spa.cappe.localhost:8001/   (or the published render route)")
    print("prod public   https://lumiere-spa.gummfit.com/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true", help="target PROD_DATABASE_URL")
    asyncio.run(main(ap.parse_args().prod))
