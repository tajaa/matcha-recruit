# Matcha sandbox autonomy — mechanical implementation plan

## 1. Objective

Make every interactive `msandbox` development session an honest, capable,
contained application-building environment:

1. The session picker shows what the selected session can actually do, using
   checks and Xs backed by live probes rather than configuration guesses.
2. The agent receives the same capability report in its own context, so it does
   not claim that it cannot inspect images, run a browser, use GitHub, run tests,
   or build a native target when that capability is available.
3. `scripts/dev-remote.sh` remains the canonical application launcher, while
   each development session receives isolated PostgreSQL, Redis, ports, process
   state, and test artifacts.
4. Linux builds, tests, browser automation, image attachments, GitHub CLI, a
   least-privilege AWS CLI profile, production diagnostics, and local Xcode
   builds are usable from the session without repeated operator approvals.
5. Production API, browser, and SQL mutation is available immediately for
   existing `companies.is_test = true` tenants. There is no per-run unlock
   command, approval prompt, or remembered tenant allowlist.
6. The same production credentials are structurally unable to mutate a
   non-test tenant, change the `is_test` boundary, retrieve unrestricted
   production secrets, or turn themselves into broader credentials.
7. Worktree changes, agent transcripts, test reports, screenshots, and native
   build logs survive container or agent termination.

This plan applies to interactive, user-owned `msandbox` sessions. The Kanban
AutoPR, error-autofix, and changelog-drafting lanes remain credential-free and
must not inherit any capability introduced here.

## 2. Decisions fixed by this plan

- **No production unlock command.** Test-tenant production access is provisioned
  when an interactive session is created or resumed. An ordinary `psql`, HTTP,
  browser, AWS, GitHub, or SSH command uses the already-scoped identity.
- **Authorization is not a prompt.** `CLAUDE.md`, `AGENTS.md`, a system prompt,
  or a shell wrapper may explain the boundary, but none is the security
  boundary.
- **`companies.is_test` is the source of truth.** Do not copy the current UUIDs
  into a static allowlist. Removing `is_test` from a company must block the next
  HTTP request or new SQL transaction from an already-running session. An
  in-flight SQL statement follows PostgreSQL snapshot semantics and is bounded
  by the restricted role's statement/idle-transaction timeouts.
- **Existing full credentials stay out.** Do not copy
  `secrets/roonMT-arm.pem`, the production `matcha` database password,
  `server/.env`, the app host's `.env.backend`, or the host's default AWS
  profile into an independent session.
- **A separate restricted PEM still provides SSH.** The sandbox receives a new
  production-test key whose server-side restrictions cannot yield an
  `ec2-user` shell, `sudo`, Docker access, environment files, or arbitrary port
  forwarding.
- **Use `dev-remote.sh`; do not create a second app launcher.** Add a
  session-data-services mode to the existing script and keep its backend,
  worker, Vite, Tell-Us, and Oceanlab orchestration in one place.
- **Local Xcode first, GitHub Actions second.** Native builds run on this Mac
  through a narrow broker and a dedicated unprivileged macOS builder account.
  GitHub Actions is the fallback when the local native builder is unavailable.
- **Autonomous mode and capability are different axes.** `permission_mode`
  controls whether the selected agent asks before its own sensitive actions.
  It does not grant broader production credentials.
- **Default deny schema growth.** A new production table is not writable by the
  sandbox until its ownership is classified and its policy is tested.
- **No automatic production DDL.** Creating roles, installing policies,
  applying migrations, and changing the production app database role retain
  the repository's existing explicit-approval and rehearsal process.

## 3. Current baseline to replace

Observed on 2026-09-02 from the local development schema and current `main`:

- `scripts/msandbox/wizard.py` offers three coarse choices: development,
  development plus browser, or agent-only. It does not render a capability
  matrix.
- `scripts/msandbox/cli.py::_doctor()` probes Node, npm, npx, pytest, Vitest,
  GitHub auth, and the Actions API. It does not probe images, the running app,
  production-test access, SSH, AWS, or the local Xcode path.
- `scripts/msandbox/session_auth.py` safely copies agent login state and
  materializes the host GitHub token, but does not provision purpose-built
  production-test credentials.
- `scripts/msandbox/docker_runtime.py` points `SANDBOX_AWS_DIR` at the host's
  complete `~/.aws` directory.
- Independent sessions use detached worktrees. Untracked files such as the
  existing production PEM and `server/.env` are not present in those
  worktrees, despite the legacy sandbox documentation describing the whole
  main checkout as mounted.
- `docker-compose.sandbox-test.yml` already supplies isolated PostgreSQL and
  Redis for validation, but ordinary development sessions still use the
  shared host development database and Redis.
- `scripts/msandbox/host_actions.py` has a safe target/action registry for
  Xcode, but only the operator-triggered validation path can invoke it. It
  executes `xcodebuild` as the logged-in macOS user against the live worktree.
- Session worktrees and homes persist, and validation JSON persists, but no
  complete per-session terminal transcript or normalized artifact index is
  written.
- The local schema contains 601 public base tables and 1,296 foreign keys.
  There are 231 tables with a direct `company_id` or `org_id`; only 43 of those
  currently have forced RLS.
