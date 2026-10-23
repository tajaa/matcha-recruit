import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Stories from './stories/Stories'
import StoryEditor from './editor/StoryEditor'
import MagazineSettings from './settings/MagazineSettings'
import ReaderView from './reader/ReaderView'
import { LINK_PREFIX } from './reader/book'
import { assetIdsIn, moveBlock, newBlock } from './editor/blocks'
import type { CappeAsset, CappeMagazine, CappePost, CappeStoryOptions, StoryBlock } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
const followed = vi.hoisted(() => ({ value: null as string | null }))
vi.mock('./reader/book', async (importOriginal) => {
  const real = await importOriginal<typeof import('./reader/book')>()
  return { ...real, followedLink: (w: Window | null | undefined) => {
    const v = followed.value
    followed.value = null
    return v ?? real.followedLink(w)
  } }
})
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const ASSET: CappeAsset = {
  id: 'a-1', kind: 'upload', url: 'https://cdn.example.test/a.jpg', prompt: null, aspect: null, image_size: null,
  created_at: '2026-10-20T09:00:00Z', source: 'upload', source_url: null, title: null, creator: null, creator_url: null,
  license: 'own', license_version: null, license_url: null, provider_label: null, credit_line: 'Photo: Ana Ruiz',
  alt: 'Boats', caption: null, width: 1600, height: 1000, bytes: 1, mime: 'image/jpeg', variants: {}, ai_generated: false,
  rights_attested_at: null, moderation: 'unchecked', updated_at: null,
}

const post = (over: Partial<CappePost> = {}): CappePost => ({
  id: 'p-1', site_id: 's-1', title: 'The harbour at dawn', slug: 'harbour', excerpt: 'Forty boats.', body: 'The boats.',
  cover_image_url: 'https://cdn.example.test/a.jpg', status: 'draft', published_at: null, created_at: '2026-10-20T09:00:00Z',
  updated_at: '2026-10-20T09:00:00Z', format: 'blocks',
  content: { blocks: [{ type: 'cover', asset_id: 'a-1', style: 'stacked', tone: 'light', focal: { x: 50, y: 50 } },
                      { type: 'text', md: 'The **boats**.', dropcap: true, columns: 1,
                        rt: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'The ' }, { type: 'text', text: 'boats', marks: [{ type: 'bold' }] }, { type: 'text', text: '.' }] }] } }] },
  kicker: 'Dispatch', topic: 'city', layout: 'standard', access: 'free', cover_asset_id: 'a-1', byline: 'Ana Ruiz',
  word_count: 2, reading_minutes: 1, hidden: false, ...over,
})

const magazine = (over: Partial<CappeMagazine> = {}): CappeMagazine => ({
  site_id: 's-1', enabled: true, name: 'Salt & Light', tagline: 'Harbour stories', about: null, masthead_style: 'classic',
  accent: null, topics: ['city'], front_at_root: false, nav_label: 'Magazine', cover_post_id: null, follow_enabled: true,
  paid_enabled: false, price_cents: null, paid_pitch: null, preview_blocks: 3, lapsed_at: null,
  created_at: null, updated_at: null, live: true, plan_includes_magazine: true, plan_includes_paid: true,
  stripe_ready: false, fee_bps: 3000, ...over,
})

const OPTIONS: CappeStoryOptions = {
  layouts: [
    { key: 'standard', label: 'Standard', content: { blocks: [newBlock('cover'), newBlock('text')] } },
    { key: 'photo_essay', label: 'Photo essay', content: { blocks: [newBlock('cover'), newBlock('photo'), newBlock('text')] } },
  ],
  topics: [{ key: 'city', label: 'City life' }, { key: 'food', label: 'Food & drink' }],
}

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    for (const [needle, value] of Object.entries(routes)) if (path.includes(needle)) return Promise.resolve(value)
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

function mount(path: string, element: React.ReactElement, pattern: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
        <Route path="/cappe/sites/:siteId/stories" element={<p>stories list</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.postHtml.mockResolvedValue('<!doctype html><p>preview</p>')
})

