# CLEANUP_PLAN.md — Completion Audit

**Date:** 2026-07-20 · **Method:** ultracode workflow — 56 adversarial verifiers (one per plan
item, A–M) + 2 global checks (boot route-count, client tsc) + synthesis. Each verifier read the
**actual tree**, not the doc; an item counts "done" only if the artifact was found in source.
Parent plan: [CLEANUP_PLAN.md](./CLEANUP_PLAN.md).

---

## 1. Headline verdict

The plan's stated implementation state was **accurate on 58 of 59 items**. Every
DONE/DEFERRED/PARTIAL/REJECTED claim held up under source inspection **except J7**, which was
marked DONE but shipped a runtime-breaking import bug. **That bug is now fixed** (commit
`362e677`) — so post-audit the plan is fully consistent with the tree.

**Tally:** 33 CONFIRMED_DONE · 22 CONFIRMED_DEFERRED · 3 PARTIAL (D2, D4, L2 — L2 self-declared) ·
1 BROKEN→FIXED (J7). Zero SURPRISE_DONE.

---

## 2. Red flags

### 🔴 J7 — was BROKEN (claimed DONE) → **FIXED**
The J7 dashboard-models foldout (`35b5a8c`) extracted 29 models into
`server/app/matcha/models/dashboard.py` but dropped `from uuid import UUID` **and** `Literal`
from the typing import. `from __future__ import annotations` turns annotations into strings, so
class definition + app import succeed and the route-count boot passes green — but at request time
`GET /dashboard` builds e.g. `PendingIncident(...)` / `EmployeeWageGapDetail(...)`, Pydantic
resolves the string annotation, and raises `PydanticUndefinedAnnotation: name 'UUID' is not
defined` → **500**.

- **Fix (`362e677`):** added `from uuid import UUID` and `Literal` to the typing import. All
  dashboard models now `model_rebuild()` clean.
- **Blast-radius check:** the other J7/J5 model foldouts — `provisioning/_models.py`,
  `broker/brokers/_models.py`, `core/models/admin.py` — were rebuild-checked and are clean. Only
  dashboard was affected.
- **Why the workflow's route-count didn't catch it:** boot exercises import, not instantiation.
  The audit's dedicated verifier reproduced the UUID failure; a follow-up full `model_rebuild()`
  sweep caught the second missing name (`Literal`) that the single repro missed.

### ⚠️ Partials (neither contradicts a DONE claim — both were UNKNOWN in the doc)
- **D2** — `DataTable.tsx` exists, adopted by **2** admin pages (Companies, BrokerTable), not 5;
  **FilterPills was never built** (zero hits).
- **D4** — shared `Modal.tsx` exists, adopted by **1** dialog (HRISSyncModal); **64 files** still
  hand-roll `fixed inset-0` overlays. Effectively unstarted.
- **L2** — self-declared PARTIAL, consistent: `render_pdf_async` landed (via J3) but the
  HTML-builder dedup (`REGISTER_PDF_CSS`, shared `esc()`, `stat_cells()`) is not done — `_esc()`
  still redefined 14×, `_PDF_CSS` still lives in `claims_readiness.py`.

### Minor wording imprecisions (intent fully met, no functional gap)
- **F4** — gate is `authFailed` (401/403), not literal `!me` — deliberate (avoids evicting a
  signed-in user on a 502). Fail-closed redirect present.
- **K3** — no `WizardShell.tsx` (only `WizardStepper.tsx`), but the substantive claim (shared
  stepper used by both wizards) is fully met.

---

## 3. Completion matrix

