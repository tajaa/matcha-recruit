"""events — Marquee: a warm, celebratory site for planners, DJs, venues and entertainers."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

MARQUEE = SiteTemplate(
    slug="marquee-events",
    name="Marquee — Events & Entertainment",
    category="events",
    description="A warm, celebratory site for event planners, DJs, venues and entertainers — services, packages, gallery and enquiries.",
    tags=("gallery", "pricing", "faq", "reviews", "contact"),
    sample_name="Marquee",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#14100e", "surface": "#1f1815", "text": "#f7efe7", "muted": "#b8a699",
            "border": "#322821", "brand": "#f59e0b", "brandText": "#14100e", "accent": "#fbbf24",
        },
        "fonts": {"heading": "Marcellus", "body": "Libre Franklin"},
        "radius": "md", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 114},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "Weddings · parties · corporate",
             "heading": "Nights people talk about for years.",
             "subheading": f"{BUSINESS_NAME} plans, hosts and soundtracks events of every size. Replace this with what you do best.",
             "cta": "Enquire about a date", "ctaHref": "/p/inquire", "cta2": "See our work", "cta2Href": "/p/gallery",
             **pic("image", "marquee-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 1000},
                         "layout": {"minHeight": "tall"}}},
            {"type": "features", "heading": "What we do",
             "items": [
                 {"icon": "✦", "title": "Full planning", "body": "From the first mood board to the last dance — every detail handled."},
                 {"icon": "♫", "title": "DJ & live sound", "body": "Read-the-room sets and clean, properly specced sound."},
                 {"icon": "◆", "title": "Styling & hire", "body": "Tables, lighting, florals and the pieces that tie it together."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True, "hover": "lift"}}},
            {"type": "gallery", "heading": "Recent celebrations",
             "images": [
                 {"url": img("marquee-table")},
                 {"url": img("marquee-dj")},
                 {"url": img("marquee-dance")},
             ]},
            {"type": "testimonial", "heading": "From our clients", "items": [
                {"quote": "Every guest asked who did this. We just pointed.", "author": "Priya & Sam", "role": "Wedding"},
                {"quote": "Ran the whole night so we didn't have to think once.", "author": "Marcus L.", "role": "Company party"},
            ]},
            {"type": "faq", "heading": "Planning questions", "items": [
                {"q": "How far in advance should we book?", "a": "Popular dates go early. Replace this with your typical lead time."},
                {"q": "Do you travel?", "a": "Say where you work and how travel is priced."},
                {"q": "Can we book just the DJ or just styling?", "a": "Yes — packages are a starting point, not a rule."},
            ]},
            {"type": "cta", "heading": "Have a date in mind?",
             "subheading": "Tell us about the day and we'll come back with ideas.",
             "cta": "Check availability", "ctaHref": "/p/inquire"},
        ]),
        page("Services", "services", 1, [
            {"type": "hero", "style": "minimal", "heading": "Services & packages",
             "subheading": "Starting points — every event is quoted on its own."},
            {"type": "pricing", "heading": "Packages", "plans": [
                {"name": "Soundtrack", "price": "from $900", "period": "", "cta": "Enquire", "ctaHref": "/p/inquire",
                 "features": ["DJ for up to 5 hours", "Sound & lighting", "Planning call"]},
                {"name": "Styled", "price": "from $3,500", "period": "", "highlighted": True, "cta": "Enquire", "ctaHref": "/p/inquire",
                 "features": ["Everything in Soundtrack", "Styling & hire", "On-the-day coordinator"]},
                {"name": "Full planning", "price": "custom", "period": "", "cta": "Enquire", "ctaHref": "/p/inquire",
                 "features": ["Venue & vendor sourcing", "Budget & timeline", "Design to delivery"]},
            ]},
            {"type": "split", "eyebrow": "How it works",
             "heading": "Three conversations, then we take it from there.",
             "body": "A first call to hear the idea, a proposal with options and clear pricing, and a planning session to lock the details. Then you enjoy the day.",
             "bullets": ["Clear proposal & pricing", "One point of contact", "Timeline shared with every vendor"],
             **pic("image", "marquee-tent")},
            {"type": "faq", "heading": "Good to know", "items": [
                {"q": "Is a deposit required?", "a": "Replace with your deposit and payment schedule."},
                {"q": "Are you insured?", "a": "State your public liability cover here."},
                {"q": "What happens if it rains?", "a": "Describe your wet-weather plan."},
            ]},
        ]),
        page("Gallery", "gallery", 2, [
            {"type": "hero", "style": "minimal", "heading": "Gallery",
             "subheading": "A few favourite moments. Swap in your own."},
            {"type": "gallery", "images": [
                {"url": img("marquee-table")}, {"url": img("marquee-dj")}, {"url": img("marquee-dance")},
                {"url": img("marquee-cake")}, {"url": img("marquee-tent")}, {"url": img("marquee-bar")},
            ]},
        ]),
        page("Inquire", "inquire", 3, [
            {"type": "hero", "style": "minimal", "heading": "Check a date",
             "subheading": "Tell us the date, the place and the kind of day you want."},
            {"type": "contact", "heading": "Enquiry",
             "subheading": "We reply within a couple of working days.",
             "fields": ["name", "email", "message"]},
            {"type": "reviews", "heading": "Recent reviews"},
        ]),
    ),
)

TEMPLATES = (MARQUEE,)
