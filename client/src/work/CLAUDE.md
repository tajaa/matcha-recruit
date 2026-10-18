# Work app (matcha-work / espresso / werk-lite frontend)

One product, three URL surfaces sharing this tree: `/work` (business, inside a Matcha company), `/espresso` (personal; legacy `/werk` redirects here), `/werk-lite` (standalone business work-chat). Dispatch is via `WorkSurfaceContext` — gate on identity, brand/paths on surface; **never hardcode `/work` in a shared page**. See root `CLAUDE.md` and `client/CLAUDE.md` for the product-level picture.

## Layout

- `routes/` — `WorkRoutes`, `EspressoRoutes`, `WerkLiteRoutes`, `WorkSurfaceContext`
- `layout/WorkLayout.tsx` — shared surface shell
- `pages/` — incl. `Inbox` (also surfaced by Matcha at `/app/inbox`)
- `components/shell/` — sidebars, kanban, notifications, connections chrome
- `components/panels/` — in-canvas feature panels (AI agents, recruiting pipeline, editors)
- `components/channels/`, `components/inbox/`
- `api/` — `matchaWork`, `channels`, `channel*`, `inbox`, `projectSocket`, `threadSocket`, `notifications` (own http surface, not `api/client.ts`)
- `hooks/` — presence, livekit, channel-notifications, voice
- `types.ts`, `data/projectTemplates`

## Backend pairing

Backend package is `server/app/matcha/routes/matcha_work/` (own `CLAUDE.md`) + `server/app/werk/` (channels/calls/job-postings, own `CLAUDE.md`) for the werk-lite chat surface specifically.

## Cross-cutting rules

Placement rules and the boundary rules between the three client apps live in `client/CLAUDE.md` — read that before adding a file here. DB/deploy/test-data rules are in root `CLAUDE.md`.

## Personal task recaps

Recaps are the Recaps view of Tasks (`pages/Tasks.tsx`, `?view=recaps&recap=<id>`;
`components/recaps/paths.ts:recapsPath` builds every link): `RecapList` on the left,
`RecapView` in the middle. `pages/Recaps.tsx` and `pages/Recap.tsx` only redirect the
old `/espresso/recaps[/:id]` URLs (the recap email links to the second). Preferences
are owner-scoped and cleared by auth cache reset; private playback reads use request
sequencing and signed URL refresh. Source links use the list's `source_id` filter. `recaps/render/` builds a separate
trusted bundle with `npm run build:recaps`; the media worker never loads the
authenticated application. Rollout: `docs/ops/ESPRESSO_RECAPS.md`.
