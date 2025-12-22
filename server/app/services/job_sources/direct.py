"""Direct company career page scraper."""

from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import JobSource, ScrapedJob


class DirectCompanyScraper(JobSource):
    """Scrapes jobs directly from company career pages."""

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
        timeout: float = 15.0,
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
        parsed = urlparse(url)

        # Extract company name if not provided
        if not company_name:
            company_name = self._extract_company_name(url)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                }
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
        except Exception:
            return []

        soup = BeautifulSoup(html, "lxml")

        # Try different parsing strategies based on the page structure
        if "greenhouse.io" in parsed.netloc:
            return self._parse_greenhouse(soup, url, company_name)
        elif "lever.co" in parsed.netloc:
            return self._parse_lever(soup, url, company_name)
        elif "ashbyhq.com" in parsed.netloc:
            return self._parse_ashby(soup, url, company_name)
        else:
            return self._parse_generic(soup, url, company_name)

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

    def _parse_greenhouse(self, soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
        """Parse Greenhouse job board pages."""
        jobs = []
        job_elements = soup.select(".opening, .job-post, [class*='job'], [class*='opening']")

        for elem in job_elements[:50]:
            title_elem = elem.select_one("a, h2, h3, .opening-title, [class*='title']")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if len(title) < 3 or len(title) > 200:
                continue

            link_elem = elem.select_one("a[href]") or title_elem
            href = link_elem.get("href", "") if link_elem.name == "a" else ""
            if not href:
                continue

            apply_url = urljoin(base_url, href)
            location = None
            department = None

            location_elem = elem.select_one(".location, [class*='location']")
            if location_elem:
                location = location_elem.get_text(strip=True)

            dept_elem = elem.select_one(".department, [class*='department']")
            if dept_elem:
                department = dept_elem.get_text(strip=True)

            jobs.append(ScrapedJob(
                title=title,
                company_name=company_name,
                location=location,
                department=department,
                apply_url=apply_url,
                source_url=base_url,
                source_name="direct",
            ))

        return jobs

    def _parse_lever(self, soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
        """Parse Lever job board pages."""
        jobs = []

        for posting in soup.select(".posting, .posting-title"):
            title_elem = posting.select_one("h5, .posting-name, a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if len(title) < 3:
                continue

            link_elem = posting.select_one("a.posting-title, a[href*='/jobs/']") or posting.find_parent("a")
            href = link_elem.get("href", "") if link_elem else ""
            if not href:
                continue

            apply_url = urljoin(base_url, href)
            location = None
            department = None

            location_elem = posting.select_one(".posting-categories .location, .sort-by-location")
            if location_elem:
                location = location_elem.get_text(strip=True)

            dept_elem = posting.select_one(".posting-categories .department, .sort-by-team")
            if dept_elem:
                department = dept_elem.get_text(strip=True)

            jobs.append(ScrapedJob(
                title=title,
                company_name=company_name,
                location=location,
                department=department,
                apply_url=apply_url,
                source_url=base_url,
                source_name="direct",
            ))

        return jobs

    def _parse_ashby(self, soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
        """Parse Ashby job board pages."""
        jobs = []

        for posting in soup.select("[class*='job'], [class*='posting'], [class*='position']"):
            title_elem = posting.select_one("a, h3, h4, [class*='title']")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if len(title) < 3 or len(title) > 200:
                continue

            link_elem = posting.select_one("a[href]") or title_elem
            href = link_elem.get("href", "") if link_elem.name == "a" else ""
            if not href:
                continue

            apply_url = urljoin(base_url, href)
            location = None

            location_elem = posting.select_one("[class*='location']")
            if location_elem:
                location = location_elem.get_text(strip=True)

            jobs.append(ScrapedJob(
                title=title,
                company_name=company_name,
                location=location,
                department=None,
                apply_url=apply_url,
                source_url=base_url,
                source_name="direct",
            ))

        return jobs

    def _parse_generic(self, soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
        """Parse generic career pages using common patterns."""
        jobs = []
        seen_titles = set()

        job_patterns = [
            "[class*='job-listing']",
            "[class*='job-item']",
            "[class*='job-card']",
            "[class*='career-item']",
            "[class*='position-item']",
            "[class*='opening']",
            "[id*='job']",
            "li[class*='job']",
            ".jobs-list li",
            ".careers-list li",
            "tr[class*='job']",
        ]

        for pattern in job_patterns:
            elements = soup.select(pattern)
            for elem in elements[:30]:
                title_elem = elem.select_one("a, h2, h3, h4, [class*='title']")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                if len(title) < 5 or len(title) > 200:
                    continue
                if title.lower() in seen_titles:
                    continue

                skip_words = ["apply", "search", "filter", "sort", "view all", "see all", "load more"]
                if any(word in title.lower() for word in skip_words):
                    continue

                link_elem = elem.select_one("a[href]")
                if not link_elem:
                    link_elem = title_elem if title_elem.name == "a" else None
                if not link_elem:
                    continue

                href = link_elem.get("href", "")
                if not href or href == "#":
                    continue

                apply_url = urljoin(base_url, href)
                location = None

                location_elem = elem.select_one("[class*='location'], [class*='place'], [class*='city']")
                if location_elem:
                    location = location_elem.get_text(strip=True)

                seen_titles.add(title.lower())
                jobs.append(ScrapedJob(
                    title=title,
                    company_name=company_name,
                    location=location,
                    department=None,
                    apply_url=apply_url,
                    source_url=base_url,
                    source_name="direct",
                ))

        return jobs
