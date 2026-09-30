import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { HrCase, HrCaseColumn } from '../types'
import HrCases from './HrCases'

const api = vi.hoisted(() => ({
  listHrCases: vi.fn(),
  getHrCase: vi.fn(),
  dismissHrCase: vi.fn(),
  getHrCaseAccess: vi.fn(),
}))
vi.mock('../api/hrCases', () => api)

const COLUMNS: HrCaseColumn[] = [
  { key: 'new', label: 'New', stages: ['flagged', 'drafting'] },
  { key: 'review', label: 'HR review', stages: ['hr_review', 'changes_requested'] },
  { key: 'done', label: 'Done', stages: ['closed', 'dismissed'] },
]

function hrCase(overrides: Partial<HrCase> = {}): HrCase {
  return {
    id: 'c1', case_number: 'HRC-2026-0001', origin: 'intake_triage', stage: 'flagged',
    stage_label: 'Flagged', column: 'new',
    checklist: [
      { key: 'flagged', label: 'Incident reviewed', done: true },
      { key: 'draft', label: 'Write-up drafted', done: false },
    ],
    allowed_events: ['start_draft', 'draft_submitted', 'dismiss'],
    source_incident_id: 'i1', incident_number: 'IR-7', incident_title: 'Late for shift again',
    employee_id: null, employee_name: 'Jane Doe', gm_user_id: 'u1', gm_name: 'Sam',
    action_type: null,
    triage: { phase: 'intake', violations: [{ policy_title: 'Attendance policy', relevance: 'violated', confidence: 0.82 }], citation_count: 1, summary: null },
    dismissed_reason: null, created_at: '2026-09-29T00:00:00Z', updated_at: '2026-09-29T00:00:00Z', closed_at: null,
    events: [{ event: 'opened', from_stage: null, to_stage: 'flagged', details: {}, created_at: '2026-09-29T00:00:00Z', actor_name: null }],
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/work/hr-cases" element={<HrCases />} />
        <Route path="/work/hr-cases/:caseId" element={<HrCases />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()))

describe('HrCases', () => {
  it('puts cases in their columns', async () => {
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [hrCase(), hrCase({ id: 'c2', case_number: 'HRC-2026-0002', stage: 'hr_review', stage_label: 'HR review', column: 'review' })] })
    renderAt('/work/hr-cases')
    const newCol = await screen.findByRole('region', { name: 'New' })
    expect(newCol.textContent).toContain('HRC-2026-0001')
    expect(screen.getByRole('region', { name: 'HR review' }).textContent).toContain('HRC-2026-0002')
  })

  it('tells non-HR users they have no access', async () => {
    api.listHrCases.mockRejectedValue(new Error('Not found'))
    renderAt('/work/hr-cases')
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', "You don't have access to HR cases.")
  })

  it('opens a case with checklist, policy matches and history', async () => {
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [hrCase()] })
    api.getHrCase.mockResolvedValue(hrCase())
    renderAt('/work/hr-cases/c1')
    const panel = await screen.findByRole('complementary', { name: 'Case HRC-2026-0001' })
    expect(panel.textContent).toContain('Attendance policy')
    expect(panel.textContent).toContain('82%')
    expect(panel.textContent).toContain('Case opened')
    expect(panel.textContent).toContain('Flagged when the incident was reported')
  })

  it('dismisses with a reason', async () => {
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [hrCase()] })
    api.getHrCase.mockResolvedValue(hrCase())
    api.dismissHrCase.mockResolvedValue(hrCase({ stage: 'dismissed', stage_label: 'Dismissed', allowed_events: [] }))
    renderAt('/work/hr-cases/c1')
    fireEvent.click(await screen.findByRole('button', { name: /Dismiss — no write-up needed/ }))
    fireEvent.change(screen.getByLabelText('Reason for dismissing'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss case' }))
    expect(await screen.findByText(/at least 10 characters/)).toBeTruthy()
    expect(api.dismissHrCase).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Reason for dismissing'), { target: { value: 'Coached verbally, no write-up' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss case' }))
    await waitFor(() => expect(api.dismissHrCase).toHaveBeenCalledWith('c1', 'Coached verbally, no write-up'))
  })

  it('hides dismiss when the stage does not allow it', async () => {
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(hrCase({ stage: 'approved', stage_label: 'Approved to deliver', allowed_events: ['delivered'] }))
    renderAt('/work/hr-cases/c1')
    await screen.findByRole('complementary', { name: 'Case HRC-2026-0001' })
    expect(screen.queryByRole('button', { name: /Dismiss/ })).toBeNull()
  })
})
