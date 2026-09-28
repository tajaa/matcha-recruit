import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BreakReminderEvent } from '../../types/employeeSchedule'

const { eventsMock, optionsMock } = vi.hoisted(() => ({ eventsMock: vi.fn(), optionsMock: vi.fn() }))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchBreakReminderEvents: eventsMock,
  fetchBreakReminderFilterOptions: optionsMock,
}))

import BreakReminderDeliveryLog from './BreakReminderDeliveryLog'
import { reminderText, wallClock } from './breakReminderFormat'

const LOCATION = { id: 'loc-1', name: 'Downtown', timezone: 'America/Los_Angeles' }

function event(overrides: Partial<BreakReminderEvent>): BreakReminderEvent {
  return {
    id: crypto.randomUUID(),
    occurred_at: '2026-09-23T18:58:00+00:00',
    event_date: '2026-09-23',
    channel: 'push',
    reminder_type: 'break_start',
    recipient_type: 'employee',
    recipient: null,
    employee: { id: 'emp-1', name: 'Ana Ruiz' },
    covered_employee_count: 1,
    location: LOCATION,
    shift_id: 'shift-1',
    break: { kind: 'meal', start_local: '2026-09-23T12:00:00', duration_minutes: 30 },
    context: {},
    outcome: 'accepted',
    outcome_detail: 'Accepted by Apple Push Notification service for 1 device(s)',
    ...overrides,
  }
}

describe('BreakReminderDeliveryLog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    optionsMock.mockResolvedValue({
      locations: [{ id: 'loc-1', name: 'Downtown' }, { id: 'loc-2', name: 'Mission' }],
      employees: [{ id: 'emp-1', name: 'Ana Ruiz' }, { id: 'emp-2', name: 'Bo Kim' }],
    })
  })

  it('distinguishes accepted, failed and unavailable, and says what delivery does not prove', async () => {
    eventsMock.mockResolvedValue({
      total: 3,
      events: [
        event({}),
        event({ channel: 'email', reminder_type: 'daily_digest', recipient: 'ana@example.com', break: null, outcome: 'failed', outcome_detail: null,
          context: { breaks: [{ kind: 'rest', start_local: '2026-09-23T15:10:00', duration_minutes: 10 }] } }),
        event({ outcome: 'unavailable', outcome_detail: 'No Matcha Schedule device registered' }),
      ],
    })

    render(<BreakReminderDeliveryLog />)

    const table = await screen.findByRole('table')
    const statuses = within(table).getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[5].textContent)
    expect(statuses).toEqual(['Accepted by provider', 'Failed', 'Unavailable'])
    expect(within(table).getByText('No details reported')).toBeInTheDocument()
    expect(screen.getByText('Daily digest · Rest 3:10 PM (10 min)')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('not that the employee received or read it, and not that a break was taken')
    expect(screen.getByText('Showing all locations, employees and dates. Dates are each location\'s calendar day.')).toBeInTheDocument()
    expect(eventsMock).toHaveBeenCalledWith({ limit: 50, offset: 0 })
  })

  it('filters by location, employee and an inclusive date range together and shows them', async () => {
    const user = userEvent.setup()
    eventsMock.mockResolvedValue({ total: 0, events: [] })
    render(<BreakReminderDeliveryLog />)
    await waitFor(() => expect(screen.getByText('No break reminders have been sent yet.')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('option', { name: 'Mission' })).toBeInTheDocument())

    await user.selectOptions(screen.getByLabelText('Location'), 'loc-2')
    await user.selectOptions(screen.getByLabelText('Employee'), 'emp-2')
    await user.type(screen.getByLabelText('From'), '2026-09-01')
    await user.type(screen.getByLabelText('To (inclusive)'), '2026-09-01')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(eventsMock).toHaveBeenLastCalledWith({
      locationId: 'loc-2', employeeId: 'emp-2', start: '2026-09-01', end: '2026-09-01', limit: 50, offset: 0,
    }))
    expect(screen.getByText(/Filtered by Location: Mission · Employee: Bo Kim · Dates: Sep 1, 2026 – Sep 1, 2026 \(inclusive\)/)).toBeInTheDocument()
    expect(screen.getByText('No break reminder deliveries match these filters.')).toBeInTheDocument()
  })

  it('refuses an inverted range without querying', async () => {
    const user = userEvent.setup()
    eventsMock.mockResolvedValue({ total: 0, events: [] })
    render(<BreakReminderDeliveryLog />)
    await waitFor(() => expect(eventsMock).toHaveBeenCalledTimes(1))

    await user.type(screen.getByLabelText('From'), '2026-09-02')
    await user.type(screen.getByLabelText('To (inclusive)'), '2026-09-01')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    expect(screen.getByRole('alert')).toHaveTextContent('The "To" date must be on or after the "From" date.')
    expect(eventsMock).toHaveBeenCalledTimes(1)
  })

  it('shows a load failure instead of an empty history', async () => {
    eventsMock.mockRejectedValue({ body: { detail: 'End date must be on or after the start date' } })
    render(<BreakReminderDeliveryLog />)
    await waitFor(() => expect(screen.getByText('End date must be on or after the start date')).toBeInTheDocument())
    expect(screen.queryByText('No break reminders have been sent yet.')).not.toBeInTheDocument()
  })

  it('pages through the history', async () => {
    const user = userEvent.setup()
    eventsMock.mockResolvedValue({ total: 120, events: [event({})] })
    render(<BreakReminderDeliveryLog />)
    await waitFor(() => expect(screen.getByText('Showing 1–50 of 120')).toBeInTheDocument())

    expect(screen.getByRole('button', { name: 'Previous delivery page' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next delivery page' }))

    await waitFor(() => expect(eventsMock).toHaveBeenLastCalledWith({ limit: 50, offset: 50 }))
    await waitFor(() => expect(screen.getByText('Showing 51–100 of 120')).toBeInTheDocument())
  })

  it('renders a manager digest as location-wide, naming how many employees it covered', async () => {
    eventsMock.mockResolvedValue({
      total: 1,
      events: [event({ reminder_type: 'daily_digest', channel: 'email', recipient_type: 'manager', recipient: 'lead@example.com',
        employee: null, break: null, covered_employee_count: 3, context: { employees_with_break_content: 3 } })],
    })
    render(<BreakReminderDeliveryLog />)
    const row = (await screen.findByText('Supervisor')).closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText("Daily digest · lists 3 employees' breaks")).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('lead@example.com')).toBeInTheDocument()
  })
})

describe('break reminder formatting', () => {
  it('reads the wall clock characters without converting time zones', () => {
    expect(wallClock('2026-09-23T00:05:00')).toBe('12:05 AM')
    expect(wallClock('2026-09-23T12:00:00-07:00')).toBe('12:00 PM')
    expect(wallClock(null)).toBe('—')
  })

  it('describes a break-start push by kind, time and length', () => {
    expect(reminderText(event({ break: { kind: 'rest', start_local: '2026-09-23T15:10:00', duration_minutes: 10 } })))
      .toBe('Break start · Rest 3:10 PM (10 min)')
  })
})