- The current tenant policies are generally `TO PUBLIC` and include
  `current_setting('app.is_admin') = 'true'`. A database login that can select
  its own session settings cannot safely reuse those policies as its only
  production-test boundary.
- `server/alembic/versions/c9cfac81407a_create_app_db_role.py` creates the
  `matcha_app LOGIN NOBYPASSRLS` foundation, but grants DML on all current and
  future public tables. Confirm the actual production `DATABASE_URL` role
  before relying on RLS; the documented `matcha` production role is a
  superuser and bypasses RLS.
- `scripts/export-dev-data.py` and `scripts/sync_tenants.py` already discover
  columns, primary keys, and single-column foreign keys and distinguish
  tenant-descended rows from shared ascended parents. Reuse that discovery
  logic, but do not treat the sync engine as a runtime security boundary. It
  deliberately omits composite foreign-key traversal and only constrains SQL
  that it generated itself.
- `server/app/core/routes/auth/test_accounts.py` already creates admin-approved
  seeded companies with `is_test = true`; keep that as the creation path.

The table and policy counts are an implementation-time baseline, not constants.
Every schema gate below must introspect the migrated database again.

## 4. Target session experience

Selecting an existing session or confirming a new one renders this before the
agent opens:

```text
Capabilities for espresso-fix
  ✅ Repository read/write       detached worktree
  ✅ Linux build tools           Python 3.12, Node, npm, Vitest
  ✅ Isolated development        PostgreSQL, Redis, backend, worker, Vite
  ✅ Headless browser            Playwright Chromium
  ✅ Image/PDF attachments       bounded session inbox
  ✅ GitHub CLI                  branch/PR/checks; no deploy authority
  ✅ AWS CLI                     sandbox profile; diagnostics only
  ✅ Production test API         live read/write, is_test enforced
  ✅ Production test database    live read/write, is_test enforced
  ✅ Production diagnostics      restricted SSH/log access
  ✅ Xcode                       isolated local macOS builder
  ❌ Non-test tenant mutation    denied by API and PostgreSQL
  ❌ Production admin/secrets    not provisioned
  ❌ Signing/deploy/merge        not provisioned
```

An unavailable capability renders `❌`, followed by the failed probe and a
specific setup or fallback. Do not render `✅` because an executable merely
exists; the probe must exercise the actual boundary. Examples:

- `✅ GitHub CLI` requires an authenticated repository read and Actions read.
- `✅ Headless browser` requires launching Chromium and closing it cleanly.
- `✅ Production test database` requires a read-only connection as the
  restricted role and a server-side assertion that the role has no non-test
  visibility.
- `✅ Xcode` requires broker health, an installed Xcode version, and one
  broker-owned no-op project inspection. It does not require a full build every
  time the picker opens.

Write the same report to
`/home/agent/.msandbox/capabilities.{json,md}` and inject the Markdown report
through each agent adapter's supported system/developer-context mechanism.
The report must say how to invoke each available capability and which actions
are intentionally denied. Do not rely on the agent discovering a shell alias.

Production-test access should support ordinary tools immediately, for example:

```text
curl/Playwright -> $PROD_TEST_BASE_URL using the session credential file
psql             -> service=matcha_prod_test
asyncpg/pytest   -> the restricted production-test service file
ssh              -> matcha-prod-test (fixed diagnostics/tunnel identity)
```

A convenience test runner may compose these operations, but it is not an
authorization gate. Direct use of the underlying tools remains available.

## 5. Trust boundaries

| Identity | Available inside session | May mutate | Must not mutate/read |
| --- | --- | --- | --- |
| Local development | Yes | Its session PostgreSQL/Redis/files | Other sessions' state; host Docker |
| Production test API principal | Yes | Its currently `is_test` company through supported endpoints | Non-test companies; admin routes |
| `matcha_test_agent` DB role | Yes | Explicitly classified rows owned by an `is_test` company | Non-test/shared/global rows; `is_test`; schema/roles |
| Restricted production SSH key | Yes | Nothing by default; tunnel only | Shell, sudo, Docker, env/secrets, arbitrary forwarding |
| Sandbox AWS profile | Yes | Only separately enumerated test-safe resources, if any | IAM, secrets, SSM, compute/deploy mutation, backups |
| Sandbox GitHub identity | Yes | Feature branches and pull requests | Protected branches, merge, secrets, environments, deploy dispatch |
| Native builder identity | Through broker | Its copied source/DerivedData/artifacts | User home, Keychain, SSH agent, Docker, signing identities |
| Kanban AutoPR identities | No change | Existing bounded patch/PR path only | Every new interactive-session credential |

Possession of the current `ec2-user` PEM, a PostgreSQL superuser password, an
AWS principal that can call SSM or retrieve secrets, or a GitHub token that can
dispatch a production deployment defeats the non-test guarantee. Capability
probes must fail if any of those broader identities leak into the container.

## 6. Delivery sequence

| PR | Outcome | Production effect |
| --- | --- | --- |
| A | Capability model, probes, picker display, and agent context | None |
| B | Isolated session development and durable artifacts | None |
| C | Complete tenant-ownership ledger and fail-closed schema audit | None |
| D | Production test-only PostgreSQL role and RLS boundary | Migration plus one-time approved role setup |
| E | Production test-only API/browser identity and automatic session provisioning | Migration, backend deploy, credential setup |
| F | Restricted SSH, AWS, and GitHub identities | One-time infrastructure setup |
| G | Isolated local macOS/Xcode builder broker | One-time local machine setup |
| H | Integrated denial tests, rollout, and documentation cleanup | Controlled production canary |

