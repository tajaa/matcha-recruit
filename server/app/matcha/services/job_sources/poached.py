"""Poached Jobs scraper - hospitality and food service jobs via SearchAPI."""

from typing import Optional

import httpx

from .base import JobSource, ScrapedJob


class PoachedJobsScraper(JobSource):
    """Scraper for Poached Jobs (hospitality/food service) using SearchAPI."""

    @property
    def source_id(self) -> str:
        return "poached"

    @property
    def source_name(self) -> str:
        return "Poached Jobs"

    @property
    def description(self) -> str:
        return "Hospitality and food service jobs - restaurants, bars, hotels, cafes"

    @property
    def industries(self) -> list[str]:
        return ["Food & Beverage", "Hospitality", "Retail"]

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
        Search Poached Jobs via SearchAPI Google Jobs.

        Args:
            query: Job title or keywords (e.g., "server", "chef", "manager")
            location: City or region (e.g., "Denver", "Portland")
            limit: Maximum results to return

        Returns:
            List of hospitality jobs
        """
        if not self._api_key:
            print("[Poached] No API key set")
            return []

        # Use user's query directly, or default to hospitality if none provided
        if query:
            search_query = query
        else:
            search_query = "restaurant OR hospitality OR food service"

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
            print(f"[Poached] SearchAPI error: {e}")
            return []

        jobs = []
        for item in data.get("jobs", [])[:limit]:
            # Filter for hospitality-related jobs
            title = item.get("title", "")
            company = item.get("company_name", "")

            jobs.append(ScrapedJob(
                title=title,
                company_name=company,
                location=item.get("location", None),
                department=None,
                salary=item.get("salary", None),
                apply_url=item.get("apply_link", "") or item.get("link", ""),
                source_url="https://poachedjobs.com",
                source_name="poached",
            ))

        return jobs
