import { useState } from 'react'
import { Button, Input, Modal, Select, Toggle } from '../ui'
import { api } from '../../api/client'
import { TYPE_OPTIONS } from '../../types/employee'

type Row = {
  first_name: string
  last_name: string
  work_email: string
  job_title: string
  department: string
  employment_type: string
  start_date: string
  rowStatus: 'idle' | 'saving' | 'success' | 'error'
  error?: string
}

const emptyRow = (): Row => ({
  first_name: '',
  last_name: '',
  work_email: '',
  job_title: '',
  department: '',
  employment_type: 'full_time',
  start_date: '',
  rowStatus: 'idle',
})

type MultiBatchModalProps = {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  departments: string[]
}

export function MultiBatchModal({ open, onClose, onSuccess, departments }: MultiBatchModalProps) {
  const [rows, setRows] = useState<Row[]>([emptyRow()])
  const [sendInvitations, setSendInvitations] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  const deptOptions = departments.map((d) => ({ value: d, label: d }))

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }

  function addRow() {
    if (rows.length < 20) setRows((prev) => [...prev, emptyRow()])
  }

  function removeRow(i: number) {
    if (rows.length > 1) setRows((prev) => prev.filter((_, j) => j !== i))
  }

  async function handleSubmit() {
    setSubmitting(true)
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i]
      if (!r.first_name.trim() || !r.last_name.trim() || !r.work_email.trim()) {
        updateRow(i, { rowStatus: 'error', error: 'Name and email required' })
        continue
      }
      updateRow(i, { rowStatus: 'saving' })
      try {
        await api.post('/employees', {
          first_name: r.first_name.trim(),
          last_name: r.last_name.trim(),
          work_email: r.work_email.trim(),
          job_title: r.job_title.trim() || undefined,
          department: r.department || undefined,
          employment_type: r.employment_type || undefined,
          start_date: r.start_date || undefined,
          skip_invitation: !sendInvitations,
        })
        updateRow(i, { rowStatus: 'success' })
      } catch (e) {
        updateRow(i, { rowStatus: 'error', error: e instanceof Error ? e.message : 'Failed' })
      }
    }
    setSubmitting(false)
    setDone(true)
  }

  function handleClose() {
    setRows([emptyRow()])
    setDone(false)
    setSendInvitations(true)
    onClose()
  }

  const successCount = rows.filter((r) => r.rowStatus === 'success').length
  const failCount = rows.filter((r) => r.rowStatus === 'error').length

  return (
    <Modal open={open} onClose={handleClose} title="Add Employees" width="xl">
      {done && (
        <div className="mb-4 rounded-lg bg-emerald-950/50 border border-emerald-800 px-4 py-3 text-sm">
          <span className="text-emerald-400">{successCount} created</span>
          {failCount > 0 && <span className="text-red-400 ml-2">{failCount} failed</span>}
        </div>
      )}

      <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="text-zinc-400 text-xs sticky top-0 bg-zinc-900 z-10">
            <tr>
              <th className="text-left px-1 py-2 font-medium">First *</th>
              <th className="text-left px-1 py-2 font-medium">Last *</th>
              <th className="text-left px-1 py-2 font-medium">Email *</th>
              <th className="text-left px-1 py-2 font-medium">Title</th>
              <th className="text-left px-1 py-2 font-medium">Dept</th>
              <th className="text-left px-1 py-2 font-medium">Type</th>
              <th className="text-left px-1 py-2 font-medium">Start</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={
                r.rowStatus === 'success' ? 'bg-emerald-950/20' :
                r.rowStatus === 'error' ? 'bg-red-950/20' : ''
              }>
                <td className="px-1 py-1">
                  <Input label="" value={r.first_name} disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { first_name: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1">
                  <Input label="" value={r.last_name} disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { last_name: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1">
                  <Input label="" value={r.work_email} disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { work_email: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1">
                  <Input label="" value={r.job_title} disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { job_title: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1">
                  {deptOptions.length > 0 ? (
                    <Select label="" options={deptOptions} value={r.department}
                      disabled={r.rowStatus !== 'idle'} placeholder="—"
                      onChange={(e) => updateRow(i, { department: e.target.value })}
                      className="!py-1.5 text-xs" />
                  ) : (
                    <Input label="" value={r.department} disabled={r.rowStatus !== 'idle'}
                      onChange={(e) => updateRow(i, { department: e.target.value })}
                      className="!py-1.5 text-xs" />
                  )}
                </td>
                <td className="px-1 py-1">
                  <Select label="" options={TYPE_OPTIONS} value={r.employment_type}
                    disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { employment_type: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1">
                  <Input label="" type="date" value={r.start_date} disabled={r.rowStatus !== 'idle'}
                    onChange={(e) => updateRow(i, { start_date: e.target.value })}
                    className="!py-1.5 text-xs" />
                </td>
                <td className="px-1 py-1 text-center">
                  {r.rowStatus === 'success' ? (
                    <span className="text-emerald-400 text-base">&#10003;</span>
                  ) : r.rowStatus === 'error' ? (
                    <span className="text-red-400 text-[10px] block" title={r.error}>&#10007;</span>
                  ) : r.rowStatus === 'saving' ? (
                    <span className="text-zinc-500 text-xs">...</span>
                  ) : rows.length > 1 ? (
                    <button onClick={() => removeRow(i)}
                      className="text-zinc-600 hover:text-zinc-400 text-xs">&#10005;</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!done && (
        <div className="mt-3 flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={addRow} disabled={rows.length >= 20 || submitting}>
            + Add Row
          </Button>
          <div className="flex items-center gap-3 text-sm text-zinc-400">
            <label className="flex items-center gap-2">
              <Toggle checked={sendInvitations} onChange={setSendInvitations} disabled={submitting} />
              Send invitations
            </label>
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <Button variant="ghost" onClick={handleClose}>
          {done ? 'Close' : 'Cancel'}
        </Button>
        {done ? (
          <Button onClick={() => { if (successCount > 0) onSuccess(); handleClose() }}>Done</Button>
        ) : (
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Adding...' : `Add ${rows.length} Employee${rows.length > 1 ? 's' : ''}`}
          </Button>
        )}
      </div>
    </Modal>
  )
}
