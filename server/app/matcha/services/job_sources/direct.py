"""Direct company career page scraper using Jina AI Reader."""

from typing import Optional
from urllib.parse import urlparse

from ....core.services.jina_reader import JinaReaderClient
from ..job_extractor import JobExtractor, ExtractedJob
from .base import JobSource, ScrapedJob


class DirectCompanyScraper(JobSource):
    """Scrapes jobs directly from company career pages using Jina AI Reader."""

    def __init__(
        self,
        jina_api_key: str,
        gemini_api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
    ):
        """
        Initialize the scraper.

        Args:
            jina_api_key: Jina AI Reader API key
            gemini_api_key: Gemini API key (if not using Vertex)
            vertex_project: GCP project for Vertex AI (alternative to API key)
            vertex_location: Vertex AI location
        """
        self._jina_client = JinaReaderClient(api_key=jina_api_key)
        self._extractor = JobExtractor(
            api_key=gemini_api_key,
            vertex_project=vertex_project,
            vertex_location=vertex_location,
        )

    @property
    def source_id(self) -> str:
        return "direct"

    @property
    def source_name(self) -> str:
        return "Direct Company Page"

    @property
    def description(self) -> str:
        return "Scrape jobs directly from a company's career page"

    @property
    def industries(self) -> list[str]:
        return []  # Works for any industry

    async def search(
        self,
        query: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 50,
    ) -> list[ScrapedJob]:
        """Not used for direct scraping - use scrape_url instead."""
        return []

    async def scrape_url(
        self,
        url: str,
        company_name: Optional[str] = None,
        timeout: float = 30.0,
    ) -> list[ScrapedJob]:
        """
        Scrape jobs from a specific career page URL.

        Args:
            url: The career page URL to scrape
            company_name: Optional company name (extracted from URL if not provided)
            timeout: Request timeout in seconds

        Returns:
            List of jobs found on the page
        """
        # Extract company name if not provided
        if not company_name:
            company_name = self._extract_company_name(url)

        # Fetch page content as markdown via Jina Reader
        response = await self._jina_client.fetch_as_markdown(url, timeout=timeout)

        if response.error:
            print(f"[DirectCompanyScraper] Jina fetch failed for {url}: {response.error}")
            return []

        if not response.markdown or len(response.markdown.strip()) < 100:
            print(f"[DirectCompanyScraper] Empty or minimal content from {url}")
            return []

        # Extract jobs from markdown using LLM
        extracted = await self._extractor.extract_jobs(
            markdown=response.markdown,
            url=url,
        )

        # Convert ExtractedJob to ScrapedJob
        jobs = [
            ScrapedJob(
                title=job.title,
                company_name=company_name,
                location=job.location,
                department=job.department,
                apply_url=job.apply_url,
                source_url=url,
                source_name="direct",
            )
            for job in extracted
        ]

        return jobs

    def _extract_company_name(self, url: str) -> str:
        """Extract company name from URL."""
        parsed = urlparse(url)

        # Handle job board URLs
        if "greenhouse.io" in parsed.netloc:
            parts = parsed.path.strip("/").split("/")
            if parts:
                return parts[0].replace("-", " ").title()
        elif "lever.co" in parsed.netloc:
            parts = parsed.path.strip("/").split("/")
            if parts:
                return parts[0].replace("-", " ").title()
        elif "ashbyhq.com" in parsed.netloc:
            parts = parsed.path.strip("/").split("/")
            if parts:
                return parts[0].replace("-", " ").title()

        # Default: use domain name
        domain = parsed.netloc.replace("www.", "")
        domain = domain.split(".")[0]
        return domain.replace("-", " ").title()
