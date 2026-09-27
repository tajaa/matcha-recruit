# Espresso bundled Codex app-server spike — 2026-09-26

Status at spike handoff: **partially proven**. The native integration worked for login, authenticated MCP transport, and live web search. Successful Matcha card retrieval was blocked by an existing connector SQL defect. The user subsequently approved implementation on a new branch and a PR; the implementation addendum below records that work and its remaining acceptance checks.

## Scope and environment

- Started on `main` at `600fa72`. During the spike the checkout advanced externally to `1cc90a9`; the Espresso and connector surfaces used here did not change between those commits. No branch operations, commits, pushes, deployments, or schema changes were performed.
- The pre-existing untracked root `package-lock.json` was left untouched.
- macOS 26.6.2, arm64; installed `codex-cli 0.155.1`.
- First built the real Espresso target with `platforms/desktop/Espresso/run.sh build`.
- Copied that Xcode project and its source trees into `/private/tmp/espresso-codex-spike`. In the copy only, replaced `App/MatchaApp.swift` with a minimal SwiftUI spike window and `Process`/stdio bridge. This is the actual Espresso target, frameworks and App Sandbox entitlements, with a temporary entry point; it does **not** validate the production Settings/card UI.
- Used bundle ID `com.matchawork.espresso-codex-spike` to isolate storage. `CODEX_HOME` was explicitly set to its container's `Library/Application Support/CodexSpike`; credentials were managed by Codex with `cli_auth_credentials_store="file"`. No terminal Codex credentials were copied or inspected.
- The bridge had a temporary loopback controller. This is test machinery, not a proposed production listener; production should use private pipes directly.
- Used the running local dev API at `http://localhost:8001/api/mcp`. With explicit user approval, created one temporary OAuth client and one 30-minute `kanban:read` access token for the existing `maria.chen@example.com` dev account. No refresh token; no research-card mutations. The token was passed only in `MATCHA_MCP_TOKEN`, never in the prompt.

## Measured results

| Check | Result | Evidence |
|---|---|---|
| Bundled app-server starts inside App Sandbox | Pass | `Process` launched `Contents/Helpers/codex`; `initialize` returned version 0.155.1 and the isolated container path. A native read of the repository's `CLAUDE.md` outside the container was denied. |
| Browser login via `account/login/start` | Pass | Initially `account:null`; `{type:"chatgpt"}` returned `loginId`/`authUrl`; `NSWorkspace.open` returned true; the user completed login; `account/login/completed` returned `success:true`. |
| Account read and persistence | Pass | `account/read` returned `type:"chatgpt", planType:"prolite"`; persisted through app/server restart. Email redacted from evidence. |
| Environment bearer and streamable-HTTP MCP | Pass at transport/auth level | `mcpServerStatus/list` reported Matcha `runtimeStatus:"connected"`, `authStatus:"bearerToken"`, and `list_research_cards`. An actual model turn called the tool with `limit:1`. |
| Successful Matcha card retrieval | **Blocked** | The authenticated call reached Matcha's tool, then returned `Error executing tool list_research_cards`. Backend traceback identifies a nonexistent column, detailed below. |
| Live web search in the same turn | Pass | `web_search:"live"`; completed `webSearch` item for Apple App Sandbox inheritance with actual source results. The turn completed normally while reporting the MCP tool failure. |
| Logout and grant cleanup | Pass | `account/logout` followed by `account/read` returned `account:null`. Revocation updated the sole access-token row; zero active tokens remained; reuse of the old bearer returned HTTP 401. Spike app/server stopped. |

The signed-in turn used the runtime's default model, `gpt-6-astra`; no API key was supplied. This proves the user's ChatGPT login path, not an API-key fallback. `turn/completed` alone must not be treated as research success: the measured turn completed even though its MCP item failed.

### Required packaging correction

Bundling only `codex` was insufficient for this installed distribution. Its first model turn failed to execute tools because `Contents/Helpers/codex-code-mode-host` was missing. After bundling and signing that sibling executable, both the real MCP call and web search ran.

Both helper executables were signed with exactly these App Sandbox entitlements:

```xml
<key>com.apple.security.app-sandbox</key><true/>
<key>com.apple.security.inherit</key><true/>
```

The parent retains Espresso's current App Sandbox and network client/server entitlements. `codesign --verify --deep --strict` passed. No sandbox entitlement was removed.

The initial attempt to add Hardened Runtime to the ad-hoc Debug parent failed at launch: dyld rejected `Espresso.debug.dylib` because of signing/team identity validation. Restoring the baseline Debug signing options allowed launch. This is a **release validation gap**, not evidence that a correctly signed Developer ID archive fails. No distribution archive, notarization, or App Store upload was attempted.

