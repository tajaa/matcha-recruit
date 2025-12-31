"""LLM-based job listing extractor from markdown content."""

import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from google import genai


@dataclass
class ExtractedJob:
    """A job extracted from markdown content."""

    title: str
    location: Optional[str]
    department: Optional[str]
    apply_url: str


JOB_EXTRACTION_PROMPT = """Extract job listings from this career page content.

PAGE URL: {url}

MARKDOWN CONTENT:
{markdown}

Extract ALL job listings found on this page. For each job, identify:
1. Job title (required)
2. Location (if mentioned, e.g., "San Francisco, CA", "Remote", "New York, NY")
3. Department/Team (if mentioned, e.g., "Engineering", "Sales", "Marketing")
4. Application URL or link path (construct from relative paths if needed)

Return ONLY a JSON object with this structure:
{{
    "jobs": [
        {{
            "title": "Job Title",
            "location": "City, State or Remote or null",
            "department": "Department name or null",
            "apply_path": "/careers/job-id or full URL"
        }}
    ]
}}

Rules:
- Include ALL distinct job positions found on the page
- Do NOT include navigation links, category headers, footer links, or non-job items
- If a job appears multiple times, include it only once
- If no jobs are found, return an empty jobs array
- For apply_path, use the most specific link to that job posting
- If no specific job link exists, use null for apply_path

Return ONLY the JSON object, no other text."""


class JobExtractor:
    """Extracts structured job listings from markdown using LLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
        model: str = "gemini-3-flash-preview",
    ):
        """
        Initialize the job extractor.

        Args:
            api_key: Gemini API key (if not using Vertex)
            vertex_project: GCP project for Vertex AI (alternative to API key)
            vertex_location: Vertex AI location
            model: Model to use for extraction
        """
        self.model = model

        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

    async def extract_jobs(
        self,
        markdown: str,
        url: str,
    ) -> list[ExtractedJob]:
        """
        Extract job listings from markdown content.

        Args:
            markdown: The markdown content of the career page
            url: The source URL (used for constructing apply URLs)

        Returns:
            List of ExtractedJob objects
        """
        # Truncate markdown if too long (LLM context limits)
        max_chars = 50000
        if len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n\n[Content truncated...]"

        prompt = JOB_EXTRACTION_PROMPT.format(
            url=url,
            markdown=markdown,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )

            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            jobs = []

            for job_data in result.get("jobs", []):
                title = job_data.get("title", "").strip()
                if not title or len(title) < 3:
                    continue

                # Construct full apply URL
                apply_path = job_data.get("apply_path")
                if apply_path:
                    if apply_path.startswith("http"):
                        apply_url = apply_path
                    else:
                        apply_url = urljoin(url, apply_path)
                else:
                    apply_url = url  # Fallback to page URL

                jobs.append(
                    ExtractedJob(
                        title=title,
                        location=job_data.get("location"),
                        department=job_data.get("department"),
                        apply_url=apply_url,
                    )
                )

            return jobs

        except json.JSONDecodeError as e:
            print(f"[JobExtractor] Failed to parse JSON: {e}")
            return []
        except Exception as e:
            print(f"[JobExtractor] Extraction failed: {e}")
            return []
