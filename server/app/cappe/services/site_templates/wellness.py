"""wellness — Lumen: a warm editorial site for coaches, therapists and wellness practices."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

LUMEN = SiteTemplate(
    slug="lumen-coach",
    name="Lumen — Coach & Wellness",
    category="wellness",
    description="A warm, editorial site for coaches, counsellors and wellness practitioners — method, proof, pricing and online booking.",
    tags=("booking", "pricing", "faq", "services"),
    sample_name="Lumen",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fdfbf7", "surface": "#f3eee4", "text": "#1c1a17", "muted": "#6b5f50",
            "border": "#e6ddcd", "brand": "#b4532a", "brandText": "#ffffff", "accent": "#d97706",
        },
        "fonts": {"heading": "Fraunces", "body": "Inter"},
        "radius": "md", "heroStyle": "split", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 108},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "split", "eyebrow": "1:1 sessions",
             "heading": "Become the version of you that's been waiting.",
             "subheading": f"{BUSINESS_NAME} offers personal coaching for people who are done waiting for permission. Clear goals, real accountability, steady progress.",
             "cta": "Book a free intro call", "ctaHref": "/p/book", "cta2": "My approach", "cta2Href": "/p/about",
             **pic("image", "lumen-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900}}},
            {"type": "stats", "items": [
                {"value": "1:1", "label": "Every session is just us"},
                {"value": "Weekly", "label": "A steady rhythm"},
                {"value": "90 days", "label": "To your first milestone"},
            ]},
            {"type": "split", "reverse": True, "eyebrow": "How it works",
             "heading": "A method, not a motivational poster.",
             "body": "We start with where you actually are, name the goal that matters, and build a plan you'll keep. Then we do the unglamorous part — showing up, every week.",
             "bullets": ["Weekly 1:1 sessions", "A plan tailored to your goals", "Accountability that sticks", "Tools you keep after we're done"],
             "cta": "See pricing", "ctaHref": "/p/pricing",
             **pic("image", "lumen-method")},
            {"type": "testimonial", "heading": "In their words", "items": [
                {"quote": "Six months of this did what three years of self-help books couldn't.", "author": "Maya T.", "role": "Founder"},
                {"quote": "I finally have a system instead of a guilt complex.", "author": "Devin R.", "role": "Product manager"},
            ]},
            {"type": "faq", "heading": "Questions, answered", "items": [
                {"q": "Who is this for?", "a": "Anyone navigating a transition — a new role, a new business, or a season where the old playbook stopped working."},
                {"q": "How long is a typical engagement?", "a": "Most clients work with me for three to six months. We reassess every month so you're never locked in."},
                {"q": "Do you offer a trial?", "a": "Yes — a free 30-minute intro call so we can both decide it's a fit."},
                {"q": "In person or remote?", "a": "Remote by default, with optional in-person intensives. Replace this with your own setup."},
            ]},
            {"type": "cta", "heading": "Ready to start?",
             "subheading": "Book a free intro call and we'll map your first 90 days.",
             "cta": "Book a free call", "ctaHref": "/p/book"},
        ]),
        page("About", "about", 1, [
            {"type": "hero", "style": "minimal", "eyebrow": "About",
             "heading": "Hi, I'm your coach.",
             "subheading": "A sentence about who you help and the change you create."},
            {"type": "split", "eyebrow": "My story",
             "heading": "Why I do this work.",
             "body": "Replace this with your background — what you've done, what you learned the hard way, and why you decided to help others do it faster.",
             "bullets": ["Certified & trained", "Years in the field", "A point of view you can trust"],
             **pic("image", "lumen-about")},
            {"type": "credentials", "heading": "Training & credentials",
             "subheading": "Replace these with your real certifications.",
             "items": [
                 {"title": "Certified professional coach", "issuer": "Your accrediting body", "detail": "Add the programme and level."},
                 {"title": "Continuing education", "issuer": "Your institute", "detail": "Describe your ongoing training."},
             ]},
        ]),
        page("Pricing", "pricing", 2, [
            {"type": "hero", "style": "minimal", "heading": "Ways to work together",
             "subheading": "Pick the depth that fits where you are."},
            {"type": "pricing", "plans": [
                {"name": "Intro", "price": "$0", "period": "/call", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["30-minute intro call", "Honest fit assessment", "A first next step"]},
                {"name": "Monthly", "price": "$450", "period": "/mo", "highlighted": True, "cta": "Start", "ctaHref": "/p/book",
                 "features": ["Weekly 1:1 sessions", "Support between calls", "Your tailored plan", "Cancel anytime"]},
                {"name": "Intensive", "price": "$1,800", "period": "", "cta": "Enquire", "ctaHref": "/p/book",
                 "features": ["Full-day deep dive", "90-day roadmap", "Two follow-up sessions"]},
            ]},
        ]),
        page("Book", "book", 3, [
            {"type": "hero", "style": "minimal", "heading": "Book a session",
             "subheading": "Pick a time that works. Your first intro call is free."},
            {"type": "booking", "heading": "Choose a time",
             "subheading": "You'll get a confirmation by email."},
            {"type": "contact", "heading": "Prefer to write first?",
             "subheading": "Tell me a little about where you are and what you want to change.",
             "fields": ["name", "email", "message"]},
        ]),
    ),
)

TEMPLATES = (LUMEN,)
