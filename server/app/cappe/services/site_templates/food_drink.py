"""food-drink — Saveur (café / bistro) and Maison (fine dining)."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

SAVEUR = SiteTemplate(
    slug="saveur-bistro",
    name="Saveur — Café & Bistro",
    category="food-drink",
    description="A warm page for a café, bistro or neighbourhood restaurant — menu, photos, hours and a way to reserve.",
    tags=("menu", "hours", "map", "reviews", "contact"),
    sample_name="Saveur",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#16100c", "surface": "#1f1813", "text": "#f5ece0", "muted": "#b9a892",
            "border": "#322619", "brand": "#e0992f", "brandText": "#16100c", "accent": "#f59e0b",
        },
        "fonts": {"heading": "Playfair Display", "body": "Lora"},
        "radius": "md", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 110},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Neighbourhood kitchen",
             "heading": "Fresh, local, made daily.",
             "subheading": f"{BUSINESS_NAME} serves seasonal plates and natural wine. Replace this with what you cook and why people come back.",
             "cta": "View menu", "ctaHref": "/p/menu", "cta2": "Reserve a table", "cta2Href": "/p/visit",
             **pic("image", "saveur-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900},
                         "layout": {"minHeight": "tall"}}},
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
            {"type": "gallery", "heading": "From the kitchen",
             "images": [
                 {"url": img("saveur-plate-1")},
                 {"url": img("saveur-plate-2")},
                 {"url": img("saveur-plate-3")},
             ]},
            {"type": "reviews", "heading": "What guests say",
             "subheading": "Reviews from people who've eaten with us."},
            {"type": "hours", "heading": "Hours"},
            {"type": "cta", "heading": "Come hungry.",
             "subheading": "Walk-ins welcome; reservations for larger parties.",
             "cta": "Reserve a table", "ctaHref": "/p/visit"},
        ]),
        page("Menu", "menu", 1, [
            {"type": "hero", "style": "minimal", "heading": "Menu",
             "subheading": "Seasonal — it changes with what's good."},
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
        page("Visit", "visit", 2, [
            {"type": "hero", "style": "minimal", "heading": "Visit us",
             "subheading": "Find us, check the hours, or request a table."},
            {"type": "map", "heading": "Find us"},
            {"type": "hours", "heading": "Opening hours"},
            {"type": "contact", "heading": "Reservations",
             "subheading": "Date, time, party size and anything we should know.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

MAISON = SiteTemplate(
    slug="maison-dining",
    name="Maison — Fine Dining",
    category="food-drink",
    description="A refined restaurant site with a kitchen story, tasting menu, FAQ and reservation requests.",
    tags=("menu", "contact", "faq"),
    sample_name="Maison",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#141210", "surface": "#1e1a16", "text": "#f6efe6", "muted": "#bdae9c",
            "border": "#2e2820", "brand": "#c9a24b", "brandText": "#141210", "accent": "#e0b85e",
        },
        "fonts": {"heading": "Playfair Display", "body": "Lora"},
        "radius": "sm", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 112, "headingWeight": 400},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Tasting menu",
             "heading": "A table worth the evening.",
             "subheading": f"Seasonal tasting menus and a considered cellar at {BUSINESS_NAME}.",
             "cta": "Reserve", "ctaHref": "/p/reserve",
             **pic("image", "maison-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 1100},
                         "layout": {"minHeight": "tall"}}},
            {"type": "split", "eyebrow": "The kitchen",
             "heading": "Cooked by hand, plated with intent.",
             "body": "Each menu is built around what the farms send that week. Nothing frozen, nothing rushed — just the best of the season, served the way it should be.",
             "bullets": ["Seasonal tasting menu", "Natural & classic wine pairings", "A limited number of covers each night"],
             **pic("image", "maison-chef")},
            {"type": "menu", "heading": "This week's menu",
             "sections": [
                {"name": "To begin", "items": [
                    {"name": "Oyster, cucumber, dill", "description": "Daily catch, mignonette."},
                    {"name": "Heirloom tomato", "description": "Stracciatella, basil oil."},
                ]},
                {"name": "Mains", "items": [
                    {"name": "Dry-aged duck", "description": "Cherry, turnip, jus."},
                    {"name": "Line-caught turbot", "description": "Brown butter, capers."},
                ]},
                {"name": "To finish", "items": [
                    {"name": "Dark chocolate, olive oil"},
                    {"name": "Selection of cheese"},
                ]},
             ]},
            {"type": "faq", "heading": "Good to know", "items": [
                {"q": "Do you accommodate dietary needs?", "a": "Yes — note them when you reserve and the kitchen will adapt the menu."},
                {"q": "Is there a dress code?", "a": "Smart casual. Replace with your own policy."},
                {"q": "Large parties?", "a": "Private parties can be arranged. Enquire below."},
            ]},
            {"type": "cta", "heading": "Reserve your evening.",
             "subheading": "Tables open a month ahead.",
             "cta": "Request a table", "ctaHref": "/p/reserve"},
        ]),
        page("Reservations", "reserve", 1, [
            {"type": "hero", "style": "minimal", "heading": "Reservations",
             "subheading": "Send your details and we'll confirm by email."},
            {"type": "contact", "heading": "Request a table",
             "subheading": "Date, time, party size, and any dietary notes.",
             "fields": ["name", "email", "message"]},
            {"type": "map", "heading": "Find us"},
            {"type": "hours", "heading": "Service hours"},
        ]),
    ),
)

TEMPLATES = (SAVEUR, MAISON)
