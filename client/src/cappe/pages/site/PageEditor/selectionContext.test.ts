// Pure decision logic for sticky selection — see selectionContext.ts's header
// for why this is split out of useCanvasBridge (which has no test coverage).
// Run:  npm run test:run -- selectionContext
import { describe, expect, it } from 'vitest'
import { decideSelect, decideSelectionUpdate } from './selectionContext'
import type { CanvasSelection } from './useCanvasBridge'

const sel = (over: Partial<CanvasSelection> = {}): CanvasSelection => ({
  block: 'k1', field: null, element: null, kind: 'text', start: null, end: null, text: null, ...over,
})

describe('decideSelect', () => {
  it('non-sticky: always applies immediately, regardless of current context', () => {
    expect(decideSelect({ sticky: false, currentBlock: 0, incomingBlock: 1, incomingKey: 'k2' }))
      .toEqual({ action: 'apply' })
  })

  it('sticky + no current context: first pick applies immediately (no friction)', () => {
    expect(decideSelect({ sticky: true, currentBlock: null, incomingBlock: 1, incomingKey: 'k2' }))
      .toEqual({ action: 'apply' })
  })

  it('sticky + same block re-clicked: applies (a refinement, not a switch)', () => {
    expect(decideSelect({ sticky: true, currentBlock: 1, incomingBlock: 1, incomingKey: 'k2' }))
      .toEqual({ action: 'apply' })
  })

  it('sticky + a different block: stages a pending switch keyed on its _k', () => {
    expect(decideSelect({ sticky: true, currentBlock: 0, incomingBlock: 1, incomingKey: 'k2' }))
      .toEqual({ action: 'stage', pending: { blockKey: 'k2', selection: null } })
  })

  it('sticky + different block but unresolvable _k (iframe DOM lagging): applies, matching today', () => {
    expect(decideSelect({ sticky: true, currentBlock: 0, incomingBlock: 1, incomingKey: undefined }))
      .toEqual({ action: 'apply' })
  })
})

describe('decideSelectionUpdate', () => {
  it('detail for the block already staged as pending: stages', () => {
    const pending = { blockKey: 'k2', selection: null }
    const next = sel({ block: 'k2', field: 'heading' })
    expect(decideSelectionUpdate({ sticky: true, pending, next })).toBe('stage')
  })

  it('sticky + empty shape (dead-space click in the current section): ignores', () => {
    const next = sel({ field: null, element: null })
    expect(decideSelectionUpdate({ sticky: true, pending: null, next })).toBe('ignore')
  })

  it('sticky + a real field selection on the current block: applies', () => {
    const next = sel({ field: 'heading' })
    expect(decideSelectionUpdate({ sticky: true, pending: null, next })).toBe('apply')
  })

  it('sticky + a real element selection: applies', () => {
    const next = sel({ element: 'el-1', field: null })
    expect(decideSelectionUpdate({ sticky: true, pending: null, next })).toBe('apply')
  })

  it('non-sticky + empty shape: applies (Form/Canvas modes keep today\'s behavior)', () => {
    const next = sel({ field: null, element: null })
    expect(decideSelectionUpdate({ sticky: false, pending: null, next })).toBe('apply')
  })

  it('pending exists but the detail is for a DIFFERENT block than staged: falls through to ignore/apply', () => {
    const pending = { blockKey: 'k2', selection: null }
    // detail arrives for the CURRENT block (k1), not the staged one (k2) —
    // an empty shape here is still a dead-space click, still ignored.
    const next = sel({ block: 'k1', field: null, element: null })
    expect(decideSelectionUpdate({ sticky: true, pending, next })).toBe('ignore')
  })
})
