# client/src/api — Core Hygiene Refactor (full technical plan)

> **Status (verified 2026-07-26): NOT IMPLEMENTED.** The nested
> `client/src/api/compliance/compliance/` folder this plan dissolves is still present (15
> files), and none of its 7 new files exist. Build order: **no fixed slot** — touches only
> `client/src/api/` (plus single-line import edits in `client/src/work/`), conflicts with
> nothing, and its 10 steps are each commit-sized and leave `tsc` green. Use as filler
> between the server-side items. Numbered last for neutrality, not low value.

## Context

`client/src/api` (71 files, ~6,940 lines) surveyed for efficiency/refactoring/organization. Layer is fundamentally healthy — every domain module uses the shared `api` helper from `client.ts`, all SSE goes through `sse.ts`, zero dead files — but it accumulated: ~145 lines of domain code bolted onto `client.ts`, the API base URL redeclared 36× in 4 spellings, two structurally-identical error classes forcing callers to know the transport, pilot types redeclared 3–4×, a triple-nested `api/compliance/compliance/` folder, a fragile re-export shim, ambiguous duplicate basenames, one misfiled root module, and 8 call sites outside the layer hand-rolling what helpers already do.

**Scope (user-chosen): core api/ hygiene + the 8 offending outside call sites.** Not in scope: `api/ir`/`api/er` creation (73 inline literals), `/admin` wrapping (107 sites), type-hoisting to `types/` (39 files / 344 declarations — client/CLAUDE.md defers it to its own PR: "don't fix them piecemeal"). Never touch `client/src/cappe/` or `client/tellus/`. `client/src/work/` gets path-only import updates at documented crossing points.

**Behavior contract: zero behavior changes**, except three adjudicated micro-fixes called out inline (trailing-slash normalization, ER phantom-download fix, IR export error-message format) — each flagged in its step.

**Verified environment facts** (load-bearing):
- `client/tsconfig.app.json`: `moduleResolution: "bundler"` (directory → `index.ts` resolution works for both tsc and Vite), `useDefineForClassFields: true` (a subclass redeclaring a parent-assigned field clobbers it to `undefined`), `verbatimModuleSyntax: true` (type-only imports MUST use `import type`), `strict`, `noUnusedLocals`.
- Typecheck command: `cd client && npx tsc -p tsconfig.app.json --noEmit`. NEVER bare `npx tsc --noEmit` (root tsconfig is `files: []` + references — always exits 0).
- Tests: vitest configured; `npm run test:run`.
- `client.ts` does NOT import `sse.ts` (so `sse.ts → client.ts` imports are cycle-free). `client.ts` DOES import `errorReporter.ts` (line 2) — errorReporter must never import back.

Each step is a commit-sized chunk that leaves tsc green. Suggested commit order = step order.

---

## File inventory

**Created (7):**

| path | contents |
|---|---|
| `client/src/api/handbook/handbook.ts` | `handbooks` object (30 methods) from client.ts:159–251 |
| `client/src/api/handbook/policies.ts` | `policies` object (5 methods) from client.ts:253–272 |
| `client/src/api/admin/landingMedia.ts` | `landingMedia` + 4 `Landing*` types from client.ts:360–397 |
| `client/src/api/settings/settings.ts` | `uploadAvatar` from client.ts:354–358 |
| `client/src/api/compliance/index.ts` | 15-line barrel (replaces `compliance.ts`) |
| `client/src/data/complianceLabels.ts` | moved `labels.ts` (git mv) |
| `client/src/api/client.test.ts` | new: `API_BASE` normalization + `ApiError` shape tests |

**Moved via `git mv` (18):** 15 files `api/compliance/compliance/*.ts` → `api/compliance/*.ts` (2 renamed: `key-coverage.ts`→`keyCoverage.ts`, `quality-audit.ts`→`qualityAudit.ts`; `labels.ts`→`data/complianceLabels.ts`); `api/broker-chat/brokerChat.ts` → `api/broker-chat/companyBrokerChat.ts`; `api/resourcePins.ts` → `api/resources/resourcePins.ts`.

**Deleted (2):** `api/compliance/compliance.ts` (barrel, replaced by `index.ts`), `api/admin/adminOnboarding.ts` (shim).

**Edited:** `api/client.ts`, `api/sse.ts`, `api/sse.test.ts`, 5 pilot modules, 25 matcha BASE-redeclaration files, 4 work files, 39 compliance-barrel consumers, 8 extracted-symbol consumers, 4 hand-rolled call sites, 3 localStorage sites (comments only), `client/CLAUDE.md`.

---

## Step 1 — Export `API_BASE`; kill 36 redeclarations

### 1a. `api/client.ts:4`

```ts
// before
const BASE = import.meta.env.VITE_API_URL ?? '/api'
// after — trailing-slash normalized once, exported for every consumer that
// must hand-roll fetch (SSE, public endpoints, beacons)
export const API_BASE = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')
```

Rename the 6 internal uses (`client.ts:13, 90, 105, 333, 338, 344`) `BASE` → `API_BASE`.

### 1b. Redeclaration sites — exact list (grep-verified)

