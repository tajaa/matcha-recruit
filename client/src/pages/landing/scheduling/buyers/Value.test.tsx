import type { ReactNode } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Value } from './Value'
import { Pricing } from './Pricing'

vi.mock('../../../../components/marketing/kit/motion', () => ({ Reveal: ({ children, className }: { children: ReactNode; className?: string }) => <div className={className}>{children}</div> }))
beforeEach(() => vi.clearAllMocks())
const loadExample = () => fireEvent.click(screen.getByRole('button', { name: 'Load café example' }))
const remaining = (name: string) => within(screen.getByRole('group', { name: `Minutes still needed with ${name}` }))

describe('plan value calculator', () => {
  it('starts with no savings and visible instructions', () => {
    render(<Value onContact={vi.fn()} />)
    for (const title of ['Measure your current week', 'Estimate each plan separately', 'Compare the full picture']) expect(screen.getByText(title)).toBeInTheDocument()
    expect(screen.getByTestId('basic-net-value')).toHaveTextContent('−$49')
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent('−$99')
    expect(screen.getByTestId('autopilot-net-value')).toHaveTextContent('−$149')
  })
  it('loads a labeled example with separate plan savings and no invented labor savings', () => {
    render(<Value onContact={vi.fn()} />)
    loadExample()
    expect(screen.getByRole('status', { name: 'Scenario' })).toHaveTextContent('illustrative assumptions, not measured customer results')
    expect(screen.getByTestId('basic-net-value')).toHaveTextContent('$179')
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent('$280')
    expect(screen.getByTestId('autopilot-net-value')).toHaveTextContent('$559')
    expect(screen.getByTestId('pro-net-cash')).toHaveTextContent('−$99')
  })
  it('keeps each plan edit when switching and retains unsupported Basic cost-review work', async () => {
    const user = userEvent.setup()
    render(<Value onContact={vi.fn()} />)
    loadExample()
    fireEvent.change(remaining('Pro').getByLabelText('Building and reviewing the schedule'), { target: { value: '120' } })
    const proValue = screen.getByTestId('pro-net-value').textContent
    await user.click(screen.getByRole('button', { name: 'Edit Basic assumptions' }))
    expect(remaining('Basic').getByLabelText('Building and reviewing the schedule')).toHaveValue(180)
    expect(remaining('Basic').getByLabelText('Reviewing labor cost and overtime')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Edit Pro assumptions' }))
    expect(remaining('Pro').getByLabelText('Building and reviewing the schedule')).toHaveValue(120)
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent(proValue!)
  })
  it('assumes unchanged time for blank plan fields and calculates cancellation per plan', () => {
    render(<Value onContact={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Value of manager time ($ / hour)'), { target: { value: '35' } })
    fireEvent.change(within(screen.getByRole('group', { name: 'Manager minutes / week / location' })).getByLabelText('Building and reviewing the schedule'), { target: { value: '240' } })
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent('−$99')
    fireEvent.change(screen.getByLabelText('Current scheduler ($ / month / location)'), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Cancel my current scheduler with Pro/ }))
    expect(screen.getByTestId('pro-net-cash')).toHaveTextContent('−$59')
    expect(screen.getByTestId('basic-net-cash')).toHaveTextContent('−$49')
  })
  it('shows cleared and fractional-location input errors without plausible totals', () => {
    render(<Value onContact={vi.fn()} />)
    loadExample()
    fireEvent.change(screen.getByLabelText('Locations to include'), { target: { value: '1.5' } })
    expect(screen.getByRole('alert')).toHaveTextContent('whole number')
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent('—')
    fireEvent.change(screen.getByLabelText('Locations to include'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Value of manager time ($ / hour)'), { target: { value: '' } })
    expect(screen.getByTestId('pro-net-value')).toHaveTextContent('—')
  })
  it('requires an hourly cost before displaying claimed labor savings', () => {
    render(<Value onContact={vi.fn()} />)
    fireEvent.click(screen.getByText(/Add measured paid-labor savings/))
    fireEvent.change(screen.getByLabelText('Regular paid hours removed / week / location'), { target: { value: '2' } })
    expect(screen.getByRole('alert')).toHaveTextContent('regular staff cost above $0')
    expect(screen.getByTestId('pro-net-cash')).toHaveTextContent('—')
    fireEvent.change(screen.getByLabelText('Regular staff cost ($ / hour)'), { target: { value: '20' } })
    expect(screen.getByTestId('pro-net-cash')).toHaveTextContent('$74')
  })
  it('describes extra work without presenting it as savings and announces the selected result', () => {
    render(<Value onContact={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Value of manager time ($ / hour)'), { target: { value: '35' } })
    fireEvent.change(remaining('Pro').getByLabelText('Building and reviewing the schedule'), { target: { value: '60' } })
    expect(within(screen.getByRole('article', { name: 'Pro estimate' })).getByText('1 extra')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Selected plan result' })).toHaveTextContent('−$250.67 net monthly value; −$99.00 net monthly cash')
  })
  it('scales recurring totals while deducting business onboarding time from value only', () => {
    render(<Value onContact={vi.fn()} />)
    loadExample()
    fireEvent.change(screen.getByLabelText('Locations to include'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('One-time switching spend ($ / business)'), { target: { value: '300' } })
    fireEvent.change(screen.getByLabelText('Manager onboarding hours / business'), { target: { value: '6' } })
    expect(screen.getByText('$6,214')).toBeInTheDocument()
    expect(screen.getByText('−$2,676')).toBeInTheDocument()
  })
  it('clears all plan assumptions and opens consultation', () => {
    const contact = vi.fn()
    render(<Value onContact={contact} />)
    loadExample()
    fireEvent.click(screen.getByRole('button', { name: 'Clear assumptions' }))
    expect(screen.getByTestId('autopilot-net-value')).toHaveTextContent('−$149')
    expect(remaining('Pro').getByLabelText('Building and reviewing the schedule')).toHaveValue(null)
    fireEvent.click(screen.getByRole('button', { name: 'Discuss my assumptions' }))
    expect(contact).toHaveBeenCalledOnce()
  })
  it('preserves the proposed pricing shown alongside the calculator', () => {
    render(<Pricing onContact={vi.fn()} />)
    for (const price of ['49', '99', '149']) expect(screen.getByText(price)).toBeInTheDocument()
  })
})
