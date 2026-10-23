import { act, createEvent, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import StoryEditor from './editor/StoryEditor'
import { duplicateBlock, insertBlock, newBlock } from './editor/blocks'
import { HISTORY_LIMIT, MERGE_MS, historyReducer, type History } from './editor/history'
import { withText } from './editor/blocks'
import type { RtDoc } from './canvas/rt'
import type { FrameMessage } from './canvas/bridge'
import type { CappePost, CappeStoryOptions, StoryBlock } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const para = (text: string, marks: string[] = []): RtDoc => ({ type: 'doc', content: [{ type: 'paragraph', content: [
  marks.length ? { type: 'text', text, marks: marks.map((type) => ({ type })) } as never : { type: 'text', text }] }] })
const text = (md: string): StoryBlock => ({ ...(newBlock('text') as Extract<StoryBlock, { type: 'text' }>), md, rt: para(md) })

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

const PAGE = '<!doctype html><p>preview</p>'
const send = (source: Window, data: unknown) => act(() => { window.dispatchEvent(new MessageEvent('message', { data, source })) })

/** The story's pages, shown, as the frame would show them: what the page says. */
async function onPage() {
  const frame = await waitFor(() => {
    const f = document.querySelector(`iframe[srcdoc="${PAGE}"]`) as HTMLIFrameElement | null
    if (!f) throw new Error('not yet')
    return f
  })
  const win = frame.contentWindow!
  send(win, { type: 'mz-ready' })
  send(win, { type: 'mz-shown' })
  return (m: FrameMessage | Record<string, unknown>) => send(win, m)
}

/** The headline typed on the page. */
const typeHeadline = (say: Awaited<ReturnType<typeof onPage>>, value: string) =>
  say({ type: 'mz-edit', story: 'preview', block: -1, field: '@title', value, rich: false })
const headline = () => screen.getByRole('heading', { level: 1 })

/** The story's blocks, in order, as the layers panel lists them. */
const kinds = () => Array.from(screen.getByRole('tree', { name: 'The story’s layers' }).querySelectorAll(':scope > li > div'))
  .map((row) => row.textContent)
const rows = () => Array.from(screen.getByRole('tree', { name: 'The story’s layers' }).querySelectorAll<HTMLElement>(':scope > li > div'))

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

describe('withText', () => {
  it("takes tighten's passage with its document, or lets the server make one", () => {
    const bs = [newBlock('cover'), text('old')]
    expect(withText(bs, 1, 'new', para('new'))[1]).toMatchObject({ md: 'new', rt: para('new') })
    expect(withText(bs, 1, 'new')[1]).not.toHaveProperty('rt')
    expect(withText(bs, 0, 'x')).toEqual(bs)
  })
})

describe('StoryEditor — editing', () => {
  it('undoes and redoes typing from the buttons and the keyboard', async () => {
    mountEditor()
    const say = await onPage()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled()
    typeHeadline(say, 'Dawn')
    expect(headline()).toHaveTextContent('Dawn')
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(headline()).toHaveTextContent('The harbour at dawn')
    expect(screen.queryByText('Unsaved')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    expect(headline()).toHaveTextContent('Dawn')
    fireEvent.keyDown(window, { key: 'z', metaKey: true })
    expect(headline()).toHaveTextContent('The harbour at dawn')
    fireEvent.keyDown(window, { key: 'z', metaKey: true, shiftKey: true })
    expect(headline()).toHaveTextContent('Dawn')
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'y', ctrlKey: true })
    expect(headline()).toHaveTextContent('Dawn')
  })

  it('undoes words typed on the page from the page’s own keys, and saves what is shown', async () => {
    api.put.mockImplementation((_path: string, body: Partial<CappePost>) => Promise.resolve(post(body)))
    mountEditor()
    const say = await onPage()
    say({ type: 'mz-edit', story: 'preview', block: 1, field: 'md', value: para('First words. More.'), rich: true })
    expect(await screen.findByText('Unsaved')).toBeInTheDocument()
    say({ type: 'mz-key', key: 'undo' })
    await waitFor(() => expect(screen.queryByText('Unsaved')).not.toBeInTheDocument())
    say({ type: 'mz-key', key: 'redo' })
    expect(await screen.findByText('Unsaved')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const block = (api.put.mock.calls[0][1] as { content: { blocks: StoryBlock[] } }).content.blocks[1]
    expect(block).toMatchObject({ md: 'First words. More.', rt: para('First words. More.') })
  })

  it('leaves ⌘Z to Assist’s own fields', async () => {
    mountEditor()
    const say = await onPage()
    typeHeadline(say, 'Dawn')
    fireEvent.click(screen.getByRole('button', { name: /Assist/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'Draft' }))
    const notes = screen.getByLabelText('Your notes')
    const ev = createEvent.keyDown(notes, { key: 'z', metaKey: true })
    fireEvent(notes, ev)
    expect(ev.defaultPrevented).toBe(false)  // the browser undoes the notes
    expect(headline()).toHaveTextContent('Dawn')  // the story is untouched
    fireEvent.keyDown(document.body, { key: 'z', metaKey: true })
    expect(headline()).toHaveTextContent('The harbour at dawn')
  })

  it('saves with ⌘S only when there is something to save', async () => {
    api.put.mockResolvedValue(post({ title: 'Dawn' }))
    mountEditor()
    const say = await onPage()
    fireEvent.keyDown(window, { key: 's', metaKey: true })
    expect(api.put).not.toHaveBeenCalled()
    typeHeadline(say, 'Dawn')
    const ev = createEvent.keyDown(window, { key: 's', metaKey: true })
    fireEvent(window, ev)
    expect(ev.defaultPrevented).toBe(true)
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect((api.put.mock.calls[0][1] as { title: string }).title).toBe('Dawn')
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('adds a block after the one selected, duplicates one, and undoes each as a step', async () => {
    mountEditor()
    const say = await onPage()
    expect(kinds()).toEqual(['Cover', 'First words.'])
    // The cover selected: a divider from Elements goes right after it.
    say({ type: 'mz-select', target: { kind: 'block', story: 'preview', block: 0 } })
    fireEvent.click(screen.getByRole('button', { name: 'Elements' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add divider to the story' }))
    fireEvent.click(screen.getByRole('button', { name: 'Layers' }))
    expect(kinds()).toEqual(['Cover', 'Divider', 'First words.'])
    expect(await screen.findByRole('heading', { name: 'Divider' })).toBeInTheDocument()

    // The text block, picked in the layers panel, copied from its panel.
    fireEvent.click(rows()[2])
    fireEvent.click(await screen.findByRole('button', { name: 'Duplicate block' }))
    expect(kinds()).toEqual(['Cover', 'Divider', 'First words.', 'First words.'])

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover', 'Divider', 'First words.'])
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover', 'First words.'])
    // The cover is never copied.
    fireEvent.click(rows()[0])
    expect(await screen.findByRole('heading', { name: 'Cover' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Duplicate block' })).toBeNull()
  })

  it('moves a block by dragging it in the layers panel, never above the cover', async () => {
    mountEditor()
    await onPage()
    fireEvent.click(screen.getByRole('button', { name: 'Text' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add pull quote to the story' }))
    fireEvent.click(screen.getByRole('button', { name: 'Layers' }))
    expect(kinds()).toEqual(['Cover', 'First words.', 'Pull quote'])

    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' }
    const [cover, words, quote] = rows()
    expect(cover).toHaveAttribute('draggable', 'false')
    fireEvent.dragStart(quote, { dataTransfer })
    // The cover refuses the drop: its dragover isn't cancelled.
    const overCover = createEvent.dragOver(cover, { dataTransfer })
    fireEvent(cover, overCover)
    expect(overCover.defaultPrevented).toBe(false)
    fireEvent.dragOver(words, { dataTransfer })
    expect(words).toHaveClass('ring-1')
    fireEvent.drop(words, { dataTransfer })
    expect(kinds()).toEqual(['Cover', 'Pull quote', 'First words.'])
    // The block moved stays selected.
    expect(within(screen.getByRole('complementary', { name: 'Selected' })).getByRole('heading', { name: 'Pull quote' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(kinds()).toEqual(['Cover', 'First words.', 'Pull quote'])
  })

  it('asks before leaving with unsaved changes', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mountEditor()
    typeHeadline(await onPage(), 'Dawn')
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