Pattern per site: add `import { API_BASE } from '<rel>/api/client'`, delete the local const, rename local uses. Local const names vary — noted where non-`BASE`:

Top-level consts (matcha):
- `api/sse.ts:22` (`||` variant — see Risks)
- `utils/usageTracker.ts:13` (has `as string | undefined` cast — drop it)
- `components/landing/NewsletterHeroSection.tsx:4`
- `components/marketing/NewsletterSignup.tsx:4`
- `components/ir/IRCopilotPanel/helpers.ts:1` — **delete the exported `BASE` entirely**; sole consumer `useCopilotPanel.ts:7` (`import { BASE } from './helpers'`) switches to `import { API_BASE } from '../../../api/client'` (merge into its existing client.ts import at line 3). helpers.ts keeps its other exports.
- `hooks/useSidebarBadges.ts:5`
- `pages/ResetPassword.tsx:5`, `pages/BetaRegister.tsx:6`
- `pages/landing/Subscribe.tsx:5` (named `API`), `pages/landing/StartQualify.tsx:17` (double-quoted)
- `pages/auth/MatchaLiteSignup.tsx:8`, `pages/auth/ComplianceSignup.tsx:10`, `pages/auth/MatchaXSignup.tsx:7`, `pages/auth/ProductSignup.tsx:12`, `pages/auth/IrSignup.tsx:6`, `pages/auth/BusinessInviteRegister.tsx:6`
- `pages/shared/AnonymousReport.tsx:7`, `CandidateInterview.tsx:7`, `ExternalIntake.tsx:5`, `usePublicToken.ts:4`, `RequestInfoForm.tsx:6`, `LocationIntake.tsx:8`, `PublicHandbook.tsx:9`, `OfferSign.tsx:6`, `ERExportDownload.tsx:5`

In-function consts (matcha):
- `pages/Login.tsx:90` (`const baseUrl = … || '/api'`)
- `components/marketing/PricingContactModal.tsx:68` (`const apiBase = … || '/api';`)

Work app (documented shared-layer imports; path/const-only changes):
- `work/api/matchaWork/_base.ts:8` → `export const BASE = API_BASE` (keep the re-export — 3 intra-package consumers stay untouched)
- `work/api/channels.ts:212` (in-function) and `:369` (`const PUBLIC_BASE`, top-level) → both use imported `API_BASE`
- `work/api/baseSocket.ts:18` (in-function `base`; its `.replace(/\/api$/, '')` WS derivation works identically on the normalized value)
- `work/components/panels/ProjectPanel/useProjectPanel.ts:228, 245` (in-function)

**Deliberately excluded:**
- `api/errorReporter.ts:10` — client.ts imports errorReporter (client.ts:2); importing `API_BASE` back = module cycle (TDZ hazard). Keep local const + comment: `// Deliberately duplicates client.ts API_BASE — importing it back would create a cycle.`
- `components/ir/IRExportModal.tsx:104`, `pages/app/er/ERCaseDetail.tsx:105` — lines deleted wholesale in Step 8; don't double-touch.
- All of `cappe/` (own client).

**Micro-behavior note (accepted):** the `||`→`??`-based shared constant differs only when `VITE_API_URL` is set to empty string (not a real config); trailing-slash strip FIXES the current `//api/...` double-slash bug at 34 of 36 sites.

Verify: tsc; `grep -rn VITE_API_URL client/src | grep -v cappe/` → exactly `api/client.ts:4` + `api/errorReporter.ts:10` (+ the two Step-8 sites until Step 8 lands).

---

## Step 2 — Extract domain code out of client.ts

All extracted methods map 1:1 onto exported `api.*` helpers. Verified: no PUT-with-FormData exists anywhere in the extracted code (`policies.create` is POST FormData → `api.upload`); `api.post(path, undefined)` sends no body, exactly matching the old bare `request(path, {method:'POST'})`.

### 2a. New `api/handbook/handbook.ts`

```ts
import { api } from '../client'
import type {
  HandbookListItem, HandbookDetail, HandbookCreate, HandbookUpdate,
  HandbookChangeRequest, HandbookDistributionResult, HandbookDistributionRecipient,
  HandbookAcknowledgementSummary, HandbookFreshnessCheck, HandbookCoverage,
  CompanyHandbookProfile, CompanyHandbookProfileInput, HandbookGuidedDraftRequest,
  HandbookGuidedDraftResponse, HandbookWizardDraft, HandbookWizardDraftState,
  HandbookPublishResponse, HandbookShareLink, HandbookSection,
} from '../../types/handbook'

export const handbooks = { /* 30 methods, signatures below */ }
```

Method-by-method mapping (paths/bodies/return types byte-identical to client.ts:181–251):

