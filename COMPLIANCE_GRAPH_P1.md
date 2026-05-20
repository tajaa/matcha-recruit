# Compliance Graph — P1 Technical Specification

> **Companion to `COMPLIANCE_GRAPH_DESIGN.md`.** That doc is the
> architecture (the *why* + the full multi-phase shape). This doc is the
> implementation-level spec for **P1 only**: stand up the per-company
> `cc_*` graph from the finalized dossier, expose it via a read API, and
> render it with location drill-down. **No *new research* in P1** — but
> the graph is not an empty shell: requirements already resolved by the
> wizard (`dossier.coverage`) are linked to the shared bank live
> (`ingested`), and gaps land `pending` as the P2 worklist. The "go out
> and grab" research engine is P2.
>
> **Status: SPEC — for review before code.**

## P1 decisions (locked)

| # | Decision | Choice |
|---|---|---|
| Scope | How much to build | **Full P1**: tables + builder + read API + graph view |
| Gap C | Re-onboard / rebuild behavior | **Versioned snapshot** — new `cc_graph.version`; prior → `superseded` (immutable history); latest active |
| Gap D | Legacy `company_compliance_scope` | **Dual-write** — finalize keeps writing legacy rows AND builds `cc_graph`; cutover deferred |
| Trigger | When the graph builds | **Auto at finalize** (best-effort, separate conn, **build-once per session**) + manual "Rebuild" button (always new version) |
| Content | Per-company vs shared | **Shared-content layer** — graph holds STRUCTURE; regulatory CONTENT lives in shared cross-company stores (see below) |
| Coverage | Seed already-resolved data | **Yes** — `dossier.coverage` seeds `cc_requirement` at build (covered → linked `ingested`; gaps → `pending`). Graph shows covered-vs-gap with no research (Issue 1). |
| Navigation | View after the fact | **Location drill-down** — click business → location (e.g. Chicago) → effective set = location-specific + inherited Federal/State/County. |

## Shared-content layer (cross-company dedup)

**Principle.** The `cc_*` graph is per-company **structure** — *which*
jurisdictions × categories × creds × policies apply to *this* company.
The actual regulatory **content** (requirement text, cert/cred detail,
policy body) lives in **shared, cross-company stores**, so two biotech
companies don't each re-research the same policy. A graph leaf *points
at* a shared row; falls back to per-company custom when genuinely unique.

This sharpens "forget the old system": we drop
`company_compliance_scope` (the per-company *manifest*) but **keep**
`jurisdiction_requirements` (the shared *content* bank) and the other
shared catalogs — they are exactly the dedup layer we want.

**Reuse what exists; add only the one missing store:**

| Leaf | Shared content store | Dedup key | Status |
|---|---|---|---|
| requirement | `jurisdiction_requirements` (`database.py:2878`) | `(jurisdiction_id, requirement_key)` | EXISTS — reuse |
| certification | `certifications_catalog` (`zzzz_a01`) | `slug` | EXISTS — reuse |
| license | `licenses_catalog` (`zzzz_a01`) | `slug` | EXISTS — reuse |
| employee credential | `credential_types` + `role_categories` + `credential_requirement_templates` | `key` / tiered `company_id IS NULL` | EXISTS — reuse |
| **policy** | **none — only per-company `policies`** | — | **NEW: `compliance_policy_template`** |

