import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock, useSidebarBadgesMock, fetchCompanyBrokerChatSummaryMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  useSidebarBadgesMock: vi.fn(),
  fetchCompanyBrokerChatSummaryMock: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../hooks/useSidebarBadges', () => ({ useSidebarBadges: useSidebarBadgesMock }))
vi.mock('../../api/broker-chat/companyBrokerChat', () => ({
  fetchCompanyBrokerChatSummary: fetchCompanyBrokerChatSummaryMock,
}))

import ClientSidebar from './ClientSidebar'

function renderSidebar(hasCredentialTemplates: boolean) {
  useMeMock.mockReturnValue({
    me: {
      user: { id: 'user-1', email: 'client@example.com', role: 'client' },
      profile: { name: 'Client User', company_name: 'Example Company' },
    },
    loading: false,
    isPersonal: false,
    hasFeature: (feature: string) => feature === 'credential_templates' && hasCredentialTemplates,
    isBetaFeature: () => false,
  })

  return render(
    <MemoryRouter initialEntries={['/app/credential-templates']}>
      <ClientSidebar />
    </MemoryRouter>,
  )
}

describe('ClientSidebar credential templates navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSidebarBadgesMock.mockReturnValue({
      badges: { ir: 0, er: 0, escalations: 0, inbox: 0, notifications: 0 },
      markSeen: vi.fn(),
    })
    fetchCompanyBrokerChatSummaryMock.mockReturnValue(new Promise(() => {}))
  })

  it('shows a clearly labeled active link when the feature is enabled', () => {
    renderSidebar(true)

    const link = screen.getByRole('link', { name: 'Credential Templates' })
    expect(link).toHaveAttribute('href', '/app/credential-templates')
    expect(link).toHaveClass('bg-vsc-bg')
  })

  it('hides the link when the feature is disabled', () => {
    renderSidebar(false)

    expect(screen.queryByRole('link', { name: 'Credential Templates' })).not.toBeInTheDocument()
  })
})
