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
- `components/TemplateGallery.tsx` — the template shelf (category filter chips, full-site preview
  modal, "For you" ordering by the Discover category the wizard asked for). Shared by
  `pages/CappeTemplates.tsx` and the wizard's last step. Every template is on every plan; a paid
  account's previews pass `premium=1` so it sees the polish it will keep.
- `onboarding/CappeOnboardingWizard.tsx` asks the Discover category ONCE (step 3) — it sorts the
  shelf and seeds `directory_category` on `POST /sites/from-template`.
- `utils/plan.ts` — `isPremiumPlan`, the client mirror of the server's `design_gate.PREMIUM_PLANS`.
- `magazine/` — photo-journalism magazines (server spec: `server/app/cappe/CLAUDE.md` §Magazines).
  `library/LibraryPanel.tsx` is the picture library with alt text, captions and credits (the
  Library page at `sites/:siteId/library`; pass `onPick` to use it as a picker).
  `library/StockSearch.tsx` is its "Find free photos" section: archive chips, license badges,
  multi-select import, "stock a topic", and polling of the server's imports. Archive thumbnails are
  signed paths under the Cappe API (`cappeApiBase` + `thumb`), never the archive's own URLs.
  `library/IllustrateForm.tsx` draws a labeled AI illustration (a refusal for a real person shows as
  a refusal, `code === 'real_person'`). `editor/AssistPanel.tsx` is the editor's Assist (draft,
  headlines, captions, tighten, archive searches): it sends the editor's unsaved story, shows each
  proposal, and changes nothing until the writer applies it.
  Writers (`account_type='writer'`): `writers/WritersLanding.tsx` at `/cappe/magazines/start`,
  `CappeSignup writerOnly` / `CappeLogin writerOnly` at `/cappe/magazines/signup|login`,
  `writers/WriterHome.tsx` (`/cappe/writer`: their stories, or `onboarding/MagazineOnboarding.tsx`
  at `/cappe/writer/new`), `issues/Issues.tsx` (`sites/:siteId/issues`). `CappeSidebar` gives a
  writer the magazine's nav (Stories, Library, Followers = the Subscribers page, Issues, settings).
  Where an account lands after auth is one function: `utils/postAuthHome.ts`.
  Paid readers (cappemag05): the paid section of `settings/MagazineSettings.tsx` (price typed in dollars,
  `settings/price.ts`), "Who can read it" in the story editor (a Paywall block is offered once a story is
  for subscribers), `readers/Readers.tsx` (subscriptions and free comps) and `earnings/Earnings.tsx`
  (the ledger and `StripeConnectCard magazineFeeBps`, which names the magazine share, not the plan fee).
  Reader accounts (cappemag06, `account_type='reader'`): `shelf/` is their dashboard, outside
  `CappeLayout` (which sends a reader there): `CappeSignup readerOnly` / `CappeLogin readerOnly` at
  `/cappe/reader/signup|login` (a `next` inside `/cappe/reader` is honoured, `shelf/readerPaths.ts`),
  `shelf/ReaderLayout.tsx` (bar + sign-in gate), `Shelf.tsx` (`/cappe/reader`: every magazine held, open one
  by its address), `ShelfMagazine.tsx` (`/cappe/reader/m/:slug`: subscribe, cancel/keep, stories) and
  `ShelfStory.tsx` (`…/:story`: the server's page in a `sandbox="allow-same-origin"` frame, turned by
  `reader/book.ts`; its links and paywall button are wired from the parent).
  `stories/Stories.tsx` (the wall of covers at `sites/:siteId/stories`; `/blog` redirects here),
  `editor/StoryEditor.tsx` + `editor/BlockEditor.tsx` (blocks, a library picker, a live preview
  iframe fed by `POST /stories/preview`), `settings/MagazineSettings.tsx`. `storyBlocks.ts` mirrors
  the server's block/layout lists and a server test keeps them equal.

## Backend pairing

Backend package is `server/app/cappe/` (own `CLAUDE.md`, cross-references `DOMAINS.md` for domain-reselling ops).

## Cross-cutting rules

Placement rules and boundary rules between the three client apps live in `client/CLAUDE.md` — read that before adding a file here. DB/deploy/test-data rules are in root `CLAUDE.md`.
