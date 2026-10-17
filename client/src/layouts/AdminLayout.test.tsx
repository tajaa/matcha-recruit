import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ADMIN_AREAS } from '../components/admin/adminNavigation'
import AdminLayout from './AdminLayout'

function CurrentPage() {
  return <p>{useLocation().pathname}</p>
}

function renderPage(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/admin/*" element={<CurrentPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminLayout', () => {
  it.each(ADMIN_AREAS.flatMap((area) => area.pages.map((page) => ({ area, page }))))(
    'exposes the correct sibling pages at $page.to', ({ area, page }) => {
      renderPage(page.to)
      expect(screen.getByText(page.to)).toBeInTheDocument()
      if (area.pages.length === 1) {
        expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
        return
      }
      const nav = screen.getByRole('navigation', { name: `${area.label} pages` })
      expect(within(nav).getAllByRole('link')).toHaveLength(area.pages.length)
      expect(within(nav).getByRole('link', { name: page.label })).toHaveAttribute('aria-current', 'page')
    },
  )

  it('selects a parent page on a direct detail URL and navigates between siblings', async () => {
    renderPage('/admin/companies/company-1')
    const nav = screen.getByRole('navigation', { name: 'Customers pages' })
    expect(within(nav).getByRole('link', { name: 'Companies' })).toHaveAttribute('aria-current', 'page')
    await userEvent.click(within(nav).getByRole('link', { name: 'Test accounts' }))
    expect(screen.getByText('/admin/test-accounts')).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Test accounts' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Companies' })).not.toHaveAttribute('aria-current')
  })
})
