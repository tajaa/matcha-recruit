import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StoreReady from './StoreReady'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))

const SITE = { id: 'site-1', name: 'Tide Goods', slug: 'tide-goods', subdomain: 'tide-goods', custom_domain: null, status: 'draft' }
const PRODUCTS = [
  { id: 'p1', name: 'Tea towel', price_cents: 1850, currency: 'USD', image_url: 'https://cdn.example.com/t.jpg', status: 'active' },
  { id: 'p2', name: 'Apron', price_cents: 4200, currency: 'USD', image_url: null, status: 'active' },
  { id: 'p3', name: 'Old draft', price_cents: 100, currency: 'USD', image_url: null, status: 'draft' },
]
const READINESS = {
  ready: true,
  items: [
    { key: 'content', label: 'Add an intro', hint: '', done: true, required: true, action: 'pages' },
    { key: 'offering', label: 'Add something to buy', hint: '', done: true, required: false, action: 'shop' },
    { key: 'payments', label: 'Take card payments', hint: 'Connect Stripe.', done: false, required: false, action: 'payments' },
    { key: 'branding', label: 'Add your logo', hint: '', done: true, required: false, action: 'settings' },
  ],
}

function respond(site = SITE) {
  api.get.mockImplementation((path: string) => {
    if (path === '/sites/site-1') return Promise.resolve(site)
    if (path === '/sites/site-1/products') return Promise.resolve(PRODUCTS)
    if (path === '/sites/site-1/readiness') return Promise.resolve(READINESS)
    if (path === '/sites/site-1/pages') return Promise.resolve([{ id: 'home-1' }])
    return Promise.reject(new Error(path))
  })
}

function renderReady() {
  render(
    <MemoryRouter initialEntries={['/cappe/sites/site-1/ready']}>
      <Routes>
        <Route path="/cappe/sites/:siteId/ready" element={<StoreReady />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  respond()
})

describe('StoreReady', () => {
  it('shows what is on sale and only the next steps not yet done', async () => {
    renderReady()
    expect(await screen.findByRole('heading', { name: 'Tide Goods is ready to sell' })).toBeInTheDocument()
    expect(screen.getByText('Tea towel')).toBeInTheDocument()
    expect(screen.getByText('$18.50')).toBeInTheDocument()
    expect(screen.queryByText('Old draft')).not.toBeInTheDocument()
    // A product with no photo offers one.
    expect(screen.getByRole('link', { name: /Add a photo/ })).toHaveAttribute('href', '/cappe/sites/site-1/shop')
    expect(screen.getByRole('link', { name: /Add another product/ })).toHaveAttribute('href', '/cappe/sites/site-1/shop')
    expect(screen.getByRole('link', { name: /Take card payments/ })).toHaveAttribute('href', '/cappe/sites/site-1/orders')
    expect(screen.getByRole('link', { name: /Read your return and shipping policies/ }))
      .toHaveAttribute('href', '/cappe/sites/site-1/shop#policies')
    expect(screen.queryByText('Add your logo')).not.toBeInTheDocument()
    expect(screen.queryByText('Add something to buy')).not.toBeInTheDocument()
  })

  it('publishes in one tap and links to the live store', async () => {
    api.post.mockResolvedValue({ ...SITE, status: 'published' })
    renderReady()
    fireEvent.click(await screen.findByRole('button', { name: /Publish my store/ }))
    expect(await screen.findByRole('heading', { name: 'Tide Goods is live' })).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/site-1/publish')
    expect(screen.getByRole('link', { name: /View your store/ })).toHaveAttribute('href', expect.stringMatching(/^https:\/\/tide-goods\./))
  })

  it('says why publishing failed', async () => {
    api.post.mockRejectedValue(new Error('Finish these before publishing: Add your policies'))
    renderReady()
    fireEvent.click(await screen.findByRole('button', { name: /Publish my store/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Finish these before publishing')
    expect(screen.getByRole('button', { name: /Publish my store/ })).toBeEnabled()
  })

  it('says when the store could not be loaded', async () => {
    api.get.mockRejectedValue(new Error('Site not found'))
    renderReady()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Site not found'))
  })
})
