import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ShippingAddressesSettings from './ShippingAddressesSettings'
import { ApiError } from '../../../api/client'

const mock = vi.hoisted(() => ({ list: vi.fn(), add: vi.fn(), update: vi.fn(), remove: vi.fn() }))
vi.mock('../../api/matchaWork', async () => ({
  ...(await vi.importActual<typeof import('../../api/matchaWork/agentCards')>('../../api/matchaWork/agentCards')),
  listShippingAddresses: mock.list,
  addShippingAddress: mock.add,
  updateShippingAddress: mock.update,
  deleteShippingAddress: mock.remove,
}))

const home = {
  id: 'a1', name: 'Haley Smith', line1: '1 Main St', line2: '', city: 'Oakland', region: 'CA',
  postal_code: '94607', country: 'US', phone: '', is_default: true, created_at: null,
}
const office = { ...home, id: 'a2', line1: '2 Work Ave', is_default: false }

beforeEach(() => vi.clearAllMocks())

function fill() {
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Haley Smith' } })
  fireEvent.change(screen.getByLabelText('Street address'), { target: { value: '1 Main St' } })
  fireEvent.change(screen.getByLabelText('City'), { target: { value: 'Oakland' } })
  fireEvent.change(screen.getByLabelText('State'), { target: { value: 'CA' } })
  fireEvent.change(screen.getByLabelText('ZIP'), { target: { value: '94607' } })
}

describe('ShippingAddressesSettings', () => {
  it('lists addresses with the default marked, and adds one', async () => {
    mock.list.mockResolvedValue({ enabled: true, addresses: [home] })
    mock.add.mockResolvedValue(home)
    render(<ShippingAddressesSettings isAdmin />)
    expect(await screen.findByText(/Haley Smith, 1 Main St, Oakland, CA 94607, US/)).toBeTruthy()
    expect(screen.getByText('Default')).toBeTruthy()
    fireEvent.click(screen.getByText('Add an address'))
    fill()
    fireEvent.change(screen.getByLabelText('Country code'), { target: { value: 'us' } })
    fireEvent.click(screen.getByText('Save address'))
    await waitFor(() => expect(mock.add).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Haley Smith', line1: '1 Main St', region: 'CA', postal_code: '94607', country: 'US',
    })))
    expect(await screen.findByText('Address saved.')).toBeTruthy()
  })

  it('makes another address the default and removes one', async () => {
    mock.list.mockResolvedValue({ enabled: true, addresses: [home, office] })
    mock.update.mockResolvedValue({ ...office, is_default: true })
    mock.remove.mockResolvedValue(undefined)
    render(<ShippingAddressesSettings isAdmin />)
    fireEvent.click(await screen.findByLabelText('Make 2 Work Ave the default'))
    await waitFor(() => expect(mock.update).toHaveBeenCalledWith('a2', expect.objectContaining({ is_default: true })))
    fireEvent.click(screen.getByLabelText('Remove address 1 Main St'))
    await waitFor(() => expect(mock.remove).toHaveBeenCalledWith('a1'))
  })

  it('shows the server refusal', async () => {
    mock.list.mockResolvedValue({ enabled: true, addresses: [] })
    mock.add.mockRejectedValue(new ApiError('400', 400, { detail: "That isn't a valid ZIP code." }))
    render(<ShippingAddressesSettings isAdmin />)
    fireEvent.click(await screen.findByText('Add an address'))
    fill()
    fireEvent.click(screen.getByText('Save address'))
    expect(await screen.findByText("That isn't a valid ZIP code.")).toBeTruthy()
  })

  it('renders nothing when buying is not enabled and no addresses exist', async () => {
    mock.list.mockResolvedValue({ enabled: false, addresses: [] })
    const { container } = render(<ShippingAddressesSettings />)
    await waitFor(() => expect(mock.list).toHaveBeenCalled())
    await waitFor(() => expect(container.querySelector('section')).toBeNull())
  })
})
