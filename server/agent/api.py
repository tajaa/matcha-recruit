"""Agent HTTP API — FastAPI wrapper around the sandboxed agent.

Exposes chat, email, calendar, and briefing capabilities over HTTP.
Auth via shared secret bearer token.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from .config import load_config
from .sandbox import Sandbox, SandboxViolation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent.api")

# --- Globals set during lifespan ---
sandbox: Sandbox | None = None
config = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sandbox, config
    config = load_config()
    sandbox = Sandbox(config)
    logger.info(f"Agent API started. Workspace: {config.workspace_root}")
    logger.info(f"Gmail: {'enabled' if sandbox.gmail else 'disabled'}")
    logger.info(f"Calendar: {'enabled' if sandbox.calendar else 'disabled'}")
    yield
    logger.info("Agent API shutting down")


app = FastAPI(title="matcha-agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_SECRET = os.getenv("AGENT_API_SECRET", "")


def _check_auth(request: Request):
    """Verify bearer token. Skip auth if no secret is configured (dev mode)."""
    if not API_SECRET:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {API_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- Request/Response models ---

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    response: str


class EmailFetchRequest(BaseModel):
    max_results: int = 10


class EmailDraftRequest(BaseModel):
    email_id: str
    instructions: str = ""


class CalendarCreateRequest(BaseModel):
    email_id: str


class FeedItem(BaseModel):
    url: str
    name: str = ""


class ConfigUpdate(BaseModel):
    feeds: list[FeedItem] | None = None
    gmail_label_ids: list[str] | None = None
    gmail_max_emails: int | None = None
    rss_interests: str | None = None
    rss_max_entries_per_feed: int | None = None


# --- Routes ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gmail": sandbox.gmail is not None if sandbox else False,
        "calendar": sandbox.calendar is not None if sandbox else False,
        "llm": sandbox.llm is not None if sandbox else False,
    }


@app.post("/agent/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    _check_auth(request)

    context_parts = []
    if req.history:
        history = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'Agent'}: {m.get('content', '')}"
            for m in req.history[-20:]
        )
        context_parts.append(f"Conversation so far:\n{history}")

    context_block = "\n\n".join(context_parts)

    prompt = f"""You are a helpful assistant running inside a sandboxed agent.
You can discuss files, provide analysis, draft emails, and answer questions.
Be concise and direct.

{context_block}

User: {req.message}"""

    try:
        response = await sandbox.llm.generate(prompt)
        return ChatResponse(response=response)
    except SandboxViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/email/fetch")
async def email_fetch(req: EmailFetchRequest, request: Request):
    _check_auth(request)

    if sandbox.gmail is None:
        raise HTTPException(status_code=400, detail="Gmail not configured")

    try:
        max_emails = req.max_results or config.gmail_max_emails
        label_ids = config.gmail_label_ids if config.gmail_label_ids else None
        messages = await sandbox.gmail.fetch_unread(max_results=max_emails, label_ids=label_ids)
        if not messages:
            return {"emails": [], "message": "No unread emails"}

        emails = []
        for msg in messages:
            email = await sandbox.gmail.get_message(msg["id"])
            emails.append(email)

        return {"emails": emails}
    except SandboxViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Email fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/email/draft")
async def email_draft(req: EmailDraftRequest, request: Request):
    _check_auth(request)

    if sandbox.gmail is None:
        raise HTTPException(status_code=400, detail="Gmail not configured")

    try:
        email = await sandbox.gmail.get_message(req.email_id)

        prompt = f"""Draft a professional reply to this email. Do NOT include a subject line — just the body text.
{f"Instructions: {req.instructions}" if req.instructions else "Write a helpful, concise reply."}

Original email:
From: {email['from']}
Subject: {email['subject']}
Body:
{email['body'][:3000]}"""

        draft_body = await sandbox.llm.generate(prompt)

        result = await sandbox.gmail.create_draft(
            to=email["from"],
            subject=f"Re: {email['subject']}",
            body=draft_body,
        )

        return {
            "draft_id": result.get("id"),
            "to": email["from"],
            "subject": f"Re: {email['subject']}",
            "body": draft_body,
        }
    except SandboxViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Email draft error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/calendar/create")
async def calendar_create(req: CalendarCreateRequest, request: Request):
    _check_auth(request)

    if sandbox.calendar is None:
        raise HTTPException(status_code=400, detail="Calendar not configured")
    if sandbox.gmail is None:
        raise HTTPException(status_code=400, detail="Gmail not configured")

    try:
        import json
        import re

        email = await sandbox.gmail.get_message(req.email_id)

        prompt = f"""Extract meeting/event details from this email. Return ONLY valid JSON with these fields:
