import { DndContext } from '@dnd-kit/core'
import { render, screen } from '@testing-library/react'
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
