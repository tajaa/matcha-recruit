import { afterEach, describe, expect, it, vi } from 'vitest'
import { BODY_WRITING_NOTICE } from '../../magazine/writing'
import type { Measure } from '../compose/compose'
import { newItem, paraText } from '../model/doc'
import type { Doc, Para } from '../model/types'
import { DEFAULT_VIEW, Store } from '../store/store'
import { TextEditor } from './editor'

const mono: Measure = { width: (c, t) => [...t].length * c.size / 2, metrics: (c) => ({ asc: c.size * 0.8, desc: c.size * 0.2 }) }
const editors: TextEditor[] = []
const clipboard = () => new Event('paste', { cancelable: true }) as ClipboardEvent

function open(paras: Para[], at: [number, number] = [0, 0], head = at) {
  const doc: Doc = {
    v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
    baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
    pages: [{ id: 'p1' }], guides: [], items: [newItem('text', 'p1', 't1', { x: 50, y: 50, w: 400, h: 300 })],
    threads: [{ id: 's1', frames: ['t1'], paras }], paywall_page: null,
  }
  const store = new Store({
    doc, selection: ['t1'], editing: null, page: 0, tool: 'text', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
  }, mono)
  const editor = new TextEditor(store, () => null)
  editors.push(editor)
  editor.open('s1', at, head)
  const view = editor.view!
  view.setProps({ handleScrollToSelection: () => true })
  const words = () => store.get().doc.threads[0].paras.map(paraText)
  return { store, editor, view, words }
}

afterEach(() => { editors.splice(0).forEach((e) => e.destroy()); vi.restoreAllMocks() })

describe('article bodies are written directly', () => {
  it.each([undefined, 'p'] as const)('blocks plain and rich paste into body role %s without dirtying or replacing selected words', (role) => {
    const { store, view, words } = open([{ role, runs: [{ t: 'My own words' }] }], [0, 0], [0, 12])
    const before = view.state.selection.toJSON()
    view.pasteText('Imported prose', clipboard())
    view.pasteHTML('<p><strong>Imported</strong> prose</p>', clipboard())
    expect(words()).toEqual(['My own words'])
    expect(view.state.selection.toJSON()).toEqual(before)
    expect(store.get().notice).toBe(BODY_WRITING_NOTICE)
    expect(store.get().save.state).toBe('saved')
    expect(store.canUndo()).toBe(false)
  })

  it('blocks context-menu paste and mobile beforeinput, including empty bodies', () => {
    const { store, view, words } = open([{ runs: [{ t: '' }] }])
    const paste = new Event('paste', { bubbles: true, cancelable: true })
    view.dom.dispatchEvent(paste)
    expect(paste.defaultPrevented).toBe(true)
    for (const inputType of ['insertFromPaste', 'insertFromPasteAsQuotation', 'insertFromDrop']) {
      const event = new InputEvent('beforeinput', { inputType, bubbles: true, cancelable: true })
      view.dom.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
    }
    expect(words()).toEqual([''])
    expect(store.get().save.state).toBe('saved')
  })

  it('allows normal typing, Unicode, composition input, spelling corrections and undo', () => {
    const { store, view, words } = open([{ runs: [{ t: '' }] }])
    for (const inputType of ['insertText', 'insertCompositionText', 'insertReplacementText']) {
      const event = new InputEvent('beforeinput', { inputType, bubbles: true, cancelable: true })
      view.dom.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(false)
    }
    view.dispatch(view.state.tr.insertText('Café 日本語 🌱'))
    expect(words()).toEqual(['Café 日本語 🌱'])
    store.undo()
    expect(words()).toEqual([''])
    store.redo()
    expect(words()).toEqual(['Café 日本語 🌱'])
  })

  it.each(['h1', 'h2', 'h3', 'quote', 'caption'] as const)('allows pasting %s text even when a body paragraph exists elsewhere', (role) => {
    const { view, words } = open([{ role, runs: [{ t: 'Title' }] }, { runs: [{ t: 'Body' }] }], [0, 0], [0, 5])
    view.pasteText('Pasted text', clipboard())
    expect(words()).toEqual(['Pasted text', 'Body'])
  })

  it('blocks paste across a selection that starts in a headline and includes body text', () => {
    const { view, words } = open([{ role: 'h1', runs: [{ t: 'Title' }] }, { runs: [{ t: 'Body' }] }], [0, 0], [1, 4])
    view.pasteText('Replacement', clipboard())
    expect(words()).toEqual(['Title', 'Body'])
  })

  it('blocks body paragraphs brought in by a rich paste at a headline', () => {
    const { view, words } = open([{ role: 'h1', runs: [{ t: 'Title' }] }])
    view.pasteHTML('<p>First</p><p>Imported article body</p><p>Last</p>', clipboard())
    expect(words()).toEqual(['Title'])
  })

  it('checks the drop destination, rather than the current caret, before changing anything', () => {
    const { store, view, words } = open([{ role: 'h1', runs: [{ t: 'Title' }] }, { runs: [{ t: 'Body' }] }])
    vi.spyOn(view, 'posAtCoords').mockReturnValue({ pos: 8, inside: 7 })
    const event = new MouseEvent('drop', { clientX: 10, clientY: 10, cancelable: true })
    const slice = view.state.doc.slice(1, 3)
    expect(view.someProp('handleDrop', (f) => f(view, event as DragEvent, slice, false))).toBe(true)
    expect(event.defaultPrevented).toBe(true)
    expect(words()).toEqual(['Title', 'Body'])
    expect(store.get().save.state).toBe('saved')
  })

  it('blocks dragging body words out into a caption before the source can be deleted', () => {
    const { view, words } = open([{ runs: [{ t: 'Body' }] }, { role: 'caption', runs: [{ t: 'Caption' }] }], [0, 0], [0, 4])
    vi.spyOn(view, 'posAtCoords').mockReturnValue({ pos: 7, inside: 6 })
    const event = new MouseEvent('drop', { cancelable: true })
    expect(view.someProp('handleDrop', (f) => f(view, event as DragEvent, view.state.selection.content(), true))).toBe(true)
    expect(words()).toEqual(['Body', 'Caption'])
  })

  it('applies the same body rule when the editor is shown in the Story Editor panel', () => {
    const { editor, view, words } = open([{ runs: [{ t: 'Typed' }] }])
    const panel = document.createElement('div')
    document.body.appendChild(panel)
    editor.showIn(panel)
    view.pasteText('Pasted', clipboard())
    expect(words()).toEqual(['Typed'])
    editor.showIn(null)
    panel.remove()
  })
})
