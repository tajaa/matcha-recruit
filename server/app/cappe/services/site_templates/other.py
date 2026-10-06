"""other — Margin: a reading-first blog / personal site."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page

MARGIN = SiteTemplate(
    slug="margin-blog",
    name="Margin — Blog & Notes",
    category="other",
    description="A reading-first blog with elegant typography, a clean post list and a newsletter — for writers and personal sites.",
    tags=("blog", "newsletter", "personal"),
    sample_name="Margin",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fbf8f3", "surface": "#f1ebe1", "text": "#1f1b17", "muted": "#6f655a",
            "border": "#e5dccd", "brand": "#b4532a", "brandText": "#ffffff", "accent": "#b4532a",
        },
        "fonts": {"heading": "Fraunces", "body": "Lora"},
        "radius": "sm", "heroStyle": "minimal", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 106},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "minimal", "eyebrow": "Notes",
             "heading": "Thoughts & writing.",
             "subheading": f"Occasional essays from {BUSINESS_NAME} on craft, work and the things in between.",
             "_design": {"motion": {"effect": "fade-up", "easing": "gentle", "duration": 900}}},
            {"type": "posts", "heading": "Recent", "items": [
                {"date": "This month", "title": "On keeping a smaller surface area",
                 "excerpt": "Why I stopped adding and started removing — and what that did to the work."},
                {"date": "Last month", "title": "The case for slow tools",
                 "excerpt": "Fast software optimises for the demo. Slow software optimises for the decade."},
                {"date": "Earlier", "title": "Notes from a quiet quarter",
                 "excerpt": "Three months of fewer inputs, and what came back changed."},
            ]},
            {"type": "newsletter", "heading": "Get new posts by email",
             "subheading": "A short note when something new is published. No spam, ever."},
        ]),
        page("About", "about", 1, [
            {"type": "hero", "style": "minimal", "heading": "About",
             "subheading": "A sentence about who you are and what you write about."},
            {"type": "text",
             "body": "I write about making things — the craft, the doubt, the parts nobody puts in the case study. Replace this with your own story: tell readers what you write about and why they should subscribe."},
            {"type": "contact", "heading": "Say hello",
             "subheading": "Replies to every note, eventually.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (MARGIN,)
