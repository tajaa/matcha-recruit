"""pets — Pawprint: a warm, playful site for groomers, daycare, boarding and trainers."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

PAWPRINT = SiteTemplate(
    slug="pawprint-pets",
    name="Pawprint — Pet Care",
    category="pets",
    description="A warm, playful site for groomers, daycare, boarding, walkers and trainers — services, prices, booking and happy-customer photos.",
    tags=("booking", "pricing", "gallery", "reviews", "hours", "map"),
    sample_name="Pawprint",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fffaf3", "surface": "#fdf0e0", "text": "#2b2118", "muted": "#7c6a5a",
            "border": "#f3e2cc", "brand": "#ea580c", "brandText": "#ffffff", "accent": "#16a34a",
        },
        "fonts": {"heading": "Bricolage Grotesque", "body": "Work Sans"},
        "radius": "2xl", "heroStyle": "image", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 112, "headingWeight": 700},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Grooming · daycare · boarding",
             "heading": "Happy pets, calm owners.",
             "subheading": f"{BUSINESS_NAME} looks after your animals like they're ours. Replace this with the care you offer and the pets you welcome.",
             "cta": "Book a visit", "ctaHref": "/p/book", "cta2": "Services & prices", "cta2Href": "/p/services",
             **pic("image", "pawprint-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "spring", "duration": 800},
                         "layout": {"minHeight": "tall"}}},
            {"type": "features", "heading": "What we offer",
             "items": [
                 {"icon": "✂", "title": "Grooming", "body": "Bath, brush, trim and nails — gentle handling for nervous pets."},
                 {"icon": "☀", "title": "Daycare", "body": "Supervised play in small, well-matched groups."},
                 {"icon": "🌙", "title": "Boarding", "body": "Comfortable overnight stays with daily photo updates."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True, "hover": "lift"}}},
            {"type": "pricing", "heading": "Popular services", "plans": [
                {"name": "Bath & brush", "price": "from $45", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Shampoo & condition", "Blow-dry", "Nail trim"]},
                {"name": "Full groom", "price": "from $85", "period": "", "highlighted": True, "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Everything in Bath & brush", "Haircut & style", "Ear clean"]},
                {"name": "Daycare day", "price": "$38", "period": "/day", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Supervised play", "Rest time", "Pick-up by closing"]},
            ]},
            {"type": "gallery", "heading": "Fresh from the tub",
             "images": [
                 {"url": img("pawprint-bath")},
                 {"url": img("pawprint-play")},
                 {"url": img("pawprint-cat")},
             ]},
            {"type": "reviews", "heading": "From our regulars",
             "subheading": "What owners say after their first visit."},
            {"type": "cta", "heading": "Spots fill fast on weekends.",
             "subheading": "Book online in under a minute.",
             "cta": "Book now", "ctaHref": "/p/book"},
        ]),
        page("Services", "services", 1, [
            {"type": "hero", "style": "minimal", "heading": "Services & prices",
             "subheading": "Replace these with your own services, breeds and prices."},
            {"type": "pricing", "heading": "Grooming", "plans": [
                {"name": "Small dog", "price": "from $55", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Bath & dry", "Trim & tidy", "Nails & ears"]},
                {"name": "Large dog", "price": "from $95", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Bath & dry", "Full haircut", "Nails & ears"]},
                {"name": "Cat groom", "price": "from $70", "period": "", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Gentle handling", "Brush-out or lion cut", "Nails"]},
            ]},
            {"type": "pricing", "heading": "Daycare & boarding", "plans": [
                {"name": "Daycare", "price": "$38", "period": "/day", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Small playgroups", "Rest periods", "Multi-day bundles"]},
                {"name": "Boarding", "price": "$65", "period": "/night", "highlighted": True, "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Private suite", "Two walks a day", "Photo updates"]},
                {"name": "Training", "price": "$70", "period": "/session", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Puppy basics", "Recall & leash", "Behaviour support"]},
            ]},
            {"type": "faq", "heading": "Good to know", "items": [
                {"q": "Do you need vaccination records?", "a": "Yes — describe which vaccinations you require and how to send them."},
                {"q": "Can my nervous dog be groomed?", "a": "Describe how you handle anxious or reactive pets."},
                {"q": "What should I bring for boarding?", "a": "Food, medication and a familiar blanket. Replace with your own list."},
            ]},
        ]),
        page("Book", "book", 2, [
            {"type": "hero", "style": "minimal", "heading": "Book a visit",
             "subheading": "Choose a service and a time. We'll confirm by email."},
            {"type": "booking", "heading": "Pick a time"},
            {"type": "hours", "heading": "Opening hours"},
        ]),
        page("Visit", "visit", 3, [
            {"type": "hero", "style": "minimal", "heading": "Find us",
             "subheading": "Drop-off, pick-up and parking details."},
            {"type": "map", "heading": "Location"},
            {"type": "hours", "heading": "Hours"},
            {"type": "contact", "heading": "Questions?",
             "subheading": "New customers, special needs or anything else.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (PAWPRINT,)
