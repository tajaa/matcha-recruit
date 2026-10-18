import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Pricing from './Pricing'

vi.mock('../../../api/client', () => ({ api: { get: vi.fn(async () => ({ products: [] })) }, ApiError: class extends Error {} }))
vi.mock('./PricingForm', () => ({ PricingForm: ({ productCode }: { productCode: string }) => <div data-testid="price-form">{productCode}</div> }))
vi.mock('../../../components/admin/StripeCatalogPanel', () => ({ StripeCatalogPanel: () => <div>Stripe catalog</div> }))

describe('consolidated pricing', () => {
  it('retains every built-in price previously split between Pricing and Signup Links', async () => {
    render(<MemoryRouter><Pricing /></MemoryRouter>)
    expect(screen.getAllByTestId('price-form').map((item) => item.textContent).sort()).toEqual([
      'matcha_lite', 'matcha_lite_essentials', 'matcha_compliance', 'addon_voice_intake', 'addon_hris_sync', 'addon_handbook_watch', 'tellus_brand', 'espresso_lite', 'espresso_pro',
    ].sort())
    expect(await screen.findByText('No published scheduling product is billed through Stripe.')).toBeInTheDocument()
    expect(screen.getByText('Beta products — excluded from the commercial Stripe catalog')).toBeInTheDocument()
    expect(screen.getByText('Matcha Incidents')).toBeInTheDocument()
    expect(screen.getByText('Matcha Scheduler')).toBeInTheDocument()
  })
})
