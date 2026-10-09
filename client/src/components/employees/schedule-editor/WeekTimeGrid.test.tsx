import { DndContext } from '@dnd-kit/core'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import WeekTimeGrid from './WeekTimeGrid'

const DAYS = ['2026-09-14', '2026-09-15']

function renderGrid(overrides: Partial<React.ComponentProps<typeof WeekTimeGrid>> = {}) {
  return render(
    <DndContext>
      <WeekTimeGrid
        days={DAYS}
        shifts={[]}
        pendingKeys={new Set()}
        editPublished={false}
        selectedEmployeeId={null}
        huumeSelectedShiftIds={new Set()}
        onCreateAt={() => {}}
        onOpenShift={() => {}}
        onToggleHuumeSelection={() => {}}
        onAssignSelected={() => {}}
        onResizeShift={() => {}}
        {...overrides}
      />
    </DndContext>,
  )
}

describe('WeekTimeGrid day cost', () => {
  it('shows no money at all without cost access', () => {
    renderGrid()
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument()
  })

  it('dashes a day whose staff could not be priced at all, rather than calling it free', () => {
    // The failure this guards: `costByDay[day] ?? 0` rendered "$0" beside a
    // fully-staffed day, and a manager reading the columns staffs it harder.
    renderGrid({
      costByDay: { '2026-09-14': 720, '2026-09-15': 0 },
      unpricedDays: new Set(['2026-09-15']),
    })
    expect(screen.getByText('$720')).toBeInTheDocument()
    expect(screen.getByText('\u2014')).toBeInTheDocument()
  })

  it('marks a PARTLY priced day as a floor instead of a total', () => {
    // Three of four people priced: "$540" unmarked reads as the day's total
    // and makes it look like the cheap day.
    renderGrid({
      costByDay: { '2026-09-14': 720, '2026-09-15': 540 },
      unpricedDays: new Set(['2026-09-15']),
    })
    expect(screen.getByText('\u2265$540')).toBeInTheDocument()
  })

  it('shows $0 for a genuine day off', () => {
    renderGrid({ costByDay: { '2026-09-14': 720, '2026-09-15': 0 }, unpricedDays: new Set() })
    expect(screen.getByText('$0')).toBeInTheDocument()
  })
})

describe('WeekTimeGrid proposal layer', () => {
  const preview = {
    id: 'autopilot:2026-09-14:barista:1', starts_at: '2026-09-14T07:00:00+00:00', ends_at: '2026-09-14T15:00:00+00:00',
    role: 'Barista', names: ['Amy'], open: 1, warn: true, reasons: ['short rest'],
  }

  it('draws a proposed shift read-only, with who and the open seat', () => {
    renderGrid({ previewShifts: [preview] })
    const block = screen.getByRole('img', { name: /^Proposed Barista .+: Amy, 1 open$/ })
    expect(block).toHaveAttribute('title', 'short rest')
    // No handles: a preview can't be dragged, resized, opened or sent to Huume.
    expect(block.querySelector('button')).toBeNull()
    expect(screen.getByText('open')).toBeInTheDocument()
  })

  it('shares lanes with real shifts on the same day', () => {
    renderGrid({
      previewShifts: [preview],
      shifts: [{
        id: 'real-1', starts_at: '2026-09-14T08:00:00+00:00', ends_at: '2026-09-14T12:00:00+00:00',
        role: 'Shift Lead', status: 'draft', required_staff: 1, assignments: [], kind: 'work',
      } as unknown as React.ComponentProps<typeof WeekTimeGrid>['shifts'][number]],
    })
    const proposed = screen.getByRole('img', { name: /^Proposed Barista/ })
    expect(proposed.style.left).not.toBe('')
    expect(screen.getByText('Shift Lead')).toBeInTheDocument()
  })

  it('bands each day with demand, red where the proposal staffs less', () => {
    renderGrid({
      demand: { '2026-09-14': [
        { start: 420, end: 480, demand: 2, covered: 1 },
        { start: 480, end: 540, demand: 2, covered: 2 },
      ] },
    })
    const short = screen.getByRole('img', { name: '07:00–08:00: demand 2, covered 1' })
    const ok = screen.getByRole('img', { name: '08:00–09:00: demand 2, covered 2' })
    expect(short.className).toContain('bg-red-400')
    expect(ok.className).toContain('bg-emerald-400')
    // The board opens an hour before the first demand (06:00), not at midnight.
    expect(short.style.top).toBe('60px')
    expect(short.style.height).toBe('60px')
  })
})

describe('WeekTimeGrid visible hours', () => {
  const shift = (starts: string, ends: string, overrides: Record<string, unknown> = {}) => ({
    id: 'shift-1', starts_at: starts, ends_at: ends, role: 'Barista', status: 'draft',
    required_staff: 1, assignments: [], kind: 'work', ...overrides,
  } as unknown as React.ComponentProps<typeof WeekTimeGrid>['shifts'][number])

  it('opens an hour before the first shift instead of at midnight, and can show the whole day', () => {
    renderGrid({ shifts: [shift('2026-09-14T06:30:00Z', '2026-09-14T13:30:00Z')] })
    expect(screen.queryByText('00:00')).not.toBeInTheDocument()
    expect(screen.getByText('05:00')).toBeInTheDocument()
    expect(screen.queryByLabelText('Create shift on 2026-09-14 at 0 minutes')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '24h' }))
    expect(screen.getByText('00:00')).toBeInTheDocument()
    expect(screen.getByLabelText('Create shift on 2026-09-14 at 0 minutes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'fit' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('outlines a shift a proposal changes, with what it does, and tags one an apply just changed', () => {
    renderGrid({
      shifts: [
        shift('2026-09-14T08:00:00Z', '2026-09-14T12:00:00Z'),
        shift('2026-09-15T08:00:00Z', '2026-09-15T12:00:00Z', { id: 'shift-2', role: 'Opener' }),
      ],
      marks: new Map([['shift-1', { warn: true, chips: [{ tone: 'add', label: '+ Sam' }] }]]),
      recentShiftIds: new Set(['shift-2']),
    })
    expect(screen.getByText('+ Sam').closest('[data-proposed]')).toHaveClass('ring-amber-400/40')
    expect(screen.getByText('Just changed').closest('[data-recent]')).toBeInTheDocument()
  })
})
