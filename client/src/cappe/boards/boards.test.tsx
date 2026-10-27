import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CappeAsset } from '../types'
import type { Board, Pin } from './api'
import { angleTo, cascade, COMPACT_AT, fitView, raise, resized, toBoard, zoomAt } from './board'
import { asUrl, fromText, fromTransfer, pinnable, tooBig, typingIn } from './paste'
import { MAX_FILE_BYTES, NOTE_MAX, SIZE_MAX, SIZE_MIN } from './limits'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() }))
vi.mock('../api', async () => {
  const real = await vi.importActual<typeof import('../api')>('../api')
  return { ...real, cappeApi: api, cappeApiBase: '/api/cappe' }
})

const { default: BoardsPage } = await import('./BoardsPage')
const { default: BoardPage } = await import('./BoardPage')
const { default: BoardTab } = await import('../studio/ui/add/BoardTab')
const { StudioContext } = await import('../studio/ui/context')
const { DEFAULT_VIEW, Store } = await import('../studio/store/store')

const NOW = '2026-10-27T12:00:00Z'
const pin = (id: string, over: Partial<Pin> = {}): Pin => ({
  id, board_id: 'b1', kind: 'note', x: 0, y: 0, w: 220, h: 180, rotation: 0, z: 1, asset_id: null, in_library: false,
  src: null, full: null, file_url: null, alt: null, filename: null, mime: null, size_bytes: 0, width: null, height: null,
  note: 'Warm light', color: 'yellow', url: null, title: null, description: null, site_name: null,
  created_at: NOW, updated_at: NOW, ...over,
})
const board = (over: Partial<Board> = {}): Board =>
  ({ id: 'b1', title: 'Spring issue', pin_count: 0, covers: [], created_at: NOW, updated_at: NOW, ...over })
const asset = (over: Partial<CappeAsset> = {}): CappeAsset =>
  ({ id: 'a1', url: 'https://cdn.example.test/a.jpg', width: 1500, height: 1000, alt: 'Dunes', kind: 'upload', variants: null, ...over } as CappeAsset)

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

// ── geometry ────────────────────────────────────────────────────────────────

describe('the board’s geometry', () => {
  it('keeps the point under the cursor still while zooming', () => {
    const view = { x: 40, y: -20, zoom: 1 }
    const before = toBoard(view, 300, 200)
    const after = zoomAt(view, 1.5, 300, 200)
    expect(toBoard(after, 300, 200).x).toBeCloseTo(before.x)
    expect(toBoard(after, 300, 200).y).toBeCloseTo(before.y)
    expect(zoomAt(view, 100, 0, 0).zoom).toBe(3)
    expect(zoomAt(view, 0.001, 0, 0).zoom).toBe(0.2)
  })

  it('fits every pin in view, never past 100%', () => {
    const pins = [pin('a', { x: 0, y: 0, w: 200, h: 100 }), pin('b', { x: 1800, y: 900, w: 200, h: 100 })]
    const v = fitView(pins, 1000, 600)
    expect(v.zoom).toBeLessThan(1)
    const tl = { x: v.x, y: v.y }
    expect(tl.x).toBeGreaterThanOrEqual(47)
    expect(fitView([pin('a', { w: 100, h: 100 })], 1000, 800).zoom).toBe(1)
    expect(fitView([], 1000, 800)).toEqual({ x: 48, y: 48, zoom: 1 })
  })

  it('raises a pin above the rest, and renumbers when the numbers climb too high', () => {
    const pins = [pin('a', { z: 1 }), pin('b', { z: 2 }), pin('c', { z: 3 })]
    const r = raise(pins, 'a')
    expect(r.changed.map((p) => [p.id, p.z])).toEqual([['a', 4]])
    expect(raise(pins, 'c').changed).toEqual([])
    const high = [pin('a', { z: COMPACT_AT }), pin('b', { z: 5 }), pin('c', { z: 7 })]
    const compact = raise(high, 'b')
    expect(Object.fromEntries(compact.pins.map((p) => [p.id, p.z]))).toEqual({ c: 1, a: 2, b: 3 })
    expect(compact.changed).toHaveLength(3)
  })

  it('sizes pictures in their shape, notes freely, within the bounds', () => {
    const photo = pin('p', { kind: 'image', w: 300, h: 200 })
    expect(resized(photo, 600, 50)).toEqual({ w: 600, h: 400 })
    expect(resized(photo, 600, 50, true)).toEqual({ w: 600, h: 50 })
    expect(resized(pin('n'), 10, 99999)).toEqual({ w: SIZE_MIN, h: SIZE_MAX })
  })

  it('turns from the centre and snaps to straight', () => {
    const c = { x: 100, y: 100 }
    expect(angleTo(c, { x: 100, y: 0 })).toBe(0)
    expect(angleTo(c, { x: 200, y: 100 })).toBe(90)
    expect(angleTo(c, { x: 102, y: 0 })).toBe(0)
    expect(angleTo(c, { x: 150, y: 0 })).toBeCloseTo(26.6, 0)
  })

  it('cascades several drops so none hides another', () => {
    const at = { x: 100, y: 100 }
    expect(cascade(at, 0)).toEqual({ x: 100, y: 100 })
    expect(cascade(at, 2)).toEqual({ x: 156, y: 156 })
  })
})