| method signature | new impl |
|---|---|
| `list: () => Promise<HandbookListItem[]>` | `api.get<HandbookListItem[]>('/handbooks')` |
| `get: (id: string) => Promise<HandbookDetail>` | `api.get(…/handbooks/${id})` |
| `create: (data: HandbookCreate) => Promise<HandbookDetail>` | `api.post('/handbooks', data)` |
| `update: (id: string, data: HandbookUpdate) => Promise<HandbookDetail>` | `api.put(…, data)` |
| `publish: (id) => Promise<HandbookPublishResponse>` | `api.post(…/publish)` (no body) |
| `archive: (id) => Promise<{message: string}>` | `api.post(…/archive)` |
| `getProfile / updateProfile` | `api.get` / `api.put('/handbooks/profile', data)` |
| `getAutoScopes: () => Promise<{state: string; city: string \| null}[]>` | `api.get` |
| `uploadFile: (file: File)` | build `FormData` (`fd.append('file', file)`) → `api.upload<{url: string; filename: string; company_id: string}>('/handbooks/upload', fd)` |
| `downloadPdf: (id, title)` | `api.download(…/pdf, \`${title}.pdf\`)` (unchanged — already used api.download) |
| `getShareLink: (id) => Promise<HandbookShareLink \| null>` | `api.get` (keep the "published-only / null when never shared" comment) |
| `createShareLink: (id, expiresInDays?: number)` | `api.post(…/share, { expires_in_days: expiresInDays ?? null })` |
| `revokeShareLink: (id) => Promise<{status: string}>` | `api.delete` |
| `generateGuidedDraft / getWizardDraft / saveWizardDraft / clearWizardDraft` | `api.post('/handbooks/guided-draft', data)` / `api.get<HandbookWizardDraft \| null>` / `api.put('/handbooks/wizard-draft', { state })` / `api.delete<{deleted: boolean}>` |
| `listChanges / acceptChange / rejectChange` | `api.get` / `api.post(…/accept)` / `api.post(…/reject)` |
| `distribute: (id, employeeIds?: string[])` | `api.post(…/distribute, employeeIds ? { employee_ids: employeeIds } : undefined)` — conditional-body semantics identical |
| `listDistributionRecipients / acknowledgements` | `api.get` |
| `getLatestFreshnessCheck: (id) => Promise<HandbookFreshnessCheck \| null>` / `runFreshnessCheck` | `api.get` / `api.post` |
| `getCoverage / markSectionReviewed` | `api.get` / `api.post<HandbookSection>(…/sections/${sectionId}/mark-reviewed)` |

### 2b. New `api/handbook/policies.ts`

```ts
import { api } from '../client'
import type { PolicyResponse } from '../../types/policy'

export const policies = {
  list: (status?: string, category?: string): Promise<PolicyResponse[]> => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (category) params.set('category', category)
    const qs = params.toString()
    return api.get<PolicyResponse[]>(`/policies${qs ? `?${qs}` : ''}`)
  },
  get: (id: string) => api.get<PolicyResponse>(`/policies/${id}`),
  create: (data: FormData) => api.upload<PolicyResponse>('/policies', data),
  update: (id: string, data: Record<string, unknown>) => api.put<PolicyResponse>(`/policies/${id}`, data),
  delete: (id: string) => api.delete<void>(`/policies/${id}`),
}
```
Lives beside handbook.ts: sole consumer is `pages/app/handbook/Policies.tsx` (handbook domain).

### 2c. New `api/admin/landingMedia.ts`

```ts
import { api, API_BASE } from '../client'

export type LandingSizzleVideo = { id: string; title: string; caption?: string; url: string | null }
export type LandingCustomerLogo = { name: string; url: string }
export type LandingTestimonial = { quote: string; author: string; title: string }
export type LandingMedia = {
  hero_video_url: string | null
  hero_poster_url: string | null
  sizzle_videos: LandingSizzleVideo[]
  customer_logos: LandingCustomerLogo[]
  testimonials: LandingTestimonial[]
}

export const landingMedia = {
  // Public unauthenticated endpoint — deliberate raw fetch (no auth header, no refresh)
  getPublic: async (): Promise<LandingMedia> => {
    const res = await fetch(`${API_BASE}/landing-media`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  },
  getAdmin: () => api.get<LandingMedia>('/admin/landing-media'),
  save: (data: LandingMedia) => api.put<{ ok: boolean; value: LandingMedia }>('/admin/landing-media', data),
  upload: (file: File, kind: 'video' | 'image') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', kind)
    return api.upload<{ url: string; filename: string; content_type: string; size: number }>('/admin/landing-media/upload', fd)
  },
}
```
Home = `api/admin/` — sole consumer is `pages/admin/LandingMedia.tsx` (verified: no public page imports it).

### 2d. New `api/settings/settings.ts`

```ts
import { api } from '../client'

export function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<{ avatar_url: string }>('/auth/avatar', fd)
}
```
Sole consumer `pages/app/settings/UserSettings.tsx`; folder mirrors `pages/app/settings/`.

### 2e. client.ts deletions

Delete lines 159–272 (`types/handbook` import + `handbooks` + `types/policy` import + `policies`) and 354–397 (`uploadAvatar` + landing types + `landingMedia`). Result: client.ts ≈ 215 lines of pure infra (refresh dance, ApiError, request, authStreamHeaders, _fetchWithRefresh, _saveBlobResponse, api, API_BASE).

### 2f. Consumer import updates (all 8, exact lines verified)

