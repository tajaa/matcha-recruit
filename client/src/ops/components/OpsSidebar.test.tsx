import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkSurfaceProvider } from '../../work/routes/WorkSurfaceContext'

const { useMeMock, listChannelsMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  listChannelsMock: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../work/api/channels', () => ({ listChannels: listChannelsMock }))

import OpsSidebar from './OpsSidebar'

describe('OpsSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listChannelsMock.mockReturnValue(new Promise(() => {}))
    useMeMock.mockReturnValue({
      me: { user: { role: 'admin' }, profile: null },
      hasFeature: () => false,
    })
  })

  it('shows admin-only Ops capabilities without company flags', () => {
    render(
      <MemoryRouter initialEntries={['/ops']}>
        <WorkSurfaceProvider value="matcha-ops">
          <OpsSidebar open onToggle={vi.fn()} />
        </WorkSurfaceProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: /Events/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Inventory/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Schedule/ })).toBeInTheDocument()
  })
})
