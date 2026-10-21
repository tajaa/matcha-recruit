import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MagazineSettings from './settings/MagazineSettings'
import StoryEditor from './editor/StoryEditor'
import Readers from './readers/Readers'
import Earnings from './earnings/Earnings'
import StripeConnectCard from '../components/StripeConnectCard'
import CappeSidebar from '../components/CappeSidebar'
import { priceCents, priceLabel } from './settings/price'
import { newBlock } from './editor/blocks'
import type { CappeAccount, CappeMagazine, CappeMagazineEarnings, CappePost, CappeStoryOptions } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe', clearCappeTokens: vi.fn() }))

const magazine = (over: Partial<CappeMagazine> = {}): CappeMagazine => ({
  site_id: 's-1', enabled: true, name: 'Salt & Light', tagline: null, about: null, masthead_style: 'classic', accent: null,
  topics: [], front_at_root: true, nav_label: 'Magazine', cover_post_id: null, follow_enabled: true, paid_enabled: false,
  price_cents: null, paid_pitch: null, preview_blocks: 3, lapsed_at: null, created_at: null, updated_at: null, live: true,
  plan_includes_magazine: true, plan_includes_paid: true, stripe_ready: true, fee_bps: 3000, ...over,
})

const OPTIONS: CappeStoryOptions = {
  layouts: [{ key: 'standard', label: 'Standard', content: { blocks: [newBlock('cover'), newBlock('text')] } }],
  topics: [{ key: 'city', label: 'City life' }],
}

const post = (over: Partial<CappePost> = {}): CappePost => ({
  id: 'p-1', site_id: 's-1', title: 'Low tide', slug: 'low-tide', excerpt: null, body: '', cover_image_url: null,
  status: 'draft', published_at: null, created_at: '2026-10-20T09:00:00Z', updated_at: '2026-10-20T09:00:00Z',
  format: 'blocks', content: { blocks: [newBlock('cover'), newBlock('text')] }, kicker: null, topic: null,
  layout: 'standard', access: 'free', cover_asset_id: null, byline: null, word_count: 0, reading_minutes: 1, hidden: false,
  ...over,
}) as CappePost

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.includes(k))
    return hit === undefined ? Promise.reject(new Error(`unexpected GET ${path}`)) : Promise.resolve(routes[hit])
  })
}

function mount(path: string, element: React.ReactElement, pattern: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path={pattern} element={element} /></Routes></MemoryRouter>)
}

beforeEach(() => {
  api.postHtml.mockResolvedValue('<p>preview</p>')
})

describe('prices', () => {
  it('reads dollars and writes them back', () => {
    expect(priceCents('5')).toBe(500)
    expect(priceCents(' $5.50 ')).toBe(550)
    expect(priceCents('')).toBeNull()
    expect(priceCents('0.50')).toBeNaN()
    expect(priceCents('2000')).toBeNaN()
    expect(priceLabel(500)).toBe('$5')
    expect(priceLabel(550)).toBe('$5.50')
  })
})

