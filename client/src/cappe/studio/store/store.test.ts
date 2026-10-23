import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Measure } from '../compose/compose'
import { addItem, deletePage, moveItems } from '../model/ops'
import type { Doc } from '../model/types'
import { CappeApiError } from '../../api'
import { studioApi } from '../api'
import { Saver } from './saver'
import { DEFAULT_VIEW, Store, type State } from './store'

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }

const doc = (): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: true, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }, { id: 'p2' }], guides: [], items: [], threads: [], paywall_page: null,
})

const store = () => new Store({
  doc: doc(), selection: [], editing: null, page: 1, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [],
  overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
  save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
} as State, mono)

afterEach(() => vi.useRealTimers())

describe('the store', () => {
  it('keeps each edit as an undo step, and redo puts it back', () => {
    const s = store()
    const changes: Doc[] = []
    s.onDocChange = (d) => changes.push(d)
    s.edit((d) => addItem(d, 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc)
    s.set({ selection: ['r1'] })
    s.edit((d) => moveItems(d, ['r1'], 5, 0))
    expect(s.get().save.state).toBe('dirty')
    s.undo()
    expect(s.get().doc.items[0].x).toBe(0)
    s.undo()
    expect(s.get().doc.items).toEqual([])
    expect(s.get().selection).toEqual([]) // what's gone can't stay selected
    s.redo()
    s.redo()
    expect(s.get().doc.items[0].x).toBe(5)
    expect(s.canRedo()).toBe(false)
    expect(changes).toHaveLength(6)
  })

  it('makes edits with the same key one step, until sealed or a moment passes', () => {
    vi.useFakeTimers()
    const s = store()
    s.edit((d) => addItem(d, 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc)
    s.edit((d) => moveItems(d, ['r1'], 1, 0), { key: 'nudge' })
    s.edit((d) => moveItems(d, ['r1'], 1, 0), { key: 'nudge' })
    s.seal()
    s.edit((d) => moveItems(d, ['r1'], 1, 0), { key: 'nudge' })
    vi.advanceTimersByTime(2000)
    s.edit((d) => moveItems(d, ['r1'], 1, 0), { key: 'nudge' })
    const xs = [s.get().doc.items[0].x]
    for (let k = 0; k < 3; k++) { s.undo(); xs.push(s.get().doc.items[0].x) }
    expect(xs).toEqual([4, 3, 2, 0])
  })

  it('an edit that changes nothing is no step, and a new edit clears redo', () => {
    const s = store()
    const before = s.get().doc
    s.edit((d) => d, { extra: { tool: 'text' } })
    expect(s.get().doc).toBe(before)
    expect(s.get().tool).toBe('text')
    expect(s.canUndo()).toBe(false)
    s.edit((d) => addItem(d, 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc)
    s.undo()
    s.edit((d) => addItem(d, 'ellipse', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc)
    expect(s.canRedo()).toBe(false)
  })

  it('composes text on every edit, and a replaced document has no history', () => {
    const s = store()
    s.edit((d) => {
      const r = addItem(d, 'text', 'p1', { x: 0, y: 0, w: 100, h: 100 })
      return { ...r.doc, threads: [{ id: 's1', frames: [r.id], paras: [{ runs: [{ t: 'one two', size: 10 }] }] }] }
    })
    expect(s.get().doc.threads[0].comp?.lines).toHaveLength(1)
    const listener = vi.fn()
    const off = s.subscribe(listener)
    s.replace({ ...doc(), pages: [{ id: 'p1' }] })
    expect(s.canUndo()).toBe(false)
    expect(s.get().page).toBe(0) // a page that's gone isn't in view
    expect(listener).toHaveBeenCalledTimes(1)
    off()
  })
})

describe('a page deleted', () => {
  it('leaves the page in view and the selection within the document', () => {
    const s = store()  // two pages, the second in view
    s.edit((d) => addItem(d, 'rect', 'p2', { x: 0, y: 0, w: 10, h: 10 }).doc)
    s.set({ selection: ['r1'] })
    s.edit((d) => deletePage(d, 1))
    expect(s.get().doc.pages).toHaveLength(1)
    expect(s.get()).toMatchObject({ page: 0, selection: [] })
  })
})

describe('a face that finishes loading', () => {
  it('saves the lines it sets again, with no undo step', () => {
    const s = store()
    s.edit((d) => {
      const r = addItem(d, 'text', 'p1', { x: 0, y: 0, w: 100, h: 100 })
      return { ...r.doc, threads: [{ id: 's1', frames: [r.id], paras: [{ runs: [{ t: 'one two three four', size: 10 }] }] }] }
    })
    s.set((x) => ({ save: { ...x.save, state: 'saved' } }))
    const before = s.get().doc.threads[0].comp!.lines.length
    const changes: Doc[] = []
    s.onDocChange = (d) => changes.push(d)
    const undoable = s.canUndo()
    s.measure = { ...mono, width: (c, t) => [...t].length * 1.5 * c.size }  // the real face is wider
    s.recompose()
    expect(s.get().doc.threads[0].comp!.lines.length).toBeGreaterThan(before)
    expect(s.get().save.state).toBe('dirty')
    expect(changes).toHaveLength(1)
    expect(s.canUndo()).toBe(undoable)
    s.recompose()  // nothing changed: nothing to save
    expect(changes).toHaveLength(1)
  })
})

describe('saving', () => {
  const saved = { rev: 2, draft: false } as Awaited<ReturnType<typeof studioApi.save>>
  const dirty = () => {
    const s = store()
    const saver = new Saver(s, 's-1', 'p-1')
    s.edit((d) => addItem(d, 'rect', 'p1', { x: 0, y: 0, w: 10, h: 10 }).doc)
    return { s, saver }
  }

  it('fails quietly for an autosave and out loud when asked strictly', async () => {
    vi.spyOn(studioApi, 'save').mockRejectedValue(new Error('Network down'))
    const { s, saver } = dirty()
    await expect(saver.save()).resolves.toBeUndefined()
    expect(s.get().save.state).toBe('error')
    await expect(saver.save({ strict: true })).rejects.toThrow('Network down')
    expect(saver.unsaved()).toBe(true)
    saver.dispose()
  })

  it('counts a story saved elsewhere as unsaved here, and refuses a strict save of it', async () => {
    vi.spyOn(studioApi, 'save').mockRejectedValue(new CappeApiError('Saved elsewhere', 'stale_rev', 409))
    const { s, saver } = dirty()
    await saver.save()
    expect(s.get().save.state).toBe('conflict')
    expect(saver.unsaved()).toBe(true)
    await expect(saver.save({ strict: true })).rejects.toThrow('saved somewhere else')
    saver.dispose()
  })

  it('resolves a strict save once the story is saved', async () => {
    vi.spyOn(studioApi, 'save').mockResolvedValue(saved)
    const { s, saver } = dirty()
    await expect(saver.save({ strict: true })).resolves.toBeUndefined()
    expect(s.get().save).toMatchObject({ state: 'saved', rev: 2 })
    expect(saver.unsaved()).toBe(false)
    saver.dispose()
  })
})
