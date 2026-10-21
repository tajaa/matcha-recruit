import { createEvent, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StoryEditor from './editor/StoryEditor'
import MarkdownField from './editor/MarkdownField'
import { duplicateBlock, insertBlock, newBlock } from './editor/blocks'
import { HISTORY_LIMIT, MERGE_MS, historyReducer, type History } from './editor/history'
import { formatMarkdown, shortcutFormat } from './editor/markdown'
import { wireBook } from './reader/book'
import type { CappePost, CappeStoryOptions, StoryBlock } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const text = (md: string): StoryBlock => ({ ...(newBlock('text') as Extract<StoryBlock, { type: 'text' }>), md })

const post = (over: Partial<CappePost> = {}): CappePost => ({
  id: 'p-1', site_id: 's-1', title: 'The harbour at dawn', slug: 'harbour', excerpt: 'Forty boats.', body: 'The boats.',
  cover_image_url: null, status: 'draft', published_at: null, created_at: '2026-10-20T09:00:00Z',
  updated_at: '2026-10-20T09:00:00Z', format: 'blocks',
  content: { blocks: [newBlock('cover'), text('First words.')] },
  kicker: '', topic: 'city', layout: 'standard', access: 'free', cover_asset_id: null, byline: 'Ana Ruiz',
  word_count: 2, reading_minutes: 1, hidden: false, ...over,
})

const OPTIONS: CappeStoryOptions = {
  layouts: [{ key: 'standard', label: 'Standard', content: { blocks: [newBlock('cover'), newBlock('text')] } }],
  topics: [{ key: 'city', label: 'City life' }],
}

function mountEditor() {
  api.get.mockImplementation((path: string) => {
    if (path.includes('/posts/p-1')) return Promise.resolve(post())
    if (path.includes('/stories/options')) return Promise.resolve(OPTIONS)
    if (path.includes('/assets')) return Promise.resolve({ assets: [] })
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
  return render(
    <MemoryRouter initialEntries={['/cappe/sites/s-1/stories/p-1']}>
      <Routes>
        <Route path="/cappe/sites/:siteId/stories/:postId" element={<StoryEditor />} />
        <Route path="/cappe/sites/:siteId/stories" element={<p>stories list</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

const kinds = () => screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'))

beforeEach(() => {
  api.postHtml.mockResolvedValue('<!doctype html><p>preview</p>')
})
afterEach(() => vi.restoreAllMocks())

describe('historyReducer', () => {
  const start: History<string> = { past: [], present: 'a', future: [], at: 0 }
  const set = (h: History<string>, v: string, now: number, step = false) => historyReducer(h, { kind: 'set', next: () => v, step, now })

  it('folds quick edits into one step, keeps slow ones and steps apart', () => {
    let h = set(start, 'ab', 10_000)
    h = set(h, 'abc', 10_000 + MERGE_MS - 1)
    expect(h.past).toEqual(['a'])
    h = set(h, 'abcd', 10_000 + 3 * MERGE_MS)
    expect(h.past).toEqual(['a', 'abc'])
    h = set(h, 'abcde', 10_000 + 3 * MERGE_MS + 1, true)
    h = set(h, 'abcdef', 10_000 + 3 * MERGE_MS + 2)
    expect(h.past).toEqual(['a', 'abc', 'abcd', 'abcde'])
  })

  it('undoes, redoes, and a new edit drops what could be redone', () => {
    let h = set(start, 'b', 1, true)
    h = set(h, 'c', 2, true)
    h = historyReducer(h, { kind: 'undo' })
    expect(h.present).toBe('b')
    h = historyReducer(h, { kind: 'redo' })
    expect(h.present).toBe('c')
    h = historyReducer(historyReducer(h, { kind: 'undo' }), { kind: 'undo' })
    expect(h).toMatchObject({ present: 'a', past: [], future: ['b', 'c'] })
    expect(historyReducer(h, { kind: 'undo' })).toBe(h)
    h = set(h, 'z', 3)
    expect(h).toMatchObject({ present: 'z', past: ['a'], future: [] })
    expect(historyReducer(h, { kind: 'redo' })).toBe(h)
  })

  it('ignores an edit that changes nothing; reset and replace add no step', () => {
    expect(historyReducer(start, { kind: 'set', next: (v) => v, step: true, now: 1 })).toBe(start)
    const h = set(start, 'b', 1, true)
    expect(historyReducer(h, { kind: 'replace', value: 'B' })).toMatchObject({ present: 'B', past: ['a'] })
    expect(historyReducer(h, { kind: 'reset', value: 'x' })).toEqual({ past: [], present: 'x', future: [], at: 0 })
  })

  it('keeps at most HISTORY_LIMIT steps', () => {
    let h = start
    for (let i = 0; i < HISTORY_LIMIT + 5; i++) h = set(h, `v${i}`, i, true)
    expect(h.past).toHaveLength(HISTORY_LIMIT)
  })
})

describe('formatMarkdown', () => {
  it('wraps the selection in bold or italic, and unwraps it again', () => {
    expect(formatMarkdown('a cat sat', 2, 5, 'bold')).toEqual({ value: 'a **cat** sat', start: 4, end: 7 })
    expect(formatMarkdown('a **cat** sat', 4, 7, 'bold')).toEqual({ value: 'a cat sat', start: 2, end: 5 })
    expect(formatMarkdown('a cat', 2, 5, 'italic').value).toBe('a *cat*')
    // Italic inside bold adds marks rather than eating the bold's.
    expect(formatMarkdown('**cat**', 2, 5, 'italic').value).toBe('***cat***')
  })

  it('puts in words to type over when nothing is selected', () => {
    expect(formatMarkdown('Hi ', 3, 3, 'bold')).toEqual({ value: 'Hi **bold words**', start: 5, end: 15 })
  })

  it('makes a link with the address selected', () => {
    const e = formatMarkdown('see this', 4, 8, 'link')
    expect(e.value).toBe('see [this](https://)')
    expect(e.value.slice(e.start, e.end)).toBe('https://')
  })

  it('marks every line the selection touches, and toggles it off', () => {
    const v = 'intro\none\ntwo\nend'
    const on = formatMarkdown(v, 7, 11, 'bullets')
    expect(on.value).toBe('intro\n- one\n- two\nend')
    expect(formatMarkdown(on.value, on.start, on.end, 'bullets').value).toBe(v)
    expect(formatMarkdown(v, 7, 11, 'numbers').value).toBe('intro\n1. one\n2. two\nend')
    expect(formatMarkdown('> old', 0, 0, 'h2').value).toBe('## old')
    expect(formatMarkdown('Title', 0, 0, 'h3').value).toBe('### Title')
    expect(formatMarkdown('said', 1, 1, 'quote').value).toBe('> said')
  })

  it('knows the shortcuts', () => {
    const k = (key: string, over = {}) => shortcutFormat({ key, metaKey: true, ctrlKey: false, shiftKey: false, altKey: false, ...over })
    expect([k('b'), k('I'), k('k'), k('x'), k('b', { shiftKey: true }), k('b', { metaKey: false })]).toEqual(['bold', 'italic', 'link', null, null, null])
  })
})

describe('insertBlock and duplicateBlock', () => {
  const cover = newBlock('cover')
  it('inserts anywhere after the cover; a cover only goes first, once', () => {
    const bs = [cover, text('a')]
    expect(insertBlock(bs, 0, newBlock('divider')).map((b) => b.type)).toEqual(['cover', 'divider', 'text'])
    expect(insertBlock(bs, 9, newBlock('quote')).map((b) => b.type)).toEqual(['cover', 'text', 'quote'])
    expect(insertBlock(bs, 1, newBlock('cover'))).toBe(bs)
    expect(insertBlock([text('a')], 1, newBlock('cover')).map((b) => b.type)).toEqual(['cover', 'text'])
    const paid = [text('a'), newBlock('paywall')]
    expect(insertBlock(paid, 0, newBlock('paywall'))).toBe(paid)
  })

  it('copies a block (not the cover or paywall) right after itself, deeply', () => {
    const bs = [cover, text('a'), text('b')]
    const out = duplicateBlock(bs, 1)
    expect(out.map((b) => (b.type === 'text' ? b.md : b.type))).toEqual(['cover', 'a', 'a', 'b'])
    expect(out[2]).not.toBe(out[1])
    expect(duplicateBlock(bs, 0)).toBe(bs)
    expect(duplicateBlock(bs, 7)).toBe(bs)
  })
})

describe('MarkdownField', () => {
  it('formats the selected words from the bar and from ⌘B', () => {
    const onChange = vi.fn()
    render(<MarkdownField value="a cat sat" onChange={onChange} label="Text" />)
    const area = screen.getByLabelText('Text') as HTMLTextAreaElement
    area.setSelectionRange(2, 5)
    fireEvent.click(screen.getByRole('button', { name: 'Bold (⌘B)' }))
    expect(onChange).toHaveBeenLastCalledWith('a **cat** sat')
    area.setSelectionRange(2, 5)
    fireEvent.keyDown(area, { key: 'i', metaKey: true })
    expect(onChange).toHaveBeenLastCalledWith('a *cat* sat')
    fireEvent.click(screen.getByRole('button', { name: 'Numbered list' }))
    expect(onChange).toHaveBeenLastCalledWith('1. a cat sat')
  })
})

describe('StoryEditor — editing', () => {
  it('undoes and redoes typing from the buttons and the keyboard', async () => {
    mountEditor()
    const headline = await screen.findByLabelText('Headline')
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled()
    fireEvent.change(headline, { target: { value: 'Dawn' } })
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(headline).toHaveValue('The harbour at dawn')
    expect(screen.queryByText('Unsaved')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    expect(headline).toHaveValue('Dawn')
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    expect(headline).toHaveValue('The harbour at dawn')
    fireEvent.keyDown(window, { key: 'z', metaKey: true, shiftKey: true })
    expect(headline).toHaveValue('Dawn')
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'y', ctrlKey: true })
    expect(headline).toHaveValue('Dawn')
  })

  it('saves with ⌘S only when there is something to save', async () => {
    api.put.mockResolvedValue(post({ title: 'Dawn' }))
    mountEditor()
    const headline = await screen.findByLabelText('Headline')
    fireEvent.keyDown(window, { key: 's', metaKey: true })
    expect(api.put).not.toHaveBeenCalled()
    fireEvent.change(headline, { target: { value: 'Dawn' } })
    const ev = createEvent.keyDown(window, { key: 's', metaKey: true })
    fireEvent(window, ev)
    expect(ev.defaultPrevented).toBe(true)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect((api.put.mock.calls[0][1] as { title: string }).title).toBe('Dawn')
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('inserts a block between two, duplicates one, and undoes each as a step', async () => {
    mountEditor()
    await screen.findByLabelText('Headline')
    // The "+" before the text block (the cover has none in front of it).
    fireEvent.click(screen.getByRole('button', { name: 'Insert a block here' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Divider' }))
    expect(kinds()).toEqual(['Cover block', 'Divider block', 'Text block'])
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()

    expect(screen.getAllByRole('button', { name: 'Duplicate block' })).toHaveLength(2)  // never the cover
    fireEvent.click(screen.getAllByRole('button', { name: 'Duplicate block' })[1])
    expect(kinds()).toEqual(['Cover block', 'Divider block', 'Text block', 'Text block'])
    expect(screen.getAllByDisplayValue('First words.')).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover block', 'Divider block', 'Text block'])
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover block', 'Text block'])
  })

  it('moves a block by dragging its grip onto another, never above the cover', async () => {
    mountEditor()
    await screen.findByLabelText('Headline')
    fireEvent.click(screen.getByRole('button', { name: /Add a block/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Pull quote' }))
    expect(kinds()).toEqual(['Cover block', 'Text block', 'Pull quote block'])

    const dataTransfer = { setData: vi.fn(), setDragImage: vi.fn(), effectAllowed: '', dropEffect: '' }
    const grips = screen.getAllByTitle('Drag to move')
    expect(grips).toHaveLength(2)  // the cover has none
    const cards = document.querySelectorAll('[data-block]')
    fireEvent.dragStart(grips[1], { dataTransfer })
    expect(dataTransfer.setDragImage).toHaveBeenCalledWith(cards[2], 24, 24)
    // The cover refuses the drop: its dragover isn't cancelled.
    const overCover = createEvent.dragOver(cards[0], { dataTransfer })
    fireEvent(cards[0], overCover)
    expect(overCover.defaultPrevented).toBe(false)
    fireEvent.dragOver(cards[1], { dataTransfer })
    expect(cards[1]).toHaveClass('ring-2')
    fireEvent.drop(cards[1], { dataTransfer })
    expect(kinds()).toEqual(['Cover block', 'Pull quote block', 'Text block'])
    expect(document.querySelector('.ring-2')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover block', 'Text block', 'Pull quote block'])
  })

  it('asks before leaving with unsaved changes', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mountEditor()
    fireEvent.change(await screen.findByLabelText('Headline'), { target: { value: 'Dawn' } })
    fireEvent.click(screen.getByRole('link', { name: /Stories/ }))
    expect(confirm).toHaveBeenCalled()
    expect(screen.queryByText('stories list')).not.toBeInTheDocument()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('link', { name: /Stories/ }))
    expect(await screen.findByText('stories list')).toBeInTheDocument()
  })
})

describe('wireBook (the preview frames)', () => {
  function bookDoc(spreadW: number, totalW: number) {
    // A frame's document, like the preview's: it has its own window.
    const frame = document.createElement('iframe')
    document.body.appendChild(frame)
    const doc = frame.contentDocument!
    doc.body.innerHTML = '<div class="mz-reader" data-mz-book><button data-mz-prev hidden></button>'
      + '<div class="mz-book"><div class="mz-pages"><article>Words</article></div></div>'
      + '<button data-mz-next hidden></button><p data-mz-folio></p></div>'
    const book = doc.querySelector('.mz-book') as HTMLElement
    Object.defineProperty(book, 'clientWidth', { value: spreadW })
    Object.defineProperty(book, 'scrollWidth', { value: totalW })
    let left = 0
    Object.defineProperty(book, 'scrollLeft', { get: () => left, set: (v: number) => { left = v } })
    Object.defineProperty(book, 'scrollTo', { value: undefined })
    return { doc, book, q: (sel: string) => doc.querySelector(sel) as HTMLElement }
  }

  it('turns spreads with the arrows and keys, counts pages, and opens where it was', () => {
    const { doc, book, q } = bookDoc(800, 2400)
    const turns: number[] = []
    const ctl = wireBook(doc, 1, (i) => turns.push(i))!
    expect(book.scrollLeft).toBe(800)
    expect(q('[data-mz-folio]').textContent).toBe('Page 2 of 3')
    expect([q('[data-mz-prev]').hidden, q('[data-mz-next]').hidden]).toEqual([false, false])
    q('[data-mz-next]').click()
    expect(book.scrollLeft).toBe(1600)
    expect(q('[data-mz-next]').hidden).toBe(true)
    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', cancelable: true }))
    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageUp', cancelable: true }))
    expect(book.scrollLeft).toBe(0)
    expect(q('[data-mz-prev]').hidden).toBe(true)
    doc.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', metaKey: true }))
    expect(book.scrollLeft).toBe(0)
    expect(turns).toEqual([1, 2, 1, 0])
    ctl.dispose()
    q('[data-mz-next]').click()
    expect(book.scrollLeft).toBe(0)
  })

  it('does nothing on a page that is not a book', () => {
    expect(wireBook(document.implementation.createHTMLDocument('front'))).toBeNull()
    expect(wireBook(null)).toBeNull()
    const { doc, q } = bookDoc(800, 800)
    wireBook(doc, 4)
    expect(q('[data-mz-folio]').textContent).toBe('')
    expect([q('[data-mz-prev]').hidden, q('[data-mz-next]').hidden]).toEqual([true, true])
  })
})
