# Work app (matcha-work / werk / werk-lite frontend)

One product, three URL surfaces sharing this tree: `/work` (business, inside a Matcha company), `/werk` (personal), `/werk-lite` (standalone business work-chat). Dispatch is via `WorkSurfaceContext` — gate on identity, brand/paths on surface; **never hardcode `/work` in a shared page**. See root `CLAUDE.md`'s Matcha-work / Werk / Werk-Lite sections and `client/CLAUDE.md`'s app-first layout table for the product-level picture.

## Layout

- `routes/` — `WorkRoutes`, `WerkRoutes`, `WerkLiteRoutes`, `WorkSurfaceContext`
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
