import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Features from './Features'

vi.mock('../../../api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

import { api } from '../../../api/client'

const mockGet = vi.mocked(api.get)
const mockPatch = vi.mocked(api.patch)

type Company = { id: string; company_name: string; enabled_features: Record<string, boolean>; is_test: boolean }

const FLAGS = [
  { key: 'handbooks', is_beta: false, non_test_enabled_count: 0, non_test_companies: [] },
  {
    key: 'property', is_beta: true, non_test_enabled_count: 1,
    non_test_companies: [{ id: 'c1', company_name: 'Acme Dental' }],
  },
  // A backend flag the catalog has no label for.
  { key: 'zz_new_flag', is_beta: false, non_test_enabled_count: 0, non_test_companies: [] },
]

function serve(companies: Company[]) {
  mockGet.mockImplementation((path: string) => {
    if (path === '/admin/company-features') return Promise.resolve(companies)
    if (path === '/admin/feature-flags') return Promise.resolve(FLAGS)
    if (path === '/admin/products') return Promise.resolve({ builtin_products: [] })
    return Promise.resolve({
      company_id: companies[0].id, plan: { kind: 'unknown', slug: null, label: '—' },
      addons: [], features: {}, grants: {}, grant_types: [],
    })
  })
}

// The switch sits next to its label inside the row.
function rowOf(label: string) {
  return screen.getByText(label, { selector: 'span.truncate' }).closest('div') as HTMLElement
}

beforeEach(() => { vi.clearAllMocks() })

describe('admin Features', () => {
  it('lists a backend flag the catalog does not name under Other, and toggles it', async () => {
    const company = { id: 'c1', company_name: 'Acme Dental', enabled_features: {}, is_test: false }
    serve([company])
    mockPatch.mockResolvedValue({ enabled_features: { zz_new_flag: true } })
    render(<Features />)

    await screen.findByText('Other')
    const toggle = within(rowOf('zz_new_flag')).getByRole('switch')
    expect(toggle).toBeEnabled()
    await userEvent.click(toggle)

    expect(mockPatch).toHaveBeenCalledWith('/admin/company-features/c1', { feature: 'zz_new_flag', enabled: true })
    await waitFor(() => expect(within(rowOf('zz_new_flag')).getByRole('switch')).toBeChecked())
  })

  it('marks a beta flag that is on for a non-test company, and leaves it switchable off', async () => {
    serve([{ id: 'c1', company_name: 'Acme Dental', enabled_features: { property: true }, is_test: false }])
    render(<Features />)

    await screen.findByText('Beta · non-test')
    const row = rowOf('Property (SOV/COPE grading, insurance-to-value, cat perils)')
    expect(row.firstElementChild).toHaveAttribute('title', expect.stringContaining('on for this non-test company'))
    expect(within(row).getByRole('switch')).toBeEnabled()
  })

  it('does not mark the same flag on a test account', async () => {
    serve([{ id: 't1', company_name: 'Sandbox Co', enabled_features: { property: true }, is_test: true }])
    render(<Features />)

    await screen.findByText('Other')
    expect(screen.queryByText('Beta · non-test')).not.toBeInTheDocument()
    expect(within(rowOf('Property (SOV/COPE grading, insurance-to-value, cat perils)')).getByText('Beta')).toBeInTheDocument()
  })

  it('names the non-test companies with a beta flag on in Manage beta, and lists Other flags there', async () => {
    serve([{ id: 'c1', company_name: 'Acme Dental', enabled_features: { property: true }, is_test: false }])
    render(<Features />)

    await screen.findByText('Other')
    await userEvent.click(screen.getByRole('button', { name: /Manage beta/ }))

    // The modal's card holds its title and its body.
    const modal = (await screen.findByText('Manage beta status')).parentElement as HTMLElement
    expect(within(modal).getByText('On for 1 non-test: Acme Dental')).toBeInTheDocument()
    expect(within(modal).getByText('Other')).toBeInTheDocument()
    expect(within(modal).getByText('zz_new_flag')).toBeInTheDocument()
  })
})
