import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from '../../App'
import { WorkSurfaceProvider, useWorkBase } from './WorkSurfaceContext'
import { api } from '../../api/client'

const identity = vi.hoisted(() => ({ personal: true }))

vi.mock('../../hooks/useMe', () => ({
  useMe: () => ({ isPersonal: identity.personal, loading: false, hasFeature: () => false }),
}))
vi.mock('../hooks/usePresenceHeartbeat', () => ({ usePresenceHeartbeat: () => {} }))
vi.mock('../hooks/useChannelNotifications', () => ({ useChannelNotifications: () => {} }))
vi.mock('../api/matchaWork', () => ({
  fetchUsageMeter: () => Promise.resolve(null),
  USAGE_CHANGED_EVENT: 'mw-usage-changed',
}))
vi.mock('../components/shell/WorkSidebar', () => ({ default: () => null }))
vi.mock('../components/shell/WerkLiteSidebar', () => ({ default: () => null }))
vi.mock('../../ops/components/OpsWorkspaceSidebar', () => ({ default: () => null }))
vi.mock('../components/shell/NotificationBell', () => ({ default: () => null }))
vi.mock('../components/shell/NotificationSettingsMenu', () => ({ default: () => null }))
vi.mock('../components/shell/OnlineUsersPanel', () => ({ OnlineUsersPanel: () => null }))
vi.mock('../pages/MatchaWorkList', () => ({ default: () => <output data-testid="home">Home</output> }))
vi.mock('../pages/ChannelView', () => ({ default: () => <output data-testid="channel">Channel view</output> }))
vi.mock('../pages/Inbox', () => ({ default: () => <output data-testid="inbox">Inbox</output> }))
vi.mock('../pages/ProjectView', () => ({ default: () => <output data-testid="project">Project view</output> }))
vi.mock('../pages/Journals', () => ({ default: () => <output data-testid="journals">Journals view</output> }))

function LocationMarker() {
  const { pathname, search } = useLocation()
  return <output data-testid="location">{pathname}{search}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationMarker />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  identity.personal = true
  localStorage.clear()
})

afterEach(() => vi.unstubAllGlobals())

describe('Espresso routes', () => {
  it('renders the personal work shell with Espresso branding', async () => {
    renderAt('/espresso')
    await waitFor(() => expect(screen.getByTestId('home')).toBeInTheDocument(), { timeout: 5000 })
    expect(screen.getByText('Espresso')).toBeInTheDocument()
  })

  it('renders the personal channel view', async () => {
    renderAt('/espresso/channels/abc')
    expect(await screen.findByTestId('channel')).toBeInTheDocument()
  })

  it('routes journal details before the thread catch-all', async () => {
    renderAt('/espresso/journals/abc')
    expect(await screen.findByTestId('journals')).toBeInTheDocument()
  })

  it('bounces business users to /work with the path and query', async () => {
    identity.personal = false
    renderAt('/espresso/inbox?filter=unread')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/work/inbox?filter=unread'))
    expect(screen.getByTestId('inbox')).toBeInTheDocument()
  })

  it('bounces personal users from /work and preserves the project path', async () => {
    renderAt('/work/projects/abc?tab=chat')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/espresso/projects/abc?tab=chat'))
    expect(screen.getByTestId('project')).toBeInTheDocument()
  })

  it('redirects legacy /werk links to /espresso', async () => {
    renderAt('/werk/projects/abc?tab=chat')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/espresso/projects/abc?tab=chat'))
    expect(screen.getByTestId('project')).toBeInTheDocument()
  })

  it('uses /espresso as the personal base', () => {
    function BaseProbe() {
      return <output data-testid="base">{useWorkBase()}</output>
    }
    render(<WorkSurfaceProvider value="espresso"><BaseProbe /></WorkSurfaceProvider>)
    expect(screen.getByTestId('base')).toHaveTextContent('/espresso')
  })

  it('opens the required plan paywall when a gated request returns 403', async () => {
    renderAt('/espresso')
    await screen.findByTestId('home')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'plan_required', required_plan: 'pro', current_plan: 'free', feature: 'projects_collab' },
    }), { status: 403, headers: { 'Content-Type': 'application/json' } })))
    let error: unknown
    await act(async () => {
      try {
        await api.get('/matcha-work/projects')
      } catch (cause) {
        error = cause
      }
    })
    expect(error).toMatchObject({ status: 403 })
    expect(screen.getByRole('dialog')).toHaveTextContent('Collab workspaces need Pro')
  })
})
