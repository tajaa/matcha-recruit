import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CappeApiError } from '../../api'
import type { Measure } from '../compose/compose'
import { addItem } from '../model/ops'
import type { Doc, RectItem } from '../model/types'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { studioApi, type MerlinReply } from '../api'
import { commandsPayload, conversation, guidePayload, MATCH_QUESTION, MERLIN_SUGGESTIONS, roundNotes, SUGGESTIONS } from './ask/conversation'
import type { Applied } from './ask/merlinOps'
import { command } from './commands'
import { StudioContext, type StudioCtx } from './context'
import { GUIDE } from './guideContent'
import { AskPanel } from './panels/AskPanel'

// Getting a picture ready (read, made smaller) is held until a test lets it finish.
const prep = vi.hoisted(() => ({ pending: [] as { name: string; done: () => void }[] }))
vi.mock('./ask/conversation', async (importOriginal) => {
  const real = await importOriginal<typeof import('./ask/conversation')>()
  return {
    ...real,
    preparePicture: (f: File) => new Promise((resolve) => {
      prep.pending.push({ name: f.name, done: () => resolve({ media_type: 'image/jpeg', data: f.name, preview: `data:image/jpeg;base64,${f.name}` }) })
    }),
  }
})

// Drawing the person's own design needs a real browser: here it gives a stand-in.
const snap = vi.hoisted(() => ({ calls: 0, args: [] as unknown[], result: null as null | { media_type: 'image/jpeg'; data: string; preview: string } }))
vi.mock('./ask/snapshot', () => ({ snapshot: async (...args: unknown[]) => { snap.calls++; snap.args = args; return snap.result } }))

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const doc = (): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null,
})

function studio() {
  const d = addItem(doc(), 'rect', 'p1', { x: 0, y: 0, w: 100, h: 100 }).doc
  const store = new Store({
    doc: d, selection: [], editing: null, page: 0, tool: 'select', view: { ...DEFAULT_VIEW }, panels: ['ask'], drawer: null,
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
  } as State, mono)
  const fonts = { book: { manifest: { faces: [{ family: 'Bebas Neue' }] } }, ensureDoc: vi.fn(async () => {}) }
  const ctx = { store, siteId: 's1', postId: 'post1', fonts } as unknown as StudioCtx
  render(<StudioContext.Provider value={ctx}><AskPanel /></StudioContext.Provider>)
  return { store, ctx }
}

const box = () => screen.getByRole('textbox', { name: 'Your question' })

beforeEach(() => vi.restoreAllMocks())

describe('what goes with a question', () => {
  it('fits what the server takes (studio/ask.py and the route’s limits)', () => {
    const guide = guidePayload()
    expect(guide.map((s) => s.id)).toEqual(GUIDE.map((s) => s.id))
    let total = 0
    for (const s of guide) {
      expect(s.id).toMatch(/^[a-z0-9-]{1,40}$/)
      expect(s.title.length).toBeLessThanOrEqual(120)
      expect(s.body.length).toBeLessThanOrEqual(1000)
      expect(s.points.length).toBeLessThanOrEqual(16)
      for (const p of s.points) expect(p.length).toBeLessThanOrEqual(600)
      total += s.title.length + s.body.length + s.points.reduce((n, p) => n + p.length + 3, 0) + 20
    }
    expect(total).toBeLessThan(40_000)
    expect(guide.find((s) => s.id === 'keys')!.points).toContain('Space + drag: Move around the pages')

    const { store } = studio()
    const commands = commandsPayload(store.get())
    expect(commands.length).toBeLessThanOrEqual(150)
    for (const c of commands) {
      expect(c.id).toMatch(/^[a-z0-9-]{1,40}$/)
      expect(c.label.length).toBeLessThanOrEqual(80)
      expect(c.keys.length).toBeLessThanOrEqual(16)
    }
    expect(commands.map((c) => c.id)).not.toContain('ask')
    expect(commands.find((c) => c.id === 'duplicate')).toEqual({ id: 'duplicate', label: 'Duplicate', keys: '⌘D', enabled: false })
  })
})

