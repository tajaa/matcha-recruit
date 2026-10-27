import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CappeApiError } from '../../api'
import type { Measure } from '../compose/compose'
import { addItem } from '../model/ops'
import type { Doc } from '../model/types'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { studioApi } from '../api'
import { commandsPayload, conversation, guidePayload, SUGGESTIONS } from './ask/conversation'
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
const snap = vi.hoisted(() => ({ calls: 0, result: null as null | { media_type: 'image/jpeg'; data: string; preview: string } }))
vi.mock('./ask/snapshot', () => ({ snapshot: async () => { snap.calls++; return snap.result } }))

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
  const ctx = { store, siteId: 's1', postId: 'post1' } as unknown as StudioCtx
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
    expect(conversation(store).get().draft).not.toBeNull()
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
