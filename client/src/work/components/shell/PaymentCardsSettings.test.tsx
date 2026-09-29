import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import PaymentCardsSettings from './PaymentCardsSettings'
import { ApiError } from '../../../api/client'

const mock = vi.hoisted(() => ({ list: vi.fn(), add: vi.fn(), remove: vi.fn() }))
vi.mock('../../api/matchaWork', async () => ({
  ...(await vi.importActual<typeof import('../../api/matchaWork/agentCards')>('../../api/matchaWork/agentCards')),
  listPaymentCards: mock.list,
  addPaymentCard: mock.add,
  deletePaymentCard: mock.remove,
}))

const card = { id: 'c1', label: 'Mercury test', brand: 'visa', last4: '4242', exp_month: 3, exp_year: 2031, created_at: null }

beforeEach(() => vi.clearAllMocks())

describe('PaymentCardsSettings', () => {
  it('lists saved cards by brand and last 4 only, and removes one', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: true, cards: [card] })
    mock.remove.mockResolvedValue(undefined)
    render(<PaymentCardsSettings isAdmin />)
    expect(await screen.findByText(/Visa ending 4242/)).toBeTruthy()
    expect(screen.getByText(/03\/31/)).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Remove card ending 4242'))
    await waitFor(() => expect(mock.remove).toHaveBeenCalledWith('c1'))
  })

  it('saves a card with no security-code field and clears the number', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: true, cards: [] })
    mock.add.mockResolvedValue(card)
    render(<PaymentCardsSettings isAdmin />)
    const number = await screen.findByLabelText('Card number')
    expect(screen.queryByLabelText(/CVV|CVC|security/i)).toBeNull()
    fireEvent.change(number, { target: { value: '4242 4242 4242 4242' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '03/31' } })
    fireEvent.change(screen.getByLabelText('Label (optional)'), { target: { value: 'Mercury test' } })
    fireEvent.click(screen.getByText('Save card'))
    await waitFor(() => expect(mock.add).toHaveBeenCalledWith({
      number: '4242 4242 4242 4242', exp_month: 3, exp_year: 2031, label: 'Mercury test',
    }))
    expect(await screen.findByText('Card saved.')).toBeTruthy()
    expect((screen.getByLabelText('Card number') as HTMLInputElement).value).toBe('')
  })

  it('checks the expiry format before sending anything', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: true, cards: [] })
    render(<PaymentCardsSettings isAdmin />)
    fireEvent.change(await screen.findByLabelText('Card number'), { target: { value: '4242424242424242' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: 'next year' } })
    fireEvent.click(screen.getByText('Save card'))
    expect(await screen.findByText('Enter the expiry as MM/YY.')).toBeTruthy()
    expect(mock.add).not.toHaveBeenCalled()
  })

  it('shows the server refusal', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: true, cards: [] })
    mock.add.mockRejectedValue(new ApiError('400', 400, { detail: "That isn't a valid card number." }))
    render(<PaymentCardsSettings isAdmin />)
    fireEvent.change(await screen.findByLabelText('Card number'), { target: { value: '4242424242424241' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '3/2031' } })
    fireEvent.click(screen.getByText('Save card'))
    expect(await screen.findByText("That isn't a valid card number.")).toBeTruthy()
  })

  it('says so when card storage is not configured', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: false, cards: [] })
    render(<PaymentCardsSettings isAdmin />)
    expect(await screen.findByText(/Card storage isn't set up/)).toBeTruthy()
    expect(screen.queryByLabelText('Card number')).toBeNull()
  })

  it('renders nothing when buying is not enabled and no cards exist', async () => {
    mock.list.mockResolvedValue({ enabled: false, configured: true, cards: [] })
    const { container } = render(<PaymentCardsSettings isAdmin />)
    await waitFor(() => expect(mock.list).toHaveBeenCalled())
    await waitFor(() => expect(container.querySelector('section')).toBeNull())
  })
})

describe('PaymentCardsSettings load failure', () => {
  it('shows the error with a retry instead of disappearing', async () => {
    mock.list.mockRejectedValueOnce(new Error('Server is updating.'))
    mock.list.mockResolvedValueOnce({ enabled: true, configured: true, cards: [card] })
    render(<PaymentCardsSettings isAdmin />)
    expect(await screen.findByText(/Couldn't load your cards: Server is updating\./)).toBeTruthy()
    fireEvent.click(screen.getByText('Retry'))
    expect(await screen.findByText(/Visa ending 4242/)).toBeTruthy()
  })
})

describe('PaymentCardsSettings for non-admins', () => {
  it('shows the section when the server enables buying for this account', async () => {
    mock.list.mockResolvedValue({ enabled: true, configured: true, cards: [] })
    render(<PaymentCardsSettings />)
    expect(await screen.findByLabelText('Card number')).toBeTruthy()
  })

  it('shows nothing while loading or when the load fails', async () => {
    mock.list.mockRejectedValue(new Error('boom'))
    const { container } = render(<PaymentCardsSettings />)
    await waitFor(() => expect(mock.list).toHaveBeenCalled())
    expect(container.querySelector('section')).toBeNull()
  })
})
