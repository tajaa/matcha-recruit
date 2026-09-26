# Plan: in-app "Sign in with ChatGPT" for Espresso via a bundled Codex app-server

Status: proposed, 2026-09-26. The first milestone is a spike (below). Get approval before building the full feature.

Repo: `/Users/finch/Documents/github/matcha`. Read root `CLAUDE.md`, `server/CLAUDE.md`, `client/CLAUDE.md`
and `docs/ops/MCP_CONNECTOR.md` first.

## Goal

Espresso is the macOS SwiftUI app at `platforms/desktop/Espresso/` (Xcode project `Matcha.xcodeproj`, scheme
`Matcha`). Its users should be able to:

1. Click **Sign in with ChatGPT** inside Espresso. This is a real ChatGPT sign-in, and Codex owns the credentials.
2. On a kanban **research** card, click **Research with Codex**. The research runs locally through Codex on the
   user's own ChatGPT plan, and the report lands back on the card.

It must stay within vendor rules. This is the same pattern T3 Code uses: it builds on OpenAI's documented
`codex app-server` ("use the Codex app server to build custom clients that handle authentication…"). The Codex
CLI is Apache-2.0.

## Policy constraints (already researched; do not relitigate)

- **Do NOT impersonate Codex's OAuth client or hold OpenAI tokens in our code.** That is the OpenCode plugin
  approach, which is gray. Codex's own app-server performs the login and stores the credentials; Espresso only
  drives it over JSON-RPC.
- **Claude is out of scope for the local path.**
  - Claude Code is proprietary, so it can't be bundled.
  - The App Sandbox blocks running the user's own install.
  - Anthropic's policy on subscriptions in third-party tools is in flux: banned 2026-04-04, reversed 05-13,
    change paused 06-15.
  - Claude users go through the existing MCP connector (below).
- Our server never sees ChatGPT or Claude credentials.

## What already exists (PR #607, merged to main)

Matcha is a remote MCP connector with its own OAuth 2.1 authorization server.

**Server**

- `server/app/core/services/mcp_oauth.py` — `MatchaOAuthProvider`, over the MCP Python SDK 2.2 auth handlers:
  - dynamic client registration (DCR), PKCE S256, and a consent handle;
  - opaque tokens (`mat_at_…` / `mat_rt_…`) stored as sha256 and bound to `<origin>/api/mcp`;
  - refresh-token rotation with family revocation, and `revoke_user_grants` on password change.
- `server/app/matcha/routes/mcp_connector/server.py` — the MCP server:
  - mounted at `POST /api/mcp`, stateless JSON;
  - OAuth routes at `/api/oauth/*` plus `/.well-known/oauth-*`;
  - per-IP rate limits.
- `server/app/matcha/routes/mcp_connector/research.py` — the tools `list_research_cards`, `get_research_card`,
  `claim_research_card` and `attach_research_report`.
  - The report is published as `research-report-<id8>-r<N>.md`, plus a note and a move to Review. This is the
    same contract as AutoPR's `publish-research.sh`.
  - Required headings, in order: `### Summary`, `### Findings`, `### Recommendation`, `### Sources`.
- `server/app/matcha/routes/matcha_work/connectors.py`:
  - `GET /matcha-work/connectors` and `DELETE /matcha-work/connectors/{client_id}`;
  - consent `GET` and `POST`;
  - `POST /matcha-work/projects/{p}/tasks/{t}/research-launch` with `{client: claude|chatgpt|claude_code|codex}`,
    which returns a deep link or a shell command. `research.launch_prompt()` builds the prompt.
- `load_current_user(user_id, *, check_session_revocation=...)` was split out of `get_current_user` in
  `server/app/core/dependencies.py`. #608 later added a device-session argument, so read the current signature.
- Migration `mcpconn01` (tables `oauth_clients`, `oauth_authorization_codes`, `oauth_tokens`) is applied to
  dev. It is **not** applied to prod, and prod is not deployed yet.
