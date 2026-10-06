"""Template imagery — prompts in code, hosted URLs in a sidecar JSON.

Templates used to ship `picsum.photos` links: random-subject stock that went
live on real customers' sites and depended on a third party staying up. Now
every image slot is a KEY in `IMAGE_MANIFEST`, resolved by `image_url()`:

- Once `scripts/cappe_template_imagery.py` has run, the key maps to a photo
  the product generated itself (same Gemini image model + S3/CloudFront
  storage the editor already uses for owners' images) and recorded in
  `imagery_urls.json` beside this module.
- Until then it maps to the self-hosted placeholder endpoint
  (`GET /api/cappe/templates/placeholder/{key}.svg`): a deterministic,
  brand-neutral gradient tile. Previews look designed, nothing is fetched from
  outside our own origin, and the drift test's "no third-party host" rule
  holds in both states.

The prompt lives here, next to the slot it fills, so the script never has to
guess what a slot is for and a reviewer can read the intended photo without
opening the generated asset.
"""
from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PLACEHOLDER_PATH = "/api/cappe/templates/placeholder/{key}.svg"
_URLS_FILE = pathlib.Path(__file__).with_name("imagery_urls.json")

# Aspect ratios the image model accepts; the renderer's slots map onto them.
HERO = "16:9"
WIDE = "4:3"
TALL = "3:4"
SQUARE = "1:1"

# Appended to every prompt — template imagery is always a background or a
# section photo, so it must never carry text, people's faces, or a watermark.
PROMPT_SUFFIX = (
    " Professional photography, natural light, shallow depth of field, muted editorial colour grade."
    " No text, no logos, no watermark, no readable signage, no recognisable faces."
)


@dataclass(frozen=True)
class ImageSpec:
    prompt: str
    aspect: str = WIDE


