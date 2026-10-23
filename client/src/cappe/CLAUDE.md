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
  at `/cappe/writer/new`), `emails/Emails.tsx` (`sites/:siteId/emails`: a story emailed to followers;
  its API still says "issues"). `CappeSidebar` gives a writer the magazine's nav (Stories, Issues,
  Library, Followers = the Subscribers page, Emails, settings); a business site gets Issues beside Magazine.
  Issues in print (cappemag07): `issues/IssuesPage.tsx` (`sites/:siteId/issues`, the wall) and
  `issues/IssueEditor.tsx` (`…/issues/:issueId`): one undoable document (`issues/issueDoc.ts`) with
  Stories / Cover / Contents tabs (`IssueStories.tsx` + `StoryPicker.tsx`, `CoverPanel.tsx`,
  `ContentsPanel.tsx`) and the whole issue previewed in `reader/BookFrame.tsx` (its `spread` prop turns to
  the cover or the contents with the tab). `issues/coverVocab.ts` mirrors the server's cover lists and
  limits (pinned by a server test); `issueDoc.fitMasthead` mirrors `issue_schema.fit_masthead`.
  `editor/PictureSlot.tsx` is the library-picture field the story and cover editors share. In a frame a
  contents entry can't be heard, so `prepareFrame` turns each `#mz-s-` link into a label for a hidden
  radio that `wireBook` watches.
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
  `ShelfStory.tsx` (`…/:story`: the server's page in `reader/BookFrame.tsx`, with `allow-popups` for web
  links; its paywall gets a link to the magazine's page here, and its other pages open on the site).
  `stories/Stories.tsx` (the wall of covers at `sites/:siteId/stories`; `/blog` redirects here),
  `editor/StoryEditor.tsx` + `editor/BlockEditor.tsx` (blocks, a library picker, a live preview
  iframe fed by `POST /stories/preview`), `settings/MagazineSettings.tsx`. `storyBlocks.ts` mirrors
  the server's block/layout lists and a server test keeps them equal.
  A story page in one of our frames always goes through `reader/BookFrame.tsx` (preview, "View as a
  reader"): the frames are `sandbox="allow-same-origin"` with no scripts, and Safari runs nothing we
  attach inside them, so the arrows, page count and keys are outside and `reader/book.ts` drives the
  pages (see the Cappe server CLAUDE.md, magazines). Don't add listeners to a frame's document.
  **The story editor is one design workspace** (`editor/StoryEditor.tsx` + `magazine/workspace/`, 2026-10-22;
  there is no Outline any more): a left rail of panels (`AddPanels.tsx`: Text, Photos, Elements; `LayersPanel.tsx`:
  the story's blocks in order with each picture's layers, topmost first, to select, hide, lock, rename and drag),
  the story's own pages in the middle (`EditFrame`, with zoom), and a right inspector for what is selected
  (`LayerInspector.tsx` for layers; `ArtInspector.tsx` for a picture or designed page: what to add on it, what is
  on it, its own settings; `canvas/BlockPanel.tsx` over `editor/BlockOptions.tsx` for other blocks; the story's
  settings when nothing is). Words, shapes and pictures go ON the picture or page in hand; blocks go into the
  story after the block in hand (`workspace/actions.ts`, pure: `addText`/`addShape`/`addImage`/`addBlock`/
  `addPage`, and `command` for copy/cut/paste/duplicate/group/ungroup/arrange/delete, with a module-level
  clipboard any picture can paste). A design changed in the panels is drawn on the page at once
  (`designMessages` → `EditFrame`'s `outbox` → the frame's `mz-design`; worked out during render from the
  previous document, never in an effect) while the server sets the page again; one changed on the page
  (`mz-layers`, typing) isn't sent back. Keys pressed in the panels outside a box typed in act on the layers
  as the page's do (`panelKey`). The design model, ops and renderer are `magazine/design/` (`designOps.ts`,
  `designRender.ts` = the server's bytes, `fonts.ts`/`fontStack.ts`); controls are `workspace/controls.tsx`
  (scrub-to-change numbers that take sums, `evalSum`; colour picker with eyedropper; gradient fills) and
  `FontField.tsx`. On the page, `frame/layers.ts` selects, moves, resizes, turns, snaps (with guides), lassos and
  nudges layers, and double-click types in one. The issue editor still opens on its pages with the slim panel.
  **Editing on the page** (`magazine/canvas/`): `EditFrame.tsx` is the one frame that
  runs scripts: `sandbox="allow-scripts"` with no same-origin. It writes the editor runtime
  (`magazine/frame/`, TypeScript + Tiptap) into each page: `vite-mz-frame.ts` bundles it into one script
  and its stylesheet (`virtual:mz-frame`, rebuilt when a frame file changes in dev, empty in Vitest; inlined,
  so no CSP change), and it talks only by `postMessage`. Rich fields are Tiptap editors mounted on the
  field itself (`frame/rich.ts`, opened from the page's `data-mz-rt` registry); plain fields are
  `contenteditable`. `frame.test.ts` loads it onto a small edit page in jsdom. It is double-buffered (a new render
  loads hidden, is sent `mz-goto` with the selection or spread, and swaps in on `mz-shown`) and never
  replaced while words are typed (`mz-editing`). Everything the page sends goes through `bridge.ts`
  (source, shape, indexes, field names, lengths); `storyDoc.ts` / `issueEdits.ts` apply it and drop an edit
  that names a block or field the story doesn't have (`fields.ts`, pinned by the server). Rich text arrives
  as a document, cleaned to what the server keeps (`canvas/rt.ts` `cleanRt`, with `rtToMd` for the Markdown
  beside it; both pinned by `server/tests/cappe/fixtures/magazine_rt_cases.json`). The issue editor's panel
  beside the page is `BlockPanel.tsx` (over `editor/BlockOptions.tsx`), `issues/CoverPanel.tsx`'s exported
  sections, and `ContentsPanel`. The issue editor keeps an
  unsaved copy of each story edited on its pages (`IssueDoc.drafts`), previews them with the issue
  (`stories_content`) and saves each changed story's words first (`storyWordsBody`: never its status),
  then the issue (a released issue's save publishes its drafts, so it must publish the new words; it waits
  if a draft's words failed), naming any that fail. A save is settled onto the document as it is by then
  (`useHistory().map` + `issueDoc.settleIssue`/`settleStories`: words typed meanwhile stay unsaved) and
  pins each story's pre-save words into the undo states that showed them (`pinStories`), so undo reaches
  back past a save. Release and Withdraw change only the issue's status, never the document, so unsaved
  changes (the issue's and its stories') survive both. `EditFrame` drops a render that was loading when
  words were typed (it predates them) and numbers renders with a counter that never repeats. Field lengths are cut by whole characters
  (`fields.clip`), never half an emoji.

## Backend pairing

Backend package is `server/app/cappe/` (own `CLAUDE.md`, cross-references `DOMAINS.md` for domain-reselling ops).

## Cross-cutting rules

Placement rules and boundary rules between the three client apps live in `client/CLAUDE.md` — read that before adding a file here. DB/deploy/test-data rules are in root `CLAUDE.md`.