// ── what a paste or a drop means ────────────────────────────────────────────

describe('pasting and dropping', () => {
  const transfer = (o: { files?: File[]; text?: string; uri?: string }) => ({
    files: o.files ?? [], items: null,
    getData: (t: string) => (t === 'text/plain' ? o.text ?? '' : t === 'text/uri-list' ? o.uri ?? '' : ''),
  })

  it('makes a link of an address and a note of anything else', () => {
    expect(fromText('https://example.com/look')).toEqual({ kind: 'link', url: 'https://example.com/look' })
    expect(fromText('www.example.org')).toEqual({ kind: 'link', url: 'www.example.org' })
    expect(fromText('example.com/a/b')).toEqual({ kind: 'link', url: 'example.com/a/b' })
    expect(fromText('Warm light, 70s grain')).toEqual({ kind: 'note', text: 'Warm light, 70s grain' })
    expect(fromText('x'.repeat(NOTE_MAX + 50))).toMatchObject({ kind: 'note' })
    expect((fromText('x'.repeat(NOTE_MAX + 50)) as { text: string }).text).toHaveLength(NOTE_MAX)
    expect(fromText('   ')).toBeNull()
    expect(asUrl('see example.com')).toBeNull()
  })

  it('takes files first: a copied screenshot also carries its name as words', () => {
    const shot = new File(['x'], 'Screenshot.png', { type: 'image/png' })
    expect(fromTransfer(transfer({ files: [shot], text: 'Screenshot.png' }))).toEqual({ kind: 'files', files: [shot] })
    expect(fromTransfer(transfer({ uri: '# comment\nhttps://example.com/x', text: 'https://example.com/x' })))
      .toEqual({ kind: 'link', url: 'https://example.com/x' })
    expect(fromTransfer(null)).toBeNull()
  })

  it('knows what the server takes', () => {
    expect(pinnable(new File(['x'], 'a.png', { type: 'image/png' }))).toBe(true)
    expect(pinnable(new File(['x'], 'brief.docx', { type: '' }))).toBe(true)
    expect(pinnable(new File(['x'], 'song.mp3', { type: 'audio/mpeg' }))).toBe(false)
    expect(tooBig({ size: MAX_FILE_BYTES + 1 } as File)).toBe(true)
  })

  it('leaves a paste in a field to the field', () => {
    expect(typingIn(document.createElement('input'))).toBe(true)
    expect(typingIn(document.createElement('div'))).toBe(false)
  })
})

// ── the wall of boards ──────────────────────────────────────────────────────

function at(path: string, routes: React.ReactNode) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>{routes}</Routes></MemoryRouter>)
}

