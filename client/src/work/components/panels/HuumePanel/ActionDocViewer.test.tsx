import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { HuumeActionScheduleWeekDraft } from '../../../types'
import ActionDocViewer from './ActionDocViewer'


function weekDraft(
  overrides: Partial<HuumeActionScheduleWeekDraft> = {},
): HuumeActionScheduleWeekDraft {
  return {
    type: 'schedule_week_draft',
    status: 'proposed',
    confirm_id: 'ab12cd34',
    generation_run_id: 'run-1',
    location_id: 'loc-1',
    week_start: '2026-08-23',
    source_mode: 'existing',
    summary: 'Built a draft proposal: 8 of 8 positions filled.',
    metrics: {
      shift_count: 4, required_positions: 8, filled_positions: 8, open_positions: 0,
      gap_count: 1, operating_hours_known: true,
    },
    ...overrides,
  }
}

const GAP = {
  kind: 'close_buffer_uncovered',
  severity: 'gap' as const,
  day: '2026-08-24',
  window: { start: '17:00', end: '17:20' },
  minutes: 20,
  detail: 'Nobody is scheduled to close on Monday (17:00–17:20, 20 min after the doors shut).',
}

const ADVISORY = {
  kind: 'thin_close',
  severity: 'advisory' as const,
  day: '2026-08-26',
  window: { start: '16:00', end: '17:00' },
  detail: 'Wednesday opens with 3 on but closes with one.',
}

describe('ActionDocViewer — generated week', () => {
  it('shows what the week does not cover, grouped and labelled', () => {
    render(<ActionDocViewer action={weekDraft({ findings: [GAP, ADVISORY] })} />)

    expect(screen.getByText('Needs review')).toBeTruthy()
    expect(screen.getByText('Nobody scheduled to close')).toBeTruthy()
    expect(screen.getByText('Thin at close')).toBeTruthy()
    expect(screen.getByText(/Nobody is scheduled to close on Monday/)).toBeTruthy()
  })

  it('distinguishes a real hole from something worth a look', () => {
    const { container } = render(
      <ActionDocViewer action={weekDraft({ findings: [GAP, ADVISORY] })} />,
    )

    // A gap wears the same red chip as an open position; an advisory is amber,
    // so a manager can tell "nobody is on" from "check this" at a glance.
    expect(container.querySelectorAll('[class*="red"]').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('[class*="amber"]').length).toBeGreaterThan(0)
  })

  it('says coverage was never checked when the store has no saved hours', () => {
    render(<ActionDocViewer action={weekDraft({
      findings: [],
      metrics: { filled_positions: 8, required_positions: 8, operating_hours_known: false },
    })} />)

    expect(screen.getByText(/opening hours are not saved/)).toBeTruthy()
  })

  it('renders nothing extra for a week that is genuinely covered', () => {
    render(<ActionDocViewer action={weekDraft({ findings: [] })} />)

    expect(screen.queryByText('Needs review')).toBeNull()
  })

  it('falls back to the server wording for a finding kind it does not know', () => {
    render(<ActionDocViewer action={weekDraft({
      findings: [{ kind: 'some_future_kind', severity: 'gap', detail: 'Something new happened.' }],
    })} />)

    expect(screen.getByText('Needs a look')).toBeTruthy()
    expect(screen.getByText(/Something new happened/)).toBeTruthy()
  })
})