PRs A-C are safe to merge without enabling production access. PRs D-F must
land and pass their denial suites before interactive sessions receive any
production-test credential. Do not temporarily mount the current broad
credentials while waiting for the restricted identities.

---

# PR A — capability contract and truthful picker

## A1. Data model

Add to `scripts/msandbox/models.py`:

```python
CapabilityStatus = Literal["available", "unavailable", "denied"]


@dataclass(frozen=True)
class CapabilityResult:
    id: str
    title: str
    status: CapabilityStatus
    detail: str
    invocation: str | None = None
    checked_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CapabilityReport:
    schema_version: int
    session_id: str
    results: tuple[CapabilityResult, ...]
    checked_at: str
```

Do not put credentials, tokens, connection strings, PEM paths, response
bodies, or command output containing environment values into this model.

Add `last_capability_check_at` and `capability_report_path` to `SessionRecord`.
Keep `scripts/msandbox/schemas/session-v1.json` backward compatible by making
the fields optional; old records continue to load.

## A2. Probe registry

Create `scripts/msandbox/capabilities.py` with one registry and two probe
phases:

- **Host probes before container start:** Docker health, local native-builder
  health, configured restricted credential directories, and Xcode installation.
- **Container probes after start:** toolchain versions, Git/GitHub auth, AWS
  identity, isolated data services, browser launch, attachment readability,
  production-test API login, restricted SQL identity, and restricted SSH
  connectivity.

Every probe returns a `CapabilityResult`; it never raises out of the complete
report. Probes must be read-only, bounded by a timeout, and redact stdout.

Use stable capability IDs:

```text
repo_rw, linux_build, isolated_dev, browser, attachments,
github, aws, prod_test_api, prod_test_db, prod_diagnostics,
xcode, non_test_mutation, prod_admin, signing_deploy
```

The last three are explicit denied capabilities. A successful security probe
renders them as `❌ ... denied`; a detected leak is a report failure, not a
green capability.

## A3. CLI and wizard

- Add `msandbox capabilities SESSION [--refresh]` in
  `scripts/msandbox/cli.py`.
- Replace `_doctor()`'s independent probe list with the shared registry.
  `doctor` prints details and exits nonzero for a required unavailable
  capability or a failed denial assertion.
- In `scripts/msandbox/wizard.py`, show the cached report when a session is
  selected and refresh stale reports before `Open agent`.
- Show the planned capabilities in the new-session confirmation screen. After
  creation, show the live report and do not open the agent until the user has
  had a chance to see it.
- Keep browser as an image choice because it changes the content-addressed
  Docker image. All other credentials are interactive-session defaults, not
  permission-mode toggles.

## A4. Agent-visible context

- Render mode-600 JSON and Markdown under the session home.
- Extend `scripts/msandbox/agent_adapters.py` with a per-agent
  `capability_context_args()` implementation using a documented, supported
  system/developer prompt mechanism for Codex, Claude, and OpenCode.
- The injected text must begin: “This capability report was measured for this
  session. Test the named invocation before claiming the capability is absent.”
- Include ordinary invocations, for example `gh pr view`, `aws sts
  get-caller-identity`, the production-test base URL, the restricted database
  alias, browser command, and native build request. Never include secret values.
- Refresh the files and restart/reload the adapter context when a capability
  changes during resume.

## A5. Tests

Extend `scripts/tests/test_msandbox_v2.py` to cover:

- full and partial probe reports;
- timeout, missing executable, bad credentials, and malformed probe output;
- redaction of token/password/PEM/URL-password patterns;
- old session-record compatibility;
- picker rendering with checks and Xs;
- the same report reaching each agent adapter; and
- a leak probe turning the entire doctor result red.

Update `scripts/tests/test_agent_sandbox_networking.sh` to assert the rendered
Compose configuration contains only the intended restricted mounts.

### PR A acceptance

- [ ] Selecting a session always displays a measured capability report.
- [ ] The agent receives the same report before its first user task.
- [ ] A missing capability is an honest `❌` with a working fallback.
- [ ] No report contains a credential or secret-bearing URL.
- [ ] `msandbox doctor SESSION` and the picker share exactly one probe registry.

---

# PR B — isolated development and durable session output

## B1. Session-local PostgreSQL and Redis

- Move the PostgreSQL/Redis service definitions shared by development and
  validation into a Compose fragment, for example
  `docker-compose.sandbox-data.yml`.
- Use PostgreSQL 15 with pgvector to match the documented local/production
  major version and extension surface.
- Give every Compose project its own named PostgreSQL volume and Redis service.
  Do not publish either service to the host.
- Make `docker-compose.sandbox-dev.yml` depend on those services and set:

```text
DATABASE_URL=postgresql://matcha:...@postgres:5432/matcha_session
REDIS_URL=redis://redis:6379/0
```

- Keep `docker-compose.sandbox-test.yml` disposable for validation. Development
  and validation must not share a database volume.
