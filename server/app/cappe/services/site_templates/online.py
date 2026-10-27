"""Product-first starters for sellers without a physical storefront.

The owner's name/tagline personalise an editable shop. Example merchandise
belongs to the private preview, never the product catalog.
"""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page


def _store(slug, name, description, colors, fonts, eyebrow, collection, sample_name):
    return SiteTemplate(
        slug=slug, name=name, category="retail", description=description,
        tags=("store", "online-store", "quick-start"), sample_name=sample_name,
        theme={"mode": "light", "colors": colors, "fonts": fonts, "radius": "sm",
               "heroStyle": "minimal", "navStyle": "simple", "premium": True},
        pages=(page("Home", "home", 0, [
            {"type": "hero", "style": "minimal", "eyebrow": eyebrow, "heading": BUSINESS_NAME,
             "subheading": "Find something you love. Make it part of your everyday.",
             "cta": "Explore the collection", "ctaHref": "#shop"},
            {"type": "store", "heading": collection},
        ]),),
    )


STUDIO = _store(
    "online-studio", "Studio — Online shop", "Earthy, tactile and quietly beautiful. A considered home for your collection.",
    {"bg": "#f5f1e8", "surface": "#e9e4d8", "text": "#303b2c", "muted": "#686d5d",
     "border": "#d6d8c9", "brand": "#3c4c36", "brandText": "#f5f1e8", "accent": "#b8946d"},
    {"heading": "Fraunces", "body": "Inter"}, "For the art of everyday", "The collection", "Forma Studio",
)
EDIT = _store(
    "online-edit", "Edit — Online shop", "A striking editorial masthead, gallery proportions and an uncompromising product focus.",
    {"bg": "#ffffff", "surface": "#f3f3f1", "text": "#171717", "muted": "#737373",
     "border": "#e5e5e5", "brand": "#171717", "brandText": "#ffffff", "accent": "#525252"},
    {"heading": "DM Sans", "body": "Inter"}, "An independent point of view", "Selected objects", "The Edit",
)
POP = _store(
    "online-pop", "Pop — Online shop", "Big personality, electric colour and playful cards. Made to stand out.",
    {"bg": "#f9f5e9", "surface": "#e4edfb", "text": "#203cb2", "muted": "#53618c",
     "border": "#203cb2", "brand": "#203cb2", "brandText": "#ffffff", "accent": "#f6d94e"},
    {"heading": "Sora", "body": "Inter"}, "A little out of the ordinary", "Good things, this way", "Good Things",
)

TEMPLATES = (STUDIO, EDIT, POP)
