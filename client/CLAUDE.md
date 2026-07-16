# Client (React + Vite Frontend)

React 18 + TypeScript + Vite + Tailwind. Single SPA served at `/`; backend API at `/api` (proxied in dev via Vite, served by Nginx in prod).

## Layout

```
client/src/
├── App.tsx                  Route registration. Tier-routed via TenantSidebar.
├── main.tsx                 Vite entry
├── index.css                Tailwind directives + global styles
├── api/                     API client layer
│   ├── client.ts            api.get/post/put/delete + 401 refresh
│   ├── chatClient.ts        WebSocket AI chat client
│   └── <domain>.ts          Per-domain helpers (typed wrappers)
├── components/
│   ├── ui/                  Generic primitives (Button, Input, Modal, Select, Toggle, Badge)
│   ├── ClientSidebar.tsx    Full Matcha-platform sidebar
│   ├── TenantSidebar.tsx    Dispatcher → ClientSidebar / IrSidebar / ResourcesFreeSidebar
│   ├── AdminSidebar.tsx, BrokerSidebar.tsx
│   ├── FeatureGate.tsx, UpgradeUpsellCard.tsx
│   ├── ir/                  IR Copilot, panels, analysis tabs
│   ├── ir-only/             Matcha-lite shell (IrSidebar, billing CTA)
│   ├── resources-free/      Free-tier sidebar + upgrade panel
│   ├── channels/, inbox/, work/  Matcha-work surfaces
│   ├── compliance/, employees/, dashboard/, handbook/, …
│   └── auth/                RequireBusinessAccount, login forms
├── features/                Feature-based modules
│   ├── discipline/
│   └── ir-onboarding/
├── hooks/                   Domain-specific hooks
│   ├── useMe.ts             User+features (THE auth state)
│   ├── ir/, er/, compliance/, discipline/, employees/, risk-assessment/
│   └── single-file utilities (useChannelNotifications, useSidebarBadges)
├── layouts/                 WorkLayout, etc.
├── pages/                   Route-level pages
│   ├── app/                 /app/* (Matcha-platform)
│   ├── admin/, broker/, work/, auth/, shared/, landing/
│   └── BetaRegister.tsx, Login.tsx, Landing.tsx, ResetPassword.tsx, SSOCallback.tsx
├── types/                   Shared TypeScript types
├── utils/                   Pure utilities (incl. tier.ts)
├── data/                    Static / seed data
└── generated/               Auto-generated types (DO NOT EDIT)
```

## Conventions

**Auth + identity**:
- `useMe()` is the source of truth. Exposes `user`, `hasRole(role)`, `hasFeature(flag)`, `companyFeatures`. Never read tokens directly from localStorage in components — go through this hook.
- Tokens live in localStorage as `matcha_access_token` and `matcha_refresh_token`. `api/client.ts` attaches `Authorization: Bearer <token>` automatically and refreshes on 401.
- Public/anon endpoints bypass the auth interceptor: pass `{ skipAuth: true }` option, or use the bare `fetch()` (see `IRCopilotPanel.tsx` stream handler).

**Routing + tier dispatch**:
- `App.tsx` registers all routes. `TenantSidebar` dispatches sidebar shell by tier (`client/src/utils/tier.ts` has `isIrOnlyTier`, `isMatchaLitePending`, `isResourcesFreeTier`).
- Free tier → `ResourcesFreeSidebar`; matcha-lite paid → `IrSidebar`; matcha-lite pending → `MatchaLitePendingSidebar`; full Matcha → `ClientSidebar`.
- Per-feature pages are gated by `<FeatureGate flag="…">` (`components/FeatureGate.tsx`). When a user URL-hops to a feature they don't have, the gate renders `<UpgradeUpsellCard>` instead of a 403.

**API calls**:
- Use the `api` helper from `api/client.ts` (`api.get<T>(path, opts?)`, `api.post`, `api.put`, `api.delete`, `api.upload`, `api.download`).
- The base URL is `VITE_API_URL` env var, falls back to `/api`.
- Don't construct raw `fetch()` calls in components unless you need streaming (SSE/WebSocket).

