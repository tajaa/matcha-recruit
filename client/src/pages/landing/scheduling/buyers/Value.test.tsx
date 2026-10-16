import type { ReactNode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Value } from './Value'
import { Pricing } from './Pricing'
import { MemoryRouter } from 'react-router-dom'
import { SCHEDULING_SIGNUP_PATH } from '../signup'

vi.mock('../../../../components/marketing/kit/motion', () => ({ Reveal: ({ children, className }: { children: ReactNode; className?: string }) => <div className={className}>{children}</div> }))
beforeEach(() => vi.clearAllMocks())
const set = (label: RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('value calculator', () => {
  it('asks for three numbers and shows a result straight away', () => {
    render(<Value onContact={vi.fn()} />)
    expect(screen.getAllByRole('spinbutton')).toHaveLength(3)
    expect(screen.getByLabelText('Number of locations')).toHaveValue(1)
    expect(screen.getByTestId('current-monthly')).toHaveTextContent('$433')
    expect(screen.getByTestId('subscription')).toHaveTextContent('$149')
    expect(screen.getByTestId('break-even')).toHaveTextContent('83 minutes a week')
    expect(screen.getByText(/Assumes Autopilot, our highest plan/)).toBeInTheDocument()
  })
  it('updates as the numbers change and scales with locations', () => {
    render(<Value onContact={vi.fn()} />)
    set(/Number of locations/, '3')
    set(/Average hourly wage/, '30')
    set(/Time spent building the schedule/, '5')
    expect(screen.getByTestId('current-monthly')).toHaveTextContent('$1,950')
    expect(screen.getByTestId('hours-monthly')).toHaveTextContent('65')
    expect(screen.getByTestId('subscription')).toHaveTextContent('$447')
    expect(screen.getByText(/across 3 locations/)).toBeInTheDocument()
    expect(screen.getByTestId('break-even')).toHaveTextContent('69 minutes a week per location, out of the 300 you spend now')
  })
  it('does not present a win when the time entered cannot cover the plan', () => {
    render(<Value onContact={vi.fn()} />)
    set(/Time spent building the schedule/, '1')
    expect(screen.getByTestId('break-even')).toHaveTextContent('it would not pay for itself')
  })
  it('shows input errors without plausible totals', () => {
    render(<Value onContact={vi.fn()} />)
    set(/Number of locations/, '1.5')
    expect(screen.getByRole('alert')).toHaveTextContent('whole number')
    expect(screen.getByTestId('current-monthly')).toHaveTextContent('—')
    set(/Number of locations/, '1')
    set(/Average hourly wage/, '')
    expect(screen.getByTestId('current-monthly')).toHaveTextContent('—')
    set(/Average hourly wage/, '0')
    expect(screen.getByTestId('break-even')).toHaveTextContent('Enter an hourly wage above $0')
  })
  it('opens consultation', () => {
    const contact = vi.fn()
    render(<Value onContact={contact} />)
    fireEvent.click(screen.getByRole('button', { name: 'Talk through my numbers' }))
    expect(contact).toHaveBeenCalledOnce()
  })
  it('prices the estimate at the live checkout price once it loads', () => {
    render(<Value onContact={vi.fn()} livePrice={{ name: 'Matcha S&C', perLocation: 45.5 }} />)
    set(/Number of locations/, '2')
    expect(screen.getByTestId('subscription')).toHaveTextContent('$91')
    expect(screen.getByText(/Assumes Matcha S&C at checkout · \$45\.50 \/ location \/ month/)).toBeInTheDocument()
  })
  it('offers the live price with a Start now link to the signup', () => {
    render(<MemoryRouter><Pricing onContact={vi.fn()} livePrice={{ name: 'Matcha S&C', perLocation: 50 }} /></MemoryRouter>)
    expect(screen.getByTestId('live-price')).toHaveTextContent('Start today at $50 per location, per month.')
    expect(screen.getByRole('link', { name: /Start now/ })).toHaveAttribute('href', SCHEDULING_SIGNUP_PATH)
  })
  it('shows no live price before it loads', () => {
    render(<Pricing onContact={vi.fn()} />)
    expect(screen.queryByTestId('live-price')).toBeNull()
  })
  it('preserves the proposed pricing shown alongside the calculator', () => {
    render(<Pricing onContact={vi.fn()} />)
    for (const price of ['49', '99', '149']) expect(screen.getByText(price)).toBeInTheDocument()
  })
})
