"""Base class for job source scrapers."""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class ScrapedJob(BaseModel):
    """A job listing scraped from any source."""
    title: str
    company_name: str
    location: Optional[str] = None
    department: Optional[str] = None
    salary: Optional[str] = None
    apply_url: str
    source_url: str
    source_name: str  # e.g., "poached", "wellfound", "direct"


class SourceInfo(BaseModel):
    """Information about a job source."""
    id: str
    name: str
    description: str
    industries: list[str]  # What industries this source is good for


class JobSource(ABC):
    """Abstract base class for job source scrapers."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source (e.g., 'poached', 'wellfound')."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for this source."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this source provides."""
        pass

    @property
    @abstractmethod
    def industries(self) -> list[str]:
        """Industries this source is best for."""
        pass

    @abstractmethod
    async def search(
        self,
        query: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 50,
    ) -> list[ScrapedJob]:
        """
        Search for jobs from this source.

        Args:
            query: Optional search query (job title, keywords)
            location: Optional location filter
            limit: Maximum number of results to return

        Returns:
            List of scraped jobs
        """
        pass

    def get_info(self) -> SourceInfo:
        """Get information about this source."""
        return SourceInfo(
            id=self.source_id,
            name=self.source_name,
            description=self.description,
            industries=self.industries,
        )
