import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import SchedulingLanding from '.'

// The hero animation is a lazy Remotion stage; the tabs are what's under test.
vi.mock('./Stage', () => ({ default: () => null }))

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

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<SchedulingLanding />} />
        <Route path="/incidents" element={<SchedulingLanding tab="incidents" />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('home landing tabs', () => {
  it('home is the scheduling tab, with the product switch pointing at both tabs', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/Next week’s schedule/)
    const tabs = within(screen.getByRole('navigation', { name: 'Product' }))
    expect(tabs.getByRole('link', { name: 'Scheduling' }).getAttribute('aria-current')).toBe('page')
    expect(tabs.getByRole('link', { name: 'Incidents' }).getAttribute('href')).toBe('/incidents')
    expect(document.getElementById('draft')).not.toBeNull()
    expect(document.getElementById('triage')).toBeNull()
  })

  it('/incidents is the incident workflow, in order, from report to signed copy', () => {
    renderAt('/incidents')
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

  it('every step in the top bar and margin clock has a section to scroll to', () => {
    renderAt('/incidents')
    const links = Array.from(document.querySelectorAll('nav[aria-label="Page sections"] a[href^="#"]'))
    expect(links.length).toBe(5)
    for (const a of links) expect(document.getElementById(a.getAttribute('href')!.slice(1))).not.toBeNull()
  })
})