- Dev env vars: `MCP_PUBLIC_ORIGIN` (defaults to `APP_BASE_URL`) and `MCP_APP_ORIGIN` (the SPA origin used for
  the consent page).

**Espresso**

- `Views/SettingsView.swift` → `ConnectorsSettingsTab`.
- `Views/MatchaWork/TaskViewer/TaskViewerSheet+Header.swift` → `researchWithAssistantControl`, with
  Claude/ChatGPT/Claude Code/Codex buttons. Today they only copy commands or open deep links.
- Models `MWConnectorsState` and `MWResearchLaunch` in `Models/MatchaWork/ProjectTaskModels.swift`; service
  calls in `Services/MatchaWorkService+Tasks.swift`.

**Web**

- `client/src/work/components/shell/AiConnectorsSettings.tsx`, `ResearchWithAssistant.tsx`, and
  `client/src/work/pages/ConnectorConsent.tsx`.

## Codex app-server protocol (probed against codex-cli 0.155.1)

**Launch and framing**

- `codex app-server` speaks newline-delimited JSON-RPC 2.0 over stdio.
- Handshake: `initialize {clientInfo:{name,title,version}}`, then send the `initialized` notification.
- Full schema: `codex app-server generate-json-schema --out <dir>`.

**Account**

- `account/read {}` → `{account: {type:"chatgpt", email, planType} | null, requiresOpenaiAuth}`.
  Verified: it returns `chatgpt` / `prolite` for the dev user.
- `account/login/start {type:"chatgpt", appBrand?: "codex"|"chatgpt"}` → `{type:"chatgpt", authUrl, loginId}`.
  Open `authUrl` in a browser, then await the `account/login/completed` notification `{loginId, success, error}`.
- Device-code variant: `{type:"chatgptDeviceCode"}` → `{verificationUrl, userCode}`.
- Also available: `account/login/cancel`, `account/logout`, `account/rateLimits/read`, `account/usage/read`.

**Work**

- `thread/start` takes `{config: {…overrides}, cwd, model, sandbox, approvalPolicy, developerInstructions, ephemeral}`.
- `turn/start` takes `{threadId, input: [UserInput], effort, model, outputSchema, sandboxPolicy, approvalPolicy}`.
- Notifications: `item/started`, `item/completed`, `item/agentMessage/delta`, `turn/completed`.
- `turn/interrupt` cancels a turn.

**MCP**

- `mcpServer/oauth/login {name, scopes?, threadId?}` → `{authorizationUrl}`.
- Also `mcpServerStatus/list` and `config/mcpServer/reload`.
- Codex config supports streamable-HTTP MCP servers via `mcp_servers.<name>.url` and
  `mcp_servers.<name>.bearer_token_env_var`.

The installed binary is about 229 MB, Mach-O arm64.

## Proposed design

### 1. Bundle Codex

Put the `codex` binary inside Espresso.app (e.g. `Contents/Helpers/codex`), code-signed with the app, and
include the Apache-2.0 LICENSE and NOTICE.

Espresso is App-Sandboxed (`Espresso/Matcha.entitlements`: app-sandbox, network client/server, user-selected
files, camera, mic). Sandboxed apps may only execute binaries inside their own bundle. Consequences:

- Codex's `CODEX_HOME` / `~` resolves to the container, `~/Library/Containers/<bundle>/Data`.
- Espresso therefore keeps its own ChatGPT login, separate from the user's terminal Codex. That's fine.
- Decide whether to ship universal (arm64 + x86_64) or arm64-only.

### 2. `CodexBridge` Swift actor (new file)

Adding a Swift file needs 4 hand edits to `project.pbxproj` (PBXBuildFile, PBXFileReference, group child,
Sources phase); run `plutil -lint` afterwards. The actor:

- spawns the app-server with `Process` and pipes;
- frames JSON lines, correlates request ids, and dispatches notifications;
- handles timeouts and restarts, and terminates the process on app quit.

