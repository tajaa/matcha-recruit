import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ADMIN_AREAS } from '../components/admin/adminNavigation'
import { AdminPageHeader } from '../components/admin/AdminPageHeader'
import AdminLayout from './AdminLayout'

function CurrentPage() {
  const location = useLocation()
  return <><AdminPageHeader title="Current tool" /><p>{location.pathname + location.search + location.hash}</p></>
}

function renderPage(pathname: string) {
  return render(<MemoryRouter initialEntries={[pathname]}><Routes><Route element={<AdminLayout />}><Route path="/admin/*" element={<CurrentPage />} /></Route></Routes></MemoryRouter>)
}

describe('AdminLayout', () => {
  it.each(ADMIN_AREAS.flatMap((area) => area.pages.flatMap((page) => (page.tabs ?? [page]).map((tab) => ({ area, page, tab })))))('keeps $tab.to reachable in its workspace', ({ area, page, tab }) => {
    renderPage(tab.to)
    expect(screen.getByText(tab.to)).toBeInTheDocument()
    if (area.pages.length > 1) {
      const nav = screen.getByRole('navigation', { name: `${area.label} workspaces` })
      expect(within(nav).getAllByRole('link')).toHaveLength(area.pages.length)
      expect(within(nav).getByRole('link', { name: page.label })).toHaveAttribute('aria-current', 'page')
    }
    if (page.tabs) {
      const nav = screen.getByRole('navigation', { name: `${page.label} pages` })
      expect(within(nav).getAllByRole('link')).toHaveLength(page.tabs.length)
      expect(within(nav).getByRole('link', { name: tab.label })).toHaveAttribute('aria-current', 'page')
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(page.label)
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Current tool')
    } else expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Current tool')
  })

  it('selects a parent tool on a detail URL and navigates between account tools', async () => {
    renderPage('/admin/companies/company-1')
    const nav = screen.getByRole('navigation', { name: 'Accounts pages' })
    expect(within(nav).getByRole('link', { name: 'Businesses' })).toHaveAttribute('aria-current', 'page')
    await userEvent.click(within(nav).getByRole('link', { name: 'Feature access' }))
    expect(screen.getByText('/admin/features')).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Feature access' })).toHaveAttribute('aria-current', 'page')
  })

  it('preserves direct-link filters and anchors', () => {
    renderPage('/admin/studio?view=library&state=CA#requirement')
    expect(screen.getByText('/admin/studio?view=library&state=CA#requirement')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Studio' })).toHaveAttribute('aria-current', 'page')
  })
})