- Initialize only the new isolated database. Applying repository migrations to
  that disposable/session-owned database is permitted; never reuse this path
  for localhost production tunnels or any URL containing the production hosts.
- Record the initialized Alembic head set and fail startup if a reused session
  volume has drifted. The failure tells the agent/operator how to rebuild that
  session database without deleting the worktree.

## B2. Keep `dev-remote.sh` canonical

Modify `scripts/dev-remote.sh` so `AGENT_SANDBOX=1`:

- trusts its already-injected `DATABASE_URL` and `REDIS_URL`;
- waits on the parsed service hosts rather than hardcoding
  `host.docker.internal`;
- never calls the unavailable Docker CLI;
- uses a session-unique tmux name derived from `MSANDBOX_SESSION_ID`;
- continues to start backend, worker, main Vite, Tell-Us, and Oceanlab; and
- prints the container and host-published URLs from the assigned `PortSet`.

Host use remains unchanged: the user's ordinary `dev-remote.sh` continues to
use `matcha-postgres`, `matcha-redis`, and the normal ports.

## B3. Browser and attachments

- Preserve the Playwright image overlay. Add the browser launch probe to the
  session readiness marker so `✅` means Chromium actually starts.
- Keep the bounded attachment inbox and existing no-symlink/path-traversal/size
  rules.
- Ensure `deliver_attachments()` records image MIME metadata and the
  agent-visible path in the artifact index, but never copies an attachment into
  the Git worktree automatically.

## B4. Durable outputs

Create per-session directories under the existing private state root:

```text
sessions/<id>/artifacts/index.json
sessions/<id>/transcripts/terminal.log
sessions/<id>/checkpoints/latest.md
sessions/<id>/validation/*.json
sessions/<id>/native-builds/<request-id>/...
sessions/<id>/browser/<capture-id>/...
```

- Attach a mode-600 `tmux pipe-pane` transcript when the agent launches.
- Strip terminal control sequences on a second normalized pass; retain the raw
  mode-600 transcript for recovery.
- Rotate by size, never by a short wall-clock timer. Retain the current and two
  previous transcript segments while the session is active.
- Index validation logs, screenshots, native-build logs, and explicit agent
  checkpoint summaries by content hash.
- On a normal stop, request a best-effort agent checkpoint, then stop. A failed
  checkpoint must not prevent preserving the worktree and transcript.
- `release_session()` may remove these only after the worktree is clean and
  published; add `--keep-artifacts` for operator-selected retention.

### PR B acceptance

- [ ] Two development sessions can mutate their own local databases without
      observing each other's rows.
- [ ] The host `dev-remote.sh` stack remains running and unchanged.
- [ ] Killing the container preserves source changes, database volume,
      transcript, validation reports, and screenshots.
- [ ] A resumed session uses the same local state and receives updated URLs.

---

# PR C — complete tenant-ownership ledger

## C1. One machine-readable classification

Create `server/app/database/test_tenant_access.toml`. Every public base table
must resolve to exactly one class:

```toml
[tables.schedule_shifts]
scope = "direct"
tenant_column = "company_id"
allow = ["select", "insert", "update", "delete"]

[tables.er_case_documents]
scope = "parent"
path = ["case_id", "er_cases.id", "company_id"]
allow = ["select", "insert", "update", "delete"]

[tables.jurisdictions]
scope = "shared_read_only"
allow = ["select"]

[tables.stripe_webhook_events]
scope = "denied"
reason = "global idempotency and billing boundary"
```

Allowed scope values:

- `direct`: a non-null `company_id` or `org_id` is checked directly;
- `parent`: an explicit, acyclic join path reaches a direct tenant owner;
- `principal`: ownership is through a user/client/employee identity and has an
  explicit tenant-resolution query;
- `shared_read_only`: readable reference data, never mutable;
- `denied`: unavailable to the role; and
- `external_product`: Cappe, Tell-Us, Oceanlab, or another identity model not
  governed by `companies.is_test`, denied until it receives its own test marker
  and plan.

Do not infer runtime authorization from table-name prefixes. Prefixes may help
generate the initial ledger, but the committed ledger resolves every table.

## C2. Schema auditor and policy generator

Create `scripts/msandbox/test_tenant_schema.py` with these subcommands:

```text
inventory --database-url ...
validate-ledger --database-url ...
render-policies --database-url ... --output ...
verify-installed --database-url ...
```

Requirements:

1. Introspect all public base tables, columns, primary keys, unique keys,
   sequences, RLS flags, policies, grants, and every single/composite FK.
2. Reuse or extract the schema-loading primitives in
   `scripts/export-dev-data.py`; do not maintain a second divergent FK parser.
3. Fail on an unclassified table, missing path column, ambiguous ownership
   path, nullable break in a claimed required path, cyclic path, policy/grant
   mismatch, or new writable column on `companies` that is not reviewed.
4. Treat all four currently observed composite foreign keys explicitly. Their
   Tell-Us tables remain `external_product` for this release.
5. Emit deterministic SQL and a human-readable coverage report. The committed
   migration contains a reviewed snapshot; production does not execute a live
   code generator.