describe('Ask the Studio', () => {
  it('asks a suggestion with the page, the guide and the commands, and shows the answer', async () => {
    const ask = vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Use **Layout → Add a spread**.', links: [] })
    studio()
    fireEvent.click(screen.getByRole('button', { name: SUGGESTIONS[0] }))
    expect(await screen.findByText('Layout → Add a spread')).toBeInTheDocument()
    const [site, post, body] = ask.mock.calls[0]
    expect([site, post]).toEqual(['s1', 'post1'])
    expect(body.question).toBe(SUGGESTIONS[0])
    expect(body.page).toContain('Document: 1 page')
    expect(body.guide.length).toBe(GUIDE.length)
    expect(body.commands.some((c) => c.id === 'story-editor')).toBe(true)
    expect(body.history).toEqual([])
    expect(body.picture).toBeNull()
  })

  it('sends on Enter, not Shift+Enter, and follows up with the earlier turns', async () => {
    const ask = vi.spyOn(studioApi, 'ask')
      .mockResolvedValueOnce({ answer: 'Two facing pages.', links: [] })
      .mockResolvedValueOnce({ answer: 'Layout menu.', links: [] })
    studio()
    fireEvent.change(box(), { target: { value: 'What is a spread?' } })
    fireEvent.keyDown(box(), { key: 'Enter', shiftKey: true })
    expect(ask).not.toHaveBeenCalled()
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Two facing pages.')
    expect(box()).toHaveValue('')
    fireEvent.change(box(), { target: { value: 'How do I add one?' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Layout menu.')
    expect(ask.mock.calls[1][2].history).toEqual([{ q: 'What is a spread?', a: 'Two facing pages.' }])
  })

  it('turns an answer’s links into the guide and commands, and keeps away the ones that take things away', async () => {
    vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Like this.', links: [
      { kind: 'guide', id: 'flow' }, { kind: 'guide', id: 'nope' },
      { kind: 'command', id: 'page-add' }, { kind: 'command', id: 'duplicate' }, { kind: 'command', id: 'page-delete' },
    ] })
    const { store } = studio()
    fireEvent.change(box(), { target: { value: 'How?' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Like this.')
    expect(screen.queryByRole('button', { name: /Delete this page/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Duplicate/ })).toBeDisabled() // nothing selected
    fireEvent.click(screen.getByRole('button', { name: 'Guide: Text that flows' }))
    expect(store.get().guide).toBe('flow')
    fireEvent.click(screen.getByRole('button', { name: /Add a page/ }))
    expect(store.get().doc.pages).toHaveLength(2)
    act(() => store.set({ selection: [store.get().doc.items[0].id] }))
    expect(screen.getByRole('button', { name: /Duplicate/ })).toBeEnabled()
  })

  it('says when the day’s questions are used up, and tries again in place', async () => {
    const ask = vi.spyOn(studioApi, 'ask')
      .mockRejectedValueOnce(new CappeApiError('Too many requests. Please try again later.', undefined, 429))
      .mockResolvedValueOnce({ answer: 'Now it works.', links: [] })
    studio()
    fireEvent.change(box(), { target: { value: 'Why?' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    expect(await screen.findByRole('alert')).toHaveTextContent('You’ve asked as much as you can for today.')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('Now it works.')
    expect(screen.getAllByText('Why?')).toHaveLength(1)
    expect(ask).toHaveBeenCalledTimes(2)
  })

  it('keeps the conversation when the panel closes, and Help → Ask brings it back with the keyboard', async () => {
    vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Kept.', links: [] })
    const { store, ctx } = studio()
    fireEvent.change(box(), { target: { value: 'Keep this' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Kept.')
    fireEvent.click(screen.getByRole('button', { name: 'Close Ask the Studio' }))
    expect(store.get().panels).not.toContain('ask')
    expect(conversation(store).get().turns).toHaveLength(1)
    act(() => command('ask').run(ctx))
    expect(store.get().panels).toContain('ask')
    await waitFor(() => expect(box()).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Start over' }))
    expect(screen.getByRole('button', { name: SUGGESTIONS[1] })).toBeInTheDocument()
  })

  it('shows a picture an answer names as its words, never loading it', async () => {
    vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Like this ![the look](https://evil.cloudfront.net/x.png?page=secret)', links: [] })
    studio()
    fireEvent.change(box(), { target: { value: 'What look?' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    expect(await screen.findByText('[the look]')).toBeInTheDocument()
    expect(document.querySelector('img[src*="evil"]')).toBeNull()
  })

  it('waits for a picture being got ready, and keeps the one chosen last', async () => {
    prep.pending = []
    const ask = vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Warm and grainy.', links: [] })
    studio()
    const input = screen.getByLabelText('Attach a picture', { selector: 'input' })
    const pick = (name: string) => fireEvent.change(input, { target: { files: [new File(['x'], name, { type: 'image/png' })] } })
    fireEvent.change(box(), { target: { value: 'Make it look like this' } })
    pick('first')
    pick('second')
    expect(await screen.findByText('Getting the picture ready…')).toBeInTheDocument()
    // Ask waits: Enter and the button do nothing until it's ready.
    fireEvent.keyDown(box(), { key: 'Enter' })
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(ask).not.toHaveBeenCalled()
    // The second finishes first; the first, late, doesn't replace it.
    await act(async () => { prep.pending[1].done() })
    await act(async () => { prep.pending[0].done() })
    expect(screen.getByAltText('The picture to send')).toHaveAttribute('src', 'data:image/jpeg;base64,second')
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Warm and grainy.')
    expect(ask.mock.calls[0][2].picture).toEqual({ media_type: 'image/jpeg', data: 'second' })
  })

  it('never cuts an earlier answer through the middle of a character', async () => {
    const long = `${'a'.repeat(3999)}😀 and more`
    const ask = vi.spyOn(studioApi, 'ask')
      .mockResolvedValueOnce({ answer: long, links: [] })
      .mockResolvedValueOnce({ answer: 'Fine.', links: [] })
    studio()
    fireEvent.change(box(), { target: { value: 'One' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1))
    await screen.findByText(/and more/)
    fireEvent.change(box(), { target: { value: 'Two' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Fine.')
    const sent = ask.mock.calls[1][2].history[0].a
    expect(sent).toBe('a'.repeat(3999))
    expect(sent).not.toMatch(/[\ud800-\udbff]$/)
  })

  it('refuses a picture it can’t send', async () => {
    studio()
    const input = screen.getByLabelText('Attach a picture', { selector: 'input' })
    fireEvent.change(input, { target: { files: [new File(['GIF89a'], 'a.gif', { type: 'image/gif' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Attach a JPEG, PNG or WebP picture.')
  })
})

describe('matching a look from a picture', () => {
  const dragged = (files: File[], types = ['Files']) => ({ dataTransfer: { types, files, dropEffect: 'none' } })
  const section = () => screen.getByRole('region', { name: 'Ask the Studio' })

  it('takes a screenshot dropped anywhere on the panel as the reference, and sends it', async () => {
    prep.pending = []
    const ask = vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Bigger type, more white.', links: [] })
    studio()
    fireEvent.dragOver(section(), dragged([]))
    expect(screen.getByText('Drop the picture of the look you want')).toBeInTheDocument()
    fireEvent.drop(section(), dragged([new File(['x'], 'shot', { type: 'image/png' })]))
    expect(screen.queryByText('Drop the picture of the look you want')).toBeNull()
    await act(async () => { prep.pending[0].done() })
    expect(screen.getByAltText('The picture to send')).toHaveAttribute('src', 'data:image/jpeg;base64,shot')
    fireEvent.change(box(), { target: { value: 'Make this look like this' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Bigger type, more white.')
    expect(ask.mock.calls[0][2].picture).toEqual({ media_type: 'image/jpeg', data: 'shot' })
  })

  it('says what to do with something that isn’t a picture file', () => {
    studio()
    fireEvent.drop(section(), dragged([new File(['x'], 'notes.txt', { type: 'text/plain' })]))
    expect(screen.getByRole('alert')).toHaveTextContent('Drop a JPEG, PNG or WebP picture.')
    // Dragged out of another web page: only its address comes.
    fireEvent.drop(section(), dragged([], ['text/uri-list']))
    expect(screen.getByRole('alert')).toHaveTextContent('Save that picture first')
    // Leaving the panel takes the drop sign away.
    fireEvent.dragOver(section(), dragged([]))
    fireEvent.dragLeave(section(), { relatedTarget: document.body })
    expect(screen.queryByText('Drop the picture of the look you want')).toBeNull()
  })

  it('“Ask about this” opens Ask on the selection with the question started, and isn’t offered to the model', () => {
    const { store, ctx } = studio()
    const id = store.get().doc.items[0].id
    expect(command('ask-about').enabled!(store.get())).toBe(false)
    act(() => store.set({ selection: [id], panels: [] }))
    act(() => command('ask-about').run(ctx))
    expect(store.get().panels).toContain('ask')
    expect(store.get().selection).toEqual([id])
    expect(box()).toHaveValue('How can I make this look like the picture I’ve attached?')
    expect(commandsPayload(store.get()).some((c) => c.id === 'ask-about')).toBe(false)
    // Taken once: the panel reopened doesn't put it back over what was done since.
    expect(conversation(store).get().draft).toBeNull()
    fireEvent.change(box(), { target: { value: '' } })
    cleanup()
    render(<StudioContext.Provider value={ctx}><AskPanel /></StudioContext.Provider>)
    expect(box()).toHaveValue('')
    // Asked again, the words come again.
    act(() => command('ask-about').run(ctx))
    expect(box()).toHaveValue('How can I make this look like the picture I’ve attached?')
  })
})

describe('comparing their design with the look they want', () => {
  it('sends a picture of their design beside the reference, and shows both', async () => {
    prep.pending = []
    snap.calls = 0
    snap.result = { media_type: 'image/jpeg', data: 'mine', preview: 'data:image/jpeg;base64,mine' }
    const ask = vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Tighter, heavier type.', links: [] })
    studio()
    fireEvent.change(screen.getByLabelText('Attach a picture', { selector: 'input' }), { target: { files: [new File(['x'], 'ref', { type: 'image/png' })] } })
    await act(async () => { prep.pending[0].done() })
    fireEvent.change(box(), { target: { value: 'Make this look like this' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Tighter, heavier type.')
    expect(ask.mock.calls[0][2]).toMatchObject({ picture: { data: 'ref' }, current: { media_type: 'image/jpeg', data: 'mine' } })
    expect(screen.getByAltText('Your design, as sent')).toHaveAttribute('src', 'data:image/jpeg;base64,mine')
    expect(screen.getByText('Yours now')).toBeInTheDocument()
  })

  it('draws nothing without a reference picture, and asks anyway when the drawing fails', async () => {
    prep.pending = []
    snap.calls = 0
    snap.result = null
    const ask = vi.spyOn(studioApi, 'ask').mockResolvedValue({ answer: 'Fine.', links: [] })
    studio()
    fireEvent.change(box(), { target: { value: 'How do I add a page?' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await screen.findByText('Fine.')
    expect(snap.calls).toBe(0)
    expect(ask.mock.calls[0][2].current).toBeNull()
    fireEvent.change(screen.getByLabelText('Attach a picture', { selector: 'input' }), { target: { files: [new File(['x'], 'ref2', { type: 'image/png' })] } })
    await act(async () => { prep.pending[0].done() })
    fireEvent.change(box(), { target: { value: 'Like this' } })
    fireEvent.keyDown(box(), { key: 'Enter' })
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(2))
    expect(snap.calls).toBe(1)
    expect(ask.mock.calls[1][2]).toMatchObject({ picture: { data: 'ref2' }, current: null })
    expect(screen.queryByText('Yours now')).toBeNull()
  })
})

describe('Merlin', () => {
  const rect = (store: Store) => store.get().doc.items[0] as RectItem
  const design = (words: string) => {
    fireEvent.click(screen.getByRole('radio', { name: /Merlin/ }))
    fireEvent.change(screen.getByRole('textbox', { name: 'What Merlin should design' }), { target: { value: words } })
    fireEvent.click(screen.getByRole('button', { name: 'Design it' }))
  }
  const later = () => {
    let resolve!: (r: MerlinReply) => void
    return { promise: new Promise<MerlinReply>((r) => { resolve = r }), resolve: (r: MerlinReply) => resolve(r) }
  }

  beforeEach(() => {
    snap.calls = 0
    snap.result = { media_type: 'image/jpeg', data: 'page', preview: 'data:image/jpeg;base64,page' }
  })

  it('designs in rounds, each with the page as it is now, and makes them one undo step', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
      .mockResolvedValueOnce({ say: 'Made the box red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: false, dropped: 1 })
      .mockResolvedValueOnce({ say: 'Moved it onto the margin.', ops: [{ op: 'set', id: 'r1', x: 50, y: 50 }, { op: 'set', id: 'zz1', x: 1 }], done: true, dropped: 0 })
    const { store } = studio()
    fireEvent.click(screen.getByRole('radio', { name: /Merlin/ }))
    expect(screen.getByRole('button', { name: MERLIN_SUGGESTIONS[0] })).toBeInTheDocument()
    const before = store.get().doc
    design('Make the box bolder')
    await screen.findByText('Merlin made 2 changes.')
    expect(merlin).toHaveBeenCalledTimes(2)
    const [first, second] = merlin.mock.calls.map((call) => call[2])
    expect(first).toMatchObject({ request: 'Make the box bolder', round: 1, previous: [], picture: null, current: { data: 'page' } })
    expect(first.page).toContain('[id r1]')
    expect(snap.args[3]).toEqual({ whole: true })
    expect(second.round).toBe(2)
    expect(second.previous).toEqual([{ say: 'Made the box red.', notes: ['Did {"op":"set","id":"r1","fill":"#ff0000"}', '1 edit couldn’t be used and was left out.'], did: 1, skipped: 1 }])
    expect(first.selected).toBe(0)
    expect(rect(store)).toMatchObject({ fill: '#ff0000', x: 50, y: 50 })
    expect(screen.getByText('Made the box red.')).toBeInTheDocument()
    // Round 1: one made and one the server left out; round 2: one made, one not on the page.
    expect(screen.getAllByText('1 change · 1 it couldn’t make')).toHaveLength(2)
    expect(screen.getByText('Before')).toBeInTheDocument()
    // Both rounds are one step: Undo Merlin takes the page back as it was.
    fireEvent.click(screen.getByRole('button', { name: 'Undo Merlin' }))
    expect(store.get().doc.items).toEqual(before.items)
    expect(screen.getByText('Undone: your page is as it was.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Undo Merlin' })).not.toBeInTheDocument()
    expect(store.canUndo()).toBe(false)
  })

  it('stops when the page is changed while it works, keeping what it already did', async () => {
    const two = later()
    vi.spyOn(studioApi, 'merlin')
      .mockResolvedValueOnce({ say: 'Red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: false, dropped: 0 })
      .mockReturnValueOnce(two.promise)
    const { store } = studio()
    design('Bolder')
    await waitFor(() => expect(rect(store).fill).toBe('#ff0000'))
    act(() => store.edit((d) => ({ ...d, paper: '#000000' })))
    await act(async () => two.resolve({ say: 'Moved.', ops: [{ op: 'set', id: 'r1', x: 99 }], done: true, dropped: 0 }))
    await screen.findByText('You changed the page while Merlin worked, so it stopped there.')
    expect(rect(store).x).toBe(0)
    expect(screen.getByText('Merlin made 1 change.')).toBeInTheDocument()
    // One ⌘Z now undoes the person's change, so Undo Merlin isn't offered.
    expect(screen.queryByRole('button', { name: 'Undo Merlin' })).not.toBeInTheDocument()
  })

  it('says how much was selected, so a narrow change can go to the quick model', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin').mockResolvedValueOnce({ say: 'Done.', ops: [], done: true, dropped: 0 })
    const { store } = studio()
    act(() => store.set({ selection: ['r1'] }))
    design('Make it red')
    await screen.findByText('Merlin left the page as it was.')
    expect(merlin.mock.calls[0][2].selected).toBe(1)
  })

  it('Stop leaves the round it asked for unmade', async () => {
    const one = later()
    const merlin = vi.spyOn(studioApi, 'merlin').mockReturnValueOnce(one.promise)
    const { store } = studio()
    design('Bolder')
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }))
    expect(screen.getByText('Stopping…')).toBeInTheDocument()
    expect(merlin.mock.calls[0][3]?.aborted).toBe(true) // the request is called off, not waited for
    await act(async () => one.resolve({ say: 'Red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: true, dropped: 0 }))
    await screen.findByText('Stopped.')
    expect(rect(store).fill).toBe('#d9d4cc')
    expect(store.canUndo()).toBe(false)
  })

  it('Stop while a request is called off shows Stopped, not an error', async () => {
    vi.spyOn(studioApi, 'merlin').mockImplementationOnce((_s, _p, _b, signal) => new Promise((_, reject) => {
      signal?.addEventListener('abort', () => reject(new DOMException('The operation was aborted.', 'AbortError')))
    }))
    studio()
    design('Bolder')
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }))
    await screen.findByText('Stopped.')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('Try again after a later round failed carries on from that round, in the same undo step', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
      .mockResolvedValueOnce({ say: 'Made the box red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: false, dropped: 0 })
      .mockRejectedValueOnce(new Error('Merlin couldn’t design that this time. Try again.'))
      .mockResolvedValueOnce({ say: 'Moved it.', ops: [{ op: 'set', id: 'r1', x: 50 }], done: true, dropped: 0 })
    const { store } = studio()
    const before = store.get().doc
    design('Bolder')
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('Merlin made 2 changes.')
    expect(merlin.mock.calls.map((call) => call[2].round)).toEqual([1, 2, 2])
    expect(merlin.mock.calls[2][2].previous).toHaveLength(1)
    expect(screen.getAllByText('Bolder')).toHaveLength(1)
    expect(rect(store)).toMatchObject({ fill: '#ff0000', x: 50 })
    act(() => store.undo())
    expect(store.get().doc).toBe(before) // one undo takes both rounds back
  })

  it('Try again starts over when the page was changed after the failure', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
      .mockResolvedValueOnce({ say: 'Red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: false, dropped: 0 })
      .mockRejectedValueOnce(new Error('Try again.'))
      .mockResolvedValueOnce({ say: 'Done.', ops: [], done: true, dropped: 0 })
    const { store } = studio()
    design('Bolder')
    await screen.findByRole('alert')
    act(() => store.edit((d) => ({ ...d, paper: '#000000' })))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(merlin).toHaveBeenCalledTimes(3))
    expect(merlin.mock.calls[2][2]).toMatchObject({ round: 1, previous: [] })
  })

  it('with no page in view, the request is kept in a turn that says so', () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
    const { store } = studio()
    act(() => store.set({ page: 5 }))
    design('Bolder')
    expect(screen.getByRole('alert')).toHaveTextContent('There’s no page in view for Merlin to design.')
    expect(screen.getByText('Bolder')).toBeInTheDocument()
    expect(merlin).not.toHaveBeenCalled()
  })

  it('a Merlin suggestion fills the box rather than changing the page', () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
    studio()
    fireEvent.click(screen.getByRole('radio', { name: /Merlin/ }))
    fireEvent.change(screen.getByRole('textbox', { name: 'What Merlin should design' }), { target: { value: 'my draft' } })
    fireEvent.click(screen.getByRole('button', { name: MERLIN_SUGGESTIONS[1] }))
    expect(screen.getByRole('textbox', { name: 'What Merlin should design' })).toHaveValue(MERLIN_SUGGESTIONS[1])
    expect(merlin).not.toHaveBeenCalled()
  })

  it('says when the day’s designs are used up, and tries again', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
      .mockRejectedValueOnce(new CappeApiError('Too many requests. Please try again later.', undefined, 429))
      .mockResolvedValueOnce({ say: 'Done.', ops: [], done: true, dropped: 0 })
    studio()
    design('Bolder')
    expect(await screen.findByRole('alert')).toHaveTextContent('Merlin has designed as much as it can for you today.')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('Merlin left the page as it was.')
    expect(merlin).toHaveBeenCalledTimes(2)
    expect(screen.getAllByText('Bolder')).toHaveLength(1)
  })

  it('goes on to the next round when every edit it sent was unusable, telling the next round so', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin')
      .mockResolvedValueOnce({ say: 'Tried a grid.', ops: [], done: false, dropped: 3 })
      .mockResolvedValueOnce({ say: 'Made the box red.', ops: [{ op: 'set', id: 'r1', fill: '#ff0000' }], done: true, dropped: 0 })
    const { store } = studio()
    design('Bolder')
    await screen.findByText('Merlin made 1 change.')
    expect(merlin).toHaveBeenCalledTimes(2)
    expect(merlin.mock.calls[1][2].previous).toEqual([
      { say: 'Tried a grid.', notes: ['3 edits couldn’t be used and were left out.'], did: 0, skipped: 1 }])
    expect(rect(store).fill).toBe('#ff0000')
  })

  it('stops when the model sent nothing at all, or says it is done', async () => {
    const merlin = vi.spyOn(studioApi, 'merlin').mockResolvedValueOnce({ say: 'It already matches.', ops: [], done: false, dropped: 0 })
    studio()
    design('Bolder')
    await screen.findByText('Merlin left the page as it was.')
    expect(merlin).toHaveBeenCalledTimes(1)
  })

  it('Ask the Studio and Ask about this answer, even when the panel was last left on Merlin', () => {
    const { store, ctx } = studio()
    const id = store.get().doc.items[0].id
    act(() => command('merlin').run(ctx))
    expect(conversation(store).get().mode).toBe('merlin')
    act(() => command('ask').run(ctx))
    expect(conversation(store).get().mode).toBe('ask')
    // "Ask about this" starts a question; sent from Merlin's box it would design from the same words.
    act(() => command('merlin').run(ctx))
    act(() => store.set({ selection: [id] }))
    act(() => command('ask-about').run(ctx))
    expect(conversation(store).get().mode).toBe('ask')
    expect(box()).toHaveValue(MATCH_QUESTION)
  })

  it('Help → Design with Merlin opens the panel in Merlin; Merlin isn’t a command Ask offers', () => {
    const { store, ctx } = studio()
    act(() => store.set({ panels: [] }))
    act(() => command('merlin').run(ctx))
    expect(store.get().panels).toContain('ask')
    expect(conversation(store).get().mode).toBe('merlin')
    expect(commandsPayload(store.get()).map((c) => c.id)).not.toContain('merlin')
  })
})

describe('what a round tells the next one', () => {
  const applied = (did: number, skipped: number): Applied => ({
    doc: doc(),
    did: Array.from({ length: did }, (_, k) => `Did ${k}`),
    skipped: Array.from({ length: skipped }, (_, k) => `Skipped ${k}`),
  })

  it('counts what took and what didn’t, and says how many edits were left out', () => {
    const r = roundNotes(true, applied(2, 1), 1)
    expect(r).toEqual({ notes: ['Did 0', 'Did 1', 'Skipped 0', '1 edit couldn’t be used and was left out.'], did: 2, skipped: 2 })
    expect(roundNotes(true, applied(1, 0), 3).notes.at(-1)).toBe('3 edits couldn’t be used and were left out.')
  })

  it('counts nothing as done when the page didn’t change', () => {
    const r = roundNotes(false, applied(2, 1), 0)
    expect(r.did).toBe(0)
    expect(r.notes[0]).toMatch(/^None of these edits took/)
    expect(r.skipped).toBe(2)
  })

  it('never sends more than the server takes: 60 notes, and no more skipped than that', () => {
    // 40 edits made and 70 not (many text frames pushed past their size): the next request would be refused over 60.
    const r = roundNotes(true, applied(40, 70), 2)
    expect(r.notes).toHaveLength(60)
    expect(r.did).toBe(40)
    expect(r.skipped).toBe(60)
    expect(roundNotes(true, applied(0, 90), 0).skipped).toBe(60)
  })
})
