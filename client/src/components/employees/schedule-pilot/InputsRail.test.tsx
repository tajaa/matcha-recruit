import { DndContext } from '@dnd-kit/core'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InputsRail from './InputsRail'
import { SETUP_KICKOFF_PROMPT } from '../../../hooks/employees/useScheduleHuumeThread'
import type { EmployeeLaborCost, PlanningInputs, PlanningRosterPerson, RosterEmployee, WeekLaborCost } from '../../../types/employeeSchedule'

function person(id: string, name: string, minutes: number, overrides: Partial<PlanningRosterPerson> = {}): PlanningRosterPerson {
  return {
    employee_id: id, name, job_title: 'Barista', jobs: ['Shift Lead'],
    availability_state: 'windows', windows: {}, time_away: [],
    caps: {
      max_weekly_minutes: 2400, target_weekly_minutes: null, min_weekly_minutes: null,
      allow_overtime: false, max_consecutive_days: null, prefer_extra_hours: false,
    },
    load: { minutes, shifts: minutes / 480, days: [] },
    ...overrides,
  }
}

function inputs(overrides: Partial<PlanningInputs> = {}): PlanningInputs {
  return {
    week_start: '2026-08-23', week_end: '2026-08-29',
    roster: [person('e1', 'Dana Reyes', 960), person('e2', 'Ben Ortiz', 480)],
    roster_truncated: false,
    open_slots: [],
    policy: { min_rest_hours: 8, max_shifts_per_day: 1, max_consecutive_days: 6, default_weekly_cap_minutes: 2400 },
    jurisdiction: { state: 'CA', status: 'curated', message: 'Scheduling law for CA is on file (hand-curated).' },
    week_rules: { established: true, missing: [] },
    profile: { operating_hours: {}, leader_required: false, leader_job_names: [] },
    ...overrides,
  }
}

function employee(id: string, name: string, overrides: Partial<RosterEmployee> = {}): RosterEmployee {
  return { id, name, job_title: 'Barista', department: null, job_ids: [], ...overrides }
}

const ROSTER = [employee('e1', 'Dana Reyes'), employee('e2', 'Ben Ortiz')]

function renderRail(overrides: Partial<React.ComponentProps<typeof InputsRail>> = {}) {
  const props = {
    inputs: inputs(),
    loading: false,
    roster: ROSTER,
    rosterFlags: null,
    selectedEmployeeId: null,
    onSelectEmployee: vi.fn(),
    weekRules: { established: true, missing: [] as never[] },
    locationName: 'Wilshire',
    credentialsEnabled: false,
    onOpenWeekSetup: vi.fn(),
    onOpenJobs: vi.fn(),
    onAskHuume: vi.fn(),
    onShowShift: vi.fn(),
    ...overrides,
  }
  const view = render(<DndContext><InputsRail {...props} /></DndContext>)
  return { ...props, ...view }
}