6. Mark externally dangerous test-tenant tables—billing credentials, OAuth
   tokens, SSO config, webhook idempotency, secrets, and production delivery
   control—as `denied` or `shared_read_only` even if they have `company_id`.
7. Mark email-bearing mutations safe only where the existing reserved-domain
   send guard applies; all provisioned test users use RFC-reserved domains.

## C3. CI gate

After `alembic upgrade heads` on the isolated CI database, run:

```text
python scripts/msandbox/test_tenant_schema.py validate-ledger --database-url "$DATABASE_URL"
```

Add it to the `automation-contracts` validation surface and CI. A PR creating a
table or FK without updating the ledger fails before merge.

### PR C acceptance

- [ ] All migrated public tables are classified exactly once.
- [ ] Every mutable table has a complete tenant path and both `USING` and
      `WITH CHECK` expressions.
- [ ] Shared ascended parents are never classified as tenant-mutable merely
      because a test row references them.
- [ ] New tables fail CI by default.

---

# PR D — PostgreSQL-enforced production test mutation

## D1. Role and helper

Create a new Alembic migration from the correct live head at implementation
time. Do not reuse or edit `c9cfac81407a`.

The migration creates:

- `matcha_test_access_owner NOLOGIN BYPASSRLS`, owner of exactly one policy
  helper function and no tables; and
- `matcha_test_agent LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOREPLICATION NOBYPASSRLS`, initially without a password.

Create a hardened function equivalent to:

```sql
CREATE FUNCTION public.matcha_is_test_company(candidate uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.companies AS c
    WHERE c.id = candidate
      AND c.is_test IS TRUE
      AND c.deleted_at IS NULL
  )
$$;
```

Own it with the no-login owner, revoke execution from `PUBLIC`, and grant only
the roles that require it. Grant that owner only the exact `companies` columns
the function reads. Confirm the owner cannot log in, is not granted to another
role, owns no tables, and owns no other executable function. Its narrow
`BYPASSRLS` attribute exists only so the fixed boolean lookup cannot recurse
through the `companies` policy; the sandbox login never receives that role or
attribute.

## D2. Policies

For every `direct`, `parent`, or `principal` table in the ledger:

- enable and force RLS;
- install a role-specific permissive `sandbox_test_access` policy;
- install a role-specific restrictive `sandbox_test_boundary` policy; and
- use the same ownership predicate for `USING` and `WITH CHECK`.

The restrictive policy is mandatory because existing policies are `TO PUBLIC`
and use session-controlled custom settings. A caller setting
`app.is_admin=true`, `app.current_tenant_id=<non-test>`, or any unknown GUC must
still fail the restrictive test-company predicate.

For `companies`:

- allow `SELECT` only when `id` is currently test;
- grant `UPDATE` only on reviewed, non-boundary columns;
- never grant update on `id`, `is_test`, billing identifiers, deletion state,
  or other credential/authority columns;
- deny `INSERT` and `DELETE`; new test companies continue through the existing
  admin-only test-account registration flow; and
- enforce `WITH CHECK (is_test IS TRUE AND deleted_at IS NULL)` directly on the
  row so an update or trigger cannot move or declassify it.

For `shared_read_only`, grant only the reviewed `SELECT` columns. For `denied`
and `external_product`, grant nothing.

Do not grant:

- schema `CREATE`;
- role membership or `SET ROLE` targets;
- DDL, function creation, extension control, large-object control, or event
  triggers;
- default privileges on future tables/sequences;
- unrestricted sequence access; or
- execute on application/internal security-definer functions.

Grant sequence use individually only when an allowed insert truly requires it.
UUID-backed tables normally need no sequence grant.

Set bounded role defaults for `statement_timeout` and
`idle_in_transaction_session_timeout`, and keep the role at `READ COMMITTED`.
The revocation contract is the next HTTP request or new SQL transaction, not
the middle of a statement that already obtained a snapshot.

## D3. Existing application role prerequisite

Before enabling the session credential:

1. Query production `current_user`, `rolsuper`, and `rolbypassrls` through the
   trusted operator path.
2. If the app still connects as `matcha`, complete and validate the documented
   switch to `matcha_app NOBYPASSRLS` first.
3. Re-run the full server suite plus authenticated production-test smoke tests.
4. Do not enable sandbox API mutation while the production request path can
   bypass the same restrictive policies.

The migration must preserve normal application behavior. Add or repair
`matcha_app` policies for newly forced-RLS tables in the same migration; do not
assume application-level joins replace database policy on a directly queried
child table.

## D4. Credential bootstrap

Add `scripts/msandbox/bootstrap-production-test-access.sh` as a one-time,
operator-run setup script. It may:

- verify the migration is installed;
- generate and set a random password for `matcha_test_agent` without writing it
  to shell history;
- store the password in a mode-600 file under
  `~/.config/matcha-msandbox/production-test/`;
- run the complete local denial suite; and
- print—but never automatically execute—the production canary steps.

This one-time infrastructure setup retains explicit approval. After it is
complete, starting and using a session requires no production unlock command.

## D5. Database tests

Create `server/tests/infrastructure/test_test_tenant_db_role.py` against an
isolated migrated PostgreSQL instance with two companies: one test and one
non-test. Run every attempt as `matcha_test_agent`.

Required assertions:

