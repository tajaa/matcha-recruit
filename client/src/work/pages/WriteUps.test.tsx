import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ManagerCase } from '../types'
import WriteUps from './WriteUps'

const api = vi.hoisted(() => ({
  listMyWriteUps: vi.fn(),
  markWriteUpDelivered: vi.fn(),
  searchCaseEmployees: vi.fn(),
  searchCaseIncidents: vi.fn(),
  submitWriteUp: vi.fn(),
  uploadSignedCopy: vi.fn(),
}))
vi.mock('../api/hrCases', () => api)

function mcase(overrides: Partial<ManagerCase> = {}): ManagerCase {
  return {
    id: 'c1', case_number: 'HRC-2026-0001', stage: 'flagged', stage_label: 'Flagged',
    checklist: [{ key: 'flagged', label: 'Incident reviewed', done: true }],
    incident_id: 'i1', incident_number: 'IR-7', incident_title: 'Late', employee_id: 'e1', employee_name: 'Jane Doe',
    action_type: null, review: null, decision: null, decision_reason: null, delivered_at: null,
    has_draft: false, can_submit_draft: true, can_mark_delivered: false, can_upload_signed: false, signed_check: null, updated_at: null,
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/work/write-ups" element={<WriteUps />} />
        <Route path="/work/write-ups/:caseId" element={<WriteUps />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
  api.searchCaseEmployees.mockResolvedValue({ employees: [{ id: 'e1', name: 'Jane Doe', job_title: 'Barista' }] })
  api.searchCaseIncidents.mockResolvedValue({ incidents: [] })
})

describe('WriteUps', () => {
  it('lists my write-ups and shows HR notes without leave details', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({
      stage: 'changes_requested', stage_label: 'Changes requested', decision: 'changes_requested',
      decision_reason: 'Add the dates.', has_draft: true,
      review: { held_for_hr: false, message: null, notes: [{ code: 'missing_date', detail: "The letter doesn't say when." }] },
    })] })
    renderAt('/work/write-ups/c1')
    expect(await screen.findByText('Add the dates.')).toBeTruthy()
    expect(screen.getByText("The letter doesn't say when.")).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send a revised draft' })).toBeTruthy()
  })

  it('shows the held message when HR must look first', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({ review: { held_for_hr: true, message: "This write-up can't go forward as written.", notes: [] } })] })
    renderAt('/work/write-ups/c1')
    expect(await screen.findByText("This write-up can't go forward as written.")).toBeTruthy()
  })

  it('sends a new write-up with an uploaded file', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [] })
    api.submitWriteUp.mockResolvedValue({ status: 'submitted', case: mcase({ id: 'c9', case_number: 'HRC-2026-0009' }) })
    renderAt('/work/write-ups')
    fireEvent.click(await screen.findByRole('button', { name: /New write-up/ }))
    fireEvent.change(screen.getByLabelText('Employee'), { target: { value: 'ja' } })
    fireEvent.click(await screen.findByRole('button', { name: /Jane Doe/ }))
    fireEvent.change(screen.getByLabelText('When it happened'), { target: { value: '2026-09-03' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    const file = new File(['%PDF'], 'w.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('Write-up file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to HR' }))
    await waitFor(() => expect(api.submitWriteUp).toHaveBeenCalled())
    expect(api.submitWriteUp.mock.calls[0][0]).toMatchObject({
      employeeId: 'e1', actionType: 'written_warning', infractionType: 'attendance',
      occurrenceDates: ['2026-09-03'], file,
    })
    expect(await screen.findByText('HRC-2026-0009: sent to HR for review.')).toBeTruthy()
  })

  it('validates before sending', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [] })
    renderAt('/work/write-ups')
    fireEvent.click(await screen.findByRole('button', { name: /New write-up/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Send to HR' }))
    expect(await screen.findByText('Pick the employee this write-up is for.')).toBeTruthy()
    expect(api.submitWriteUp).not.toHaveBeenCalled()
  })

  it('marks an approved write-up delivered', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({ stage: 'approved', stage_label: 'Approved to deliver', can_submit_draft: false, can_mark_delivered: true })] })
    api.markWriteUpDelivered.mockResolvedValue(mcase())
    renderAt('/work/write-ups/c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Mark delivered' }))
    await waitFor(() => expect(api.markWriteUpDelivered).toHaveBeenCalledWith('c1', expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)))
  })
})

describe('WriteUps signed copy', () => {
  it('uploads the signed copy after delivery', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({ stage: 'delivered', stage_label: 'Delivered', can_submit_draft: false, can_upload_signed: true })] })
    api.uploadSignedCopy.mockResolvedValue(mcase())
    renderAt('/work/write-ups/c1')
    const file = new File(['%PDF'], 'signed.pdf', { type: 'application/pdf' })
    fireEvent.change(await screen.findByLabelText('Signed copy'), { target: { files: [file] } })
    await waitFor(() => expect(api.uploadSignedCopy).toHaveBeenCalledWith('c1', file))
    expect(await screen.findByText(/signed copy filed/)).toBeTruthy()
  })

  it('tells the manager what to fix, and nothing about comments', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({ stage: 'needs_attention', stage_label: 'Needs attention', can_submit_draft: false, can_upload_signed: true,
      signed_check: { outcome: 'fix_needed', problems: ["There's no employee signature on it."] } })] })
    renderAt('/work/write-ups/c1')
    expect(await screen.findByText("There's no employee signature on it.")).toBeTruthy()
    expect(screen.getByLabelText('Signed copy')).toBeTruthy()
  })

  it('hides the upload while HR reviews the signed copy', async () => {
    api.listMyWriteUps.mockResolvedValue({ cases: [mcase({ stage: 'needs_attention', stage_label: 'Needs attention', can_submit_draft: false, can_upload_signed: true,
      signed_check: { outcome: 'with_hr', problems: [] } })] })
    renderAt('/work/write-ups/c1')
    expect(await screen.findByText('HR is reviewing the signed copy.')).toBeTruthy()
    expect(screen.queryByLabelText('Signed copy')).toBeNull()
  })
})
