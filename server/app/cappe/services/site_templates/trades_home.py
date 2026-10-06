"""trades-home — Keystone: a trust-first site for plumbers, electricians, builders and cleaners."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

KEYSTONE = SiteTemplate(
    slug="keystone-trades",
    name="Keystone — Trades & Home Services",
    category="trades-home",
    description="A clear, trust-first site for plumbers, electricians, builders, landscapers and cleaners — services, credentials, reviews and a quote form.",
    tags=("services", "reviews", "contact", "hours", "map"),
    sample_name="Keystone",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#ffffff", "surface": "#f1f5f4", "text": "#0f1f1c", "muted": "#51625e",
            "border": "#d9e2df", "brand": "#0f766e", "brandText": "#ffffff", "accent": "#f59e0b",
        },
        "fonts": {"heading": "Plus Jakarta Sans", "body": "Plus Jakarta Sans"},
        "radius": "md", "heroStyle": "split", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 106, "headingWeight": 700},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "split", "eyebrow": "Licensed · insured · local",
             "heading": "Done right, on time, tidy when we leave.",
             "subheading": f"{BUSINESS_NAME} handles repairs, installs and renovations for homes and small businesses. Replace this with your trade and service area.",
             "cta": "Get a free quote", "ctaHref": "/p/contact", "cta2": "Our services", "cta2Href": "/p/services",
             **pic("image", "keystone-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "snappy", "duration": 700}}},
            {"type": "stats", "items": [
                {"value": "Same week", "label": "Typical start for small jobs"},
                {"value": "Fixed quotes", "label": "No surprises on the invoice"},
                {"value": "Guaranteed", "label": "Workmanship warranty on every job"},
            ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "features", "heading": "What we do",
             "items": [
                 {"icon": "🔧", "title": "Repairs", "body": "Fast fixes for the things that stop a household working."},
                 {"icon": "⚡", "title": "Installations", "body": "New fittings, fixtures and systems — installed to code."},
                 {"icon": "🏠", "title": "Renovations", "body": "Kitchens, bathrooms and extensions, start to finish."},
             ]},
            {"type": "credentials", "heading": "Licensed and insured",
             "subheading": "Replace these with your real licence numbers and cover.",
             "items": [
                 {"title": "Trade licence", "issuer": "Your licensing body", "detail": "Licence number and class."},
                 {"title": "Public liability insurance", "issuer": "Your insurer", "detail": "Cover amount."},
                 {"title": "Background-checked team", "issuer": "Your policy", "detail": "Every person who enters a home."},
             ]},
            {"type": "reviews", "heading": "What customers say",
             "subheading": "Reviews from recent jobs."},
            {"type": "cta", "heading": "Need it sorted?",
             "subheading": "Send a few details and photos — we'll quote quickly.",
             "cta": "Request a quote", "ctaHref": "/p/contact"},
        ]),
        page("Services", "services", 1, [
            {"type": "hero", "style": "minimal", "heading": "Services",
             "subheading": "Replace these with the work you actually do."},
            {"type": "features", "heading": "Residential", "items": [
                {"icon": "✦", "title": "Service one", "body": "What it covers and what the customer gets."},
                {"icon": "✦", "title": "Service two", "body": "What it covers and what the customer gets."},
                {"icon": "✦", "title": "Service three", "body": "What it covers and what the customer gets."},
            ]},
            {"type": "features", "heading": "Commercial", "items": [
                {"icon": "◆", "title": "Maintenance contracts", "body": "Scheduled upkeep for shops, offices and rentals."},
                {"icon": "◆", "title": "Fit-outs", "body": "New premises ready to open."},
                {"icon": "◆", "title": "Emergency call-outs", "body": "When something fails after hours."},
            ]},
            {"type": "split", "eyebrow": "Recent work",
             "heading": "A kitchen, start to finish.",
             "body": "Describe a recent project: the brief, what you did, how long it took. Photos sell the next job.",
             "bullets": ["Scoped and quoted up front", "Finished on schedule", "Site left clean every day"],
             **pic("image", "keystone-work")},
            {"type": "faq", "heading": "Pricing & process", "items": [
                {"q": "Do you charge for quotes?", "a": "Replace with your policy — most trades quote small jobs free."},
                {"q": "How do you price?", "a": "Fixed quote, hourly, or call-out fee — say which and when."},
                {"q": "Do you offer emergency service?", "a": "Describe hours, response times and after-hours rates."},
            ]},
        ]),
        page("Reviews", "reviews", 2, [
            {"type": "hero", "style": "minimal", "heading": "Reviews",
             "subheading": "Straight from the people whose homes we've worked in."},
            {"type": "reviews", "heading": "Customer reviews"},
            {"type": "cta", "heading": "Want the same result?",
             "cta": "Get a quote", "ctaHref": "/p/contact"},
        ]),
        page("Contact", "contact", 3, [
            {"type": "hero", "style": "minimal", "heading": "Request a quote",
             "subheading": "Tell us what needs doing and where. Photos help."},
            {"type": "contact", "heading": "Quote request",
             "subheading": "We reply within one working day.",
             "fields": ["name", "email", "message"]},
            {"type": "hours", "heading": "Hours"},
            {"type": "map", "heading": "Service area"},
        ]),
    ),
)

TEMPLATES = (KEYSTONE,)
