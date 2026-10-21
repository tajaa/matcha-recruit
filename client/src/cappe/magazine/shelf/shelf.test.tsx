import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Shelf from './Shelf'
import ShelfMagazine from './ShelfMagazine'
import ShelfStory from './ShelfStory'
import ReaderLayout from './ReaderLayout'
import CappeLayout from '../../layout/CappeLayout'
import { magazineSlugFrom, readerMagazinePath, readerNext, readerStoryPath } from './readerPaths'
import { LINK_PREFIX } from '../reader/book'
import type { CappeReaderMagazine, CappeReaderStoryCard, CappeShelfMagazine } from '../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const token = vi.hoisted(() => ({ value: 'a' as string | null }))
const me = vi.hoisted(() => ({ account: null as null | Record<string, unknown>, loading: false }))
const followed = vi.hoisted(() => ({ value: null as string | null }))
vi.mock('../reader/book', async (importOriginal) => {
  const real = await importOriginal<typeof import('../reader/book')>()
  return { ...real, followedLink: (w: Window | null | undefined) => {
    const v = followed.value
    followed.value = null
    return v ?? real.followedLink(w)
  } }
})
vi.mock('../../api', () => ({
  cappeApi: api, clearCappeTokens: vi.fn(), getCappeToken: () => token.value,
}))
vi.mock('../../hooks/useCappeMe', () => ({ useCappeMe: () => me, invalidateCappeMeCache: vi.fn() }))

const story = (over: Partial<CappeReaderStoryCard> = {}): CappeReaderStoryCard => ({
  slug: 'low-tide', title: 'Low tide', kicker: 'Coast', excerpt: 'The water goes out.', topic: null, access: 'paid',
  published_at: '2026-10-20T09:00:00Z', reading_minutes: 4,
  cover: { url: 'https://cdn.test/960.webp', alt: 'Tide pools', credit: 'Photo: Ana' }, ...over,
})

const SUB = { id: 'sub-1', status: 'active', current_period_end: '2026-11-21T09:00:00Z', cancel_at_period_end: false,
  total_cents: 500, currency: 'USD' }

const held = (over: Partial<CappeShelfMagazine> = {}): CappeShelfMagazine => ({
  site_id: 's-1', slug: 'salt', name: 'Salt & Light', tagline: 'Sea stories', accent: '#0ea5e9',
  origin: 'https://salt.gummfit.test', live: true, subscription: SUB, comp: null, latest: story(), ...over,
})

const magazine = (over: Partial<CappeReaderMagazine> = {}): CappeReaderMagazine => ({
  site_id: 's-1', slug: 'salt', name: 'Salt & Light', tagline: 'Sea stories', accent: null,
  origin: 'https://salt.gummfit.test', price_cents: 500, currency: 'USD', paid_pitch: 'Every week.',
  taking_subscribers: true, has_access: false, subscription: null, comp: null, stories: [story()], has_more: false,
  page: 1, ...over,
})

function Where() {
  const loc = useLocation()
  return <p>at {loc.pathname}{loc.search}</p>
}

function mount(path: string, pattern: string, element: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  token.value = 'a'
  me.account = { id: 'a-1', email: 'rae@example.com', account_type: 'reader' }
  me.loading = false
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('reader paths', () => {
  it('reads a magazine from its handle, address or a link', () => {
    expect(magazineSlugFrom(' Salt ')).toBe('salt')
    expect(magazineSlugFrom('salt.gummfit.com')).toBe('salt')
    expect(magazineSlugFrom('https://salt.gummfit.com/stories/low-tide')).toBe('salt')
    expect(magazineSlugFrom('https://gummfit.com/cappe/reader/m/salt')).toBe('salt')
    expect(magazineSlugFrom('')).toBeNull()
    expect(magazineSlugFrom('not a magazine!')).toBeNull()
    expect(readerStoryPath('salt', 'low tide')).toBe('/cappe/reader/m/salt/low%20tide')
  })

  it('goes on after sign-in only within the dashboard', () => {
    expect(readerNext('/cappe/reader/m/salt?subscribed=1')).toBe('/cappe/reader/m/salt?subscribed=1')
    expect(readerNext('/cappe/readerx')).toBe('/cappe/reader')
    expect(readerNext('https://evil.test/cappe/reader')).toBe('/cappe/reader')
    expect(readerNext(null)).toBe('/cappe/reader')
  })
})

describe('the shell', () => {
  it('sends someone signed out to the reader sign-in and back', () => {
    token.value = null
    mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ReaderLayout />)
    expect(screen.getByText('at /cappe/reader/login?next=%2Fcappe%2Freader%2Fm%2Fsalt')).toBeInTheDocument()
  })

  it('keeps a reader out of the site builder', () => {
    mount('/cappe/sites', '/cappe/sites', <CappeLayout />)
    expect(screen.getByText('at /cappe/reader')).toBeInTheDocument()
  })
})

