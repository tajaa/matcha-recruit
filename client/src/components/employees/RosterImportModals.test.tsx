import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock, postMock, downloadMock, uploadMock, features } = vi.hoisted(() => ({
  getMock: vi.fn(), postMock: vi.fn(), downloadMock: vi.fn(), uploadMock: vi.fn(),
  features: new Set<string>(),
}))

vi.mock('../../api/client', () => ({
  api: { get: getMock, post: postMock, download: downloadMock, upload: uploadMock },
}))
vi.mock('../../hooks/useMe', () => ({
  useMe: () => ({ hasFeature: (flag: string) => features.has(flag) }),
}))

import { BulkUploadModal } from './BulkUploadModal'
import { HRISSyncModal } from './HRISSyncModal'

const CONNECTED = {
  connected: true, status: 'connected', mode: 'finch', gusto_company_id: null,
  has_client_secret: true, last_sync_at: null, total_synced_employees: 0,
}
const SYNCED = {
  sync_run_id: 'run-1', status: 'completed', created_count: 12, updated_count: 0,
  skipped_count: 0, error_count: 0, errors: [],
}

function renderIn(node: React.ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>)
}

beforeEach(() => {
  features.clear()
  getMock.mockReset()
  postMock.mockReset()
  downloadMock.mockReset().mockResolvedValue(undefined)
  uploadMock.mockReset()
})

describe('HRISSyncModal', () => {
  it('runs the first sync by itself when opened by the connect redirect', async () => {
    features.add('hris_finch').add('employee_schedule')
    getMock.mockResolvedValue(CONNECTED)
    postMock.mockResolvedValue(SYNCED)
    const onSuccess = vi.fn()

    renderIn(<HRISSyncModal open autoSync onClose={vi.fn()} onSuccess={onSuccess} />)

    await waitFor(() => expect(postMock).toHaveBeenCalledWith('/provisioning/hris/sync', {}))
    expect(await screen.findByText('Sync complete')).toBeInTheDocument()
    expect(onSuccess).toHaveBeenCalled()
    // Once: a re-render must not start a second import.
    expect(postMock).toHaveBeenCalledTimes(1)
    // An HRIS does not know which store someone works at; say where to go next.
    expect(screen.getByRole('link', { name: 'open the schedule' })).toHaveAttribute('href', '/ops/schedule')
  })

  it('waits for the button on an ordinary open', async () => {
    features.add('hris_finch')
    getMock.mockResolvedValue(CONNECTED)

    renderIn(<HRISSyncModal open onClose={vi.fn()} onSuccess={vi.fn()} />)

    await waitFor(() => expect(getMock).toHaveBeenCalledWith('/provisioning/hris/status'))
    await screen.findByRole('button', { name: /Sync/ })
    expect(postMock).not.toHaveBeenCalled()
  })

  it('does not sync when the redirect came back without a connection', async () => {
    features.add('hris_finch')
    getMock.mockResolvedValue({ ...CONNECTED, connected: false, status: 'disconnected' })

    renderIn(<HRISSyncModal open autoSync onClose={vi.fn()} onSuccess={vi.fn()} />)

    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(postMock).not.toHaveBeenCalled()
  })
})

describe('BulkUploadModal', () => {
  it('hands a scheduling customer the short roster template and names the store column', async () => {
    features.add('employee_schedule')
    const user = userEvent.setup()
    renderIn(<BulkUploadModal open onClose={vi.fn()} onSuccess={vi.fn()} />)

    expect(screen.getByText('location')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Download CSV Template' }))
    expect(downloadMock).toHaveBeenCalledWith(
      '/employees/bulk-upload/template?variant=scheduling', 'employee_template.csv',
    )
  })

  it('keeps the full template for everyone else', async () => {
    const user = userEvent.setup()
    renderIn(<BulkUploadModal open onClose={vi.fn()} onSuccess={vi.fn()} />)

    expect(screen.queryByText('location')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Download CSV Template' }))
    expect(downloadMock).toHaveBeenCalledWith('/employees/bulk-upload/template', 'employee_template.csv')
  })

  it('points at the schedule once a roster is in', async () => {
    features.add('employee_schedule')
    const user = userEvent.setup()
    uploadMock.mockResolvedValue({
      total_rows: 2, created: 2, failed: 0, errors: [], employee_ids: [],
      credentials_created: 0, rows_missing_work_location: 0,
    })
    renderIn(<BulkUploadModal open onClose={vi.fn()} onSuccess={vi.fn()} />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, new File(['email,first_name,last_name\n'], 'roster.csv', { type: 'text/csv' }))

    expect(await screen.findByText('2 created')).toBeInTheDocument()
    expect(uploadMock.mock.calls[0][0]).toBe('/employees/bulk-upload?send_invitations=false')
    expect(screen.getByRole('link', { name: 'open the schedule' })).toHaveAttribute('href', '/ops/schedule')
  })
})
