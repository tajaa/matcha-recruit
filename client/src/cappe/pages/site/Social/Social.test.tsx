import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Social from './index'
import type {
  CappeSocialConnection, CappeSocialInboxItem, CappeSocialOverview, CappeSocialPost, CappeSocialSettings,
} from '../../../types'

const api = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(),
}))
vi.mock('../../../api', () => ({ cappeApi: api }))

const CONN: CappeSocialConnection = {
  id: 'c-1', platform: 'instagram', external_id: 'ig1', handle: 'pocoffee', display_name: 'pocoffee', avatar_url: null,
  status: 'connected', last_error: null, followers_count: 812, metrics: {}, metrics_at: null, token_expires_at: null,
  connected_at: '2026-10-01T00:00:00Z',
}
const SETTINGS: CappeSocialSettings = {
  autoreply_mode: 'review', reply_to_comments: true, reply_to_messages: true, tone: 'friendly', business_facts: '',
  signature: null, default_hashtags: [], max_auto_per_hour: 20, escalate_words: [], autoreply_available: true,
  video_available: false, ai_available: true,
}
const OVERVIEW: CappeSocialOverview = {
  connections: 1, scheduled: 2, published_30d: 5, inbox_new: 1, drafts_waiting: 0,
  followers: [{ platform: 'instagram', handle: 'pocoffee', followers_count: 812 }], autoreply_mode: 'review',
  meta_configured: true, ai_available: true,
}
const ITEM: CappeSocialInboxItem = {
  id: 'i-1', connection_id: 'c-1', platform: 'instagram', handle: 'pocoffee', kind: 'comment', external_id: 'x',
  external_parent_id: null, author_name: 'maya', text: 'Do you have oat milk?', received_at: '2026-10-20T10:00:00Z',
  status: 'drafted', classification: { intent: 'product_question' },
  replies: [{ id: 'r-1', body: 'Yes — oat milk is free!', mode: 'approved', status: 'draft', model: 'claude-haiku-5-5',
    grounding: { facts_used: ["Owner's notes: Oat milk is free."] }, external_reply_id: null, error: null,
    created_at: '2026-10-20T10:00:05Z', sent_at: null }],
}
const POST: CappeSocialPost = {
  id: 'p-1', site_id: 's-1', caption: 'Fresh roast', media: [{ url: 'https://cdn.example.test/a.jpg', kind: 'image' }],
  link_url: null, product_id: null, status: 'scheduled', scheduled_at: '2026-10-22T16:00:00Z', published_at: null,
  ai_meta: {}, created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z',
  targets: [{ id: 't-1', connection_id: 'c-1', platform: 'instagram', handle: 'pocoffee', status: 'pending',
    external_post_id: null, permalink: null, error: null, attempts: 0, published_at: null, metrics: {} }],
}

function answer(connections: CappeSocialConnection[] = [CONN]) {
  return (path: string) => {
    if (path.endsWith('/social/connections')) return Promise.resolve({ configured: true, connections })
    if (path.endsWith('/social/settings')) return Promise.resolve(SETTINGS)
    if (path.endsWith('/social/overview')) return Promise.resolve(OVERVIEW)
    if (path.includes('/social/inbox')) return Promise.resolve([ITEM])
    if (path.includes('/social/posts')) return Promise.resolve([POST])
    if (path.endsWith('/products')) return Promise.resolve([])
    return Promise.reject(new Error(`unexpected ${path}`))
  }
}

function load(url = '/sites/s-1/social', connections?: CappeSocialConnection[]) {
  api.get.mockImplementation(answer(connections))
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="/sites/:siteId/social" element={<Social />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
})

