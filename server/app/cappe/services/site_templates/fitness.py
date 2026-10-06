"""fitness — Verve: a high-energy studio site with memberships and class booking."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

VERVE = SiteTemplate(
    slug="verve-fitness",
    name="Verve — Fitness Studio",
    category="fitness",
    description="A high-energy site for gyms, studios and trainers — memberships, class booking, FAQ and social proof.",
    tags=("booking", "pricing", "faq", "hours"),
    sample_name="Verve",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#0a0f0d", "surface": "#121a17", "text": "#f0fdf4", "muted": "#86a394",
            "border": "#1d2a23", "brand": "#22c55e", "brandText": "#062012", "accent": "#a3e635",
        },
        "fonts": {"heading": "Sora", "body": "Inter"},
        "radius": "xl", "heroStyle": "centered", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 112, "headingWeight": 700},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "centered", "eyebrow": "Move better",
             "heading": "Stronger every session.",
             "subheading": f"Small-group strength, mobility and conditioning at {BUSINESS_NAME} — coached, not crowded.",
             "cta": "Book a class", "ctaHref": "/p/book", "cta2": "See memberships", "cta2Href": "/p/pricing",
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "snappy", "duration": 700},
                         "layout": {"minHeight": "tall"}}},
            {"type": "stats", "items": [
                {"value": "6:1", "label": "Member-to-coach ratio"},
                {"value": "40+", "label": "Classes a week"},
                {"value": "All levels", "label": "Every movement scales"},
            ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "split", "reverse": True, "eyebrow": "Why us",
             "heading": "Coaching that actually watches your form.",
             "body": "No mirror-lined warehouse with one trainer for forty people. Small groups, real attention, and a plan that progresses with you.",
             "bullets": ["Programmed progressions", "Form-first coaching", "All levels welcome"],
             "cta": "Book your first class", "ctaHref": "/p/book",
             **pic("image", "verve-coach")},
            {"type": "reviews", "heading": "Member stories",
             "subheading": "What people say after their first month."},
            {"type": "faq", "heading": "Before your first class", "items": [
                {"q": "I'm a total beginner — is that okay?", "a": "Perfect, actually. Every movement scales, and your coach adjusts on the spot."},
                {"q": "What should I bring?", "a": "Water, training shoes, and yourself. We've got the rest."},
                {"q": "Can I freeze my membership?", "a": "Yes — pause anytime. Edit this answer with your own policy."},
            ]},
            {"type": "cta", "heading": "First class is on us.",
             "subheading": "Grab a spot and come see what coached training feels like.",
             "cta": "Book a free class", "ctaHref": "/p/book"},
        ]),
        page("Memberships", "pricing", 1, [
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
        page("Book", "book", 2, [
            {"type": "hero", "style": "minimal", "heading": "Book a class",
             "subheading": "Pick a time that works — spots are limited on purpose."},
            {"type": "booking", "heading": "Reserve your spot",
             "subheading": "Choose a class and we'll see you on the floor."},
            {"type": "hours", "heading": "Studio hours"},
            {"type": "map", "heading": "Find the studio"},
        ]),
    ),
)

TEMPLATES = (VERVE,)
