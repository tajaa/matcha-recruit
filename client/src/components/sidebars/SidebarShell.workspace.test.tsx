import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Users, Link2, CalendarDays, Radio } from 'lucide-react'

const { useMeMock, listChannelsMock } = vi.hoisted(() => ({
  useMeMock: vi.fn(),
  listChannelsMock: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: useMeMock }))
vi.mock('../../work/api/channels', () => ({ listChannels: listChannelsMock }))

import SidebarShell from './SidebarShell'
import { withoutOpsRows } from './workspaceNav'
import type { NavItem } from './SidebarShell'

const NAV: NavItem[] = [
  { to: '/app/employees', icon: Users, label: 'Employees' },
  { to: '/app/symlink', icon: Link2, label: 'Sym-links', feature: 'symlink' },
  { to: '/ops/schedule', icon: CalendarDays, label: 'Schedule' },
  { to: '/ops', icon: Radio, label: 'Matcha Ops', feature: 'matcha_ops' },
]

function setFlags(flags: string[]) {
  useMeMock.mockReturnValue({
    me: { user: { role: 'client', email: 'owner@example.com' }, profile: { name: 'Owner' } },
    hasFeature: (f: string) => flags.includes(f),
    isBetaFeature: () => false,
  })
}

function renderAt(path: string, workspaceSwitch = true) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarShell logoTo="/app" logoLabel="Matcha" nav={NAV} footerSlot={null} workspaceSwitch={workspaceSwitch} />
    </MemoryRouter>,
  )
}

const OPS_FLAGS = ['matcha_ops', 'ems', 'inventory', 'employee_schedule', 'symlink']

describe('SidebarShell Matcha | Ops switch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listChannelsMock.mockResolvedValue([
      { id: 'c1', name: 'downtown-floor', unread_count: 3 },
    ])
  })

  it('opens on Matcha under /app, without the rows that lead into /ops', () => {
    setFlags(OPS_FLAGS)
    renderAt('/app/employees')
    expect(screen.getByRole('tab', { name: /Matcha/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('link', { name: 'Employees' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sym-links' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Matcha Ops' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Schedule' })).not.toBeInTheDocument()
  })

  it('swaps to the Ops features and channels on click, without navigating', async () => {
    setFlags(OPS_FLAGS)
    renderAt('/app/employees')
    fireEvent.click(screen.getByRole('tab', { name: /Ops/ }))
    expect(screen.getByRole('tab', { name: /Ops/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('link', { name: 'Events' })).toHaveAttribute('href', '/ops/events')
    expect(screen.getByRole('link', { name: 'Inventory' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Schedule' })).toHaveAttribute('href', '/ops/schedule')
    expect(screen.queryByRole('link', { name: 'Waste & par' })).not.toBeInTheDocument() // flag off
    expect(screen.queryByRole('link', { name: 'Employees' })).not.toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /downtown-floor/ })).toHaveAttribute('href', '/ops/channels/c1')
  })

  it('opens on Ops when the page is under /ops', () => {
    setFlags(OPS_FLAGS)
    renderAt('/ops/inventory')
    expect(screen.getByRole('tab', { name: /Ops/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('link', { name: 'Inventory' })).toBeInTheDocument()
  })

  it('shows no switch (and the full nav) without matcha_ops', async () => {
    setFlags(['symlink'])
    renderAt('/app/employees')
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Schedule' })).toBeInTheDocument()
    await waitFor(() => expect(listChannelsMock).not.toHaveBeenCalled())
  })

  it('shows no switch on rails that do not opt in', () => {
    setFlags(OPS_FLAGS)
    renderAt('/app/employees', false)
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(listChannelsMock).not.toHaveBeenCalled()
  })
})

describe('withoutOpsRows', () => {
  it('drops /ops rows from items and groups, and empty groups', () => {
    const out = withoutOpsRows([
      { to: '/app/employees', icon: Users, label: 'Employees' },
      { label: 'Ops only', items: [{ to: '/ops/events', icon: Radio, label: 'Events' }] },
      { label: 'Mixed', items: [{ to: '/app/x', icon: Radio, label: 'X' }, { to: '/ops', icon: Radio, label: 'Ops' }] },
    ])
    expect(out.map((i) => i.label)).toEqual(['Employees', 'Mixed'])
    expect('items' in out[1] && out[1].items.map((i) => i.label)).toEqual(['X'])
  })
})
