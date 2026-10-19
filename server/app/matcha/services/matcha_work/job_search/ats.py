"""Public applicant-tracking-system APIs: Greenhouse, Lever, Ashby and Workable.

A posting's apply link often points at one of these. Their public job-board
APIs give the full description, structured pay (Lever `salaryRange`,
Greenhouse pay ranges, Ashby salary/bonus/equity components, Workable's
salary fields) and, for Greenhouse and Workable, the application's actual
questions. When no link leads to one, `find_on_board` looks for the job on the
employer's own Greenhouse, Lever or Ashby board, its name guessed from the
employer's.

The API URL is built from tokens matched out of the apply link (or the
employer's name) by a strict pattern, on a fixed host, and fetched through
`safe_fetch.fetch_public`. A posting page never chooses where the server
connects.
"""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlsplit

from app.core.services.safe_fetch import FetchedResponse, UnsafeURL, fetch_public
from app.matcha.services.matcha_work.agent_card.page_extract import plain_text

from . import comp as comp_mod
from . import normalize

logger = logging.getLogger(__name__)

MAX_BYTES = 3_000_000
TOTAL_TIMEOUT = 15.0
MAX_DESCRIPTION = 20_000
MAX_QUESTIONS = 40
# Each ATS by name, for a job read on it ("Read on Lever").
NAMES = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "workable": "Workable"}

_TOKEN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}"
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_GREENHOUSE_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/jobs/(?P<job>\d{{1,20}})/?$")
_LEVER_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/(?P<job>{_UUID})(?:/apply)?/?$")
_ASHBY_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/(?P<job>{_UUID})(?:/application)?/?$")
# apply.workable.com/{account}/j/{shortcode}/: the shortcode alone (/j/{shortcode})
# redirects to it, and a page read follows that redirect (`phases.read_job_page`).
_WORKABLE_PATH = re.compile(rf"^/(?P<board>{_TOKEN})/j/(?P<job>[0-9A-Za-z]{{6,20}})(?:/apply)?/?$")
_GH_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co": False, "jobs.eu.lever.co": True}

# Personal legal status: answered by the person, never drafted. A security
# clearance turns on citizenship and background, so it belongs here too.
_AUTHORIZATION = re.compile(
    r"authori[sz]ed to work|sponsor|visa|citizen|work permit|right to work|immigration|"
    r"clearance|ts/sci|top secret",
    re.I,
)
_DEMOGRAPHIC = re.compile(
    r"gender|race|racial|ethnic|veteran|disabilit|hispanic|latino|sexual orientation|pronoun|"
    r"transgender|date of birth|\bage\b",
    re.I,
)
_PROFILE_KEYS = {
    "first_name", "last_name", "preferred_name", "email", "phone", "resume", "resume_text",
    "cover_letter", "cover_letter_text", "linkedin_profile", "website",
    # Workable's standard fields
    "firstname", "lastname", "headline", "address", "summary", "avatar",
}


@dataclass(frozen=True)
class AtsRef:
    provider: str  # greenhouse | lever | ashby | workable
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
        if self.provider == "workable":
            return f"https://apply.workable.com/api/v2/accounts/{self.board}/jobs/{self.job_id}"
        return f"https://api.ashbyhq.com/posting-api/job-board/{self.board}?includeCompensation=true"

    def view(self) -> dict:
        return {"provider": self.provider, "board": self.board, "job_id": self.job_id, "eu": self.eu}

    def board_url(self) -> str:
        """The posting's page on its board, which `detect` reads back as
        this ref (a Greenhouse posting's own `absolute_url` may be the
        employer's careers site)."""
        if self.provider == "greenhouse":
            return f"https://job-boards.greenhouse.io/{self.board}/jobs/{self.job_id}"
        if self.provider == "lever":
            return f"https://jobs{'.eu' if self.eu else ''}.lever.co/{self.board}/{self.job_id}"
        if self.provider == "workable":
            return f"https://apply.workable.com/{self.board}/j/{self.job_id}/"
        return f"https://jobs.ashbyhq.com/{self.board}/{self.job_id}"


@dataclass
class AtsPosting:
    ref: AtsRef
    url: str | None
    title: str = ""
    company: str = ""  # Greenhouse names it; elsewhere the board's name stands in (`employer`)
    location: str = ""
    remote: bool | None = None
    description: str = ""
    findings: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)

    @property
    def employer(self) -> str:
        return self.company or self.ref.board


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
    if host == "apply.workable.com":
        match = _WORKABLE_PATH.match(path)
        if match and ".." not in match.group("board") and match.group("board").lower() not in ("api", "j"):
            return AtsRef("workable", match.group("board"), match.group("job"))
    return None


