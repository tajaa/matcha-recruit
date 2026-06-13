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

    # ── PREMIUM ─────────────────────────────────────────────────────────────
    # 5) Coach / personal brand — warm editorial, Fraunces serif, split + faq.
    "lumen-coach": {
        "name": "Lumen — Coach & Creator",
        "category": "personal",
        "description": "A warm, editorial personal-brand site for coaches, consultants, and creators.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 2900,
        "structure": {
            "theme": {
                "mode": "light",
                "colors": {
                    "bg": "#fdfbf7", "surface": "#f3eee4", "text": "#1c1a17", "muted": "#6b5f50",
                    "border": "#e6ddcd", "brand": "#b4532a", "brandText": "#ffffff", "accent": "#d97706",
                },
                "fonts": {"heading": "Fraunces", "body": "Inter"},
                "radius": "md", "heroStyle": "split", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "split", "eyebrow": "1:1 Coaching",
                     "heading": "Become the version of you that's been waiting.",
                     "subheading": "Personal coaching for people who are done waiting for permission. Clear goals, real accountability, steady progress.",
                     "cta": "Work with me", "ctaHref": "/p/contact", "cta2": "My approach", "cta2Href": "/p/about",
                     "image": f"{PIC}/lumen-hero/1000/800"},
                    {"type": "stats", "items": [
                        {"value": "12 yrs", "label": "Coaching experience"},
                        {"value": "600+", "label": "Clients guided"},
                        {"value": "4.9★", "label": "Average rating"},
                    ]},
                    {"type": "split", "reverse": True, "eyebrow": "How it works",
                     "heading": "A method, not a motivational poster.",
                     "body": "We start with where you actually are, name the goal that matters, and build a plan you'll keep. Then we do the unglamorous part — showing up, every week.",
                     "bullets": ["Weekly 1:1 sessions", "A plan tailored to your goals", "Accountability that actually sticks", "Tools you keep after we're done"],
                     "cta": "See pricing", "ctaHref": "/p/work", "image": f"{PIC}/lumen-method/900/700"},
                    {"type": "testimonial", "heading": "In their words", "items": [
                        {"quote": "Six months with Lumen did what three years of self-help books couldn't.", "author": "Maya T.", "role": "Founder"},
                        {"quote": "I finally have a system instead of a guilt complex.", "author": "Devin R.", "role": "Product Manager"},
                    ]},
                    {"type": "faq", "heading": "Questions, answered", "items": [
                        {"q": "Who is this for?", "a": "Anyone navigating a transition — a new role, a new business, or a season where the old playbook stopped working."},
                        {"q": "How long is a typical engagement?", "a": "Most clients work with me for three to six months. We reassess every month so you're never locked into something that isn't working."},
                        {"q": "Do you offer a trial?", "a": "Yes — a free 30-minute intro call so we can both decide it's a fit before anything else."},
                        {"q": "Is this in person or remote?", "a": "Remote by default, with optional in-person intensives. Replace this answer with your own setup."},
                    ]},
                    {"type": "cta", "heading": "Ready to start?",
                     "subheading": "Book a free intro call and we'll map your first 90 days.",
                     "cta": "Book a free call", "ctaHref": "/p/contact"},
                ]),
                _page("About", "about", 1, [
                    {"type": "hero", "style": "minimal", "eyebrow": "About",
                     "heading": "Hi, I'm your coach.",
                     "subheading": "A sentence about who you help and the change you create."},
                    {"type": "split", "eyebrow": "My story",
                     "heading": "Why I do this work.",
                     "body": "Replace this with your background — what you've done, what you learned the hard way, and why you decided to help others do it faster.",
                     "bullets": ["Certified & trained", "Years in the field", "A point of view you can trust"],
                     "image": f"{PIC}/lumen-about/900/700"},
                ]),
                _page("Pricing", "work", 2, [
                    {"type": "hero", "style": "minimal", "heading": "Ways to work together",
                     "subheading": "Pick the depth that fits where you are."},
                    {"type": "pricing", "plans": [
                        {"name": "Intro", "price": "$0", "period": "/call", "cta": "Book", "ctaHref": "/p/contact",
                         "features": ["30-minute intro call", "Honest fit assessment", "A first next step"]},
                        {"name": "Monthly", "price": "$450", "period": "/mo", "highlighted": True, "cta": "Start", "ctaHref": "/p/contact",
                         "features": ["Weekly 1:1 sessions", "Async support between calls", "Your tailored plan", "Cancel anytime"]},
                        {"name": "Intensive", "price": "$1,800", "period": "", "cta": "Enquire", "ctaHref": "/p/contact",
                         "features": ["Full-day deep dive", "90-day roadmap", "Two follow-up sessions"]},
                    ]},
                ]),
                _page("Contact", "contact", 3, [
                    {"type": "contact", "heading": "Let's talk",
                     "subheading": "Tell me a little about where you are and what you want to change.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 6) Photography portfolio — dark, Playfair, gold, bento gallery + logos.
    "onyx-photo": {
        "name": "Onyx — Photography",
        "category": "portfolio",
        "description": "A cinematic dark portfolio for photographers and visual studios.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 2900,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#111014", "surface": "#1c1a22", "text": "#f7f5f0", "muted": "#a89f93",
                    "border": "#2c2933", "brand": "#d4af37", "brandText": "#111014", "accent": "#d4af37",
                },
                "fonts": {"heading": "Playfair Display", "body": "Inter"},
                "radius": "md", "heroStyle": "image", "navStyle": "centered",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "image", "eyebrow": "Photography",
                     "heading": "Light, held still.",
                     "subheading": "Editorial, portrait, and brand photography for people who care how it looks.",
                     "cta": "View portfolio", "ctaHref": "/p/work", "image": f"{PIC}/onyx-hero/1600/1000"},
                    {"type": "bento", "heading": "Selected frames", "items": [
                        {"title": "Editorial", "body": "Magazine & brand stories", "image": f"{PIC}/onyx1/900/700", "span": "wide"},
                        {"title": "Portrait", "image": f"{PIC}/onyx2/700/900", "span": "tall"},
                        {"title": "Product", "image": f"{PIC}/onyx3/700/500"},
                        {"title": "Travel", "image": f"{PIC}/onyx4/700/500"},
                        {"title": "Events", "image": f"{PIC}/onyx5/900/600", "span": "wide"},
                    ]},
                    {"type": "logos", "heading": "Seen in", "items": [
                        {"name": "VOGUE"}, {"name": "Kinfolk"}, {"name": "Monocle"}, {"name": "Aperture"},
                    ]},
                    {"type": "testimonial", "items": [
                        {"quote": "Onyx made our whole team look like the brand we wished we were.", "author": "Lena K.", "role": "Creative Director"},
                    ]},
                    {"type": "cta", "heading": "Have a shoot in mind?",
                     "subheading": "Tell me the vision — I'll bring the light.",
                     "cta": "Start a project", "ctaHref": "/p/contact"},
                ]),
                _page("Work", "work", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Portfolio",
                     "subheading": "A selection of recent work. Swap in your own frames."},
                    {"type": "gallery", "images": [
                        {"url": f"{PIC}/onyxw1/800/800"}, {"url": f"{PIC}/onyxw2/800/800"},
                        {"url": f"{PIC}/onyxw3/800/800"}, {"url": f"{PIC}/onyxw4/800/800"},
                        {"url": f"{PIC}/onyxw5/800/800"}, {"url": f"{PIC}/onyxw6/800/800"},
                    ]},
                ]),
                _page("Contact", "contact", 2, [
                    {"type": "contact", "heading": "Book a shoot",
                     "subheading": "Dates, location, and what you're imagining.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 7) Fitness studio — bold, Sora, electric; stats + booking widget.
    "verve-fitness": {
        "name": "Verve — Fitness Studio",
        "category": "fitness",
        "description": "A high-energy studio site with class booking, memberships, and social proof.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 3900,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#0a0f0d", "surface": "#121a17", "text": "#f0fdf4", "muted": "#86a394",
                    "border": "#1d2a23", "brand": "#22c55e", "brandText": "#062012", "accent": "#a3e635",
                },
                "fonts": {"heading": "Sora", "body": "Inter"},
                "radius": "xl", "heroStyle": "centered", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "centered", "eyebrow": "Move better",
                     "heading": "Stronger every session.",
                     "subheading": "Small-group strength, mobility, and conditioning — coached, not crowded.",
                     "cta": "Book a class", "ctaHref": "/p/book", "cta2": "See memberships", "cta2Href": "/p/pricing"},
                    {"type": "stats", "items": [
                        {"value": "6:1", "label": "Member-to-coach ratio"},
                        {"value": "40+", "label": "Classes a week"},
                        {"value": "1,200", "label": "Strong members"},
                    ]},
                    {"type": "split", "reverse": True, "eyebrow": "Why Verve",
                     "heading": "Coaching that actually watches your form.",
                     "body": "No mirror-lined warehouse with one trainer for forty people. Small groups, real attention, and a plan that progresses with you.",
                     "bullets": ["Programmed progressions", "Form-first coaching", "All levels welcome"],
                     "cta": "Book your first class", "ctaHref": "/p/book", "image": f"{PIC}/verve-coach/900/700"},
                    {"type": "faq", "heading": "Before your first class", "items": [
                        {"q": "I'm a total beginner — is that okay?", "a": "Perfect, actually. Every movement scales, and your coach adjusts on the spot."},
                        {"q": "What should I bring?", "a": "Water, training shoes, and yourself. We've got the rest."},
                        {"q": "Can I freeze my membership?", "a": "Yes — pause anytime. Edit this answer with your own policy."},
                    ]},
                    {"type": "cta", "heading": "First class is on us.",
                     "subheading": "Grab a spot and come see what coached training feels like.",
                     "cta": "Book free class", "ctaHref": "/p/book"},
                ]),
                _page("Memberships", "pricing", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Memberships",
                     "subheading": "No contracts. Cancel whenever."},
                    {"type": "pricing", "plans": [
                        {"name": "Drop-in", "price": "$28", "period": "/class", "cta": "Book", "ctaHref": "/p/book",
                         "features": ["One class", "No commitment", "Gear included"]},
                        {"name": "Unlimited", "price": "$179", "period": "/mo", "highlighted": True, "cta": "Join", "ctaHref": "/p/book",
                         "features": ["Unlimited classes", "Free assessment", "App & tracking", "Bring-a-friend passes"]},
                        {"name": "Coached", "price": "$320", "period": "/mo", "cta": "Enquire", "ctaHref": "/p/book",
                         "features": ["Everything in Unlimited", "Monthly 1:1", "Custom programming"]},
                    ]},
                ]),
                _page("Book", "book", 2, [
                    {"type": "hero", "style": "minimal", "heading": "Book a class",
                     "subheading": "Pick a time that works — spots are limited on purpose."},
                    {"type": "booking", "heading": "Reserve your spot",
                     "subheading": "Choose a class and we'll see you on the floor."},
                ]),
            ],
        },
    },

    # 8) Fine dining — Studio dark, Playfair, gold; split chef story + menu.
    "maison-dining": {
        "name": "Maison — Fine Dining",
        "category": "food",
        "description": "A refined restaurant site with chef story, menu, and reservations.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 3900,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#141210", "surface": "#1e1a16", "text": "#f6efe6", "muted": "#bdae9c",
                    "border": "#2e2820", "brand": "#c9a24b", "brandText": "#141210", "accent": "#e0b85e",
                },
                "fonts": {"heading": "Playfair Display", "body": "Lora"},
                "radius": "sm", "heroStyle": "image", "navStyle": "centered",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "image", "eyebrow": "Est. 2009 · Tasting menu",
                     "heading": "A table worth the evening.",
                     "subheading": "Seasonal tasting menus and a cellar built over fifteen years.",
                     "cta": "Reserve", "ctaHref": "/p/reserve", "image": f"{PIC}/maison-hero/1600/1000"},
                    {"type": "split", "eyebrow": "The kitchen",
                     "heading": "Cooked by hand, plated with intent.",
                     "body": "Our chef builds each menu around what the farms send that week. Nothing frozen, nothing rushed — just the best of the season, served the way it should be.",
                     "bullets": ["Seasonal tasting menu", "Natural & classic wine pairings", "Counted covers each night"],
                     "image": f"{PIC}/maison-chef/900/700"},
                    {"type": "menu", "heading": "This week's menu",
                     "sections": [
                        {"name": "To begin", "items": [
                            {"name": "Oyster, cucumber, dill", "description": "Daily catch, mignonette.", "price": "—"},
                            {"name": "Heirloom tomato", "description": "Stracciatella, basil oil.", "price": "—"},
                        ]},
                        {"name": "Mains", "items": [
                            {"name": "Dry-aged duck", "description": "Cherry, turnip, jus.", "price": "—"},
                            {"name": "Line-caught turbot", "description": "Brown butter, capers.", "price": "—"},
                        ]},
                        {"name": "To finish", "items": [
                            {"name": "Dark chocolate, olive oil", "price": "—"},
                            {"name": "Selection of cheese", "price": "—"},
                        ]},
                     ]},
                    {"type": "faq", "heading": "Good to know", "items": [
                        {"q": "Do you accommodate dietary needs?", "a": "Yes — note them when you reserve and the kitchen will adapt the menu."},
                        {"q": "Is there a dress code?", "a": "Smart casual. Replace with your own policy."},
                        {"q": "Large parties?", "a": "We seat private parties of up to twelve. Enquire below."},
                    ]},
                    {"type": "cta", "heading": "Reserve your evening.",
                     "subheading": "Tables open thirty days out.",
                     "cta": "Request a table", "ctaHref": "/p/reserve"},
                ]),
                _page("Reservations", "reserve", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Reservations",
                     "subheading": "Send your details and we'll confirm by email."},
                    {"type": "contact", "heading": "Request a table",
                     "subheading": "Date, time, party size, and any dietary notes.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 9) Agency / consultancy — clean Sora, deep indigo; logos + bento services.
    "praxis-agency": {
        "name": "Praxis — Agency",
        "category": "business",
        "description": "A sharp, credible site for agencies and consultancies — services, proof, and process.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 4900,
        "structure": {
            "theme": {
                "mode": "dark",
                "colors": {
                    "bg": "#0b1020", "surface": "#131a2e", "text": "#f1f5f9", "muted": "#94a3b8",
                    "border": "#1f2a44", "brand": "#6366f1", "brandText": "#ffffff", "accent": "#818cf8",
                },
                "fonts": {"heading": "Sora", "body": "Inter"},
                "radius": "lg", "heroStyle": "split", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "split", "eyebrow": "Strategy & Design",
                     "heading": "We turn ambitious ideas into shipped work.",
                     "subheading": "A senior team for brands that need strategy, design, and engineering under one roof.",
                     "cta": "Start a project", "ctaHref": "/p/contact", "cta2": "Our work", "cta2Href": "/p/work",
                     "image": f"{PIC}/praxis-hero/1000/800"},
                    {"type": "logos", "heading": "Partnered with", "items": [
                        {"name": "Northwind"}, {"name": "Helio"}, {"name": "Cassette"}, {"name": "Field"}, {"name": "Pace"},
                    ]},
                    {"type": "stats", "items": [
                        {"value": "60+", "label": "Products shipped"},
                        {"value": "$200M", "label": "Raised by clients"},
                        {"value": "9 yrs", "label": "Average team tenure"},
                    ]},
                    {"type": "bento", "heading": "What we do", "items": [
                        {"icon": "◆", "title": "Brand", "body": "Positioning, identity, and messaging that hold up.", "span": "wide"},
                        {"icon": "▣", "title": "Product design", "body": "Interfaces people understand on the first try."},
                        {"icon": "⚙", "title": "Engineering", "body": "Production-grade builds, not prototypes."},
                        {"icon": "↗", "title": "Growth", "body": "Funnels and experiments that compound.", "span": "wide"},
                    ]},
                    {"type": "testimonial", "items": [
                        {"quote": "Praxis operated like our most senior in-house team — just faster.", "author": "Ana M.", "role": "CEO, Northwind"},
                        {"quote": "The clearest thinking we've hired. Worth every cent.", "author": "Tom B.", "role": "Founder, Helio"},
                    ]},
                    {"type": "faq", "heading": "How we work", "items": [
                        {"q": "What does an engagement look like?", "a": "Most start with a paid discovery sprint, then a fixed-scope build. We'll scope yours on a call."},
                        {"q": "How fast can you start?", "a": "Usually within two weeks. Edit this with your real availability."},
                        {"q": "Do you work fixed-fee or retainer?", "a": "Both — depends on the work. We'll recommend what fits."},
                    ]},
                    {"type": "cta", "heading": "Let's build something.",
                     "subheading": "Tell us the problem; we'll tell you how we'd solve it.",
                     "cta": "Start a project", "ctaHref": "/p/contact"},
                ]),
                _page("Work", "work", 1, [
                    {"type": "hero", "style": "minimal", "heading": "Selected work",
                     "subheading": "A few engagements we can talk about."},
                    {"type": "bento", "items": [
                        {"title": "Northwind — rebrand", "body": "Identity + site in 6 weeks", "image": f"{PIC}/praxisw1/900/700", "span": "wide"},
                        {"title": "Helio — product", "image": f"{PIC}/praxisw2/700/900", "span": "tall"},
                        {"title": "Cassette — app", "image": f"{PIC}/praxisw3/700/500"},
                        {"title": "Pace — growth", "image": f"{PIC}/praxisw4/700/500"},
                    ]},
                ]),
                _page("Contact", "contact", 2, [
                    {"type": "contact", "heading": "Start a project",
                     "subheading": "What you're building, your timeline, and your budget range.",
                     "fields": ["name", "email", "message"]},
                ]),
            ],
        },
    },

    # 10) Creator store — Sunset coral, Sora; storefront + split + newsletter.
    "bloom-store": {
        "name": "Bloom — Creator Store",
        "category": "store",
        "description": "A friendly storefront for creators selling products, downloads, and sessions.",
        "preview_image_url": None,
        "is_premium": True,
        "price_cents": 2900,
        "structure": {
            "theme": {
                "mode": "light",
                "colors": {
                    "bg": "#fff8f3", "surface": "#ffeee3", "text": "#2a1d18", "muted": "#7a6258",
                    "border": "#f6ddcd", "brand": "#f0603a", "brandText": "#ffffff", "accent": "#fb923c",
                },
                "fonts": {"heading": "Sora", "body": "Inter"},
                "radius": "2xl", "heroStyle": "centered", "navStyle": "simple",
            },
            "pages": [
                _page("Home", "home", 0, [
                    {"type": "hero", "style": "centered", "eyebrow": "The shop is open",
                     "heading": "Things I made, for you.",
                     "subheading": "Prints, downloads, and the occasional 1:1 — all in one little shop.",
                     "cta": "Shop now", "ctaHref": "#shop", "cta2": "Say hi", "cta2Href": "/p/about"},
                    {"type": "features", "heading": "Why shop here", "items": [
                        {"icon": "✦", "title": "Made by me", "body": "Every item is designed and made by hand."},
                        {"icon": "⚡", "title": "Instant downloads", "body": "Digital goods land in your inbox right away."},
                        {"icon": "♡", "title": "Support a maker", "body": "Your order goes straight to an independent creator."},
                    ]},
                    {"type": "store", "heading": "Shop", "subheading": "Pick something you love."},
                    {"type": "split", "reverse": True, "eyebrow": "About",
                     "heading": "Hi, I'm the maker behind Bloom.",
                     "body": "Replace this with your story — what you make, why you started, and what makes your work yours.",
                     "bullets": ["Independent & handmade", "Shipped with care", "Made in small batches"],
                     "image": f"{PIC}/bloom-maker/900/700"},
                    {"type": "testimonial", "items": [
                        {"quote": "Beautiful work, beautifully packaged. Already ordered twice.", "author": "Priya N.", "role": "Repeat customer"},
                    ]},
                    {"type": "newsletter", "heading": "Get first dibs",
                     "subheading": "New drops and the occasional discount — no spam, ever."},
                ]),
                _page("About", "about", 1, [
                    {"type": "hero", "style": "minimal", "heading": "About Bloom",
                     "subheading": "The maker, the method, the mission."},
                    {"type": "text", "body": [
                        "Tell people who you are and why your work exists.",
                        "A second paragraph for the details that make customers trust you — your process, materials, or guarantee."]},
                    {"type": "contact", "heading": "Questions?",
                     "fields": ["name", "email", "message"]},
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