- "summary": event title (string)
- "start": start datetime in ISO 8601 with timezone, e.g. "2026-03-10T14:00:00-08:00" (string)
- "end": end datetime in ISO 8601 with timezone (string) — if duration not specified, default to 1 hour
- "description": brief description or agenda (string or null)
- "attendees": list of email addresses mentioned (list of strings, or empty list)
- "location": meeting location or video link if mentioned (string or null)

If you cannot determine a date/time, use your best guess based on context (today is {datetime.now().strftime('%Y-%m-%d')}).

Email:
From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}
Body:
{email['body'][:3000]}"""

        raw = await sandbox.llm.generate(prompt)

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            raise HTTPException(status_code=422, detail="Could not extract event details")

        event_data = json.loads(json_match.group())

        result = await sandbox.calendar.create_event(
            summary=event_data.get("summary", email["subject"]),
            start=event_data["start"],
            end=event_data["end"],
            description=event_data.get("description"),
            attendees=event_data.get("attendees") or None,
            location=event_data.get("location"),
        )

        return {
            "event": event_data,
            "link": result.get("htmlLink", ""),
        }
    except SandboxViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid event JSON from LLM")
    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agent/config")
async def get_config(request: Request):
    _check_auth(request)
    return {
        "feeds": [{"url": f["url"], "name": f.get("name", "")} for f in config.rss_feeds],
        "gmail_label_ids": config.gmail_label_ids,
        "gmail_max_emails": config.gmail_max_emails,
        "rss_interests": config.rss_interests,
        "rss_max_entries_per_feed": config.rss_max_entries_per_feed,
    }


@app.put("/agent/config")
async def update_config(req: ConfigUpdate, request: Request):
    _check_auth(request)

    import yaml

    if req.feeds is not None:
        feeds_list = [{"url": f.url, "name": f.name} for f in req.feeds]
        config.rss_feeds = feeds_list
        # Persist to feeds.yaml
        feeds_path = Path(config.workspace_root) / "feeds.yaml"
        with open(feeds_path, "w") as f:
            yaml.dump({"feeds": feeds_list}, f, default_flow_style=False)
        # Update fetcher whitelist with new feed URLs
        all_urls = [feed["url"] for feed in feeds_list]
        all_urls.extend(config.allowed_url_patterns)
        if config.gmail_enabled:
            all_urls.append("https://gmail.googleapis.com/gmail/v1/")
            all_urls.append("https://oauth2.googleapis.com/token")
            all_urls.append("https://www.googleapis.com/calendar/v3/")
        sandbox.fetcher._allowed = list(all_urls)
        logger.info(f"Updated feeds: {len(feeds_list)} feeds")

    if req.gmail_label_ids is not None:
        config.gmail_label_ids = req.gmail_label_ids
        logger.info(f"Updated Gmail labels: {config.gmail_label_ids}")

    if req.gmail_max_emails is not None:
        config.gmail_max_emails = max(1, min(req.gmail_max_emails, 100))
        logger.info(f"Updated Gmail max emails: {config.gmail_max_emails}")

    if req.rss_interests is not None:
        config.rss_interests = req.rss_interests
        logger.info(f"Updated RSS interests: {config.rss_interests}")

    if req.rss_max_entries_per_feed is not None:
        config.rss_max_entries_per_feed = max(1, min(req.rss_max_entries_per_feed, 50))
        logger.info(f"Updated max entries per feed: {config.rss_max_entries_per_feed}")

    return await get_config(request)


@app.post("/agent/briefing")
async def run_briefing(request: Request):
    _check_auth(request)

    from .skills import rss_briefing

    try:
        result = await rss_briefing.run(config, sandbox)
        if result:
            content = sandbox.fs.read(result)
            return {"file": result, "content": content}
        return {"file": None, "content": "No briefing generated"}
    except SandboxViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Briefing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Static UI ---
# In Docker: built Vite output copied to agent/static/
# Locally: run the Vite dev server instead (port 5176)
static_dir = Path(__file__).parent / "static"
if static_dir.is_dir() and (static_dir / "index.html").exists():
    # Serve Vite build assets if present
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    async def serve_ui(path: str = ""):
        return HTMLResponse((static_dir / "index.html").read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9100)