| Item | Claimed | Verified | Gap |
|---|---|---|---|
| **A** | DONE | ✅ CONFIRMED_DONE | none |
| **B** | DONE | ✅ CONFIRMED_DONE | none |
| **C** | DONE (30) | ✅ CONFIRMED_DONE | none (40 consumers, exceeds) |
| **D1** | DEFERRED | ✅ CONFIRMED_DEFERRED | register→checkout still copy-pasted 3×+ |
| **D2** | UNKNOWN | ⚠️ PARTIAL | FilterPills absent; DataTable 2/5 pages |
| **D3** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **D4** | UNKNOWN | ⚠️ PARTIAL | 1/65 dialogs on shared Modal |
| **E1** | DONE | ✅ CONFIRMED_DONE | none |
| **E2** | DEFERRED | ✅ CONFIRMED_DEFERRED | top-5 still monolithic, as claimed |
| **E3** | DONE | ✅ CONFIRMED_DONE | none |
| **E4** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **F1** | DONE | ✅ CONFIRMED_DONE | none |
| **F2** | DONE | ✅ CONFIRMED_DONE | none |
| **F3** | DONE | ✅ CONFIRMED_DONE | none |
| **F4** | DONE | ✅ CONFIRMED_DONE | wording (`authFailed` not `!me`); intent met |
| **F5** | SKIPPED | ✅ CONFIRMED_DEFERRED | none |
| **F6** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **F7** | DONE | ✅ CONFIRMED_DONE | none |
| **G1** | DONE | ✅ CONFIRMED_DONE | none |
| **G2** | DONE | ✅ CONFIRMED_DONE | none |
| **G3** | DONE | ✅ CONFIRMED_DONE | none |
| **G4** | DONE | ✅ CONFIRMED_DONE | none |
| **G5** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **G6** | DEFERRED | ✅ CONFIRMED_DEFERRED | instrument dup across 4 pages persists |
| **H1** | DONE | ✅ CONFIRMED_DONE | none |
| **H2** | DONE | ✅ CONFIRMED_DONE | none |
| **H3** | DEFERRED | ✅ CONFIRMED_DEFERRED | ~24 work/ dialogs still hand-roll |
| **H4** | DEFERRED | ✅ CONFIRMED_DEFERRED | line counts unchanged |
| **H5** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **I1** | DEFERRED | ✅ CONFIRMED_DEFERRED | none |
| **I2** | DONE | ✅ CONFIRMED_DONE | none |
| **I3** | DONE | ✅ CONFIRMED_DONE | none |
| **I4** | DEFERRED | ✅ CONFIRMED_DEFERRED | two StatCard impls still separate |
| **I5** | DEFERRED | ✅ CONFIRMED_DEFERRED | 3 IR panels repeat scaffold |
| **J1** | DONE | ✅ CONFIRMED_DONE | none (router/table out of scope) |
| **J2** | DONE | ✅ CONFIRMED_DONE | none |
| **J3** | DONE (−L2) | ✅ CONFIRMED_DONE | none |
| **J4** | DONE | ✅ CONFIRMED_DONE | none |
| **J5** | DONE | ✅ CONFIRMED_DONE | none |
| **J6** | DONE | ✅ CONFIRMED_DONE | none |
| **J7** | DONE | 🔧 **BROKEN → FIXED** (`362e677`) | missing `UUID`+`Literal` imports → now added |
| **J8** | REJECTED | ✅ CONFIRMED_DEFERRED | rejection holds (preambles genuinely distinct) |
| **J9** | DONE | ✅ CONFIRMED_DONE | none |
| **K1** | DEFERRED | ✅ CONFIRMED_DEFERRED | RegisterPageShell absent |
| **K2** | DEFERRED | ✅ CONFIRMED_DEFERRED | usePublicToken/PublicPageShell absent |
| **K3** | DONE | ✅ CONFIRMED_DONE | no WizardShell name; stepper met |
| **K4** | DEFERRED | ✅ CONFIRMED_DEFERRED | MetricStrip absent |
| **K5** | DEFERRED | ✅ CONFIRMED_DEFERRED | attestation triplicated |
| **L1** | DONE (5) | ✅ CONFIRMED_DONE | none (6 sites, exceeds) |
| **L2** | PARTIAL | ⚠️ PARTIAL (as claimed) | CSS/esc/stat_cells dedup not done |
| **L3** | DONE | ✅ CONFIRMED_DONE | none (dispatch gate is separate layer) |
| **L4** | DONE | ✅ CONFIRMED_DONE | none |
| **L5** | DONE | ✅ CONFIRMED_DONE | none |
| **L6** | DONE | ✅ CONFIRMED_DONE | none |
| **L7** | DEFERRED | ✅ CONFIRMED_DEFERRED | analyzer dedup not started (after J2) |
| **L8** | DONE | ✅ CONFIRMED_DONE | none |
| **L9** | DEFERRED | ✅ CONFIRMED_DEFERRED | resources.py/compliance.py still monolithic |
| **M1** | DONE | ✅ CONFIRMED_DONE | none |
| **M2** | DONE | ✅ CONFIRMED_DONE | none |

