"""automotive — Torque: a confident site for workshops, detailers and tyre shops."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

TORQUE = SiteTemplate(
    slug="torque-auto",
    name="Torque — Auto Shop & Detailing",
    category="automotive",
    description="A confident, no-nonsense site for mechanics, detailers and tyre shops — services, packages, certifications, booking and hours.",
    tags=("booking", "pricing", "services", "hours", "map"),
    sample_name="Torque",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#0c0e12", "surface": "#151920", "text": "#f1f4f8", "muted": "#94a0b2",
            "border": "#232a35", "brand": "#ef4444", "brandText": "#ffffff", "accent": "#f59e0b",
        },
        "fonts": {"heading": "Archivo Black", "body": "Libre Franklin"},
        "radius": "sm", "heroStyle": "image", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 110},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Service · repairs · detailing",
             "heading": "Straight answers. Honest prices. Done right.",
             "subheading": f"{BUSINESS_NAME} keeps your car running and looking the part. Replace this with your specialties and the makes you work on.",
             "cta": "Book a service", "ctaHref": "/p/book", "cta2": "Services & prices", "cta2Href": "/p/services",
             **pic("image", "torque-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "snappy", "duration": 700},
                         "layout": {"minHeight": "tall"}}},
            {"type": "features", "heading": "What we do",
             "items": [
                 {"icon": "🔧", "title": "Servicing & repairs", "body": "Logbook servicing, diagnostics, brakes, suspension and more."},
                 {"icon": "✦", "title": "Detailing", "body": "Interior and exterior detailing, paint correction and protection."},
                 {"icon": "◎", "title": "Tyres & alignment", "body": "Fitting, balancing and alignment while you wait."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "stats", "items": [
                {"value": "Same day", "label": "On most services"},
                {"value": "Up-front", "label": "Quotes before any work"},
                {"value": "Warrantied", "label": "Parts and labour"},
            ]},
            {"type": "credentials", "heading": "Certified technicians",
             "subheading": "Replace with your real certifications and memberships.",
             "items": [
                 {"title": "Licensed workshop", "issuer": "Your licensing body", "detail": "Licence number."},
                 {"title": "Manufacturer-trained", "issuer": "Brands you specialise in", "detail": "Factory diagnostics and tooling."},
                 {"title": "Industry association member", "issuer": "Your association", "detail": "Code of conduct and dispute resolution."},
             ]},
            {"type": "reviews", "heading": "What drivers say"},
            {"type": "cta", "heading": "Hearing something odd?",
             "subheading": "Book a check — we'll tell you what it is and what it costs before we touch it.",
             "cta": "Book now", "ctaHref": "/p/book"},
        ]),
        page("Services", "services", 1, [
            {"type": "hero", "style": "minimal", "heading": "Services & prices",
             "subheading": "Indicative pricing — every job is confirmed before work starts."},
            {"type": "pricing", "heading": "Servicing", "plans": [
                {"name": "Basic service", "price": "from $180", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Oil & filter", "Fluids & safety check", "Report with photos"]},
                {"name": "Logbook service", "price": "from $320", "period": "", "highlighted": True, "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Manufacturer schedule", "Genuine or equivalent parts", "Warranty-safe"]},
                {"name": "Diagnostics", "price": "$120", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Fault scan", "Road test", "Written quote"]},
            ]},
            {"type": "pricing", "heading": "Detailing", "plans": [
                {"name": "Maintenance wash", "price": "$60", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Hand wash & dry", "Wheels & tyres", "Interior vacuum"]},
                {"name": "Full detail", "price": "from $350", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Decontamination", "Interior deep clean", "Sealant"]},
                {"name": "Paint correction", "price": "custom", "period": "", "cta": "Enquire", "ctaHref": "/p/visit",
                 "features": ["Multi-stage polish", "Ceramic coating options", "Inspection first"]},
            ]},
            {"type": "split", "eyebrow": "Detailing bay",
             "heading": "Finish that looks better than new.",
             "body": "Describe your detailing process and products, and the kinds of cars you work on most.",
             "bullets": ["Dedicated indoor bay", "Professional-grade products", "Before-and-after photos"],
             **pic("image", "torque-detail")},
            {"type": "faq", "heading": "Good to know", "items": [
                {"q": "Do you offer a courtesy car or lift?", "a": "Replace with what you offer while the car is in."},
                {"q": "Will servicing here void my warranty?", "a": "Explain your logbook servicing and how it protects the warranty."},
                {"q": "What payment methods do you take?", "a": "List them here."},
            ]},
        ]),
        page("Book", "book", 2, [
            {"type": "hero", "style": "minimal", "heading": "Book your car in",
             "subheading": "Choose a service and a drop-off time."},
            {"type": "booking", "heading": "Pick a time"},
            {"type": "hours", "heading": "Workshop hours"},
        ]),
        page("Visit", "visit", 3, [
            {"type": "hero", "style": "minimal", "heading": "Find the workshop",
             "subheading": "Parking, drop-off and after-hours key box details."},
            {"type": "map", "heading": "Location"},
            {"type": "hours", "heading": "Hours"},
            {"type": "contact", "heading": "Ask a question",
             "subheading": "Quotes, parts or anything else.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (TORQUE,)
