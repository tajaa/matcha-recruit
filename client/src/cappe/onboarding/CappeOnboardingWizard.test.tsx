import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeOnboardingWizard from './CappeOnboardingWizard'
import type { CappeTemplateSummary } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), upload: vi.fn(), categories: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, fetchCappeTemplateCategories: api.categories }))

// Whatever zone the test machine is in — the wizard sends the browser's.
const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone

const me = vi.hoisted(() => ({ account: { name: 'Pat Lee', account_type: 'business', plan: 'free' } }))
vi.mock('../hooks/useCappeMe', () => ({ useCappeMe: () => ({ account: me.account }) }))

const SWATCH = { bg: '#fff', surface: '#eee', brand: '#0a0', text: '#111' }
const TEMPLATES: CappeTemplateSummary[] = [
  { slug: 'journal', name: 'Journal', category: 'other', category_label: 'Other', tags: [], description: 'Writing first.',
    mode: 'light', heading_font: 'Fraunces', swatch: SWATCH, pages: [{ slug: 'home', title: 'Home' }] },
  { slug: 'corner-cafe', name: 'Corner Cafe', category: 'food-drink', category_label: 'Food & Drink', tags: [], description: 'Menu and hours.',
    mode: 'dark', heading_font: 'Playfair Display', swatch: SWATCH, pages: [{ slug: 'home', title: 'Home' }] },
]
const CATEGORIES = [
  { slug: 'food-drink', label: 'Food & Drink' },
  { slug: 'art-design', label: 'Art & Design' },
  { slug: 'trades-home', label: 'Trades & Home Services' },
  { slug: 'other', label: 'Other' },
]

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderWizard() {
  render(
    <MemoryRouter initialEntries={['/cappe/onboarding']}>
      <Routes>
        <Route path="/cappe/onboarding" element={<CappeOnboardingWizard />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

type Mode = 'Online only' | 'One location' | 'Multiple locations'

async function toCategoryStep(mode: Mode, name: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(mode) }))
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  fireEvent.change(screen.getByLabelText('Business name'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  await screen.findByRole('heading', { name: 'What kind of business is it?' })
}

async function toStartStep(mode: Mode, name: string, category: string | null = 'Food & Drink') {
  await toCategoryStep(mode, name)
  if (category) {
    fireEvent.click(await screen.findByRole('button', { name: category }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  } else {
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
  }
  await screen.findByRole('heading', { name: 'How do you want to start?' })
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  api.get.mockReset().mockResolvedValue(TEMPLATES)
  api.post.mockReset().mockResolvedValue({ id: 'site-1' })
  api.put.mockReset().mockResolvedValue({ id: 'site-1' })
  api.upload.mockReset().mockResolvedValue({ url: 'https://cdn.example.com/mug.jpg' })
  api.categories.mockReset().mockResolvedValue(CATEGORIES)
  me.account = { name: 'Pat Lee', account_type: 'business', plan: 'free' }
})

describe('CappeOnboardingWizard', () => {
  it('previews the address before anything is created', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /One location/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.change(screen.getByLabelText('Business name'), { target: { value: "Mara's Coffee" } })

    expect(screen.getByText(/mara-s-coffee\./)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('asks the kind of business once and cannot continue without an answer or a skip', async () => {
    renderWizard()
    await toCategoryStep('One location', 'Corner Bakery')

    expect(screen.getByRole('button', { name: /Continue/ })).toBeDisabled()
    fireEvent.click(await screen.findByRole('button', { name: 'Trades & Home Services' }))
    expect(screen.getByRole('button', { name: 'Trades & Home Services' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Continue/ })).toBeEnabled()
  })

  it('offers a personal account the creative slice of the taxonomy', async () => {
    me.account = { name: 'Pat Lee', account_type: 'personal', plan: 'free' }
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /One location/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.change(screen.getByLabelText('Your name or business name'), { target: { value: 'Pat Lee' } })
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    await screen.findByRole('heading', { name: "What's the site for?" })

    expect(await screen.findByRole('button', { name: 'Art & Design' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Food & Drink' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Trades & Home Services' })).not.toBeInTheDocument()
  })

  it('creates a blank site when asked to, keeping the category it asked for', async () => {
    renderWizard()
    await toStartStep('One location', ' Corner Bakery ')
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank site' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/sites', {
      name: 'Corner Bakery', source_type: 'blank', is_multi_location: false, directory_category: 'food-drink',
    })
    // The site takes the owner's timezone instead of staying on UTC.
    expect(api.put).toHaveBeenCalledWith('/sites/site-1', { timezone: TZ })
  })

  describe('online only: the quick store', () => {
    const SELLS = { plan_code: 'business', plan_name: 'Business', allowed_fulfillment: ['physical', 'digital'] }

    // jsdom has no object URLs; the photo preview needs one.
    beforeEach(() => {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mug')
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    })

    async function toProductStep(plan: object = SELLS, templates = TEMPLATES) {
      api.get.mockImplementation((path: string) =>
        Promise.resolve(path === '/billing/entitlements' ? plan : templates))
      api.post.mockResolvedValue({ site: { id: 'site-1' }, product: { id: 'prod-1' } })
      renderWizard()
      expect(screen.getByText('Where do customers find you?')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: /Online only/ }))
      fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
      expect(screen.queryByText('Your first branch')).not.toBeInTheDocument()
      fireEvent.change(screen.getByLabelText('Store name'), { target: { value: ' Tide Goods ' } })
      fireEvent.change(screen.getByLabelText(/What do you sell/), { target: { value: 'Linen, dyed by hand.' } })
      fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
      // Design and optional product share the final step; no category question.
      await screen.findByRole('heading', { name: 'Make it your store' })
    }

    it('makes the store with its first product in one call, then adds the photo', async () => {
      await toProductStep()
      const create = screen.getByRole('button', { name: /Create my store/ })
      expect(create).toBeDisabled()
      const photo = new File(['x'], 'mug.jpg', { type: 'image/jpeg' })
      fireEvent.change(screen.getByLabelText('Product photo'), { target: { files: [photo] } })
      fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Tea towel' } })
      fireEvent.change(screen.getByLabelText('Price (USD)'), { target: { value: '18.5' } })
      fireEvent.change(screen.getByLabelText('How many in stock'), { target: { value: '30' } })
      fireEvent.click(create)

      await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/ready'))
      expect(api.post).toHaveBeenCalledTimes(1)
      expect(api.post).toHaveBeenCalledWith('/sites/quick-store', {
        name: 'Tide Goods', tagline: 'Linen, dyed by hand.', timezone: TZ, template_slug: 'online-studio',
        product: { name: 'Tea towel', price_cents: 1850, inventory: 30 },
      })
      expect(api.upload).toHaveBeenCalledWith('/sites/site-1/upload', expect.any(FormData))
      expect(api.put).toHaveBeenCalledWith('/sites/site-1/products/prod-1', { image_url: 'https://cdn.example.com/mug.jpg' })
    })

    it('leaves stock untracked when no count is given', async () => {
      await toProductStep()
      fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Tea towel' } })
      fireEvent.change(screen.getByLabelText('Price (USD)'), { target: { value: '18' } })
      fireEvent.click(screen.getByRole('button', { name: /Create my store/ }))
      await waitFor(() => expect(api.post).toHaveBeenCalled())
      expect(api.post.mock.calls[0][1].product).toEqual({ name: 'Tea towel', price_cents: 1800, inventory: null })
      expect(api.upload).not.toHaveBeenCalled()
    })

    it('still lands on the store when the photo upload fails', async () => {
      api.upload.mockRejectedValueOnce(new Error('too big'))
      await toProductStep()
      fireEvent.change(screen.getByLabelText('Product photo'), { target: { files: [new File(['x'], 'm.jpg')] } })
      fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Tea towel' } })
      fireEvent.change(screen.getByLabelText('Price (USD)'), { target: { value: '18' } })
      fireEvent.click(screen.getByRole('button', { name: /Create my store/ }))
      await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/ready'))
    })

    it('says which plan sells goods, and can make the store without a product', async () => {
      await toProductStep({ plan_code: 'free', plan_name: 'Free', allowed_fulfillment: ['digital', 'service', 'booking'] })
      expect(await screen.findByText(/Physical products are sold on the Business plan/)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'See plans' })).toHaveAttribute('href', '/cappe/billing')
      expect(screen.queryByLabelText('Product name')).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Create my store, add products later' }))
      await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/ready'))
      expect(api.post.mock.calls[0][1].product).toBeNull()
    })

    it('creates a designed draft without requiring product details', async () => {
      await toProductStep()
      expect(screen.getByRole('button', { name: /Choose Studio/ })).toHaveAttribute('aria-pressed', 'true')
      fireEvent.click(screen.getByRole('button', { name: 'See my store, add products later' }))
      await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/ready'))
      expect(api.post.mock.calls[0][1]).toMatchObject({ product: null, template_slug: 'online-studio' })
      expect(api.upload).not.toHaveBeenCalled()
    })

    it('saves the selected online design', async () => {
      const pop = { ...TEMPLATES[0], slug: 'online-pop', name: 'Pop — Online shop', tags: ['online-store'] }
      await toProductStep(SELLS, [...TEMPLATES, pop])
      fireEvent.click(await screen.findByRole('button', { name: 'Choose Pop — Online shop' }))
      fireEvent.click(screen.getByRole('button', { name: 'See my store, add products later' }))
      await waitFor(() => expect(api.post).toHaveBeenCalled())
      expect(api.post.mock.calls[0][1]).toMatchObject({ template_slug: 'online-pop', product: null })
    })

    it('shows why the store could not be made', async () => {
      await toProductStep()
      api.post.mockRejectedValueOnce(new Error('Your plan includes 1 site. Upgrade to create more.'))
      fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Tea towel' } })
      fireEvent.change(screen.getByLabelText('Price (USD)'), { target: { value: '18' } })
      fireEvent.click(screen.getByRole('button', { name: /Create my store/ }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Your plan includes 1 site')
    })
  })

  it('still finishes when the timezone cannot be saved', async () => {
    api.put.mockRejectedValueOnce(new Error('offline'))
    renderWizard()
    await toStartStep('One location', 'Corner Bakery')
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank site' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1'))
  })

  it('a blank site with the category skipped sends none', async () => {
    renderWizard()
    await toStartStep('One location', 'Corner Bakery', null)
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank site' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/sites', {
      name: 'Corner Bakery', source_type: 'blank', is_multi_location: false,
    })
  })

  it('starts from a template, the chosen category first, and seeds the Discover listing', async () => {
    renderWizard()
    await toStartStep('One location', 'Corner Bakery', 'Food & Drink')

    const picks = await screen.findAllByRole('button', { name: /^Use the .* template$/ })
    // The food template leads because that is what the person told us.
    expect(picks.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Use the Corner Cafe template', 'Use the Journal template',
    ])
    fireEvent.click(picks[0])

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1'))
    expect(api.post).toHaveBeenCalledWith('/sites/from-template', {
      template_slug: 'corner-cafe', name: 'Corner Bakery', is_multi_location: false, directory_category: 'food-drink',
    })
  })

  it('skipping the category sends none and keeps the catalog order', async () => {
    renderWizard()
    await toStartStep('One location', 'Corner Bakery', null)

    const picks = await screen.findAllByRole('button', { name: /^Use the .* template$/ })
    expect(picks.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Use the Journal template', 'Use the Corner Cafe template',
    ])
    fireEvent.click(picks[1])

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/sites/from-template', {
      template_slug: 'corner-cafe', name: 'Corner Bakery', is_multi_location: false,
    })
  })

  it('still reaches the shelf when the category list cannot load', async () => {
    api.categories.mockRejectedValueOnce(new Error('offline'))
    renderWizard()
    await toCategoryStep('One location', 'Corner Bakery')

    expect(await screen.findByText(/Couldn't load the category list/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    await screen.findByRole('heading', { name: 'How do you want to start?' })
  })

  it('keeps the several-locations answer on the template path and seeds the first branch', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /Multiple locations/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.change(screen.getByLabelText('Business name'), { target: { value: 'Corner Bakery' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Downtown'), { target: { value: 'Mission' } })
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    await screen.findByRole('heading', { name: 'What kind of business is it?' })
    fireEvent.click(await screen.findByRole('button', { name: 'Other' }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use the Journal template' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/locations'))
    expect(api.post).toHaveBeenNthCalledWith(1, '/sites/from-template', {
      template_slug: 'journal', name: 'Corner Bakery', is_multi_location: true, directory_category: 'other',
    })
    expect(api.post).toHaveBeenNthCalledWith(2, '/sites/site-1/locations', { name: 'Mission', is_default: true, timezone: TZ })
  })

  it('shows why creation failed and lets the person try again', async () => {
    api.post.mockRejectedValueOnce(new Error('That site address was just taken.'))
    renderWizard()
    await toStartStep('One location', 'Corner Bakery')
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank site' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('That site address was just taken.')
    expect(screen.getByRole('button', { name: 'Start with a blank site' })).toBeEnabled()
  })
})