describe('the boards page', () => {
  it('shows each board with its pictures and makes a new one', async () => {
    api.get.mockResolvedValue({ boards: [board({ pin_count: 3, covers: ['/public/board-files/t1', 'https://cdn.example.test/w.webp'] })] })
    api.post.mockResolvedValue(board({ id: 'b2', title: 'Covers' }))
    at('/cappe/sites/s1/boards', <>
      <Route path="/cappe/sites/:siteId/boards" element={<BoardsPage />} />
      <Route path="/cappe/sites/:siteId/boards/:boardId" element={<p>opened board</p>} />
    </>)
    expect(await screen.findByText('Spring issue')).toBeInTheDocument()
    expect(screen.getByText(/3 pins/)).toBeInTheDocument()
    const imgs = document.querySelectorAll('img')
    expect([...imgs].map((i) => i.getAttribute('src'))).toEqual(['/api/cappe/public/board-files/t1', 'https://cdn.example.test/w.webp'])
    fireEvent.change(screen.getByLabelText('New board name'), { target: { value: '  Covers ' } })
    fireEvent.click(screen.getByRole('button', { name: /New board/ }))
    expect(await screen.findByText('opened board')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s1/boards', { title: 'Covers' })
  })

  it('asks before deleting a board', async () => {
    api.get.mockResolvedValue({ boards: [board()] })
    api.delete.mockResolvedValue(null)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    at('/cappe/sites/s1/boards', <Route path="/cappe/sites/:siteId/boards" element={<BoardsPage />} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Spring issue' }))
    expect(api.delete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete Spring issue' }))
    await waitFor(() => expect(screen.queryByText('Spring issue')).not.toBeInTheDocument())
    expect(api.delete).toHaveBeenCalledWith('/sites/s1/boards/b1')
    confirm.mockRestore()
  })
})

// ── one board ───────────────────────────────────────────────────────────────

function openBoard(pins: Pin[]) {
  api.get.mockResolvedValue({ board: board({ pin_count: pins.length }), pins, assets: [] })
  return at('/cappe/sites/s1/boards/b1', <Route path="/cappe/sites/:siteId/boards/:boardId" element={<BoardPage />} />)
}

function paste(data: { files?: File[]; text?: string }) {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', {
    value: { files: data.files ?? [], items: null, getData: (t: string) => (t === 'text/plain' ? data.text ?? '' : '') },
  })
  act(() => { document.body.dispatchEvent(event) })
}

describe('a board', () => {
  it('pins a pasted screenshot as an upload', async () => {
    openBoard([])
    expect(await screen.findByText('Pin anything that inspires you')).toBeInTheDocument()
    api.upload.mockResolvedValue(pin('p1', { kind: 'image', src: '/public/board-files/t', note: null }))
    const shot = new File(['png'], 'Screenshot.png', { type: 'image/png' })
    paste({ files: [shot], text: 'Screenshot.png' })
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(1))
    const [path, form] = api.upload.mock.calls[0]
    expect(path).toBe('/sites/s1/boards/b1/pins/upload')
    expect((form as FormData).get('file')).toBe(shot)
    expect(await screen.findByRole('button', { name: /^Picture/ })).toBeInTheDocument()
  })

  it('pins a pasted address as a link and pasted words as a note', async () => {
    openBoard([])
    await screen.findByText('Pin anything that inspires you')
    api.post.mockResolvedValue(pin('p2', { kind: 'link', url: 'https://example.com', title: 'Example' }))
    paste({ text: 'https://example.com' })
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s1/boards/b1/pins',
      expect.objectContaining({ kind: 'link', url: 'https://example.com' })))
    paste({ text: 'Soft, warm, a little grainy' })
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/sites/s1/boards/b1/pins',
      expect.objectContaining({ kind: 'note', note: 'Soft, warm, a little grainy' })))
  })

  it('refuses what it can’t pin and says why', async () => {
    openBoard([])
    await screen.findByText('Pin anything that inspires you')
    paste({ files: [new File(['x'], 'song.mp3', { type: 'audio/mpeg' })] })
    expect(await screen.findByRole('status')).toHaveTextContent('song.mp3')
    expect(api.upload).not.toHaveBeenCalled()
  })

  it('writes a new note where you are and sends only its place', async () => {
    openBoard([])
    await screen.findByText('Pin anything that inspires you')
    api.post.mockResolvedValue(pin('n1', { note: 'Cover: sea glass' }))
    fireEvent.click(screen.getByTitle('Note'))
    const box = screen.getByLabelText('Note')
    fireEvent.change(box, { target: { value: '  Cover: sea glass ' } })
    fireEvent.blur(box)
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const body = api.post.mock.calls[0][1]
    expect(Object.keys(body).sort()).toEqual(['color', 'kind', 'note', 'x', 'y'])
    expect(body).toMatchObject({ kind: 'note', note: 'Cover: sea glass', color: 'yellow' })
  })

  it('drops a blank new note', async () => {
    openBoard([])
    await screen.findByText('Pin anything that inspires you')
    fireEvent.click(screen.getByTitle('Note'))
    fireEvent.blur(screen.getByLabelText('Note'))
    expect(screen.queryByLabelText('Note')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('takes the selected pin off with Delete, after asking', async () => {
    openBoard([pin('n1')])
    const note = await screen.findByRole('button', { name: /^Note: Warm light/ })
    api.delete.mockResolvedValue(null)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.focus(note)
    fireEvent.keyDown(document, { key: 'Delete' })
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sites/s1/boards/b1/pins/n1'))
    expect(screen.queryByRole('button', { name: /^Note: Warm light/ })).not.toBeInTheDocument()
    confirm.mockRestore()
  })

  it('offers a private picture to the library and shows the library’s copy after', async () => {
    openBoard([pin('p1', { kind: 'image', src: '/public/board-files/t', full: '/public/board-files/f', note: null })])
    fireEvent.focus(await screen.findByRole('button', { name: /^Picture/ }))
    fireEvent.click(screen.getByRole('button', { name: /Add to library/ }))
    const dialog = screen.getByRole('dialog', { name: 'Add to your library' })
    const add = within(dialog).getByRole('button', { name: 'Add to library' })
    expect(add).toBeDisabled()
    fireEvent.click(within(dialog).getByLabelText(/I took this picture/))
    api.post.mockResolvedValue({ pin: pin('p1', { kind: 'image', in_library: true, asset_id: 'a1', src: 'https://cdn.example.test/w.webp' }), asset: asset() })
    fireEvent.click(add)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s1/boards/b1/pins/p1/library',
      expect.objectContaining({ rights_attested: true })))
    expect(await screen.findByText('In your library')).toBeInTheDocument()
  })
})

