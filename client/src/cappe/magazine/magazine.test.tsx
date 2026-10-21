import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Stories from './stories/Stories'
import StoryEditor from './editor/StoryEditor'
import MagazineSettings from './settings/MagazineSettings'
import { assetIdsIn, moveBlock, newBlock } from './editor/blocks'
import type { CappeAsset, CappeMagazine, CappePost, CappeStoryOptions, StoryBlock } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
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
                      { type: 'text', md: 'The **boats**.', dropcap: true, columns: 1 }] },
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
        <Route path="/sites/:siteId/stories" element={<p>stories list</p>} />
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
    mount('/sites/s-1/stories', <Stories />, '/sites/:siteId/stories')
    expect(await screen.findByRole('heading', { name: 'Salt & Light' })).toBeInTheDocument()
    expect(screen.getByText('Live on your site.')).toBeInTheDocument()
    expect(screen.getByText('The harbour at dawn')).toBeInTheDocument()
    expect(screen.getByText('hidden')).toBeInTheDocument()
    expect(screen.getByText('Plain post')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'draft' }))
    expect(screen.queryByText('Hidden one')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /New story/ }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/posts', { title: 'Untitled story', format: 'blocks', layout: 'standard' }))
  })

  it('says when the plan has no magazine and shows an empty state', async () => {
    answer({ '/posts': [], '/magazine': magazine({ live: false, plan_includes_magazine: false }), '/stories/options': OPTIONS })
    mount('/sites/s-1/stories', <Stories />, '/sites/:siteId/stories')
    expect(await screen.findByText(/doesn’t include a magazine/)).toBeInTheDocument()
    expect(screen.getByText(/No stories yet/)).toBeInTheDocument()
  })

  it('shows a load failure', async () => {
    api.get.mockRejectedValue(new Error('Server error'))
    mount('/sites/s-1/stories', <Stories />, '/sites/:siteId/stories')
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })
})

