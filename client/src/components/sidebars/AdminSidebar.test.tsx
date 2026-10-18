import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ADMIN_AREAS } from '../admin/adminNavigation'
import AdminLayout from '../../layouts/AdminLayout'
import AdminCategoryPage from '../../pages/admin/AdminCategoryPage'
import AdminSidebar from './AdminSidebar'

vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ me: null, hasFeature: () => false, isBetaFeature: () => false }) }))

function renderPage(pathname: string) {
  return render(<MemoryRouter initialEntries={[pathname]}>
    <AdminSidebar />
    <Routes><Route element={<AdminLayout />}>
      <Route path="/admin/areas/:category" element={<AdminCategoryPage />} />
      <Route path="/admin/*" element={<h1>Tool page</h1>} />
    </Route></Routes>
  </MemoryRouter>)
}

describe('AdminSidebar', () => {
  it('keeps admin dark only without a theme switch', () => {
    renderPage('/admin/areas/customers')
    expect(screen.queryByRole('button', { name: /^(Light|Dark) mode$/ })).not.toBeInTheDocument()
  })

  it.each(ADMIN_AREAS.flatMap((area) => area.pages.map((page) => ({ area, page }))))('selects $area.label on $page.to while keeping the category destination', ({ area, page }) => {
    renderPage(`${page.to}/detail`)
    const sidebar = screen.getByRole('complementary')
    const active = within(sidebar).getByRole('link', { name: area.label })
    expect(active).toHaveAttribute('href', area.to)
    expect(active).toHaveAttribute('aria-current', 'page')
    expect(within(sidebar).getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page')).toHaveLength(1)
  })

  it.each(ADMIN_AREAS.filter((area) => area.to.startsWith('/admin/areas/')))('opens the $label directory when its active category is clicked', async (area) => {
    renderPage(area.pages[0].to)
    await userEvent.click(within(screen.getByRole('complementary')).getByRole('link', { name: area.label }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(area.label)
    expect(screen.getByRole('navigation', { name: `${area.label} tools` })).toBeInTheDocument()
    expect(within(screen.getByRole('complementary')).getByRole('link', { name: area.label })).toHaveAttribute('aria-current', 'page')
  })

  it('does not select a category for a partial tool path', () => {
    renderPage('/admin/newsletters')
    expect(within(screen.getByRole('complementary')).getAllByRole('link').some((link) => link.getAttribute('aria-current') === 'page')).toBe(false)
  })
})