describe('InputsRail — people', () => {
  it('puts the heaviest week first, because that is the question being asked', () => {
    renderRail()
    const names = screen.getAllByRole('button').map((button) => button.textContent ?? '')
      .filter((text) => text.includes('Dana Reyes') || text.includes('Ben Ortiz'))
    expect(names[0]).toContain('Dana Reyes')
    expect(names[1]).toContain('Ben Ortiz')
  })

  it('draws each person’s hours against the policy tick', () => {
    renderRail()
    expect(screen.getByRole('img', { name: 'Dana Reyes: 16h this week' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Ben Ortiz: 8h this week' })).toBeInTheDocument()
  })

  it('counts shifts and days, and names the jobs they can actually work', () => {
    renderRail({ inputs: inputs({ roster: [person('e1', 'Dana Reyes', 960, { jobs: ['Shift Lead', 'Barista'], load: { minutes: 960, shifts: 2, days: ['2026-08-24', '2026-08-25'] } })] }) })
    expect(screen.getByText('2 shifts · 2 days')).toBeInTheDocument()
    expect(screen.getByText('Shift Lead, Barista')).toBeInTheDocument()
  })

  it('flags time away on the row', () => {
    renderRail({ inputs: inputs({ roster: [person('e1', 'Dana Reyes', 0, { time_away: [{ start: '2026-08-27', end: '2026-08-28' }] })] }) })
    expect(screen.getByText('away 8/27–8/28')).toBeInTheDocument()
  })

  it('selects and clears a person', () => {
    const props = renderRail()
    fireEvent.click(screen.getByText('Dana Reyes'))
    expect(props.onSelectEmployee).toHaveBeenCalledWith('e1')

    const { onSelectEmployee } = renderRail({ selectedEmployeeId: 'e1' })
    fireEvent.click(screen.getAllByRole('button', { name: 'Clear selected employee' })[0])
    expect(onSelectEmployee).toHaveBeenCalledWith(null)
  })

  it('refuses to hand out someone a credential block already stops', () => {
    renderRail({
      rosterFlags: { e1: { overdue_training: 0, lapsed_credentials: 1, blocking_credentials: ['Food Handler Card expired'] } },
    })
    const row = screen.getByRole('button', { name: /Dana Reyes cannot be scheduled/ })
    expect(row).toBeDisabled()
    expect(within(row).getByText('Blocked')).toBeInTheDocument()
  })

  it('previews qualification against the inspected shift’s own date', () => {
    const qualified = [employee('e1', 'Dana Reyes', {
      job_qualifications: [{ job_id: 'job-1', qualified_from: '2026-09-01', qualified_until: '2026-09-30' }],
    })]
    const { unmount } = render(
      <DndContext>
        <InputsRail
          inputs={inputs({ roster: [person('e1', 'Dana Reyes', 0)] })} loading={false} roster={qualified} rosterFlags={null}
          selectedEmployeeId={null} onSelectEmployee={vi.fn()} requiredJobId="job-1" requiredJobDate="2026-08-31"
          weekRules={{ established: true, missing: [] }} locationName="Wilshire" credentialsEnabled={false}
          onOpenWeekSetup={vi.fn()} onOpenJobs={vi.fn()} onAskHuume={vi.fn()} onShowShift={vi.fn()}
        />
      </DndContext>,
    )
    expect(screen.getByText('Not qualified')).toBeInTheDocument()
    unmount()

    render(
      <DndContext>
        <InputsRail
          inputs={inputs({ roster: [person('e1', 'Dana Reyes', 0)] })} loading={false} roster={qualified} rosterFlags={null}
          selectedEmployeeId={null} onSelectEmployee={vi.fn()} requiredJobId="job-1" requiredJobDate="2026-09-15"
          weekRules={{ established: true, missing: [] }} locationName="Wilshire" credentialsEnabled={false}
          onOpenWeekSetup={vi.fn()} onOpenJobs={vi.fn()} onAskHuume={vi.fn()} onShowShift={vi.fn()}
        />
      </DndContext>,
    )
    expect(screen.queryByText('Not qualified')).not.toBeInTheDocument()
  })

  it('says when the list was cut short rather than pretending it is everyone', () => {
    renderRail({ inputs: inputs({ roster_truncated: true }) })
    expect(screen.getByText(/Showing the first 2 people by load/)).toBeInTheDocument()
  })

  it('finds a person by name or by the job they hold', () => {
    renderRail()
    fireEvent.change(screen.getByPlaceholderText('Find a person'), { target: { value: 'ortiz' } })
    expect(screen.queryByText('Dana Reyes')).not.toBeInTheDocument()
    expect(screen.getByText('Ben Ortiz')).toBeInTheDocument()
  })
})

describe('InputsRail — open seats', () => {
  const withSeats = inputs({
    open_slots: [
      { shift_id: 's1', role: 'Shift Lead', job_id: null, starts_at: '2026-08-24T06:00:00+00:00', ends_at: '2026-08-24T14:00:00+00:00', required_staff: 2, open: 2 },
      { shift_id: 's2', role: 'Barista', job_id: null, starts_at: '2026-08-25T06:00:00+00:00', ends_at: '2026-08-25T14:00:00+00:00', required_staff: 1, open: 1 },
    ],
  })

  it('totals the open seats and groups them by day', () => {
    renderRail({ inputs: withSeats })
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Mon 8/24')).toBeInTheDocument()
    expect(screen.getByText('2 open')).toBeInTheDocument()
  })

  it('shows a seat on the board when it is clicked', () => {
    const props = renderRail({ inputs: withSeats })
    // The people rows carry aria-labels, so only the seat matches by its own text.
    fireEvent.click(screen.getByRole('button', { name: /Shift Lead/ }))
    expect(props.onShowShift).toHaveBeenCalledWith('s1')
  })

  it('hands the whole fill to Huume', () => {
    const props = renderRail({ inputs: withSeats })
    fireEvent.click(screen.getByRole('button', { name: /Fill with Huume/ }))
    expect(props.onAskHuume).toHaveBeenCalledWith('Fill the open shifts this week.')
  })

  it('says so plainly when the week is fully staffed', () => {
    renderRail()
    expect(screen.getByText('Every seat this week is filled.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Fill with Huume/ })).not.toBeInTheDocument()
  })
})

describe('InputsRail — policy and law', () => {
  it('states the house rules and marks them as policy, not law', () => {
    renderRail()
    expect(screen.getByText('At least 8h rest between shifts')).toBeInTheDocument()
    expect(screen.getByText('1 shift a day unless a split is asked for')).toBeInTheDocument()
    expect(screen.getByText('At most 6 days in a row')).toBeInTheDocument()
    expect(screen.getByText('40h a week unless overtime is allowed')).toBeInTheDocument()
    expect(screen.getByText(/House policy — what the planner and Huume refuse to break. Not the law/)).toBeInTheDocument()
  })

  it('repeats the server’s sentence about the state’s law, whatever it says', () => {
    const { unmount } = renderRail()
    expect(screen.getByText('Scheduling law for CA is on file (hand-curated).')).toBeInTheDocument()
    unmount()

    renderRail({
      inputs: inputs({ jurisdiction: { state: 'TX', status: 'unmapped', message: 'Legality was NOT verified for TX — Matcha has no researched scheduling thresholds for it.' } }),
    })
    expect(screen.getByText(/Legality was NOT verified for TX/)).toBeInTheDocument()
  })
})

describe('InputsRail — setup', () => {
  it('names what is missing and offers both ways to fix it', () => {
    const props = renderRail({ weekRules: { established: false, missing: ['operating_hours', 'leader_rule'] } })

    expect(screen.getByText(/Wilshire is still missing hours, the leader rule/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Set up with Huume' }))
    expect(props.onAskHuume).toHaveBeenCalledWith(SETUP_KICKOFF_PROMPT)

    fireEvent.click(screen.getByRole('button', { name: 'Fill it in myself' }))
    expect(props.onOpenWeekSetup).toHaveBeenCalled()
  })

  it('confirms the setup is saved rather than staying silent', () => {
    renderRail()
    expect(screen.getByText('Hours, staffing pattern and leader rule are saved.')).toBeInTheDocument()
  })

  it('opens the jobs drawer, naming credentials only when the company has them', () => {
    const { onOpenJobs, ...rest } = renderRail()
    void rest
    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))
    expect(onOpenJobs).toHaveBeenCalled()

    renderRail({ credentialsEnabled: true })
    expect(screen.getByRole('button', { name: 'Jobs & credentials' })).toBeInTheDocument()
  })
})


function personCost(id: string, total: number, priced = true): EmployeeLaborCost {
  return {
    employee_id: id, classification: 'hourly', inferred_classification: false,
    priced, reason: priced ? null : 'no_pay_rate',
    minutes: 960, ot_minutes: 0, doubletime_minutes: 0,
    straight_cost: total, ot_cost: 0, doubletime_cost: 0, salaried_cost: 0,
    ot_premium: 0, total, days: [],
  }
}

function weekCost(overrides: Partial<WeekLaborCost> = {}): WeekLaborCost {
  return {
    week_start: '2026-08-23',
    total: 1200, hourly_total: 1200, salaried_total: 0, open_seat_total: 0,
    ot_premium: 0, ot_minutes: 0, by_day: {},
    employees: [personCost('e1', 800), personCost('e2', 400)],
    unpriced_employee_ids: [], unpriced_employee_count: 0, unpriced_open_seats: 0,
    unpriced_days: [], truncated: false,
    basis: {
      daily_ot_hours: 8, daily_doubletime_hours: 12, weekly_ot_hours: 40,
      ot_multiplier: 1.5, doubletime_multiplier: 2, as_scheduled: true,
      overtime_citation: 'Cal. Lab. Code \u00a7 510(a)',
    },
    ...overrides,
  }
}

describe('InputsRail labor cost', () => {
  it('shows no money at all when the viewer has no cost access', () => {
    renderRail()
    expect(screen.queryByText('Labor cost')).not.toBeInTheDocument()
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument()
  })

  it('breaks the week down and cites the overtime statute', () => {
    renderRail({ cost: weekCost({ salaried_total: 500, open_seat_total: 272, total: 1972, ot_premium: 60 }) })
    expect(screen.getByText('Labor cost')).toBeInTheDocument()
    expect(screen.getByText('$1,972')).toBeInTheDocument()
    expect(screen.getByText('Salaried')).toBeInTheDocument()
    expect(screen.getByText('Unfilled seats')).toBeInTheDocument()
    expect(screen.getByText('$60 OT')).toBeInTheDocument()
    expect(screen.getByText(/Cal. Lab. Code/)).toBeInTheDocument()
    expect(screen.getByText(/As scheduled, not as worked/)).toBeInTheDocument()
  })

  it('names what is missing instead of quietly costing it at zero', () => {
    renderRail({
      cost: weekCost({
        employees: [personCost('e1', 800), personCost('e2', 0, false)],
        unpriced_employee_ids: ['e2'], unpriced_employee_count: 1, unpriced_open_seats: 2,
      }),
    })
    expect(screen.getByText(/1 person has no pay rate on file/)).toBeInTheDocument()
    expect(screen.getByText(/2 open seats are on a job with no default rate/)).toBeInTheDocument()
    expect(screen.getByText(/the real figure is higher/)).toBeInTheDocument()
  })

  it('shows a dash, not \u00240, for a person with no rate on file', () => {
    renderRail({
      cost: weekCost({
        employees: [personCost('e1', 800), personCost('e2', 0, false)],
        unpriced_employee_ids: ['e2'], unpriced_employee_count: 1,
      }),
    })
    const ben = screen.getByText('Ben Ortiz').closest('button')!
    expect(within(ben).getByText('\u2014')).toBeInTheDocument()
    expect(within(ben).queryByText('$0')).not.toBeInTheDocument()
  })
})


describe('InputsRail unpriced vs unscheduled', () => {
  it('shows $0 for someone with no shifts, not the no-rate dash', () => {
    // `cost.employees` only carries people who worked. In a normal week the
    // bench is most of the roster, and marking all of them "no pay rate on
    // file" both lies and buries the rows that really are missing data.
    renderRail({ cost: weekCost({ employees: [personCost('e1', 800)] }) })
    const ben = screen.getByText('Ben Ortiz').closest('button')!
    expect(within(ben).getByText('$0')).toBeInTheDocument()
    expect(within(ben).queryByText('\u2014')).not.toBeInTheDocument()
  })

  it('still dashes someone the server named as unpriced', () => {
    renderRail({
      cost: weekCost({
        employees: [personCost('e1', 800)],
        unpriced_employee_ids: ['e2'], unpriced_employee_count: 1,
      }),
    })
    const ben = screen.getByText('Ben Ortiz').closest('button')!
    expect(within(ben).getByText('\u2014')).toBeInTheDocument()
  })
})
