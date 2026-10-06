"""tech — Launch: a conversion-focused landing page for a software product."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page

LAUNCH = SiteTemplate(
    slug="launch-saas",
    name="Launch — Product Landing",
    category="tech",
    description="A crisp landing page for an app or software product — features, pricing, proof and a clear call to action.",
    tags=("landing", "pricing", "contact"),
    sample_name="Launch",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#ffffff", "surface": "#f2f5fb", "text": "#0f1729", "muted": "#556077",
            "border": "#e0e6f0", "brand": "#2563eb", "brandText": "#ffffff", "accent": "#4f46e5",
        },
        "fonts": {"heading": "Space Grotesk", "body": "Inter"},
        "radius": "xl", "heroStyle": "centered", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 108},
        "style": {"buttonPadX": 22, "buttonPadY": 12},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "centered", "eyebrow": "Now in early access",
             "heading": f"{BUSINESS_NAME} helps your team ship faster.",
             "subheading": "Everything your team needs to plan, build and launch — in one place. Replace this with your product's promise.",
             "cta": "Start free", "ctaHref": "/p/pricing", "cta2": "Book a demo", "cta2Href": "/p/contact",
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900},
                         "layout": {"minHeight": "tall"}}},
            {"type": "logos", "heading": "Trusted by teams at", "items": [
                {"name": "Northwind"}, {"name": "Helio"}, {"name": "Cassette"}, {"name": "Field"}, {"name": "Pace"},
            ]},
            {"type": "features", "heading": "Built for momentum",
             "subheading": "Powerful on its own, better together.",
             "items": [
                 {"icon": "⚡", "title": "Fast", "body": "Realtime sync keeps everyone on the same page."},
                 {"icon": "🔒", "title": "Secure", "body": "SSO, granular permissions and audit logs by default."},
                 {"icon": "🔌", "title": "Connected", "body": "Integrations for the tools you already use."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "testimonial", "heading": "What customers say",
             "items": [
                 {"quote": "We cut our launch cycle in half within a month.", "author": "Jordan L.", "role": "Head of Product"},
                 {"quote": "The one tool the whole team actually agrees on.", "author": "Sam R.", "role": "Engineering Lead"},
             ]},
            {"type": "pricing", "heading": "Simple pricing",
             "plans": [
                 {"name": "Starter", "price": "$0", "period": "/mo", "cta": "Get started", "ctaHref": "/p/contact",
                  "features": ["Up to 3 projects", "Community support", "1 GB storage"]},
                 {"name": "Pro", "price": "$24", "period": "/mo", "highlighted": True, "cta": "Start free trial", "ctaHref": "/p/contact",
                  "features": ["Unlimited projects", "Priority support", "100 GB storage", "Advanced analytics"]},
                 {"name": "Team", "price": "$99", "period": "/mo", "cta": "Contact sales", "ctaHref": "/p/contact",
                  "features": ["Everything in Pro", "SSO + SAML", "Dedicated manager", "SLA"]},
             ]},
            {"type": "faq", "heading": "Questions, answered", "items": [
                {"q": "Is there a free plan?", "a": "Yes — Starter is free for small teams. Replace this with your own answer."},
                {"q": "Can I cancel any time?", "a": "Monthly plans cancel in one click from your billing page."},
                {"q": "Do you offer discounts for nonprofits or education?", "a": "Describe your policy here."},
            ]},
            {"type": "cta", "heading": "Ready to get started?",
             "subheading": "Spin up your workspace in under a minute.",
             "cta": "Start free", "ctaHref": "/p/pricing"},
        ]),
        page("Pricing", "pricing", 1, [
            {"type": "hero", "style": "minimal", "heading": "Pricing",
             "subheading": "Start free. Upgrade when you're ready."},
            {"type": "pricing",
             "plans": [
                 {"name": "Starter", "price": "$0", "period": "/mo", "cta": "Get started", "ctaHref": "/p/contact",
                  "features": ["Up to 3 projects", "Community support", "1 GB storage"]},
                 {"name": "Pro", "price": "$24", "period": "/mo", "highlighted": True, "cta": "Start trial", "ctaHref": "/p/contact",
                  "features": ["Unlimited projects", "Priority support", "100 GB storage", "Analytics"]},
                 {"name": "Team", "price": "$99", "period": "/mo", "cta": "Contact sales", "ctaHref": "/p/contact",
                  "features": ["Everything in Pro", "SSO + SAML", "Dedicated manager", "SLA"]},
             ]},
        ]),
        page("Contact", "contact", 2, [
            {"type": "contact", "heading": "Talk to us",
             "subheading": "Questions about plans or a demo? Send a note.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (LAUNCH,)
