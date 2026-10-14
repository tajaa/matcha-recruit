"""Public applicant-tracking-system APIs: Greenhouse, Lever and Ashby.

A posting's apply link often points at one of these. Their public job-board
APIs give the full description, structured pay (Lever `salaryRange`,
Greenhouse pay ranges, Ashby salary/bonus/equity components) and, for
Greenhouse, the application's actual questions.

The API URL is built from tokens matched out of the apply link by a strict
pattern, on a fixed host, and fetched through `safe_fetch.fetch_public`. A
posting page never chooses where the server connects.
"""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from app.core.services.safe_fetch import FetchedResponse, UnsafeURL, fetch_public

from . import comp as comp_mod
from . import normalize

logger = logging.getLogger(__name__)

MAX_BYTES = 3_000_000
TOTAL_TIMEOUT = 15.0
MAX_DESCRIPTION = 20_000
MAX_QUESTIONS = 40

_TOKEN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}"
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_GREENHOUSE_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/jobs/(?P<job>\d{{1,20}})/?$")
_LEVER_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/(?P<job>{_UUID})(?:/apply)?/?$")
_ASHBY_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/(?P<job>{_UUID})(?:/application)?/?$")
_GH_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co": False, "jobs.eu.lever.co": True}

_AUTHORIZATION = re.compile(
    r"authori[sz]ed to work|sponsor|visa|citizen|work permit|right to work|immigration", re.I,
)
_DEMOGRAPHIC = re.compile(
    r"gender|race|racial|ethnic|veteran|disabilit|hispanic|latino|sexual orientation|pronoun|"
    r"transgender|date of birth|\bage\b",
    re.I,
)
_PROFILE_KEYS = {
    "first_name", "last_name", "preferred_name", "email", "phone", "resume", "resume_text",
    "cover_letter", "cover_letter_text", "linkedin_profile", "website",
}


@dataclass(frozen=True)
class AtsRef:
    provider: str  # greenhouse | lever | ashby
    board: str
    job_id: str
    eu: bool = False

    def api_url(self) -> str:
        if self.provider == "greenhouse":
            return (f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs/{self.job_id}"
                    "?questions=true&pay_transparency=true")
        if self.provider == "lever":
            host = "api.eu.lever.co" if self.eu else "api.lever.co"
            return f"https://{host}/v0/postings/{self.board}/{self.job_id}"
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.board}?includeCompensation=true"

    def view(self) -> dict:
        return {"provider": self.provider, "board": self.board, "job_id": self.job_id, "eu": self.eu}


@dataclass
class AtsPosting:
    ref: AtsRef
    url: str | None
    title: str = ""
    location: str = ""
    remote: bool | None = None
    description: str = ""
    findings: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)


def detect(url: str | None) -> AtsRef | None:
    """The ATS posting an apply link points at, or None."""
    url = normalize.http_url(url)
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if host in _GH_HOSTS:
        if path.rstrip("/") == "/embed/job_app":
            query = parse_qs(parts.query)
            board = (query.get("for") or [""])[0]
            job = (query.get("token") or [""])[0]
            if re.fullmatch(_TOKEN, board) and re.fullmatch(r"\d{1,20}", job):
                return AtsRef("greenhouse", board, job)
            return None
        match = _GREENHOUSE_PATH.match(path)
        if match and ".." not in match.group("board"):
            return AtsRef("greenhouse", match.group("board"), match.group("job"))
        return None
    if host in _LEVER_HOSTS:
        match = _LEVER_PATH.match(path)
        if match and ".." not in match.group("board"):
            return AtsRef("lever", match.group("board"), match.group("job").lower(), eu=_LEVER_HOSTS[host])
        return None
    if host == "jobs.ashbyhq.com":
        match = _ASHBY_PATH.match(path)
        if match and ".." not in match.group("board"):
            return AtsRef("ashby", match.group("board"), match.group("job").lower())
    return None


