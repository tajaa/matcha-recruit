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
- `host.ts` — `isCappeHost` / `cappeSiteHost` host detection; `cappePath()` drops the `/gummfit` or `/cappe` prefix on gummfit.com (the tree is served at `/` there), and `cappeAuthPaths` holds the sign-in, setup and reset links. Use them for public and sign-in links, not literal `/gummfit/...`. `App.tsx` redirects old `gummfit.com/gummfit/...` links to the root
- `types.ts`, `data/` — cappe types, `cappeThemes`/`cappePagePresets`/`timezones`
- `components/TemplateGallery.tsx` — the template shelf (category filter chips, full-site preview
  modal, "For you" ordering by the Discover category the wizard asked for). Shared by
  `pages/CappeTemplates.tsx` and the wizard's last step. Every template is on every plan; a paid
  account's previews pass `premium=1` so it sees the polish it will keep.
- `onboarding/CappeOnboardingWizard.tsx` asks the Discover category ONCE (step 3) — it sorts the
  shelf and seeds `directory_category` on `POST /sites/from-template`.
  Its **Online only** answer is the quick store instead: store name + one line → starter design
  and optional first product → `POST /sites/quick-store` → `onboarding/StoreReady.tsx`
  (`sites/:siteId/ready`): private storefront preview, draft products, and required launch actions.
  The owner reviews product details and policies before publishing; examples never become real products.
- `utils/plan.ts` — `isPremiumPlan`, the client mirror of the server's `design_gate.PREMIUM_PLANS`.
- `magazine/` — photo-journalism magazines (server spec: `server/app/cappe/CLAUDE.md` §Magazines).
  `library/LibraryPanel.tsx` is the picture library with alt text, captions and credits (the
  Library page at `sites/:siteId/library`; pass `onPick` to use it as a picker).
  `library/StockSearch.tsx` is its "Find free photos" section: archive chips, license badges,
  multi-select import, "stock a topic", and polling of the server's imports. Archive thumbnails are
  signed paths under the Cappe API (`cappeApiBase` + `thumb`), never the archive's own URLs.
  `library/IllustrateForm.tsx` draws a labeled AI illustration (a refusal for a real person shows as
  a refusal, `code === 'real_person'`). `editor/AssistPanel.tsx` is the editor's Assist (headlines,
  captions, archive searches; article bodies are written directly): it sends the editor's unsaved story, shows each
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
  `ShelfStory.tsx` opens `reader/ReaderModal.tsx` at `…/:story`: a native dialog (full viewport on a phone,
  inset on desktop), with a private notebook beside the pages or in place of them on a phone. Select words
  to highlight, underline or comment; Comment without a selection adds a page note. `reader/annotations.ts`
  polls selection from the script-less frame (no listeners in it), and paints plain-text quote anchors with
  context. Ambiguous/deleted quotes stay in the notebook without marking other words. Pages/Text view have
  separate anchors; the notebook says they are private. Writes reuse a UUID after an uncertain save, retain
  the draft on failure, and delete only after the server confirms. `reader/commentDraft.ts` keeps
  account/story/view-scoped comment drafts and retry UUIDs in memory across history navigation;
  refresh/tab close warn while any retained draft is dirty, including outside the reader, and sign-out
  asks before discarding the account's drafts. Completed saves clear only the unchanged comment
  they submitted; marks and newer typing keep the draft. Conflicting quote context stays unresolved.
  The reader does NOT enable BookFrame's
  `keys` option: its recurring iframe blur would interrupt native touch-selection handles. The regular page
  arrows and swipe still work. The server's page stays in `reader/BookFrame.tsx`, with `allow-popups` for web
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
  Article bodies reject pasted and dropped text through `magazine/writing.ts`; the frame applies it to
  rich body fields, and Studio applies it to paragraphs with the Body text role (including the default).
  Headlines, captions and other text roles keep paste. This is an editor rule, not authorship verification.
