"""professional — Praxis: a credible site for agencies, consultancies and firms."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

PRAXIS = SiteTemplate(
    slug="praxis-agency",
    name="Praxis — Agency & Consultancy",
    category="professional",
    description="A sharp, credible site for agencies, consultancies and professional firms — services, proof, process and a clear next step.",
    tags=("services", "faq", "contact"),
    sample_name="Praxis",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fafafa", "surface": "#eef0f6", "text": "#0f1324", "muted": "#5b6378",
            "border": "#dfe3ee", "brand": "#4338ca", "brandText": "#ffffff", "accent": "#6366f1",
        },
        "fonts": {"heading": "Sora", "body": "Inter"},
        "radius": "lg", "heroStyle": "split", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 106},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "split", "eyebrow": "Strategy & design",
             "heading": "We turn ambitious ideas into shipped work.",
             "subheading": f"{BUSINESS_NAME} is a senior team for brands that need strategy, design and delivery under one roof.",
             "cta": "Start a project", "ctaHref": "/p/contact", "cta2": "Our work", "cta2Href": "/p/work",
             **pic("image", "praxis-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900}}},
            {"type": "logos", "heading": "Partnered with", "items": [
                {"name": "Northwind"}, {"name": "Helio"}, {"name": "Cassette"}, {"name": "Field"}, {"name": "Pace"},
            ]},
            {"type": "stats", "items": [
                {"value": "60+", "label": "Projects delivered"},
                {"value": "Senior", "label": "Every person on the team"},
                {"value": "One roof", "label": "Strategy, design, build"},
            ]},
            {"type": "bento", "heading": "What we do", "items": [
                {"icon": "◆", "title": "Brand", "body": "Positioning, identity, and messaging that hold up.", "span": "wide"},
                {"icon": "▣", "title": "Product design", "body": "Interfaces people understand on the first try."},
                {"icon": "⚙", "title": "Delivery", "body": "Production-grade builds, not prototypes."},
                {"icon": "↗", "title": "Growth", "body": "Funnels and experiments that compound.", "span": "wide"},
            ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True, "hover": "lift"}}},
            {"type": "testimonial", "items": [
                {"quote": "They operated like our most senior in-house team — just faster.", "author": "Ana M.", "role": "CEO"},
                {"quote": "The clearest thinking we've hired. Worth every cent.", "author": "Tom B.", "role": "Founder"},
            ]},
            {"type": "faq", "heading": "How we work", "items": [
                {"q": "What does an engagement look like?", "a": "Most start with a paid discovery sprint, then a fixed-scope build. We'll scope yours on a call."},
                {"q": "How fast can you start?", "a": "Usually within a couple of weeks. Edit this with your real availability."},
                {"q": "Fixed fee or retainer?", "a": "Both — it depends on the work. We'll recommend what fits."},
            ]},
            {"type": "cta", "heading": "Let's build something.",
             "subheading": "Tell us the problem; we'll tell you how we'd solve it.",
             "cta": "Start a project", "ctaHref": "/p/contact"},
        ]),
        page("Work", "work", 1, [
            {"type": "hero", "style": "minimal", "heading": "Selected work",
             "subheading": "A few engagements we can talk about."},
            {"type": "bento", "items": [
                {"title": "Rebrand", "body": "Identity and site in six weeks", "image": img("praxis-work-1"), "span": "wide"},
                {"title": "Product", "image": img("praxis-work-2"), "span": "tall"},
                {"title": "Platform", "image": img("praxis-work-3")},
                {"title": "Growth", "image": img("praxis-work-4")},
            ]},
        ]),
        page("Contact", "contact", 2, [
            {"type": "contact", "heading": "Start a project",
             "subheading": "What you're building, your timeline, and your budget range.",
             "fields": ["name", "email", "message"]},
            {"type": "map", "heading": "Our office"},
        ]),
    ),
)

TEMPLATES = (PRAXIS,)