| file:line | before | after |
|---|---|---|
| `components/handbook/HandbookShareCard.tsx:3` | `import { handbooks } from '../../api/client'` | `…from '../../api/handbook/handbook'` |
| `components/handbook/HandbookDistributeModal.tsx:3` | same | same pattern |
| `pages/app/handbook/HandbookForm.tsx:3` | `…from '../../../api/client'` | `…from '../../../api/handbook/handbook'` |
| `pages/app/handbook/Handbooks.tsx:3` | same | same |
| `pages/app/handbook/HandbookDetail.tsx:3` | same | same |
| `pages/app/handbook/Policies.tsx:2` | `import { policies, api } from '../../../api/client'` | `import { api } from '../../../api/client'` + `import { policies } from '../../../api/handbook/policies'` |
| `pages/app/settings/UserSettings.tsx:4` | `import { uploadAvatar, api } from '../../../api/client'` | `import { api } from '../../../api/client'` + `import { uploadAvatar } from '../../../api/settings/settings'` |
| `pages/admin/LandingMedia.tsx:4` | `import { landingMedia, type LandingMedia, type LandingSizzleVideo, type LandingCustomerLogo, type LandingTestimonial } from '../../api/client'` | same names `from '../../api/admin/landingMedia'` |

(Symbol-grep verified: no other file imports `handbooks`/`policies`/`landingMedia`/`uploadAvatar`/`Landing*` from `api/client` — including `work/`.)

---

## Step 3 — Error-class unification + pilot type dedupe

### 3a. `api/sse.ts`

```ts
// line 20 — extend existing import (no cycle: client.ts never imports sse.ts)
import { authStreamHeaders, ApiError, API_BASE } from './client'
// line 22 — DELETE: const BASE = import.meta.env.VITE_API_URL || '/api'
//   (postSSE's fetch at :167 uses API_BASE instead)
```

```ts
// lines 122–131 replacement. CRITICAL: no `status`/`body` field declarations in
// the subclass — with useDefineForClassFields:true they'd re-define over the
// parent-assigned values as undefined.
export class SSEHttpError extends ApiError {
  constructor(message: string, status: number, body: unknown) {
    super(message, status, body)
    this.name = 'SSEHttpError'
  }
}
```

```ts
// new, next to PilotMessage (~line 39)
/** A grounded claim + the record ids that establish it. Redeclared verbatim
 *  across the pilot modules before consolidation. */
export type CitedPoint = { point: string; cited_ids: string[] }
```

### 3b. Pilot modules — exact edits (all verified against current source)

`api/broker/brokerPilot.ts`:
```ts
// import block gains: type PilotMessage as SsePilotMessage, type CitedPoint
// :79  export type EvidenceMapItem = { point: string; cited_ids: string[] }
//   →  export type EvidenceMapItem = CitedPoint
// :95–100 (MessageMeta already ends `} | null`, so TMeta carries the null)
//   →  export type PilotMessage = SsePilotMessage<MessageMeta>
```

`api/admin/compliancePilot.ts`:
```ts
// import block gains: type PilotMessage as SsePilotMessage, type CitedPoint, type SessionStatus
// :20  export type Citation = { point: string; cited_ids: string[] }  →  export type Citation = CitedPoint
// :54–59 (metadata here is `MessageMeta | null` — null OUTSIDE the meta type)
//   →  export type PilotMessage = SsePilotMessage<MessageMeta | null>
// :110 (inside PilotSession)  status: 'active' | 'closed'  →  status: SessionStatus
```

`api/handbook-pilot/handbookPilot.ts`:
```ts
// import block gains: type PilotMessage as SsePilotMessage
// :22–27 (MessageMeta at :16–20 already `} | null`)
//   →  export type PilotMessage = SsePilotMessage<MessageMeta>
```

`api/legal-defense/legalDefense.ts`:
```ts
// import block gains: type CitedPoint
// :47  export type EvidenceMapItem = { point: string; cited_ids: string[] }  →  export type EvidenceMapItem = CitedPoint
// (MatterMessage at :60 is NOT a PilotMessage — different shape, stays)
```

`api/analysis-pilot/analysisPilot.ts`:
```ts
// import block gains: type CitedPoint
// :227  evidence_map: Array<{ point: string; cited_ids: string[] }>  →  evidence_map: CitedPoint[]
```

All old exported names (`EvidenceMapItem` ×2, `Citation`, `PilotMessage` ×3) survive as aliases — zero consumer edits (`pages/broker/pilot/Console.tsx`, `pages/admin/studio/pilot/Console.tsx`, etc. untouched). `brokerPilot.ts:12` and `handbookPilot.ts:12` already re-export `SessionStatus` — unchanged.

Note: `verbatimModuleSyntax` — the new imports are type-only, so `import { streamPilotChat as sharedStreamPilotChat, type PilotMessage as SsePilotMessage, type CitedPoint, … } from '../sse'` (inline `type` markers, matching existing style).

---

## Step 4 — Flatten `api/compliance/compliance/` → `api/compliance/`

### 4a. Moves (`git mv`, history-preserving)

