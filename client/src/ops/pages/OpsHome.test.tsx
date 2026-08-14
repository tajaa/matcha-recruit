import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkSurfaceProvider } from '../../work/routes/WorkSurfaceContext'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))

import OpsHome from './OpsHome'

describe('OpsHome', () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'admin' }, profile: null },
      hasFeature: () => false,
    })
  })

  it('shows all Ops capability cards to platform admins', () => {
    render(
      <MemoryRouter>
        <WorkSurfaceProvider value="matcha-ops">
          <OpsHome />
        </WorkSurfaceProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: /Events/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Inventory/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Schedule/ })).toBeInTheDocument()
  })

  it('still hides unentitled capabilities for ordinary clients', () => {
    useMeMock.mockReturnValue({
      me: { user: { role: 'client' }, profile: { enabled_features: {} } },
      hasFeature: () => false,
    })

    render(
      <MemoryRouter>
        <WorkSurfaceProvider value="matcha-ops">
          <OpsHome />
        </WorkSurfaceProvider>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: /Events/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Inventory/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Schedule/ })).not.toBeInTheDocument()
  })
})
