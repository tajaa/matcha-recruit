# Client (React + Vite Frontend)

React 18 + TypeScript + Vite + Tailwind. Single SPA served at `/`; backend API at `/api` (proxied in dev via Vite, served by Nginx in prod).

## Layout — app-first

Three products share this SPA. Each guest app is a **self-contained vertical slice** under its
own top-level folder; **Matcha** (the main HR/risk platform) keeps the classic
`pages/`/`components/`/`api/`… tree at the root. `App.tsx` + `main.tsx` are the shared
composition root that dispatches between them (host axis for Cappe, route-prefix axis for the
rest — see "Routing" below).

```
client/src/
├── App.tsx, main.tsx        Composition root: host + route-prefix dispatch, shell providers
├── index.css                Tailwind directives + global styles
│
├── cappe/                   ← CAPPE app (website builder, host-routed on gummfit.com)
│   ├── routes.tsx           Route tree (mounted by App.tsx on /cappe/* and on the cappe host apex)
│   ├── layout/              CappeLayout
│   ├── pages/               incl. site/ + site/PageEditor/
│   ├── components/          incl. its OWN ui.ts + CappeSidebar (parallel stack, not shared UI)
│   ├── onboarding/          CappeOnboardingWizard
│   ├── api.ts               cappeApi (own http client — NOT api/client.ts)
│   ├── hooks/useCappeMe.ts  own auth-state hook (NOT hooks/useMe)
│   ├── host.ts              isCappeHost / cappeSiteHost (host detection)
│   ├── types.ts, data/      cappe types + cappeThemes/cappePagePresets/timezones
│
├── work/                    ← WORK app (matcha-work / werk / werk-lite — one product, 3 URL surfaces)
│   ├── routes/              WorkRoutes, WerkRoutes, WerkLiteRoutes, WorkSurfaceContext
│   ├── layout/              WorkLayout
│   ├── pages/               incl. Inbox (also surfaced by matcha at /app/inbox — see boundary rules)
│   ├── components/shell/    Surface chrome: sidebars, kanban, notifications, connections
│   ├── components/panels/   In-canvas feature panels: AI agents, recruiting pipeline, editors
│   ├── components/channels/, components/inbox/
│   ├── api/                 matchaWork, channels, channel*, inbox, projectSocket, threadSocket, notifications
│   ├── hooks/               presence, livekit, channel-notifications, voice, …
│   ├── utils/               avatarColor, kanban*, notificationSound
│   ├── types.ts             (was types/matchaWork)  data/projectTemplates
│
├── ── MATCHA (main app) — everything below is the risk platform ──
├── api/                     client.ts (THE http helper), errorReporter, authReset, resourcePins,
│   │                        profileResume (shared w/ work); domain subfolders:
│   └── risk/ hr/ admin/ billing/ broker/ compliance/
├── components/
│   ├── ui/                  Generic primitives (Button, Input, Modal, …) — the shared design system
│   ├── sidebars/            AdminSidebar, BrokerSidebar, ClientSidebar (full platform),
│   │                        TenantSidebar (tier dispatcher), SidebarShell, nav-icons
│   ├── tier-sidebars/       Below-full-platform tiers: IrSidebar/MatchaXSidebar/ComplianceSidebar + panels
│   ├── shared/              App-wide singletons: ErrorBoundary, FeatureGate, UpgradeUpsellCard,
│   │                        ThemeToggle, RouteTracker, Avatar, HelpAssistant
│   ├── widgets/             Generic reusable widgets: AiSuggest, NoteThread, PinButton, …
│   ├── marketing/           Public widgets: BlogComments, NewsletterSignup, PricingContactModal
│   ├── ir/ compliance/ employees/ dashboard/ handbook/ broker/ er/ …   domain modules
│   └── auth/                RequireBusinessAccount, RequireRole, login forms
├── features/               Feature modules: discipline/, ir-onboarding/, matcha-x-onboarding/, admin-onboarding/
├── hooks/                  useMe (THE auth state) + shared hooks at root; domain subdirs
│   │                        (ir/ er/ compliance/ discipline/ employees/ risk-assessment/ training/ admin/)
├── layouts/                AppLayout (Cappe/Work layouts live in their own app folders now)
├── pages/                  app/ admin/ broker/ portal/ auth/ shared/ landing/ home/ simpler-pages/
│   │                        + loose: BetaRegister, Login, ResetPassword, SSOCallback
│   │                        (page DIRS are lowercase-kebab; component FILES stay PascalCase)
├── types/                  Shared TS types (camelCase filenames)
├── utils/                  Pure utilities: tier.ts, theme, dateFormat, staleChunk, usageTracker,
│   │                        pcmToWav, + broker/ subdir
├── data/                   Static / seed data
└── generated/              Auto-generated types (DO NOT EDIT)
```