The new `compliance_policy_template` **mirrors the proven
`credential_requirement_templates` tiering**: `company_id IS NULL` = a
**shared library** policy any company can adopt; `company_id NOT NULL` =
a **company-specific/unique** policy (the "only applies to certain
businesses" case). `cc_policy.template_id` points at either row; NULL =
not yet resolved.

**Dedup happens at ingestion (P2/P3), via resolve-before-research.** The
dispatcher first looks up a matching shared row by its dedup key;
researches + writes to the shared store **only on a miss**; then links
every requesting company's graph leaf to that one shared row. Two
companies in the same jurisdiction/industry therefore share the row and
the research cost.

**P1's job for this layer = schema only.** P1 creates the link columns
(`cc_policy.template_id`, `cc_credential.catalog_id`,
`cc_requirement.jurisdiction_requirement_id`) + the new
`compliance_policy_template` table, all left NULL/empty. Resolution and
population are P2/P3 — but landing the columns now avoids a re-migration.

## Inputs (already shipped — do not rebuild)

The build reads the **frozen dossier** at
`onboarding_sessions.gap_analysis` (JSONB), produced by
`server/app/core/services/onboarding_dossier.py:build_gap_analysis_dossier`.
**P1 consumes `scope` AND `coverage`** — `coverage` is the dedup mapping
`map_to_bank` already computed and is seeded into the graph at build time
(see §2b). `counts`/`headcount` are not consumed.

```jsonc
{
  "company":  { "name", "industry", "specialty", ... },
  "locations": [ { "name", "address", "city", "state", "county", "zipcode", ... } ],
  "scope": {
    "naics_sector": "string|null",
    "compliance_categories":   [ { "category_slug", "scope", "reason" } ],
    "required_certifications":  [ { "slug", "name", "issuing_authority", "scope_level", "renewal_period_months" } ],
    "required_licenses":        [ { "slug", "name", "issuing_authority", "scope_level", "renewal_period_months" } ],
    "required_credentials":     [ { "slug", "name", "issuing_authority", "applies_to_role", "scope_level", "renewal_period_months", "reason" } ],
    "required_policies":        [ { "slug", "name", "scope_level", "reason" } ],
    "applicable_jurisdictions": [ { "state", "county", "city" } ]
  },
  "ai_suggestions": {
    "suggested_compliance_categories": [ { "category_slug", "scope", "reason" } ],
    "suggested_certifications":        [ { "slug", "name", "reason" } ],
    "suggested_licenses":              [ { "slug", "name", "reason" } ]
  },
  "coverage": {
    "covered": [ { "requirement_id", "category_slug", "canonical_key", "title", "scope_level", "location_id" } ],
    "gaps":    [ { "category_slug", "scope_level", "state", "county", "city", "reason" } ],
    "ambiguous": [ { "category_slug", "candidates", "why" } ]
  }
}
```

**`coverage` is the resolved dedup mapping** (verified against
`map_to_bank` + `ResolvedScope*` models): `covered.requirement_id` is an
already-resolved row in the shared `jurisdiction_requirements` bank;
`gaps` are categories with no shared row yet (the P2 worklist). P1 links
covered requirements into the graph live — no ingestion needed.

Note the field-name asymmetry to handle in the builder:
- categories use `scope` (not `scope_level`).
- certs/licenses/credentials use `scope_level`.
- `compliance_categories` source = `dossier`; `ai_suggestions.*` source =
  `ai_suggestion`.

Read-back helper already exists: `admin_onboarding.py:_dossier_from_row`
(returns the frozen snapshot if present, else assembles live).

---

## 1. Schema — migration `zzzz_b05_compliance_graph.py`

`down_revision = "zzzz_b04_onb_gap"`. Raw `op.execute` SQL, mirroring
`zzzz_a01_admin_onboarding_scope.py`. **All schema lands in this one
migration** — `cc_*` tables (incl. `cc_requirement`, unused until P2) +
the new shared `compliance_policy_template` + the link columns
(`cc_policy.template_id`, `cc_credential.catalog_id`,
`cc_requirement.jurisdiction_requirement_id`), all NULL/empty in P1.
Landing them now avoids a re-migration when ingestion (P2/P3) populates
them. `gen_random_uuid()` PKs.

```sql
-- One versioned graph per build. Latest non-superseded = active.
CREATE TABLE cc_graph (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source_session_id UUID REFERENCES onboarding_sessions(id) ON DELETE SET NULL,
    version           INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'building'
                        CHECK (status IN ('building','ready','superseded','stale')),
    built_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    built_at          TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, version)
);
CREATE INDEX idx_cc_graph_company ON cc_graph(company_id, version DESC);

-- The jurisdiction HIERARCHY (per-company snapshot; owns its tree).
CREATE TABLE cc_jurisdiction_node (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id     UUID NOT NULL REFERENCES cc_graph(id) ON DELETE CASCADE,
    parent_id    UUID REFERENCES cc_jurisdiction_node(id) ON DELETE CASCADE,
    level        TEXT NOT NULL CHECK (level IN ('federal','state','county','city')),
    name         TEXT NOT NULL,
    state        TEXT,
    county       TEXT,
    city         TEXT,
    jurisdiction_id UUID,            -- soft-ref to jurisdictions.id; NO hard FK
    source       TEXT NOT NULL DEFAULT 'dossier'
                   CHECK (source IN ('dossier','location'))
);
CREATE INDEX idx_cc_juris_graph ON cc_jurisdiction_node(graph_id);

-- A compliance category that applies, at a jurisdiction node.
CREATE TABLE cc_category_node (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id             UUID NOT NULL REFERENCES cc_graph(id) ON DELETE CASCADE,
    jurisdiction_node_id UUID NOT NULL REFERENCES cc_jurisdiction_node(id) ON DELETE CASCADE,
    category_slug        TEXT NOT NULL,
    scope_level          TEXT,
    reason               TEXT,
    source               TEXT NOT NULL DEFAULT 'dossier'
                           CHECK (source IN ('dossier','ai_suggestion')),
    ingest_status        TEXT NOT NULL DEFAULT 'pending'
                           CHECK (ingest_status IN ('pending','researching','ingested','not_found','stale'))
);
CREATE INDEX idx_cc_cat_graph ON cc_category_node(graph_id);

-- Required certs / licenses / employee credentials.
CREATE TABLE cc_credential (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id             UUID NOT NULL REFERENCES cc_graph(id) ON DELETE CASCADE,
    jurisdiction_node_id UUID REFERENCES cc_jurisdiction_node(id) ON DELETE CASCADE,
    kind                 TEXT NOT NULL CHECK (kind IN ('certification','license','credential')),
    slug                 TEXT NOT NULL,
    name                 TEXT NOT NULL,
    issuing_authority    TEXT,
    scope_level          TEXT,
    renewal_period_months INTEGER,
    applies_to_role      TEXT,                       -- Gap B: inferred staff role
    catalog_id           UUID,                        -- soft-ref to the resolved shared catalog row.
                                                      --   Which table is keyed off `kind`:
                                                      --   certification→certifications_catalog,
                                                      --   license→licenses_catalog,
                                                      --   credential→credential_types.
                                                      --   cert/license resolved AT BUILD (finalize
                                                      --   already upserts those catalogs by slug);
                                                      --   credential resolved in P3.
    grabbed_detail       JSONB NOT NULL DEFAULT '{}', -- optional per-company override; canonical
                                                      --   detail lives on the shared catalog (P3)
    source               TEXT NOT NULL DEFAULT 'dossier'
                           CHECK (source IN ('dossier','ai_suggestion')),
    ingest_status        TEXT NOT NULL DEFAULT 'pending'
                           CHECK (ingest_status IN ('pending','researching','ingested','not_found','stale')),
    verified_at          TIMESTAMP
);
CREATE INDEX idx_cc_cred_graph ON cc_credential(graph_id);

-- Required policies. Links to a shared/company template via template_id.
CREATE TABLE cc_policy (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id             UUID NOT NULL REFERENCES cc_graph(id) ON DELETE CASCADE,
    jurisdiction_node_id UUID REFERENCES cc_jurisdiction_node(id) ON DELETE CASCADE,
    policy_key           TEXT NOT NULL,
    name                 TEXT NOT NULL,
    scope_level          TEXT,
    reason               TEXT,
    source               TEXT NOT NULL DEFAULT 'dossier'
                           CHECK (source IN ('dossier','ai_suggestion')),
    template_id          UUID,                        -- soft-ref → compliance_policy_template.id;
                                                      --   NULL = unresolved/custom. Resolved in P3.
    ingest_status        TEXT NOT NULL DEFAULT 'pending'
                           CHECK (ingest_status IN ('pending','researching','ingested','not_found','stale')),
    verified_at          TIMESTAMP
);
CREATE INDEX idx_cc_policy_graph ON cc_policy(graph_id);

-- Per-company LINK to the shared requirement bank (NOT a content copy).
-- CREATED IN P1, RESOLVED + LINKED IN P2. Content read by joining
-- jurisdiction_requirements via jurisdiction_requirement_id.
CREATE TABLE cc_requirement (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_node_id         UUID NOT NULL REFERENCES cc_category_node(id) ON DELETE CASCADE,
    jurisdiction_requirement_id UUID,                 -- soft-ref → jurisdiction_requirements.id (shared)
    requirement_key          TEXT,
    status                   TEXT NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending','researching','ingested','not_found','stale')),
    linked_at                TIMESTAMP,
    verified_at              TIMESTAMP
);
CREATE INDEX idx_cc_req_cat ON cc_requirement(category_node_id);

-- NEW SHARED STORE: cross-company policy library, tiered like
-- credential_requirement_templates. company_id NULL = shared library row
-- (any company can adopt); company_id NOT NULL = company-specific/unique.
-- CREATED EMPTY IN P1, POPULATED IN P3.
CREATE TABLE compliance_policy_template (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID REFERENCES companies(id) ON DELETE CASCADE,  -- NULL = shared library
    policy_key      TEXT NOT NULL,
    name            TEXT NOT NULL,
    scope_level     TEXT,
    jurisdiction_id UUID,                              -- soft-ref to jurisdictions.id
    industry_tag    TEXT,
    template_body   TEXT,
    citation        TEXT,
    source_url      TEXT,
    source_tier     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    verified_at     TIMESTAMP,
    UNIQUE NULLS NOT DISTINCT (company_id, policy_key, scope_level, jurisdiction_id, industry_tag)
);
CREATE INDEX idx_cpt_lookup ON compliance_policy_template(policy_key, scope_level, jurisdiction_id);
```

> `UNIQUE NULLS NOT DISTINCT` requires **PostgreSQL 15+**. Confirmed safe:
> `credential_requirement_templates` (migration `z1a2b3c4d5e6`) already
> uses it in prod. Note the dependency in the migration docstring.

> **`cc_requirement` carries no `graph_id`** — reach a graph's
> requirements by joining through `cc_category_node`. The read API's tree
> assembly already walks category nodes, so no denormalization needed.

`downgrade()`: `DROP TABLE` in reverse-FK order (`cc_requirement`,
`cc_policy`, `cc_credential`, `cc_category_node`, `cc_jurisdiction_node`,
`compliance_policy_template`, `cc_graph`).

> ⚠️ **DDL is a production-DB operation.** Per repo rules, `alembic
> upgrade head` is **not** run by Claude — the user runs it after
> reviewing this migration.

---

## 2. Builder — `server/app/core/services/compliance_graph.py` (new)

Two layers, mirroring the pure/IO split in `onboarding_dossier.py`.

### 2a. Pure planner (unit-testable, no DB)

```python
def plan_compliance_graph(dossier: dict) -> dict:
    """Dossier dict -> node plan. No IO. Parent links via local keys.

    Returns:
      {
        "jurisdiction_nodes": [
          {"key": (level,state,county,city), "parent_key": <key|None>,
           "level","name","state","county","city","source"}
        ],
        "category_nodes":  [{"category_key","juris_key","category_slug","scope_level","reason","source","ingest_status"}],
        "credentials":     [{"juris_key|None","kind","slug","name","issuing_authority",
                             "scope_level","renewal_period_months","applies_to_role","source"}],
        "policies":        [{"juris_key|None","policy_key","name","scope_level","reason","source"}],
        "requirements":    [{"category_key","jurisdiction_requirement_id|None",
                             "requirement_key|None","status"}],   # ← seeded from coverage (§2c)
      }
    """
```

**Jurisdiction tree.** Sources: `scope.applicable_jurisdictions` +
distinct `(state,county,city)` from `locations`. Algorithm:
1. Always create a `federal` root: `key=("federal",None,None,None)`,
   `name="Federal"`, `parent_key=None`.
2. For each distinct `state` → a `state` node, parent = federal root.
3. For each distinct `(state,county)` with county → a `county` node,
   parent = its state node.
4. For each distinct `(state,county,city)` with city → a `city` node,
   parent = county node if present else state node.
5. Dedup every level by its key. `name` = the most specific component
   (city, else county, else state, else "Federal"). `source` =
   `location` if it came only from `locations`, else `dossier`.

**Attaching leaves to a jurisdiction node** — helper
`_match_juris_key(level_or_scope, item, juris_keys)`:
- `federal` (or unmatched/`specialty`) → federal root key.
- `state`/`county`/`city` → the most specific existing node for the
  item's `state`/`county`/`city`; if the named node wasn't built (e.g.
  category says `state` but no state in scope), **fall back to federal
  root** (never drop a leaf).

**Category nodes.** From `scope.compliance_categories` (source `dossier`)
+ `ai_suggestions.suggested_compliance_categories` (source
`ai_suggestion`). Categories use the `scope` field (map to
`scope_level`). Attach via `_match_juris_key`. Each gets a stable local
`category_key` (e.g. `(category_slug, scope_level)`) so requirements can
reference it. `ingest_status` set in §2b from coverage.

**Credentials.** Flatten three lists into `cc_credential` rows:
- `scope.required_certifications` → `kind="certification"`
- `scope.required_licenses` → `kind="license"`
- `scope.required_credentials` → `kind="credential"` (carry
  `applies_to_role`)
- `ai_suggestions.suggested_certifications`/`suggested_licenses` →
  `source="ai_suggestion"`, kind cert/license (no scope_level/renewal in
  suggestions — leave null).
`scope_level` of `federal`/`specialty`/null → `juris_key = None`
(graph-wide); `state` → state node via `_match_juris_key`.

**Policies.** `scope.required_policies` → `cc_policy` (`policy_key=slug`).
`scope_level` federal/specialty/null → `juris_key=None`; else matched.

### 2b. Coverage seeding (Issue 1 — the dedup, live in P1)

`coverage` is the resolved mapping `map_to_bank` already produced; the
planner turns it into `requirements` + sets each category's
`ingest_status`. **No ingestion, no network — pure dict work.**

- `coverage.covered[]` → one `requirements` entry per item:
  `jurisdiction_requirement_id = item["requirement_id"]` (the shared
  `jurisdiction_requirements` row — the dedup link), `status="ingested"`,
  attached to the category node matching `category_slug`.
- `coverage.gaps[]` → `requirements` entry with
  `jurisdiction_requirement_id=None`, `status="pending"` (the P2
  worklist). Use `build_missing_id` semantics (`onboarding_scope_ai.py`)
  for `requirement_key` if useful.
- A `cc_category_node`'s `ingest_status` = `ingested` if **all** its
  covered, `pending` if any gap, else `pending` (default). So the graph
  shows covered-vs-gap immediately.
- **Requirement → category match key is `(category_slug, scope_level)`,
  not slug alone** — the same slug (e.g. `osha_general`) can exist at both
  `federal` and `state` scope; a requirement attaches to the category
  node at its own scope.
- **Synthesis + placement (covered items lack geo).** `ResolvedScope*`
  shapes (verified): `covered` items carry `category_slug` +
  `scope_level` + `location_id` but **no** `state`/`county`/`city`;
  `gaps` carry full `state`/`county`/`city`. Rule:
  - If a `(category_slug, scope_level)` category node already exists →
    attach the requirement there.
  - Else **synthesize** a category node (source `dossier`, so no coverage
    row is dropped). Placement: **gaps** → `_match_juris_key(scope_level,
    gap)` using their own state/county/city (precise — these are the
    actionable worklist). **covered** (no geo) → federal root when
    `scope_level='federal'`, else the node for the company's sole state if
    exactly one state node exists, else federal root. (Covered items are
    already resolved/linked, so their node placement is cosmetic — never
    drop them, but don't fabricate a geography we don't have.) The pure
    planner stays DB-free: gaps' geo is in the dossier; covered fall back
    by state-count, no `location_id` lookup needed.

`coverage.ambiguous` is **not** seeded into the graph in P1 (it needs
human disambiguation first); it stays visible in the dossier/report. Note
in the graph view as an "N ambiguous — resolve in wizard" banner.

### 2c. IO writer

```python
async def build_company_compliance_graph(
    conn, *, company_id: UUID, session_id: UUID | None,
    dossier: dict, built_by: UUID | None,
) -> UUID:
    """Materialize plan_compliance_graph(dossier) into cc_* rows.
    Versioned: supersedes prior graphs for the company. Returns graph_id."""
```

Wrap steps 2–8 in an explicit `async with conn.transaction():` (the
builder owns its own atomic unit; see §3a — it runs on its own
connection, since `finalize_session` itself uses no wrapping
transaction).
1. `plan = plan_compliance_graph(dossier)`.
2. `next_version = (SELECT COALESCE(MAX(version),0)+1 FROM cc_graph WHERE company_id=$1)`.
3. `UPDATE cc_graph SET status='superseded' WHERE company_id=$1 AND status<>'superseded'`.
4. `INSERT cc_graph (..., version=next_version, status='ready',
   built_at=NOW(), built_by)` → `graph_id`.
5. Insert jurisdiction nodes **parent-first** (federal → state → county →
   city), building `key -> uuid` map; set `parent_id` from the map.
   Soft-resolve `jurisdiction_id`:
   `SELECT id FROM jurisdictions WHERE city=$ AND state=$` (or
   state-level match) — best-effort, null if absent. **Read-only** against
   `jurisdictions`; no writes there.
6. Insert `cc_category_node`, `cc_credential`, `cc_policy` rows, resolving
   `juris_key -> jurisdiction_node_id` (None → NULL where nullable;
   categories require a node, so None → federal root). Keep a
   `category_key -> uuid` map for step 8.
7. **Resolve cert/license `catalog_id` at build (Issue 4):** for
   `kind in (certification, license)`, `SELECT id FROM
   certifications_catalog/licenses_catalog WHERE slug=$1` and set
   `catalog_id` — finalize already upserted those rows, so the dedup link
   is free here. `kind='credential'`, `cc_policy.template_id`, and
   `cc_requirement.jurisdiction_requirement_id` for *gaps* stay NULL
   (resolved P2/P3).
8. **Insert `cc_requirement` rows from `plan["requirements"]` (Issue 1):**
   `category_node_id` from the `category_key` map;
   `jurisdiction_requirement_id` + `status` straight from the plan
   (covered → the shared row id + `ingested`; gaps → NULL + `pending`).
   This is the live dedup link to `jurisdiction_requirements` — the P1
   payoff.
9. Return `graph_id`.

---

## 3. Route changes — `server/app/core/routes/admin_onboarding.py`

### 3a. Finalize hook — auto-build, best-effort, **build-once** (Issue 3)
`finalize_session` uses **no wrapping `conn.transaction()`** (asyncpg
autocommits per statement), so its writes are durable once the `async
with get_connection()` block exits. After that block returns, build the
graph on a **separate connection**, wrapped so failure can't affect
finalize (which already returned its writes):

```python
# after finalize's `async with` block exits; company_id/dossier/session_id
# /current_user all in scope
try:
    async with get_connection() as gconn:
        # build-once: skip if this session already has a graph (finalize
        # is idempotent + re-runnable — don't inflate versions on re-run).
        exists = await gconn.fetchval(
            "SELECT 1 FROM cc_graph WHERE source_session_id=$1 LIMIT 1", session_id)
        if not exists:
            await build_company_compliance_graph(
                gconn, company_id=company_id, session_id=session_id,
                dossier=dossier, built_by=current_user.id,
            )
except Exception:
    logger.exception("compliance graph build failed for session=%s", session_id)
    # finalize already succeeded; surface via the build-graph retry button
```
Rationale: finalize is documented idempotent ("re-running rewrites the
same rows"). Auto-build is therefore **build-once per session**;
intentional rebuilds go through the explicit button (§3b), which always
bumps the version. Legacy `company_compliance_scope` / cert / license
writes (lines 768–844) are **unchanged** — that is the dual-write.

### 3b. `POST /onboarding/sessions/{session_id}/build-graph`
Auth: `require_master_admin` + per-creator 403 (reuse
`_load_owned_session`). Loads the session, gets the dossier via
`_dossier_from_row`, calls `build_company_compliance_graph` → returns
`{graph_id, version, counts}`. **Always builds a new version** (this is
the deliberate "Rebuild" path + retry after a failed auto-build). 400 if
the session has no `company_id` yet (company must exist first).

### 3c. `GET /onboarding/sessions/{session_id}/graph`
Same auth (reuse `_load_owned_session`). Loads the **latest version for
this session**: `SELECT … FROM cc_graph WHERE source_session_id=$1 ORDER
BY version DESC LIMIT 1` (session-scoped, not company-scoped — a company
may have multiple onboarding sessions, Issue 5). Fetches all nodes for
that `graph_id`, assembles a nested tree, returns
`ComplianceGraphResponse`. **404** if no graph exists → UI shows the
empty "Build architecture" state.

Node assembly: return a **flat** `nodes` list, each `cc_jurisdiction_node`
carrying `parent_id` + its own leaves — `cc_category_node` (+ its
`cc_requirement` rows joined by `category_node_id`, LEFT JOIN
`jurisdiction_requirements` for `title`/`current_value` on covered ones) /
`cc_credential` / `cc_policy` bucketed under their `jurisdiction_node_id`;
null-juris credentials/policies go in the top-level `graph_wide` bucket.
The flat list + `parent_id` lets the UI both render the tree and walk
*up* for a location's inherited (effective) set — inheritance is computed
client-side (§5b), no extra endpoint.

---

## 4. Models — `server/app/core/models/admin_onboarding.py`

**Flat node list + `parent_id`**, not a nested tree — so the UI can both
render the hierarchy AND walk *up* from any node to compute a location's
inherited (effective) set (§5). Each requirement carries display fields
LEFT-JOINed from the shared `jurisdiction_requirements` row (covered only;
gaps have nulls).

```python
class CCRequirementNode(BaseModel):
    id: str; status: str                                  # ingested (covered) | pending (gap)
    jurisdiction_requirement_id: Optional[str] = None     # the shared-bank link (dedup)
    requirement_key: Optional[str] = None
    title: Optional[str] = None                           # ← joined from jurisdiction_requirements
    current_value: Optional[str] = None                   # ← joined (covered only)

class CCCategoryNode(BaseModel):
    id: str; jurisdiction_node_id: str
    category_slug: str; scope_level: Optional[str] = None
    reason: Optional[str] = None; source: str; ingest_status: str
    requirements: list[CCRequirementNode] = Field(default_factory=list)

class CCCredentialNode(BaseModel):
    id: str; jurisdiction_node_id: Optional[str] = None
    kind: str; slug: str; name: str
    issuing_authority: Optional[str] = None; scope_level: Optional[str] = None
    renewal_period_months: Optional[int] = None
    applies_to_role: Optional[str] = None; source: str; ingest_status: str
    catalog_id: Optional[str] = None                      # resolved cert/license (P1) — the dedup link

class CCPolicyNode(BaseModel):
    id: str; jurisdiction_node_id: Optional[str] = None
    policy_key: str; name: str; scope_level: Optional[str] = None
    reason: Optional[str] = None; source: str; ingest_status: str
    template_id: Optional[str] = None

class CCJurisdictionNode(BaseModel):
    id: str; parent_id: Optional[str] = None              # ← walk up for inheritance
    level: str; name: str
    state: Optional[str] = None; county: Optional[str] = None; city: Optional[str] = None
    jurisdiction_id: Optional[str] = None; source: str
    categories: list[CCCategoryNode] = Field(default_factory=list)
    credentials: list[CCCredentialNode] = Field(default_factory=list)
    policies: list[CCPolicyNode] = Field(default_factory=list)

class CCLocationRef(BaseModel):
    """A company's real business_location, mapped to the graph node that
    governs it — powers the location drill-down (§5)."""
    id: str; name: Optional[str] = None
    city: Optional[str] = None; county: Optional[str] = None; state: Optional[str] = None
    jurisdiction_node_id: str                             # most-specific node matching this location

class CCGraphMeta(BaseModel):
    id: str; version: int; status: str
    built_at: Optional[str] = None; source_session_id: Optional[str] = None

class ComplianceGraphResponse(BaseModel):
    graph: CCGraphMeta
    company: dict                                          # name/industry/specialty for the header
    nodes: list[CCJurisdictionNode]                       # FLAT; UI builds tree + ancestry via parent_id
    locations: list[CCLocationRef]                        # the company's locations → node mapping
    graph_wide_credentials: list[CCCredentialNode] = Field(default_factory=list)
    graph_wide_policies: list[CCPolicyNode] = Field(default_factory=list)
    counts: dict[str, int]  # jurisdictions/categories/credentials/policies/requirements_covered/requirements_gaps/ambiguous
```

The read API (§3c) computes `locations` by fetching the company's
`business_locations` (real, `is_company_wide=FALSE`) and matching each to
a node by a **prefix walk, most-specific first** — try the city node for
`(state,county,city)`; else the county node for `(state,county)`; else
the state node for `(state)`; else the federal root. So a Chicago, IL
location with no city node in the graph maps to the **Illinois state
node** (not federal). (Mirrors the state-first matching
`finalize_session` uses at lines 749–764, extended to return the nearest
ancestor that exists.)

---

## 5. Frontend

### 5a. `client/src/api/adminOnboarding.ts`
Mirror the response models as TS types (`CCJurisdictionNode`,
`CCRequirementNode`, `CCLocationRef`, `ComplianceGraph`, …). Add:
```ts
getGraph:   (id) => api.get<ComplianceGraph>(`${BASE}/sessions/${id}/graph`),
buildGraph: (id) => api.post<{graph_id:string;version:number;counts:Record<string,number>}>(
                      `${BASE}/sessions/${id}/build-graph`),
```

### 5b. `ComplianceGraphView.tsx` (new) — **navigable, drill-down by location**
Route `/admin/onboarding/:sessionId/graph`. This is the "view after the
fact" surface — the explicit goal: *click the business → click their
Chicago location → see what's specific to that location.* Reuse
`GapAnalysisReport.tsx`'s visual language.

**Two-pane layout:**

- **Left rail — navigator.**
  - **Locations** list at top (from `resp.locations`): the company's real
    locations (e.g. "Chicago Clinic", "Austin Office"). Click one → focus
    its `jurisdiction_node_id`. This is the primary entry the user asked
    for.
  - **Jurisdiction tree** below: build the tree from the flat `nodes` via
    `parent_id`; render indented Federal → State → County → City,
    collapsible. Click any node → focus it. (Same focus mechanism as a
    location; a location is just a shortcut to its city node.)

- **Right pane — focused jurisdiction.** For the focused node, show its
  **effective compliance set**, split into two clearly-labeled groups:
  1. **Specific to {node name}** — leaves attached **at** this node
     (`categories` + their `requirements`, `credentials`, `policies`).
  2. **Inherited** — walk `parent_id` up to the federal root; show each
     ancestor's leaves grouped under its label ("Federal", "Illinois",
     "Cook County"). So focusing the **Chicago** node shows Chicago-
     specific items PLUS everything inherited from Cook County, Illinois,
     and Federal = the full set that location must satisfy.
  - Each leaf row carries an `ingest_status` badge: **covered**
    (`ingested`, green — a live link to the shared bank) vs **gap**
    (`pending`, amber — P2 worklist). Category rows show
    `covered / total` requirement counts from their `requirements`.
  - Default focus on load = federal root (the whole company view).

- **Header:** company name + graph `version` + `status` chip +
  **Build / Rebuild architecture** button (`buildGraph` → refetch). If
  `resp.counts.ambiguous > 0`, a banner: "N ambiguous — resolve in the
  wizard." 404 → empty state with a single **Build architecture** button.

- **Count banner:** jurisdictions · categories · credentials · policies ·
  covered · gaps.

Inheritance is computed **client-side** by walking `parent_id` — no extra
endpoint. `graph_wide_credentials`/`graph_wide_policies` (null-juris) show
under the federal root's "Specific" group.

**Focus is URL state** — store the focused node/location in the query
string (`?location=<business_location_id>` or `?node=<juris_node_id>`,
via `useSearchParams`). So a Chicago drill-down is a shareable link and
survives refresh; default (no param) = federal root.

### 5c. Navigation entry + links + route
- Register the route in `client/src/App.tsx` next to the report route.
- **Entry ("click the business")**: `pages/admin/AdminOnboarding.tsx`
  index lists onboarding sessions = the businesses. Add a **"Compliance
  architecture"** link/badge on each finalized row → its graph view. (A
  dedicated company-wide Compliance index that lists *all* companies with
  a graph — independent of onboarding sessions — is a fast follow noted
  in §8; the session list is the business list for P1.)
