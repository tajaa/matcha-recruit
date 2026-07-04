# Matcha-Work / Werk Surface Map

Reference doc clarifying the distinct "chat/workspace" product surfaces in this repo. Written 2026-07-03 after finding the root `CLAUDE.md` product table was **factually wrong** about personal vs. business routing — this doc reflects verified code, not the (stale) CLAUDE.md claim ("Personal mode ... redirected to /work"). CLAUDE.md should eventually be corrected to match this.

## The four surfaces

| Surface | Route | Identity | What it is |
|---|---|---|---|
| **Werk** (web) | `/werk` | `role='individual'` (personal signup via `BetaRegister`) | Consumer product. Same shared `pages/work/*` components as Matcha-Work, branded "Werk". |
| **Matcha-Work** (web) | `/work` | `role='client'` inside a bespoke/Pro Matcha company | Business product, embedded inside the full Matcha platform via `ClientSidebar`'s AI-group nav entry. Same shared components as Werk, branded "Matcha-Work". This is the surface with node-mode/compliance-mode/payer-mode. |
| **Werk** (macOS desktop) | `platforms/desktop/Werk/` | Whatever account is logged in | Same backend (`mw_*` tables, `matcha_work` routes) as the web surfaces. Built around personal Plus subscription (`isPersonalPlus`); will *render* business-mode UI if the account happens to carry `role=client/admin/employee`, but there is **no org-switcher** anywhere in the app — no in-product way to pick/switch a business org. Consumer-facing in practice today. |
| **Werk Lite** (web) | `/werk-lite` | Whole-company (`role='client'` or `role='employee'`), feature-gated on `werk_lite` | Genuinely separate, simpler product: channels + LiveKit calls + kanban boards only. No threads, no projects-general, no AI-turn chat, no node/compliance/payer modes — confirmed zero references in its route tree (`WerkLiteRoutes.tsx`). Own login guard (`/werk-lite/login`), own `FeatureGate`. |

## How `/werk` vs `/work` actually works

Not two separate implementations — one shared route-tree shape (`WorkRoutes.tsx` / `WerkRoutes.tsx`, same nested pages), branded via `WorkSurfaceContext` (`client/src/routes/WorkSurfaceContext.ts`):

```ts
export type WorkSurface = 'matcha-work' | 'werk' | 'werk-lite'
```

`WorkSurfaceContext.ts`'s own header comment is explicit:
> feature gating (Plus, HR skills, Node/Compliance/Payer modes, recruiting) stays keyed on **identity** (`isPersonal` / `role==='individual'`), NOT on surface. Surface drives ONLY branding strings and in-tree navigation base paths.

The actual identity↔surface enforcement (redirect if mismatched) lives in `client/src/layouts/WorkLayout.tsx:113-126`, which both `/work` and `/werk` mount:

```ts
if (!loading && surface !== 'werk-lite') {
  if (surface === 'matcha-work' && isPersonal) {
    return <Navigate to={`/werk${pathname.slice(5)}${search}`} replace />
  }
  if (surface === 'werk' && !isPersonal) {
    return <Navigate to={`/work${pathname.slice(5)}${search}`} replace />
  }
}
```
A personal user who opens `/work/...` gets client-side bounced to `/werk/...`, and vice versa.

**Known footgun:** `client/src/pages/work/ChannelInviteLanding.tsx:39` re-derives `const base = isPersonal ? '/werk' : '/work'` by hand instead of calling `useWorkBase()`, because that page lives outside the `WorkSurfaceProvider` tree (top-level `/join-channel/:code` route). Still correct today (identity-keyed), but it's a second place the surface-base logic lives — a future change to the mapping has to remember to update this file too.

## node-mode / compliance-mode / payer-mode

Not a separate surface — three buttons on the *same* `MatchaWorkThread.tsx` component that also serves personal Werk, shown/hidden by an `isIndividual` (web) / `isBusinessAccount` (desktop) check:

- Web: `client/src/pages/work/MatchaWorkThread.tsx:67-68,623,639,655`
- Desktop: `platforms/desktop/Werk/.../ThreadDetailView.swift:42-45,181`

**This gate is UI-only, not server-enforced.** Backend `require_admin_or_client` (`server/app/matcha/dependencies.py:15`) actually allows `role="individual"` too — the mode-setting endpoints (`set_thread_node_mode`/`_compliance_mode`/`_payer_mode` in `server/app/matcha/routes/matcha_work/threads.py`) and the underlying `UPDATE mw_threads SET ...` in `matcha_work_document.py` do a plain company-scoped write with no plan/feature-flag check. An individual-role user hitting the API directly could flip these on their own personal thread; nothing stops it today beyond the UI hiding the buttons.

### What "node mode" actually is

Not a canvas/graph UI — there's no reactflow/node-edge component anywhere in the client. **It's a retrieval-augmented context injector.** `server/app/matcha/services/matcha_work_node.py:build_node_context` pulls the company's real `employees`, `policies`, `handbooks`, `er_cases`, and `ir_incidents` rows from Postgres and injects them into the Gemini prompt, prefixed with an anti-hallucination instruction ("Do NOT fabricate employee names, policy details, case numbers, or incident data"). Toggling it on doesn't change the UI — it changes what the AI is silently handed before it answers, so "how many people do we have in California" gets answered from real records instead of a guess. Compliance-mode (`build_compliance_context`) is the sibling for jurisdiction-resolved legal reasoning; payer-mode does the same for Medicare NCD/LCD coverage lookups.

## Open question (not yet decided)

Whether to rename the business-embedded `/work` experience to something like **"matcha-node"** to give it a distinct brand identity from personal Werk. Consideration: node-mode is only 1 of 3 toggles (node/compliance/payer) on that surface — naming the whole thing after one toggle might undersell the other two. "Node" is also already a slight misnomer (not a graph UI, see above) independent of any rename decision. No code or naming changes have been made yet — this doc is background for that discussion.