**TypeScript**:
- `strict: true` in `tsconfig.json`. No `any` in new code; use `unknown` and narrow.
- Generated types under `src/generated/` come from a tooling step — don't hand-edit.
- Shared API response types live in `src/types/<domain>.ts`. Use them on `api.get<T>(...)` calls.
- Prefer `type` aliases over `interface` for response shapes; reserve `interface` for component props (consistent with codebase style).

**Components**:
- Functional + hooks only. No class components anywhere in the codebase.
- One default export per file when the file is a "page" or top-level component; named exports for utility components.
- Tailwind utility classes, not CSS modules. Custom design tokens (zinc palette + emerald accents) — match neighboring components rather than introducing new colors.
- Icons from `lucide-react`. Loading spinner is `<Loader2 className="animate-spin" />`.

**State**:
- `useState` + `useEffect` for component-local state. No Redux. No global state manager.
- Server state derived from `api` calls in `useEffect`, gated by `loading` flag. Optimistic updates are OK for streaming UIs (see `IRCopilotPanel` user-message echo).
- Don't introduce a query library (React Query, SWR) — current code doesn't use one. Adding one is a deliberate architectural decision, not a per-feature choice.

**Forms**:
- Controlled inputs. No form library. Validation is per-field, inline.
- File uploads use `<FileUpload>` (`components/ui/FileUpload.tsx`) with `onFiles` callback. Server bulk-upload endpoints accept multipart.

## Sidebar dispatch quickstart

`TenantSidebar.tsx:36-ish` is the only place that picks the sidebar. Adding a new tier means a new branch here plus a new sidebar component. Don't fork at the page level.

## Adding a new feature flag

Backend (`server/app/core/feature_flags.py`) is authoritative. Frontend just consumes via `useMe().hasFeature("flag_name")`. To wire a new flag:

1. Add to `DEFAULT_COMPANY_FEATURES` in `feature_flags.py` (defaults to false unless rolled out).
2. Add a row to the flag table in root `CLAUDE.md`.
3. In sidebars (`ClientSidebar.tsx` etc.), use `hasFeature("flag_name")` to conditionally render the nav entry.
4. Mount the backend router with `dependencies=[Depends(require_feature("flag_name"))]` in `server/app/matcha/routes/__init__.py`.
5. Wrap the route page with `<FeatureGate flag="flag_name">` so URL-hopping users see the upsell.

## Dev server

```bash
./scripts/dev-remote.sh    # from repo root — boots everything
# or, frontend alone (if backend tunnel is up):
cd client && npm run dev   # :5174
```

Typecheck:
```bash
cd client && npx tsc -p tsconfig.app.json --noEmit
```

**Not `npx tsc --noEmit` — it checks nothing and always exits 0.** The root
`tsconfig.json` is `{"files": [], "references": [...]}`; plain `tsc` compiles the
root project's (empty) file list and does not build referenced projects, so it
reports clean on any codebase state. Point it at `tsconfig.app.json` (or use
`npx tsc -b`). A "clean" run that returns instantly on a large change is the
tell that nothing was checked.

## Common pitfalls

- **Don't read `matcha_access_token` directly from localStorage.** Use `api/client.ts` helpers; they handle the refresh dance.
- **Don't bypass `<FeatureGate>` on a feature page.** URL-hopping is the failure mode it exists for.
- **Don't put product-tier logic in pages.** Centralize in `utils/tier.ts` + `TenantSidebar.tsx`.
- **Don't introduce a new CSS framework or design system.** Match Tailwind classes used in neighboring components.
- **Don't generate test data with realistic-looking fake email domains.** See the test-data rule in root CLAUDE.md — the server hard-blocks reserved RFC 2606 domains, but the primary mitigation is not inventing realistic fakes in the first place.
