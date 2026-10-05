import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeLayout from './CappeLayout'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({
  cappeApi: api,
  getCappeToken: () => 'token',
  clearCappeTokens: vi.fn(),
}))
vi.mock('../hooks/useCappeMe', () => ({
  useCappeMe: () => ({ account: { name: 'Pat', email: 'owner@example.com', plan: 'free', account_type: 'business' }, loading: false }),
  invalidateCappeMeCache: vi.fn(),
}))

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<CappeLayout />}>
          <Route path="/cappe/sites" element={<p>sites page</p>} />
          <Route path="/cappe/templates" element={<p>templates page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

const drawer = () => document.getElementById('cappe-sidebar') as HTMLElement
const isOpen = () => drawer().className.split(' ').includes('translate-x-0')
const toggle = () => screen.getByRole('button', { name: /menu/ })

beforeEach(() => { api.get.mockReset().mockResolvedValue([]) })

describe('CappeLayout on a phone', () => {
  it('keeps the navigation closed, and out of the tab order, until asked', () => {
    renderAt('/cappe/sites')
    expect(isOpen()).toBe(false)
    expect(drawer().className).toContain('invisible')
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(toggle()).toHaveAttribute('aria-controls', 'cappe-sidebar')
    // The rail is unconditional from md up.
    expect(drawer().className).toContain('md:visible')
    expect(drawer().className).toContain('md:translate-x-0')
  })

  it('opens from the menu button and closes on Escape', () => {
    renderAt('/cappe/sites')
    fireEvent.click(toggle())
    expect(isOpen()).toBe(true)
    expect(toggle()).toHaveAccessibleName('Close menu')
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(isOpen()).toBe(false)
  })

  it('closes when a link is followed', () => {
    renderAt('/cappe/sites')
    fireEvent.click(toggle())
    fireEvent.click(within(drawer()).getByRole('link', { name: 'Templates' }))

    expect(screen.getByText('templates page')).toBeInTheDocument()
    expect(isOpen()).toBe(false)
  })

  it('closes when the page behind it is tapped', () => {
    renderAt('/cappe/sites')
    fireEvent.click(toggle())
    const backdrop = document.querySelector('[aria-hidden="true"].fixed') as HTMLElement
    fireEvent.click(backdrop)
    expect(isOpen()).toBe(false)
  })

  it('links to plan and billing from the drawer', () => {
    renderAt('/cappe/sites')
    expect(within(drawer()).getByRole('link', { name: 'Plan & billing' })).toHaveAttribute('href', '/cappe/billing')
  })
})