```bash
cd client/src/api/compliance
git mv compliance/types.ts compliance/locations.ts compliance/calendar.ts \
       compliance/requirements.ts compliance/audit.ts compliance/credentials.ts \
       compliance/alerts.ts compliance/summary.ts compliance/checks.ts \
       compliance/posters.ts compliance/regulatory.ts compliance/payer.ts \
       compliance/admin.ts .
git mv compliance/key-coverage.ts keyCoverage.ts
git mv compliance/quality-audit.ts qualityAudit.ts
git mv compliance/labels.ts ../../data/complianceLabels.ts
git rm compliance.ts   # replaced by index.ts below
```

### 4b. Internal import fixes in the 15 moved files (exact, grep-verified)

Every file's line 1: `import { api } from '../../client'` → `'../client'`.
Deep-type imports `'../../../types/compliance'` → `'../../types/compliance'` in: `admin.ts:6`, `alerts.ts:5`, `audit.ts:2`, `checks.ts:6`, `locations.ts:8`, `posters.ts:5`, `requirements.ts:7`, `summary.ts:2`.
Sibling imports `'./types'` (calendar.ts:2, credentials.ts:2, keyCoverage.ts:5, payer.ts:7, qualityAudit.ts:5, regulatory.ts:6, summary.ts:3) — **unchanged** (siblings move together).

### 4c. New `api/compliance/index.ts`

```ts
// Barrel: the compliance HTTP/API client. Import path `api/compliance`; every
// exported symbol preserved from the pre-flatten `api/compliance/compliance`.
export * from './types'
export * from './locations'
export * from './calendar'
export * from './requirements'
export * from './audit'
export * from './credentials'
export * from './alerts'
export * from './summary'
export * from './checks'
export * from './posters'
export * from './qualityAudit'
export * from './regulatory'
export * from './payer'
export * from './keyCoverage'
export * from './admin'
```
(Old barrel's 16 lines minus `labels` — moved to data/, see 4e.) `workforceCompliance.ts` stays a sibling OUTSIDE the barrel (its 3 importers are already direct; folding in risks symbol collisions for nothing).

### 4d. Barrel-consumer updates — all 39 files

Mechanical: `'<prefix>/api/compliance/compliance'` → `'<prefix>/api/compliance'` (relative prefix unchanged). Full list:

- `hooks/compliance/`: `useComplianceAudit.ts`, `useComplianceCheck.ts`, `useComplianceData.ts`, `useLocationDetail.ts`, `useRiskSummary.ts`
- `components/compliance/`: `ComplianceAuditTab.test.tsx`, `ComplianceAuditTab/ComponentChecklist.test.tsx`, `ComplianceAuditTab/ComponentChecklist.tsx`, `ComplianceCredentialsTab.tsx`, `CompliancePostersTab.tsx`, `ComplianceRequirementsTab.tsx`†, `ComplianceRequirementsTab/RequirementRow.tsx`†, `ComplianceRiskCockpit/IssueRow.tsx`, `ComplianceRiskCockpit/RemediationTrail.tsx`, `FacilityProfileBanner.tsx`, `PayerPolicyNavigator.tsx`, `PendingResearchPanel.tsx`, `PolicyDrafter.tsx`, `ProtocolAnalysis.tsx`, `RegulatoryQuickAsk.tsx`
- `components/admin/jurisdiction/`: `CoverageHeatmap.tsx`, `GapIntelligencePanel.tsx`, `IntegrityTab.tsx`, `KeyCoverageDrawer.tsx`, `KeyIndexTab.tsx`, `RequirementAuditTable.tsx`
- `components/dashboard/ComplianceImpact.tsx`, `components/ir/OshaLogsPanel/useOshaLogs.tsx`
- `pages/admin/ComplianceManagement.tsx`, `pages/admin/PayerData.tsx`
- `pages/app/compliance/`: `Compliance.tsx`, `ComplianceCalendar.tsx`, `ComplianceCalendar/constants.ts`, `ComplianceCalendar/ListView.tsx`, `ComplianceCalendar/MonthView.tsx`
- `pages/app/legal-defense/LegalContextPanel.tsx`, `pages/app/legal-defense/modals.tsx`
- `pages/app/settings/CompanySettings.tsx`
- `work/pages/MatchaWorkThread/useThreadController.ts` (documented work→matcha crossing; path-only)

Plus the one deep import: `components/employees/ScheduleLawPanel.tsx:5` → `import { fetchLocations } from '../../api/compliance/locations'`.

### 4e. Labels → data (the two † files need a split, not just a path swap)

`labels.ts` is 22 lines of static `Record<string, string>` (`JURISDICTION_LEVEL_LABELS`, `RATE_TYPE_LABELS`) — zero HTTP; `data/laborLabels.ts` is the precedent. Both consumers import the symbols **via the barrel**:

- `components/compliance/ComplianceRequirementsTab.tsx:8`: `import { JURISDICTION_LEVEL_LABELS } from '../../api/compliance/compliance'` → `import { JURISDICTION_LEVEL_LABELS } from '../../data/complianceLabels'`
- `components/compliance/ComplianceRequirementsTab/RequirementRow.tsx:5`: `import { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../../api/compliance/compliance'` → `…from '../../../data/complianceLabels'`

(`hooks/compliance/useComplianceRequirements.test.ts:32` mentions the symbol only in a comment — no edit.)

Verify: tsc; `npm run test:run` (ComplianceAuditTab + ComponentChecklist tests import the barrel); `grep -rn 'compliance/compliance' client/src` → 0 hits.

---

## Step 5 — Delete the adminOnboarding shim

`api/admin/adminOnboarding.ts` is exactly `export * from './adminOnboarding/index'`. All 22 consumers use the specifier `'…/api/admin/adminOnboarding'`; today the file shadows the directory. Under `moduleResolution: "bundler"` (tsc) and Vite/Rollup, the same specifier resolves to `adminOnboarding/index.ts` once the file is gone.

```bash
git rm client/src/api/admin/adminOnboarding.ts
```
Zero import edits. Verify: tsc + final `npx vite build`; `grep -rn "adminOnboarding/index'" client/src` → only intra-package (none expected from consumers).

---

## Step 6 — brokerChat disambiguation

Two 52-line files named `brokerChat.ts` in folders differing by a hyphen — different products, not duplicates: `api/broker/brokerChat.ts` = broker portal (`/broker/chat/*`), `api/broker-chat/brokerChat.ts` = company side (`/broker-chat/*`, exports already `Company`-prefixed). Don't merge/factory-ize (endpoints + verb prefixes differ; 2×52 lines doesn't earn abstraction).

