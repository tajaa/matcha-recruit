"""Job source scrapers for finding jobs from various platforms."""

from .base import JobSource, ScrapedJob, SourceInfo
from .direct import DirectCompanyScraper
from .poached import PoachedJobsScraper
from .wellfound import WellfoundScraper

__all__ = [
    "JobSource",
    "ScrapedJob",
    "SourceInfo",
    "DirectCompanyScraper",
    "PoachedJobsScraper",
    "WellfoundScraper",
]

# Available sources for the API
AVAILABLE_SOURCES = {
    "poached": PoachedJobsScraper,
    "wellfound": WellfoundScraper,
}