describe('block helpers', () => {
  it('lists every picture a story uses', () => {
    const blocks: StoryBlock[] = [
      { type: 'cover', asset_id: 'a', style: 'stacked', tone: 'light', focal: { x: 50, y: 50 } },
      { type: 'photos', layout: 'pair', items: [{ asset_id: 'b', caption: '' }, { asset_id: null, caption: '' }] },
      { type: 'photo', asset_id: null, caption: '', size: 'column' },
    ]
    expect(assetIdsIn(blocks)).toEqual(['a', 'b'])
  })

  it('moves blocks but keeps the cover first', () => {
    const blocks: StoryBlock[] = [newBlock('cover'), newBlock('text'), newBlock('quote')]
    expect(moveBlock(blocks, 2, 1).map((b) => b.type)).toEqual(['cover', 'quote', 'text'])
    expect(moveBlock(blocks, 1, 0)).toBe(blocks)
    expect(moveBlock(blocks, 2, 3)).toBe(blocks)
  })
})

describe('Stories', () => {
  it('shows the stories as covers and starts a new one', async () => {
    answer({ '/posts': [post(), post({ id: 'p-2', title: 'Hidden one', hidden: true, status: 'published', format: 'markdown' })],
             '/magazine': magazine(), '/stories/options': OPTIONS })
    api.post.mockResolvedValue(post({ id: 'p-new' }))
    mount('/cappe/sites/s-1/stories', <Stories />, '/cappe/sites/:siteId/stories')
    expect(await screen.findByRole('heading', { name: 'Salt & Light' })).toBeInTheDocument()
    expect(screen.getByText('Live on your site.')).toBeInTheDocument()
    expect(screen.getByText('The harbour at dawn')).toBeInTheDocument()
    expect(screen.getByText('hidden')).toBeInTheDocument()
    expect(screen.getByText('Plain post')).toBeInTheDocument()
    // Under /cappe: on hey-matcha.com Gummfit is mounted there, and a bare
    // /sites/… link lands on Matcha's 404.
    expect(screen.getByText('The harbour at dawn').closest('a')).toHaveAttribute('href', '/cappe/sites/s-1/stories/p-1')
    expect(screen.getByRole('link', { name: /Magazine settings/ })).toHaveAttribute('href', '/cappe/sites/s-1/magazine')
    fireEvent.click(screen.getByRole('tab', { name: 'draft' }))
    expect(screen.queryByText('Hidden one')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Flowing story/ }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/posts', { title: 'Untitled story', format: 'blocks', layout: 'standard' }))
  })

  it('opens a paged story in the Studio and starts one there', async () => {
    answer({ '/posts': [post({ format: 'pages', title: 'Designed' })], '/magazine': magazine(), '/stories/options': OPTIONS })
    api.post.mockResolvedValue(post({ id: 'p-new', format: 'pages' }))
    render(
      <MemoryRouter initialEntries={['/cappe/sites/s-1/stories']}>
        <Routes>
          <Route path="/cappe/sites/:siteId/stories" element={<Stories />} />
          <Route path="/cappe/studio/:siteId/story/:postId" element={<p>the studio</p>} />
        </Routes>
      </MemoryRouter>,
    )
    expect((await screen.findByText('Designed')).closest('a')).toHaveAttribute('href', '/cappe/studio/s-1/story/p-1')
    fireEvent.click(screen.getByRole('button', { name: /New story in Studio/ }))
    expect(await screen.findByText('the studio')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/posts', { title: 'Untitled story', format: 'pages' })
  })

  it('says when the plan has no magazine and shows an empty state', async () => {
    answer({ '/posts': [], '/magazine': magazine({ live: false, plan_includes_magazine: false }), '/stories/options': OPTIONS })
    mount('/cappe/sites/s-1/stories', <Stories />, '/cappe/sites/:siteId/stories')
    expect(await screen.findByText(/doesn’t include a magazine/)).toBeInTheDocument()
    expect(screen.getByText(/No stories yet/)).toBeInTheDocument()
  })

  it('shows a load failure', async () => {
    api.get.mockRejectedValue(new Error('Server error'))
    mount('/cappe/sites/s-1/stories', <Stories />, '/cappe/sites/:siteId/stories')
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })
})

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
  return (m: Record<string, unknown>) => send(win, m)
}

/** The story's blocks, in order, as the layers panel lists them. */
const kinds = () => Array.from(screen.getByRole('tree', { name: 'The story’s layers' }).querySelectorAll(':scope > li > div'))
  .map((row) => row.textContent)