- `studio/` — **Gummfit Studio** (2026-10-22), the design application for stories made of pages, full
  screen at `/cappe/studio/:siteId/story/:postId` (outside `CappeLayout`; the classic `StoryEditor` hands a
  paged story to it). Server spec: `server/app/cappe/CLAUDE.md` §Gummfit Studio. Its core is plain
  TypeScript: `model/` (the document's types, `ops.ts` pure operations, `units.ts`, `limits.ts` mirroring the
  server), `compose/` (HarfBuzz `shaper.ts` + the greedy `compose.ts`; every edit composes again in
  `store/store.ts`, so a stored document is always set as shown), `render/layoutRender.ts` (byte-equal to the
  server's renderer; `render/sink.ts` is the **only** place allowed `innerHTML` — eslint bars it everywhere
  else in `studio/`), `text/` (a hidden ProseMirror owns typing; `caret.ts` draws the caret and selection
  from the composed lines; arrows, Home/End and the ⌘-arrows move by the composed lines, and in the Story
  Editor by the browser's), `canvas/` (pasteboard, rulers, guides, handles, `usePointer.ts` for every tool;
  the board has half a view of slack around it so any page can be centred: convert with
  `geometry.boardOffset`). React panels read the store with `useStudio` (useSyncExternalStore); a drag never
  renders React. Panel fields must `preventDefault` Enter: applying type hands focus back to the text, and
  an Enter let through would replace the selection. The Studio is always dark (`ui/studio.css` puts
  Tailwind's own zinc ramp back inside `.studio-dark`, whatever the dashboard theme). Fonts: `fonts/faces.ts`
  (the manifest), `fonts/loader.ts` (FontFace from the same bytes HarfBuzz measures).
  `picture/` is the **Picture Editor** (double-click a picture frame, ⇧⌘E, the Object panel or menu):
  `recipe.ts` mirrors the server's normalizer, `develop.ts` holds the shader and its CPU twin (tests),
  `gl.ts` draws the preview and the full-size bake, `segment.ts` + `segment.worker.ts` run the cut-out
  model (onnxruntime-web, `optimizeDeps.exclude`d, a module worker) and `samMath.ts` its arithmetic. The
  cut-out's mask always follows the recipe's clicks (an effect keyed by them, a few masks kept), so undo,
  redo, Reset all and reopening an edit show and save the mask of the clicks that are there.
  **The issue board** (`ui/board/Board.tsx`, `dialog === 'board'`, ⌥⌘P or Board in the top bar) draws every page with
  `pageItemsHtml` + `setHtml`, spread by spread and story by story. Its pure parts: `model/sections.ts` (stories as runs
  of pages; `moveBlock` moves pages or a whole story; `keepSections` re-anchors stories after any edit),
  `model/crops.ts` (linked crops: one picture through several frames on a spread; `keepLinks` after any edit — both run
  in `Store.edit`, so nothing else needs to know), `model/rhythm.ts` (each page's beat from a coverage grid),
  `model/gutter.ts` (words in the strip by the spine; View → Gutter safety shades it), `ui/board/sequence.ts` (what
  moves together: a page with a picture across the spine brings its facing page) and `ui/board/pairs.ts` (paired
  spread layouts). Object panel → Across the spread and the Object menu make and link spread pictures.
  **The guide** (`ui/StudioGuide.tsx`, words in `ui/guideContent.ts`) explains every part of the Studio; it
  opens on a first visit (localStorage `cappe-studio-guide-seen`), from Help, the top bar's ? and the
  Picture Editor's ?. **A change to a tool, panel, menu or key changes its section in the same PR**; the
  shortcuts section is built from `COMMANDS`, and a test holds the tool keys to the commands.
  **The selection bar and the right-click menu** (Canva-style, 2026-10-27): `ui/SelectionBar.tsx` floats over the
  selection with the controls changed most (text: font, size, colour, B/I/U, alignment, spacing; pictures: replace, edit,
  cut out, crop, across the spread; shapes and lines: fill and border; everything: position, transparency, lock,
  duplicate, delete, more), placed by the pure `ui/barPlace.ts` (above, else below, else the top of the view). It is a
  sibling of the scroller, never inside it, and nothing above it may get a `transform`/`filter`/`backdrop-filter`:
  its popovers are `position: fixed`. It hides while `State.gesture` (set by `usePointer`'s `drag` on the first move).
  `ui/ContextMenu.tsx` opens at `State.menu` (a right-click via `geometry.menuTarget`, or the bar's ⋯) with rows from
  `ui/menuRows.ts`; both run `COMMANDS`, never logic of their own. Align and Space evenly are `canvas/align.ts`
  (pasteboard points, so a spread's two pages line up; `rehome` puts anything whose middle crossed onto that page, the
  same step a drag's drop uses).
  **Editorial collections** (`ui/add/collections.ts`, `CollectionsTab.tsx`, `applyCollection.ts`): Templates opens
  on four ten-page art directions; Single pages keeps the original templates. A collection starts a blank
  story or inserts after the current spread (padding keeps its cover on the right and preserves original page sides), fitted to the story's
  size, with fresh ids and linked text preserved, in one undo step. Existing paywall pages follow their
  original pages. ASCII-escaped size and composed-line limits are checked after composition, before committing.
  Saved collections use `collectionsApi.ts`
  and `/api/cappe/studio/collections`: account-wide, max 50, each up to 32 pages / 1 MB. `model/collections.ts`
  strips library photo ids, image captions, compositions and reader access; type, words and guides remain.
  Page templates and collections share `ui/add/preparation.ts` so switching tabs cannot overlap placement.
  `collectionLibrary.ts` holds pending library writes and feedback per Studio store across panel remounts,
  invalidates stale reads, and reuses a save request UUID for an unchanged retry. `collectionPreview.ts`
  shares one composition across a collection's thumbnails; failed preparation can be retried.
  Built-in collections and single-page templates use `ui/add/samplePreview.ts` only at the render
  boundary: transient sample asset IDs and bundled same-origin photography illustrate the designs.
  Source documents, placement, saved collections and the library never receive those sample images.
  Saved/unknown collections get no sample projection. The guide and template panel disclose this.
  **Editorial type** (feature 4): the Character panel's Kerning (⌥←/⌥→ at the caret, `ops.kernAt`; with letters
  selected, tracking; letters typed after a kerned one don't take its kerning, `unkern`). **No browser kerns across a
  change of letter-spacing** (Chrome does across same-font spans otherwise; the composer never does across runs), so a
  word's first manual kern writes each pair's font kerning into its letters first, or the first ⌥← would open the pair;
  checked in Chromium 2026-10-24. Also Alternates and figures (the
  face's own OpenType features of `LIMITS.OT_TAGS`, measured by HarfBuzz with the same features, `Shaper.em(sha, text, ot)`)
  and Your fonts (`ui/FontsDialog.tsx`, `ui/siteFonts.ts`: the site's uploads, registered in the `FaceBook` and in
  `model/doc.registerFaces` so `charOf` keeps a `u-` key at its nearest face); the Paragraph panel's Drop cap and Keep
  lines. The composer (`compose/compose.ts`) sets each paragraph through `layPara` and sets it again (≤3 times) to mend
  a widow, orphan or runt, falling back to the first setting if mending would overset. Text wrap (`compose/wrap.ts`):
  `threadWraps` turns wrap items on a frame's page into rectangles in its coordinates (a subject's rows through
  `picturePlace`, the renderer's object-fit/position/scale arithmetic), joins the composition cache key, and the
  composer fills each line in the widest `room` at its height. **Subject in front** (`model/subject.ts`, `ui/subject.ts`):
  the photo stays under the lettering and a linked `cutout` partner showing its cut-out goes over it (`keepLinks` lets a
  partner keep its own picture and drops it when the photo changes). The photo behind is `backingFor` the cut-out: its
  parent, or an edit with the same recipe minus the mask, which the Picture Editor saves alongside (`backing`) so the
  pair lines up pixel for pixel. `isPartner` (server `schema.is_partner`) holds only while a visible photo shares the
  link: then no credit, and `geometry.hitItem` clicks it only on its `shape` unless it is selected. Collections leave own fonts and cut-out partners behind (`portableCollection`).
  **Gummfit cuts** (`fonts/cuts.ts`, the server's `studio/cuts.py`): Studio-only display and width cuts, listed after
  the catalog in `FontField` (`cuts` prop, previewed from Google in the family they are cut from), accepted by
  `charOf`, and set by `layoutRender.runStyle` in their `stand_in` family while their faces aren't built.
  **Magazine identity** (`studio/model/identity.ts`, `ui/panels/IdentityPanel.tsx`): named paragraph/character
  styles and swatches are references, with local attributes as overrides. `resolveParas` supplies effective
  type to composition/rendering/font loading; editable paragraphs and ProseMirror keep sparse references,
  including explicit default/false overrides. A style change recomposes every linked use in the document.
  Parent layouts are portable page snapshots (no site photos or cross-page threads), drawn behind local
  content and composed once per definition. Detach creates fresh local IDs; scaled copies preserve appearance.
  Page furniture is generated from page order with per-page hiding/header overrides. All reader/print rendering
  uses the same resolver. `identityLibrary.ts` retains pending writes/errors across panel mounts, refreshes
  saved templates and rejects stale read results. `/sites/:id/studio/identity` stores a versioned magazine
  template; document snapshots keep published issues stable until explicitly updated. New paged stories copy
  the saved identity. Import merges by name with ID remapping. See the Studio guide's `identity` section.

## Backend pairing

Backend package is `server/app/cappe/` (own `CLAUDE.md`, cross-references `DOMAINS.md` for domain-reselling ops).

## Cross-cutting rules

Placement rules and boundary rules between the three client apps live in `client/CLAUDE.md` — read that before adding a file here. DB/deploy/test-data rules are in root `CLAUDE.md`.

## Quick-start storefronts

Writer setup at `/cappe/writer/new` uses `magazine/onboarding/MagazineDesigns.tsx`: the four
Studio collections, real font loading/composition and the shared `PagePreview` renderer. Writers
name the magazine, browse all ten pages and open a private Studio draft directly. `starter.ts`
fits their name into the cover without changing the source collection. Photos remain a transient
preview projection; the submitted document has empty frames. Tagline, topics and website masthead
are optional. `/magazine/quick-start` creates the site and draft together; one request UUID survives
retries in the mounted form, and a submission guard prevents duplicate clicks. An uncertain network/5xx
result freezes that request's details and offers Retry opening my draft, independently of a late taken
handle check. An initial definite 4xx rejection restores editing; later retry errors preserve the pending
request because they cannot rule out an earlier commit. The server retains schema-validated composition
in the first draft, so publishing without a Studio edit keeps the designed geometry. Saved library
collections still recompose when placed. Publishing keeps the existing plan/readiness gates.

`CappeOnboardingWizard` offers online-only sellers three product-first designs (the registry's
`online-store` tag). A first product is optional; store and product remain drafts. `StoreReady` uses
an owner-only, sandboxed rendered preview, including draft products or clearly labelled examples.
Required readiness actions stay visible and disable publishing until complete. The general
`TemplateGallery` prioritises store, portfolio/personal and blog designs for business, personal and
writer accounts respectively; an explicit category takes precedence and the full shelf stays available.
The wizard's three design cards share `TemplateGallery`'s `TemplatePreview`: scaled, sandboxed live
renders of the actual designs, with inert sample photography. They replace approximate colour swatches
so the chosen layout matches the draft storefront. Preview load failure never blocks store creation.
