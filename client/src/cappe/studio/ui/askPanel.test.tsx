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

  it('refuses a picture it can’t send', async () => {
    studio()
    const input = screen.getByLabelText('Attach a picture', { selector: 'input' })
    fireEvent.change(input, { target: { files: [new File(['GIF89a'], 'a.gif', { type: 'image/gif' })] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Attach a JPEG, PNG or WebP picture.')
  })
})
