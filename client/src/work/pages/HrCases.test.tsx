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
  decideHrCase: vi.fn(),
  getWriteUpDraftUrl: vi.fn(),
  markWriteUpDelivered: vi.fn(),
  getSignedCopyUrl: vi.fn(),
  uploadSignedCopy: vi.fn(),
  acknowledgeHrCase: vi.fn(),
  recheckHrCase: vi.fn(),
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
    review: null, decision: null, decision_reason: null, decided_at: null, delivered_at: null, draft_file_id: null,
    signed_file_id: null, verification: null, attention_reasons: [],
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

describe('HrCases review and decisions', () => {
  const review = {
    checked_at: '2026-09-29T00:00:00Z',
    blocks: [],
    advisories: [
      { source: 'compliance' as const, code: 'retaliation_window', detail: 'Employee filed a complaint 20 days ago.' },
      { source: 'structure' as const, code: 'missing_date', detail: "The letter doesn't say when." },
    ],
    input: { infraction_type: 'attendance', action_type: 'written_warning', occurrence_dates: ['2026-09-03'], file_id: 'f1' },
  }

  it('shows grouped review findings and approves', async () => {
    const inReview = hrCase({ stage: 'hr_review', stage_label: 'HR review', allowed_events: ['approve', 'request_changes', 'dismiss'], review, draft_file_id: 'f1', action_type: 'written_warning' })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [inReview] })
    api.getHrCase.mockResolvedValue(inReview)
    api.decideHrCase.mockResolvedValue(inReview)
    renderAt('/work/hr-cases/c1')
    const panel = await screen.findByRole('complementary', { name: 'Case HRC-2026-0001' })
    expect(panel.textContent).toContain('Leave and retaliation check')
    expect(panel.textContent).toContain('Employee filed a complaint 20 days ago.')
    expect(panel.textContent).toContain('Written warning · attendance · 2026-09-03')
    fireEvent.click(screen.getByRole('button', { name: 'Approve to deliver' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(api.decideHrCase).toHaveBeenCalledWith('c1', 'approve', ''))
  })

  it('requires a real reason to send back', async () => {
    const inReview = hrCase({ stage: 'hr_review', stage_label: 'HR review', allowed_events: ['approve', 'request_changes'], review })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(inReview)
    api.decideHrCase.mockResolvedValue(inReview)
    renderAt('/work/hr-cases/c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Request changes' }))
    const send = screen.getByRole('button', { name: 'Send back' }) as HTMLButtonElement
    expect(send.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('What should change'), { target: { value: 'Add the date of each late arrival please.' } })
    fireEvent.click(send)
    await waitFor(() => expect(api.decideHrCase).toHaveBeenCalledWith('c1', 'request_changes', 'Add the date of each late arrival please.'))
  })

  it('shows a leave block as not approvable', async () => {
    const held = hrCase({ review: { ...review, blocks: [{ source: 'compliance', code: 'protected_leave_overlap', detail: 'Protected sick leave on 9/3 (CA 246.5).' }] } })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(held)
    renderAt('/work/hr-cases/c1')
    const alert = await screen.findByText(/Can’t be approved as written/)
    expect(alert.closest('[role="alert"]')?.textContent).toContain('CA 246.5')
  })

  it('opens the draft and marks delivery', async () => {
    const approved = hrCase({ stage: 'approved', stage_label: 'Approved to deliver', allowed_events: ['delivered'], draft_file_id: 'f1', review })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(approved)
    api.getWriteUpDraftUrl.mockResolvedValue({ url: 'https://s3/draft', filename: 'd.pdf', expires_in: 300 })
    api.markWriteUpDelivered.mockResolvedValue(approved)
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    renderAt('/work/hr-cases/c1')
    fireEvent.click(await screen.findByRole('button', { name: /Open the draft/ }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://s3/draft', '_blank', 'noopener,noreferrer'))
    fireEvent.change(screen.getByLabelText('Delivered on'), { target: { value: '2026-09-28' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mark delivered' }))
    await waitFor(() => expect(api.markWriteUpDelivered).toHaveBeenCalledWith('c1', '2026-09-28'))
    open.mockRestore()
  })
})

describe('HrCases signed copy', () => {
  const verification = {
    checked_at: '2026-09-29T00:00:00Z', outcome: 'needs_attention' as const,
    reasons: ['employee_comments', 'check_unavailable'],
    reason_text: ['The employee wrote comments on it.', "The automatic check couldn't run, so a person needs to look at it."],
    flag_hr_comments: true,
    reading: { employee_comments_text: 'I was told I could leave early.' },
  }

  it('shows reasons and the employee comment, and closes or re-checks', async () => {
    const attention = hrCase({ stage: 'needs_attention', stage_label: 'Needs attention', allowed_events: ['signed_uploaded', 'acknowledge'], signed_file_id: 's1', verification })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(attention)
    api.acknowledgeHrCase.mockResolvedValue(attention)
    api.recheckHrCase.mockResolvedValue(attention)
    renderAt('/work/hr-cases/c1')
    expect(await screen.findByText('I was told I could leave early.')).toBeTruthy()
    expect(screen.getByText('The employee wrote comments on it.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(api.recheckHrCase).toHaveBeenCalledWith('c1'))
    fireEvent.click(screen.getByRole('button', { name: 'Handled — close case' }))
    await waitFor(() => expect(api.acknowledgeHrCase).toHaveBeenCalledWith('c1'))
  })

  it('HR can upload the signed copy after delivery', async () => {
    const delivered = hrCase({ stage: 'delivered', stage_label: 'Delivered', allowed_events: ['signed_uploaded'] })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(delivered)
    api.uploadSignedCopy.mockResolvedValue(delivered)
    renderAt('/work/hr-cases/c1')
    const file = new File(['%PDF'], 'signed.pdf', { type: 'application/pdf' })
    fireEvent.change(await screen.findByLabelText('Signed copy'), { target: { files: [file] } })
    await waitFor(() => expect(api.uploadSignedCopy).toHaveBeenCalledWith('c1', file))
  })

  it('opens a filed signed copy', async () => {
    const closed = hrCase({ stage: 'closed', stage_label: 'Closed', allowed_events: [], signed_file_id: 's1',
      verification: { ...verification, outcome: 'verified', reasons: [], reason_text: [], flag_hr_comments: false, reading: {} } })
    api.listHrCases.mockResolvedValue({ columns: COLUMNS, cases: [] })
    api.getHrCase.mockResolvedValue(closed)
    api.getSignedCopyUrl.mockResolvedValue({ url: 'https://s3/signed', filename: 'Doe.pdf', expires_in: 300 })
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    renderAt('/work/hr-cases/c1')
    expect(await screen.findByText('Signed, readable and filed.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Open the signed copy/ }))
    await waitFor(() => expect(open).toHaveBeenCalledWith('https://s3/signed', '_blank', 'noopener,noreferrer'))
    open.mockRestore()
  })
})
