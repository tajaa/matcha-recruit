"""Wellfound (formerly AngelList) scraper - startup jobs via SearchAPI."""

from typing import Optional

import httpx

from .base import JobSource, ScrapedJob


class WellfoundScraper(JobSource):
    """Scraper for Wellfound/AngelList startup jobs using SearchAPI."""

    @property
    def source_id(self) -> str:
        return "wellfound"

    @property
    def source_name(self) -> str:
        return "Wellfound"

    @property
    def description(self) -> str:
        return "Startup jobs with salary and equity info - tech, product, engineering"

    @property
    def industries(self) -> list[str]:
        return ["Technology", "SaaS", "Fintech", "AI/ML", "E-commerce"]

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    def set_api_key(self, api_key: str):
        """Set the SearchAPI key."""
        self._api_key = api_key

    async def search(
        self,
        query: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 50,
    ) -> list[ScrapedJob]:
        """
        Search for startup jobs via SearchAPI Google Jobs.

        Args:
            query: Job title or keywords (e.g., "software engineer", "product manager")
            location: City or "remote"
            limit: Maximum results to return

        Returns:
            List of startup jobs
        """
        if not self._api_key:
            print("[Wellfound] No API key set")
            return []

        # Build search query for startup jobs
        search_parts = []
        if query:
            search_parts.append(query)
        else:
            search_parts.append("startup OR tech company")

        search_query = " ".join(search_parts)

        params = {
            "engine": "google_jobs",
            "q": search_query,
            "api_key": self._api_key,
        }

        if location:
            params["location"] = location

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://www.searchapi.io/api/v1/search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"[Wellfound] SearchAPI error: {e}")
            return []

        jobs = []
        for item in data.get("jobs", [])[:limit]:
            title = item.get("title", "")
            company = item.get("company_name", "")

            jobs.append(ScrapedJob(
                title=title,
                company_name=company,
                location=item.get("location", None),
                department=None,
                salary=item.get("salary", None),
                apply_url=item.get("apply_link", "") or item.get("link", ""),
                source_url="https://wellfound.com",
                source_name="wellfound",
            ))

        return jobs