---

## 4. Truly remaining work

### (a) Intentional deferrals — still correct, no action implied
D1 (signup→checkout consolidation), D3 (pilot chat hook), E2 (god-component splits, top-5),
E4 (flatten pages/admin), F5 (externalRedirect), F6 (voice ws token), G5 (list virtualization),
G6 (simpler-pages instruments), H3 (work/ modal adoption), H4 (work/ hook extractions),
H5 (useOptimisticMessages), I1 (components/pilot scaffold), I4 (shared StatCard),
I5 (IRAnalysisPanel wrapper), J8 (grounding-prompt fragment — rejected on merit),
K1 (RegisterPageShell), K2 (usePublicToken), K4 (MetricStrip), K5 (SignatureAttestation),
L7 (ER/IR analyzer dedup), L9 (split resources/compliance). **All verified absent-as-intended.**

### (b) Real gaps vs a DONE-or-scoped claim
1. **J7** — ✅ **fixed** (`362e677`): `UUID` + `Literal` added to `matcha/models/dashboard.py`.
2. **D2** — FilterPills never built; DataTable on 2/5 admin pages. *(scoped work incomplete)*
3. **D4** — Modal migration 1/65 dialogs — effectively unstarted. *(scoped work incomplete)*
4. **L2** — PDF HTML-builder dedup outstanding: `_esc()` ×14, `_PDF_CSS` un-shared.
   *(self-declared partial)*

### Genuinely finished (structural/mechanical, verified at source)
Phases **A, B, C, E1, E3, F1–F4, F7, G1–G4, H1, H2, I2, I3, J1–J6, J9, K3, L1, L3–L6, L8, M1, M2**
— confirmed in the tree, several exceeding stated scope (C: 40 vs 30 consumers; L1: 6 vs 5 sites).
The heavy backend package splits (J5 admin, J6 handbook + compliance services, L5 IR cards,
L6 matcha_work_document) all import cleanly and are reflected in the route count.

---

## 5. Global health
- **Boot / route count:** PASS — exactly **1858** routes (expected post-split). `py_compile` clean
  on both split package dirs. *Caveat that bit J7:* boot exercises import, not instantiation —
  `from __future__ import annotations` deferred the dashboard `NameError` to request time, so a
  green route count masked a live 500. Instantiation-level checks (`model_rebuild()`) are the
  real gate for model foldouts.
- **Client tsc:** CLEAN — `npx tsc -p tsconfig.app.json --noEmit` exited 0, no errors.

---

## Appendix — per-item evidence (condensed)

Selected source citations from the verifiers (full run in the workflow journal).

