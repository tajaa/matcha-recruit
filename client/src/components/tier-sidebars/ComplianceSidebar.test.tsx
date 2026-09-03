import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))

import ComplianceSidebar from './ComplianceSidebar'

describe('ComplianceSidebar credential templates navigation', () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({
      me: {
        user: { id: 'user-1', email: 'client@example.com', role: 'client' },
        profile: { name: 'Client User', company_name: 'Example Company' },
      },
      loading: false,
      hasFeature: () => true,
      isBetaFeature: () => false,
    })
  })

  it('does not expose credential templates even when the feature is enabled', () => {
    render(
      <MemoryRouter initialEntries={['/app/compliance']}>
        <ComplianceSidebar />
      </MemoryRouter>,
    )

    expect(screen.queryByRole('link', { name: /Credential/ })).not.toBeInTheDocument()
  })
})
