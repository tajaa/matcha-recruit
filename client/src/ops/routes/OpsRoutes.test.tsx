import { Outlet } from 'react-router-dom'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { useMeMock, refresh } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  refresh: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../components/shared/UpgradeUpsellCard', () => ({
  UpgradeUpsellCard: ({ title }: { title: string }) => <div>{title}</div>,
}))
vi.mock('../../work/layout/WorkLayout', () => ({
  default: () => <Outlet />,
}))

vi.mock('../../work/pages/ChannelBrowse', () => ({ default: () => <div>Channel browse</div> }))
vi.mock('../../work/pages/ChannelJoinByInvite', () => ({ default: () => <div>Channel join</div> }))
vi.mock('../../work/pages/ChannelView', () => ({ default: () => <div>Channel view</div> }))
vi.mock('../../work/pages/EventsHub', () => ({ default: () => <div>Events page</div> }))
vi.mock('../../work/pages/InventoryAudit', () => ({ default: () => <div>Inventory audit page</div> }))
vi.mock('../../work/pages/InventoryHub', () => ({ default: () => <div>Inventory page</div> }))
vi.mock('../../work/pages/ProtocolPage', () => ({ default: () => <div>Protocol page</div> }))
vi.mock('../../pages/app/employees/EmployeeSchedule', () => ({ default: () => <div>Schedule page</div> }))
vi.mock('../../pages/app/employees/ScheduleIntelligence', () => ({ default: () => <div>Schedule intelligence page</div> }))
vi.mock('../pages/OpsHome', () => ({ default: () => <div>Ops home page</div> }))
vi.mock('../pages/OpsAccess', () => ({ default: () => <div>Ops access page</div> }))

import OpsRoutes from './OpsRoutes'

describe('OpsRoutes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    refresh.mockResolvedValue(undefined)
    useMeMock.mockReturnValue({
      me: { user: { role: 'admin' }, profile: null },
      hasFeature: () => false,
      loading: false,
      refresh,
    })
  })

  it.each([
    ['/ops/events', 'Events page'],
    ['/ops/inventory', 'Inventory page'],
    ['/ops/schedule', 'Schedule page'],
    ['/ops/schedule-intelligence', 'Schedule intelligence page'],
  ])('admits platform admins to %s without company flags', (path, marker) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/ops/*" element={<OpsRoutes />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText(marker)).toBeInTheDocument()
    expect(screen.queryByText(/Upgrade to unlock/)).not.toBeInTheDocument()
  })
})
