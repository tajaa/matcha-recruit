# Frontend Design Principles for Code Reduction

Analysis of the 10 heaviest pages (19,362 total LOC) identified 6 recurring anti-patterns.
Applying these principles consistently is estimated to remove **2,250–3,350 LOC**.

---

## Principle 1: Shared Theme Module

**Problem:** Every page redefines `LT` and `DK` Tailwind token objects (50–100 LOC each).
9 of 10 heavy pages have copy-pasted versions with identical keys.

**Rule:** Theme token objects are configuration, not component logic. Define them once.

**Action:**
- Create `client/src/theme/tokens.ts` exporting canonical `LT` and `DK`
- Pages import and use directly; add local overrides only for page-specific keys
- The ~20 common keys (`pageBg`, `card`, `textMain`, `textMuted`, `border`, `btnPrimary`,
  `inputCls`, `modalBg`, etc.) must never be redefined per-page

**Files:** ERCaseDetail, Training, EmployeeDetail, ProjectDetail, HandbookForm, Compliance,
Dashboard, RiskAssessment, MatchaWorkThread
**Savings:** ~500–700 LOC

---

## Principle 2: No Inline Components

**Problem:** `ProjectDetail.tsx` (6 components) and `MatchaWorkThread.tsx` (5 components)
define functional components inside the page module. Several have their own `useState`.

**Inline components found:**
- `ProjectDetail`: `PipelineIcon`, `PipelineWizard` (~110 LOC + state), `ApplicationCard`,
  `OutreachBadge`, `Field`, `EmailPreviewBox`
- `MatchaWorkThread`: `WorkbookPreview` (~180 LOC + state), `PresentationPreview`,
  `PolicyPreview`, `OnboardingPreview`, `MessageBubble`

**Rule:** Any function that returns JSX and is not a closure over the parent render scope
belongs in its own file. This is non-negotiable when the component has its own `useState`.

**Action:**
- `client/src/components/project/` — extract ProjectDetail's inline components
- `client/src/components/matcha-work/` — already exists; move MatchaWorkThread's previews here

**Files:** ProjectDetail, MatchaWorkThread
**Savings:** ~300–500 LOC

---

## Principle 3: `useFormModal` Hook

**Problem:** Every modal needs 3–5 `useState` declarations (`showXModal`, `xForm`, `xError`,
`xSaving`) plus boilerplate open/close/reset/submit handlers. With 4–8 modals per page, this
stacks up fast. ~35–40 `show*Modal` booleans exist across the 10 files.

**Rule:** A modal has a predictable lifecycle (closed → open → submitting → done). Extract it.

**Hook signature:**
```typescript
function useFormModal<T>(initial: T): {
  isOpen: boolean
  open: (data?: Partial<T>) => void
  close: () => void
  form: T
  setForm: React.Dispatch<React.SetStateAction<T>>
  saving: boolean
  error: string | null
  wrap: (fn: () => Promise<void>) => () => Promise<void>
  // wrap(fn) automatically sets saving=true, catches errors, calls close on success
}
```

**Action:** Create `client/src/hooks/useFormModal.ts` and apply to:
- **Training.tsx** — 3 form/modal pairs → replaces ~180 LOC
- **ProjectDetail.tsx** — 5 modals → replaces ~200 LOC
- **EmployeeDetail.tsx** — 4 modals (leave alone has 3) → replaces ~150 LOC

**Files:** Training, ProjectDetail, EmployeeDetail, ERCaseDetail, MatchaWorkThread, Compliance
**Savings:** ~600–900 LOC

---

## Principle 4: `useReducer` for High-Cardinality State

**Problem:** `ERCaseDetail.tsx` has ~75 `useState` calls; 28 are for the AI analysis workflow
alone. State that transitions together (streaming starts → progress updates → complete/error)
should not be managed as 28 independent variables.

**Rule:** When a component exceeds ~15 `useState` calls, audit for clusters that transition
together. Those clusters belong in a `useReducer` inside a custom hook.

**Action:** Extract `useERCaseAnalysis(caseId)` to `client/src/hooks/er/`:
- State shape: `{ timeline, discrepancies, violations, loading, progress, error, notes }`
- Actions: `START_ANALYSIS | PROGRESS_UPDATE | ANALYSIS_COMPLETE | ANALYSIS_ERROR`
- Removes 28 useState + ~200 LOC of streaming handlers from the page component

**Files:** ERCaseDetail (primary); also applicable if other analysis/streaming pages emerge
**Savings:** ~200–300 LOC

---

## Principle 5: Centralize Static Config

**Problem:** Enum-like arrays and style maps are defined inline per page. `US_STATES` (51 LOC)
appears in multiple files. Stage, status, and type arrays are redeclared per domain.

**Rule:** Static lookup tables are data, not component logic. They go in `client/src/constants/`.

**Objects to extract:**

| Object | Current Location | Target |
|--------|-----------------|--------|
| `US_STATES` | Compliance.tsx (+ others) | `constants/geo.ts` |
| `TRAINING_TYPES`, `RECORD_STATUSES` | Training.tsx | `constants/training.ts` |
| `STAGES`, `STAGE_STYLE` | ProjectDetail.tsx | `constants/projects.ts` |
| `STATUS_OPTIONS`, `CATEGORY_OPTIONS`, `DOC_TYPE_OPTIONS` | ERCaseDetail.tsx | `constants/er.ts` |

**Files:** Compliance, Training, ProjectDetail, ERCaseDetail, RiskAssessment, Dashboard
**Savings:** ~250–350 LOC

---

## Principle 6: Extract Feature Workflows to Custom Hooks

**Problem:** `EmployeeDetail.tsx` and `ERCaseDetail.tsx` contain entire feature sub-systems
inline. EmployeeDetail mixes provisioning, leave management, and credentials. ERCaseDetail
mixes case loading, analysis streaming, share links, and determination workflow.

**Rule:** If a block of state + handlers represents a coherent, independently testable workflow,
it is a hook. Follow the pattern established in `hooks/employees/`, `hooks/compliance/`,
`hooks/offer-letters/`.

**Hooks to create:**

| Hook | Source File | State Extracted | Target Path |
|------|-------------|----------------|-------------|
| `useProvisioning(employeeId)` | EmployeeDetail | 5 provisioning states + handlers | `hooks/employees/` |
| `useLeaveManagement(employeeId)` | EmployeeDetail | 8 leave states + 3 form objects | `hooks/employees/` |
| `useERCaseAnalysis(caseId)` | ERCaseDetail | 28 analysis states + streaming | `hooks/er/` |
| `useShareLinks(caseId)` | ERCaseDetail | 5 share link states + handlers | `hooks/er/` |
| `usePipelineWorkflow(projectId)` | ProjectDetail | Rankings, applications, closing | `hooks/projects/` |

**Files:** EmployeeDetail, ERCaseDetail, ProjectDetail
**Savings:** ~400–600 LOC

---

## Priority Order

| # | Principle | LOC Saved | Effort |
|---|-----------|-----------|--------|
| 1 | Shared theme module | 500–700 | Low |
| 2 | No inline components | 300–500 | Low |
| 3 | `useFormModal` hook | 600–900 | Medium |
| 4 | Centralize static config | 250–350 | Low |
| 5 | Extract feature hooks | 400–600 | Medium |
| 6 | `useReducer` for complex state | 200–300 | Medium |
| **Total** | | **2,250–3,350** | |

---

## Verification (after any change)

```bash
cd client && npx tsc --noEmit   # must pass
cd client && npm run dev         # dev server must start
```

Manual QA: toggle light/dark mode, exercise each modal on the modified page.