- select/insert/update/delete succeeds on representative direct and indirect
  rows belonging to the test company;
- the same statements against the non-test company return no rows or an RLS
  error;
- moving a test row's tenant/parent reference to a non-test owner fails;
- inserting a child under a non-test parent fails;
- stale prepared statements and a long-lived connection fail on their next
  `READ COMMITTED` transaction after the company is changed from test to
  non-test by the operator connection;
- `UPDATE companies SET is_test=false`, changing `id`, deleting the company,
  and inserting a company all fail;
- `SET app.is_admin=true`, arbitrary `app.current_tenant_id`, `SET ROLE`, role
  creation, schema creation, function creation, and direct calls to ungranted
  security-definer functions do not widen access;
- shared parents are read-only and unrelated shared rows are not exposed when
  the ledger limits them;
- a representative trigger, cascade, and deferred constraint cannot mutate a
  non-test row as a side effect; and
- a new unclassified table has no grants and fails the ledger test.

Never point this automated test at production. The production canary is a
separate, manually invoked transaction using only reserved-domain rows in an
existing test tenant, followed by rollback.

### PR D acceptance

- [ ] The restricted role can freely mutate all classified test-tenant data.
- [ ] Every attempted non-test or boundary mutation fails in PostgreSQL even
      after hostile session settings.
- [ ] Production application traffic runs as a non-bypass role before sandbox
      API access is enabled.
- [ ] No production credential is committed or included in Docker metadata.

---

# PR E — API/browser identity and automatic session provisioning

## E1. Mark sandbox test principals

Add a small migration-backed table rather than overloading email naming:

```sql
CREATE TABLE sandbox_test_principals (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid NOT NULL REFERENCES users(id),
  disabled_at timestamptz,
  CHECK (enabled = (disabled_at IS NULL))
);
```

The table is global authorization metadata: no sandbox DB grant and no sandbox
API mutation. Add master-admin endpoints to enroll or disable only an existing
`client`, `individual`, or `employee` whose resolved company is currently
`is_test = true`. Reject admin, broker, candidate, agency, and creator roles in
the first release.

Use the existing `POST /register/test-account` flow to create test tenants and
users. Enrollment is a separate explicit admin action; do not let the sandbox
create or mark companies as test.

## E2. Enforce on every request and async boundary

- Extend `CurrentUser` with `sandbox_test_only: bool = False`.
- `get_current_user()` reads the principal row on every authenticated request.
  If it is enabled, resolve its company and require `companies.is_test = true`
  before returning the user.
- Propagate a `sandbox_test_only` context variable through
  `server/app/database/pool.py`, alongside tenant/user/admin context.
- Add restrictive `matcha_app` RLS policies whose condition is:

```text
not sandbox_test_only OR row resolves to a current is_test company
```

- Apply the same check to login and refresh. A token must stop working after
  principal disablement or test-tenant declassification without waiting for
  token expiry.
- Review HTTP, WebSocket, background `asyncio` tasks, Celery messages, file
  upload/storage operations, and external integrations. Any work queued by a
  sandbox principal carries the restriction bit and revalidates `is_test` at
  execution time.
- Do not permit a sandbox principal to call master-admin, company-selection,
  credential-management, subscription, SSO, OAuth, deploy, or tenant-lifecycle
  endpoints even if its ordinary role would expose one.

## E3. Session credential storage

Store configured test-account credentials only under:

```text
~/.config/matcha-msandbox/production-test/accounts.json
```

Format:

```json
{
  "schema_version": 1,
  "base_url": "https://hey-matcha.com",
  "accounts": [
    {"label": "primary", "email": "builder@example.com", "password_file": "accounts/primary.password"}
  ]
}
```

- Require reserved-domain email addresses.
- Keep passwords in separate mode-600 files.
- Extend `session_auth.py`'s no-follow, atomic-copy primitives to copy only this
  restricted directory into the private session home.
- Do not use Compose environment variables for passwords or tokens.
- Provide a session-local credentials helper understood by Playwright and curl;
  it reads the file at execution time and never prints the password.
- On create/resume, log in, call the authenticated profile endpoint, verify the
  returned principal is marked sandbox-only and its company is still test, then
  mark the capability available.

## E4. Automatic SQL tunnel

Add `docker-compose.sandbox-prod-test.yml`, included only for interactive
sessions with configured restricted credentials:

- an `autossh`/OpenSSH sidecar owns the limited key;
- it forwards only to the live PostgreSQL endpoint through the restricted app
  host key;
- it exposes the forwarded port only on the private Compose network;
- the workspace receives a non-secret alias/config pointing at the sidecar;
- the password comes from a mode-600 mounted file or PostgreSQL service file,
  not a Compose environment value; and
- health checks use `SELECT current_user` plus the installed-policy verifier.

The tunnel starts with the session and restarts automatically. The agent can
run ordinary `psql`/asyncpg tools immediately; it never runs an unlock or
approval command.

### PR E acceptance

- [ ] Browser and API writes succeed on enrolled production test accounts.
- [ ] Declassifying the company or disabling the principal blocks the next API,
      WebSocket, worker, and SQL mutation in an existing session.
- [ ] The session cannot use the identity to access admin or non-test routes.
- [ ] Credentials are absent from `docker inspect`, capability reports,
      transcripts, Git state, and process command lines.

