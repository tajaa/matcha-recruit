# Compliance Graph Design — Dossier-driven per-company jurisdictional architecture

> **Status: ARCHITECTURE DESIGN — for review before any code.**
>
> Decisions locked:
> 1. New **per-company compliance graph** (company owns its structured
>    graph; not the old shared bank).
> 2. Ingest the **full dossier footprint** — jurisdiction hierarchy +
>    categories + certs + licenses + credentials + policies + the actual
>    requirement content.
> 3. **Design first**, build after sign-off.

## Intent

The onboarding gap-analysis dossier stops being a document. It becomes
the **blueprint** that stands up a company's *jurisdictional
architecture*: a structured graph of every jurisdiction the company is
bound by, the categories / certs / licenses / credentials / policies that
attach at each level, and — crucially — a pipeline that **goes out and
grabs** the actual regulatory content for each node so the company is
provably covered, not just listed.

"Forget the old system" → this graph is the new source of truth.
`company_compliance_scope` + the location-timer check loop are NOT the
foundation here; we may reuse their *research services*, but the model is
fresh and company-owned.

## The per-company compliance graph (data model)

New tables, prefixed `cc_` (company-compliance graph) to stand apart from
the legacy `company_compliance_scope`. Relational, asyncpg, Postgres.
Adjacency-list hierarchy for jurisdictions.

```
cc_graph                     one (versioned) graph per company
  id, company_id, source_session_id (→ onboarding_sessions),
  version, status (building|ready|stale), built_at, built_by

cc_jurisdiction_node         the company's jurisdiction HIERARCHY
  id, graph_id, parent_id (self-FK; federal→state→county→city),
  level (enum), name, state, county, city,
  jurisdiction_id (nullable soft-ref to shared jurisdictions.id),
  source (dossier|location)
  # DECISION: per-company SNAPSHOT (own the hierarchy; aligns with
  # "company owns its graph / forget the old system"). state/county/city
  # are copied, not FK-joined, so the graph is self-contained and can't
  # be silently mutated by shared-table edits. jurisdiction_id is kept
  # only as a soft pointer for research-service reuse (resolving a node
  # to the shared bank's research), NOT a hard dependency. Trade-off:
  # ~duplicated hierarchy rows per company + jurisdiction-level facts can
  # drift from the shared table (acceptable — refresh re-verifies).

cc_category_node             a compliance category that applies, at a juris node
  id, graph_id, jurisdiction_node_id, category_slug, scope_level,
  reason, source (dossier|ai_suggestion),
  ingest_status (pending|researching|ingested|not_found|stale)

cc_requirement               GRABBED regulatory content for a category node
  id, category_node_id, requirement_key, title, summary,
  current_value, citation, source_url, source_tier,
  status (pending|researching|ingested|not_found|stale),
  ingested_at, verified_at, refresh_cadence_days

cc_credential                required certs / licenses / credentials
  id, graph_id, jurisdiction_node_id (nullable for federal/specialty),
  kind (certification|license|credential), slug, name,
  issuing_authority, scope_level, renewal_period_months,
  grabbed_detail (jsonb: application steps, renewal rules, fees),
  ingest_status, source, verified_at

cc_policy                    required policies
  id, graph_id, jurisdiction_node_id (nullable),
  policy_key, name, reason, source,
  draft_ref (→ policies / handbook section), ingest_status, verified_at
```

Every leaf (`cc_requirement`, `cc_credential`, `cc_policy`) carries an
**ingest lifecycle** + **provenance** (source_url, source_tier,
verified_at) + a **refresh cadence**. `not_found` after ingestion = a
true gap that needs manual research — surfaced loudly.

## Flow

### 1. Bootstrap: dossier → graph (the "architecture" build)

A `build_company_compliance_graph(session)` service reads the finalized
dossier (`onboarding_sessions.gap_analysis` — already persisted) and
instantiates the graph, all leaves `pending`:

- **Jurisdiction nodes** from `dossier.scope.applicable_jurisdictions` +
  `dossier.locations` → build the federal→state→county→city tree (link
  parents). This is the literal "jurisdictional hierarchy."
- **Category nodes** from `scope.compliance_categories` +
  `ai_suggestions.suggested_compliance_categories`, attached to the
  matching jurisdiction node by `scope_level`.
- **Credential nodes** from `scope.required_certifications` +
  `required_licenses` (+ ai suggestions).