### Sandbox-mode matrix

A model turn requested only `/usr/bin/true` in each mode. The outcomes were independently confirmed using app-server `command/exec`, which returned the actual exit code and stderr:

| Codex mode inside Espresso's App Sandbox | Local command result |
|---|---|
| `read-only` / `readOnly` | Exit 71: `sandbox-exec: sandbox_apply: Operation not permitted` |
| `workspace-write` / `workspaceWrite` | Exit 71: same nested sandbox failure |
| `danger-full-access` / `dangerFullAccess` | Exit 0 |

The last setting removes Codex's additional command sandbox; it does not remove the inherited macOS App Sandbox. It was a diagnostic, not the recommended research configuration. The MCP + web turn succeeded in `read-only` without local command execution. Keep the research flow read-only and disable shell execution; do not switch all research runs to full access to hide the nested-sandbox failure.

The app-server also repeatedly logged `failed to refresh available models: timeout waiting for child process to exit`, adding roughly five-second delays at multiple steps. It still completed inference and search. The responsible child operation was not isolated; startup/catalog latency remains a release blocker to investigate.

### Confirmed connector blocker

`server/app/matcha/routes/mcp_connector/research.py:166` selects `t.autopr_run_requested_at` in `list_research_cards`; `_load_card` does the same at line 96. Dev's `mw_tasks` has no such column. The local migration heads include `mcpconn01`.

This is **not** a reason to add a column or run migrations. The existing task service derives that field from `mw_task_history`: see the `autopr_run` lateral join around `server/app/matcha/services/matcha_work/project_task_service.py:1828`. It filters requests by TTL and subsequent claim/cancel events. Connector reads need to reuse the same semantics. `_load_card` feeds get, claim, publish and the REST research-launch path, so the blocker extends beyond list.

The connector's 69 unit tests passed, but their `QueryConn` fixtures fabricate `autopr_run_requested_at`; they never prepare the SQL against the real schema. Add a focused query/schema contract regression and an explicitly opt-in, read-only dev check. Preserve tenant/collaborator filters and AutoPR cancellation/claim/TTL behavior when fixing it. No fix was applied in this spike.

### Size and architecture

Measured logical file sizes, excluding duplicate symlink targets:

| Artifact | Bytes | Decimal MB |
|---|---:|---:|
| Installed `codex`, before re-signing | 228,803,200 | 228.80 |
| Bundled, re-signed `codex` | 227,475,456 | 227.48 |
| Bundled, re-signed `codex-code-mode-host` | 62,439,312 | 62.44 |
| Throwaway Debug app before helpers | 126,255,185 | 126.26 |
| Throwaway Debug app with both helpers | 416,170,530 | 416.17 |
| App increase | 289,915,345 | 289.92 |

Deflate level-6 compression of the two helper files totals 111,504,964 bytes (~111.50 MB). This is a payload estimate, not a measured App Store download or notarized archive size. License/NOTICE files and any additionally required resources are not included. `lipo -info` confirms the tested `codex` is arm64-only. Intel and universal builds were not tested; do not advertise x86_64 support until a matching distribution is bundled and tested.

## Distribution conclusion

There is no demonstrated App Sandbox obstacle to a **research-only** client that uses bundled helpers, Codex-managed login, remote MCP, and web search. The experiment does **not** establish App Store acceptance or a shippable Developer ID artifact.

Apple documents inherited sandbox helpers, and App Review requires self-contained bundles, sandboxing, and restrictions on downloaded/executed code and independent updating. Keep all required executable code in the signed bundle, disable helper self-update behavior, and avoid a general-purpose downloaded-code/shell feature in the research path. Review the exact pinned release's resources, dependencies, LICENSE and NOTICE before distribution. [Sandbox inheritance](https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html), [App Review Guidelines §§2.4.5, 2.5.1–2.5.2](https://developer.apple.com/app-store/review/guidelines/).

Recommendation: validate a correctly signed Hardened Runtime Developer ID build first through `release.sh`, once signing is available; then validate the App Store archive independently. Do not promise “App Store supported,” or conclude “Developer ID only,” from this Debug experiment. Both channels remain unverified.

## Proposed implementation after approval

### 1. Finish the spike blockers first

