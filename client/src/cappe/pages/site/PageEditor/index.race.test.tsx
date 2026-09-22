import type { ReactNode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PageEditor from './index'

type ThemeEditorForTest = {
  theme: Record<string, unknown>
  themeDirty: boolean
  setMode: (mode: 'light' | 'dark') => void
}

type ToolbarProps = {
  title: string
  meta: Record<string, unknown>
  promosDirty: boolean
  setMeta: (meta: Record<string, unknown>) => void
  setPromosDirty: (dirty: boolean) => void
  themeEditor: ThemeEditorForTest
  saving: boolean
  onSave: () => void
  onUndo: () => void
}

type FormProps = { blocks: Array<Record<string, unknown>> }

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const mocks = vi.hoisted(() => ({
  params: { siteId: 'site-1', pageId: 'page-a' },
  get: vi.fn(),
  put: vi.fn(),
  navigate: vi.fn(),
}))

const storage = (() => {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, String(value)) },
    removeItem: (key: string) => { values.delete(key) },
    clear: () => { values.clear() },
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size },
  }
})()

vi.mock('react-router-dom', () => ({
  useParams: () => mocks.params,
  useNavigate: () => mocks.navigate,
  Link: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('../../../api', () => ({
  cappeApi: { get: mocks.get, put: mocks.put },
}))

vi.mock('./DesignPrimitives', () => ({ usePremium: () => false }))
vi.mock('./useMerlin', () => ({
  useMerlin: () => ({
    open: false,
    setOpen: vi.fn(),
    width: 320,
    applyImageTo: vi.fn(),
  }),
}))
vi.mock('./useCanvasBridge', () => ({
  useCanvasBridge: () => ({
    selection: null,
    selBlock: null,
    setSelBlock: vi.fn(),
    pendingSelection: null,
    confirmPendingSelection: vi.fn(),
    dismissPendingSelection: vi.fn(),
    clearSelectedContext: vi.fn(),
    setSelection: vi.fn(),
    refreshTick: 0,
    suspendPreview: { current: false },
    selectSeq: 0,
    postToCanvas: vi.fn(),
  }),
}))
vi.mock('./usePagePreview', () => ({ usePagePreview: () => '' }))
vi.mock('./useThemeBridge', () => ({ useThemeBridge: () => ({}) }))
vi.mock('./useUnsavedGuard', () => ({ useUnsavedGuard: () => undefined }))
vi.mock('../../../utils/unsavedGuard', () => ({ confirmLeave: () => true }))

vi.mock('./EditorToolbar', () => ({
  EditorToolbar: (props: ToolbarProps) => (
    <div>
      <span data-testid="title">{props.title}</span>
      <span data-testid="meta-version">{String(props.meta.version ?? 0)}</span>
      <span data-testid="dirty">theme:{String(props.themeEditor.themeDirty)} meta:{String(props.promosDirty)}</span>
      <button
        data-testid="edit-meta"
        onClick={() => {
          props.setMeta({ ...props.meta, version: Number(props.meta.version ?? 0) + 1 })
          props.setPromosDirty(true)
        }}
      >edit meta</button>
      <button
        data-testid="edit-theme"
        onClick={() => props.themeEditor.setMode(props.themeEditor.theme.mode === 'dark' ? 'light' : 'dark')}
      >edit theme</button>
      <button data-testid="undo" onClick={props.onUndo}>undo</button>
      <button data-testid="save" disabled={props.saving} onClick={props.onSave}>save</button>
    </div>
  ),
}))
vi.mock('./FormModeView', () => ({
  FormModeView: ({ blocks }: FormProps) => <div data-testid="blocks">{JSON.stringify(blocks)}</div>,
}))
vi.mock('./CanvasModeView', () => ({ CanvasModeView: () => null }))
vi.mock('./MerlinPreviewView', () => ({ MerlinPreviewView: () => null }))
vi.mock('./ThemeMenu', () => ({ ThemeDrawer: () => null }))
vi.mock('./MerlinPanel', () => ({ MerlinDrawer: () => null }))

const page = (id: string, title: string) => ({
  id,
  site_id: 'site-1',
  title,
  slug: id,
  content: { blocks: [{ type: 'hero', heading: title }] },
  sort_order: 0,
  status: 'draft' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
})

const site = {
  id: 'site-1',
  theme_config: { mode: 'light' },
  meta_config: { version: 0 },
}

function installImmediateLoad(loadedPage = page('page-a', 'Page A')) {
  mocks.get.mockImplementation((path: string) => (
    path.endsWith('/pages') ? Promise.resolve([loadedPage]) : Promise.resolve(site)
  ))
}

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
  storage.clear()
  mocks.params.siteId = 'site-1'
  mocks.params.pageId = 'page-a'
  mocks.get.mockReset()
  mocks.put.mockReset()
  mocks.navigate.mockReset()
})

describe('PageEditor async ownership', () => {
  it('ignores an out-of-order page load after route params change', async () => {
    const first = deferred<ReturnType<typeof page>[]>()
    const second = deferred<ReturnType<typeof page>[]>()
    let pageRequest = 0
    mocks.get.mockImplementation((path: string) => {
      if (!path.endsWith('/pages')) return Promise.resolve(site)
      pageRequest += 1
      return pageRequest === 1 ? first.promise : second.promise
    })

    const view = render(<PageEditor />)
    await waitFor(() => expect(pageRequest).toBe(1))

    mocks.params.pageId = 'page-b'
    view.rerender(<PageEditor />)
    await waitFor(() => expect(pageRequest).toBe(2))
    expect(screen.queryByTestId('save')).toBeNull()

    await act(async () => { second.resolve([page('page-b', 'Page B')]) })
    expect(await screen.findByTestId('title')).toHaveTextContent('Page B')
    expect(screen.getByTestId('blocks')).toHaveTextContent('Page B')

    await act(async () => { first.resolve([page('page-a', 'Page A')]) })
    expect(screen.getByTestId('title')).toHaveTextContent('Page B')
    expect(screen.getByTestId('blocks')).toHaveTextContent('Page B')
  })

  it('keeps edits made during Save dirty and persists them on the next Save', async () => {
    installImmediateLoad()
    const firstPageSave = deferred<ReturnType<typeof page>>()
    let pageSaves = 0
    mocks.put.mockImplementation((path: string) => {
      if (path.includes('/pages/')) {
        pageSaves += 1
        return pageSaves === 1 ? firstPageSave.promise : Promise.resolve(page('page-a', 'Page A'))
      }
      return Promise.resolve(site)
    })
    render(<PageEditor />)
    await screen.findByTestId('title')

    fireEvent.click(screen.getByTestId('edit-theme'))
    fireEvent.click(screen.getByTestId('edit-meta'))
    fireEvent.click(screen.getByTestId('save'))
    await waitFor(() => expect(pageSaves).toBe(1))

    fireEvent.click(screen.getByTestId('edit-theme'))
    fireEvent.click(screen.getByTestId('edit-meta'))
    expect(screen.getByTestId('meta-version')).toHaveTextContent('2')

    await act(async () => { firstPageSave.resolve(page('page-a', 'Page A')) })
    await waitFor(() => expect(screen.getByTestId('save')).not.toBeDisabled())
    const firstSitePatch = mocks.put.mock.calls.find(([path]) => path === '/sites/site-1')?.[1]
    expect(firstSitePatch).toEqual({
      theme_config: { mode: 'dark' },
      meta_config: { version: 1 },
    })
    expect(screen.getByTestId('dirty')).toHaveTextContent('theme:true meta:true')

    fireEvent.click(screen.getByTestId('save'))
    await waitFor(() => {
      expect(mocks.put.mock.calls.filter(([path]) => path === '/sites/site-1')).toHaveLength(2)
    })
    const sitePatches = mocks.put.mock.calls.filter(([path]) => path === '/sites/site-1')
    expect(sitePatches[1][1]).toEqual({
      theme_config: { mode: 'light' },
      meta_config: { version: 2 },
    })
  })

  it('persists promo metadata restored by undo after a save', async () => {
    installImmediateLoad()
    mocks.put.mockImplementation((path: string) => (
      path.includes('/pages/') ? Promise.resolve(page('page-a', 'Page A')) : Promise.resolve(site)
    ))
    render(<PageEditor />)
    await screen.findByTestId('title')

    fireEvent.click(screen.getByTestId('edit-meta'))
    fireEvent.click(screen.getByTestId('save'))
    await waitFor(() => {
      expect(mocks.put.mock.calls.filter(([path]) => path === '/sites/site-1')).toHaveLength(1)
    })
    expect(screen.getByTestId('dirty')).toHaveTextContent('meta:false')

    fireEvent.click(screen.getByTestId('undo'))
    expect(screen.getByTestId('meta-version')).toHaveTextContent('0')
    expect(screen.getByTestId('dirty')).toHaveTextContent('meta:true')
    fireEvent.click(screen.getByTestId('save'))

    await waitFor(() => {
      expect(mocks.put.mock.calls.filter(([path]) => path === '/sites/site-1')).toHaveLength(2)
    })
    const sitePatches = mocks.put.mock.calls.filter(([path]) => path === '/sites/site-1')
    expect(sitePatches[1][1]).toEqual({ meta_config: { version: 0 } })
  })
})
