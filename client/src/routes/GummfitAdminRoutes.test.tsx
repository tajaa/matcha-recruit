import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/ui'
import { clearAuthTokens, getAccessToken } from '../api/authStorage'
import { api } from '../api/client'
import GummfitAdminRoutes from './GummfitAdminRoutes'
import Login from '../pages/Login'
import App from '../App'

const host = vi.hoisted(() => ({ cappe: false }))
vi.mock('../cappe/host', async (original) => ({ ...await original<object>(), get isCappeHost() { return host.cappe } }))
vi.mock('../cappe/routes', () => ({ default: () => <p>Public Gummfit landing</p> }))
vi.mock('../pages/landing/scheduling', () => ({ default: () => <p>Matcha scheduling landing</p> }))
vi.mock('../components/shared/RouteTracker', () => ({ default: () => null }))

const auth = vi.hoisted(() => ({ role: 'admin' as string | null, loading: false, authFailed: false }))
vi.mock('../hooks/useMe', () => ({
  useMe: () => ({ ...auth, me: auth.role ? { user: { role: auth.role, email: 'staff@example.com' } } : null }),
  invalidateMeCache: vi.fn(),
}))
vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
  API_BASE: '/api',
  logoutSession: vi.fn().mockResolvedValue(true),
}))

const modelMap = {
  apps: { matcha: 'haiku', gummfit: 'default', espresso: 'haiku' },
  surfaces: { 'matcha.ir': 'haiku', 'gummfit.studio': 'inherit' },
}
const modelSettings = {
  agent_models: modelMap,
  agent_models_version: 'version-1',
  anthropic_configured: true,
  agent_model_choices: [{ id: 'haiku', label: 'Claude Haiku' }],
  agent_model_registry: [
    { key: 'matcha', label: 'Matcha', description: 'Matcha settings', surfaces: [] },
    { key: 'gummfit', label: 'Gummfit', description: 'Gummfit settings', surfaces: [
      { key: 'gummfit.studio', label: 'Studio', description: 'Studio assistant', builtin: 'Gemini' },
    ] },
  ],
}

function Location() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

function show(path = '/gummfit/admin') {
  return render(<ToastProvider><MemoryRouter initialEntries={[path]}>
    <Location />
    <Routes>
      <Route path="/gummfit/admin/*" element={<GummfitAdminRoutes />} />
      <Route path="/" element={<p>Public Gummfit</p>} />
    </Routes>
  </MemoryRouter></ToastProvider>)
}

beforeEach(() => {
  host.cappe = false
  auth.role = 'admin'
  auth.loading = false
  auth.authFailed = false
  clearAuthTokens()
  vi.mocked(api.get).mockImplementation(async (path) => {
    if (path === '/admin/platform-settings') return modelSettings
    if (path === '/cappe/matcha-admin/plans') return [{ code: 'business', name: 'Business', status: 'active' }]
    if (path === '/admin/cappe/accounts') return {
      accounts: [], totals: { account_count: 0, site_count: 0, published_count: 0, order_count: 0, revenue_cents: 0, plan_counts: {} },
    }
    return []
  })
})

