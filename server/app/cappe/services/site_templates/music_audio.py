"""music-audio — Reverb: a dark, atmospheric site for musicians, producers and studios."""
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, img, page, pic

REVERB = SiteTemplate(
    slug="reverb-music",
    name="Reverb — Musician & Studio",
    category="music-audio",
    description="A dark, atmospheric site for artists, producers and studios — releases, shows, merch and a mailing list.",
    tags=("blog", "store", "newsletter", "gallery", "contact"),
    sample_name="Reverb",
    theme={
        "mode": "dark",
        "colors": {
            "bg": "#0d0b12", "surface": "#17131f", "text": "#f3eefb", "muted": "#9d93b1",
            "border": "#272033", "brand": "#c084fc", "brandText": "#0d0b12", "accent": "#f472b6",
        },
        "fonts": {"heading": "Syne", "body": "Manrope"},
        "radius": "lg", "heroStyle": "image", "navStyle": "centered",
        "premium": True,
        "type": {"headingScale": 116, "headingWeight": 800, "heroAnim": "shimmer"},
    },
    pages=(
        page("Home", "home", 0, [
            {"type": "hero", "style": "image", "eyebrow": "New release out now",
             "heading": "Music you can feel in your chest.",
             "subheading": f"{BUSINESS_NAME} — replace this with a line about your sound and where to hear it.",
             "cta": "Listen", "ctaHref": "/p/music", "cta2": "Upcoming shows", "cta2Href": "/p/shows",
             **pic("image", "reverb-hero"),
             "_design": {"motion": {"effect": "fade-up", "easing": "gentle", "duration": 1200, "kenburns": True},
                         "layout": {"minHeight": "screen"}}},
            {"type": "posts", "heading": "Latest releases", "items": [
                {"date": "New", "title": "Your latest single", "excerpt": "A sentence about the track and a link to where it lives."},
                {"date": "Earlier", "title": "An EP or album", "excerpt": "What it's about, who played on it, where it was recorded."},
                {"date": "Catalogue", "title": "A collaboration or remix", "excerpt": "Replace these with your real discography."},
            ]},
            {"type": "gallery", "heading": "On stage & in the studio",
             "images": [
                 {"url": img("reverb-crowd")},
                 {"url": img("reverb-studio")},
                 {"url": img("reverb-vinyl")},
             ],
             "_design": {"motion": {"effect": "fade-up", "stagger": True}}},
            {"type": "newsletter", "heading": "Be first to hear it",
             "subheading": "New music, tour dates and the occasional demo. No spam."},
            {"type": "cta", "heading": "Book us for a show or a session.",
             "subheading": "Venues, festivals, private events and studio work.",
             "cta": "Get in touch", "ctaHref": "/p/contact"},
        ]),
        page("Music", "music", 1, [
            {"type": "hero", "style": "minimal", "heading": "Music",
             "subheading": "Everything released so far — and where to stream or buy it."},
            {"type": "posts", "items": [
                {"date": "Single", "title": "Track title", "excerpt": "Streaming links, credits and a line about the song."},
                {"date": "EP", "title": "Record title", "excerpt": "Tracklist highlights and where it was made."},
                {"date": "Album", "title": "Record title", "excerpt": "Replace with your own catalogue."},
            ]},
            {"type": "store", "heading": "Merch & music",
             "subheading": "Vinyl, shirts and downloads — straight from us."},
        ]),
        page("Shows", "shows", 2, [
            {"type": "hero", "style": "minimal", "heading": "Shows",
             "subheading": "Upcoming dates. Replace these with your real listings."},
            {"type": "posts", "items": [
                {"date": "Next month", "title": "City — Venue name", "excerpt": "Doors, support act and ticket link."},
                {"date": "Later", "title": "City — Festival name", "excerpt": "Stage and set time."},
                {"date": "Later", "title": "City — Venue name", "excerpt": "All ages / 18+ and ticket link."},
            ]},
            {"type": "cta", "heading": "Want us in your city?",
             "subheading": "Promoters and venues — we'd love to hear from you.",
             "cta": "Booking enquiries", "ctaHref": "/p/contact"},
        ]),
        page("Contact", "contact", 3, [
            {"type": "contact", "heading": "Bookings & press",
             "subheading": "Shows, sessions, sync and interviews.",
             "fields": ["name", "email", "message"]},
            {"type": "split", "eyebrow": "The studio",
             "heading": "Recording, mixing and production.",
             "body": "If you also run a studio or produce for other artists, describe your rooms, gear and rates here — or delete this section.",
             "bullets": ["Tracking & mixing", "Production & co-writing", "Remote sessions"],
             **pic("image", "reverb-studio")},
        ]),
    ),
)

TEMPLATES = (REVERB,)
