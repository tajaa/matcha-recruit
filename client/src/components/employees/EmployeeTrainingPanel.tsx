import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GraduationCap, Loader2, AlertTriangle, Download } from 'lucide-react'
import { Badge, Button, Select } from '../ui'
import { useEmployeeTraining } from '../../hooks/employees/useEmployeeTraining'
import { trainingApi, type TrainingRecord, type TrainingSourceType, type TrainingRequirement } from '../../api/training/training'

const STATUS_VARIANT: Record<TrainingRecord['status'], 'neutral' | 'success' | 'warning' | 'danger'> = {
  assigned: 'neutral',
  in_progress: 'warning',
  completed: 'success',
  expired: 'danger',
  waived: 'neutral',
}

function sourceLabel(record: TrainingRecord): { text: string; link?: string } {
  const source: TrainingSourceType = record.source_type
  switch (source) {
    case 'incident':
      return record.source_ref
        ? { text: 'From an incident', link: `/app/ir/${record.source_ref}` }
        : { text: 'From an incident' }
    case 'discipline':
      return record.source_ref
        ? { text: 'Remedial — discipline record', link: `/app/discipline/${record.source_ref}` }
        : { text: 'Remedial — discipline record' }
    case 'new_hire':
      return { text: 'New-hire assignment rule' }
    case 'rule':
      return { text: 'Scheduled assignment rule' }
    case 'credential':
      return { text: 'Credential lapse' }
    case 'cadence':
      return { text: 'Recurring compliance cadence' }
    case 'bulk_assign':
      return { text: 'Bulk-assigned by an admin' }
    default:
      return { text: 'Manually assigned' }
  }
}

function ExpirationNote({ record }: { record: TrainingRecord }) {
  if (record.status === 'completed' && record.expiration_date) {
    const exp = new Date(record.expiration_date)
    const daysUntil = Math.ceil((exp.getTime() - Date.now()) / 86_400_000)
    if (daysUntil < 0) return <span className="text-red-400">Expired {exp.toLocaleDateString()}</span>
    if (daysUntil <= 60) return <span className="text-amber-400">Expires in {daysUntil}d</span>
    return <span className="text-zinc-500">Valid until {exp.toLocaleDateString()}</span>
  }
  if (record.due_date && (record.status === 'assigned' || record.status === 'in_progress')) {
    const due = new Date(record.due_date)
    const overdue = due.getTime() < Date.now()
    return (
      <span className={overdue ? 'text-red-400' : 'text-zinc-500'}>
        {overdue ? 'Overdue since' : 'Due'} {due.toLocaleDateString()}
      </span>
    )
  }
  return null
}

export function EmployeeTrainingPanel({ employeeId }: { employeeId: string }) {
  const { records, loading, error, refetch, waive } = useEmployeeTraining(employeeId)
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])
  const [showAssign, setShowAssign] = useState(false)
  const [requirementId, setRequirementId] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [assigning, setAssigning] = useState(false)
  const [waivingId, setWaivingId] = useState<string | null>(null)
  const [waiveReason, setWaiveReason] = useState('')
  const [mutError, setMutError] = useState('')

  useEffect(() => {
    trainingApi.listRequirements().then(setRequirements).catch(() => setRequirements([]))
  }, [])

  async function submitAssign() {
    const requirement = requirements.find((r) => r.id === requirementId)
    if (!requirement) return
    setAssigning(true)
    setMutError('')
    try {
      await trainingApi.createRecord({
        employee_id: employeeId,
        requirement_id: requirement.id,
        title: requirement.title,
        training_type: requirement.training_type,
        due_date: dueDate || undefined,
      })
      setRequirementId(''); setDueDate(''); setShowAssign(false)
      refetch()
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to assign training')
    } finally {
      setAssigning(false)
    }
  }

  async function submitWaive(recordId: string) {
    if (!waiveReason.trim()) return
    try {
      await waive(recordId, waiveReason.trim())
      setWaivingId(null)
      setWaiveReason('')
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to waive')
    }
  }

  async function openCertificate(recordId: string) {
    try {
      const { url } = await trainingApi.certificateUrl(recordId)
      window.open(url, '_blank')
    } catch {
      setMutError('Certificate not available yet')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading training…
      </div>
    )
  }
  if (error) return <p className="text-sm text-red-400">{error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <GraduationCap className="w-4 h-4 text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-200">Training</h3>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setShowAssign((v) => !v)}>
          Assign training
        </Button>
      </div>

      {mutError && (
        <div className="flex items-center gap-2 text-xs text-red-400 mb-3">
          <AlertTriangle className="w-3.5 h-3.5" /> {mutError}
        </div>
      )}

      {showAssign && (
        <div className="mb-4 p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 space-y-2">
          <Select
            label="Requirement"
            value={requirementId}
            onChange={(e) => setRequirementId(e.target.value)}
            placeholder="Select a training requirement…"
            options={requirements.map((r) => ({ value: r.id, label: r.title }))}
          />
          <div>
            <label className="text-xs text-zinc-500">Due date (optional)</label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full mt-1 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1.5 text-sm text-zinc-200"
            />
          </div>
          <Button size="sm" disabled={assigning || !requirementId} onClick={submitAssign}>
            {assigning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Assign'}
          </Button>
        </div>
      )}

      {records.length === 0 ? (
        <p className="text-sm text-zinc-500">No training assigned to this employee.</p>
      ) : (
        <div className="space-y-2">
          {records.map((r) => {
            const src = sourceLabel(r)
            return (
              <div key={r.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <p className="text-sm font-medium text-zinc-200 truncate">{r.title}</p>
                      <Badge variant={STATUS_VARIANT[r.status]}>{r.status.replace('_', ' ')}</Badge>
                    </div>
                    <p className="text-[11px] text-zinc-500">
                      {src.link ? <Link to={src.link} className="hover:text-emerald-400">{src.text}</Link> : src.text}
                      {r.source_note ? ` — ${r.source_note}` : ''}
                    </p>
                    <p className="text-[11px] mt-1"><ExpirationNote record={r} /></p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.status === 'completed' && (
                      <Button size="sm" variant="ghost" onClick={() => openCertificate(r.id)}>
                        <Download className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    {(r.status === 'assigned' || r.status === 'in_progress') && waivingId !== r.id && (
                      <Button size="sm" variant="ghost" onClick={() => setWaivingId(r.id)}>
                        Waive
                      </Button>
                    )}
                  </div>
                </div>
                {waivingId === r.id && (
                  <div className="mt-2 flex items-center gap-2">
                    <input
                      type="text"
                      value={waiveReason}
                      onChange={(e) => setWaiveReason(e.target.value)}
                      placeholder="Reason for waiver"
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200"
                    />
                    <Button size="sm" disabled={!waiveReason.trim()} onClick={() => submitWaive(r.id)}>
                      Confirm
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setWaivingId(null); setWaiveReason('') }}>
                      Cancel
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
