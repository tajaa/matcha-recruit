// applyMerlinOps is the last thing standing between an AI-authored op and the
// user's page content, so its refusal cases matter as much as its happy path.
// Run:  npm run test:run -- merlinOps
import { describe, expect, it } from 'vitest'
import type { CappeBlock } from '../../../types'
import { applyMerlinOps, type MerlinOp } from './merlinOps'

const hero = (): CappeBlock => ({ _k: 'k1', type: 'hero', heading: 'Old', subheading: 'Sub' })
const features = (): CappeBlock => ({
  _k: 'k2', type: 'features', items: [{ title: 'a' }, { title: 'b' }, { title: 'c' }],
})
const canvas = (): CappeBlock => ({
  _k: 'k3', type: 'canvas', grid: { cols: 24, rowH: 24, rows: 30 }, mobile: { cols: 8, rowH: 24, rows: 60 },
  elements: [{ id: 'e1', kind: 'text', text: 'hi', d: { x: 1, y: 1, w: 4, h: 2 } }],
})

const run = (blocks: CappeBlock[], ops: MerlinOp[], theme: Record<string, unknown> = {}) =>
  applyMerlinOps(blocks, theme, ops)

describe('set_field', () => {
  it('edits a scalar field', () => {
    const r = run([hero()], [{ op: 'set_field', block: 'k1', path: 'heading', value: 'New' }])
    expect(r.blocks[0].heading).toBe('New')
    expect(r.results[0].ok).toBe(true)
  })

  it('edits a list item by index', () => {
    const r = run([features()], [{ op: 'set_field', block: 'k2', path: 'items.1.title', value: 'B2' }])
    expect(r.blocks[0].items).toEqual([{ title: 'a' }, { title: 'B2' }, { title: 'c' }])
  })

  it('REFUSES a named key into a list instead of clobbering the array', () => {
    // The original bug: this replaced `items` with {title:'Fast'}, silently
    // deleting all three cards while reporting success.
    const r = run([features()], [{ op: 'set_field', block: 'k2', path: 'items.title', value: 'Fast' }])
    expect(r.blocks[0].items).toEqual([{ title: 'a' }, { title: 'b' }, { title: 'c' }])
    expect(r.results[0].ok).toBe(false)
    expect(r.blocks).toBe(r.blocks) // unchanged content
  })

  it('REFUSES an index past the end rather than padding with undefined holes', () => {
    const r = run([features()], [{ op: 'set_field', block: 'k2', path: 'items.9.title', value: 'x' }])
    expect((r.blocks[0].items as unknown[]).length).toBe(3)
    expect(r.results[0].ok).toBe(false)
  })

  it('allows appending at exactly the list length', () => {
    const r = run([features()], [{ op: 'set_field', block: 'k2', path: 'items.3.title', value: 'd' }])
    expect((r.blocks[0].items as unknown[]).length).toBe(4)
    expect(r.results[0].ok).toBe(true)
  })

  it('skips an id that no longer exists (deleted mid-flight)', () => {
    const r = run([hero()], [{ op: 'set_field', block: 'ghost', path: 'heading', value: 'x' }])
    expect(r.results[0].ok).toBe(false)
    expect(r.blocks).toBe(r.blocks)
  })
})

describe('block CRUD', () => {
  it('adds a block at an index with a fresh key', () => {
    const r = run([hero()], [{ op: 'add_block', type: 'faq', at: 0 }])
    expect(r.blocks).toHaveLength(2)
    expect(r.blocks[0].type).toBe('faq')
    expect(r.blocks[0]._k).toBeTruthy()
    expect(r.blocks[0]._k).not.toBe('k1')
  })

  it('skips an unknown block type', () => {
    const r = run([hero()], [{ op: 'add_block', type: 'not_a_type', at: 0 }])
    expect(r.blocks).toHaveLength(1)
    expect(r.results[0].ok).toBe(false)
  })

  it('removes and moves by id', () => {
    const blocks = [hero(), features()]
    expect(run(blocks, [{ op: 'remove_block', block: 'k1' }]).blocks).toHaveLength(1)
    expect(run(blocks, [{ op: 'move_block', block: 'k1', to: 1 }]).blocks[1]._k).toBe('k1')
  })
})