describe('the shelf', () => {
  it('lists each magazine with what the reader holds and its latest story', async () => {
    api.get.mockResolvedValue({ magazines: [held(), held({ site_id: 's-2', slug: 'ink', name: 'Ink', subscription: null,
      comp: { expires_at: null }, live: false, latest: null })] })
    mount('/cappe/reader', '/cappe/reader', <Shelf />)
    expect(await screen.findByRole('link', { name: 'Salt & Light' })).toHaveAttribute('href', readerMagazinePath('salt'))
    expect(screen.getByText(/^Renews/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Low tide/ })).toHaveAttribute('href', '/cappe/reader/m/salt/low-tide')
    expect(screen.getByText('Free, from the writer')).toBeInTheDocument()
    expect(screen.getByText(/isn’t up right now/)).toBeInTheDocument()
  })

  it('opens another magazine by its address', async () => {
    api.get.mockResolvedValue({ magazines: [] })
    mount('/cappe/reader', '/cappe/reader', <Shelf />)
    expect(await screen.findByText(/No magazines yet/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Open a magazine'), { target: { value: '!!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByRole('alert')).toHaveTextContent('like salt.gummfit.com')
    fireEvent.change(screen.getByLabelText('Open a magazine'), { target: { value: 'ink.gummfit.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByText('at /cappe/reader/m/ink')).toBeInTheDocument()
  })
})

describe('one magazine', () => {
  it('subscribes through Stripe and comes back here', async () => {
    api.get.mockResolvedValue(magazine())
    api.post.mockResolvedValue({ checkout_url: 'https://checkout.stripe.test/cs_1' })
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, origin: 'https://gummfit.test', assign })
    mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ShelfMagazine />)
    expect(await screen.findByText('Subscribe for $5 a month')).toBeInTheDocument()
    expect(screen.getByText('Every week.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Subscribe/ }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.stripe.test/cs_1'))
    expect(api.post).toHaveBeenCalledWith('/reader/magazines/salt/subscribe', {
      success_url: 'https://gummfit.test/cappe/reader/m/salt?subscribed=1',
      cancel_url: 'https://gummfit.test/cappe/reader/m/salt',
    })
  })

  it('cancels at the month’s end, and keeps it', async () => {
    api.get.mockResolvedValueOnce(magazine({ has_access: true, subscription: SUB }))
      .mockResolvedValueOnce(magazine({ has_access: true, subscription: { ...SUB, cancel_at_period_end: true } }))
      .mockResolvedValue(magazine({ has_access: true, subscription: SUB }))
    api.post.mockResolvedValue({ status: 'active', cancel_at_period_end: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ShelfMagazine />)
    expect(await screen.findByText('Subscribed · $5 a month')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByRole('button', { name: 'Keep it' })).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/reader/subscriptions/sub-1/cancel')
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(api.post).toHaveBeenLastCalledWith('/reader/subscriptions/sub-1/resume')
  })

  it('says what free months and a closed magazine mean', async () => {
    api.get.mockResolvedValue(magazine({ has_access: true, comp: { expires_at: null } }))
    const { unmount } = mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ShelfMagazine />)
    expect(await screen.findByText(/Free, from the writer. Every story is open to you./)).toBeInTheDocument()
    unmount()
    api.get.mockResolvedValue(magazine({ taking_subscribers: false, price_cents: null }))
    mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ShelfMagazine />)
    expect(await screen.findByText(/isn’t taking subscriptions/)).toBeInTheDocument()
  })

  it('waits for a new subscription to land after checkout', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    api.get.mockResolvedValueOnce(magazine()).mockResolvedValue(magazine({ has_access: true, subscription: SUB }))
    mount('/cappe/reader/m/salt?subscribed=1', '/cappe/reader/m/:slug', <ShelfMagazine />)
    expect(await screen.findByText('Finishing your subscription…')).toBeInTheDocument()
    await act(async () => { vi.advanceTimersByTime(2100) })
    expect(await screen.findByText('Subscribed · $5 a month')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('loads more stories', async () => {
    api.get.mockResolvedValueOnce(magazine({ has_more: true }))
      .mockResolvedValueOnce(magazine({ stories: [story({ slug: 'high-tide', title: 'High tide' })], page: 2 }))
    mount('/cappe/reader/m/salt', '/cappe/reader/m/:slug', <ShelfMagazine />)
    fireEvent.click(await screen.findByRole('button', { name: 'More stories' }))
    expect(await screen.findByText('High tide')).toBeInTheDocument()
    expect(api.get).toHaveBeenLastCalledWith('/reader/magazines/salt?page=2')
    expect(screen.queryByRole('button', { name: 'More stories' })).not.toBeInTheDocument()
  })
})

describe('reading a story', () => {
  it('shows the magazine’s page and points its links where they go', async () => {
    api.get.mockResolvedValue({ html: '<p>page</p>', paid: true, has_access: false, title: 'Low tide' })
    mount('/cappe/reader/m/salt/low-tide', '/cappe/reader/m/:slug/:story', <ShelfStory />)
    const frame = await screen.findByTitle('Low tide') as HTMLIFrameElement
    expect(frame.getAttribute('sandbox')).toBe('allow-same-origin allow-popups allow-popups-to-escape-sandbox')
    expect(api.get).toHaveBeenCalledWith('/reader/magazines/salt/stories/low-tide')
    const doc = frame.contentDocument!
    doc.head.innerHTML = '<link rel="canonical" href="https://salt.gummfit.test/stories/low-tide" />'
    doc.body.innerHTML = '<section><div data-mz-actions><noscript>Turn on JavaScript</noscript></div>'
      + '<p data-mz-alt>Read with a Gummfit reader account?</p></section>'
      + '<a href="/topics/coast">Coast</a><a href="https://example.com/x">elsewhere</a><a href="/stories/high-tide">Next</a>'
    fireEvent.load(frame)
    expect(doc.querySelector('[data-mz-alt]')).toBeNull()
    const href = (text: string) => Array.from(doc.querySelectorAll('a')).find((a) => a.textContent === text)!
    // Its own pages open on the magazine's site, the web in a new tab, and
    // a story or the paywall's button come back here.
    expect([href('Coast').getAttribute('href'), href('Coast').getAttribute('target')])
      .toEqual(['https://salt.gummfit.test/topics/coast', '_blank'])
    expect(href('elsewhere').getAttribute('target')).toBe('_blank')
    expect(href('Next').getAttribute('href')).toBe(`${LINK_PREFIX}%2Fstories%2Fhigh-tide`)
    expect(href('Subscribe to read on').getAttribute('href')).toBe(`${LINK_PREFIX}%2Fmagazine`)
    followed.value = '/magazine'
    fireEvent.load(frame)
    expect(await screen.findByText('at /cappe/reader/m/salt')).toBeInTheDocument()
  })

  it('opens the next story here', async () => {
    api.get.mockResolvedValue({ html: '<p>page</p>', paid: false, has_access: true, title: 'Low tide' })
    mount('/cappe/reader/m/salt/low-tide', '/cappe/reader/m/:slug/:story', <ShelfStory />)
    const frame = await screen.findByTitle('Low tide') as HTMLIFrameElement
    frame.contentDocument!.body.innerHTML = '<a href="/stories/high-tide">Next</a>'
    fireEvent.load(frame)
    followed.value = '/stories/high-tide'
    fireEvent.load(frame)
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/reader/magazines/salt/stories/high-tide'))
  })

  it('says when it can’t', async () => {
    api.get.mockRejectedValue(new Error('Story not found'))
    mount('/cappe/reader/m/salt/nope', '/cappe/reader/m/:slug/:story', <ShelfStory />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Story not found')
  })
})