### Boundary rules (keep the apps separate)

- **Any app may import the shared layer**: `components/ui`, `components/shared`, `hooks/useMe`,
  `api/client`, and the shell-infra utils (`theme`, `staleChunk`, `usageTracker`,
  `api/errorReporter`). Cappe deliberately does NOT use these — it has its own parallel stack.
- **Matcha must not reach into `cappe/`** except the two composition seams: `App.tsx` (host
  dispatch via `cappe/host`) and `pages/admin/Cappe.tsx` (matcha's internal admin console *for*
  Cappe). Nothing else.
- **Matcha ↔ work** crossings are limited to this documented set (like the backend's
  `tellus/geo.py` exception — don't add more without a note here):
  - `routes/AppRoutes.tsx` mounts `work/pages/Inbox` at `/app/inbox` (matcha surfaces the work inbox)
  - `pages/admin/newsletter/ComposeTab.tsx` → `work/components/panels/SectionEditor`
  - `pages/shared/CandidateInterview.tsx` → `work/hooks/useVoiceSession`
  - `components/sidebars/SidebarShell.tsx` → `work/api/channelSocket` (disconnect-on-logout)
  - work→matcha (reverse): `MatchaWorkThread` → `api/compliance` + `types/compliance`;
    `TaskBoard` → `types/dashboard`; `channels/JobPostingDetail` → `api/profileResume`
- **Within matcha, `components/` root holds only subject-area folders** — no loose files. New
  component placement: product-tier sidebar → `sidebars/`/`tier-sidebars/`; app-wide singleton →
  `shared/`; product-agnostic reusable → `widgets/`; else the relevant domain folder.
- **New api client** goes in the app's `api/` (work/cappe) or a matcha `api/<domain>/` subfolder;
  `api/` root is cross-cutting infra only.

## Conventions

**Auth + identity**:
- `useMe()` is the source of truth. Exposes `user`, `hasRole(role)`, `hasFeature(flag)`, `companyFeatures`. Never read tokens directly from localStorage in components — go through this hook.
- Tokens live in localStorage as `matcha_access_token` and `matcha_refresh_token`. `api/client.ts` attaches `Authorization: Bearer <token>` automatically and refreshes on 401.
- Public/anon endpoints bypass the auth interceptor: pass `{ skipAuth: true }` option, or use the bare `fetch()` (see `IRCopilotPanel.tsx` stream handler).

**Routing + tier dispatch**:
- `App.tsx` registers all routes. `TenantSidebar` (`components/sidebars/TenantSidebar.tsx`) dispatches sidebar shell by tier (`client/src/utils/tier.ts` has `isIrOnlyTier`, `isMatchaLitePending`, etc.).
- Free tier has no dedicated sidebar variant — it falls through to `ClientSidebar` and is gated page-by-page via `<RequireBusinessAccount>`; matcha-lite/Matcha-X/Compliance paid → `IrSidebar` / `MatchaXSidebar` / `ComplianceSidebar` (`components/tier-sidebars/`); those pending payment → the `*PendingSidebar` components defined inline in `TenantSidebar.tsx`; full Matcha → `ClientSidebar` (`components/sidebars/`).
- Per-feature pages are gated by `<FeatureGate flag="…">` (`components/shared/FeatureGate.tsx`). When a user URL-hops to a feature they don't have, the gate renders `<UpgradeUpsellCard>` (`components/shared/UpgradeUpsellCard.tsx`) instead of a 403.

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

`components/sidebars/TenantSidebar.tsx` is the only place that picks the sidebar. Adding a new tier means a new branch here plus a new sidebar component (in `components/sidebars/` for a full-platform variant, `components/tier-sidebars/` for a below-full-platform tier).  Don't fork at the page level.

## Adding a new feature flag

Backend (`server/app/core/feature_flags.py`) is authoritative. Frontend just consumes via `useMe().hasFeature("flag_name")`. To wire a new flag:

1. Add to `DEFAULT_COMPANY_FEATURES` in `feature_flags.py` (defaults to false unless rolled out).
2. Add a row to the flag table in root `CLAUDE.md`.
3. In sidebars (`components/sidebars/ClientSidebar.tsx` etc.), use `hasFeature("flag_name")` to conditionally render the nav entry.
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