```bash
git mv client/src/api/broker-chat/brokerChat.ts client/src/api/broker-chat/companyBrokerChat.ts
```
Update 2 imports (verified lines):
- `components/sidebars/ClientSidebar.tsx:13` → `import { fetchCompanyBrokerChatSummary } from '../../api/broker-chat/companyBrokerChat'`
- `pages/app/broker-chat/BrokerChat.tsx:13` (multi-line import closing `} from '../../../api/broker-chat/brokerChat'`) → `'../../../api/broker-chat/companyBrokerChat'`

Knowingly breaks dir-repeats-filename for this folder — documented in Step 10.

---

## Step 7 — Move resourcePins

```bash
git mv client/src/api/resourcePins.ts client/src/api/resources/resourcePins.ts
```
Inside the file: `from './client'` → `from '../client'`. Endpoints are `/resources/pins`; `api/` root is infra-only per CLAUDE.md. Update 2 imports (verified):
- `components/widgets/PinButton.tsx:3`: `import type { ResourceKind } from '../../api/resources/resourcePins'`
- `hooks/usePinnedResources.ts:10`: multi-line import closing → `} from '../api/resources/resourcePins'`

---

## Step 8 — Hand-rolled call sites (each read + adjudicated)

### 8a. `components/ir/IRCopilotPanel/useCopilotPanel.ts` — two sites, keep raw fetch, dedupe headers

Do NOT convert to `postSSE`: both sites call `reportApiError` with a text-sliced detail on non-ok (`(await res.clone().text()).slice(0, 500)` — the comment records this is why the prod 503 finally logged) and treat `!res.body` as failure. `postSSE` throws `SSEHttpError` without reporting — a silent observability regression.

Site 1 (`:143–151`, streamRound) and site 2 (`:252–265`, handleAccept) — same edit:
```ts
// before (per site)
const token = await ensureFreshToken()
const res = await fetch(`${BASE}/ir/incidents/${incidentId}/copilot/stream`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  },
  body: JSON.stringify({ message: userMessage }),
})
// after — raw fetch stays (manual error reporting, see comment); headers deduped
const res = await fetch(`${API_BASE}/ir/incidents/${incidentId}/copilot/stream`, {
  method: 'POST',
  headers: await authStreamHeaders({ 'Content-Type': 'application/json' }),
  body: JSON.stringify({ message: userMessage }),
})
```
Import line 3 becomes `import { api, authStreamHeaders, API_BASE } from '../../../api/client'` (drop `ensureFreshToken` — `noUnusedLocals` enforces; keep `api` — used elsewhere in the file). Line 7 (`import { BASE } from './helpers'`) deleted per Step 1. Add one comment above site 1: `// Raw fetch, not postSSE: these sites report failures to client-errors with the response text — postSSE would swallow that.`

Behavior note: `authStreamHeaders` omits the Authorization key entirely when no token exists, where the old spread did the same — identical. Token-refresh semantics identical (`authStreamHeaders` calls `ensureFreshToken`).

### 8b. `pages/app/er/ERCaseDetail.tsx:101–127` — replace with `api.downloadPost`

```ts
// before: 22-line hand-rolled POST+blob (lines 105–122, incl. its own BASE,
// ensureFreshToken, fetch, blob, createElement('a') WITHOUT document.body.appendChild)
// after
async function handleDownloadPdf() {
  if (!exportPassword.trim()) return
  setExporting(true)
  try {
    await api.downloadPost(
      `/er/cases/${caseId}/export`,
      { password: exportPassword },
      `${case_?.case_number ?? 'case'}-export.pdf`,
    )
    setExportPassword('')
  } catch { /* error handled silently */ } finally {
    setExporting(false)
  }
}
```
Drop the now-unused `ensureFreshToken` import if this was its last use (check; `api` already imported). **Documented deltas (both fixes):** gains the 401 refresh-and-retry; anchor is now document-attached — the current code has the exact phantom-download Chrome bug `_saveBlobResponse`'s comment describes (`a.click()` on an untethered anchor). Thrown-message format identical (`${status} ${statusText}`); surrounding silent catch unchanged.