- `GapAnalysisReport.tsx`: add "View compliance architecture →" link to
  `/admin/onboarding/:id/graph`.
- AdminOnboarding done step (`Steps.tsx`): graph link beside the report
  link.

---

## 6. Tests

`server/tests/admin_onboarding/test_compliance_graph.py` (new) — pure,
no DB, exercising `plan_compliance_graph`. **There is no `_sample_session`
dossier fixture** in `test_admin_onboarding.py` (its tests build pieces
inline) — so construct a sample dossier dict in this file: an ABA company
with a location carrying **`state="IL"`, `county="Cook"`, `city="Chicago"`
all three** (so the asserted Chicago→Cook County→Illinois parent chain
actually gets built), `scope` populated (incl. a BCBA credential with
`applies_to_role`, a policy), AND a `coverage` block with ≥1 `covered`
(with a `requirement_id`) + ≥1 `gap`.

- Tree: federal root exists; a state node per dossier state; Chicago is a
  city node under Cook County under Illinois (parent chain correct, so the
  UI's ancestry walk works); no orphan leaves (every category attaches to
  a built node or the federal root).
- Counts: `category_nodes` == categories + suggested_categories;
  credentials == certs + licenses + credentials (+ suggested); policies
  == required_policies.
- `applies_to_role` preserved on the BCBA credential row.
- **Coverage seeding (Issue 1):** `requirements` has one entry per
  `coverage.covered` with `status="ingested"` +
  `jurisdiction_requirement_id == requirement_id`, and one per
  `coverage.gaps` with `status="pending"` + null link. A category that is
  fully covered → node `ingest_status="ingested"`; one with a gap →
  `pending`. A `covered.category_slug` absent from the AI scope →
  synthesized category node (no coverage row dropped).