---

# PR F — restricted SSH, AWS, and GitHub

## F1. SSH identity

Create a dedicated key and server account, for example
`matcha-test-agent`, on the app host. The `authorized_keys` entry must:

- disallow PTY, agent forwarding, X11 forwarding, user rc files, and arbitrary
  commands;
- permit port forwarding only to `13.56.253.173:5433`;
- optionally restrict the source IP to this Mac's known egress address; and
- expose a fixed diagnostics command only if logs/health need SSH rather than
  AWS APIs.

The account has no sudo, Docker group, application group, home-readable
`.env.backend`, deployment checkout write, or DB-host shell. Add a canary secret
under each prohibited path and assert it is unreadable before marking SSH green.

Copy this restricted key into the session-private auth directory using the
same no-follow logic as agent/GitHub auth. Never mount the repository's current
PEM into independent sessions.

## F2. AWS identity

Create `matcha-msandbox` as a dedicated IAM role. The host controller assumes
it and writes only short-lived STS credentials into the session-private AWS
directory. Allow only the diagnostic calls the capability contract lists,
initially:

- `sts:GetCallerIdentity`;
- selected `ec2:Describe*` calls;
- bounded CloudWatch metric/log reads for Matcha service groups; and
- read-only ECR metadata if build diagnosis needs it.

Explicitly omit or deny IAM mutation, `iam:PassRole`, Secrets Manager, SSM
commands/sessions/parameters, KMS decrypt, backup object reads, S3 writes,
compute mutation, Lambda invocation/update, ECR pushes, and deployment APIs.

Change `compose_environment()` so `SANDBOX_AWS_DIR` points to the dedicated
mode-700 msandbox AWS directory. Remove the default host `~/.aws` mount for
independent interactive sessions. Set `AWS_PROFILE=matcha-msandbox` and probe
the returned ARN/account, not merely `aws --version`.

## F3. GitHub identity

Replace host-token copying for interactive sessions with a short-lived,
repository-scoped GitHub App installation token that can:

- fetch and push `codex/*` branches;
- create/update draft pull requests and comments; and
- read checks, workflow definitions, and run results.

It cannot merge, push protected branches, edit Actions secrets/environments,
approve protected deployments, edit workflow files without the dedicated
workflow permission, or dispatch production deployment workflows.

If test workflow dispatch is required, expose an allowlisted controller action
for named non-production workflows instead of granting generic Actions write.
Keep `gh` itself fully usable for the allowed operations.

## F4. Leak and escalation checks

Read-only picker probes verify identity, mounts, advertised scopes, and the
absence of broad credential files. The separate denial suite uses disposable
branches/resources and must verify from inside the container that:

- `secrets/roonMT-arm.pem` and `server/.env` are absent;
- `ssh ec2-user@...`, sudo, Docker, arbitrary SSH commands, and arbitrary
  forwarding fail;
- the AWS ARN is exactly the sandbox identity and prohibited API calls fail;
- GitHub cannot write `main`, merge a PR, read secrets, or dispatch deploy; and
- AutoPR Compose rendering still points AWS at an empty directory and strips
  all interactive credentials.

Do not make the picker mutate GitHub, AWS, or production merely to display a
checkmark.

### PR F acceptance

- [ ] `gh`, `aws`, and restricted SSH work without a per-command approval.
- [ ] None can be chained into production admin or non-test mutation authority.
- [ ] Existing broad host credentials are not mounted or copied.

---

# PR G — isolated local Xcode builder

## G1. One-time builder identity

Create an unprivileged macOS account dedicated to native builds. It has:

- no admin/sudo rights;
- no login Keychain items, signing identities, SSH agent, browser profile,
  cloud credentials, or Docker access;
- a private build root and DerivedData root;
- read access only to Xcode/toolchains and its copied request source; and
- no access to the user's home or live Matcha checkout.

Install a LaunchDaemon/service under explicit operator approval. Document its
uninstall and recovery procedure.

## G2. Narrow request broker

Add:

```text
scripts/msandbox/native_builder_server.py
scripts/msandbox/native_builder_client.py
scripts/msandbox/install-native-builder.sh
scripts/msandbox/native_builder_protocol.json
```

The request schema accepts only:

```json
{"session_id":"...","target":"espresso|matchatutor|tellus|gummfit","action":"build|test"}
```

No caller-supplied path, executable, argument, environment variable,
destination, scheme, timeout, output path, or shell text is accepted.

The trusted controller resolves the session, snapshots its tracked and
untracked source into a builder-owned directory, rejects escaping symlinks and
special files, and invokes the existing target registry. The build process
runs as the builder account against the copy, never the live worktree. Results
contain exit status, bounded/redacted logs, Xcode version, duration, and paths
to explicitly exported test/build artifacts.

Limit the broker to one active request per session, a small global concurrency
cap, a fixed maximum runtime, a fixed output-size ceiling, and complete process
group termination on timeout or session stop.

Expose the request socket inside the workspace read/write, but expose no
general host shell. Extend `host_actions.py` so operator validation and
agent-requested builds share the same request implementation.

Signing, notarization, App Store upload, device installation, `open`, arbitrary
simulator automation, and deployment remain denied capabilities.

