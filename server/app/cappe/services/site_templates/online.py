"""Product-first starters for sellers without a physical storefront.

Only the owner's name/tagline and a shop are persisted. Example merchandise
belongs to the private preview, never the product catalog.
"""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page


def _store(slug, name, description, colors, fonts, hero):
    return SiteTemplate(
        slug=slug, name=name, category="retail", description=description,
        tags=("store", "online-store", "quick-start"), sample_name="Your store",
        theme={"mode": "light", "colors": colors, "fonts": fonts, "radius": "lg",
               "heroStyle": hero, "navStyle": "simple", "premium": True},
        pages=(page("Home", "home", 0, [
            {"type": "hero", "style": hero, "heading": BUSINESS_NAME, "cta": "Shop now", "ctaHref": "#shop"},
            {"type": "store", "heading": "Shop"},
        ]),),
    )


STUDIO = _store(
    "online-studio", "Studio — Online shop", "A warm, quiet shop for makers and small collections.",
    {"bg": "#faf7f2", "surface": "#eee7dd", "text": "#29231e", "muted": "#78695c",
     "border": "#ded4c6", "brand": "#895b3b", "brandText": "#ffffff", "accent": "#895b3b"},
    {"heading": "Fraunces", "body": "Inter"}, "centered",
)
EDIT = _store(
    "online-edit", "Edit — Online shop", "A clean, editorial storefront that puts your products first.",
    {"bg": "#ffffff", "surface": "#f3f3f1", "text": "#171717", "muted": "#737373",
     "border": "#e5e5e5", "brand": "#171717", "brandText": "#ffffff", "accent": "#525252"},
    {"heading": "DM Sans", "body": "Inter"}, "minimal",
)
POP = _store(
    "online-pop", "Pop — Online shop", "A bright, playful shop for colourful products and new releases.",
    {"bg": "#fff9ef", "surface": "#ffedcf", "text": "#302133", "muted": "#796479",
     "border": "#e8d5e5", "brand": "#7539a0", "brandText": "#ffffff", "accent": "#e67529"},
    {"heading": "Sora", "body": "Inter"}, "centered",
)

TEMPLATES = (STUDIO, EDIT, POP)
