import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { RosterEmployee, ScheduleReview, Shift } from '../../../types/employeeSchedule'
import WeekRosterGrid from './WeekRosterGrid'

const DAYS = ['2026-09-14', '2026-09-15', '2026-09-16']

const person = (id: string, name: string): RosterEmployee => ({ id, name, job_title: 'Barista', department: null, job_ids: [] })

const shift = (id: string, date: string, people: Array<[string, string]>, extra: Partial<Shift> = {}): Shift => ({
  id, starts_at: `${date}T06:30:00Z`, ends_at: `${date}T13:30:00Z`, role: 'Barista', status: 'published',
  required_staff: Math.max(people.length, 1), break_minutes: 30, kind: 'work',
  assignments: people.map(([employee_id, name]) => ({ employee_id, name, job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null })),
  ...extra,
} as unknown as Shift)

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1', kind: 'edit', compliance_status: 'verified',
    assignments: [], rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'On file.' }, ...overrides,
  }
}

function renderGrid(props: Partial<React.ComponentProps<typeof WeekRosterGrid>> = {}) {
  const handlers = { onOpenShift: vi.fn(), onToggleHuumeSelection: vi.fn(), onSelectEmployee: vi.fn(), onCreateFor: vi.fn() }
  render(
    <WeekRosterGrid
      days={DAYS}
      shifts={[]}
      roster={[person('e1', 'Ellie Marsh'), person('e2', 'Maria Rossi')]}
      selectedEmployeeId={null}
      huumeSelectedShiftIds={new Set()}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

const row = (name: string) => screen.getByRole('rowheader', { name: new RegExp(name) }).closest('[role="row"]') as HTMLElement

describe('WeekRosterGrid', () => {
  it('lays the week out by person with their hours, busiest-first, and opens a shift on click', () => {
    const handlers = renderGrid({
      shifts: [shift('s1', '2026-09-15', [['e2', 'Maria Rossi']]), shift('s2', '2026-09-14', [['e2', 'Maria Rossi']])],
    })
    const rows = screen.getAllByRole('rowheader').map((cell) => cell.textContent)
    expect(rows[0]).toMatch(/^Maria Rossi13h/)
    expect(rows[1]).toMatch(/^Ellie Marsh/)
    fireEvent.click(within(row('Maria Rossi')).getAllByText('6:30a–1:30p')[0])
    expect(handlers.onOpenShift).toHaveBeenCalledWith(expect.objectContaining({ id: 's2' }))
  })

  it('puts unfilled seats in their own row, selectable for Huume', () => {
    const handlers = renderGrid({ shifts: [shift('s1', '2026-09-14', [], { required_staff: 2 })] })
    const open = row('Open seats')
    expect(within(open).getByText('Barista · 2 open')).toBeInTheDocument()
    fireEvent.click(within(open).getByRole('button', { name: 'Select Barista for Huume' }))
    expect(handlers.onToggleHuumeSelection).toHaveBeenCalled()
  })

  it('draws a proposal in place: who it adds, who it removes, and the new hours', () => {
    renderGrid({
      shifts: [shift('s1', '2026-09-14', [['e1', 'Ellie Marsh']], { required_staff: 2 })],
      review: review({ assignments: [
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e2', employee_name: 'Maria Rossi', op: 'assign', verdict: 'ok', reasons: [] },
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e1', employee_name: 'Ellie Marsh', op: 'unassign', verdict: 'ok', reasons: [] },
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e2', employee_name: 'Blocked', op: 'assign', verdict: 'blocked', reasons: [] },
      ] }),
      marks: new Map([['s1', { warn: false, chips: [{ tone: 'add', label: '+ Maria' }] }]]),
    })
    expect(within(row('Maria Rossi')).getByRole('img', { name: 'Proposed Barista 6:30a–1:30p: Maria Rossi' })).toBeInTheDocument()
    expect(within(row('Maria Rossi')).getByText(/→ 7h/)).toBeInTheDocument()
    expect(within(row('Ellie Marsh')).getByText('6:30a–1:30p').closest('div')).toHaveClass('line-through')
  })

  it('places a generated week on the people it names, adding a row for a name not on the roster', () => {
    renderGrid({
      previewShifts: [
        { id: 'p1', starts_at: '2026-09-16T09:00:00Z', ends_at: '2026-09-16T17:00:00Z', role: 'Opener', names: ['Ellie Marsh', 'Sam Ferreira'], open: 1, warn: false, reasons: [] },
      ],
    })
    expect(within(row('Ellie Marsh')).getByRole('img', { name: /^Proposed Opener 9a–5p: Ellie Marsh$/ })).toBeInTheDocument()
    expect(within(row('Sam Ferreira')).getByRole('img', { name: /Sam Ferreira$/ })).toBeInTheDocument()
    expect(within(row('Open seats')).getByText('Opener · 1 unfilled')).toBeInTheDocument()
    // A preview-only name has no record to schedule against.
    expect(within(row('Sam Ferreira')).queryByRole('button', { name: /Add a shift/ })).not.toBeInTheDocument()
  })

  it('adds a shift from an empty cell and selects a person from their name', () => {
    const handlers = renderGrid()
    fireEvent.click(screen.getByRole('button', { name: 'Add a shift for Ellie Marsh on Tue 9/15' }))
    expect(handlers.onCreateFor).toHaveBeenCalledWith('2026-09-15', 'e1')
    fireEvent.click(screen.getByRole('button', { name: /Ellie Marsh/, pressed: false }))
    expect(handlers.onSelectEmployee).toHaveBeenCalledWith('e1')
  })

  it('outlines a recently changed shift and lists someone on a shift who is not on the roster', () => {
    renderGrid({
      shifts: [shift('s1', '2026-09-14', [['e9', 'Visiting Vic']], { status: 'draft' })],
      recentShiftIds: new Set(['s1']),
      selectedEmployeeId: 'e9',
    })
    expect(within(row('Visiting Vic')).getByText('Just changed')).toBeInTheDocument()
    expect(row('Ellie Marsh')).toHaveClass('opacity-50')
  })
})
