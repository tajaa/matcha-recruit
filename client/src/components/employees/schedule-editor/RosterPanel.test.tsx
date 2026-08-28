import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RosterPanel from './RosterPanel'

const employee = {
  id: 'employee-1', name: 'Aisha Rivera', job_title: 'Manager', department: null,
  job_ids: [],
  job_qualifications: [{
    job_id: 'job-1', qualified_from: '2026-09-01', qualified_until: '2026-09-30',
  }],
}

describe('RosterPanel', () => {
  it('previews qualification against the inspected shift date', () => {
    const { rerender } = render(
      <RosterPanel roster={[employee]} rosterFlags={null} selectedEmployeeId={null}
        onSelectEmployee={vi.fn()} requiredJobId="job-1" requiredJobDate="2026-08-31" />,
    )
    expect(screen.getByText('Not qualified')).toBeInTheDocument()

    rerender(
      <RosterPanel roster={[employee]} rosterFlags={null} selectedEmployeeId={null}
        onSelectEmployee={vi.fn()} requiredJobId="job-1" requiredJobDate="2026-09-15" />,
    )
    expect(screen.queryByText('Not qualified')).not.toBeInTheDocument()

    rerender(
      <RosterPanel roster={[employee]} rosterFlags={null} selectedEmployeeId={null}
        onSelectEmployee={vi.fn()} requiredJobId="job-1" requiredJobDate="2026-10-01" />,
    )
    expect(screen.getByText('Not qualified')).toBeInTheDocument()
  })
})