- Fix the two connector SQL reads using the task-history-derived AutoPR state; add the regression described above and repeat a successful native read-only MCP turn.
- Isolate the model-catalog child-process timeout in the container.
- Test research with shell tools disabled, including hostile card/web text asking for local files or commands. Explicitly disable unrelated account apps (`features.apps=false` was tested and removed the default account-connected app inventory from the later thread). Verify the actual exposed tool inventory.
- Pin the Codex distribution and schema; validate both helpers and necessary resources under real release signing. Use `model/list` to select available models instead of hardcoding the spike's default.

### 2. Bundle and bridge

New native files under `platforms/desktop/Espresso/Espresso/`:

- `Services/Codex/CodexBridge.swift`: actor owning process, private pipes, line framing, request IDs, bounded buffers, notifications, server requests, timeouts, shutdown, and restart.
- `Models/Codex/CodexProtocol.swift`: versioned request/response/event types from the pinned schema, including unknown-event handling.
- `Services/Codex/CodexResearchCoordinator.swift`: account and single active research-run lifecycle. Start with one active run per app session to avoid process-environment/token contention.
- `CodexHelper.entitlements` plus a packaging script under `platforms/desktop/Espresso/scripts/` that verifies checksums, stages both helpers/resources/licenses and signs inside out. Wire the script into the Xcode build, not an after-sign modification of release archives.

Suggested public interfaces:

```swift
actor CodexBridge {
    func start(matchaToken: String?) async throws
    func account(refresh: Bool) async throws -> CodexAccount?
    func startLogin() async throws -> CodexLogin
    func cancelLogin(id: String) async throws
    func logout() async throws
    func startThread(_ request: CodexResearchThreadRequest) async throws -> String
    func startTurn(threadID: String, prompt: String) async throws -> String
    func interrupt(threadID: String, turnID: String) async throws
    func events() -> AsyncStream<CodexEvent>
    func stop() async
}
```

Use explicit container paths and an environment allowlist. Never load the terminal's Codex home or an OpenAI token into Swift. Obtain status through `account/read`; only Codex handles its credential file. Redact URLs with auth state, tokens, and account identifiers from logs. Serialize login/logout and process replacement. A changed bearer requires process replacement: modifying the parent's environment cannot update an already-running child.

Add each Swift file to the four required `project.pbxproj` locations and run `plutil -lint`. Keep the current bundle ID from the project (`com.matchawork.app`), not the stale `com.ahnimal.matcha` mentioned in older docs.

### 3. First-party Matcha token endpoint

Add request/response models to `server/app/matcha/models/matcha_work/connectors.py`; route to the existing `routes/matcha_work/connectors.py`; issuance logic in `core/services/mcp_oauth.py` (or a small companion service).

```text
POST /api/matcha-work/connectors/local-token
Authorization: Bearer <ordinary Matcha session JWT>
body: {"project_id":"<uuid>","task_id":"<uuid>"}
response: {
  "access_token":"mat_at_…", "token_type":"Bearer",
  "expires_at":"<UTC ISO timestamp>",
  "resource":"<configured-origin>/api/mcp",
  "client_id":"espresso-local-codex"
}
Cache-Control: no-store
```

Proposed service signature: `issue_local_access_token(current_user, *, project_id: UUID, task_id: UUID) -> LocalConnectorToken`.

Revalidate the active JWT session, feature entitlement, project membership/edit rights, and research-card eligibility. Derive user/company server-side. Mint a short-lived access token only, hashed in the existing token table, with a fixed first-party client registered transactionally/idempotently. Never accept client-selected resource, scopes, user, expiry, or client ID. Rate-limit issuance and revoke the run's token on cleanup.

The existing token schema binds access to user/resource/scopes, **not an individual card**. Validating the requested card at issuance does not make the token card-scoped. Keep all existing per-call authorization checks; if strict task-bound grants are required, propose that storage/auth change separately for approval. No new table or migration is assumed in this initial endpoint proposal, and database writes still need the user's implementation approval.

Use a fresh bearer before each run. Set a bounded run deadline before token expiry; a 401/expiry ends the run visibly. Do not silently restart or replay a publishing turn. Consider longer-run refresh only as a separate design with explicit revocation semantics.

### 4. Native account and card UI

- `Views/SettingsView.swift`: ChatGPT account status, sign-in/cancel/sign-out, browser callback progress, optional device-code fallback, rate-limit display.
- `Views/MatchaWork/TaskViewer/TaskViewerSheet+Header.swift`: route Codex to the coordinator; retain the other connector choices.
- `Services/MatchaWorkService+Tasks.swift` and `Models/MatchaWork/ProjectTaskModels.swift`: typed local-token request/response; reuse the server's research-launch prompt.
- A new progress view presents deltas, named MCP/search steps, cancel, terminal failure and verified published-report success. Hook app termination and Matcha logout/account changes to process/token cleanup.