describe('Social', () => {
  it('opens on Create with the chat, and the form is one click away', async () => {
    load()
    expect(await screen.findByLabelText('Message')).toBeInTheDocument()
    expect(screen.getByText('Posted (30 days)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Form' }))
    expect(await screen.findByText(/Drop photos here/)).toBeInTheDocument()
    expect(screen.getByLabelText('Choose photos')).toHaveAttribute('multiple')
  })

  it('sends a new owner to connect their accounts first', async () => {
    load('/sites/s-1/social', [])
    expect(await screen.findByRole('button', { name: 'Connect Instagram & Facebook' })).toBeInTheDocument()
  })

  it('reports the OAuth round trip once', async () => {
    load('/sites/s-1/social?social_error=User%20denied')
    expect(await screen.findByText('Couldn’t connect: User denied')).toBeInTheDocument()
  })

  it('saves a caption-only draft to no account', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: 'Form' }))
    fireEvent.change(await screen.findByLabelText('Caption'), { target: { value: 'Back Monday!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save as draft' }))
    api.post.mockResolvedValue({ ...POST, status: 'draft' })
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    const [path, body] = api.post.mock.calls[0]
    expect(path).toBe('/sites/s-1/social/posts')
    expect(body).toMatchObject({ caption: 'Back Monday!', media: [], connection_ids: ['c-1'], scheduled_at: null })
  })

  it('will not save an empty post', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: 'Form' }))
    await screen.findByLabelText('Caption')
    expect(screen.getByRole('button', { name: 'Schedule' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Schedule post' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Drop a photo or write a caption first')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('sends an approved draft unedited, by its id', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: /^Inbox/ }))
    const box = await screen.findByLabelText('Your reply')
    expect(box).toHaveValue('Yes — oat milk is free!')
    expect(screen.getByText('Based on')).toBeInTheDocument()
    api.post.mockResolvedValue({ ...ITEM, status: 'replied', replies: [{ ...ITEM.replies[0], status: 'sent' }] })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/social/inbox/i-1/reply',
      { body: 'Yes — oat milk is free!', reply_id: 'r-1' }))
    expect(await screen.findByText('You’re all caught up.')).toBeInTheDocument()
  })

  it('lists upcoming posts with where they go', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: /^Queue/ }))
    const card = (await screen.findByText('Fresh roast')).closest('div.rounded-2xl') as HTMLElement
    expect(within(card).getByText('scheduled')).toBeInTheDocument()
    expect(within(card).getByText('@pocoffee')).toBeInTheDocument()
  })

  it('keeps AI replies locked on a plan without them', async () => {
    api.get.mockImplementation((path: string) => path.endsWith('/social/settings')
      ? Promise.resolve({ ...SETTINGS, autoreply_mode: 'off', autoreply_available: false })
      : answer()(path))
    render(
      <MemoryRouter initialEntries={['/sites/s-1/social']}>
        <Routes><Route path="/sites/:siteId/social" element={<Social />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Accounts & AI' }))
    expect(await screen.findByText('AI replies come with the Business and Creator plans.')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Answer simple questions/ })).toBeDisabled()
  })

  it('shows Saved after saving AI reply settings', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: 'Accounts & AI' }))
    api.put.mockResolvedValue({ ...SETTINGS, tone: 'playful' })
    fireEvent.change(await screen.findByLabelText('Voice'), { target: { value: 'playful' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
    expect(api.put.mock.calls[0][1]).toMatchObject({ tone: 'playful', autoreply_mode: 'review' })
  })

  it('takes a dropped video, uploads it straight to storage and posts it by its asset', async () => {
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:clip'), revokeObjectURL: vi.fn() }))
    class Xhr {
      status = 204
      upload = {}
      onload?: () => void
      open() {}
      send() { this.onload?.() }
    }
    vi.stubGlobal('XMLHttpRequest', Xhr)
    api.get.mockImplementation((path: string) => path.endsWith('/social/settings')
      ? Promise.resolve({ ...SETTINGS, video_available: true })
      : answer()(path))
    api.post.mockImplementation((path: string) => {
      if (path.endsWith('/assets/presign')) {
        return Promise.resolve({ asset_id: 'a-1', upload_url: 'https://bucket.example.test/', fields: {}, max_bytes: 1 })
      }
      if (path.endsWith('/complete')) {
        return Promise.resolve({ id: 'a-1', status: 'rendering', frames: [], trimmed: false, error: null })
      }
      return Promise.resolve({ ...POST, status: 'rendering' })
    })
    render(
      <MemoryRouter initialEntries={['/sites/s-1/social']}>
        <Routes><Route path="/sites/:siteId/social" element={<Social />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Form' }))
    expect(await screen.findByText(/Drop photos or videos here/)).toBeInTheDocument()
    const clip = new File([new Uint8Array(8)], 'latte.mov', { type: 'video/quicktime' })
    fireEvent.change(screen.getByLabelText('Choose photos or videos'), { target: { files: [clip] } })
    expect(await screen.findByText('Preparing…')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule post' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/social/posts', expect.objectContaining({
      media: [{ kind: 'video', asset_id: 'a-1', alt: null }],
    })))
    expect(await screen.findByText(/Videos go out once they’re ready/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('says video needs a paid plan instead of uploading it', async () => {
    load()
    fireEvent.click(await screen.findByRole('button', { name: 'Form' }))
    await screen.findByText(/Drop photos here/)
    const clip = new File([new Uint8Array(8)], 'latte.mp4', { type: 'video/mp4' })
    fireEvent.change(screen.getByLabelText('Choose photos'), { target: { files: [clip] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Video posts are part of the Business, Pro and Creator plans.')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows a video post being prepared and one Instagram is processing', async () => {
    const video = { kind: 'video' as const, asset_id: 'a-1', poster: 'https://cdn.example.test/f.jpg' }
    api.get.mockImplementation((path: string) => path.includes('/social/posts')
      ? Promise.resolve([
        { ...POST, id: 'p-2', caption: 'Latte art', status: 'rendering', media: [video] },
        { ...POST, id: 'p-3', caption: 'Pour over', status: 'publishing', media: [video],
          targets: [{ ...POST.targets[0], phase: 'instagram_processing' }] },
      ])
      : answer()(path))
    render(
      <MemoryRouter initialEntries={['/sites/s-1/social']}>
        <Routes><Route path="/sites/:siteId/social" element={<Social />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /^Queue/ }))
    const card = (await screen.findByText('Latte art')).closest('div.rounded-2xl') as HTMLElement
    expect(within(card).getByText('preparing video')).toBeInTheDocument()
    expect(card.querySelector('img')).toHaveAttribute('src', 'https://cdn.example.test/f.jpg')
    expect(within(card).getByLabelText('Video')).toBeInTheDocument()
    expect(screen.getByText(/Instagram is processing the video/)).toBeInTheDocument()
  })

  it('offers a retry on a post one network took and another did not', async () => {
    api.get.mockImplementation((path: string) => path.includes('/social/posts')
      ? Promise.resolve([{ ...POST, status: 'partial', targets: [
        { ...POST.targets[0], status: 'published' },
        { ...POST.targets[0], id: 't-2', platform: 'facebook', handle: null, status: 'failed', error: 'Meta: down' },
      ] }])
      : answer()(path))
    render(
      <MemoryRouter initialEntries={['/sites/s-1/social']}>
        <Routes><Route path="/sites/:siteId/social" element={<Social />} /></Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /^Queue/ }))
    fireEvent.click(await screen.findByRole('button', { name: /^Posted/ }))
    expect(await screen.findByTitle('Retry where it failed')).toBeInTheDocument()
    expect(screen.getByText('Meta: down')).toBeInTheDocument()
  })
})