### 8c. `components/ir/IRExportModal.tsx:104–123` — replace with `api.download`

```ts
// before: hand-rolled GET+blob with own base/token/anchor (this one DID attach the anchor)
// after (params + stamp computed as today, lines 91–102 + 116 kept)
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
await api.download(`/ir/incidents/export?${params.toString()}`, `incidents-${stamp}.${format}`)
onClose()
```
Drop unused `ensureFreshToken` import if last use. **Documented delta:** on failure the catch's `setError` message becomes `"<status> <statusText>"` instead of the raw response text (today that's raw FastAPI JSON shown to the user — acceptable, arguably better). Gains 401 retry.

### 8d. `hooks/useSidebarBadges.ts:52–56` — dedupe header assembly, keep raw fetch

```ts
// before
const token = await ensureFreshToken()
if (!token) return
const res = await fetch(`${BASE}/dashboard/sidebar-badges?${params}`, {
  headers: { Authorization: `Bearer ${token}` },
})
// after — raw fetch stays: api.get would report every transient 5xx of a 60s
// poll to /client-errors. No-token early return preserved (authStreamHeaders
// omits the key when ensureFreshToken() returns null).
const headers = await authStreamHeaders()
if (!headers.Authorization) return
const res = await fetch(`${API_BASE}/dashboard/sidebar-badges?${params}`, { headers })
```
Import line 3: `import { authStreamHeaders, API_BASE } from '../api/client'` (drop `ensureFreshToken`). Do NOT switch to `api.get` — new-error-reporting behavior change on a polling endpoint.

---

## Step 9 — Raw localStorage token reads: document, don't change

All three read + adjudicated. None safely convertible — `ensureFreshToken()` calls `_logout()` (redirect to `/login`) on failed refresh, and each site must tolerate anonymous/stale sessions:

- `utils/usageTracker.ts:115` (`flush(useKeepalive)`): runs on pagehide with `keepalive: true`; must stay synchronous — an `await` before the fetch risks losing the final beacon; `api.post` can't set `keepalive`, and `sendBeacon` can't set Authorization (existing comment). Stale token costs only attribution on best-effort analytics. Add: `// Deliberate raw read (documented exception): flush() must stay sync for the pagehide beacon, and a dead session must not trigger ensureFreshToken's logout redirect.`
- `components/marketing/NewsletterSignup.tsx:62` + `components/landing/NewsletterHeroSection.tsx:74`: `/newsletter/subscribe` is optional-auth — the token is attribution-only, anonymous visitors send none, and the sites render `data.detail` inline on non-ok. `ensureFreshToken` would bounce a marketing-page visitor with a dead session to `/login` on form submit; `api.post` would throw + report to client-errors. Add the same one-line exception comment at both.

---

## Step 10 — `client/CLAUDE.md` updates

- Layout tree, api/ entry: root files = `client.ts (THE http helper — exports api, ApiError, API_BASE, ensureFreshToken, authStreamHeaders), errorReporter, authReset, sse.ts (+ sse.test.ts, client.test.ts), profileResume (shared w/ work)`; **remove** `resourcePins` from root list; folder list = `admin/ analysis-pilot/ benefits/ billing/ broker/ broker-chat/ compliance/ dashboard/ discipline/ employees/ handbook/ handbook-pilot/ labor/ legal-defense/ limit-adequacy/ matcha-x/ portal/ property/ resources/ risk/ settings/ training/` (adds handbook/, resources/, settings/; documents pre-existing benefits/, broker-chat/).
- "API calls" convention section: add — "`API_BASE` is exported from `api/client.ts` (trailing-slash-normalized). Never redeclare `import.meta.env.VITE_API_URL ?? '/api'`. Sanctioned duplicates: `api/errorReporter.ts` (cycle avoidance) and `cappe/` (own stack)."
- Same section: "`SSEHttpError extends ApiError` — `catch (e) { e instanceof ApiError }` now covers both transports."
- Pitfall bullet (raw token reads): append the three Step-9 exception sites by path.
- Boundary/api rules: note `api/compliance/index.ts` is the one intentional barrel; note `api/broker-chat/companyBrokerChat.ts` as the named exception to dir-repeats-filename (disambiguates from `api/broker/brokerChat.ts`).
- Do NOT touch the "9 modules still do" type-home note beyond its existing text — the 344-declaration hoist stays its own PR.

---

## Test plan

### New: extend `api/sse.test.ts`