Thread configuration starts with `ephemeral:true`, `approvalPolicy:"never"`, `sandbox:"read-only"`, `web_search:"live"`, `features.apps:false`, shell disabled, and only the needed Matcha tools enabled. All research instructions/data must remain subordinate to fixed application restrictions. [App-server protocol](https://learn.chatgpt.com/docs/app-server), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Handle pending request failures on EOF/crash, bounded retries before a run starts, stale events after restart, login callback cancellation, expiry, exhausted limits, app exit and user cancellation. Do not infer report success from prose or turn completion: require a successful `attach_research_report` result and refetch the card.

Existing publishing writes storage, note and card state in separate steps and is marked non-idempotent. Before adding automatic recovery, design stable run identity, concurrency/duplicate protection and reconciliation after timeout/partial publication. Until that is implemented, surface an uncertain outcome and refetch; do not automatically repeat publication. Cancellation after claim must not silently undo another actor's subsequent card edits. These are implementation requirements, not exercised write-path results from this read-only spike.

### 5. Validation gates

- Bridge tests: partial/multiple JSON lines, malformed/oversized input, out-of-order responses, unknown events, EOF/crash, timeout, cancellation, late login completion and process restart.
- Token tests: feature/session/tenant denial; concurrent first-party client creation; expiry, scope/resource mismatch, hashed-only storage, logout/password/disconnect revocation, no credentials in logs.
- Research tests: failed MCP item with a completed turn; rate limit; cancellation before/after claim; duplicate publish; upload/note/card partial failures; no unsafe replay.
- Real manual native checks: new login, callback, restart, logout, read-only MCP success, invalid/revoked bearer, live search, cancel, missing helper, Intel if offered, and both distribution archives.
- `cd server && ./venv/bin/python -m pytest tests -q` for implementation changes, plus the 80% diff-coverage gate. Real-DB mutation tests remain opt-in and require approval.
- `platforms/desktop/Espresso/run.sh build`, relevant native tests, and `plutil -lint`. If client/API-consumed types change, `cd client && npx tsc -p tsconfig.app.json --noEmit` and the production build gate.

## Validation actually run

- Baseline `platforms/desktop/Espresso/run.sh build`: restricted attempt failed on Xcode cache permissions; authorized host retry passed with ad-hoc signing.
- Throwaway `/private/tmp/espresso-codex-spike/run.sh build`: passed. Reused the baseline package cache after fresh package fetches stalled. Two existing unused-result Swift warnings.
- `plutil -lint /private/tmp/espresso-codex-spike/Matcha.xcodeproj/project.pbxproj`: passed.
- `codesign --verify --deep --strict` and helper entitlement inspection: passed.
- `codex app-server generate-json-schema --out /private/tmp/espresso-codex-spike/schema`: passed.
- Native JSON-RPC controller checks and direct `command/exec` matrix: results above.
- Dev MCP initialize/tools-list: HTTP 200; read tool: authenticated application error; revoked bearer: HTTP 401.
- Read-only `information_schema.columns` and `alembic_version` checks: absent column; `mcpconn01` present. No migration executed.
- `cd server && ./venv/bin/python -m pytest tests/mcp_connector -q`: **69 passed, 19 warnings in 2.39s**.
- `git diff --check` and `git diff --no-index --check /dev/null docs/plans/ESPRESSO_CODEX_APP_SERVER_SPIKE.md`: passed.
- Full server suite and client gates were not run: no implementation source changes in those trees. No release-signing, notarization, App Store, Intel, device-code, expiry/rate-limit, or publishing test was completed.

Temporary reproducibility material remains at `/private/tmp/espresso-codex-spike/`: Swift harness, controller, generated protocol schemas, redacted event log, concise event summary, size measurements and Debug app. The plaintext temporary Matcha token was removed from its state file after revocation. The revoked token/client audit rows remain in dev. Codex logout removed the spike login; no terminal/session credentials were touched.

## Implementation addendum — 2026-09-26

Implemented on `codex/espresso-codex-app-server`, based on `origin/main` at
`1cc90a9`, following the user's branch/PR approval:

- Both connector queries now derive pending AutoPR state from the same history
  query as the board. Native grant issuance also checks active AutoPR claims.
- Added session-authenticated, 30-minute access-only Matcha grants and per-family
  revocation using existing OAuth tables. No migration or schema changes.
- Added the pinned arm64 runtime fetch/embed/sign phase, Apache license and notice,
  Swift process bridge, per-Matcha-user credential homes, browser/device-code login,
  account status/usage, single-run research, progress/cancel and shutdown cleanup.
- Research uses the server's launch prompt and the account's advertised default
  model. It enables get/claim/attach and live search, disables account apps and
  shell tools, and refuses app-server approval requests. Success requires a
  matching successful attach result plus a refreshed Review card and attachment.
- Fixed the existing native test target's `Espresso` product-name collision and
  made the app module name explicitly `Matcha`, matching its existing tests.

Validation of this implementation:

- Full server suite with coverage: **10,154 passed, 46 skipped, 9 xfailed**;
  **100% changed-line coverage** across the five changed server modules (63 lines).
- Both repaired connector queries executed successfully in a **read-only** local
  dev transaction. Used a nonexistent UUID and returned no customer data. This
  validates real schema compatibility; it is not a new authenticated model turn.
- `run.sh build`: passed with ad-hoc signing and both bundled helpers.
- Native tests: **73 passed**, including six Codex tests. The real child test
  initialized, read an empty account, restarted, correlated concurrent RPCs, and
  shut down from the sandboxed test host using a fresh credential namespace.
  The initial test caught a pipe reader waiting for a full buffer; using available
  data fixed the stalled handshake.
- Client `npx tsc -p tsconfig.app.json --noEmit` and `npm run build`: passed
  (existing Vite chunk-size warnings). No web UI changed.
- Archive checksum verification, `codesign --verify --deep --strict`, `plutil
  -lint`, Python compilation and `git diff --check`: passed.

Still required before release: a fresh login and real **write** run through the
new UI on an approved disposable dev card; device-code flow; hostile-input/tool
inventory, expiry and rate-limit checks; publication partial-failure behavior;
real Developer ID/notarization and App Store validation. The implementation does
not add transactionality, task-scoped grants or cross-device research leases.
Revocation is best effort on process/app/session shutdown, bounded by token expiry.
The pre-existing model-catalog timeout has not been isolated. Keep the PR draft
until these acceptance checks and review are complete.

## Review follow-up — 2026-09-27

Review fixes (`f57b8d1` and the commit after it): the bridge forwards only the
events the coordinator handles and batches agent text, so a progress burst can
no longer overflow the stream mid-publish; pipe reads moved to dedicated
threads; an idle signed-in child is reused for account checks; cleanup refreshes
an expired Matcha access token; a cancelled/failed run releases its own claim
(`POST /connectors/local-tokens/{grant}/release`, only when the claim is still
the latest change and no report was stored); local grants are hidden from the
connections list; the real-child test removes its credential namespace. An
opt-in `RUN_DB_TESTS` suite PREPAREs the connector SQL against a real schema.

Acceptance checks run against local dev (disposable project "Codex acceptance
(disposable)" on the `maria.chen@example.com` account, cards A/B/C):

| Check | Result |
|---|---|
| Grant response headers | `Cache-Control: no-store`; resource `http://localhost:8001/api/mcp` |
| Server tool inventory (`tools/list`) | list/get/claim/attach |
| Codex tool inventory, research thread config | Exactly get/claim/attach (`enabled_tools` filters list); `runtimeStatus: connected`, `authStatus: bearerToken` |
| Invalid bearer in Codex | `authenticationRequired`, zero tools |
| Claim via MCP, then release | Card B back to `todo`; history `todo→in_progress→todo` plus both notes |
| Release of an unclaimed card / repeat release | `released:false, reason:not_in_progress` |
| Release with another user's grant id | 404 |
| Revoke, then reuse bearer | 204, then HTTP 401 |
| Local grant in connections list | Absent |
| Server suite | 10,170 passed, 50 skipped, 9 xfailed; diff coverage 100% (107 lines) |
| Native tests | 76 passed, including 9 Codex tests |

Model-catalog stall: `timeout waiting for child process to exit` is the display
text of Codex's generic timeout error (same enum as `RequestTimeout`), so the
stall is most likely a timed-out catalog *request*, not a stuck subprocess.
Signed out and outside the sandbox there is no stall (initialize 0.21 s,
`model/list` 0.03 s). Debug builds can now log the child's stderr in the
sandbox: `open -n --env ESPRESSO_CODEX_STDERR=<path inside the container>
Espresso.app`.

Still needs a person: a ChatGPT sign-in in the app (browser and device code),
a real write run on card A, a cancel-after-claim on card B, the hostile-input
card C, the in-sandbox stall log, and Developer ID/notarization/App Store (the
signing certificate expired 2026-09-22).
