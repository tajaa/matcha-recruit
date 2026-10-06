"""education — Chalk: a friendly, credible site for tutors, classes and small schools."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, page, pic

CHALK = SiteTemplate(
    slug="chalk-tutoring",
    name="Chalk — Tutoring & Classes",
    category="education",
    description="A friendly, credible site for tutors, classes, workshops and small schools — programmes, pricing, booking and FAQ.",
    tags=("booking", "pricing", "faq", "services"),
    sample_name="Chalk",
    theme={
        "mode": "light",
        "colors": {
            "bg": "#fffdf7", "surface": "#f6f1e4", "text": "#1f1d18", "muted": "#6b6552",
            "border": "#e8e0cc", "brand": "#2563eb", "brandText": "#ffffff", "accent": "#f59e0b",
        },
        "fonts": {"heading": "Newsreader", "body": "Inter"},
        "radius": "lg", "heroStyle": "split", "navStyle": "simple",
        "premium": True,
        "type": {"headingScale": 110},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "split", "eyebrow": "Tutoring & small-group classes",
             "heading": "Learning that finally clicks.",
             "subheading": f"{BUSINESS_NAME} offers patient, one-to-one and small-group teaching. Replace this with your subjects and who you teach.",
             "cta": "Book a free trial lesson", "ctaHref": "/p/book", "cta2": "See programmes", "cta2Href": "/p/programs",
             **pic("image", "chalk-hero"),
             "_design": {"motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900}}},
            {"type": "features", "heading": "How we teach",
             "items": [
                 {"icon": "✦", "title": "Start where you are", "body": "A short assessment, then a plan built around the gaps that matter."},
                 {"icon": "◆", "title": "Small groups, real attention", "body": "Never more than a handful of learners per session."},
                 {"icon": "▲", "title": "Progress you can see", "body": "A short note after every lesson so families know what's next."},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "stats", "items": [
                {"value": "1:1 or 1:4", "label": "Session sizes"},
                {"value": "Weekly", "label": "A steady rhythm"},
                {"value": "Every lesson", "label": "A progress note home"},
            ]},
            {"type": "testimonial", "heading": "From families", "items": [
                {"quote": "Grades went up, but the confidence came first.", "author": "Parent of a Year 10 student", "role": "Maths"},
                {"quote": "The first tutor who explained it in a way that stuck.", "author": "Adult learner", "role": "Languages"},
            ]},
            {"type": "faq", "heading": "Common questions", "items": [
                {"q": "Which subjects and ages?", "a": "List your subjects, levels and age ranges here."},
                {"q": "Online or in person?", "a": "Say where you teach and how online sessions work."},
                {"q": "How do I know it's a fit?", "a": "The first lesson is a free trial — no commitment either way."},
            ]},
            {"type": "cta", "heading": "Try a lesson, on us.",
             "subheading": "Book a free trial and see how it feels.",
             "cta": "Book a trial", "ctaHref": "/p/book"},
        ]),
        page("Programmes", "programs", 1, [
            {"type": "hero", "style": "minimal", "heading": "Programmes & pricing",
             "subheading": "Replace these with your real offers."},
            {"type": "pricing", "heading": "Ways to learn", "plans": [
                {"name": "Trial", "price": "$0", "period": "/lesson", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["45-minute first lesson", "Quick assessment", "A suggested plan"]},
                {"name": "Weekly 1:1", "price": "$60", "period": "/lesson", "highlighted": True, "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Private tuition", "Homework support between lessons", "Progress notes"]},
                {"name": "Small group", "price": "$30", "period": "/lesson", "cta": "Book", "ctaHref": "/p/book",
                 "features": ["Up to 4 learners", "Structured curriculum", "Term-time schedule"]},
            ]},
            {"type": "features", "heading": "Subjects", "items": [
                {"icon": "∑", "title": "Maths", "body": "Foundations through exam preparation."},
                {"icon": "✎", "title": "English & writing", "body": "Reading, essays and confidence on the page."},
                {"icon": "◎", "title": "Languages", "body": "Conversation-first, grammar when it helps."},
            ]},
            {"type": "split", "eyebrow": "The space",
             "heading": "A calm room to think in.",
             "body": "Describe where lessons happen — your room, your online setup, or both — and what a typical session looks like.",
             "bullets": ["Quiet, well-lit room", "Materials provided", "Parents welcome to sit in"],
             **pic("image", "chalk-classroom")},
        ]),
        page("Book", "book", 2, [
            {"type": "hero", "style": "minimal", "heading": "Book a lesson",
             "subheading": "Pick a time. The first one is free."},
            {"type": "booking", "heading": "Choose a time"},
            {"type": "contact", "heading": "Prefer to ask first?",
             "subheading": "Tell us about the learner and what you're hoping for.",
             "fields": ["name", "email", "message"]},
        ]),
        page("FAQ", "faq", 3, [
            {"type": "hero", "style": "minimal", "heading": "Questions & answers"},
            {"type": "faq", "items": [
                {"q": "What are your qualifications?", "a": "Replace with your degrees, teaching certificates and experience."},
                {"q": "Are you background-checked?", "a": "State your checks and safeguarding policy."},
                {"q": "What's the cancellation policy?", "a": "Describe your notice period and make-up lessons."},
                {"q": "Do you set homework?", "a": "Explain how practice between lessons works."},
            ]},
            {"type": "credentials", "heading": "Qualifications",
             "items": [
                 {"title": "Teaching qualification", "issuer": "Your institution", "detail": "Subject and level."},
                 {"title": "Working-with-children check", "issuer": "Your authority", "detail": "Current and verified."},
             ]},
        ]),
    ),
)

TEMPLATES = (CHALK,)
