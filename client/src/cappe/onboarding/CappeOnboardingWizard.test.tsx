import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeOnboardingWizard from './CappeOnboardingWizard'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api }))
vi.mock('../hooks/useCappeMe', () => ({
  useCappeMe: () => ({ account: { name: 'Pat Lee', account_type: 'business' } }),
}))

const TEMPLATES = [
  { id: 't-blog', name: 'Journal', slug: 'journal', category: 'blog', description: 'Writing first.', preview_image_url: null, is_premium: false, price_cents: 0 },
  { id: 't-cafe', name: 'Corner Cafe', slug: 'corner-cafe', category: 'food', description: 'Menu and hours.', preview_image_url: null, is_premium: false, price_cents: 0 },
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

async function toStartStep(mode: 'One location' | 'Multiple locations', name: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(mode) }))
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  fireEvent.change(screen.getByLabelText('Business name'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
  await screen.findByRole('heading', { name: 'How do you want to start?' })
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  api.get.mockReset().mockResolvedValue(TEMPLATES)
  api.post.mockReset().mockResolvedValue({ id: 'site-1' })
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

  it('creates a blank site when asked to', async () => {
    renderWizard()
    await toStartStep('One location', ' Corner Bakery ')
    fireEvent.click(screen.getByRole('button', { name: 'Start with a blank site' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/sites', {
      name: 'Corner Bakery', source_type: 'blank', is_multi_location: false,
    })
  })

  it('starts from a template, recommended ones first', async () => {
    renderWizard()
    await toStartStep('One location', 'Corner Bakery')

    const picks = await screen.findAllByRole('button', { name: /^Use the .* template$/ })
    // A business account sees the food template ahead of the blog one.
    expect(picks.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Use the Corner Cafe template', 'Use the Journal template',
    ])
    fireEvent.click(picks[0])

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1'))
    expect(api.post).toHaveBeenCalledWith('/sites/from-template', {
      template_id: 't-cafe', name: 'Corner Bakery', is_multi_location: false,
    })
  })

  it('keeps the several-locations answer on the template path and seeds the first branch', async () => {
    renderWizard()
    fireEvent.click(screen.getByRole('button', { name: /Multiple locations/ }))
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.change(screen.getByLabelText('Business name'), { target: { value: 'Corner Bakery' } })
    fireEvent.change(screen.getByPlaceholderText('e.g. Downtown'), { target: { value: 'Mission' } })
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Use the Journal template' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/cappe/sites/site-1/locations'))
    expect(api.post).toHaveBeenNthCalledWith(1, '/sites/from-template', {
      template_id: 't-blog', name: 'Corner Bakery', is_multi_location: true,
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
