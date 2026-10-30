import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ServicesPage from './ServicesPage'

vi.mock('../../components/marketing/PricingContactModal', () => ({
  PricingContactModal: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <p>Consultation form</p> : null),
}))
vi.mock('../../components/landing/ComplianceTicker', () => ({ ComplianceTicker: () => null }))

function show(path: string) {
  render(<MemoryRouter initialEntries={[path]}><ServicesPage /></MemoryRouter>)
}

describe('ServicesPage', () => {
  it('opens the consultation form from the booking link outreach sends', () => {
    show('/services?book=1')
    expect(screen.getByText('Consultation form')).toBeTruthy()
  })

  it('stays closed otherwise', () => {
    show('/services')
    expect(screen.queryByText('Consultation form')).toBeNull()
  })
})