describe('MagazineSettings — paid subscriptions', () => {
  it('turns them on at a price, with a pitch', async () => {
    answer({ '/magazine': magazine(), '/stories/options': OPTIONS })
    api.put.mockResolvedValue(magazine({ paid_enabled: true, price_cents: 550 }))
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
    const box = within(await screen.findByRole('region', { name: 'Paid subscriptions' }))
    expect(box.getByText(/Gummfit keeps 30% of each payment/)).toBeInTheDocument()
    fireEvent.click(box.getByRole('checkbox'))
    fireEvent.change(box.getByLabelText('Price a month'), { target: { value: '5.50' } })
    fireEvent.change(box.getByPlaceholderText(/Every story, every week/), { target: { value: ' The archive too. ' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1]).toMatchObject({ paid_enabled: true, price_cents: 550, paid_pitch: 'The archive too.', preview_blocks: 3 })
    expect(api.put.mock.calls[0][1]).not.toHaveProperty('price')
  })

  it('refuses a price it can’t charge, and says what’s missing', async () => {
    answer({ '/magazine': magazine({ stripe_ready: false, lapsed_at: '2026-10-01T09:00:00Z' }), '/stories/options': OPTIONS })
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
    const box = within(await screen.findByRole('region', { name: 'Paid subscriptions' }))
    expect(box.getByRole('link', { name: 'Connect Stripe' })).toHaveAttribute('href', '/sites/s-1/earnings')
    expect(box.getByText(/Paid subscriptions stopped on/)).toBeInTheDocument()
    fireEvent.change(box.getByLabelText('Price a month'), { target: { value: '0.25' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('between $1 and $1,000')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('says which plans charge readers', async () => {
    answer({ '/magazine': magazine({ plan_includes_paid: false }), '/stories/options': OPTIONS })
    mount('/sites/s-1/magazine', <MagazineSettings />, '/sites/:siteId/magazine')
    const box = within(await screen.findByRole('region', { name: 'Paid subscriptions' }))
    expect(box.getByText(/Writer, Creator, Business or Pro/)).toBeInTheDocument()
    expect(box.getByRole('checkbox')).toBeDisabled()
  })
})

describe('StoryEditor — who can read it', () => {
  it('makes a story paid only while the magazine charges, and offers one paywall', async () => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [] }, '/magazine': magazine({ paid_enabled: true }) })
    api.put.mockResolvedValue(post({ access: 'paid' }))
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    const select = await screen.findByLabelText('Who can read it')
    await waitFor(() => expect(within(select).getByRole('option', { name: /Subscribers/ })).not.toBeDisabled())
    fireEvent.change(select, { target: { value: 'paid' } })
    fireEvent.click(screen.getByRole('button', { name: /Add a block/ }))
    expect(screen.getByRole('menuitem', { name: 'Paywall' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1]).toMatchObject({ access: 'paid' })
  })

  it('points to the settings when the magazine doesn’t charge', async () => {
    answer({ '/posts/p-1': post(), '/stories/options': OPTIONS, '/assets': { assets: [] }, '/magazine': magazine() })
    mount('/sites/s-1/stories/p-1', <StoryEditor />, '/sites/:siteId/stories/:postId')
    const select = await screen.findByLabelText('Who can read it')
    expect(within(select).getByRole('option', { name: /Subscribers/ })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Magazine settings' })).toHaveAttribute('href', '/sites/s-1/magazine')
  })
})

describe('Readers', () => {
  it('lists who pays and gives and stops free subscriptions', async () => {
    answer({ '/magazine/readers': {
      subscriptions: [{ id: 'r-1', status: 'active', total_cents: 500, currency: 'USD', current_period_end: '2026-11-20T09:00:00Z',
        cancel_at_period_end: false, created_at: '2026-10-20T09:00:00Z', email: 'rae@example.com', name: null },
      { id: 'r-2', status: 'active', total_cents: 500, currency: 'USD', current_period_end: '2026-11-02T09:00:00Z',
        cancel_at_period_end: true, created_at: '2026-10-02T09:00:00Z', email: 'lee@example.com', name: 'Lee' }],
      comps: [{ id: 'c-1', note: 'Press', expires_at: null, created_at: '2026-10-20T09:00:00Z', email: 'press@example.com' }],
    } })
    api.post.mockResolvedValue({ id: 'c-2', note: null, expires_at: '2027-01-20T09:00:00Z', created_at: '2026-10-21T09:00:00Z', email: 'new@example.com' })
    api.delete.mockResolvedValue(null)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('/sites/s-1/readers', <Readers />, '/sites/:siteId/readers')
    expect(await screen.findByText(/2 paying readers/)).toBeInTheDocument()
    expect(screen.getByText(/\$5\/mo · Paying · renews/)).toBeInTheDocument()
    expect(screen.getByText(/\$5\/mo · Ends/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Reader’s email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('For how long'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: /Give/ }))
    expect(await screen.findByText(/new@example.com can read every story now/)).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/magazine/comps', { email: 'new@example.com', months: 3, note: null })
    fireEvent.click(screen.getByRole('button', { name: 'Stop press@example.com’s free subscription' }))
    await waitFor(() => expect(screen.queryByText('press@example.com')).not.toBeInTheDocument())
    expect(api.delete).toHaveBeenCalledWith('/sites/s-1/magazine/comps/c-1')
  })
})

describe('Earnings', () => {
  it('shows the ledger, the share and the balance', async () => {
    const earnings: CappeMagazineEarnings = {
      fee_bps: 3000, paying_readers: 3,
      all_time: [{ currency: 'USD', payments: 4, gross_cents: 2000, fee_cents: 600, refunded_cents: 500, net_cents: 900 }],
      last_30_days: [],
      payments: [{ id: 'pay-1', amount_cents: 500, fee_cents: 150, refunded_cents: 500, currency: 'USD', billing_reason: 'subscription_create',
        paid_at: '2026-10-20T09:00:00Z', email: 'rae@example.com' }],
      balance: { available: [{ amount_cents: 1200, currency: 'USD' }], pending: [] },
    }
    answer({ '/magazine/earnings': earnings, '/payments/status': { connected: true, charges_enabled: true, details_submitted: true, platform_fee_bps: 200 } })
    mount('/sites/s-1/earnings', <Earnings />, '/sites/:siteId/earnings')
    expect(await screen.findByText(/3 paying readers. Gummfit keeps 30% of each payment/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'All time' })).getByText('$9.00')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Last 30 days' })).getByText('No payments yet.')).toBeInTheDocument()
    expect(screen.getByText(/Available \$12.00/)).toBeInTheDocument()
    expect(screen.getByText(/\$5.00 refunded/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Card payments active/)).toHaveTextContent('readers’ subscriptions pay out to your Stripe account (Gummfit keeps 30%)'))
  })

  it('says why it couldn’t load', async () => {
    api.get.mockRejectedValue(new Error('Site not found'))
    mount('/sites/s-1/earnings', <Earnings />, '/sites/:siteId/earnings')
    expect(await screen.findByRole('alert')).toHaveTextContent('Site not found')
  })
})

describe('StripeConnectCard — for a magazine', () => {
  it('asks to connect for readers, not a storefront', async () => {
    api.get.mockResolvedValueOnce({ connected: false, charges_enabled: false, details_submitted: false, platform_fee_bps: 200 })
    render(<StripeConnectCard magazineFeeBps={3000} />)
    expect(await screen.findByText('Connect Stripe to charge readers')).toBeInTheDocument()
    expect(screen.getByText(/Gummfit keeps 30%. Paid subscriptions can't be turned on until then./)).toBeInTheDocument()
  })
})

describe('the writer sidebar', () => {
  it('has the readers and the earnings', () => {
    answer({ '/threads': [] })
    const writer = { id: 'a-1', email: 'ana@example.com', name: 'Ana', plan: 'writer', account_type: 'writer' } as CappeAccount
    render(<MemoryRouter initialEntries={['/cappe/sites/0f0e0d0c-0b0a-0908-0706-050403020100/stories']}>
      <CappeSidebar account={writer} />
    </MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Readers' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Earnings' })).toBeInTheDocument()
  })
})
