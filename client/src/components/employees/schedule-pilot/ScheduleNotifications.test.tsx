import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SalesSetupStatus } from '../../../types/scheduleSales'
import ScheduleNotifications from './ScheduleNotifications'

const api = vi.hoisted(() => ({ fetchSalesSetup: vi.fn(), registerSalesSender: vi.fn(), authorizeSalesSquare: vi.fn() }))
vi.mock('../../../api/employees/scheduleSales', () => api)

const EMPTY: SalesSetupStatus = {
  location_id: 'loc1', days_with_sales: 0, latest_sales_date: null, draft_imports: 0,
  square_configured: true, square_connected: false, square_bound: false, square_sync_enabled: false,
  mailbox_configured: false, mailbox_address: null, email_registered: false, email_poll_enabled: false,
}
const props = { locationId: 'loc1', locationName: 'Downtown', canManage: true, salesEnabled: true, hasProposal: false, onOpenReview: vi.fn() }

beforeEach(() => {
  vi.resetAllMocks()
  api.fetchSalesSetup.mockResolvedValue(EMPTY)
  api.registerSalesSender.mockResolvedValue({ id: 'source-1' })
})

function panel(overrides: Partial<typeof props> = {}) {
  return <MemoryRouter><ScheduleNotifications {...props} {...overrides} /></MemoryRouter>
}

describe('Schedule notifications', () => {
  it('explains missing actual sales and links to the store setup without claiming a chat imported data', async () => {
    render(panel())
    expect(await screen.findByText('Sales data is not available yet')).toBeInTheDocument()
    expect(screen.getByText(/Chat messages alone do not import sales/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Square setup & sales imports' })).toHaveAttribute('href', '/ops/inventory?setup=sales&location=loc1')
    expect(screen.getByText(/Automatic Square sync is paused/)).toBeInTheDocument()
    expect(screen.getByText(/Nightly email intake is not ready/)).toBeInTheDocument()
    expect(api.fetchSalesSetup).toHaveBeenCalledWith('loc1')
  })

  it('registers the nightly sender for the selected store and rechecks readiness', async () => {
    render(panel())
    await screen.findByText('Sales data is not available yet')
    api.fetchSalesSetup.mockResolvedValue({ ...EMPTY, email_registered: true })
    fireEvent.change(screen.getByLabelText('POS report sender email'), { target: { value: 'reports@example.com' } })
    fireEvent.change(screen.getByLabelText('Subject must contain (optional)'), { target: { value: 'Daily sales' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register sales sender' }))
    await screen.findByText('A sales sender is registered for this store.')
    expect(api.registerSalesSender).toHaveBeenCalledWith('loc1', 'reports@example.com', 'Daily sales')
    expect(screen.getByText(/Registering a sender alone does not activate it/)).toBeInTheDocument()
  })

  it('shows received sales independently of connection configuration and calls out draft imports', async () => {
    api.fetchSalesSetup.mockResolvedValue({ ...EMPTY, days_with_sales: 5, latest_sales_date: '2026-10-16', draft_imports: 2, square_connected: true })
    render(panel())
    await screen.findByText('Daily sales have been received')
    expect(screen.getByText(/Latest business date: 2026-10-16/)).toBeInTheDocument()
    expect(screen.getByText(/2 sales import\(s\) need mapping or review/)).toBeInTheDocument()
    expect(screen.getByText(/Link this store before sales can arrive/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Connect Square' })).not.toBeInTheDocument()
  })

  it('shows the receiving inbox only when configured and processing is enabled', async () => {
    api.fetchSalesSetup.mockResolvedValue({ ...EMPTY, square_bound: true, square_sync_enabled: true, mailbox_configured: true, mailbox_address: 'sales@example.com', email_poll_enabled: true })
    render(panel())
    expect(await screen.findByText('sales@example.com')).toBeInTheDocument()
    expect(screen.getByText('Square is connected and this store is linked.')).toBeInTheDocument()
    expect(screen.queryByText(/paused|Nightly email intake is not ready/)).not.toBeInTheDocument()
  })

  it('does not call protected sales endpoints for managers or plans without sales intake', () => {
    const view = render(panel({ salesEnabled: false }))
    expect(screen.getByText(/Sales intake is not enabled for this account/)).toBeInTheDocument()
    view.rerender(panel({ canManage: false }))
    expect(screen.getByText(/A company admin can connect the POS/)).toBeInTheDocument()
    expect(api.fetchSalesSetup).not.toHaveBeenCalled()
  })

  it('treats a failed setup read as unknown and offers a retry', async () => {
    api.fetchSalesSetup.mockRejectedValueOnce(new Error('Offline'))
    render(panel())
    expect(await screen.findByRole('alert')).toHaveTextContent('Sales setup could not be checked')
    expect(screen.queryByText('Sales data is not available yet')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry sales check' }))
    await screen.findByText('Sales data is not available yet')
  })

  it('keeps sender failures visible and permits another attempt', async () => {
    api.registerSalesSender.mockRejectedValueOnce(new Error('That sender is already registered.'))
    render(panel())
    await screen.findByText('Sales data is not available yet')
    fireEvent.change(screen.getByLabelText('POS report sender email'), { target: { value: 'reports@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register sales sender' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That sender is already registered.')
    expect(screen.getByRole('button', { name: 'Register sales sender' })).toBeEnabled()
  })

  it('prevents unconfigured Square connections and displays authorization failures', async () => {
    api.fetchSalesSetup.mockResolvedValueOnce({ ...EMPTY, square_configured: false })
    render(panel())
    await screen.findByText('Sales data is not available yet')
    expect(screen.getByRole('button', { name: 'Connect Square' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Recheck sales setup' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Connect Square' })).toBeEnabled())
    api.authorizeSalesSquare.mockRejectedValue(new Error('Square is unavailable'))
    fireEvent.click(screen.getByRole('button', { name: 'Connect Square' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Square is unavailable')
    expect(screen.getByRole('button', { name: 'Connect Square' })).toBeEnabled()
  })

  it('ignores a stale setup response after the store changes', async () => {
    let resolveOld!: (value: SalesSetupStatus) => void
    api.fetchSalesSetup.mockReturnValueOnce(new Promise<SalesSetupStatus>((resolve) => { resolveOld = resolve }))
    const view = render(panel())
    view.rerender(panel({ locationId: 'loc2', locationName: 'Mission' }))
    await screen.findByText('Sales data is not available yet')
    await act(async () => { resolveOld({ ...EMPTY, days_with_sales: 50 }) })
    expect(screen.queryByText('Daily sales have been received')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Square setup & sales imports' })).toHaveAttribute('href', '/ops/inventory?setup=sales&location=loc2')
  })

  it('directs a generated proposal to review without applying or publishing it', () => {
    render(panel({ canManage: false, hasProposal: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Review schedule proposal' }))
    expect(props.onOpenReview).toHaveBeenCalledOnce()
    expect(screen.getByText(/confirm it to create draft shifts/)).toBeInTheDocument()
  })
})
