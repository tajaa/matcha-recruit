import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import manifest from '../../../../../server/app/cappe/services/magazine/studio/fonts_manifest.json'
import type { FaceBook } from '../../studio/fonts/faces'
import MagazineOnboarding from '../onboarding/MagazineOnboarding'
import { handleFrom } from './handles'
import Emails from '../emails/Emails'
import WritersLanding from './WritersLanding'
import WriterHome from './WriterHome'
import CappeSidebar from '../../components/CappeSidebar'
import type { CappeAccount, CappeIssue, CappePost } from '../../types'
import { CappeApiError } from '../../api'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const pricing = vi.hoisted(() => vi.fn())
const designs = vi.hoisted(() => ({ load: vi.fn(), ensure: vi.fn() }))
vi.mock('../../api', async (original) => ({ ...await original<object>(), cappeApi: api, cappeApiBase: '/api/cappe', fetchCappePricing: pricing, clearCappeTokens: vi.fn() }))
vi.mock('../../studio/fonts/faces', async (original) => ({ ...await original<object>(), loadManifest: designs.load }))
vi.mock('../../studio/compose/shaper', async (original) => ({ ...await original<object>(), loadHarfBuzz: async () => ({}) }))
vi.mock('../../studio/fonts/loader', () => ({
  browserWidth: vi.fn(),
  FontLoader: class {
    readonly book: FaceBook
    constructor(book: FaceBook) { this.book = book }
    ensureDoc = designs.ensure
    measure = { width: (c: { size: number }, t: string) => t.length * c.size / 2,
      metrics: (c: { size: number }) => ({ asc: c.size * 0.8, desc: c.size * 0.2, cap: c.size * 0.7 }) }
  },
}))
beforeEach(() => { vi.clearAllMocks(); designs.load.mockResolvedValue(manifest); designs.ensure.mockResolvedValue(undefined) })

const OPTIONS = {
  topics: [{ key: 'travel', label: 'Travel' }, { key: 'food', label: 'Food & drink' }, { key: 'art', label: 'Art' },
    { key: 'music', label: 'Music' }],
  mastheads: [{ key: 'classic', heading: 'Bodoni Moda', body: 'Spectral' }, { key: 'modern', heading: 'Archivo Black', body: 'Libre Franklin' }],
}

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.includes(k))
    return hit === undefined ? Promise.reject(new Error(`unexpected GET ${path}`)) : Promise.resolve(routes[hit])
  })
}