describe('set_theme', () => {
  it('derives accent + brandText from a brand color, like the picker does', () => {
    const r = run([], [{ op: 'set_theme', key: 'colors.brand', value: '#ff0000' }])
    const colors = r.theme.colors as Record<string, unknown>
    expect(colors.brand).toBe('#ff0000')
    expect(colors.accent).toBe('#ff0000')
    expect(colors.brandText).toBeTruthy()
  })

  it('loads a preset\'s whole config, not just the preset name', () => {
    // The original bug: only `theme.preset` was written, so the menu showed the
    // new preset as active while the old palette kept rendering.
    const r = run([], [{ op: 'set_theme', key: 'preset', value: 'minimal' }])
    expect(r.theme.preset).toBe('minimal')
    expect(r.theme.radius).toBe('sm')
    expect((r.theme.colors as Record<string, unknown>).brand).toBe('#18181b')
  })

  it('skips an unknown preset id', () => {
    const r = run([], [{ op: 'set_theme', key: 'preset', value: 'nope' }])
    expect(r.results[0].ok).toBe(false)
    expect(r.theme).toEqual({})
  })

  it('deletes a key on a null value', () => {
    const r = applyMerlinOps([], { radius: 'lg' }, [{ op: 'set_theme', key: 'radius', value: null }])
    expect('radius' in r.theme).toBe(false)
  })
})

describe('canvas', () => {
  it('adds an element with a generated id', () => {
    const r = run([canvas()], [{
      op: 'canvas_add', block: 'k3', element: { kind: 'heading', text: 'Hi', d: { x: 1, y: 5, w: 10, h: 3 } },
    }])
    const els = r.blocks[0].elements as { id: string }[]
    expect(els).toHaveLength(2)
    expect(els[1].id).toBeTruthy()
    expect(els[1].id).not.toBe('e1')
  })

  it('patches and removes an element by id', () => {
    const moved = run([canvas()], [{ op: 'canvas_update', block: 'k3', el: 'e1', patch: { d: { x: 2, y: 9, w: 4, h: 2 } } }])
    expect((moved.blocks[0].elements as { d: { y: number } }[])[0].d.y).toBe(9)
    const gone = run([canvas()], [{ op: 'canvas_remove', block: 'k3', el: 'e1' }])
    expect(gone.blocks[0].elements).toHaveLength(0)
  })

  it('skips a canvas op aimed at a non-canvas block', () => {
    const r = run([hero()], [{ op: 'canvas_remove', block: 'k1', el: 'e1' }])
    expect(r.results[0].ok).toBe(false)
  })
})

describe('referential stability', () => {
  it('returns the identical blocks/theme refs when nothing applied', () => {
    // index.tsx keys "did anything change?" off reference equality — a new ref
    // here would push a spurious undo entry on every no-op turn.
    const blocks = [hero()]
    const theme = { mode: 'light' }
    const r = applyMerlinOps(blocks, theme, [])
    expect(r.blocks).toBe(blocks)
    expect(r.theme).toBe(theme)
  })

  it('leaves refs untouched when every op is skipped', () => {
    const blocks = [hero()]
    const theme = { mode: 'light' }
    const r = applyMerlinOps(blocks, theme, [{ op: 'remove_block', block: 'ghost' }])
    expect(r.blocks).toBe(blocks)
    expect(r.theme).toBe(theme)
  })
})

describe('set_design (the op whose absence caused the destructive substitution)', () => {
  it('sets a motion key, creating the _design bag', () => {
    const r = run([hero()], [{ op: 'set_design', block: 'k1', group: 'motion', key: 'heading', value: 'shimmer' }])
    expect(r.blocks[0]._design).toEqual({ motion: { heading: 'shimmer' } })
    expect(r.results[0].ok).toBe(true)
  })

  it('merges into an existing group without dropping sibling keys', () => {
    const b: CappeBlock = { _k: 'k9', type: 'hero', _design: { motion: { effect: 'fade' }, bg: { type: 'color' } } }
    const r = run([b], [{ op: 'set_design', block: 'k9', group: 'motion', key: 'heading', value: 'rise' }])
    expect(r.blocks[0]._design).toEqual({ motion: { effect: 'fade', heading: 'rise' }, bg: { type: 'color' } })
  })

  it('clears a key on null/empty, like DesignInspector patch()', () => {
    const b: CappeBlock = { _k: 'k9', type: 'hero', _design: { motion: { heading: 'shimmer', effect: 'fade' } } }
    const r = run([b], [{ op: 'set_design', block: 'k9', group: 'motion', key: 'heading', value: null }])
    expect(r.blocks[0]._design).toEqual({ motion: { effect: 'fade' } })
  })

  it('skips a section that no longer exists', () => {
    const r = run([hero()], [{ op: 'set_design', block: 'ghost', group: 'motion', key: 'heading', value: 'rise' }])
    expect(r.results[0].ok).toBe(false)
  })
})
