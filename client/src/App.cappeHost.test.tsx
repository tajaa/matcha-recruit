import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

// gummfit.com/login used to open Matcha's sign-in: Matcha's explicit route
// outranked the Cappe "/*" splat. On the Cappe host those paths are Gummfit's.
vi.mock('./cappe/host', () => ({ isCappeHost: true, CAPPE_HOST: 'gummfit.com' }))
vi.mock('./cappe/routes', () => ({ default: () => <p>gummfit routes</p> }))
vi.mock('./routes/GummfitAdminRoutes', () => ({ default: () => <p>gummfit staff admin</p> }))
vi.mock('./components/shared/RouteTracker', () => ({ default: () => null }))

import App from './App'

describe('App on the Gummfit host', () => {
  it.each(['/login', '/signup', '/reset-password'])('hands %s to Gummfit', async (path) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
    expect(await screen.findByText('gummfit routes')).toBeInTheDocument()
  })

  it.each(['/gummfit/admin', '/gummfit/admin/login', '/gummfit/admin/models'])('mounts the staff console at %s ahead of the customer tree', async (path) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
    expect(await screen.findByText('gummfit staff admin')).toBeInTheDocument()
    expect(screen.queryByText('gummfit routes')).not.toBeInTheDocument()
  })
})