### 3. Sign in with ChatGPT

- Lives in Settings → AI Connectors, and appears inline on a research card when the user isn't signed in.
- Status comes from `account/read`: "Signed in as <email> (<plan>)", plus Sign out.
- Sign-in: `account/login/start {type:"chatgpt"}` → `NSWorkspace.open(authUrl)` → await `account/login/completed`.
- Offer device-code login as a fallback.

### 4. Matcha tools inside Codex without a second consent

- A new server endpoint, e.g. `POST /matcha-work/connectors/local-token` (JWT auth), mints a short-lived
  `mcp_oauth` access token.
  - It's issued for a first-party client row (e.g. `espresso-local-codex`, seeded or created idempotently) and
    bound to the same resource.
- Espresso passes the token to Codex in an env var at process launch, with this per-thread config override:
  `{"mcp_servers":{"matcha":{"url":"<api>/mcp","bearer_token_env_var":"MATCHA_MCP_TOKEN"}}}`.
- This is a first-party token for our own server, not a vendor credential.
- Alternative: `mcpServer/oauth/login`, which goes through the normal consent page (one extra "Allow").

### 5. Research with Codex, per run

1. Mint the local token.
2. Start or reuse the app-server with the env set.
3. `thread/start`: ephemeral, `approvalPolicy: "never"`, sandbox `read-only`, web search enabled in config.
4. `turn/start` with the `research.launch_prompt()` text — fetched from `research-launch` with
   `client:"codex"`, or built client-side.
5. Stream progress (agent-message deltas, tool items) into the card UI.
6. Finish on `turn/completed`. The model itself calls `claim_research_card` and `attach_research_report`.

Handle cancel (`turn/interrupt`), the signed-out state, exhausted rate limits (`account/rateLimits/read`), and a
missing or crashed binary.

### 6. Keep the existing connector paths

The claude.ai and ChatGPT web deep links stay, for web users and for Claude.

## First milestone: spike (before building the full feature)

In a throwaway build, prove that:

- (a) the bundled `codex app-server` launches from sandboxed Espresso;
- (b) `account/login/start` works end to end from inside the sandbox — browser opens, callback completes, and
  `account/read` shows the account;
- (c) a turn can call a streamable-HTTP MCP server using a bearer token from an env var, and can use web search.
  Codex's own seatbelt sandboxing may fail inside the App Sandbox; try the sandbox modes and report.

Also report the app size impact, and whether this can ship in the App Store build or only in the Developer ID
build (`release.sh`). Present the findings, then a technical plan (signatures, file paths, endpoint shapes,
tests), and wait for approval.

## Repo rules (strict)

**Git**

- Never create, switch or delete branches without explicit permission — ask first.
- Re-check the current branch right before every commit. A prior commit accidentally landed on main.
- No Claude/AI attribution in commits or PRs: no Co-Authored-By, no "Generated with" footer.

**Database**

- Never run DDL, migrations or `alembic upgrade` without explicit approval.
- Dev Postgres is the local Docker container `matcha-postgres` (:5432). Prod is separate and needs approval for
  anything.

**Test data**

- Use only RFC 2606 reserved domains (`@example.com`, `*.test`).

**Checks**

- Server: `cd server && ./venv/bin/python -m pytest tests -q` — the full suite, about 10,141 passing at the time
  of writing. CI gates 80% diff coverage.
- Client: `cd client && npx tsc -p tsconfig.app.json --noEmit`. Bare `npx tsc --noEmit` checks nothing.
- Vitest needs `PATH=/opt/homebrew/bin:$PATH`.

**Espresso build**

- Build with `platforms/desktop/Espresso/run.sh`. It falls back to ad-hoc signing when the Apple Development
  cert is missing.
- That cert expired 2026-09-22, and the Xcode account login needed re-auth.

**Other**

- Background/cloud sessions: code and PR only. Never build, deploy or run `gh workflow`.
- Quote only test counts you actually measured.