function mount(path: string, element: React.ReactElement, pattern: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
        <Route path="/cappe/sites/:siteId/stories" element={<p>the stories</p>} />
        <Route path="/cappe/studio/:siteId/story/:postId" element={<p>the first Studio draft</p>} />
        <Route path="/cappe/writer/new" element={<p>name your magazine</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('handles', () => {
  it('makes a handle from a name', () => {
    expect(handleFrom('The Harbour Review')).toBe('the-harbour-review')
    expect(handleFrom('  Café  Lumière! ')).toBe('cafe-lumiere')
    expect(handleFrom('x'.repeat(40))).toHaveLength(30)
  })
})

describe('MagazineOnboarding', () => {
  it('names the magazine, checks the address and creates it', async () => {
    answer({ '/magazine/options': OPTIONS, '/magazine/handle-available': { handle: 'the-harbour-review', available: true, reason: null } })
    api.post.mockResolvedValue({ site: { id: 's-9' }, post_id: 'p-9' })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'The Harbour Review' } })
    expect(screen.getByDisplayValue('the-harbour-review')).toBeInTheDocument()
    expect(await screen.findByText(/the-harbour-review\.gummfit\.com is yours to take/, {}, { timeout: 2000 })).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Optional details/))
    for (const t of ['Travel', 'Food & drink', 'Art', 'Music']) fireEvent.click(screen.getByRole('button', { name: t }))
    expect(screen.getByRole('button', { name: 'Music' })).toHaveAttribute('aria-pressed', 'false') // three at most
    fireEvent.click(screen.getByRole('button', { name: /Archivo Black/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose Maison' }))
    fireEvent.click(screen.getByRole('button', { name: /Open my first draft/ }))
    expect(await screen.findByText('the first Studio draft')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/magazine/quick-start', expect.objectContaining({
      name: 'The Harbour Review', handle: 'the-harbour-review', tagline: null, topics: ['travel', 'food', 'art'],
      masthead_style: 'modern', request_id: expect.any(String),
    }))
    const doc = api.post.mock.calls[0][1].doc
    expect(doc.pages).toHaveLength(10)
    expect(JSON.stringify(doc)).toContain('The Harbour Review')
    expect(JSON.stringify(doc)).toContain('Playfair Poster')
    expect(doc.items.filter((i: { kind: string }) => i.kind === 'image').every((i: { asset_id: string | null }) => !i.asset_id)).toBe(true)
    expect(JSON.stringify(doc)).not.toContain('starter-media')
  })

  it('says why an address can’t be had and won’t create it', async () => {
    answer({ '/magazine/options': OPTIONS, '/magazine/handle-available': { handle: 'www', available: false, reason: 'That address is reserved. Pick another.' } })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    fireEvent.change(screen.getByDisplayValue('harbour'), { target: { value: 'WWW' } })
    expect(await screen.findByText('That address is reserved. Pick another.', {}, { timeout: 2000 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Open my first draft/ })).toBeDisabled()
  })

  it('keeps the chosen design and request id after a failed response, and prevents double submits', async () => {
    answer({ '/magazine/options': OPTIONS, '/magazine/handle-available': { handle: 'harbour', available: true } })
    let reject!: (reason: Error) => void
    api.post.mockImplementationOnce(() => new Promise((_, no) => { reject = no }))
      .mockResolvedValue({ site: { id: 's-9' }, post_id: 'p-9' })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Choose Off Register' }))
    fireEvent.click(screen.getByRole('button', { name: /Next design page/ }))
    expect(screen.getByText('2 / 10 · Contents')).toBeInTheDocument()
    fireEvent.submit(screen.getByRole('form', { name: 'Your magazine' }))
    fireEvent.submit(screen.getByRole('form', { name: 'Your magazine' }))
    expect(api.post).toHaveBeenCalledTimes(1)
    await act(async () => reject(new Error('Connection lost. Try again.')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
    expect(screen.getByRole('button', { name: 'Choose Off Register' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: /Retry opening my draft/ }))
    expect(await screen.findByText('the first Studio draft')).toBeInTheDocument()
    expect(api.post.mock.calls[1][1]).toEqual(api.post.mock.calls[0][1])
  })

  it.each(['network', 'server'])('replays an unchanged pending request after a %s failure and a late taken-handle result', async (failure) => {
    let committed = false
    api.get.mockImplementation((path: string) => Promise.resolve(path === '/magazine/options' ? OPTIONS : {
      handle: 'harbour', available: !committed, reason: committed ? 'That address is taken. Pick another.' : null,
    }))
    api.post.mockImplementationOnce(async () => {
      committed = true
      throw failure === 'network' ? new Error('Response lost') : new CappeApiError('Response lost', undefined, 500)
    }).mockResolvedValue({ site: { id: 's-9' }, post_id: 'p-9' })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    await screen.findByRole('button', { name: 'Choose Quiet Form' })
    fireEvent.change(screen.getByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open my first draft' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Open my first draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
    await screen.findByText('That address is taken. Pick another.', {}, { timeout: 2000 })
    expect(screen.getByDisplayValue('Harbour')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Choose Maison' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Retry opening my draft' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry opening my draft' }))
    expect(await screen.findByText('the first Studio draft')).toBeInTheDocument()
    expect(api.post.mock.calls[1][1]).toEqual(api.post.mock.calls[0][1])
  })

  it.each([403, 409, 422, 429])('allows correcting setup after a definite HTTP %s rejection', async (status) => {
    answer({ '/magazine/options': OPTIONS, '/magazine/handle-available': { handle: 'harbour', available: true } })
    api.post.mockRejectedValueOnce(new CappeApiError('Correct your setup', undefined, status))
      .mockResolvedValue({ site: { id: 's-9' }, post_id: 'p-9' })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open my first draft' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Open my first draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Correct your setup')
    expect(screen.getByDisplayValue('Harbour')).toBeEnabled()
    fireEvent.change(screen.getByDisplayValue('Harbour'), { target: { value: 'Harbour Two' } })
    fireEvent.click(screen.getByRole('button', { name: 'Choose Maison' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open my first draft' }))
    expect(await screen.findByText('the first Studio draft')).toBeInTheDocument()
    expect(api.post.mock.calls[1][1].name).toBe('Harbour Two')
    expect(api.post.mock.calls[1][1].handle).toBe('harbour-two')
  })

  it.each([403, 409, 422, 429])('keeps recovery available after a lost response followed by HTTP %s', async (status) => {
    let committed = false
    api.get.mockImplementation((path: string) => Promise.resolve(path === '/magazine/options' ? OPTIONS : {
      handle: 'harbour', available: !committed, reason: committed ? 'That address is taken. Pick another.' : null,
    }))
    api.post.mockImplementationOnce(async () => { committed = true; throw new Error('Response lost') })
      .mockRejectedValueOnce(new CappeApiError('Retry interrupted', undefined, status))
      .mockResolvedValue({ site: { id: 's-9' }, post_id: 'p-9' })
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open my first draft' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Open my first draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
    await screen.findByText('That address is taken. Pick another.', {}, { timeout: 2000 })
    fireEvent.click(screen.getByRole('button', { name: 'Retry opening my draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Retry interrupted')
    expect(screen.getByDisplayValue('Harbour')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Retry opening my draft' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry opening my draft' }))
    expect(await screen.findByText('the first Studio draft')).toBeInTheDocument()
    expect(api.post.mock.calls[1][1]).toEqual(api.post.mock.calls[0][1])
    expect(api.post.mock.calls[2][1]).toEqual(api.post.mock.calls[0][1])
  })

  it('can reload failed design fonts without losing the magazine name', async () => {
    answer({ '/magazine/options': OPTIONS, '/magazine/handle-available': { handle: 'harbour', available: true } })
    designs.ensure.mockRejectedValueOnce(new Error('Font connection interrupted'))
    mount('/cappe/writer/new', <MagazineOnboarding />, '/cappe/writer/new')
    fireEvent.change(await screen.findByPlaceholderText('The Harbour Review'), { target: { value: 'Harbour' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Font connection interrupted')
    expect(screen.getByRole('button', { name: /Open my first draft/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Reload designs' }))
    expect(await screen.findByRole('button', { name: 'Choose Quiet Form' })).toBeInTheDocument()
    expect(screen.getByDisplayValue('Harbour')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /Open my first draft/ })).toBeEnabled())
  })
})

const story = (over: Partial<CappePost> = {}) => ({
  id: 'p-1', title: 'Before the town wakes', status: 'published', format: 'blocks', hidden: false, access: 'free', ...over,
}) as CappePost

const sentIssue: CappeIssue = {
  id: 'i-1', story_id: 'p-2', story_title: 'Low tide', subject: 'Low tide', status: 'sent', include_body: false,
  recipient_count: 40, failed_count: 2, sent_at: '2026-10-20T09:00:00Z', created_at: '2026-10-20T09:00:00Z',
}

describe('Emails', () => {
  it('sends a test, then the issue, and lists what went out', async () => {
    answer({
      '/issues': [sentIssue],
      '/posts': [story(), story({ id: 'p-2', title: 'Low tide' }), story({ id: 'p-3', title: 'Draft', status: 'draft' }),
        story({ id: 'p-4', title: 'Made in Studio', format: 'pages' }), story({ id: 'p-5', title: 'Plain post', format: 'markdown' })],
      '/subscribers': [{ status: 'subscribed' }, { status: 'subscribed' }, { status: 'pending_confirmation' }],
    })
    api.post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/test') ? { to: 'ana@example.com' }
      : { ...sentIssue, id: 'i-2', story_id: 'p-1', subject: 'Dawn', status: 'sending', recipient_count: 0, failed_count: 0 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('/cappe/sites/s-1/emails', <Emails />, '/cappe/sites/:siteId/emails')
    expect(await screen.findByText(/Sent to 40 · 2 didn’t go/)).toBeInTheDocument()
    const select = screen.getByLabelText('Story')
    // Stories made in Studio too; not plain posts.
    expect(Array.from((select as HTMLSelectElement).options).map((o) => o.text)).toEqual(['Before the town wakes', 'Made in Studio'])
    fireEvent.change(screen.getByPlaceholderText('Before the town wakes'), { target: { value: 'Dawn' } })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Send me a test/ }))
    expect(await screen.findByText('A test is on its way to ana@example.com.')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/posts/p-1/issue/test', { subject: 'Dawn', include_body: true })
    fireEvent.click(screen.getByRole('button', { name: 'Send to 2' }))
    expect(await screen.findByText(/Sending\. It can take/)).toBeInTheDocument()
    expect(api.post).toHaveBeenLastCalledWith('/sites/s-1/posts/p-1/issue', { subject: 'Dawn', include_body: true })
    expect(screen.getByText('Sending…')).toBeInTheDocument()
  })

  it('never sends a paid story whole, and waits for followers', async () => {
    answer({ '/issues': [], '/posts': [story({ access: 'paid' })], '/subscribers': [] })
    mount('/cappe/sites/s-1/emails', <Emails />, '/cappe/sites/:siteId/emails')
    expect(await screen.findByRole('checkbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'No followers yet' })).toBeDisabled()
  })

  it('shows a send that failed', async () => {
    answer({ '/issues': [], '/posts': [story()], '/subscribers': [{ status: 'subscribed' }] })
    api.post.mockRejectedValue(new Error('This story has already gone to your followers.'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('/cappe/sites/s-1/emails', <Emails />, '/cappe/sites/:siteId/emails')
    fireEvent.click(await screen.findByRole('button', { name: 'Send to 1' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already gone')
  })
})

describe('WritersLanding', () => {
  it('quotes the Writer plan from the pricing writers see', async () => {
    pricing.mockResolvedValue({ plans: [
      { code: 'free', name: 'Free', description: 'Draft', prices: [] },
      { code: 'writer', name: 'Writer', description: 'Publish', prices: [{ interval: 'month', unit_amount_cents: 900 }] },
    ], addons: [] })
    render(<MemoryRouter><WritersLanding /></MemoryRouter>)
    expect(await screen.findByText('$9/mo')).toBeInTheDocument()
    expect(screen.getByText(/\$9 a month when you publish/)).toBeInTheDocument()
    expect(pricing).toHaveBeenCalledWith('writer')
    expect(screen.getByRole('link', { name: 'Start your magazine' })).toHaveAttribute('href', '/cappe/magazines/signup')
  })
})

describe('WriterHome', () => {
  it('goes to the magazine, or to naming one', async () => {
    answer({ '/sites': [{ id: 's-1' }] })
    mount('/cappe/writer', <WriterHome />, '/cappe/writer')
    expect(await screen.findByText('the stories')).toBeInTheDocument()
    answer({ '/sites': [] })
    await act(async () => { mount('/cappe/writer', <WriterHome />, '/cappe/writer') })
    await waitFor(() => expect(screen.getByText('name your magazine')).toBeInTheDocument())
  })
})

describe('the writer sidebar', () => {
  it('is the magazine, not a shop', () => {
    answer({ '/threads': [] })
    const writer = { id: 'a-1', email: 'ana@example.com', name: 'Ana', plan: 'writer', account_type: 'writer' } as CappeAccount
    render(<MemoryRouter initialEntries={['/cappe/sites/0f0e0d0c-0b0a-0908-0706-050403020100/stories']}>
      <CappeSidebar account={writer} />
    </MemoryRouter>)
    expect(screen.getByText('Gummfit Magazines')).toBeInTheDocument()
    for (const label of ['Stories', 'Issues', 'Library', 'Followers', 'Emails', 'Magazine settings']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.queryByRole('link', { name: 'Storefront' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /All sites/ })).not.toBeInTheDocument()
  })
})
