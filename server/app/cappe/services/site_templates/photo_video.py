"""photo-video — Onyx: a cinematic dark portfolio for photographers and visual studios."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

ONYX = SiteTemplate(
    slug="onyx-photo",
    name="Onyx — Photography",
    category="photo-video",
    description="A cinematic dark portfolio for photographers, filmmakers and visual studios — bento highlights, gallery, press and booking enquiries.",
    tags=("portfolio", "gallery", "contact"),
    sample_name="Onyx",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#111014", "surface": "#1c1a22", "text": "#f7f5f0", "muted": "#a89f93",
            "border": "#2c2933", "brand": "#d4af37", "brandText": "#111014", "accent": "#d4af37",
        },
        "fonts": {"heading": "Playfair Display", "body": "Inter"},
        "radius": "md", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 112, "heroAnim": "rise"},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Photography & film",
             "heading": "Light, held still.",
             "subheading": f"Editorial, portrait and brand photography by {BUSINESS_NAME} — for people who care how it looks.",
             "cta": "View portfolio", "ctaHref": "/p/work", "cta2": "Book a shoot", "cta2Href": "/p/contact",
             **pic("image", "onyx-hero"),
             "_design": {"motion": {"effect": "fade-up", "easing": "gentle", "duration": 1100, "kenburns": True},
                         "layout": {"minHeight": "screen"}}},
            {"type": "bento", "heading": "Selected frames", "items": [
                {"title": "Editorial", "body": "Magazine & brand stories", "image": img("onyx-bento-1"), "span": "wide"},
                {"title": "Portrait", "image": img("onyx-bento-2"), "span": "tall"},
                {"title": "Product", "image": img("onyx-bento-3")},
                {"title": "Travel", "image": img("onyx-bento-4")},
                {"title": "Events", "image": img("onyx-bento-5"), "span": "wide"},
            ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True, "hover": "lift"}}},
            {"type": "logos", "heading": "Seen in", "items": [
                {"name": "Your press"}, {"name": "Features"}, {"name": "Publications"}, {"name": "Awards"},
            ]},
            {"type": "testimonial", "items": [
                {"quote": "They made our whole team look like the brand we wished we were.", "author": "Lena K.", "role": "Creative director"},
            ]},
            {"type": "cta", "heading": "Have a shoot in mind?",
             "subheading": "Tell me the vision — I'll bring the light.",
             "cta": "Start a project", "ctaHref": "/p/contact"},
        ]),
        page("Work", "work", 1, [
            {"type": "hero", "style": "minimal", "heading": "Portfolio",
             "subheading": "A selection of recent work. Swap in your own frames."},
            {"type": "gallery", "images": [
                {"url": img("onyx-work-1")}, {"url": img("onyx-work-2")},
                {"url": img("onyx-work-3")}, {"url": img("onyx-work-4")},
                {"url": img("onyx-work-5")}, {"url": img("onyx-work-6")},
            ]},
        ]),
        page("Contact", "contact", 2, [
            {"type": "contact", "heading": "Book a shoot",
             "subheading": "Dates, location, and what you're imagining.",
             "fields": ["name", "email", "message"]},
            {"type": "faq", "heading": "Working together", "items": [
                {"q": "How far ahead should I book?", "a": "Replace with your typical lead time."},
                {"q": "Do you travel?", "a": "Describe where you shoot and how travel is billed."},
                {"q": "When do I get the photos?", "a": "Set expectations for proofs and final delivery."},
            ]},
        ]),
    ),
)

TEMPLATES = (ONYX,)