- **Policy nodes** — **deferred to P3.** The dossier can't seed them yet
  (Gap A: `ai_scope` has no policies). P1 builds jurisdiction + category +
  credential nodes only; policy nodes land once scope expansion learns to
  surface them.

Triggered at finalize (or an explicit "Build compliance architecture"
action on the dossier page).

**`not_found` recovery:** when a leaf finishes ingestion with no content
(research whiffed), it surfaces in the graph view as a **manual-research
item**. The team fills it via the existing `/fill-gaps <city> <state>`
path (or human research into the source), then re-runs ingestion for that
leaf. `not_found` is a visible worklist state, never a silent drop.

### 2. Ingestion: "go out and grab" (the engine)

A dispatcher enqueues one research job per `pending` leaf, **routed by
node type to an existing service** (no new research engines):

| Leaf | Grab via (existing) | Writes |
|---|---|---|
| `cc_requirement` (category × jurisdiction) | `compliance_service` jurisdiction research; `medical_compliance_research` / `oncology_research` workers | requirement content + citation + tier |
| `cc_credential` | `credential_inference.py` / `credential_template_service.py` | renewal rules, authority, application detail |
| `cc_policy` | `policy_suggestion_service.py` / `policy_draft_service.py` / `handbook_service.py` | drafted/attached policy → `draft_ref` |

Each job: `pending → researching → ingested` (content + provenance) or
`not_found`. Job/leaf status tracked on the graph so the dossier page
shows live per-node progress ("researching… / ingested / gap").

### 3. Freshness

Each leaf has `refresh_cadence_days` + `verified_at`. A scheduler
re-ingests stale leaves; legislation signals (reuse `legislation_watch`
feeds) mark affected leaves `stale`. New loop, graph-keyed (not
location-timer keyed).

## Reuse map (don't rebuild)

- Jurisdiction resolution + hierarchy: existing `jurisdictions` table
  (level/parent_id/state/county/city) — `cc_jurisdiction_node` mirrors its
  shape; resolver logic from `map_to_bank`.
- Requirement research: `compliance_service.py` research +
  `_upsert_requirements_additive`; `medical_compliance_research`,
  `oncology_research` workers.
- Credentials: `credential_inference`, `credential_template_service`,
  `certifications_catalog` / `licenses_catalog`.
- Policies: `policy_suggestion_service`, `policy_draft_service`,
  `handbook_service`, `policies` table.
- Dossier assembler: `server/app/core/services/onboarding_dossier.py`
  (shipped) is the input.

## Gaps to resolve in the design (decisions for review)

**Gap A — DONE (commit 8eee8dc).** `ai_scope` + the dossier now capture
`required_policies` + `required_credentials`. Scope expansion
(`onboarding_scope_ai.py:expand_scope`) emits both; dossier renders
Policies + Credentials sections. Policy nodes can now seed from the
dossier in P3.

**Gap B — DONE (commit 8eee8dc).** Distinction settled: company-level
certs/licenses stay in `required_certifications` / `required_licenses`;
employee/professional credentials (BCBA, RBT, …) live in
`required_credentials` with an `applies_to_role`, and Gemini **infers
them from the staff roles named in the company description**. Verified
live on the ABA company (BCBA + RBT inferred). Per-employee tracking
remains a separate surface (company-level *requirement* only here).

**Gap C — graph versioning on re-onboard.** Re-finalize / re-run → new
`cc_graph.version` (immutable history) vs in-place update. Recommend
versioned: a new build supersedes, old kept for audit.

**Gap D — relationship to the legacy system (dual-write during build).**
"Forget it for now" = build standalone. Concretely: for the duration of
the build, **finalize keeps writing the legacy `company_compliance_scope`
rows AND builds the new `cc_graph`** (dual-write) — nothing that depends
on the old scope breaks while the graph matures. This graph conceptually
supersedes `company_compliance_scope`; the cutover (stop dual-writing,
migrate existing companies onto the graph retroactively) is a later
decision, deferred. Calling it out so the transition isn't limbo:
dual-write now, decide cutover once P1–P3 prove the graph carries its
weight.

## Phasing (build order, after design sign-off)

- **P1 — Model + bootstrap.** `cc_*` tables (migration) +
  `build_company_compliance_graph` (dossier → **jurisdiction + category +
  credential** nodes, all `pending`; policy nodes deferred to P3) + a read
  API + graph view on the dossier page. No ingestion yet — proves the
  architecture stands up from the dossier.
- **P2 — Requirement ingestion.** Dispatcher + `cc_requirement` research
  (the core "grab"), per-node status on the UI.