describe('StoryEditor', () => {
  beforeEach(() => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [ASSET] } })
  })

  it('edits the blocks, previews, and saves the content with the cover', async () => {
    api.put.mockResolvedValue(post({ title: 'Dawn', status: 'published' }))
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    expect(await screen.findByDisplayValue('The harbour at dawn')).toBeInTheDocument()
    expect(screen.getByText('Photo: Ana Ruiz')).toBeInTheDocument()  // the cover slot shows its credit
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Dawn' } })
    fireEvent.change(screen.getByDisplayValue('The **boats**.'), { target: { value: 'New words.' } })
    fireEvent.click(screen.getByRole('button', { name: /Add a block/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Pull quote' }))
    expect(screen.getByLabelText('Pull quote block')).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Cover' })).not.toBeInTheDocument()  // there is one already

    await waitFor(() => expect(api.postHtml).toHaveBeenCalled(), { timeout: 2000 })
    const previewBody = api.postHtml.mock.calls.at(-1)![1] as { title: string; content: { blocks: StoryBlock[] } }
    expect(previewBody.title).toBe('Dawn')

    fireEvent.click(screen.getByRole('button', { name: /Publish/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const sent = api.put.mock.calls[0][1] as Record<string, unknown>
    expect(sent.title).toBe('Dawn')
    expect(sent.status).toBe('published')
    expect(sent.cover_asset_id).toBe('a-1')
    const blocks = (sent.content as { blocks: StoryBlock[] }).blocks
    expect(blocks[1]).toEqual({ type: 'text', md: 'New words.', dropcap: true, columns: 1 })
    expect(blocks[2].type).toBe('quote')
    expect(await screen.findByText('published')).toBeInTheDocument()
  })

  it('picks a picture from the library into a photo block', async () => {
    api.put.mockResolvedValue(post())
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await screen.findByDisplayValue('The harbour at dawn')
    fireEvent.click(screen.getByRole('button', { name: /Add a block/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Photo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose picture' }))
    const dialog = await screen.findByRole('dialog', { name: 'Choose a picture' })
    expect(dialog).toBeInTheDocument()
    // LibraryPanel lists the asset; opening it and choosing "Use this picture" fills the slot.
    fireEvent.click(await screen.findByRole('button', { name: /Photo: Ana Ruiz/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use this picture' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change picture' })).toBeInTheDocument()
  })

  it('applies an Assist headline and opens a suggested archive search', async () => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [ASSET] },
      '/library/search': { source: 'nasa', query: 'earth at night', page: 0, has_more: false, results: [] } })
    api.post.mockImplementation((_path: string, body: { action: string }) => Promise.resolve(body.action === 'headlines'
      ? { action: 'headlines', headlines: [{ title: 'Four a.m.', dek: 'Boats go out.', kicker: 'Dispatch' }] }
      : { action: 'search_terms', terms: [{ source: 'nasa', query: 'earth at night' }] }))
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await screen.findByDisplayValue('The harbour at dawn')
    fireEvent.click(screen.getByRole('button', { name: 'Assist' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use this' }))
    expect(screen.getByLabelText('Headline')).toHaveValue('Four a.m.')
    expect(screen.getByLabelText('Kicker')).toHaveValue('Dispatch')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()

    fireEvent.click(screen.getByRole('tab', { name: 'Find pictures' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Search' }))
    const dialog = await screen.findByRole('dialog', { name: 'Find pictures' })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/sites/s-1/library/search?source=nasa&q=earth+at+night&page=0'))
    expect(within(dialog).getByPlaceholderText(/Harbour at dawn/)).toHaveValue('earth at night')
  })

  it('removes and reorders blocks', async () => {
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await screen.findByDisplayValue('The harbour at dawn')
    fireEvent.click(screen.getByRole('button', { name: /Add a block/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Divider' }))
    const sections = () => screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'))
    expect(sections()).toEqual(['Cover block', 'Text block', 'Divider block'])
    fireEvent.click(screen.getAllByRole('button', { name: 'Move up' })[2])
    expect(sections()).toEqual(['Cover block', 'Divider block', 'Text block'])
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove block' })[1])
    expect(sections()).toEqual(['Cover block', 'Text block'])
  })

  it('offers to turn a plain post into a story', async () => {
    answer({ '/posts/p-1': post({ format: 'markdown', content: null, body: 'Old *words*.' }), '/stories/options': OPTIONS, '/assets': { assets: [] } })
    api.put.mockResolvedValue(post({ content: { blocks: [{ type: 'text', md: 'Old *words*.', dropcap: true, columns: 1 }] } }))
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    expect(await screen.findByText(/plain post written as Markdown/)).toBeInTheDocument()
    expect(api.postHtml).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Turn into a story' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/posts/p-1', { format: 'blocks' }))
    expect(await screen.findByDisplayValue('Old *words*.')).toBeInTheDocument()
  })

  it('shows a save failure and deletes after confirming', async () => {
    api.put.mockRejectedValue(new Error('A picture in this story isn’t in your library any more.'))
    api.delete.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await screen.findByDisplayValue('The harbour at dawn')
    fireEvent.click(screen.getByRole('button', { name: /Publish/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t in your library')
    fireEvent.click(screen.getByRole('button', { name: /Delete story/ }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sites/s-1/posts/p-1'))
    expect(await screen.findByText('stories list')).toBeInTheDocument()
  })

  it('switching layout on an empty story fills in that layout’s blocks', async () => {
    answer({ '/posts/p-1': post({ content: { blocks: [newBlock('cover'), newBlock('text')] } }), '/stories/options': OPTIONS, '/assets': { assets: [] } })
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    await screen.findByDisplayValue('The harbour at dawn')
    fireEvent.change(screen.getByLabelText('Layout'), { target: { value: 'photo_essay' } })
    expect(screen.getAllByRole('region').map((s) => s.getAttribute('aria-label'))).toEqual(['Cover block', 'Photo block', 'Text block'])
  })
})

describe('MagazineSettings', () => {
  it('loads, edits and saves', async () => {
    answer({ '/magazine': magazine(), '/stories/options': OPTIONS })
    api.put.mockResolvedValue(magazine({ topics: ['city', 'food'], masthead_style: 'display', front_at_root: true }))
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
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
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
    expect(await screen.findByText(/Your plan doesn’t include a magazine/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('topics from the list')
  })

  it('caps topics at five', async () => {
    const many = { ...OPTIONS, topics: ['a', 'b', 'c', 'd', 'e', 'f'].map((k) => ({ key: k, label: k.toUpperCase() })) }
    answer({ '/magazine': magazine({ topics: ['a', 'b', 'c', 'd', 'e'] }), '/stories/options': many })
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
    await screen.findByDisplayValue('Salt & Light')
    fireEvent.click(screen.getByRole('button', { name: 'F' }))
    expect(screen.getByRole('button', { name: 'F' })).toHaveAttribute('aria-pressed', 'false')
  })
})
