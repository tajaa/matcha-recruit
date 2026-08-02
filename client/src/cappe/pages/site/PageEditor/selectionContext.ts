/** Pure decision logic for Merlin's STICKY selection context.
 *
 *  Without stickiness, two things silently break the "Working on X — what
 *  should we do here?" chip: a click on a section's dead space posts a
 *  `cz-selection` shaped `{field:null, element:null}`, which downgrades a
 *  fine-grained "Editing: …" chip to nothing; and a click on a DIFFERENT
 *  section repoints the whole context immediately, with no chance to say
 *  "no, keep what I was doing." `useCanvasBridge.ts` calls these two
 *  functions from its `cz-select`/`cz-selection` message handlers so the
 *  branching logic is unit-testable without a DOM or an iframe.
 *
 *  Kept out of the hook deliberately: `useCanvasBridge` has no test coverage
 *  today (see its own file header) and this is the part of it worth pinning.
 */
import type { CanvasSelection } from './useCanvasBridge'

/** A different section the user clicked while a Merlin context was already
 *  active — staged, not applied, until the panel's "Switch" confirms it.
 *  Keyed on the block's stable `_k` (a numeric index would go stale under a
 *  reorder/insert between the click and the confirm). */
export type PendingSelection = { blockKey: string; selection: CanvasSelection | null }

/** `cz-select` (a click that changed which BLOCK is targeted) routing.
 *  'apply' is today's behavior — select immediately. 'stage' parks the new
 *  block as a pending switch without touching the current context. */
export function decideSelect(opts: {
  sticky: boolean
  currentBlock: number | null
  incomingBlock: number
  incomingKey: string | undefined
}): { action: 'apply' } | { action: 'stage'; pending: PendingSelection } {
  const { sticky, currentBlock, incomingBlock, incomingKey } = opts
  if (!sticky || currentBlock == null || incomingBlock === currentBlock || !incomingKey) {
    // non-sticky (Form/Canvas editing without Merlin): today's behavior
    // no context yet: first pick should never require confirmation
    // same block re-clicked: not a "switch", just a refinement
    // unresolvable index: iframe DOM lagging blocks state — leave as today
    return { action: 'apply' }
  }
  return { action: 'stage', pending: { blockKey: incomingKey, selection: null } }
}

/** `cz-selection` (field/range/element detail within a block) routing.
 *  - 'stage'  — the detail belongs to the block already staged as pending;
 *               ride it there so Switch applies the FULL context, not just
 *               the section.
 *  - 'ignore' — sticky + an empty shape (field and element both null): the
 *               dead-space click that used to silently blank a finer chip.
 *  - 'apply'  — today's behavior (also covers non-sticky mode entirely). */
export function decideSelectionUpdate(opts: {
  sticky: boolean
  pending: PendingSelection | null
  next: CanvasSelection
}): 'stage' | 'ignore' | 'apply' {
  const { sticky, pending, next } = opts
  if (sticky && pending && next.block === pending.blockKey) return 'stage'
  if (sticky && next.field == null && next.element == null) return 'ignore'
  return 'apply'
}
