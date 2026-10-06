import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeOnboardingWizard from './CappeOnboardingWizard'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), categories: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, fetchCappeTemplateCategories: api.categories }))

const me = vi.hoisted(() => ({ account: { name: 'Pat Lee', account_type: 'business', plan: 'free' } }))
vi.mock('../hooks/useCappeMe', () => ({ useCappeMe: () => ({ account: me.account }) }))

const SWATCH = { bg: '#fff', surface: '#eee', brand: '#0a0', text: '#111' }
const TEMPLATES = [
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

async function toCategoryStep(mode: 'One location' | 'Multiple locations', name: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(mode) }))
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  fireEvent.change(screen.getByLabelText('Business name'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  await screen.findByRole('heading', { name: 'What kind of business is it?' })
}

async function toStartStep(mode: 'One location' | 'Multiple locations', name: string, category: string | null = 'Food & Drink') {
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
    expect(api.post).toHaveBeenNthCalledWith(2, '/sites/site-1/locations', { name: 'Mission', is_default: true })
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