describe('Gummfit staff console', () => {
  it('exposes every existing Gummfit tool using the staff APIs', async () => {
    show()
    expect(await screen.findByText('No Gummfit accounts found.')).toBeInTheDocument()
    for (const [label, endpoint] of [
      ['Brands', null],
      ['Creators', '/admin/cappe/creators'],
      ['Signup links', '/cappe/matcha-admin/signup-grants'],
      ['Studio bank', '/cappe/matcha-admin/studio-bank?kind=photo'],
    ] as const) {
      fireEvent.click(screen.getByRole('button', { name: label }))
      if (endpoint) await waitFor(() => expect(api.get).toHaveBeenCalledWith(endpoint))
    }
    expect(screen.getByRole('navigation', { name: 'Gummfit admin' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open Gummfit admin/ })).not.toBeInTheDocument()
  })

  it('sends signed-out staff to the staff login and preserves their destination', async () => {
    auth.role = null
    auth.authFailed = true
    show('/gummfit/admin?view=bank')
    expect(await screen.findByRole('heading', { name: 'Admin sign in.' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/gummfit/admin/login?next=%2Fgummfit%2Fadmin%3Fview%3Dbank')
    expect(api.get).not.toHaveBeenCalled()
  })

  it('keeps tools unmounted while identity is loading', () => {
    auth.role = null
    auth.loading = true
    show()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalled()
  })

  it('fails closed without redirecting on a transient identity failure', () => {
    auth.role = null
    show()
    expect(screen.getByText(/Could not verify your session/)).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalled()
    expect(screen.getByTestId('location')).toHaveTextContent('/gummfit/admin')
  })

  it('blocks non-admin staff identities before any tool loads', async () => {
    auth.role = 'client'
    show()
    expect(await screen.findByText('Public Gummfit')).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalled()
  })

  it('edits only Gummfit controls and preserves other apps in the versioned save', async () => {
    vi.mocked(api.put).mockResolvedValue({ agent_models: modelMap, version: 'version-2' })
    show('/gummfit/admin/models')
    const select = await screen.findByRole('combobox', { name: 'Gummfit default' })
    expect(screen.queryByRole('combobox', { name: 'Matcha default' })).not.toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'haiku' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/admin/platform-settings/agent-models', {
      apps: { ...modelMap.apps, gummfit: 'haiku' }, surfaces: modelMap.surfaces, version: 'version-1',
    }))
  })

  it('shows a settings error with retry instead of allowing an empty-map save', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('Network unavailable'))
    show('/gummfit/admin/models')
    expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable')
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('combobox', { name: 'Gummfit default' })).toBeInTheDocument()
  })

  it.each([
    [null, '/gummfit/admin'],
    ['/gummfit/admin?view=grants', '/gummfit/admin?view=grants'],
    ['/admin/settings', '/gummfit/admin'],
    ['https://example.com', '/gummfit/admin'],
    ['/gummfit/admin/login', '/gummfit/admin'],
    ['/gummfit/admin/login/', '/gummfit/admin'],
    ['/GUMMFIT/ADMIN/LOGIN///?next=/admin', '/gummfit/admin'],
    ['/gummfit/%61dmin/%6cogin/', '/gummfit/admin'],
    ['/gummfit/%61dmin?view=bank', '/gummfit/%61dmin?view=bank'],
  ])('signs staff in and validates the return path %s', async (next, destination) => {
    vi.mocked(api.post).mockResolvedValue({ access_token: 'staff-access', refresh_token: 'staff-refresh', user: { role: 'admin' } })
    show(`/gummfit/admin/login${next ? `?next=${encodeURIComponent(next)}` : ''}`)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'staff@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe(destination))
    expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'staff@example.com', password: 'test-password' })
    expect(getAccessToken()).toBe('staff-access')
  })

  it('rejects a non-admin login without saving its credentials', async () => {
    vi.mocked(api.post).mockResolvedValue({ access_token: 'client-access', refresh_token: 'client-refresh', user: { role: 'client' } })
    show('/gummfit/admin/login')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'customer@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/Administrator access is required/)).toBeInTheDocument()
    expect(getAccessToken()).toBeNull()
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', 'https://hey-matcha.com/reset-password')
  })

  it('retains the existing Matcha login flow and role destination', async () => {
    vi.mocked(api.post).mockResolvedValue({ access_token: 'client-access', refresh_token: 'client-refresh', user: { role: 'client' } })
    render(<MemoryRouter initialEntries={['/login']}><Location /><Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/app" element={<p>Matcha app</p>} />
    </Routes></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Sign in.' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in with SSO' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'customer@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Matcha app')).toBeInTheDocument()
    expect(getAccessToken()).toBe('client-access')
  })

  it.each([false, true])('opens Gummfit from View Gummfit on the Cappe host=%s', async (cappe) => {
    host.cappe = cappe
    render(<ToastProvider><MemoryRouter initialEntries={['/gummfit/admin']}><App /></MemoryRouter></ToastProvider>)
    fireEvent.click(await screen.findByRole('link', { name: 'View Gummfit' }))
    expect(await screen.findByText('Public Gummfit landing')).toBeInTheDocument()
    expect(screen.queryByText('Matcha scheduling landing')).not.toBeInTheDocument()
  })

  it.each(['/GUMMFIT/ADMIN/models', '/gummfit/%61dmin?view=bank', '/%67ummfit/admin/'])('uses staff sign-in for accepted Gummfit URL %s', async (path) => {
    host.cappe = true
    auth.role = null
    auth.authFailed = true
    render(<ToastProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></ToastProvider>)
    expect(await screen.findByRole('heading', { name: 'Admin sign in.' })).toBeInTheDocument()
    expect(screen.queryByText('Public Gummfit landing')).not.toBeInTheDocument()
  })
})
