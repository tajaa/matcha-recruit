# Agent Integration: API + Matcha Work + Standalone UI

## Context
The sandboxed agent (server/agent/) runs in an isolated Docker container with Gmail, Calendar, and Gemini capabilities. Two goals:
1. **Matcha Work integration** — agent email/calendar skills available inside the MW chat UI
2. **Standalone agent UI** — dedicated web UI at hey-matcha.com/agent/ for direct agent interaction

Both share the same agent HTTP API. Build in order: API → MW integration → standalone UI.

---

## Phase 1: Agent HTTP API — `server/agent/api.py` (new)

FastAPI app wrapping existing sandbox capabilities. Runs on port 9100.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check + gmail/calendar status |
| `/agent/chat` | POST | Chat with Gemini (reuses cli.py `_chat` logic) |
| `/agent/email/fetch` | POST | Fetch unread emails via SandboxedGmail |
| `/agent/email/draft` | POST | LLM-draft a reply + save to Gmail Drafts |
| `/agent/calendar/create` | POST | Create calendar event via SandboxedCalendar |

- Auth: `Authorization: Bearer {AGENT_API_SECRET}` middleware
- No persistent state — callers own conversation history
- Reuses existing Sandbox class and all its security constraints

**Supporting changes:**
- `server/agent/config.py` — add `api_secret: str` field
- `server/agent/requirements.txt` — add `fastapi`, `uvicorn`
- `server/agent/Dockerfile` — change entrypoint to `python -m agent.api`

## Phase 2: Docker Networking — `docker-compose.yml`

Agent joins both networks so backend can reach it:
```yaml
matcha-agent:
  networks:
    - agent-network   # isolation from Redis/DB
    - matcha-network   # reachable by backend
  environment:
    - AGENT_API_SECRET=${AGENT_API_SECRET}
    - GEMINI_API_KEY=${GEMINI_API_KEY}
  entrypoint: ["python", "-m", "agent.api"]
  healthcheck:
    test: ["CMD", "curl", "-sf", "http://localhost:9100/health"]
```

Agent still can't access DB/Redis — no credentials, no libraries, URL whitelist blocks it.

## Phase 3: Backend Agent Service — `server/app/core/services/agent_service.py` (new)

Thin async HTTP client (~100 lines):
- `chat(message, history)` → str
- `fetch_emails(max_results)` → list[dict]
- `draft_email_reply(email_id, instructions)` → dict
- `create_calendar_event(...)` → dict
- Uses `httpx.AsyncClient`, 60s timeout, bearer auth
- `is_configured` property for graceful degradation

Also add `agent_api_url` and `agent_api_secret` to `server/app/config.py`.

## Phase 4: Matcha Work Integration

**`server/app/matcha/services/matcha_work_ai.py`:**
- Add to `SUPPORTED_AI_SKILLS`: `agent_email`, `agent_calendar`
- Add to `SUPPORTED_AI_OPERATIONS`: `fetch_emails`, `draft_reply`, `create_event`
- Add agent skill descriptions to system prompt template

**`server/app/matcha/routes/matcha_work.py`:**
- In `_apply_ai_updates_and_operations`, add handler for `agent_*` skills
- `skill: agent_email, op: fetch_emails` → call agent → format email list as assistant message
- `skill: agent_email, op: draft_reply` → call agent → show draft preview
- `skill: agent_calendar, op: create_event` → call agent → show event confirmation
- Agent ops don't modify thread `current_state` — results are ephemeral assistant messages

## Phase 5: Standalone Agent UI

Simple chat-style web UI served by the agent's FastAPI:
- Static HTML/JS/CSS served from `server/agent/static/`
- Clean chat interface with message history
- Sidebar or buttons for: email fetch, draft, calendar, briefing
- Accessible at `hey-matcha.com/agent/` via nginx proxy to port 9100
- Auth: simple login page (AGENT_UI_PASSWORD env var or same shared secret)

---

## Security Model

| Concern | Protection |
|---|---|
| DB access | No DATABASE_URL, no asyncpg in agent |
| Redis access | No REDIS_URL, no redis lib in agent |
| App email (MailerSend) | Not available to agent; agent uses Gmail Drafts only, `/send` blocked |
| API auth | Shared secret bearer token, only backend knows it |
| Container | read-only rootfs, cap-drop ALL, no-new-privileges, 256MB limit |
| Outbound HTTP | SandboxedFetcher URL whitelist enforced |
| Gmail | Read + draft only, send explicitly blocked |

## Files to Create
- `server/agent/api.py` — HTTP API
- `server/app/core/services/agent_service.py` — backend proxy client
- `server/agent/static/` — standalone UI (Phase 5)

## Files to Modify
- `server/agent/config.py` — add api_secret
- `server/agent/requirements.txt` — add fastapi, uvicorn
- `server/agent/Dockerfile` — entrypoint change
- `docker-compose.yml` — networking + env vars + healthcheck
- `server/app/config.py` — add agent_api_url, agent_api_secret
- `server/app/matcha/services/matcha_work_ai.py` — add agent skills to prompt
- `server/app/matcha/routes/matcha_work.py` — handle agent operations
- `agent.sh` — update for API mode

## Verification
1. `curl http://localhost:9100/health` — agent API responds
2. `curl -H "Authorization: Bearer $SECRET" -X POST http://localhost:9100/agent/email/fetch` — returns emails
3. In Matcha Work, type "check my emails" — formatted email list appears
4. Type "draft a reply to #1 saying thanks" — draft preview, saved to Gmail Drafts
5. Visit hey-matcha.com/agent/ — standalone chat UI works
6. `docker exec matcha-agent python -c "import asyncpg"` — fails (no DB lib)
