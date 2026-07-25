import { useEffect, useState } from 'react'
import { GraduationCap, Loader2, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Card, Button, Select, Badge } from '../ui'
import { useIncidentTrainings } from '../../hooks/ir/useIncidentTrainings'
import { trainingApi, type TrainingRequirement } from '../../api/training/training'

const STATUS_VARIANT: Record<string, 'neutral' | 'success' | 'warning' | 'danger'> = {
  assigned: 'neutral',
  in_progress: 'warning',
  completed: 'success',
  expired: 'danger',
  waived: 'neutral',
}

/**
 * Admin-triggered "assign training" from an incident (B2 of the training
 * integration). Defaults to the incident's involved_employee_ids server-side
 * — this panel intentionally has no employee picker in v1.
 */
export function IRAssignTrainingPanel({ incidentId }: { incidentId: string }) {
  const { trainings, loading, error, assignTraining } = useIncidentTrainings(incidentId)
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([])
  const [showAssign, setShowAssign] = useState(false)
  const [requirementId, setRequirementId] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [mutError, setMutError] = useState('')
  const [lastResult, setLastResult] = useState<string | null>(null)

  useEffect(() => {
    trainingApi.listRequirements().then(setRequirements).catch(() => setRequirements([]))
  }, [])

  async function submitAssign() {
    if (!requirementId) return
    setSaving(true)
    setMutError('')
    try {
      const result = await assignTraining({
        requirement_id: requirementId,
        due_date: dueDate || null,
        note: note.trim() || null,
      })
      setLastResult(
        result.assigned_count
          ? `Assigned to ${result.assigned_count} employee(s).`
          : result.accelerated_count
            ? `Already assigned to ${result.accelerated_count} employee(s) — due date pulled in.`
            : result.already_open_count
              ? `Already assigned to ${result.already_open_count} employee(s) — no change needed.`
              : 'No matching employees to assign.',
      )
      setRequirementId(''); setDueDate(''); setNote(''); setShowAssign(false)
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to assign training')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <GraduationCap className="w-4 h-4 text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-200">Training</h3>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setShowAssign((v) => !v)}>
          Assign training
        </Button>
      </div>

      {lastResult && (
        <div className="flex items-center gap-2 text-xs text-emerald-300 mb-3">
          <CheckCircle2 className="w-3.5 h-3.5" /> {lastResult}
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
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-zinc-500">Due date (optional)</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full mt-1 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1.5 text-sm text-zinc-200"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500">Note (optional)</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Why this training"
                className="w-full mt-1 bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1.5 text-sm text-zinc-200"
              />
            </div>
          </div>
          <p className="text-xs text-zinc-500">
            Assigned to this incident's involved employees.
          </p>
          {mutError && (
            <div className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertTriangle className="w-3.5 h-3.5" /> {mutError}
            </div>
          )}
          <Button size="sm" disabled={saving || !requirementId} onClick={submitAssign}>
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Assign'}
          </Button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="text-xs text-red-400">{error}</p>
      ) : trainings.length === 0 ? (
        <p className="text-xs text-zinc-500">No training assigned from this incident yet.</p>
      ) : (
        <div className="space-y-1.5">
          {trainings.map((t) => (
            <div key={t.id} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-zinc-300 truncate">{t.title}</span>
                <span className="text-zinc-500 truncate">— {t.employee_name}</span>
              </div>
              <Badge variant={STATUS_VARIANT[t.status] || 'neutral'}>{t.status.replace('_', ' ')}</Badge>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
