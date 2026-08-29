import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock } = vi.hoisted(() => ({ useMeMock: vi.fn() }))

vi.mock('../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../components/shared/FeatureGate', () => ({
  FeatureGate: ({ children }: { children: ReactNode }) => children,
}))
vi.mock('../pages/portal/PortalLayout', () => ({ default: () => <Outlet /> }))
vi.mock('../pages/portal/PortalDashboard', () => ({ default: () => <div>Dashboard page</div> }))
vi.mock('../pages/portal/PortalSchedule', () => ({ default: () => <div>Schedule page</div> }))
vi.mock('../pages/portal/PortalBenefits', () => ({ default: () => <div>Benefits page</div> }))
vi.mock('../pages/portal/AskHR', () => ({ default: () => <div>Ask HR page</div> }))
vi.mock('../pages/portal/EmployeeTakeTraining', () => ({ default: () => <div>Training page</div> }))
vi.mock('../pages/portal/EmployeeSignDocument', () => ({ default: () => <div>Document page</div> }))

import PortalRoutes from './PortalRoutes'

function renderPortal(hasSchedule: boolean) {
  useMeMock.mockReturnValue({
    hasFeature: (feature: string) => feature === 'employee_schedule' && hasSchedule,
    loading: false,
  })

  render(
    <MemoryRouter initialEntries={['/portal']}>
      <Routes>
        <Route path="/portal/*" element={<PortalRoutes />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PortalRoutes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens My Schedule by default when employee scheduling is enabled', async () => {
    renderPortal(true)

    expect(await screen.findByText('Schedule page')).toBeInTheDocument()
  })

  it('falls back to Dashboard when employee scheduling is disabled', async () => {
    renderPortal(false)

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })
})