- **A** — all A-list paths absent; `grep IrAnalysisPanel|TimelineConstructor|ComplianceOverviewTab|PinnedResourcesPanel|resourceCatalog` → 0 hits; commit `f60f1d0`.
- **B** — `api/sse.ts` exports `consumeSSE`/`postSSE`/`streamPilotChat`; 20 importers; no raw `new EventSource`/`getReader()` outside it.
- **C** — `hooks/useAsync.ts` + `useAsyncAction`; 40 consumer files; `useAsync.test.tsx`.
- **D2** — `ui/DataTable.tsx` imported by Companies + BrokerTable only; `FilterPill` → 0 hits; commit `970a156`.
- **D4** — `ui/Modal.tsx` full-featured; only `HRISSyncModal.tsx` adopts; 64 files still `fixed inset-0`.
- **E3** — `pages/admin/Settings.tsx` 0 `fetch(`; routes via `adminSettingsApi.*`; commit `7acf459`.
- **F1** — `sandbox=""` on all 5: DealFlow:443, LiteEditionPanel:112, BrokerTab:241, BookPricingTab:278, FullDealTab:199.
- **F2** — `analysis-pilot/MetricViews.tsx:27` `<img src=data:image/svg+xml;utf8,…>`; no `dangerouslySetInnerHTML`.
- **F3** — `CitationSources.tsx:87` `safeUrl(c.source_url)`; `utils/safeUrl.ts` present.
- **G1** — `Hero.tsx:12` lazy `ProductCarousel`; `index.tsx:15` lazy `PricingContactModal`; both `Suspense`.
- **G4** — `Toast.tsx:51` `useMemo(() => ({toast}), [toast])`.
- **H1** — `work/routes/WorkRouteTree.tsx:29`; WorkRoutes/WerkRoutes are one-line delegators.
- **H2** — `work/api/baseSocket.ts:36 abstract class BaseSocket`; thread/project/channel sockets extend it.
- **I2** — `utils/format.ts` `relativeTime`/`formatMoney`/`formatBytes` + `format.test.ts`; 10 importers.
- **I3** — `ui/badgeMaps.ts` severity/priority/confidence/determination; adopted by ER panels.
- **J1** — `pre_termination_service.py` + `jina_reader.py` gone; `config.jina_api_key` gone; `penalty_facts.py` kept (flagged); commit `d35eb37`.
- **J2** — `genai_client.get_genai_client` used in 52 files; `genai.Client(` only in the factory.
- **J3** — `pdf.py` `render_pdf`/`render_pdf_async`/`safe_url_fetcher`; no `HTML(string=…).write_pdf` outside it; 29 files use it.
- **J4** — `audit_log.py:insert_audit_log`; ir/er/accommodations wrappers delegate.
- **J5** — `core/routes/admin/` 9 modules + `_shared` + `__init__`; router = 172 routes; commit `d197318`.
- **J6** — `handbook_service/` + `compliance_service/` packages; no `.py` twins; both resolve to `__init__.py`.
- **J7** — provisioning/ + broker/brokers/ + models/dashboard.py present; `UUID`/`Literal` missing (masked by future-annotations) → 500 at request time → **fixed `362e677`**.
- **J8** — no shared preamble constant; each `build_corpus` preamble names its own cid namespaces + "NEVER invent" list (analysis/broker/handbook/legal). Rejection holds.
- **J9** — sole defs in `matcha/models/audit_log.py`; er_case.py + accommodation.py re-export shim.
- **K3** — `ui/WizardStepper.tsx` used by IrOnboardingWizard:140 + MatchaXOnboardingWizard:121.
- **L1** — `core/services/model_json.py` (`strip_json_fence`/`clean_model_json`/`parse_model_json`); 6 sites migrated; loud-failure sites deliberately skipped.
- **L2** — `render_pdf_async` present; no `REGISTER_PDF_CSS`/`stat_cells`/shared `esc`; `_esc()` ×14; `_PDF_CSS` in claims_readiness.py.
- **L3** — `workers/utils.py` `scheduler_settings_row`/`scheduler_enabled`; 21 task files use them; no inline gate in tasks/ (celery_app dispatch gate is a separate layer).
- **L4** — `matcha/models/benefits.py` gone; 0 importers; commit `c1c6d95`.
- **L5** — `ir_incidents/_cards.py` (14 `build_*_card` factories); `_shared.py` 1878→1475; commit `10f83f4`.
- **L6** — `matcha_work_document/` package (`_coerce`/`_email_html`/`_storage`/`_tokens`); no `.py` twin.
- **L8** — `core/services/company_contacts.py` shared `_CONTACTS_SQL`; ir_deadline_alerts + leave_agent + compliance_service submodules consume it.
- **M1** — `core/services/scoped_auth.py:make_token_helpers`; tellus/cappe auth.py are ~29-line wrappers.