```ts
import { SSEHttpError } from './sse'
import { ApiError } from './client'

describe('SSEHttpError', () => {
  it('is an ApiError — one instanceof covers both transports', () => {
    const e = new SSEHttpError('conflict', 409, { detail: 'conflict' })
    expect(e).toBeInstanceOf(SSEHttpError)
    expect(e).toBeInstanceOf(ApiError)
    expect(e).toBeInstanceOf(Error)
  })

  // Guards the useDefineForClassFields hazard: a redeclared field in the
  // subclass would clobber the parent-assigned status/body to undefined.
  it('carries status/body/message through super', () => {
    const e = new SSEHttpError('conflict', 409, { detail: 'conflict' })
    expect(e.status).toBe(409)
    expect(e.body).toEqual({ detail: 'conflict' })
    expect(e.message).toBe('conflict')
    expect(e.name).toBe('SSEHttpError')
  })

  it('a plain ApiError is NOT an SSEHttpError', () => {
    expect(new ApiError('x', 500, null)).not.toBeInstanceOf(SSEHttpError)
  })
})
```
(Safe: sse.test.ts already transitively imports client.ts via sse.ts → authStreamHeaders; nothing in client.ts touches window/localStorage at module scope.)

### New: `api/client.test.ts`

```ts
import { describe, it, expect } from 'vitest'
import { API_BASE, ApiError } from './client'

describe('API_BASE', () => {
  it('never ends with a slash (34 of 36 former redeclarations built double-slash URLs)', () => {
    expect(API_BASE.endsWith('/')).toBe(false)
    expect(API_BASE.length).toBeGreaterThan(0)
  })
})

describe('ApiError', () => {
  it('exposes status and body for callers branching on status', () => {
    const e = new ApiError('too many', 429, { detail: 'too many' })
    expect(e.status).toBe(429)
    expect(e.body).toEqual({ detail: 'too many' })
    expect(e.name).toBe('ApiError')
  })
})
```

### Existing tests that gate the refactor
- `api/sse.test.ts` (13 consumeSSE cases) — must stay green after the sse.ts edits.
- `components/compliance/ComplianceAuditTab.test.tsx` + `ComplianceAuditTab/ComponentChecklist.test.tsx` — import the compliance barrel; prove Step 4's flatten.
- `hooks/compliance/useComplianceRequirements.test.ts` — compliance hooks unaffected by path change (imports the hook, not the barrel).

### Type-level guarantees (tsc is the test)
- Pilot aliases: `PilotMessage = SsePilotMessage<MessageMeta>` vs `SsePilotMessage<MessageMeta | null>` — a wrong nullability placement fails compile at the consumer consoles.
- `verbatimModuleSyntax` rejects any missing `type` marker on the new type imports.
- `noUnusedLocals` catches every leftover `ensureFreshToken`/`BASE` import at the edited call sites.

---

## Verification checklist (run after each step; full set at end)

```bash
cd /Users/finch/Documents/github/matcha/client
npx tsc -p tsconfig.app.json --noEmit          # every step
npm run test:run                                # steps 3, 4, final (sse + compliance + new tests)
npx vite build                                  # final — proves bundler resolution (shim delete, barrel, moves)
```

Greps (from `client/src`), all expected empty at the end:
```bash
grep -rn "compliance/compliance" .                                   # step 4
grep -rn "from '.*api/client'" . | grep -E "handbooks|policies|landingMedia|uploadAvatar|Landing" # step 2
grep -rn "broker-chat/brokerChat'" .                                 # step 6
grep -rn "api/resourcePins" .                                        # step 7
grep -rn "point: string; cited_ids" . --include='*.ts' | grep -v api/sse.ts   # step 3
grep -rn "VITE_API_URL" . | grep -v cappe/                           # step 1 → only client.ts + errorReporter.ts
grep -rn "matcha_access_token" components/ pages/ hooks/ utils/      # step 9 → only the 3 commented exceptions + logout removeItem sites
git status                                                           # moves show as renames
```

---

## Risks

1. **`SSEHttpError extends ApiError`** widens what `instanceof ApiError` matches. Audited: the 7 files testing `instanceof ApiError` are REST-only paths (`useMe.ts`, `EmployeeSchedule.tsx`, …) — none consume postSSE/streamPilotChat; `streamPilotChat` handles `SSEHttpError` internally. Future overlap degrades gracefully (same fields).
2. **`useDefineForClassFields: true`** — subclass must not redeclare `status`/`body`; new sse.test.ts case pins it.
3. **errorReporter cycle** — excluded from API_BASE adoption; comment prevents future "cleanup" reintroducing the cycle.
4. **Normalization deltas** — trailing-slash strip only changes behavior when `VITE_API_URL` ends in `/` (fixes `//api`); sse.ts `||`→shared-`??` differs only on empty-string env (not a real config).
5. **Directory-index resolution** (Steps 4/5) — guaranteed by `moduleResolution: bundler` + Vite; final `vite build` proves end-to-end.
6. **Pilot generic nullability** — inside vs outside `MessageMeta` differs per module (broker/handbook: inside; compliance: outside); tsc enforces at the consoles.
7. **`git mv` + content edits in same commit** — keep edits to import lines only so rename detection holds (default similarity threshold is safe at these sizes).

## Explicitly deferred (not this PR)

- `api/ir/` + `api/er/` modules (49 + 24 inline endpoint literals in components/hooks) — natural follow-up, same pattern as this pass.
- `/admin` client consolidation (107 call sites).
- Type hoisting `api/*` → `types/` (39 files, 344 declarations — CLAUDE.md: own PR).
- `pages/admin` / `pages/broker` flattening (deferred on purpose per docs).
