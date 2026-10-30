import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { WorkSurfaceProvider } from '../../routes/WorkSurfaceContext'
import WorkSidebar from './WorkSidebar'

const account = vi.hoisted(() => ({ personal: true, tasksEnabled: true, jobSearchEnabled: true, projects: true }))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: account.personal, hasFeature: () => false }) }))
vi.mock('../../hooks/useEntitlements', () => ({ useEntitlements: () => ({ ...account, can: (k: string) => k === 'projects_solo' && account.projects, plan: 'pro' }) }))
vi.mock('../../hooks/useTasksSummary', () => ({ useTasksSummary: () => ({ count: 0, attention: false }) }))
vi.mock('../../hooks/useHrCaseAccess', () => ({ useHrCaseAccess: () => false }))
vi.mock('../../hooks/useStars', () => ({ useStars: () => [], getStarredFileMeta: () => [] }))
vi.mock('./WorkSidebar/useSidebarData', () => ({ useSidebarData: () => ({
  channels: [], projects: [], threads: [], journals: [], inboxUnread: 0, pendingConnections: 0, loggedEventsCount: 0,
}) }))
vi.mock('./WorkSidebar/useSectionState', () => ({ useSectionState: () => ({}) }))
vi.mock('./WorkSidebar/useSidebarRename', () => ({ useSidebarRename: () => ({}) }))
vi.mock('./WorkSidebar/ChannelsSection', () => ({ default: () => null }))
vi.mock('./WorkSidebar/ProjectsSection', () => ({ default: () => null }))
vi.mock('./WorkSidebar/ChatsSection', () => ({ default: () => null }))
vi.mock('./WorkSidebar/SidebarFooter', () => ({ default: () => null }))
vi.mock('../panels/TemplatePickerModal', () => ({ default: () => null }))

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>
}

function sidebar(open: boolean) {
  render(
    <MemoryRouter initialEntries={['/espresso']}>
      <WorkSurfaceProvider value="espresso">
        <WorkSidebar open={open} onToggle={vi.fn()} />
        <Location />
      </WorkSurfaceProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => { account.personal = true; account.tasksEnabled = true; account.jobSearchEnabled = true; account.projects = true })

describe.each([true, false])('sidebar open=%s', (open) => {
  it('has Tasks and no separate Job search entry', () => {
    sidebar(open)
    expect(screen.queryByRole('button', { name: 'Job search' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Tasks' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks')
  })

  it('keeps Tasks available for accounts with only Job search', () => {
    account.tasksEnabled = false
    sidebar(open)
    expect(screen.getByRole('button', { name: 'Tasks' })).toBeInTheDocument()
  })

  it('hides Tasks when neither feature is available', () => {
    account.tasksEnabled = false
    account.jobSearchEnabled = false
    sidebar(open)
    expect(screen.queryByRole('button', { name: 'Tasks' })).not.toBeInTheDocument()
  })

  it('keeps personal Tasks out of business workspaces', () => {
    account.personal = false
    sidebar(open)
    expect(screen.queryByRole('button', { name: 'Tasks' })).not.toBeInTheDocument()
  })

  it('has Sales for personal accounts that can make a workspace', () => {
    sidebar(open)
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/sales')
  })

  it('keeps Sales out of business workspaces and accounts without workspaces', () => {
    account.personal = false
    sidebar(open)
    expect(screen.queryByRole('button', { name: 'Sales' })).not.toBeInTheDocument()
  })
})