- Edge: empty `applicable_jurisdictions` but populated `locations` → tree
  still built from locations; empty everything → just the federal root.

Run: `cd server && ./venv/bin/python -m pytest tests/admin_onboarding/ -q`
Frontend typecheck: `cd client && npx tsc --noEmit`.

---

## 7. End-to-end verification (manual; needs DB tunnel + migration)

1. **User reviews + runs** `alembic upgrade head` (creates `cc_*` +
   `compliance_policy_template`).
2. Finalize a wizard session (e.g. the ABA / behavioral-health company)
   OR open the graph view and click **Build architecture**.
3. Confirm in DB: one `cc_graph` (version 1, `status='ready'`);
   `cc_jurisdiction_node` has a federal root + the company's state(s)/
   county/city; `cc_requirement` rows seeded from coverage (covered =
   `status='ingested'` with a `jurisdiction_requirement_id`; gaps =
   `pending`); cert/license `cc_credential.catalog_id` resolved; legacy
   `company_compliance_scope` rows still present (dual-write intact).
4. **Re-run finalize** → **no** new `cc_graph` version (build-once guard,
   Issue 3).
5. `GET /graph` → tree renders. **Click the Chicago location** → right
   pane shows Chicago-specific items + inherited Federal/Illinois/Cook
   County; covered leaves green, gaps amber.
