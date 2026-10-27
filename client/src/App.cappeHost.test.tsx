import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

// gummfit.com/login used to open Matcha's sign-in: Matcha's explicit route
// outranked the Cappe "/*" splat. On the Cappe host those paths are Gummfit's.
vi.mock('./cappe/host', async (importOriginal) => ({ ...(await importOriginal<object>()), isCappeHost: true }))
vi.mock('./cappe/routes', () => ({
  default: function GummfitRoutes() {
    const location = useLocation()
    return <p>gummfit routes at {`${location.pathname}${location.search}${location.hash}`}</p>
  },
}))
vi.mock('./routes/GummfitAdminRoutes', () => ({ default: () => <p>gummfit staff admin</p> }))
vi.mock('./components/shared/RouteTracker', () => ({ default: () => null }))

import App from './App'

describe('App on the Gummfit host', () => {
  it.each(['/login', '/signup', '/reset-password'])('hands %s to Gummfit', async (path) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
    expect(await screen.findByText(`gummfit routes at ${path}`)).toBeInTheDocument()
  })

  it.each([
    ['/gummfit/login', '/login'],
    ['/gummfit/website-setup?plan=pro&interval=month', '/website-setup?plan=pro&interval=month'],
    ['/gummfit/creators/login#top', '/creators/login#top'],
    ['/gummfit', '/'],
  ])('redirects the old %s link to %s', async (from, to) => {
    render(<MemoryRouter initialEntries={[from]}><App /></MemoryRouter>)
    expect(await screen.findByText(`gummfit routes at ${to}`)).toBeInTheDocument()
  })

  it.each(['/gummfit/admin', '/gummfit/admin/login', '/gummfit/admin/models'])('mounts the staff console at %s ahead of the customer tree', async (path) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
    expect(await screen.findByText('gummfit staff admin')).toBeInTheDocument()
    expect(screen.queryByText(/gummfit routes/)).not.toBeInTheDocument()
  })
})