## G3. Native-builder security tests

Create a fixture Xcode project with shell phases that attempt to:

- read canaries from the user's home, Keychain, `.ssh`, `.aws`, and repository
  secrets;
- access the Docker socket;
- write outside the builder request directory;
- use a caller-supplied output path or build argument; and
- leave a child process running after timeout.

Every attempt must fail while an ordinary Espresso build succeeds. Killing a
request must terminate its full process group. Concurrent sessions receive
different source, DerivedData, and result directories.

If the broker probe is red, the capability report gives the exact applicable
GitHub Actions fallback. It must not tell the agent that Xcode is categorically
impossible.

### PR G acceptance

- [ ] An autonomous session can request and iterate on an Espresso/macOS or
      iOS build without operator interaction.
- [ ] Agent-controlled Xcode build phases cannot access the user's account or
      live checkout.
- [ ] Logs and artifacts persist in the session artifact index.

---

# PR H — integration, rollout, and operational proof

## H1. End-to-end capability suite

Add one host-run suite that creates a temporary interactive session and proves:

1. capability UI and agent context agree;
2. local DB writes are isolated from the host and another session;
3. browser launch, screenshot, and image attachment delivery work;
4. Git branch/PR operations and Actions reads work;
5. AWS and SSH diagnostics work with their restricted identities;
6. a local Xcode build runs and its output is retained;
7. API and SQL CRUD succeeds for a production test tenant;
8. equivalent non-test CRUD, tenant reassignment, `is_test` change, privilege
   escalation, secret access, deployment, and signing all fail; and
9. container kill/resume preserves work and outputs.

The production portion is opt-in and manually invoked because it mutates live
test data. It creates only reserved-domain records, tags them with a unique run
ID, verifies them, deletes only those rows, and writes an audit summary. It
must never create/drop/alter a live table, role, or schema.

## H2. Rollout order

1. Merge A-C and observe capability reporting with production capabilities red.
2. Apply D to local isolated PostgreSQL and run the complete role suite.
3. Rehearse D against a current production snapshot and review the generated
   ledger/policy coverage report.
4. With explicit approval, back up production, apply D, provision the role, and
   run the rollback-only production canary.
5. Deploy E, enroll one existing test-account user, and prove immediate
   declassification/disablement.
6. Provision F identities and repeat escalation probes from inside a real
   session.
7. Install G's local builder and run its hostile build-phase fixture.
8. Enable automatic production-test credential provisioning for one canary
   interactive session.
9. After the full H1 suite passes, enable it for all interactive sessions.

At every stage, a failed probe produces `❌` and leaves the rest of the session
usable. It never falls back to a broader host credential.

## H3. Documentation updates

Update together:

- `docs/ops/MSANDBOX_SESSIONS.md` — picker, capabilities, ordinary invocations,
  persistence, native builds, and test-production access;
- `docs/ops/AGENT_SANDBOX.md` — replace the current broad AWS/PEM threat model;
- `docs/ops/DB_WORKFLOW.md` — role/policy setup, schema-ledger gate, canary, and
  revocation;
- `CLAUDE.md` — concise capability and production-test boundary summary; and
- `scripts/msandbox/test_targets.toml` — native target/action registry and
  fallback workflow names.

Explicitly distinguish:

- live test-tenant mutation (automatic and allowed);
- non-test production mutation (technically denied);
- production DDL/migrations (operator-approved only);
- code publication by feature branch/PR (allowed);
- merge/deploy/sign/release (not provisioned); and
- AutoPR's credential-free lane (unchanged).

## H4. Rollback

- Session provisioning has a global kill switch that removes the restricted
  credentials and prod-test Compose overlay from newly started sessions. It
  does not delete worktrees or artifacts.
- Disable all `sandbox_test_principals` and rotate the DB password/SSH key/AWS
  identity/GitHub App key independently.
- Revoke grants from `matcha_test_agent` before dropping policies or roles.
- Keep RLS enabled for the normal application role; do not roll back tenant
  isolation merely to disable sandbox access.
- Stop/uninstall the native builder service and remove only its dedicated
  account data after verifying no requested artifacts need retention.
- Never restore the old full AWS mount or `ec2-user` PEM as a fallback.

## H5. Definition of done

- [ ] A freshly created interactive development session displays checks/Xs for
      all named capabilities and injects the same report into its agent.
- [ ] The session autonomously edits, runs isolated local dev, executes tests,
      uses Chromium, consumes image attachments, uses `gh`/AWS/SSH diagnostics,
      and runs applicable local Xcode builds.
- [ ] Ordinary API, browser, and SQL tools mutate live production test tenants
      without a special unlock command or repeated approval.
- [ ] Database and application enforcement block non-test mutation even with
      hostile IDs, stale tokens, changed GUCs, indirect child tables, retries,
      WebSockets, and queued work.
- [ ] The agent cannot alter `is_test`, obtain broader credentials, access host
      secrets, merge/deploy/sign, or escape through Xcode build phases.
- [ ] Every public table is classified; schema growth fails closed.
- [ ] Container/process/time-limit failure loses neither source changes nor the
      latest available transcript, checkpoint, test report, screenshot, or
      native-build output.
- [ ] AutoPR and other sealed automation lanes remain credential-free.