6. Click **Rebuild** → `cc_graph` version 2 created, version 1 →
   `superseded`; latest renders.

---

## 8. Out of scope (later phases — see design doc)

- **P2** requirement ingestion + **resolve-before-research dedup**:
  dispatcher resolves each `cc_category_node` to a shared
  `jurisdiction_requirements` row by `(jurisdiction_id, category)`;
  researches (`_upsert_requirements_additive` /
  `run_medical_compliance_research` / `run_oncology_research` /
  `run_compliance_check_task`) + writes the shared bank ONLY on a miss;
  links the leaf via `cc_requirement.jurisdiction_requirement_id`.
  Per-node live status.
- **P3** credential + policy ingestion. Credentials resolve `slug` →
  shared catalog (`certifications_catalog` / `licenses_catalog` /
  `credential_types`) into `cc_credential.catalog_id`. Policies resolve
  into `compliance_policy_template` (shared library first, else mint a
  company-specific tier-row) and link `cc_policy.template_id`. Reuses
  `credential_template_service`, `policy_draft_service`,
  `handbook_service`.
- **P4** freshness loop + legislation re-stale (graph-keyed).
- `dispatch-research` stub, owner-invite loop — independent backlog.
- Cross-company **slug normalization** (so `bcba` vs `bacb_bcba` resolve
  to one shared catalog/template row) — needed once the P2/P3 dedup
  dispatcher lands.
- **Company-wide Compliance index** — a `/admin/compliance` (or similar)
  page listing *all* companies that have a `cc_graph`, independent of
  onboarding sessions, as the durable "browse every business" entry. P1
  uses the onboarding-session list as the business list; this is the fast
  follow once graphs exist for many companies.