// ── the Studio's Board tab ──────────────────────────────────────────────────

function studio() {
  const store = new Store({
    doc: { v: 1, size: { w: 600, h: 800 }, facing: false, margins: { t: 50, b: 50, i: 60, o: 40 }, cols: { n: 1, g: 12 },
      baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
      pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null },
    selection: [], editing: null, page: 0, tool: 'text', view: { ...DEFAULT_VIEW, zoom: 1 }, panels: [], drawer: 'board',
    overset: new Set(), assets: {}, dialog: null, guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
  } as never, { width: (c: { size: number }, t: string) => [...t].length * 0.5 * c.size, metrics: (c: { size: number }) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) } as never)
  const el = document.createElement('div')
  const ctx = { store, siteId: 's1', postId: 'post1', board: () => el, editor: { close: vi.fn() },
    fonts: { book: null, ensure: vi.fn(async () => {}) } }
  return { store, ctx }
}

describe('the Studio’s Board tab', () => {
  it('adds a library picture from a board to the page', async () => {
    api.get.mockImplementation(async (path: string) => (path === '/sites/s1/boards'
      ? { boards: [board()] }
      : { board: board(), pins: [pin('p1', { kind: 'image', asset_id: 'a1', in_library: true, src: 'https://cdn.example.test/w.webp', note: null }),
          pin('n1', { z: 0 })], assets: [asset()] }))
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx as never}><BoardTab /></StudioContext.Provider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Add Dunes' }))
    expect(store.get().doc.items.some((i) => i.kind === 'image' && i.asset_id === 'a1')).toBe(true)
    expect(screen.getByText('Warm light')).toBeInTheDocument()
  })

  it('asks before a private picture goes into the library', async () => {
    api.get.mockImplementation(async (path: string) => (path === '/sites/s1/boards'
      ? { boards: [board()] }
      : { board: board(), pins: [pin('p1', { kind: 'image', src: '/public/board-files/t', note: null })], assets: [] }))
    const { store, ctx } = studio()
    render(<StudioContext.Provider value={ctx as never}><BoardTab /></StudioContext.Provider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Add this reference picture to your library' }))
    expect(store.get().doc.items).toHaveLength(0)
    fireEvent.click(screen.getByLabelText(/I took this picture/))
    api.post.mockResolvedValue({ pin: pin('p1', { kind: 'image', in_library: true, asset_id: 'a1' }), asset: asset() })
    fireEvent.click(screen.getByRole('button', { name: 'Add to library' }))
    await waitFor(() => expect(store.get().doc.items.some((i) => i.kind === 'image' && i.asset_id === 'a1')).toBe(true))
  })

  it('points to the dashboard when there is no board yet', async () => {
    api.get.mockResolvedValue({ boards: [] })
    const { ctx } = studio()
    render(<StudioContext.Provider value={ctx as never}><BoardTab /></StudioContext.Provider>)
    expect(await screen.findByRole('link', { name: /Start a mood board/ })).toHaveAttribute('href', '/cappe/sites/s1/boards')
  })
})
