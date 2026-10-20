import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BusinessIdentityCard from './BusinessIdentityCard'
import PoliciesCard from './PoliciesCard'
import type { CappePolicy } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const policy = (over: Partial<CappePolicy>): CappePolicy => ({
  kind: 'refund', title: 'Refund policy', path: '/policies/refund', starter: 'Returns\nWithin 30 days.',
  body: null, updated_at: null, ...over,
})
const POLICIES = [
  policy({}),
  policy({ kind: 'shipping', title: 'Shipping policy', path: '/policies/shipping', body: 'We ship weekly.' }),
]
const SITE = { id: 's-1', slug: 'lumen', subdomain: 'lumen', custom_domain: 'lumen.example.com', status: 'published', tax_label: 'VAT' }

beforeEach(() => {
  api.get.mockReset()
  api.put.mockReset()
})

describe('PoliciesCard', () => {
  function load(site = SITE) {
    api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/policies') ? { policies: POLICIES } : site))
  }

  it('publishes a policy from our starting text', async () => {
    load()
    api.put.mockResolvedValue({ policies: [{ ...POLICIES[0], body: 'Returns\nWithin 30 days.' }, POLICIES[1]] })
    render(<PoliciesCard siteId="s-1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Refund policy' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start from our text' }))
    expect(screen.getByRole('textbox', { name: 'Refund policy' })).toHaveValue('Returns\nWithin 30 days.')
    fireEvent.click(screen.getByRole('button', { name: /Publish/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/policies/refund', { body: 'Returns\nWithin 30 days.' }))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('links a published policy on the live store, and can take it down', async () => {
    load()
    api.put.mockResolvedValue({ policies: [POLICIES[0], { ...POLICIES[1], body: null }] })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<PoliciesCard siteId="s-1" />)
    expect(await screen.findByRole('link', { name: 'View your shipping policy' }))
      .toHaveAttribute('href', 'https://lumen.example.com/policies/shipping')
    fireEvent.click(screen.getByRole('button', { name: 'Shipping policy' }))
    fireEvent.click(screen.getByRole('button', { name: 'Take down' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1/policies/shipping', { body: '' }))
    confirm.mockRestore()
  })

  it('offers no link while the store isn’t live', async () => {
    load({ ...SITE, status: 'draft' })
    render(<PoliciesCard siteId="s-1" />)
    const list = await screen.findByRole('list')
    expect(within(list).queryByRole('link')).not.toBeInTheDocument()
    expect(within(list).getByText('published')).toBeInTheDocument()
  })

  it('says it couldn’t load instead of offering empty boxes', async () => {
    api.get.mockRejectedValue(new Error('down'))
    render(<PoliciesCard siteId="s-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your policies')
  })
})

describe('BusinessIdentityCard', () => {
  it('loads and saves who is selling', async () => {
    api.get.mockResolvedValue({ ...SITE, legal_name: 'Lumen Ltd', business_address: null, tax_id: null, collect_phone: false })
    api.put.mockResolvedValue({})
    render(<BusinessIdentityCard siteId="s-1" />)
    expect(await screen.findByRole('textbox', { name: 'Legal business name' })).toHaveValue('Lumen Ltd')
    fireEvent.change(screen.getByRole('textbox', { name: /VAT number/ }), { target: { value: ' GB123 ' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Business address' }), { target: { value: '12 Market St' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /phone number/ }))
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/sites/s-1', {
      legal_name: 'Lumen Ltd', business_address: '12 Market St', tax_id: 'GB123', collect_phone: true,
    }))
  })

  it('offers nothing to save when it couldn’t load', async () => {
    api.get.mockRejectedValue(new Error('down'))
    render(<BusinessIdentityCard siteId="s-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your business details')
    expect(screen.queryByRole('button', { name: /Save/ })).not.toBeInTheDocument()
  })
})
