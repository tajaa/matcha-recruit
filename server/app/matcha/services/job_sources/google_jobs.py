"""Google Jobs search via SearchAPI - direct job search with full control."""

from typing import Optional

import httpx

from .base import JobSource, ScrapedJob


class GoogleJobsScraper(JobSource):
    """Direct Google Jobs search via SearchAPI."""

    @property
    def source_id(self) -> str:
        return "google_jobs"

    @property
    def source_name(self) -> str:
        return "Google Jobs"

    @property
    def description(self) -> str:
        return "Search all jobs via Google Jobs - full control over query"

    @property
    def industries(self) -> list[str]:
        return []  # Works for any industry

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
        Search Google Jobs directly.

        Args:
            query: Job title, company, or any search terms
            location: City, state, or "remote"
            limit: Maximum results to return

        Returns:
            List of jobs from Google Jobs
        """
        if not self._api_key:
            print("[GoogleJobs] No API key set")
            return []

        if not query:
            query = "jobs"  # Default to general jobs search

        params = {
            "engine": "google_jobs",
            "q": query,
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
            print(f"[GoogleJobs] SearchAPI error: {e}")
            return []

        jobs = []
        for item in data.get("jobs", [])[:limit]:
            title = item.get("title", "")
            company = item.get("company_name", "")

            # Get apply link - try multiple fields
            apply_url = (
                item.get("apply_link") or
                item.get("sharing_link") or
                ""
            )

            # Get salary if available
            salary = None
            if item.get("salary"):
                salary = item.get("salary")
            elif item.get("detected_extensions", {}).get("salary"):
                salary = item["detected_extensions"]["salary"]

            # Get source (e.g., "via Indeed", "via LinkedIn")
            via = item.get("via", "")
            source_display = via.replace("via ", "") if via else "Google Jobs"

            jobs.append(ScrapedJob(
                title=title,
                company_name=company,
                location=item.get("location", None),
                department=None,
                salary=salary,
                apply_url=apply_url,
                source_url="https://www.google.com/search?q=jobs",
                source_name=source_display,
            ))

        return jobs
