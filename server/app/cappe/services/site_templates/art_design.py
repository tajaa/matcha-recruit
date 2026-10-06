"""art-design — Atelier: a bold dark portfolio for designers and makers."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

ATELIER = SiteTemplate(
    slug="atelier-portfolio",
    name="Atelier — Portfolio",
    category="art-design",
    description="A bold dark portfolio for designers, illustrators and makers — work first, words second.",
    tags=("portfolio", "gallery", "contact"),
    sample_name="Atelier",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#0b0b0f", "surface": "#15151d", "text": "#fafafa", "muted": "#9ca3af",
            "border": "#262630", "brand": "#a3e635", "brandText": "#0b0b0f", "accent": "#a3e635",
        },
        "fonts": {"heading": "Space Grotesk", "body": "Inter"},
        "radius": "2xl", "heroStyle": "split", "navStyle": "simple",
        # Premium polish (stripped for free plans by gate_theme).
        "premium": True,
        "type": {"headingScale": 108},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "split", "eyebrow": "Designer & maker",
             "heading": f"{BUSINESS_NAME} builds things people love to use.",
             "subheading": "Independent design across brand, web and interface. Replace this line with the one sentence that says what you make.",
             "cta": "View work", "ctaHref": "/p/work", "cta2": "Get in touch", "cta2Href": "/p/contact",
             **pic("image", "atelier-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900}}},
            {"type": "features", "heading": "What I do",
             "items": [
                 {"icon": "✦", "title": "Brand", "body": "Identity systems that scale from logo to product."},
                 {"icon": "◆", "title": "Web", "body": "Fast, accessible marketing sites and storefronts."},
                 {"icon": "▲", "title": "Product", "body": "End-to-end interface design for apps and tools."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "gallery", "heading": "Selected work",
             "images": [
                 {"url": img("atelier-work-1"), "caption": "Identity"},
                 {"url": img("atelier-work-2"), "caption": "Web"},
                 {"url": img("atelier-work-3"), "caption": "Colour & type"},
                 {"url": img("atelier-work-4"), "caption": "Packaging"},
                 {"url": img("atelier-work-5"), "caption": "App"},
                 {"url": img("atelier-work-6"), "caption": "Print"},
             ]},
            {"type": "cta", "heading": "Have a project in mind?",
             "subheading": "Tell me what you're making and when you need it.",
             "cta": "Start a conversation", "ctaHref": "/p/contact"},
        ]),
        page("Work", "work", 1, [
            {"type": "hero", "style": "minimal", "heading": "Work",
             "subheading": "A selection of recent projects. Swap these for your own."},
            {"type": "gallery",
             "images": [
                 {"url": img("atelier-work-1"), "caption": "Project one"},
                 {"url": img("atelier-work-2"), "caption": "Project two"},
                 {"url": img("atelier-work-3"), "caption": "Project three"},
                 {"url": img("atelier-work-4"), "caption": "Project four"},
                 {"url": img("atelier-work-5"), "caption": "Project five"},
                 {"url": img("atelier-work-6"), "caption": "Project six"},
             ]},
        ]),
        page("Contact", "contact", 2, [
            {"type": "contact", "heading": "Let's work together",
             "subheading": "Tell me about your project and timeline.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (ATELIER,)
