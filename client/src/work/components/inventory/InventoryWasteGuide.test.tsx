import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import InventoryWasteGuide from './InventoryWasteGuide'

const STORAGE_KEY = 'matcha-inventory-waste-guide-v1:company-1'

function Guide({ open }: { open: boolean }) {
  return (
    <InventoryWasteGuide
      open={open}
      autoOpenKey="company-1"
      onClose={() => undefined}
    />
  )
}

describe('InventoryWasteGuide persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps a manually reopened guide open when its next step changes routes', async () => {
    localStorage.setItem(STORAGE_KEY, '1')
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/work/inventory/waste?inventoryGuideStep=2#waste-review']}>
        <Routes>
          <Route path="/work/inventory/waste" element={<Guide open />} />
          <Route path="/work/inventory" element={<Guide open={false} />} />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /next/i }))

    expect(await screen.findByText('Make perishability visible')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Skip guide' }))
    expect(screen.queryByText('Waste & predictive PAR guide')).not.toBeInTheDocument()
  })

  it('uses the session marker when local storage cannot be read', () => {
    sessionStorage.setItem(STORAGE_KEY, '1')
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => { throw new DOMException('blocked', 'SecurityError') }),
      setItem: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/work/inventory']}>
        <Guide open={false} />
      </MemoryRouter>,
    )

    expect(screen.queryByText('Waste & predictive PAR guide')).not.toBeInTheDocument()
  })
})
