import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../hooks/useMe', () => ({ useMe: useMeMock }))

import { CredentialTemplatesRoute } from './AppRoutes'

describe('CredentialTemplatesRoute product boundary', () => {
  beforeEach(() => {
    useMeMock.mockReturnValue({
      me: {
        user: { role: 'client' },
        profile: {
          signup_source: 'matcha_compliance',
          enabled_features: { credential_templates: true },
        },
      },
      loading: false,
      hasFeature: () => true,
    })
  })

  it('redirects standalone Compliance tenants out of the client-only route', async () => {
    render(
      <MemoryRouter initialEntries={['/app/credential-templates']}>
        <Routes>
          <Route path="/app/credential-templates" element={<CredentialTemplatesRoute />} />
          <Route path="/app/compliance" element={<div>Compliance home</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Compliance home')).toBeInTheDocument()
  })
})
