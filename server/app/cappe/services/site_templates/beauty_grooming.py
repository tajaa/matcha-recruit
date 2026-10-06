"""beauty-grooming — Lumière: an elegant site for salons, spas, barbers and nail studios."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

LUMIERE = SiteTemplate(
    slug="lumiere-salon",
    name="Lumière — Salon & Spa",
    category="beauty-grooming",
    description="An elegant, airy site for salons, spas, barbers and nail studios — treatment menu, online booking, team credentials and reviews.",
    tags=("booking", "pricing", "reviews", "hours", "map"),
    sample_name="Lumière",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fef7f6", "surface": "#fbe9ea", "text": "#2b1f22", "muted": "#7d6367",
            "border": "#f3d9dc", "brand": "#c1466a", "brandText": "#ffffff", "accent": "#c1466a",
        },
        "fonts": {"heading": "Cormorant Garamond", "body": "DM Sans"},
        "radius": "2xl", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 122, "heroAnim": "rise"},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Salon & spa",
             "heading": "Leave feeling like yourself, only more so.",
             "subheading": f"Facials, hair and nails at {BUSINESS_NAME}. Replace this with the treatments you're known for.",
             "cta": "Book an appointment", "ctaHref": "/p/book", "cta2": "See treatments", "cta2Href": "/p/services",
             **pic("image", "lumiere-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 1000},
                         "layout": {"minHeight": "tall"}}},
            {"type": "features", "heading": "Signature treatments",
             "subheading": "A few favourites — the full menu is on the Services page.",
             "items": [
                 {"icon": "✦", "title": "Glow facial", "body": "A 60-minute reset: cleanse, exfoliate, mask and massage."},
                 {"icon": "❀", "title": "Cut & colour", "body": "Consultation-led colour and a cut that grows out well."},
                 {"icon": "◌", "title": "Manicure & pedicure", "body": "Clean, careful and long-lasting — classic or gel."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True, "hover": "lift"}}},
            {"type": "split", "eyebrow": "The space",
             "heading": "Calm from the moment you walk in.",
             "body": "Soft light, warm towels and people who listen before they reach for the scissors. Replace this with what makes your place yours.",
             "bullets": ["Licensed, insured professionals", "Clean-ingredient products", "Easy online booking"],
             "cta": "Meet the team", "ctaHref": "/p/services",
             **pic("image", "lumiere-room")},
            {"type": "gallery", "heading": "A look inside",
             "images": [
                 {"url": img("lumiere-products")},
                 {"url": img("lumiere-towels")},
                 {"url": img("lumiere-nails")},
             ]},
            {"type": "reviews", "heading": "Kind words",
             "subheading": "Reviews from clients who've been in the chair."},
            {"type": "cta", "heading": "Ready when you are.",
             "subheading": "Pick a time online — it takes a minute.",
             "cta": "Book now", "ctaHref": "/p/book"},
        ]),
        page("Services", "services", 1, [
            {"type": "hero", "style": "minimal", "heading": "Treatments & prices",
             "subheading": "Replace these with your own services and prices."},
            {"type": "pricing", "heading": "Skin", "plans": [
                {"name": "Express facial", "price": "$65", "period": "30 min", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Cleanse & exfoliate", "Mask", "Moisture & SPF"]},
                {"name": "Glow facial", "price": "$120", "period": "60 min", "highlighted": True, "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Everything in Express", "Extractions", "Massage", "LED or peel add-on"]},
                {"name": "Advanced treatment", "price": "$180", "period": "75 min", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Consultation", "Targeted actives", "Aftercare plan"]},
            ]},
            {"type": "pricing", "heading": "Hair & nails", "plans": [
                {"name": "Cut & style", "price": "$70", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Consultation", "Wash & cut", "Blow-dry"]},
                {"name": "Colour", "price": "from $140", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Full or partial", "Toner & gloss", "Treatment"]},
                {"name": "Gel manicure", "price": "$55", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Shape & cuticles", "Gel polish", "Hand massage"]},
            ]},
            {"type": "credentials", "heading": "Our team",
             "subheading": "Replace with your stylists and estheticians.",
             "items": [
                 {"title": "Licensed esthetician", "issuer": "State board", "detail": "Skin specialist — facials, peels and LED."},
                 {"title": "Senior stylist", "issuer": "Colour certified", "detail": "Balayage, lived-in colour and precision cuts."},
                 {"title": "Nail technician", "issuer": "Licensed", "detail": "Gel, classic and nail art."},
             ]},
            {"type": "faq", "heading": "Before you book", "items": [
                {"q": "Do I need a consultation first?", "a": "Colour and advanced skin treatments start with a quick chat — book one online."},
                {"q": "What's your cancellation policy?", "a": "Replace this with your own policy and notice period."},
                {"q": "Which products do you use?", "a": "Describe your product lines here."},
            ]},
        ]),
        page("Book", "book", 2, [
            {"type": "hero", "style": "minimal", "heading": "Book an appointment",
             "subheading": "Choose a treatment and a time. You'll get a confirmation by email."},
            {"type": "booking", "heading": "Pick a time"},
            {"type": "hours", "heading": "Opening hours"},
        ]),
        page("Visit", "visit", 3, [
            {"type": "hero", "style": "minimal", "heading": "Visit us",
             "subheading": "Find us, check the hours, or send a note."},
            {"type": "map", "heading": "Find the salon"},
            {"type": "hours", "heading": "Hours"},
            {"type": "contact", "heading": "Questions?",
             "subheading": "Gift cards, group bookings or anything else.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (LUMIERE,)