def html_to_text(value: str, limit: int = MAX_DESCRIPTION) -> str:
    """Plain text from HTML, keeping line breaks between blocks."""
    if not value:
        return ""
    soup = BeautifulSoup(html.unescape(value), "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]


def _question_kind(key: str, label: str, field_type: str) -> str:
    """profile (filled from the person's details), file, authorization,
    demographic (never answered), or open (drafted)."""
    if field_type == "file":
        return "file"
    if _DEMOGRAPHIC.search(label):
        return "demographic"
    if _AUTHORIZATION.search(label):
        return "authorization"
    if key in _PROFILE_KEYS:
        return "profile"
    return "open"


_GH_TYPES = {
    "input_text": "text", "textarea": "textarea", "input_file": "file",
    "multi_value_single_select": "select", "multi_value_multi_select": "multi_select",
    "input_hidden": "hidden",
}


def greenhouse_questions(raw: Any) -> list[dict]:
    out = []
    for question in raw if isinstance(raw, list) else []:
        if not isinstance(question, dict):
            continue
        fields = [f for f in (question.get("fields") or []) if isinstance(f, dict)]
        if not fields:
            continue
        first = fields[0]
        field_type = _GH_TYPES.get(str(first.get("type") or ""), "text")
        if field_type == "hidden":
            continue
        if any(_GH_TYPES.get(str(f.get("type") or "")) == "file" for f in fields):
            field_type = "file"
        key = normalize.clean_text(first.get("name"), 120)
        label = normalize.clean_text(question.get("label"), 300)
        if not key or not label:
            continue
        options = [
            normalize.clean_text(v.get("label"), 120)
            for v in (first.get("values") or []) if isinstance(v, dict) and v.get("label")
        ][:40]
        out.append({
            "key": key, "label": label, "required": bool(question.get("required")),
            "type": field_type, "options": options,
            "kind": _question_kind(key, label, field_type),
        })
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def parse_greenhouse(ref: AtsRef, data: dict) -> AtsPosting:
    url = normalize.http_url(data.get("absolute_url"))
    location = data.get("location") if isinstance(data.get("location"), dict) else {}
    description = html_to_text(str(data.get("content") or ""))
    findings = comp_mod.from_greenhouse(data.get("pay_input_ranges"), url=url)
    findings.extend(comp_mod.scan_text(description, origin="ats_api", url=url))
    return AtsPosting(
        ref=ref, url=url,
        title=normalize.clean_text(data.get("title"), 200),
        location=normalize.clean_text(location.get("name"), 200),
        remote=normalize.is_remote(location.get("name")),
        description=description,
        findings=findings,
        questions=greenhouse_questions(data.get("questions")),
    )


def parse_lever(ref: AtsRef, data: dict) -> AtsPosting:
    url = normalize.http_url(data.get("hostedUrl"))
    categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    parts = [str(data.get("descriptionPlain") or "")]
    for item in data.get("lists") or []:
        if isinstance(item, dict):
            parts.append(normalize.clean_text(item.get("text"), 200))
            parts.append(html_to_text(str(item.get("content") or ""), 6_000))
    parts.append(str(data.get("additionalPlain") or ""))
    description = "\n".join(p for p in parts if p).strip()[:MAX_DESCRIPTION]
    findings = comp_mod.from_lever(data, url=url)
    findings.extend(f for f in comp_mod.scan_text(description, origin="ats_api", url=url)
                    if f["component"] != "base" or not any(x["component"] == "base" for x in findings))
    workplace = str(data.get("workplaceType") or "").lower()
    return AtsPosting(
        ref=ref, url=url,
        title=normalize.clean_text(data.get("text"), 200),
        location=normalize.clean_text(categories.get("location"), 200),
        remote=True if workplace == "remote" else normalize.is_remote(categories.get("location")),
        description=description,
        findings=findings,
    )


def parse_ashby(ref: AtsRef, data: dict) -> AtsPosting | None:
    for job in data.get("jobs") or []:
        if not isinstance(job, dict) or str(job.get("id") or "").lower() != ref.job_id:
            continue
        url = normalize.http_url(job.get("jobUrl"))
        description = str(job.get("descriptionPlain") or "")[:MAX_DESCRIPTION]
        if not description and job.get("descriptionHtml"):
            description = html_to_text(str(job["descriptionHtml"]))
        findings = comp_mod.from_ashby(job.get("compensation"), url=url)
        findings.extend(f for f in comp_mod.scan_text(description, origin="ats_api", url=url)
                        if not any(x["component"] == f["component"] for x in findings))
        return AtsPosting(
            ref=ref, url=url,
            title=normalize.clean_text(job.get("title"), 200),
            location=normalize.clean_text(job.get("location"), 200),
            remote=True if job.get("isRemote") else normalize.is_remote(job.get("location")),
            description=description,
            findings=findings,
        )
    return None


FetchFn = Callable[..., Awaitable[FetchedResponse]]


async def fetch(ref: AtsRef, *, fetch_fn: FetchFn = fetch_public) -> AtsPosting | None:
    """The posting from its ATS's public API; None when it is gone or unreadable."""
    url = ref.api_url()
    try:
        response = await fetch_fn(url, max_bytes=MAX_BYTES, accept="application/json",
                                  total_timeout=TOTAL_TIMEOUT)
    except (UnsafeURL, TimeoutError, OSError) as exc:
        logger.info("ats fetch failed %s %s: %s", ref.provider, ref.board, type(exc).__name__)
        return None
    except Exception:
        logger.warning("ats fetch failed %s %s", ref.provider, ref.board, exc_info=True)
        return None
    if response.status != 200 or response.truncated:
        return None
    try:
        data = json.loads(response.body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if ref.provider == "greenhouse":
        return parse_greenhouse(ref, data)
    if ref.provider == "lever":
        return parse_lever(ref, data)
    return parse_ashby(ref, data)
