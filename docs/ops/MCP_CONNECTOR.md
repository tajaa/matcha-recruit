# Matcha MCP connector — research cards on the person's own Claude / ChatGPT plan

## Why this shape (policy, verified 2026-09-26)

The goal: when a person has Claude or ChatGPT, their kanban **research** cards run on *their* plan
instead of AutoPR's `gpt-5.6-luna` on our API key. AutoPR stays available as it was.

The only shape both vendors sanction for this is **Matcha as a remote MCP connector**:

- **Anthropic.** Consumer (Free/Pro/Max) OAuth tokens are for Claude Code and claude.ai only.
  Using them in any other product, the Agent SDK included, violates the consumer terms. So we
  must never spawn a user's `claude -p` from our app or hold their token.
  ([Claude Code authentication](https://code.claude.com/docs/en/authentication))
- **OpenAI.** Programmatic Codex use should authenticate with an API key. ChatGPT sign-in is
  documented for OpenAI's own clients, and third-party use of a user's plan through
  `codex app-server` is unconfirmed. ([Codex auth](https://learn.chatgpt.com/docs/auth))
- **Remote MCP connectors** are the sanctioned path on both sides:
  - claude.ai custom connectors run on every plan (Free is limited to one connector).
  - ChatGPT developer-mode apps run on Plus, Pro, Business, Enterprise and Education.
  - In both, the model runs on the person's plan and our server only exposes tools.

The invariants that keep this compliant:

1. Matcha never asks for, stores or proxies a Claude or OpenAI credential. The OAuth in this
   feature authenticates the person to **Matcha**, not the other way round.
2. In-app AI (Huume, pilots, AutoPR) stays on our own keys, separate from the connector.
3. Every tool call re-derives access from the token's user. Model-supplied ids are never trusted.

## Wire layout

All routes live on one origin: `MCP_PUBLIC_ORIGIN`, falling back to `APP_BASE_URL`.

| Path | What |
|---|---|
| `POST /api/mcp` | MCP Streamable HTTP, **stateless JSON** (fits nginx 90 s / CloudFront 60 s) |
| `GET /.well-known/oauth-protected-resource[/api/mcp]` | RFC 9728; `resource = <origin>/api/mcp` |
| `GET /.well-known/oauth-authorization-server[/api/oauth]` | RFC 8414; issuer = origin, endpoints under `/api/oauth` |
| `/api/oauth/authorize`, `/token`, `/register`, `/revoke` | MCP SDK handlers over `MatchaOAuthProvider` |
| `/oauth/consent?request=…` (SPA) | Consent page. Sends a logged-out visitor through `/login?next=` |
| `/api/matcha-work/connectors*` | Consent API, grants list and disconnect |
| `POST /api/matcha-work/projects/{p}/tasks/{t}/research-launch` | Returns the deep link (claude.ai / chatgpt.com `?q=`) or a `claude` command |

Code:

- `server/app/core/services/mcp_oauth.py` — the authorization server's storage and policy.
- `server/app/matcha/routes/mcp_connector/` — `server.py` assembles MCP and the OAuth routes;
  `research.py` holds the tools and their access rules.
- `server/app/matcha/routes/matcha_work/connectors.py` — the REST routes above.
- Clients: `client/src/work/pages/ConnectorConsent.tsx`,
  `work/components/shell/ProjectKanbanBoard/ResearchWithAssistant.tsx`, and Espresso's
  `TaskViewerSheet+Header.swift` (`researchWithAssistantControl`).

**Mounting.** `main.py` appends the connector routes before the root-level Cappe renderer, and
enters `session_manager.run()` inside the lifespan.

**nginx.** `/.well-known/oauth-*` is proxied to the backend. `/api/mcp` and `/api/oauth/*` ride
the ordinary `/api/` block.

## OAuth rules (MCP authorization spec 2025-11-25)

- **Registration.** Dynamic client registration (RFC 7591) is open. Redirect URIs must be `https`
  or `http` on loopback (Claude Code). Expected redirects:
  - `https://claude.ai/api/mcp/auth_callback`
  - `https://chatgpt.com/connector_platform_oauth_redirect`, or `https://chatgpt.com/connector/oauth/{id}`
- **Authorization.** PKCE S256 is required. Redirect URIs must match exactly. An unregistered
  redirect gets a 400 page and is never redirected to. A `resource` other than `<origin>/api/mcp`
  gets `invalid_target`.
- **Consent.** `authorize()` never mints a code. It signs the validated request into a 10-minute
  JWT handle (`type=mcp_oauth_consent`) and sends the browser to the consent page. Only the
  logged-in person's approval mints a code. The redirect carries `iss` (RFC 9207).
- **Codes.** Single use (a conditional `UPDATE … used_at`), PKCE-bound, valid for 10 minutes.
- **Tokens.**
  - Opaque (`mat_at_…` / `mat_rt_…`) and stored as sha256 only.
  - Access tokens last 1 h; refresh tokens last 30 d and rotate on every use.
  - Replaying a spent refresh token revokes the whole grant (`family_id`).
  - Audience-bound: the bearer middleware rejects any token whose `resource` is not the MCP URL.
- **Per-call checks.**
  - The user is active and not suspended, and their company isn't deleted
    (`load_current_user(check_session_revocation=False)`).
  - `require_feature("matcha_work")`.
  - A rate limit of 120 calls per minute per user.
- **Revocation.**
  - Disconnect in the UI (`DELETE /matcha-work/connectors/{client_id}`).
  - Any password change or reset (`revoke_user_grants`).
  - Not on logout: a browser logout advances `tokens_valid_after`, which connector tokens
    deliberately ignore.
- **DCR client secrets** are stored as issued, because the SDK compares them in constant time.
  They authenticate a client that still needs a person's consent plus a PKCE verifier. They are
  not bearer credentials for user data.

## Tools (v1)

| Tool | Annotation | Does |
|---|---|---|
| `list_research_cards` | read-only | Research cards in To do, Changes requested or In progress on boards the person can see (company or collaborator; sensitive project types hidden for employees) |
| `get_research_card` | read-only | Question, review note, inlined text attachments (≤64 KB), previous report, `report_contract` |
| `claim_research_card` | write, idempotent | To do / Changes requested → In progress, plus a note. Refused while the card is queued for AutoPR |
| `attach_research_report` | write, destructive (visible to teammates) | Validates the headings, uploads `research-report-<id8>-r<N>.md` with a provenance line, posts the note `"<card_note>\n\nReport attached: <file>"`, moves the card to Review |

**Report contract.** The report needs `### Summary`, `### Findings`, `### Recommendation` and
`### Sources`, in that order, and must be ≤200 KB. The card note is one line of ≤240 characters.
The filename and announcement match `publish-research.sh`, so Espresso renders the report as-is and
an AutoPR revision round finds it.

**AutoPR coexistence.** The bot only selects To do / Changes requested cards on its four watched
boards, so claiming (→ In progress) keeps it off.

## Connect / test

- **claude.ai:** Settings → Connectors → Add custom connector → `https://hey-matcha.com/api/mcp`,
  then complete the Matcha consent.
- **ChatGPT:** Settings → Apps & Connectors → Advanced → Developer mode, then create an app with
  the same URL and OAuth.
- **Claude Code:** `claude mcp add --transport http matcha https://hey-matcha.com/api/mcp`, then
  `/mcp` to log in.
- **Local:**
  1. Run `dev-remote.sh`.
  2. Start a public HTTPS tunnel to the backend (Claude and ChatGPT connect from their own clouds).
  3. Set `MCP_PUBLIC_ORIGIN=<tunnel>` and `MCP_APP_ORIGIN=http://localhost:5174` (the consent page
     is on Vite).
  4. Run `npx @modelcontextprotocol/inspector` against `<tunnel>/api/mcp`.
- **Deploy prerequisites:** apply migration `mcpconn01` (`migrate-dev.sh`, then `migrate-prod.sh`)
  and apply `deploy/nginx/matcha.conf` per `deploy/nginx/README.md`. The CloudFront origin gate
  already covers the new paths.

## Launch checklist (before listing publicly)

- Privacy-policy section on connector data: what the tools read and write, and token retention.
- Support contact and an icon.
- A security review of the OAuth surface.
- Anthropic connector-directory submission and an OpenAI app submission. Both are optional;
  custom connectors work without them.
- Open question: whether a `claude.ai/new?q=` / `chatgpt.com/?q=` chat enables the connector
  automatically. Verify on first real use. If not, the prompt tells the person to enable Matcha in
  the chat.
