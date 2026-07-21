"""Curated section presets — professionally-authored block content + design.

Each preset is a named combination of block type, placeholder content, and a
`_design` bag using the design vocabulary (motion/bg/layout/colors from
`design_registry`, including the Phase 1-3 additions: easing, soft reveals,
responsive pads). Merlin applies one via:

    {"op":"apply_section_preset","preset":"<key>","at":<index>}

which `merlin_ops._v_apply_section_preset` REWRITES at validation time into a
fully-populated `add_block` op — the client never needs this library (no
Python/TS mirror; the expanded op is ordinary and fully editable afterwards).

Authoring rules (enforced by tests/cappe/test_section_presets.py — the
drift-gate runs every preset through the real add_block validation and a
render smoke test):
  - `content` keys/values must satisfy `merlin_catalog.BLOCK_FIELDS` kinds
    (+ SELECT_OPTIONS for selects).
  - `design` groups/keys/values must satisfy the AI-facing DESIGN_GROUPS specs
    (so e.g. no `layout.gap` — that key is a renderer-only px override).
  - Copy is business-agnostic placeholder text the user will edit; never
    invent emails/domains (root CLAUDE.md test-data rule).
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SectionPreset:
    key: str
    label: str
    blurb: str            # one line, shown to the model in the prompt catalog
    block_type: str
    content: dict[str, Any] = field(default_factory=dict)
    design: dict[str, dict[str, Any]] = field(default_factory=dict)


SECTION_PRESETS: tuple[SectionPreset, ...] = (
    SectionPreset(
        key="hero-impact",
        label="Impact hero",
        blurb="tall centered hero, big rising headline, two CTAs",
        block_type="hero",
        content={
            "eyebrow": "Welcome",
            "heading": "Make something people remember",
            "subheading": "One clear sentence about the value you deliver and who it's for.",
            "style": "centered",
            "cta": "Get started",
            "ctaHref": "#contact",
            "cta2": "Learn more",
            "cta2Href": "#about",
        },
        design={
            "motion": {"effect": "fade-up", "heading": "rise", "easing": "gentle", "duration": 900},
            "layout": {"minHeight": "tall", "padTop": "xl", "padBottom": "xl", "padTopSm": "lg"},
        },
    ),
    SectionPreset(
        key="hero-split-product",
        label="Split product hero",
        blurb="split hero with image slot, eyebrow + single CTA",
        block_type="hero",
        content={
            "eyebrow": "New",
            "heading": "The simpler way to get it done",
            "subheading": "Short supporting copy. Add your product photo on the right.",
            "style": "split",
            "cta": "See how it works",
            "ctaHref": "#features",
        },
        design={
            "motion": {"effect": "fade", "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="stats-band-dark",
        label="Dark stats band",
        blurb="dark full-width band with 4 staggered stat numbers",
        block_type="stats",
        content={
            "heading": "Results that speak for themselves",
            "subheading": "",
            "items": [
                {"value": "10k+", "label": "Happy customers"},
                {"value": "99.9%", "label": "Uptime"},
                {"value": "4.9★", "label": "Average rating"},
                {"value": "24/7", "label": "Support"},
            ],
        },
        design={
            "bg": {"type": "color", "color": "#101216"},
            "colors": {"text": "#c7cbd4", "heading": "#ffffff"},
            "motion": {"effect": "fade-up", "stagger": True, "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="testimonial-wall",
        label="Testimonial wall",
        blurb="three customer quotes, staggered reveal",
        block_type="testimonial",
        content={
            "heading": "What customers say",
            "items": [
                {"quote": "Exactly what we needed — set up in an afternoon and it just works.", "author": "Jordan M.", "role": "Owner"},
                {"quote": "The team is responsive and the quality shows everywhere.", "author": "Sam R.", "role": "Operations lead"},
                {"quote": "We switched from a bigger name and haven't looked back.", "author": "Alex T.", "role": "Founder"},
            ],
        },
        design={
            "motion": {"effect": "fade-up", "stagger": True, "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="pricing-highlight",
        label="Highlighted pricing",
        blurb="three plans with the middle one highlighted",
        block_type="pricing",
        content={
            "heading": "Simple, honest pricing",
            "plans": [
                {"name": "Starter", "price": "19", "period": "mo",
                 "features": ["Core features", "Email support", "1 user"],
                 "cta": "Choose Starter", "ctaHref": "#contact", "highlighted": False},
                {"name": "Growth", "price": "49", "period": "mo",
                 "features": ["Everything in Starter", "Priority support", "5 users", "Advanced reports"],
                 "cta": "Choose Growth", "ctaHref": "#contact", "highlighted": True},
                {"name": "Scale", "price": "99", "period": "mo",
                 "features": ["Everything in Growth", "Dedicated manager", "Unlimited users"],
                 "cta": "Choose Scale", "ctaHref": "#contact", "highlighted": False},
            ],
        },
        design={
            "motion": {"effect": "fade-up", "stagger": True, "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "xl"},
        },
    ),
    SectionPreset(
        key="cta-band-bold",
        label="Bold CTA band",
        blurb="brand-colored call-to-action band with a springy entrance",
        block_type="cta",
        content={
            "heading": "Ready when you are",
            "subheading": "Start today — it takes less than five minutes.",
            "cta": "Get started",
            "ctaHref": "#contact",
        },
        design={
            "motion": {"effect": "scale-up", "easing": "spring"},
        },
    ),
    SectionPreset(
        key="faq-clean",
        label="Clean FAQ",
        blurb="narrow FAQ list with four starter questions",
        block_type="faq",
        content={
            "heading": "Frequently asked questions",
            "subheading": "",
            "items": [
                {"q": "How do I get started?", "a": "Reach out through the contact form and we'll take it from there."},
                {"q": "What does it cost?", "a": "See the pricing section above — no hidden fees."},
                {"q": "Can I cancel anytime?", "a": "Yes. There are no long-term contracts."},
                {"q": "Do you offer support?", "a": "Every plan includes support; response times vary by plan."},
            ],
        },
        design={
            "motion": {"effect": "fade", "easing": "gentle"},
            "layout": {"maxWidth": "narrow", "padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="logos-strip",
        label="Logo strip",
        blurb="compact social-proof strip of customer names/logos",
        block_type="logos",
        content={
            "heading": "Trusted by teams at",
            "items": [
                {"name": "Northwind"}, {"name": "Acme Co"}, {"name": "Globex"},
                {"name": "Initech"}, {"name": "Umbra Labs"},
            ],
        },
        design={
            "motion": {"effect": "fade", "easing": "gentle"},
            "layout": {"padTop": "sm", "padBottom": "sm"},
        },
    ),
    SectionPreset(
        key="features-grid",
        label="Feature grid",
        blurb="three-up feature cards with icons, staggered reveal",
        block_type="features",
        content={
            "heading": "Everything you need",
            "subheading": "The essentials, done well — nothing you don't.",
            "items": [
                {"icon": "✦", "title": "Fast to start", "body": "Up and running in minutes, not weeks."},
                {"icon": "◆", "title": "Built to last", "body": "Reliable, secure, and always improving."},
                {"icon": "▲", "title": "Real support", "body": "Talk to a human who actually knows the product."},
            ],
        },
        design={
            "motion": {"effect": "fade-up", "stagger": True, "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="bento-showcase",
        label="Bento showcase",
        blurb="asymmetric bento grid of five capability tiles",
        block_type="bento",
        content={
            "heading": "One platform, many wins",
            "subheading": "",
            "items": [
                {"icon": "★", "title": "The headline capability", "body": "Lead with your strongest feature here.", "span": "2"},
                {"icon": "◆", "title": "Second thing", "body": "Short and concrete."},
                {"icon": "✦", "title": "Third thing", "body": "Short and concrete."},
                {"icon": "▲", "title": "Fourth thing", "body": "Short and concrete."},
                {"icon": "●", "title": "Fifth thing", "body": "Short and concrete.", "span": "2"},
            ],
        },
        design={
            "motion": {"effect": "fade-up", "stagger": True, "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "xl"},
        },
    ),
    SectionPreset(
        key="split-checklist",
        label="Split with checklist",
        blurb="image + copy split section with three checkmark bullets",
        block_type="split",
        content={
            "eyebrow": "Why us",
            "heading": "The details make the difference",
            "body": "A short paragraph that earns the bullets below — specific, not salesy.",
            "bullets": ["No setup fees", "Cancel anytime", "Support that answers"],
            "cta": "Talk to us",
            "ctaHref": "#contact",
            "reverse": False,
        },
        design={
            "motion": {"effect": "slide-left", "easing": "gentle"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    SectionPreset(
        key="text-statement",
        label="Statement",
        blurb="single big centered statement with a soft blur-up reveal",
        block_type="text",
        content={
            "heading": "We believe good work speaks quietly and carries far.",
            "body": "",
        },
        design={
            "motion": {"effect": "blur-up", "easing": "gentle", "duration": 1100},
            "layout": {"maxWidth": "narrow", "align": "center", "padTop": "xl", "padBottom": "xl"},
        },
    ),
)

PRESETS_BY_KEY: dict[str, SectionPreset] = {p.key: p for p in SECTION_PRESETS}
