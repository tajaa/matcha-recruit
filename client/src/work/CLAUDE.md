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

## Résumé

The person's résumé (`user_resumes`) is the Résumé view of Tasks
(`pages/Tasks.tsx`, `?view=resume`; `components/resume/paths.ts:resumePath`):
`ResumePane` shows where it is kept, the original (a fresh fifteen-minute link
on each open), what was read from it, and the text Espresso uses, editable in
place. `hooks/useMyResume.ts` is the one shared, owner-scoped copy, so a résumé
dropped into a job search form (`ResumeFormField`, drawn for a field with
`widget: "resume"`) shows in Tasks at once. Rules: `server/.../job_search/CLAUDE.md`.
A job's pane can tailor that résumé to the posting (`pages/JobSearch/TailoredResume.tsx`,
"Your résumé for this job"); the rules for what may be rewritten are in the same doc,
§Tailored résumé.

## Sales

`pages/Sales.tsx` (`/espresso/sales`) is the web review-and-send surface for
sales campaigns, over `api/matchaWork/sales.ts`; the Mac Pipeline is the other.
`pages/Sales/useSales.ts` tags what it loads with the workspace or campaign it
is for and polls a sending campaign; `salesLogic.ts` holds the CSV import
parser (the Mac's header aliases) and what may be sent. The server owns every
rule (review tokens, footer, opt-outs, the consulting draft checks): the page
shows them. `Sales/SalesGuide.tsx` is the how-it-works wizard (first visit,
and "How it works"), in the same shape as `Tasks/TasksGuide.tsx`. Rules:
`docs/ESPRESSO_SALES.md`.

## Personal task recaps

Recaps are the Recaps view of Tasks (`pages/Tasks.tsx`, `?view=recaps&recap=<id>`;
`components/recaps/paths.ts:recapsPath` builds every link): `RecapList` on the left,
`RecapView` in the middle. `pages/Recaps.tsx` and `pages/Recap.tsx` only redirect the
old `/espresso/recaps[/:id]` URLs (the recap email links to the second). Preferences
are owner-scoped and cleared by auth cache reset; private playback reads use request
sequencing and signed URL refresh. Source links use the list's `source_id` filter. `recaps/render/` builds a separate
trusted bundle with `npm run build:recaps`; the media worker never loads the
authenticated application. Rollout: `docs/ops/ESPRESSO_RECAPS.md`.