def html_to_text(value: str, limit: int = MAX_DESCRIPTION) -> str:
    """Plain text from (possibly HTML-escaped) HTML, one line per block."""
    return plain_text(html.unescape(value or ""), limit)


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
        company=normalize.clean_text(data.get("company_name"), 200),
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


_WORKABLE_TYPES = {"paragraph": "textarea", "file": "file", "boolean": "select", "dropdown": "select"}


def workable_questions(raw: Any) -> list[dict]:
    """The application form's fields, in Greenhouse's shape: the standard
    profile fields, the employer's own questions. Groups (education,
    experience) are the résumé's, not questions."""
    out = []
    for section in raw if isinstance(raw, list) else []:
        for item in (section.get("fields") or []) if isinstance(section, dict) else []:
            if not isinstance(item, dict) or item.get("type") == "group":
                continue
            key = normalize.clean_text(item.get("id"), 120)
            label = normalize.clean_text(item.get("label"), 300)
            if not key or not label:
                continue
            raw_type = str(item.get("type") or "")
            options = ["Yes", "No"] if raw_type == "boolean" else [
                normalize.clean_text(o.get("value"), 120)
                for o in item.get("options") or [] if isinstance(o, dict) and o.get("value")
            ][:40]
            field_type = _WORKABLE_TYPES.get(raw_type) or ("select" if options else "text")
            if raw_type == "dropdown" and item.get("singleOption") is False:
                field_type = "multi_select"
            out.append({
                "key": key, "label": label, "required": bool(item.get("required")),
                "type": field_type, "options": options,
                "kind": _question_kind(key, label, field_type),
            })
            if len(out) >= MAX_QUESTIONS:
                return out
    return out


def _workable_place(place: Any) -> str:
    if not isinstance(place, dict):
        return ""
    parts = [normalize.clean_text(place.get(k), 80) for k in ("city", "region", "country")]
    return ", ".join(p for p in parts if p)


def most_reads(ref: AtsRef) -> int:
    """At most the calls `fetch` makes for this posting (Workable's
    application questions are a second): what to reserve, not what it costs."""
    return 2 if ref.provider == "workable" else 1


def workable_published(data: dict) -> bool:
    """Not closed or archived."""
    return data.get("state") in (None, "published")


def parse_workable(ref: AtsRef, data: dict, form: Any = None) -> AtsPosting | None:
    """None for a posting no longer published (closed, archived)."""
    if not workable_published(data):
        return None
    url = f"https://apply.workable.com/{ref.board}/j/{ref.job_id}/"
    places = [_workable_place(p) for p in data.get("locations") or []]
    location = "; ".join(dict.fromkeys(p for p in places if p)) or _workable_place(data.get("location"))
    description = html_to_text("\n".join(
        str(data.get(k) or "") for k in ("description", "requirements", "benefits")))
    findings = comp_mod.from_workable(data, url=url)
    findings.extend(f for f in comp_mod.scan_text(description, origin="ats_api", url=url)
                    if f["component"] != "base" or not findings)
    workplace = str(data.get("workplace") or "").lower()
    return AtsPosting(
        ref=ref, url=url,
        title=normalize.clean_text(data.get("title"), 200),
        location=normalize.clean_text(location, 200),
        remote=True if data.get("remote") is True or workplace == "remote" else normalize.is_remote(location),
        description=description,
        findings=findings,
        questions=workable_questions(form),
    )


FetchFn = Callable[..., Awaitable[FetchedResponse]]


async def _answer(url: str, what: str, fetch_fn: FetchFn) -> tuple[Any, bool]:
    """A public ATS API's JSON answer, and whether the ATS answered for sure:
    its JSON, or a 404 or 410 (it has no such posting). A timeout, a refusal,
    a server error or a cut-off body is no answer either way."""
    try:
        response = await fetch_fn(url, max_bytes=MAX_BYTES, accept="application/json",
                                  total_timeout=TOTAL_TIMEOUT)
    except (UnsafeURL, TimeoutError, OSError) as exc:
        logger.info("ats fetch failed %s: %s", what, type(exc).__name__)
        return None, False
    except Exception:
        logger.warning("ats fetch failed %s", what, exc_info=True)
        return None, False
    if response.status in (404, 410):
        return None, True
    if response.status != 200 or response.truncated:
        return None, False
    try:
        return json.loads(response.body), True
    except ValueError:
        return None, False


async def _json(url: str, what: str, fetch_fn: FetchFn) -> Any:
    """A public ATS API's JSON answer; None when it is missing or unreadable."""
    return (await _answer(url, what, fetch_fn))[0]


