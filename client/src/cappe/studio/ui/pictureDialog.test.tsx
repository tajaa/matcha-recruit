import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Measure } from '../compose/compose'
import { addItem, patchItems } from '../model/ops'
import type { Doc } from '../model/types'
import { DEFAULT_VIEW, Store, type State } from '../store/store'
import { COMMANDS } from './commands'
import { StudioContext, type StudioCtx } from './context'
import { PictureDialog } from './dialogs'

// The editor itself is tested on its own; here it says where it opened and
// hands back an edited picture.
vi.mock('../picture/PictureEditor', () => ({
  default: ({ asset, startIn, onDone, onClose, onHelp }: { asset: { id: string }; startIn: string; onDone: (a: unknown) => void; onClose: () => void; onHelp: (s: string) => void }) => (
    <div>
      <p>Editing {asset.id} in {startIn}</p>
      <button type="button" onClick={() => onDone({ id: 'e1', kind: 'edit', url: 'https://cdn.example.test/e.png', parent_asset_id: asset.id, recipe: { look: 'noir' }, credit_line: 'Haley' })}>Finish</button>
      <button type="button" onClick={onClose}>Leave</button>
      <button type="button" onClick={() => onHelp('cutout')}>Help</button>
    </div>
  ),
}))

const mono: Measure = { width: (c, t) => [...t].length * 0.5 * c.size, metrics: (c) => ({ asc: 0.8 * c.size, desc: 0.2 * c.size }) }
const doc = (): Doc => ({
  v: 1, size: { w: 600, h: 800 }, facing: true, margins: { t: 50, b: 50, i: 50, o: 50 }, cols: { n: 1, g: 12 },
  baseline: { start: 50, step: 12 }, grid: { step: 12 }, bleed: 9, units: 'pt', paper: '#ffffff',
  pages: [{ id: 'p1' }], guides: [], items: [], threads: [], paywall_page: null,
})

/** A page with an empty picture frame and one holding the Campanile. */
function studio() {
  let d = addItem(doc(), 'image', 'p1', { x: 0, y: 0, w: 100, h: 100 }).doc
  d = addItem(d, 'image', 'p1', { x: 200, y: 0, w: 100, h: 100 }).doc
  const [empty, full] = d.items.map((i) => i.id)
  d = patchItems(d, [full], { asset_id: 'a1' })
  const store = new Store({
    doc: d, selection: [full], editing: null, page: 1, tool: 'select', view: { ...DEFAULT_VIEW }, panels: [], drawer: null,
    overset: new Set(), assets: { a1: { id: 'a1', url: 'https://cdn.example.test/a.jpg', credit_line: 'Haley' } },
    dialog: 'picture', guide: null, threading: null, snaps: null, marquee: null,
    save: { rev: 1, state: 'saved', message: null, draft: false, live: false },
  } as State, mono)
  const ctx = { store, siteId: 's1' } as unknown as StudioCtx
  return { store, ctx, empty, full }
}
const show = (ctx: StudioCtx, cutout?: boolean) =>
  render(<StudioContext.Provider value={ctx}><PictureDialog cutout={cutout} /></StudioContext.Provider>)

describe('the Picture Editor in the Studio', () => {
  it('puts the edited picture in its frame as one undo step, and in the library', () => {
    const { store, ctx, full } = studio()
    show(ctx)
    expect(screen.getByText('Editing a1 in adjust')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    const s = store.get()
    expect(s.dialog).toBeNull()
    expect(s.doc.items.find((i) => i.id === full)).toMatchObject({ asset_id: 'e1' })
    expect(s.assets.e1).toMatchObject({ kind: 'edit', parent: 'a1', recipe: { look: 'noir' } })
    store.undo()
    expect(store.get().doc.items.find((i) => i.id === full)).toMatchObject({ asset_id: 'a1' })
  })

  it('opens at the cut-out, and leaving changes nothing', () => {
    const { store, ctx, full } = studio()
    show(ctx, true)
    expect(screen.getByText('Editing a1 in cutout')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }))
    expect(store.get().dialog).toBeNull()
    expect(store.get().doc.items.find((i) => i.id === full)).toMatchObject({ asset_id: 'a1' })
  })

  it('opens the guide at the section asked for, over the editor', () => {
    const { store, ctx } = studio()
    show(ctx, true)
    fireEvent.click(screen.getByRole('button', { name: 'Help' }))
    expect(store.get().guide).toBe('cutout')
    expect(store.get().dialog).toBe('picture')
    COMMANDS.find((c) => c.id === 'shortcuts')!.run(ctx)
    expect(store.get().guide).toBe('keys')
  })

  it('asks for a picture when the frame selected is empty', () => {
    const { store, ctx, empty } = studio()
    store.set({ selection: [empty] })
    show(ctx)
    expect(screen.getByText(/Select a picture frame with a picture in it/)).toBeInTheDocument()
  })

  it('is on the menus only while a picture is selected', () => {
    const { store, empty } = studio()
    const edit = COMMANDS.find((c) => c.id === 'edit-picture')!
    const cut = COMMANDS.find((c) => c.id === 'cut-out')!
    expect([edit.enabled!(store.get()), cut.enabled!(store.get())]).toEqual([true, true])
    store.set({ selection: [empty] })
    expect(edit.enabled!(store.get())).toBe(false)
    store.set({ selection: [] })
    expect(cut.enabled!(store.get())).toBe(false)
  })
})
