"""Job source scrapers for finding jobs from various platforms."""

from .base import JobSource, ScrapedJob, SourceInfo
from .direct import DirectCompanyScraper
from .google_jobs import GoogleJobsScraper
from .poached import PoachedJobsScraper
from .wellfound import WellfoundScraper

__all__ = [
    "JobSource",
    "ScrapedJob",
    "SourceInfo",
    "DirectCompanyScraper",
    "GoogleJobsScraper",
    "PoachedJobsScraper",
    "WellfoundScraper",
]

# Available sources for the API
AVAILABLE_SOURCES = {
    "google_jobs": GoogleJobsScraper,
    "poached": PoachedJobsScraper,
    "wellfound": WellfoundScraper,
}