@dataclass(frozen=True)
class AtsRead:
    """One posting read from its ATS. `closed` only when the ATS itself said
    so: it answered without the job (a 404, an Ashby board without it, a
    Workable job no longer published). A read that got no answer is neither."""
    posting: AtsPosting | None
    closed: bool = False


async def read(ref: AtsRef, *, more: Callable[[], bool] | None = None,
               fetch_fn: FetchFn = fetch_public) -> AtsRead:
    """The posting from its ATS's public API, as `fetch` reads it, and
    whether the ATS said it is closed."""
    data, answered = await _answer(ref.api_url(), f"{ref.provider} {ref.board}", fetch_fn)
    if not isinstance(data, dict):
        return AtsRead(None, closed=answered and data is None)
    posting: AtsPosting | None
    if ref.provider == "greenhouse":
        posting = parse_greenhouse(ref, data)
    elif ref.provider == "lever":
        posting = parse_lever(ref, data)
    elif ref.provider == "workable":
        if not workable_published(data):
            return AtsRead(None, closed=True)
        form = None
        if more is None or more():
            # The form is keyed by the shortcode alone; Workable's are global.
            form = await _json(f"https://apply.workable.com/api/v1/jobs/{ref.job_id}/form",
                               f"workable form {ref.board}", fetch_fn)
        posting = parse_workable(ref, data, form)
    else:
        posting = parse_ashby(ref, data)
        if posting is None and not isinstance(data.get("jobs"), list):
            return AtsRead(None)  # not a board's list of jobs: no answer about this one
    return AtsRead(posting, closed=posting is None or not posting.title)


async def fetch(ref: AtsRef, *, more: Callable[[], bool] | None = None,
                fetch_fn: FetchFn = fetch_public) -> AtsPosting | None:
    """The posting from its ATS's public API; None when it is gone or
    unreadable. One call, which the caller pays for first. Workable's
    application questions are a second, paid with `more()` when it is given:
    asked only for a posting still published, and left out when `more()`
    refuses."""
    return (await read(ref, more=more, fetch_fn=fetch_fn)).posting


# ── the employer's own board ─────────────────────────────────────────────────

_BOARD_LISTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
    "lever": "https://api.lever.co/v0/postings/{board}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true",
}


def board_names(company: str) -> list[str]:
    """Board names to try for an employer ("Prompt Therapy Solutions" ->
    prompttherapysolutions, prompt): its name run together, then its first
    word when that word is distinctive on its own. None for a listing that
    hides the employer."""
    if not normalize.named_employer(company):
        return []
    words = normalize.company_key(company).split()
    names = ["".join(words)]
    if len(words) > 1 and words[0].isalpha() and words[0] in normalize.name_words(company):
        names.append(words[0])
    return [n for n in dict.fromkeys(names) if re.fullmatch(_TOKEN, n)]


def _listed(provider: str, data: Any, title: str) -> dict | None:
    """The board's job with this title: the same title first, then a close one."""
    jobs = data if provider == "lever" else (data.get("jobs") if isinstance(data, dict) else None)
    key = "text" if provider == "lever" else "title"
    near = [j for j in (jobs if isinstance(jobs, list) else [])
            if isinstance(j, dict) and normalize.same_title(title, str(j.get(key) or ""))]
    same = [j for j in near if normalize.title_words(str(j.get(key) or "")) == normalize.title_words(title)]
    return (same or near or [None])[0]


async def find_on_board(company: str, title: str, *, take: Callable[[], bool],
                        fetch_fn: FetchFn = fetch_public) -> AtsPosting | None:
    """The job on the employer's own Greenhouse, Lever or Ashby board, for a
    posting whose links lead nowhere readable: each guessed board's public job
    list (`board_names`) searched for the title. Every call is paid for with
    `take()` first; None once one is refused."""
    for board in board_names(company):
        for provider, list_url in _BOARD_LISTS.items():
            if not take():
                return None
            data = await _json(list_url.format(board=board), f"{provider} board {board}", fetch_fn)
            job = _listed(provider, data, title) if data is not None else None
            job_id = str((job or {}).get("id") or "")
            if provider == "greenhouse" and re.fullmatch(r"\d{1,20}", job_id):
                if not take():
                    return None
                return await fetch(AtsRef("greenhouse", board, job_id), fetch_fn=fetch_fn)
            if provider == "lever" and re.fullmatch(_UUID, job_id):
                return parse_lever(AtsRef("lever", board, job_id.lower()), job)
            if provider == "ashby" and re.fullmatch(_UUID, job_id):
                return parse_ashby(AtsRef("ashby", board, job_id.lower()), data)
    return None
