import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MatchaWork from './workspaces/MatchaWork'
import Companies from './Companies'
import Customers from './Customers'
import { RegistrationTable } from './accounts/RegistrationTable'

const { apiMock } = vi.hoisted(() => ({ apiMock: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
vi.mock('../../../api/client', () => ({ api: apiMock }))

function account(index: number) {
  const key = String(index).padStart(4, '0')
  return {
    user_id: `user-${key}`, company_id: `company-${key}`, email: `member${key}@example.test`, name: `Member ${key}`,
    created_at: new Date(Date.UTC(2024, 0, 1) + index * 3600000).toISOString(),
    free_tokens_used: index, free_token_limit: 1000000, free_tokens_remaining: 1000000 - index,
    subscription_token_limit: 0, subscription_tokens_remaining: 0, has_active_subscription: index % 3 === 0,
    beta_features: { matcha_work_beta_lite: index % 3 === 1, matcha_work_beta_full: false }, is_suspended: index % 5 === 0,
    subscription: index % 3 === 0 ? { pack_id: 'Pro', status: 'active', amount_cents: 2000, stripe_subscription_id: `sub-${key}`, stripe_customer_id: `customer-${key}`, current_period_end: null, canceled_at: null } : null,
  }
}

function company(index: number) {
  const user = account(index)
  return {
    id: user.company_id, company_name: `Business ${String(index).padStart(4, '0')}`, owner_email: user.email, owner_name: user.name, owner_user_id: user.user_id,
    status: 'approved', signup_source: 'bespoke', industry: null, healthcare_specialties: null, company_size: null,
    is_personal: false, is_test: false, is_suspended: false, deleted_at: null, created_at: user.created_at, subscription: user.subscription,
  }
}

function setup(count = 1005) {
  const accounts = Array.from({ length: count }, (_, index) => account(index))
  const companies = Array.from({ length: count }, (_, index) => company(index))
  apiMock.get.mockImplementation(async (path: string) => {
    if (path.startsWith('/admin/business-registrations')) return { registrations: companies, total: companies.length }
    if (path.endsWith('/matcha-work/business')) return companies.map((company) => ({
      company_id: company.id, company_name: company.company_name, company_status: company.status, signup_source: company.signup_source,
      member_count: 2, free_tokens_used: 0, free_token_limit: 1000000, free_tokens_remaining: 1000000,
      subscription_token_limit: 0, subscription_tokens_remaining: 0, has_active_subscription: false, created_at: company.created_at,
    }))
    return accounts
  })
  return { accounts, companies }
}

describe('compact admin account lists', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.post.mockResolvedValue({})
    apiMock.patch.mockResolvedValue({})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  it('bounds personal rows and searches the full list from any page', async () => {
    setup()
    const user = userEvent.setup()
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    expect(await screen.findByText('1–25 of 1,005')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(26)
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.getByText('26–50 of 1,005')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Search personal accounts' }), 'member0000')
    expect(screen.getByRole('link', { name: 'member0000@example.test' })).toBeInTheDocument()
    expect(screen.getByText('1–1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    await user.clear(screen.getByRole('textbox', { name: 'Search personal accounts' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Rows per page' }), '50')
    expect(screen.getAllByRole('row')).toHaveLength(51)
    expect(screen.getByText('1–50 of 1,005')).toBeInTheDocument()
  })

  it('combines status and plan filters and sorts before pagination', async () => {
    setup(60)
    const user = userEvent.setup()
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    await screen.findByText('1–25 of 60')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account status' }), 'suspended')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Plan filter' }), 'paid')
    expect(screen.getByText('1–4 of 4')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account status' }), 'all')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Plan filter' }), 'all')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort personal accounts' }), 'name')
    expect(within(screen.getAllByRole('row')[1]).getByRole('link', { name: 'member0000@example.test' })).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort personal accounts' }), 'tokens')
    expect(within(screen.getAllByRole('row')[1]).getByRole('link', { name: 'member0059@example.test' })).toBeInTheDocument()
  })

  it('preserves token grants, comp access, reset links, suspension, and Stripe links', async () => {
    setup(3)
    const user = userEvent.setup()
    apiMock.post.mockImplementation(async (path: string) => path.endsWith('password-reset') ? { reset_url: 'https://example.test/reset' } : {})
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    await screen.findByText('1–3 of 3')
    await user.click(screen.getByRole('checkbox', { name: 'Pro comp for member0001@example.test' }))
    await waitFor(() => expect(apiMock.patch).toHaveBeenCalledWith('/admin/users/user-0001/beta-flags', { matcha_work_beta_full: true }))
    await user.click(screen.getByRole('button', { name: 'Actions for member0001@example.test' }))
    await user.click(screen.getByRole('menuitem', { name: 'Grant tokens' }))
    await user.type(screen.getByRole('textbox', { name: 'Token grant amount' }), '100000')
    await user.click(screen.getByRole('button', { name: 'Grant 100K' }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/matcha-work/billing/admin/companies/company-0001/tokens', { tokens: 100000, description: 'Admin grant to individual: member0001@example.test' }))
    await waitFor(() => expect(screen.queryByText('Grant Tokens')).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Actions for member0001@example.test' }))
    await user.click(screen.getByRole('menuitem', { name: 'Reset password' }))
    expect(apiMock.post).toHaveBeenCalledWith('/admin/users/user-0001/password-reset', {})
    await user.click(screen.getByRole('button', { name: 'Actions for member0001@example.test' }))
    await user.click(screen.getByRole('menuitem', { name: 'Suspend account' }))
    expect(window.confirm).toHaveBeenCalledWith('Suspend member0001@example.test? They will be locked out.')
    expect(apiMock.post).toHaveBeenCalledWith('/admin/users/user-0001/suspend', {})
    await user.click(screen.getByRole('button', { name: 'Actions for member0000@example.test' }))
    expect(screen.getByRole('menuitem', { name: 'Open Stripe subscription' })).toHaveAttribute('href', 'https://dashboard.stripe.com/subscriptions/sub-0000')
  })

  it('paginates business workspaces and keeps their token grant request', async () => {
    setup(60)
    const user = userEvent.setup()
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Business workspaces' }))
    await screen.findByText('1–25 of 60')
    expect(screen.getAllByRole('row')).toHaveLength(26)
    await user.type(screen.getByRole('textbox', { name: 'Search business workspaces' }), 'Business 0059')
    expect(screen.getByText('1–1 of 1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Grant tokens' }))
    await user.type(screen.getByRole('textbox', { name: 'Custom token amount' }), '500000')
    const dialog = screen.getByRole('heading', { name: 'Grant tokens — Business 0059' }).parentElement!
    await user.click(within(dialog).getByRole('button', { name: 'Grant tokens' }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/matcha-work/billing/admin/companies/company-0059/tokens', { tokens: 500000, description: 'Admin grant to business: Business 0059' }))
  })

  it('keeps signup URL generation available from the compact toolbar', async () => {
    setup(1)
    const user = userEvent.setup()
    apiMock.post.mockResolvedValue({ invite_url: 'https://example.test/invite/one', email: 'invite@example.test', reused: false })
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    await screen.findByText('1–1 of 1')
    await user.click(screen.getByRole('button', { name: 'Generate Signup URL' }))
    await user.type(screen.getByRole('textbox', { name: 'Invite email' }), 'invite@example.test')
    await user.click(screen.getByRole('button', { name: 'Generate URL' }))
    expect(await screen.findByText('https://example.test/invite/one')).toBeInTheDocument()
    expect(apiMock.post).toHaveBeenCalledWith('/admin/individual-invites', { email: 'invite@example.test' })
  })

  it('shows a failed load and can retry without claiming the list is empty', async () => {
    setup(1)
    apiMock.get.mockRejectedValueOnce(new Error('Account service unavailable'))
    const user = userEvent.setup()
    render(<MemoryRouter><MatchaWork /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Account service unavailable')
    expect(screen.queryByText('No individual users yet.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('1–1 of 1')).toBeInTheDocument()
  })

  it('paginates companies, searches owner email, and preserves server filters', async () => {
    setup()
    const user = userEvent.setup()
    render(<MemoryRouter><Companies /></MemoryRouter>)
    await screen.findByText('1–25 of 1,005')
    expect(screen.getAllByRole('row')).toHaveLength(26)
    await user.type(screen.getByRole('textbox', { name: 'Search companies' }), 'member0000@example.test')
    expect(screen.getByRole('link', { name: 'Business 0000' })).toBeInTheDocument()
    expect(screen.getByText('1–1 of 1')).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Company status' }), 'pending')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Company tier' }), 'compliance')
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith('/admin/business-registrations?status=pending&tier=compliance'))
  })

  it('paginates customer tabs and preserves subscription actions', async () => {
    setup(60)
    const user = userEvent.setup()
    render(<MemoryRouter><Customers /></MemoryRouter>)
    await screen.findByText('1–25 of 60')
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    await user.type(screen.getByRole('textbox', { name: 'Search customers' }), 'Business 0000')
    expect(screen.getByText('1–1 of 1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Actions for Business 0000' }))
    await user.click(screen.getByRole('menuitem', { name: 'Cancel at period end' }))
    expect(apiMock.post).toHaveBeenCalledWith('/admin/companies/company-0000/cancel-subscription', {})
    await user.click(screen.getByRole('button', { name: /^Matcha Work Personal/ }))
    expect(screen.getByText('0–0 of 0')).toBeInTheDocument()
    await user.clear(screen.getByRole('textbox', { name: 'Search customers' }))
    expect(screen.getByText('1–25 of 60')).toBeInTheDocument()
  })

  it('shows only restore for a deleted company', async () => {
    const restore = vi.fn()
    const user = userEvent.setup()
    render(<MemoryRouter><RegistrationTable tab="all" rows={[{ ...company(0), deleted_at: '2026-01-01' }]} onRestore={restore} onSuspend={vi.fn()} onReset={vi.fn()} onCancel={vi.fn()} onCancelAtEnd={vi.fn()} onSoftDelete={vi.fn()} /></MemoryRouter>)
    await user.click(screen.getByRole('button', { name: 'Actions for Business 0000' }))
    expect(screen.getAllByRole('menuitem')).toHaveLength(1)
    await user.click(screen.getByRole('menuitem', { name: 'Restore company' }))
    expect(restore).toHaveBeenCalledOnce()
  })
})
