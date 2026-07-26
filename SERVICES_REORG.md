# Services Directory Reorg (2026-07-25)

## Why

`server/app/matcha/services/` had grown to 141 flat files (~62,000 LOC), no
internal structure. Hard to navigate, hard to tell what's related to what.

## What changed

Split into 18 domain subpackages, file basenames unchanged:

| Package | Contents |
|---|---|
| `ir/` | IR/OSHA incident services + `naics_titles` |
| `er/` | Employee-relations services + `labor_relations_ai` |
| `discipline/` | Progressive discipline engine + compliance + PDF |
| `leave/` | Leave-of-absence + accommodations |
| `scheduling/` | Shift scheduling + Fair Workweek |
| `training/` | Training assignment/grading/PDF |
| `onboarding/` | Onboarding orchestration + Google Workspace/Slack provisioning |
| `hris/` | Gusto/Finch HRIS sync |
| `benefits/` | Benefits eligibility/enrollment |
| `workforce/` | Workforce-compliance trackers + pay equity/wage benchmarks/flight risk |
| `risk_analytics/` | Risk-assessment, benchmark, cohort, anomaly, Monte Carlo |
| `matcha_work/` | Projects/threads/journals/kanban/elements (~26 files) + `matcha_work_document/` package |
| `billing/` | Stripe billing, token budget, entitlements, model pricing |
| `pilots/` | Analysis/Handbook/Ask-HR/HR pilots, legal research + `legal_defense/` + `analysis_packs/` packages |
| `broker/` | Broker-facing services, EPL/risk-index/submission readiness |
| `insurance/` | WC/loss-run/COI/limit-adequacy/risk-transfer/BLS rates |
| `property/` | Property SOV/cat/exposure/risk |
| `interviews/` | Interview transcript analyzers |

Stayed at `services/` root (genuinely cross-domain, imported everywhere):
`claims_readiness`, `notification_service`, `signature_provider`, `precedent_common`.

Deleted `job_sources/` (dead — only `.pyc` files left, no source).

Folded the 3 pre-existing subpackages in: `legal_defense/` → `pilots/`,
`analysis_packs/` → `pilots/`, `matcha_work_document/` → `matcha_work/`.

## How it was done

1. **Domain map** — every basename assigned to exactly one domain, validated
   1:1 against the actual directory listing before touching anything.
2. **Move** — `git mv` per file into its domain dir (plain `mv` + re-add for
   the 3 untracked-at-the-time subpackages, since `git mv` no-ops on
   untracked dirs).
3. **Mechanical import rewrite** — a script rewrote every import site across
   `app/`, `tests/`, `scripts/`: absolute imports, relative imports at every
   routes depth, intra-services relative imports, string-literal patch
   targets in tests. Cross-domain multi-name imports (e.g.
   `from ...services import coterie_service, risk_to_rate`) were split by
   hand where the script couldn't safely do it.
4. **Bugs found and fixed along the way**, all caused by files nesting one
   level deeper than before:
   - A double-`services` string bug in the first regex pass (global sed fix).
   - Relative imports reaching *outside* `services/` (`config`, `database`,
     `core.*`, `models.*`, `routes.*`) needed +1 dot.
   - The `from ..services[.NAME]` spelling (explicit "services" after 2 dots)
     wasn't recognized by the first pass at all.
   - Indented/lazy `from . import X` (function-local) and comment-terminated
     bare imports (`from app.matcha.services import X as y  # noqa`) were
     missed by the anchored regexes.
   - Three services load a data file via `__file__`-relative paths
     (`wage_benchmark_service.py`, `benchmark_service.py`, `gmail_service.py`)
     — needed one more `dirname()`/`.parent` hop.
   - The 3 folded-in packages had their own cross-package relative imports
     (`legal_defense`'s refs to `claims_readiness` and `discipline_engine`)
     needing hand-fixed dot-depth.
5. **`ai_usage.py` cost-label fix** — its Gemini-cost attribution derives a
   label from the caller's module `__name__`. Added a *positional* strip
   (only the segment right after `app.matcha.services.`) rather than a global
   stopword, since several domain names (`broker`, `insurance`, `pilots`,
   `onboarding`) collide with existing `routes/` grouping-folder names and a
   global stopword would risk merging unrelated cost rollups. Net effect:
   every moved service's cost label is byte-identical to its pre-move label —
   zero fork in `ai_usage_log` history.
6. **Stragglers** — `scripts/wc_data/build_bls_rates.py` output path,
   `tellus/services/geo.py`'s documented `property_cat` import, root
   `CLAUDE.md` + `ir_incidents/CLAUDE.md` exact-path references, stale
   docstring mentions in a handful of tests.

## Verification

- Full repo `py_compile` clean.
- `import app.main` clean.
- Full test suite: **65 failed / 4332 passed — identical to the pre-reorg
  baseline** (diffed failure sets before/after; zero new failures, zero
  fixed-by-accident). The pre-existing failures (blog_pdf export, a few
  order-dependent suites, 4 known `spec_from_file_location` collection
  errors) are untouched by this change.

## Not done

- Not committed — left as a working-tree change for review.
- No new per-domain `CLAUDE.md` docs written (none were requested).
