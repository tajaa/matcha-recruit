# Legal Pilot round 6 — evidence count shows but record rows don't render

## Context

Round 5 added `min-h-0` to the right-sidebar flex-col wrapper (`index.tsx:273`) to bound its height so `EvidencePanel`'s inner `overflow-y-auto` could scroll. That bounded the column — but it exposed the aggravating factor flagged in the round-5 plan. Reviewer (6th round) now reports:

> "I can see 'evidence 69 records' but there's no records listed below that"

## Root cause

Inside the bounded sidebar column, four panels share the height:
- `LegalContextPanel` — **variable, can be tall**: jurisdiction chain chips + a research-results block capped at `max-h-64` (16rem) — `LegalContextPanel.tsx:78`
- `SubjectScopeSetter` — ~5rem
- `EvidencePanel` — `flex min-h-0 flex-1 flex-col`, records in an inner `flex-1 overflow-y-auto` — `EvidencePanel.tsx:17,27`
- `PacketsPanel` — `max-h-[45%] shrink-0 overflow-y-auto` — `PacketsPanel.tsx:39`

`EvidencePanel` is the only `flex-1` child, and with `min-h-0` it is allowed to shrink to **zero**. When `LegalContextPanel` (after a research run) + `PacketsPanel` (`shrink-0`, refuses to yield, up to 45%) together consume the column, `EvidencePanel`'s `flex-1` basis collapses to ~0px. Its count header (`px-4 pt-4`, natural height) still renders — "69 records" — but the scrollable record list below it (`flex-1 overflow-y-auto`) gets ~0px height and shows nothing. Exactly "count shows, no records below."

The per-panel-scroll design is too fragile: it only works when the flex math happens to leave `EvidencePanel` a usable height, which a tall legal-landscape panel breaks.

## Fix — make the sidebar one scroll container, panels natural-height

Stop letting panels fight for flex space. The whole sidebar becomes a single vertical scroll; each panel renders at its natural height and the outer column scrolls. Records are always present (natural height) and always reachable (one scrollbar).

1. `client/src/pages/app/LegalDefense/index.tsx:273` — sidebar wrapper: keep `min-h-0` (bounds height for the scroll), add `overflow-y-auto`, drop nothing else:
   `flex min-h-0 w-80 shrink-0 flex-col border-l border-white/[0.06]` → `flex min-h-0 w-80 shrink-0 flex-col overflow-y-auto border-l border-white/[0.06]`
2. `client/src/pages/app/LegalDefense/EvidencePanel.tsx:17` — root: `flex min-h-0 flex-1 flex-col` → `flex flex-col` (natural height, no longer a flex-1 competitor).
3. `client/src/pages/app/LegalDefense/EvidencePanel.tsx:27` — record list: `flex-1 overflow-y-auto` → remove both classes (let rows render at natural height; the outer sidebar scrolls). The list `<div>` can drop its className entirely or keep a neutral one.
4. `client/src/pages/app/LegalDefense/PacketsPanel.tsx:39` — root: `max-h-[45%] shrink-0 overflow-y-auto border-t …` → `shrink-0 border-t …` (natural height; outer scroll reaches it). Keep the `border-t` + spacing.

Leave `LegalContextPanel.tsx:78`'s `max-h-64 overflow-y-auto` research block as-is — a bounded inner region for a potentially long case list is intended and pre-existing; it composes fine inside the outer scroll.

Scope: **Legal Pilot only.** `client/src/pages/broker/BrokerPilot/` has the same shape but is out of ticket — leave it.

Reviewed for issues:
- `RecordViewer` (opened on record click) is a `Modal` (`RecordViewer.tsx:218`, own `max-h-[85vh]` + overflow) — independent of panel layout, unaffected.
- Removing `min-h-0`/`flex-1` from EvidencePanel root restores `min-height:auto` = content height, so nothing can collapse inside the outer scroll. Keeping them would reintroduce the round-6 bug.
- Accepted tradeoff: WORK PRODUCT is no longer pinned at the sidebar bottom — it scrolls with the content. The reviewer's priority is seeing evidence records; a pinned packets block is what starved them of space.
- Longest case (Compliance expanded, 100 rows) = one long sidebar scroll; backend caps the list at 100, acceptable.

## Verification

1. `cd client && npx tsc --noEmit --incremental false` — clean (className-only edits).
2. Dev UI (`:5174`): open `/app/legal-pilot` → "Jones vs 720 Behavioral". Confirm: (a) evidence group rows render under the count immediately; (b) expanding any group shows its record rows; (c) after a Research run (tall Legal-landscape block) the evidence rows STILL render and the whole sidebar scrolls end-to-end to Work Product; (d) short window height — everything still reachable by scrolling. Test both before and after research so the tall-legal-landscape case is covered.
3. Reviewer retest in werk UI (needs frontend deploy — FE-only change).

## Critical files

- `client/src/pages/app/LegalDefense/index.tsx:273`
- `client/src/pages/app/LegalDefense/EvidencePanel.tsx:17,27`
- `client/src/pages/app/LegalDefense/PacketsPanel.tsx:39`
