"""What a story is about. One topic per story; a magazine lists up to five.
The keys are stable (they are stored and appear in `/topics/<key>`); the
labels are what readers see."""
from __future__ import annotations

from typing import Optional

TOPICS: dict[str, str] = {
    "fashion": "Fashion",
    "style": "Style",
    "beauty": "Beauty",
    "culture": "Culture",
    "art": "Art",
    "photography": "Photography",
    "design": "Design",
    "architecture": "Architecture",
    "music": "Music",
    "film": "Film",
    "books": "Books",
    "food": "Food & drink",
    "travel": "Travel",
    "city": "City life",
    "nature": "Nature",
    "environment": "Environment",
    "politics": "Politics",
    "world": "World",
    "society": "Society",
    "science": "Science",
    "tech": "Technology",
    "sports": "Sports",
    "wellness": "Wellness",
    "history": "History",
    "essays": "Essays",
}


def normalize_topic(value: Optional[str]) -> Optional[str]:
    """A known topic key, or None for empty/unknown input."""
    key = (value or "").strip().lower()
    return key if key in TOPICS else None


def topic_label(key: Optional[str]) -> str:
    return TOPICS.get(key or "", "")


# "Stock this topic": a few searches per topic, tried in order until enough
# pictures are found. Openverse's photographs carry most topics; the museums
# and NASA are where history, art and science look their best.
TOPIC_QUERIES: dict[str, tuple[tuple[str, str], ...]] = {
    "fashion": (("openverse", "street fashion"), ("openverse", "runway fashion"), ("met", "fashion plate")),
    "style": (("openverse", "street style portrait"), ("openverse", "vintage clothing")),
    "beauty": (("openverse", "makeup portrait"), ("openverse", "hair salon")),
    "culture": (("openverse", "festival crowd"), ("smithsonian", "celebration")),
    "art": (("met", "painting"), ("smithsonian", "painting"), ("openverse", "art gallery")),
    "photography": (("openverse", "film photography"), ("smithsonian", "photograph portrait")),
    "design": (("openverse", "interior design"), ("met", "textile pattern")),
    "architecture": (("openverse", "modern architecture"), ("met", "architecture drawing")),
    "music": (("openverse", "concert stage"), ("openverse", "musician portrait")),
    "film": (("openverse", "cinema"), ("openverse", "film set")),
    "books": (("openverse", "bookshop"), ("met", "illuminated manuscript")),
    "food": (("openverse", "street food"), ("openverse", "farmers market")),
    "travel": (("openverse", "travel landscape"), ("openverse", "old town street")),
    "city": (("openverse", "city street night"), ("openverse", "urban skyline")),
    "nature": (("openverse", "forest landscape"), ("nasa", "earth from space")),
    "environment": (("nasa", "earth observatory"), ("openverse", "climate protest")),
    "politics": (("openverse", "protest march"), ("openverse", "parliament building")),
    "world": (("openverse", "market crowd"), ("nasa", "earth at night")),
    "society": (("openverse", "community gathering"), ("smithsonian", "people portrait")),
    "science": (("nasa", "laboratory"), ("nasa", "nebula"), ("smithsonian", "scientific instrument")),
    "tech": (("openverse", "technology workspace"), ("nasa", "rocket launch")),
    "sports": (("openverse", "sports action"), ("openverse", "stadium crowd")),
    "wellness": (("openverse", "yoga outdoors"), ("openverse", "running trail")),
    "history": (("met", "historical portrait"), ("smithsonian", "historic photograph")),
    "essays": (("openverse", "quiet room window light"), ("met", "landscape painting")),
}