IMAGE_MANIFEST: dict[str, ImageSpec] = {
    # ── art-design · Atelier ────────────────────────────────────────────────
    "atelier-hero": ImageSpec("A designer's studio desk from above: sketchbook, pencils, swatch cards and a laptop on pale wood", WIDE),
    "atelier-work-1": ImageSpec("Close-up of printed brand identity stationery fanned on a concrete surface", SQUARE),
    "atelier-work-2": ImageSpec("A minimal website mockup displayed on a laptop beside a coffee cup", SQUARE),
    "atelier-work-3": ImageSpec("Hands arranging colour swatches and type specimens on a studio table", SQUARE),
    "atelier-work-4": ImageSpec("A packaging prototype in kraft card photographed on a seamless backdrop", SQUARE),
    "atelier-work-5": ImageSpec("A tablet showing an app interface wireframe, stylus resting beside it", SQUARE),
    "atelier-work-6": ImageSpec("Letterpress type blocks arranged in a wooden drawer", SQUARE),
    # ── food-drink · Saveur ─────────────────────────────────────────────────
    "saveur-hero": ImageSpec("A warm neighbourhood bistro interior at dusk: candlelit wooden tables, open kitchen glow", HERO),
    "saveur-plate-1": ImageSpec("A seasonal small plate of burrata and stone fruit on ceramic, overhead", SQUARE),
    "saveur-plate-2": ImageSpec("Fresh pasta being plated with brown butter and sage in a restaurant kitchen", SQUARE),
    "saveur-plate-3": ImageSpec("Two glasses of natural wine on a marble bar top with soft evening light", SQUARE),
    # ── food-drink · Maison ─────────────────────────────────────────────────
    "maison-hero": ImageSpec("A fine-dining room with linen-draped tables, low amber lighting and a single orchid per table", HERO),
    "maison-chef": ImageSpec("A chef's hands finishing a tasting-menu plate with tweezers, dark moody kitchen", WIDE),
    # ── wellness · Lumen ────────────────────────────────────────────────────
    "lumen-hero": ImageSpec("A calm sunlit room with a linen armchair, a notebook and a cup of tea on a side table", WIDE),
    "lumen-method": ImageSpec("An open planner with a pen and a small plant on a warm oak desk, morning light", WIDE),
    "lumen-about": ImageSpec("A quiet reading nook with soft cushions, a wool throw and a window onto greenery", WIDE),
    # ── photo-video · Onyx ──────────────────────────────────────────────────
    "onyx-hero": ImageSpec("Dramatic studio lighting: a single softbox beam across a dark backdrop with drifting haze", HERO),
    "onyx-bento-1": ImageSpec("An editorial fashion still life: draped silk and a vintage chair in a shaft of light", WIDE),
    "onyx-bento-2": ImageSpec("A tall portrait-format study of a figure in silhouette against a window, face unseen", TALL),
    "onyx-bento-3": ImageSpec("A luxury product photographed on black glass with a gold reflection", WIDE),
    "onyx-bento-4": ImageSpec("A travel landscape at blue hour: mountains and a lone road", WIDE),
    "onyx-bento-5": ImageSpec("An events venue at night lit by strings of warm bulbs, blurred motion", WIDE),
    "onyx-work-1": ImageSpec("A moody black-and-white architectural detail", SQUARE),
    "onyx-work-2": ImageSpec("A still life of fruit and pewter in Dutch-master lighting", SQUARE),
    "onyx-work-3": ImageSpec("Golden-hour field with long shadows", SQUARE),
    "onyx-work-4": ImageSpec("A close-up of hands holding a vintage film camera", SQUARE),
    "onyx-work-5": ImageSpec("Rain on a city window at night with bokeh lights", SQUARE),
    "onyx-work-6": ImageSpec("A minimalist interior with one chair and strong directional light", SQUARE),
    # ── fitness · Verve ─────────────────────────────────────────────────────
    "verve-coach": ImageSpec("A small-group strength class: kettlebells and a rack in a bright industrial gym, athletes seen from behind", WIDE),
    # ── professional · Praxis ───────────────────────────────────────────────
    "praxis-hero": ImageSpec("A bright modern studio workspace with a large whiteboard of sticky notes and two laptops", WIDE),
    "praxis-work-1": ImageSpec("Brand guideline pages spread across a conference table", WIDE),
    "praxis-work-2": ImageSpec("A tall phone mockup showing a clean product interface on a desk", TALL),
    "praxis-work-3": ImageSpec("A laptop with a dashboard of charts in a sunlit office", WIDE),
    "praxis-work-4": ImageSpec("A team's hands pointing at printed growth charts on a table", WIDE),
    # ── retail · Bloom ──────────────────────────────────────────────────────
    "bloom-maker": ImageSpec("A maker's workbench with hand-finished ceramics, twine and kraft packaging in soft daylight", WIDE),
    # ── beauty-grooming · Lumière ───────────────────────────────────────────
    "lumiere-hero": ImageSpec("A serene spa treatment room: linen-draped bed, eucalyptus, warm stone, soft window light", HERO),
    "lumiere-room": ImageSpec("A salon styling station with a round mirror, blush walls and brass fittings", WIDE),
    "lumiere-products": ImageSpec("Clean-skincare bottles arranged on a marble shelf with a sprig of eucalyptus", SQUARE),
    "lumiere-towels": ImageSpec("Rolled white towels, a candle and dried flowers on a wooden tray", SQUARE),
    "lumiere-nails": ImageSpec("A manicure station with pastel polish bottles and a small vase", SQUARE),
    # ── music-audio · Reverb ────────────────────────────────────────────────
    "reverb-hero": ImageSpec("A concert stage from the wings: haze, violet and magenta spotlights, a microphone stand in silhouette", HERO),
    "reverb-studio": ImageSpec("A recording studio desk with a mixing console, studio monitors and a warm lamp", WIDE),
    "reverb-crowd": ImageSpec("A crowd seen from behind at a club show, hands raised, purple stage glow", WIDE),
    "reverb-vinyl": ImageSpec("A turntable spinning a vinyl record, close-up with shallow focus", SQUARE),
    # ── events · Marquee ────────────────────────────────────────────────────
    "marquee-hero": ImageSpec("An outdoor evening reception under strings of warm festoon lights with long tables", HERO),
    "marquee-table": ImageSpec("A styled dinner table with candles, linen and seasonal flowers", WIDE),
    "marquee-dj": ImageSpec("A DJ booth with controllers and coloured light beams in a dark venue", WIDE),
    "marquee-dance": ImageSpec("A dance floor blurred with motion under a disco ball", WIDE),
    "marquee-cake": ImageSpec("A minimalist tiered celebration cake with fresh flowers on a stand", SQUARE),
    "marquee-tent": ImageSpec("A white marquee tent on a lawn at golden hour", WIDE),
    "marquee-bar": ImageSpec("A mobile cocktail bar with copper shakers and citrus garnish", SQUARE),
    # ── trades-home · Keystone ──────────────────────────────────────────────
    "keystone-hero": ImageSpec("A tidy tradesperson's van open at the back showing organised tools, parked outside a house", WIDE),
    "keystone-work": ImageSpec("A freshly finished kitchen renovation with new cabinetry and a tiled splashback", WIDE),
    # ── education · Chalk ───────────────────────────────────────────────────
    "chalk-hero": ImageSpec("A bright study desk with open textbooks, a notebook, pencils and a plant", WIDE),
    "chalk-classroom": ImageSpec("A small, sunlit classroom with a whiteboard and a round table, empty", WIDE),
    # ── pets · Pawprint ─────────────────────────────────────────────────────
    "pawprint-hero": ImageSpec("A cheerful dog-grooming salon: a freshly groomed golden retriever on a table, pastel walls", HERO),
    "pawprint-play": ImageSpec("Dogs playing in a sunny, fenced daycare yard", WIDE),
    "pawprint-cat": ImageSpec("A relaxed cat on a soft blanket in a bright boarding suite", SQUARE),
    "pawprint-bath": ImageSpec("A small dog wrapped in a towel after a bath, looking content", SQUARE),
    # ── automotive · Torque ─────────────────────────────────────────────────
    "torque-hero": ImageSpec("A clean modern auto workshop at night: a car on a lift under cool LED lighting", HERO),
    "torque-detail": ImageSpec("Close-up of a gloved hand polishing a glossy dark car bonnet with a microfibre cloth", WIDE),
}


def _load_urls() -> dict[str, str]:
    try:
        data = json.loads(_URLS_FILE.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("cappe templates: imagery_urls.json is unreadable; using placeholders", exc_info=True)
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}


IMAGE_URLS: dict[str, str] = _load_urls()


def image_url(key: str) -> str:
    """Hosted URL for a manifest key, else the placeholder tile.

    Raises for an unknown key — that is an authoring typo, and import-time is
    the cheapest place to find it (the drift test imports every template).
    """
    if key not in IMAGE_MANIFEST:
        raise KeyError(f"template image '{key}' is not in IMAGE_MANIFEST")
    return IMAGE_URLS.get(key) or PLACEHOLDER_PATH.format(key=key)
