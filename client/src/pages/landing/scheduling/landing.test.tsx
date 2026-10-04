import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import SchedulingLanding from '.'
import SchedulingHomeRedirect from './SchedulingHomeRedirect'
import { SCHEDULING_SIGNUP_PATH } from './signup'
import { landingMedia } from '../../../api/admin/landingMedia'
import { EMPTY_COMMERCIAL } from '../../../types/landingMedia'

// The hero animation is a lazy Remotion stage; the tabs are what's under test.
vi.mock('./Stage', () => ({ default: () => null }))
vi.mock('../../../api/admin/landingMedia', () => ({ landingMedia: { getPublic: vi.fn() } }))

const media = { hero_video_url: null, hero_poster_url: null, sizzle_videos: [], customer_logos: [], testimonials: [] }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(landingMedia.getPublic).mockResolvedValue(media)
  Element.prototype.scrollIntoView = vi.fn()
})

beforeAll(() => {
  // useInView (Reveal) observes sections as they scroll in; jsdom has no IntersectionObserver.
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return []
      }
    },
  )
  window.scrollTo = () => {}
  // useMedia (reduced motion / narrow) reads matchMedia; jsdom doesn't define it.
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
    onchange: null,
  })) as typeof window.matchMedia
})

function LocationProbe() {
  const { pathname, search, hash } = useLocation()
  const navigate = useNavigate()
  return <><output aria-label="Current URL">{pathname}{search}{hash}</output><button onClick={() => navigate(-1)}>Back</button></>
}

function renderAt(path: string, prior?: string) {
  return render(
    <MemoryRouter initialEntries={prior ? [prior, path] : [path]} initialIndex={prior ? 1 : 0}>
      <LocationProbe />
      <Routes>
        <Route path="/" element={<SchedulingLanding />} />
        <Route path="/incidents" element={<SchedulingLanding tab="incidents" />} />
        <Route path="/scheduling-v2" element={<SchedulingHomeRedirect />} />
      </Routes>
    </MemoryRouter>,
  )
}

// The tabs are lazy chunks: wait for the hero before asserting on the page.
async function renderLanding(path: string) {
  const view = renderAt(path)
  await screen.findByRole('heading', { level: 1 })
  return view
}

describe('home landing tabs', () => {
  it('home is the scheduling tab, with the product switch pointing at both tabs', async () => {
    await renderLanding('/')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/Next week’s schedule/)
    const tabs = within(screen.getByRole('navigation', { name: 'Product' }))
    expect(tabs.getByRole('link', { name: 'Scheduling' }).getAttribute('aria-current')).toBe('page')
    expect(tabs.getByRole('link', { name: 'Scheduling' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Matcha scheduling' })).toHaveAttribute('href', '/')
    expect(tabs.getByRole('link', { name: 'Incidents' }).getAttribute('href')).toBe('/incidents')
    expect(document.getElementById('draft')).not.toBeNull()
    expect(document.getElementById('triage')).toBeNull()
  })

  it('shows the complete buying guide at the indexable canonical home URL', async () => {
    await renderLanding('/')
    for (const id of ['recovery', 'setup', 'fit', 'value', 'pricing', 'questions']) {
      expect(document.getElementById(id)).not.toBeNull()
    }
    const guide = screen.getByRole('navigation', { name: 'Buying guide' })
    for (const link of within(guide).getAllByRole('link')) {
      expect(document.getElementById(link.getAttribute('href')!.slice(1))).not.toBeNull()
    }
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute('href', 'https://hey-matcha.com/')
    expect(document.querySelector('meta[name="robots"]')).toBeNull()
    expect(document.title).not.toMatch(/preview/i)
  })

  it('plays an enabled saved commercial on home', async () => {
    const url = 'https://media.example.com/film.mp4'
    vi.mocked(landingMedia.getPublic).mockResolvedValue({ ...media, scheduling_commercial: { ...EMPTY_COMMERCIAL, enabled: true, desktop_video_url: url } })
    renderAt('/')
    expect(await screen.findByLabelText('Matcha scheduling commercial')).toHaveAttribute('src', url)
    expect(screen.getByRole('button', { name: 'Skip to the schedule' })).toBeInTheDocument()
  })

  it('keeps home usable when media cannot load', async () => {
    vi.mocked(landingMedia.getPublic).mockRejectedValue(new Error('offline'))
    await renderLanding('/')
    expect(landingMedia.getPublic).toHaveBeenCalledOnce()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Next week’s schedule')
    expect(document.getElementById('pricing')).not.toBeNull()
  })

  it('redirects preview links with campaign parameters and section anchors without adding history', async () => {
    renderAt('/scheduling-v2?utm_source=review#pricing', '/incidents')
    await waitFor(() => expect(screen.getByLabelText('Current URL')).toHaveTextContent('/?utm_source=review#pricing'))
    await waitFor(() => expect(document.getElementById('pricing')).not.toBeNull())
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledOnce()
    expect(vi.mocked(Element.prototype.scrollIntoView).mock.contexts[0]).toBe(document.getElementById('pricing'))
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/closed case/i))
    expect(screen.getByLabelText('Current URL')).toHaveTextContent('/incidents')
  })

  it('scheduling is self-serve: every primary call to action starts an account', async () => {
    await renderLanding('/')
    // Top bar, hero and close. The walkthrough is still offered, as the
    // second choice rather than the only door in.
    const starts = screen.getAllByRole('link', { name: /Start now/ })
    expect(starts).toHaveLength(3)
    for (const link of starts) expect(link.getAttribute('href')).toBe(SCHEDULING_SIGNUP_PATH)
    expect(screen.getAllByRole('button', { name: /book a walkthrough/i }).length).toBeGreaterThanOrEqual(2)
  })

  it('the incidents tab keeps the walkthrough as its call to action', async () => {
    await renderLanding('/incidents')
    expect(screen.queryByRole('link', { name: /Start now/ })).toBeNull()
    expect(screen.getAllByRole('button', { name: /book a walkthrough/i }).length).toBeGreaterThanOrEqual(1)
    expect(landingMedia.getPublic).not.toHaveBeenCalled()
    expect(document.getElementById('pricing')).toBeNull()
  })

  it('/incidents is the incident workflow, in order, from report to signed copy', async () => {
    await renderLanding('/incidents')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/closed case/i)
    const tabs = within(screen.getByRole('navigation', { name: 'Product' }))
    expect(tabs.getByRole('link', { name: 'Incidents' }).getAttribute('aria-current')).toBe('page')
    expect(tabs.getByRole('link', { name: 'Scheduling' }).getAttribute('href')).toBe('/')
    const ids = ['report', 'triage', 'writeup', 'approve', 'signed']
    const found = ids.map((id) => document.getElementById(id))
    expect(found.every(Boolean)).toBe(true)
    // document order = timeline order, so the margin clock reads top to bottom
    for (let i = 1; i < found.length; i++) {
      expect(found[i - 1]!.compareDocumentPosition(found[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
    expect(document.getElementById('draft')).toBeNull()
  })

  it('every step in the top bar and margin clock has a section to scroll to', async () => {
    await renderLanding('/incidents')
    const links = Array.from(document.querySelectorAll('nav[aria-label="Page sections"] a[href^="#"]'))
    expect(links.length).toBe(5)
    for (const a of links) expect(document.getElementById(a.getAttribute('href')!.slice(1))).not.toBeNull()
  })
})