const inspector = () => within(screen.getByRole('complementary', { name: 'Selected' }))
const openStory = () => mount('/cappe/sites/s-1/stories/p-1', <StoryEditor />, '/cappe/sites/:siteId/stories/:postId')

describe('StoryEditor', () => {
  beforeEach(() => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [ASSET] } })
  })

  it('hands a story made of pages to the Studio', async () => {
    answer({ '/posts/p-1': post({ format: 'pages' }), '/stories/options': OPTIONS, '/assets': { assets: [ASSET] } })
    render(
      <MemoryRouter initialEntries={['/cappe/sites/s-1/stories/p-1']}>
        <Routes>
          <Route path="/cappe/sites/:siteId/stories/:postId" element={<StoryEditor />} />
          <Route path="/cappe/studio/:siteId/story/:postId" element={<p>the studio</p>} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('the studio')).toBeInTheDocument()
  })

  it('edits on the page, sets the page again, and saves the content with the cover', async () => {
    api.put.mockResolvedValue(post({ title: 'Dawn', status: 'published' }))
    openStory()
    const say = await onPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('The harbour at dawn')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    // The cover selected: its picture and credit, and what can go on it.
    say({ type: 'mz-select', target: { kind: 'block', story: 'preview', block: 0 } })
    expect(await inspector().findByText('Photo: Ana Ruiz')).toBeInTheDocument()
    expect(inspector().getByRole('button', { name: 'Add heading' })).toBeEnabled()

    say({ type: 'mz-edit', story: 'preview', block: -1, field: '@title', value: 'Dawn', rich: false })
    say({ type: 'mz-edit', story: 'preview', block: 1, field: 'md', rich: true,
      value: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'New words.' }] }] } })
    // Nothing in hand: a block goes at the end. A story has one cover.
    say({ type: 'mz-select', target: { kind: 'none' } })
    fireEvent.click(screen.getByRole('button', { name: 'Text' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add pull quote to the story' }))
    expect(await inspector().findByRole('heading', { name: 'Pull quote' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Elements' }))
    expect(screen.queryByRole('button', { name: 'Add cover to the story' })).not.toBeInTheDocument()

    await waitFor(() => expect(api.postHtml.mock.calls.at(-1)![1]).toMatchObject({ title: 'Dawn', edit: true }), { timeout: 2000 })
    fireEvent.click(screen.getByRole('button', { name: /Publish/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const sent = api.put.mock.calls[0][1] as Record<string, unknown>
    expect(sent.title).toBe('Dawn')
    expect(sent.status).toBe('published')
    expect(sent.cover_asset_id).toBe('a-1')
    const blocks = (sent.content as { blocks: StoryBlock[] }).blocks
    expect(blocks[1]).toEqual({ type: 'text', md: 'New words.', rt: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'New words.' }] }] }, dropcap: true, columns: 1 })
    expect(blocks[2].type).toBe('quote')
    expect(await screen.findByText('published')).toBeInTheDocument()
  })

  it('picks a picture into a photo block, then lays one on it from the photos panel', async () => {
    api.put.mockResolvedValue(post())
    openStory()
    await onPage()
    fireEvent.click(screen.getByRole('button', { name: 'Elements' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add photo to the story' }))
    // Words and shapes wait for its picture.
    expect(await inspector().findByRole('heading', { name: 'Photo' })).toBeInTheDocument()
    expect(inspector().getByRole('button', { name: 'Add heading' })).toBeDisabled()
    fireEvent.click(inspector().getByRole('button', { name: 'Choose picture' }))
    const dialog = await screen.findByRole('dialog', { name: 'Choose a picture' })
    expect(dialog).toBeInTheDocument()
    // LibraryPanel lists the asset; opening it and choosing "Use this picture" fills the slot.
    fireEvent.click(await within(dialog).findByRole('button', { name: /Photo: Ana Ruiz/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use this picture' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(inspector().getByRole('button', { name: 'Change picture' })).toBeInTheDocument()

    // The picture in hand: a picture from the panel is laid ON it, at its own shape.
    fireEvent.click(screen.getByRole('button', { name: 'Photos' }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Boats' }))
    expect(await inspector().findByRole('textbox', { name: 'Layer name' })).toHaveValue('Boats')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const photo = (api.put.mock.calls[0][1] as { content: { blocks: StoryBlock[] } }).content.blocks[2] as Extract<StoryBlock, { type: 'photo' }>
    expect(photo).toMatchObject({ type: 'photo', asset_id: 'a-1' })
    // 40% of the photo's width; the same shape as the 16:10 picture on it.
    expect(photo.design!.layers).toEqual([expect.objectContaining({ kind: 'image', asset_id: 'a-1', w: 40, h: 40 })])
  })

  it('applies an Assist headline and opens a suggested archive search', async () => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [ASSET] },
      '/library/search': { source: 'nasa', query: 'earth at night', page: 0, has_more: false, results: [] } })
    api.post.mockImplementation((_path: string, body: { action: string }) => Promise.resolve(body.action === 'headlines'
      ? { action: 'headlines', headlines: [{ title: 'Four a.m.', dek: 'Boats go out.', kicker: 'Dispatch' }] }
      : { action: 'search_terms', terms: [{ source: 'nasa', query: 'earth at night' }] }))
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await onPage()
    fireEvent.click(screen.getByRole('button', { name: 'Assist' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use this' }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Four a.m.')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()

    fireEvent.click(screen.getByRole('tab', { name: 'Find pictures' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Search' }))
    const dialog = await screen.findByRole('dialog', { name: 'Find pictures' })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/sites/s-1/library/search?source=nasa&q=earth+at+night&page=0'))
    expect(within(dialog).getByPlaceholderText(/Harbour at dawn/)).toHaveValue('earth at night')
  })

  it('removes and reorders blocks from the panel of the one selected', async () => {
    openStory()
    await onPage()
    fireEvent.click(screen.getByRole('button', { name: 'Elements' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add divider to the story' }))
    fireEvent.click(screen.getByRole('button', { name: 'Layers' }))
    expect(kinds()).toEqual(['Cover', 'The boats.', 'Divider'])
    fireEvent.click(inspector().getByRole('button', { name: 'Move up' }))
    expect(kinds()).toEqual(['Cover', 'Divider', 'The boats.'])
    // The cover stays first.
    expect(inspector().getByRole('button', { name: 'Move up' })).toBeDisabled()
    fireEvent.click(inspector().getByRole('button', { name: 'Remove block' }))
    expect(kinds()).toEqual(['Cover', 'The boats.'])
    expect(inspector().getByRole('heading', { name: 'The story' })).toBeInTheDocument()
  })

  it('offers to turn a plain post into a story', async () => {
    answer({ '/posts/p-1': post({ format: 'markdown', content: null, body: 'Old *words*.' }), '/stories/options': OPTIONS, '/assets': { assets: [] } })
    api.put.mockResolvedValue(post({ content: { blocks: [{ type: 'text', md: 'Old *words*.', dropcap: true, columns: 1, rt: { type: 'doc', content: [
      { type: 'paragraph', content: [{ type: 'text', text: 'Old ' }, { type: 'text', text: 'words', marks: [{ type: 'italic' }] }, { type: 'text', text: '.' }] }] } }] } }))
    openStory()
    expect(await screen.findByText(/plain post written as Markdown/)).toBeInTheDocument()
    expect(api.postHtml).not.toHaveBeenCalled()
    expect(screen.queryByRole('tree')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Turn into a story' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/posts/p-1', { format: 'blocks' }))
    // The server keeps its words as a document; the workspace opens on its pages.
    await onPage()
    expect(kinds()).toEqual(['Old words.'])
    expect(api.postHtml).toHaveBeenCalledWith('/sites/s-1/stories/preview', expect.objectContaining({ edit: true }))
  })

  it('shows a save failure and deletes after confirming', async () => {
    api.put.mockRejectedValue(new Error('A picture in this story isn’t in your library any more.'))
    api.delete.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    openStory()
    await onPage()
    fireEvent.click(screen.getByRole('button', { name: /Publish/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t in your library')
    fireEvent.click(screen.getByRole('button', { name: /Delete story/ }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sites/s-1/posts/p-1'))
    expect(await screen.findByText('stories list')).toBeInTheDocument()
  })

  it('switching layout on an empty story fills in that layout’s blocks', async () => {
    answer({ '/posts/p-1': post({ content: { blocks: [newBlock('cover'), newBlock('text')] } }), '/stories/options': OPTIONS, '/assets': { assets: [] } })
    openStory()
    await onPage()
    fireEvent.change(screen.getByLabelText('Layout'), { target: { value: 'photo_essay' } })
    expect(kinds()).toEqual(['Cover', 'Photo', 'Text'])
  })
})

describe('MagazineSettings', () => {
  it('loads, edits and saves', async () => {
    answer({ '/magazine': magazine(), '/stories/options': OPTIONS })
    api.put.mockResolvedValue(magazine({ topics: ['city', 'food'], masthead_style: 'display', front_at_root: true }))
    mount('/cappe/sites/s-1/magazine', <MagazineSettings />, '/cappe/sites/:siteId/magazine')
    expect(await screen.findByDisplayValue('Salt & Light')).toBeInTheDocument()
    expect(screen.getByText(/Live: your stories render/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Food & drink' }))
    fireEvent.click(screen.getByRole('radio', { name: /Display/ }))
    fireEvent.click(screen.getByLabelText(/The magazine is the home page/))
    expect(screen.queryByLabelText(/Link in the site’s menu/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const sent = api.put.mock.calls[0][1] as Record<string, unknown>
    expect(sent).toMatchObject({ topics: ['city', 'food'], masthead_style: 'display', front_at_root: true, name: 'Salt & Light', accent: null })
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
  })

  it('warns when the plan has no magazine and shows a save failure', async () => {
    answer({ '/magazine': magazine({ live: false, plan_includes_magazine: false }), '/stories/options': OPTIONS })
    api.put.mockRejectedValue(new Error('Pick the magazine’s topics from the list.'))
    mount('/cappe/sites/s-1/magazine', <MagazineSettings />, '/cappe/sites/:siteId/magazine')
    expect(await screen.findByText(/Your plan doesn’t include a magazine/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('topics from the list')
  })

  it('caps topics at five', async () => {
    const many = { ...OPTIONS, topics: ['a', 'b', 'c', 'd', 'e', 'f'].map((k) => ({ key: k, label: k.toUpperCase() })) }
    answer({ '/magazine': magazine({ topics: ['a', 'b', 'c', 'd', 'e'] }), '/stories/options': many })
    mount('/cappe/sites/s-1/magazine', <MagazineSettings />, '/cappe/sites/:siteId/magazine')
    await screen.findByDisplayValue('Salt & Light')
    fireEvent.click(screen.getByRole('button', { name: 'F' }))
    expect(screen.getByRole('button', { name: 'F' })).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('ReaderView', () => {
  it('shows the page as a reader sees it and follows story links inside', async () => {
    api.postHtml.mockResolvedValue('<!doctype html><a href="/stories/low-tide">Low tide</a><a href="https://elsewhere.test/">x</a>')
    render(
      <MemoryRouter initialEntries={['/cappe/sites/s-1/magazine/view']}>
        <Routes><Route path="/cappe/sites/:siteId/magazine/view" element={<ReaderView />} /></Routes>
      </MemoryRouter>,
    )
    const frame = await screen.findByTitle('Reader view') as HTMLIFrameElement
    expect(api.postHtml).toHaveBeenCalledWith('/sites/s-1/magazine/view', {})
    expect(frame).toHaveAttribute('sandbox', 'allow-same-origin')
    expect(screen.getByText(/Only you can see this until you publish/)).toBeInTheDocument()
    // jsdom doesn't load srcDoc, so the page's link is written into the frame here.
    frame.contentDocument!.body.innerHTML = '<a href="/stories/low-tide">Low tide</a>'
    fireEvent.load(frame)
    expect(frame.contentDocument!.querySelector('a')!.getAttribute('href')).toBe(`${LINK_PREFIX}%2Fstories%2Flow-tide`)
    // Following it leaves the frame on that blank page; jsdom can't, so say so.
    followed.value = '/stories/low-tide'
    fireEvent.load(frame)
    await waitFor(() => expect(api.postHtml).toHaveBeenLastCalledWith('/sites/s-1/magazine/view', { slug: 'low-tide' }))
  })
})
