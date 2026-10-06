"""retail — Bloom: a friendly storefront for makers and small shops."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

BLOOM = SiteTemplate(
    slug="bloom-store",
    name="Bloom — Shop",
    category="retail",
    description="A friendly storefront for makers, boutiques and small shops — products front and centre, a story, and a newsletter.",
    tags=("store", "newsletter", "contact"),
    sample_name="Bloom",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fff8f3", "surface": "#ffeee3", "text": "#2a1d18", "muted": "#7a6258",
            "border": "#f6ddcd", "brand": "#f0603a", "brandText": "#ffffff", "accent": "#fb923c",
        },
        "fonts": {"heading": "Sora", "body": "Inter"},
        "radius": "2xl", "heroStyle": "centered", "navStyle": "simple",
        "premium": True,
        "style": {"buttonPadX": 22, "buttonPadY": 12},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "centered", "eyebrow": "The shop is open",
             "heading": "Things we made, for you.",
             "subheading": f"Welcome to {BUSINESS_NAME}. Replace this with what you sell and who it's for.",
             "cta": "Shop now", "ctaHref": "#shop", "cta2": "Our story", "cta2Href": "/p/about",
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "spring", "duration": 800}}},
            {"type": "features", "heading": "Why shop here", "items": [
                {"icon": "✦", "title": "Made with care", "body": "Every item is designed and finished by hand."},
                {"icon": "⚡", "title": "Fast dispatch", "body": "Orders ship within a couple of business days."},
                {"icon": "♡", "title": "Support a small business", "body": "Your order goes straight to the people who made it."},
            ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "store", "heading": "Shop", "subheading": "Pick something you love."},
            {"type": "split", "reverse": True, "eyebrow": "About",
             "heading": "Hi — we're the makers behind the shop.",
             "body": "Replace this with your story — what you make, why you started, and what makes your work yours.",
             "bullets": ["Independent & handmade", "Shipped with care", "Made in small batches"],
             **pic("image", "bloom-maker")},
            {"type": "reviews", "heading": "From our customers",
             "subheading": "Real reviews from real orders."},
            {"type": "newsletter", "heading": "Get first dibs",
             "subheading": "New drops and the occasional discount — no spam, ever."},
        ]),
        page("Shop", "shop", 1, [
            {"type": "hero", "style": "minimal", "heading": "Shop",
             "subheading": "Everything in stock right now."},
            {"type": "store", "heading": "All products"},
            {"type": "faq", "heading": "Shipping & returns", "items": [
                {"q": "How long does shipping take?", "a": "Replace with your dispatch and delivery times."},
                {"q": "Can I return something?", "a": "Describe your returns policy here."},
                {"q": "Do you ship internationally?", "a": "Say where you ship and what it costs."},
            ]},
        ]),
        page("About", "about", 2, [
            {"type": "hero", "style": "minimal", "heading": f"About {BUSINESS_NAME}",
             "subheading": "The makers, the method, the mission."},
            {"type": "text", "body": "Tell people who you are and why your work exists. Then add the details that make customers trust you — your process, materials, or guarantee."},
            {"type": "contact", "heading": "Questions?",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (BLOOM,)
