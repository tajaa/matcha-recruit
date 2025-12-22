"""Career page scraper service for finding job openings by industry."""

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel


class ScrapedJob(BaseModel):
    """A job listing scraped from a company career page."""
    title: str
    company_name: str
    location: Optional[str] = None
    department: Optional[str] = None
    apply_url: str
    source_url: str


class CareerPageResult(BaseModel):
    """Result from scraping a career page."""
    company_name: str
    career_url: str
    jobs: list[ScrapedJob]
    error: Optional[str] = None


class OpeningsSearchResult(BaseModel):
    """Complete result from an openings search."""
    jobs: list[ScrapedJob]
    sources_scraped: int
    sources_failed: int
    industry: str
    query: Optional[str] = None


# Common industry categories
INDUSTRIES = [
    "Technology",
    "Finance",
    "Healthcare",
    "E-commerce",
    "SaaS",
    "Fintech",
    "AI/ML",
    "Cybersecurity",
    "Biotech",
    "Clean Energy",
    "Education",
    "Media",
    "Gaming",
    "Real Estate",
    "Logistics",
]


async def search_career_pages(
    industry: str,
    api_key: str,
    query: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Use SearchAPI to find company career pages for a given industry.

    Returns a list of search results with URLs to career pages.
    """
    # Build search query to find career pages
    search_query = f"{industry} companies careers jobs hiring"
    if query:
        search_query = f"{query} {industry} careers jobs"

    # Add site filters to target career pages
    search_query += " (site:*/careers OR site:*/jobs OR site:greenhouse.io OR site:lever.co OR site:ashbyhq.com)"

    params = {
        "engine": "google",
        "q": search_query,
        "api_key": api_key,
        "num": limit,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://www.searchapi.io/api/v1/search",
            params=params
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get("organic_results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })

    return results


async def scrape_career_page(url: str, timeout: float = 15.0) -> CareerPageResult:
    """
    Fetch and parse a career page to extract job listings.

    Handles various career page formats:
    - Direct HTML job listings
    - Greenhouse
    - Lever
    - Ashby
    - Generic job boards
    """
    parsed = urlparse(url)
    company_name = _extract_company_name(url)

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
    except Exception as e:
        return CareerPageResult(
            company_name=company_name,
            career_url=url,
            jobs=[],
            error=str(e)
        )

    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # Try different parsing strategies based on the page structure
    if "greenhouse.io" in parsed.netloc:
        jobs = _parse_greenhouse(soup, url, company_name)
    elif "lever.co" in parsed.netloc:
        jobs = _parse_lever(soup, url, company_name)
    elif "ashbyhq.com" in parsed.netloc:
        jobs = _parse_ashby(soup, url, company_name)
    else:
        jobs = _parse_generic(soup, url, company_name)

    return CareerPageResult(
        company_name=company_name,
        career_url=url,
        jobs=jobs
    )


def _extract_company_name(url: str) -> str:
    """Extract company name from URL."""
    parsed = urlparse(url)

    # Handle job board URLs
    if "greenhouse.io" in parsed.netloc:
        # e.g., https://boards.greenhouse.io/company
        parts = parsed.path.strip("/").split("/")
        if parts:
            return parts[0].replace("-", " ").title()
    elif "lever.co" in parsed.netloc:
        # e.g., https://jobs.lever.co/company
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


def _parse_greenhouse(soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
    """Parse Greenhouse job board pages."""
    jobs = []

    # Greenhouse uses various class patterns
    job_elements = soup.select(".opening, .job-post, [class*='job'], [class*='opening']")

    for elem in job_elements[:50]:  # Limit to prevent over-scraping
        title_elem = elem.select_one("a, h2, h3, .opening-title, [class*='title']")
        if not title_elem:
            continue

        title = title_elem.get_text(strip=True)
        if len(title) < 3 or len(title) > 200:
            continue

        # Get link
        link_elem = elem.select_one("a[href]") or title_elem
        href = link_elem.get("href", "") if link_elem.name == "a" else ""
        if not href:
            continue

        apply_url = urljoin(base_url, href)

        # Try to get location/department
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
            source_url=base_url
        ))

    return jobs


def _parse_lever(soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
    """Parse Lever job board pages."""
    jobs = []

    # Lever uses .posting class
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
        location_elem = posting.select_one(".posting-categories .location, .sort-by-location")
        if location_elem:
            location = location_elem.get_text(strip=True)

        department = None
        dept_elem = posting.select_one(".posting-categories .department, .sort-by-team")
        if dept_elem:
            department = dept_elem.get_text(strip=True)

        jobs.append(ScrapedJob(
            title=title,
            company_name=company_name,
            location=location,
            department=department,
            apply_url=apply_url,
            source_url=base_url
        ))

    return jobs


def _parse_ashby(soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
    """Parse Ashby job board pages."""
    jobs = []

    # Ashby uses various class patterns
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
            source_url=base_url
        ))

    return jobs


def _parse_generic(soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
    """Parse generic career pages using common patterns."""
    jobs = []

    # Look for common job listing patterns
    job_patterns = [
        # Class-based selectors
        "[class*='job-listing']",
        "[class*='job-item']",
        "[class*='job-card']",
        "[class*='career-item']",
        "[class*='position-item']",
        "[class*='opening']",
        # ID-based selectors
        "[id*='job']",
        # Common list structures
        "li[class*='job']",
        ".jobs-list li",
        ".careers-list li",
        # Table-based
        "tr[class*='job']",
    ]

    seen_titles = set()

    for pattern in job_patterns:
        elements = soup.select(pattern)
        for elem in elements[:30]:
            # Find title - look for links or headings
            title_elem = elem.select_one("a, h2, h3, h4, [class*='title']")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)

            # Skip invalid titles
            if len(title) < 5 or len(title) > 200:
                continue
            if title.lower() in seen_titles:
                continue

            # Skip common non-job text
            skip_words = ["apply", "search", "filter", "sort", "view all", "see all", "load more"]
            if any(word in title.lower() for word in skip_words):
                continue

            # Find link
            link_elem = elem.select_one("a[href]")
            if not link_elem:
                link_elem = title_elem if title_elem.name == "a" else None

            if not link_elem:
                continue

            href = link_elem.get("href", "")
            if not href or href == "#":
                continue

            apply_url = urljoin(base_url, href)

            # Get location if available
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
                source_url=base_url
            ))

    # If no jobs found with specific selectors, try finding job-like links
    if not jobs:
        jobs = _parse_job_links(soup, base_url, company_name)

    return jobs


def _parse_job_links(soup: BeautifulSoup, base_url: str, company_name: str) -> list[ScrapedJob]:
    """Fallback: find links that look like job postings."""
    jobs = []
    seen_urls = set()

    # Job-related URL patterns
    job_url_patterns = [
        r"/jobs?/",
        r"/careers?/",
        r"/positions?/",
        r"/openings?/",
        r"/apply",
        r"/job-",
        r"/position-",
    ]

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Check if URL looks like a job posting
        is_job_url = any(re.search(pattern, href, re.I) for pattern in job_url_patterns)

        if not is_job_url:
            continue

        # Skip navigation/filter links
        if len(text) < 5 or len(text) > 150:
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)
        jobs.append(ScrapedJob(
            title=text,
            company_name=company_name,
            location=None,
            department=None,
            apply_url=full_url,
            source_url=base_url
        ))

    return jobs[:20]  # Limit fallback results


async def search_openings(
    industry: str,
    api_key: str,
    query: Optional[str] = None,
    max_sources: int = 10,
) -> OpeningsSearchResult:
    """
    Search for job openings by industry.

    1. Find career pages using SearchAPI
    2. Scrape each career page for job listings
    3. Return aggregated results
    """
    # Find career pages
    career_pages = await search_career_pages(industry, api_key, query, limit=max_sources)

    # Scrape each page concurrently with rate limiting
    all_jobs = []
    sources_scraped = 0
    sources_failed = 0

    # Process in batches to avoid overwhelming servers
    batch_size = 3
    for i in range(0, len(career_pages), batch_size):
        batch = career_pages[i:i + batch_size]
        tasks = [scrape_career_page(page["url"]) for page in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                sources_failed += 1
            elif isinstance(result, CareerPageResult):
                if result.error:
                    sources_failed += 1
                else:
                    sources_scraped += 1
                    all_jobs.extend(result.jobs)

        # Rate limit between batches
        if i + batch_size < len(career_pages):
            await asyncio.sleep(0.5)

    return OpeningsSearchResult(
        jobs=all_jobs,
        sources_scraped=sources_scraped,
        sources_failed=sources_failed,
        industry=industry,
        query=query
    )
