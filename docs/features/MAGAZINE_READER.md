# Magazine reading room

Open a story from My magazines or the Feed. It opens in a reading modal: inset on a desktop,
full screen in a phone browser. Close returns to its magazine. The existing page arrows and
swipe turn pages; Studio stories also offer Text view for reading their words at a comfortable size.

Select words (long-press and move the selection handles on a phone), then choose Highlight,
Underline or Comment. Comment without selecting words adds a note to the current page. Notes opens
Your notebook, beside the page on a desktop and as a separate pane on a phone; Return to pages
closes that pane. Click a note's page label to return to its passage. Delete removes the saved note.

Notes are private to the signed-in account and saved across devices. Pages and Text view keep their
own marks, since their text order can differ. If a writer changes a passage, its saved quote stays in
the notebook; ambiguous matches do not highlight a different passage. Page-only notes refer to the
page at the time of writing; classic flowing pages can paginate differently after resizing.

A failed save keeps the selection/comment and reuses its request ID when retried. A failed deletion
keeps the note. Leaving with an unsaved comment asks before discarding it. An unavailable notes API
leaves the pages readable and offers Retry loading in the notebook.

The existing magazine entitlement applies. Paid stories require a live subscription or comp to read
or write annotations. This feature does not change checkout, add a single-issue purchase product,
or add public/social comments. The magazine currently sells subscriptions; an issue-purchase
entitlement would be a separate billing change.

## Deployment

Apply Alembic revision `cappereader01` after `cappefont01` before deploying the API. It adds only
`cappe_reader_annotations` and its post index. Existing rows and payment data are untouched.
No migrations are applied by this PR. Downgrade refuses while annotations remain; export or deliberately
remove them before downgrading. Deploying the frontend first leaves reading available, with a notes
loading error until the API is available.

## Validation

- From `client/`: `npm run build`
- From `client/`: `npm run test:run -- src/cappe/magazine/reader src/cappe/magazine/shelf/shelf.test.tsx`
- From `server/`: `python -m pytest tests/cappe/test_cappe_reader_annotations.py -q`
- From `server/`: `python -m pytest tests -q` (unit suite; no DB required)

Browser checks should cover Chromium and WebKit at desktop and phone widths: select formatted words,
paint overlapping marks, save a page comment, close/reopen the notebook, reload saved notes, and close
the dialog. Verify all four annotation controls fit at 320 px, safe-area padding, focus containment,
and native text selection. Physical iOS/Android selection handles still deserve a device check. Escape is handled while
focus is in the outer dialog controls; a script-less iframe does not deliver its keyboard events
to the parent, so the visible Close reader button is available while the page has focus.
