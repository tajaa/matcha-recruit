import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Input, Select } from '../ui'
import type { InvestigationInterview, InvestigationInterviewCreate, IRWitness } from '../../types/ir'
import type { BadgeVariant } from '../ui'

const INTERVIEW_ROLE_OPTIONS = [
  { value: 'complainant', label: 'Complainant' },
  { value: 'respondent', label: 'Respondent' },
  { value: 'witness', label: 'Witness' },
  { value: 'manager', label: 'Manager' },
]

type Props = { incidentId: string; witnesses: IRWitness[] }

export function IRInterviewScheduler({ incidentId, witnesses }: Props) {
  const [interviews, setInterviews] = useState<InvestigationInterview[]>([])
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<InvestigationInterviewCreate[]>([])
  const [msg, setMsg] = useState('')
  const [scheduling, setScheduling] = useState(false)

  const fetchInterviews = useCallback(async () => {
    setLoading(true)
    try { setInterviews(await api.get<InvestigationInterview[]>(`/ir/incidents/${incidentId}/investigation-interviews`)) }
    catch { setInterviews([]) }
    finally { setLoading(false) }
  }, [incidentId])

  useEffect(() => { fetchInterviews() }, [fetchInterviews])

  function prefillFromWitnesses() {
    if (!witnesses?.length) return
    setRows(witnesses.map((w) => ({
      interviewee_name: w.name,
      interviewee_email: w.contact || '',
      interviewee_role: 'witness',
    })))
  }

  async function schedule() {
    const valid = rows.filter((r) => r.interviewee_name.trim() && r.interviewee_role)
    if (valid.length === 0) return
    setScheduling(true)
    try {
      const payload = valid.map((r) => ({
        interviewee_name: r.interviewee_name.trim(),
        interviewee_email: r.interviewee_email?.trim() || null,
        interviewee_role: r.interviewee_role,
        send_invite: !!r.interviewee_email?.trim(),
        custom_message: msg || null,
      }))
      await api.post(`/ir/incidents/${incidentId}/investigation-interviews/batch`, payload)
      setRows([])
      setMsg('')
      fetchInterviews()
    } finally { setScheduling(false) }
  }

  async function cancel(id: string) {
    await api.delete(`/ir/incidents/${incidentId}/investigation-interviews/${id}`)
    setInterviews((prev) => prev.filter((i) => i.id !== id))
  }

  async function resend(id: string) {
    await api.post(`/ir/incidents/${incidentId}/investigation-interviews/${id}/resend-invite`)
  }

  return (
    <div className="space-y-5">
      {loading ? (
        <p className="text-sm text-zinc-500">Loading interviews...</p>
      ) : interviews.length === 0 ? (
        <p className="text-sm text-zinc-600">No investigation interviews scheduled yet.</p>
      ) : (
        <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
          {interviews.map((iv) => (
            <div key={iv.id} className="px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-zinc-200">{iv.interviewee_name}</span>
                  {iv.interviewee_role && <Badge variant="neutral">{iv.interviewee_role}</Badge>}
                  <Badge variant={iv.status === 'completed' ? 'success' : iv.status === 'pending' ? 'warning' : 'neutral' as BadgeVariant}>
                    {iv.status}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  {iv.status === 'pending' && iv.interviewee_email && (
                    <button type="button" onClick={() => resend(iv.id)} className="text-xs text-zinc-500 hover:text-zinc-300">Resend</button>
                  )}
                  {iv.status === 'pending' && (
                    <button type="button" onClick={() => cancel(iv.id)} className="text-xs text-zinc-600 hover:text-red-400">Cancel</button>
                  )}
                </div>
              </div>
              {iv.interviewee_email && <p className="text-xs text-zinc-500 mt-0.5">{iv.interviewee_email}</p>}
              <p className="text-[11px] text-zinc-600 mt-0.5">Created {new Date(iv.created_at).toLocaleDateString()}</p>
            </div>
          ))}
        </div>
      )}

      <div className="border border-zinc-800 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Schedule Interviews</p>
          <div className="flex items-center gap-2">
            {witnesses && witnesses.length > 0 && (
              <button type="button" onClick={prefillFromWitnesses} className="text-xs text-emerald-400 hover:text-emerald-300">
                Pre-fill from witnesses
              </button>
            )}
            <button type="button" onClick={() => setRows([...rows, { interviewee_name: '', interviewee_email: '', interviewee_role: 'witness' }])}
              className="text-xs text-emerald-400 hover:text-emerald-300">+ Add</button>
          </div>
        </div>
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input label="" placeholder="Name" value={row.interviewee_name}
              onChange={(e) => { const copy = [...rows]; copy[i] = { ...copy[i], interviewee_name: e.target.value }; setRows(copy) }} className="flex-1" />
            <Input label="" placeholder="Email" value={row.interviewee_email || ''}
              onChange={(e) => { const copy = [...rows]; copy[i] = { ...copy[i], interviewee_email: e.target.value }; setRows(copy) }} className="flex-1" />
            <div className="w-32">
              <Select label="" options={INTERVIEW_ROLE_OPTIONS} value={row.interviewee_role}
                onChange={(e) => { const copy = [...rows]; copy[i] = { ...copy[i], interviewee_role: e.target.value }; setRows(copy) }} />
            </div>
            <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))}
              className="text-xs text-zinc-600 hover:text-red-400">&times;</button>
          </div>
        ))}
        {rows.length > 0 && (
          <>
            <textarea
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-zinc-600"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Custom message for invite emails (optional)"
            />
            <Button size="sm" disabled={scheduling} onClick={schedule}>
              {scheduling ? 'Scheduling...' : `Schedule ${rows.filter((r) => r.interviewee_name.trim()).length} Interview(s)`}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