- **P3 — Credential + policy ingestion.** Wire the credential + policy
  services; resolve Gap A (extend scope expansion).
- **P4 — Freshness loop + versioning.** Refresh cadence, legislation
  re-stale, `cc_graph` versioning on re-onboard.

## Verification (per phase, when built)

- **P1:** finalize a session → `cc_graph` + nodes created; counts match
  the dossier; graph view renders the hierarchy. Unit-test the builder
  pure function (dossier dict → node list) like `build_gap_analysis_dossier`.
- **P2:** dispatch on a known jurisdiction → `cc_requirement` rows
  populate with citations; `not_found` flagged where research whiffs.
- **P3/P4:** credential/policy nodes ingest; stale-and-refresh cycle.

## Out of scope

- Owner-invite loop (token → account, currently unwired) — see backlog.
- Migrating existing companies onto the graph (Gap D — later).
- Per-employee credential tracking (company-level requirement only here).

## Remaining gaps / backlog (work later)

Inventory of everything still open, so we can pick up cold. Roughly
priority-ordered.

### Design decisions still open (block the graph build)
- **Gap C — graph versioning on re-onboard.** Versioned snapshot
  (`cc_graph.version`, immutable history) vs in-place update. Recommend
  versioned. Decide before P1.
- **Gap D — legacy coexistence.** Dual-write `company_compliance_scope`
  + new `cc_graph` during the build; cutover (stop dual-writing + migrate
  existing companies onto the graph) deferred until P1–P3 prove the
  graph. Decide cutover trigger.

### The graph build itself (the main remaining work)
- **P1** — `cc_*` tables (migration) + `build_company_compliance_graph`
  (dossier → jurisdiction + category + credential nodes) + read API +
  graph view. (Policies seed here too now that Gap A is done.)
- **P2** — ingestion dispatcher + `cc_requirement` research, per-node
  status.
- **P3** — credential + policy ingestion.
- **P4** — freshness loop + versioning.

### Onboarding wizard wiring (independent of the graph)
- **Owner-invite loop unwired (high impact).** `finalize_session` mints
  `onboarding_sessions.invite_token` but **nothing consumes it** — no
  acceptance route, no email send. The onboarded owner currently has no
  way into the platform. Needs: an acceptance route that reads the
  token → creates the owner user (role=client) bound to the company, +
  an email send (reuse `EmailService`). `admin_onboarding.py:finalize_session`.
- **`dispatch-research` is a stub.** `admin_onboarding.py` ~line 577
  logs a TODO and enqueues nothing. To make the wizard's "research these
  gaps" button real: for each approved `(category_slug, jurisdiction)`
  gap, resolve `jurisdiction_id` + enqueue the right worker
  (`run_medical_compliance_research` / `run_oncology_research` /
  `run_compliance_check_task(..., allow_live_research=True)`), then
  re-resolve + attach. (Largely subsumed by P2 ingestion if we go
  graph-first.)
- **Scheduled checks never research** (`compliance_checks.py:26`,
  `allow_live_research=False`). Deliberate cost gate; means gaps fill
  only via manual `/fill-gaps`. Leave off unless we want auto-research.

### Cleanup / smaller
- **`ResolvedScopeAmbiguous` model drift.** Pydantic/TS type requires
  `category_slug`, but `map_to_bank` builds ambiguous items without it
  (`onboarding_scope_ai.py` ~539, ~564). Runtime-safe today (report
  doesn't read it). Either emit `category_slug` on ambiguous items or
  relax the model.
- **No catalog enum for policy/credential slugs.** Gemini free-picks, so
  two companies may coin different slugs for the same cert (`bcba` vs
  `bacb_bcba`). Matters once the graph dedups/researches across
  companies — consider a slug-normalization or a catalog table.
  → **Addressed by the shared-content layer** in `COMPLIANCE_GRAPH_P1.md`:
  the graph holds per-company *structure*; content lives in shared stores
  (`jurisdiction_requirements`, `certifications_catalog`/`licenses_catalog`,
  `credential_*`, + new `compliance_policy_template`), leaves link to a
  shared row via `cc_requirement.jurisdiction_requirement_id` /
  `cc_credential.catalog_id` / `cc_policy.template_id` (resolve-before-
  research dedup, P2/P3). Cross-company slug normalization still needed
  for the resolver to match variant slugs to one shared row.
- **Migration `zzzz_b04` (gap_analysis column) must run before
  finalize** on any environment, else finalize 500s. Operational
  reminder, not code.
