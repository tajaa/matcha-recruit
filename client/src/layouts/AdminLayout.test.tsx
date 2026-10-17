import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ADMIN_AREAS, findAdminPage } from '../components/admin/adminNavigation'
import { AdminPageHeader } from '../components/admin/AdminPageHeader'
import AdminCategoryPage from '../pages/admin/AdminCategoryPage'
import AdminLayout from './AdminLayout'

function CurrentPage() {
  const location = useLocation()
  const active = findAdminPage(location.pathname)
  return <><AdminPageHeader title={active?.page.label ?? 'Current tool'} /><p>{location.pathname + location.search + location.hash}</p></>
}

function renderPage(pathname: string) {
  return render(<MemoryRouter initialEntries={[pathname]}><Routes><Route element={<AdminLayout />}>
    <Route path="/admin/areas/:category" element={<AdminCategoryPage />} />
    <Route path="/admin/*" element={<CurrentPage />} />
  </Route></Routes></MemoryRouter>)
}

const directories = ADMIN_AREAS.filter((area) => area.to.startsWith('/admin/areas/'))

describe('AdminLayout and category directories', () => {
  it.each(directories)('shows every $label tool by name on its category page', (area) => {
    renderPage(area.to)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(area.label)
    expect(screen.getByText(area.description)).toBeInTheDocument()
    const tools = screen.getByRole('navigation', { name: `${area.label} tools` })
    expect(within(tools).getAllByRole('link')).toHaveLength(area.pages.length)
    for (const page of area.pages) {
      expect(within(tools).getByRole('link', { name: page.label })).toHaveAttribute('href', page.to)
      expect(within(tools).getByText(page.description)).toBeInTheDocument()
    }
  })

  it.each(directories.flatMap((area) => area.pages.map((page) => ({ area, page }))))('opens $page.to as its own page and returns to its category', async ({ area, page }) => {
    renderPage(area.to)
    const tools = screen.getByRole('navigation', { name: `${area.label} tools` })
    await userEvent.click(within(tools).getByRole('link', { name: page.label }))
    expect(screen.getByText(page.to)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(page.label)
    expect(screen.queryByRole('navigation', { name: /workspaces|pages/ })).not.toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole('link', { name: area.label }))
    expect(screen.getByRole('navigation', { name: `${area.label} tools` })).toBeInTheDocument()
  })

  it('keeps tool and category links available on a detail URL', () => {
    renderPage('/admin/companies/company-1')
    const breadcrumb = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(within(breadcrumb).getByRole('link', { name: 'Customers' })).toHaveAttribute('href', '/admin/areas/customers')
    expect(within(breadcrumb).getByRole('link', { name: 'Companies' })).toHaveAttribute('href', '/admin/companies')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Companies')
  })

  it('preserves direct-link filters and anchors', () => {
    renderPage('/admin/studio?view=library&state=CA#requirement')
    expect(screen.getByText('/admin/studio?view=library&state=CA#requirement')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Compliance Studio')
  })

  it('opens Updates directly without repeating its breadcrumb', () => {
    renderPage('/admin/updates')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Updates')
    expect(within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getAllByText('Updates')).toHaveLength(1)
  })

  it('recovers an unknown category to the customer directory', () => {
    renderPage('/admin/areas/unknown')
    expect(screen.getByRole('navigation', { name: 'Customers tools' })).toBeInTheDocument()
  })
})
