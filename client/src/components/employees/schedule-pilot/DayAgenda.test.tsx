import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ScheduleReview, Shift } from '../../../types/employeeSchedule'
import DayAgenda from './DayAgenda'

const DAYS = ['2026-09-13', '2026-09-14', '2026-09-15']

const shift = (id: string, date: string, people: Array<[string, string]>, extra: Partial<Shift> = {}): Shift => ({
  id, starts_at: `${date}T06:30:00Z`, ends_at: `${date}T13:30:00Z`, role: 'Barista', status: 'published',
  required_staff: Math.max(people.length, 1), break_minutes: 0, kind: 'work',
  assignments: people.map(([employee_id, name]) => ({ employee_id, name, job_title: null, status: 'assigned', availability_overridden: false, availability_override_at: null })),
  ...extra,
} as unknown as Shift)

function review(assignments: ScheduleReview['assignments']): ScheduleReview {
  return {
    proposal_id: 'p1', kind: 'edit', compliance_status: 'verified', assignments,
    rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'On file.' },
  }
}

function renderAgenda(props: Partial<React.ComponentProps<typeof DayAgenda>> = {}) {
  const handlers = { onOpenShift: vi.fn(), onToggleHuumeSelection: vi.fn(), onCreateOn: vi.fn() }
  render(<DayAgenda days={DAYS} shifts={[]} huumeSelectedShiftIds={new Set()} {...handlers} {...props} />)
  return handlers
}

describe('DayAgenda', () => {
  it('opens on the first busy day and switches days from the strip', () => {
    renderAgenda({ shifts: [shift('s1', '2026-09-14', [['e1', 'Ellie Marsh']]), shift('s2', '2026-09-15', [], { role: 'Closer' })] })
    expect(screen.getByRole('tab', { name: /Monday, Sep 14, 1 shift/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Ellie Marsh')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Tuesday, Sep 15/ }))
    expect(screen.getByText('Closer')).toBeInTheDocument()
    expect(screen.getByText('1 open')).toBeInTheDocument()
    expect(screen.getByText(/· 1 unfilled/)).toBeInTheDocument()
  })

  it('shows what Huume would change on the card, with an always-visible Huume button', () => {
    const handlers = renderAgenda({
      shifts: [shift('s1', '2026-09-14', [['e1', 'Ellie Marsh']], { required_staff: 2 })],
      review: review([
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e2', employee_name: 'Maria Rossi', op: 'assign', verdict: 'ok', reasons: [] },
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e1', employee_name: 'Ellie Marsh', op: 'unassign', verdict: 'ok', reasons: [] },
        { shift_id: 's1', role: 'Barista', starts_at: null, ends_at: null, employee_id: 'e3', employee_name: 'Nope', op: 'assign', verdict: 'blocked', reasons: [] },
      ]),
      marks: new Map([['s1', { warn: false, chips: [{ tone: 'add', label: '+ Maria' }, { tone: 'move', label: '↻ 7a–2p' }] }]]),
    })
    expect(screen.getByText('+ Maria Rossi')).toBeInTheDocument()
    expect(screen.getByText('Ellie Marsh')).toHaveClass('line-through')
    expect(screen.queryByText(/Nope/)).not.toBeInTheDocument()
    // The add is on the names already; the line carries only what isn't.
    expect(screen.getByLabelText('Proposed by Huume')).toHaveTextContent(/^↻ 7a–2p$/)

    fireEvent.click(screen.getByRole('button', { name: 'Select Barista for Huume' }))
    expect(handlers.onToggleHuumeSelection).toHaveBeenCalled()
    fireEvent.click(screen.getByText('6:30a–1:30p'))
    expect(handlers.onOpenShift).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }))
  })

  it('draws proposed new shifts, tags a just-changed one, and adds a shift on the chosen day', () => {
    const handlers = renderAgenda({
      shifts: [shift('s1', '2026-09-13', [['e1', 'Ellie Marsh']], { status: 'draft' })],
      recentShiftIds: new Set(['s1']),
      previewShifts: [{ id: 'p1', starts_at: '2026-09-13T15:00:00Z', ends_at: '2026-09-13T22:00:00Z', role: 'Closer', names: ['Sam'], open: 1, warn: false, reasons: [] }],
    })
    expect(screen.getByRole('img', { name: 'Proposed Closer 3p–10p: Sam, 1 open' })).toBeInTheDocument()
    expect(screen.getByText('Just changed')).toBeInTheDocument()
    expect(screen.getByText('draft')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Add shift/ }))
    expect(handlers.onCreateOn).toHaveBeenCalledWith('2026-09-13')
  })

  it('says so when a day is empty', () => {
    renderAgenda()
    expect(screen.getByText('Nothing scheduled this day.')).toBeInTheDocument()
  })
})
