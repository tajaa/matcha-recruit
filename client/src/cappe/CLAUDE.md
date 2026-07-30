# Cappe app (frontend)

Website-builder frontend for the consumer brand **Gummfit**, host-routed on gummfit.com. Self-contained vertical slice — parallel stack, does not share Matcha's `components/ui`, `api/client.ts`, or `hooks/useMe`. See root `CLAUDE.md`'s "Repo layout — products map" and `client/CLAUDE.md`'s app-first layout table for where this fits.

## Layout

- `routes.tsx` — route tree (mounted by `App.tsx` on `/cappe/*` and on the cappe host apex)
- `layout/` — `CappeLayout`
- `pages/` — incl. `site/` + `site/PageEditor/`
- `components/` — incl. its **own** `ui.ts` + `CappeSidebar` (not shared UI)
- `onboarding/` — `CappeOnboardingWizard`
- `api.ts` — `cappeApi`, own http client (not `api/client.ts`)
- `hooks/useCappeMe.ts` — own auth-state hook (not `hooks/useMe`)
- `host.ts` — `isCappeHost` / `cappeSiteHost` host detection
- `types.ts`, `data/` — cappe types, `cappeThemes`/`cappePagePresets`/`timezones`

## Backend pairing

Backend package is `server/app/cappe/` (own `CLAUDE.md`, cross-references `DOMAINS.md` for domain-reselling ops).

## Cross-cutting rules

Placement rules and boundary rules between the three client apps live in `client/CLAUDE.md` — read that before adding a file here. DB/deploy/test-data rules are in root `CLAUDE.md`.
