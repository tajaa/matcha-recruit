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
