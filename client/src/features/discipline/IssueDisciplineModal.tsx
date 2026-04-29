import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Modal, Select, Textarea } from '../../components/ui'
import { api } from '../../api/client'
import {
  useDisciplinePolicies,
  useDisciplineRecommendation,
} from '../../hooks/discipline/useDiscipline'
import type {
  DisciplineLevel,
  DisciplineSeverity,
  DisciplineRecord,
} from '../../api/discipline'
import { Loader2, Sparkles } from 'lucide-react'

type EmployeeOption = {
  id: string
  first_name: string | null
  last_name: string | null
  department?: string | null
}

function fullName(e: EmployeeOption): string {
  return [e.first_name || '', e.last_name || ''].join(' ').trim() || e.id.slice(0, 8)
}

type Props = {
  open: boolean
  onClose: () => void
  prefilledEmployeeId?: string
  onIssued?: (record: DisciplineRecord) => void
}

const SEVERITIES: { value: DisciplineSeverity; label: string }[] = [
  { value: 'minor', label: 'Minor' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'severe', label: 'Severe' },
  { value: 'immediate_written', label: 'Immediate Written' },
]

const LEVEL_LABEL: Record<DisciplineLevel, string> = {
  verbal_warning: 'Verbal Warning',
  written_warning: 'Written Warning',
  pip: 'Performance Improvement Plan',
  final_warning: 'Final Warning',
  suspension: 'Suspension',
}

export default function IssueDisciplineModal({
  open,
  onClose,
  prefilledEmployeeId,
  onIssued,
}: Props) {
  const navigate = useNavigate()
  const { policies } = useDisciplinePolicies()
  const { recommendation, recommend, issue, reset, loading: recLoading, error: recError } =
    useDisciplineRecommendation()

  const [employees, setEmployees] = useState<EmployeeOption[]>([])
  const [employeeId, setEmployeeId] = useState(prefilledEmployeeId || '')
  const [infractionType, setInfractionType] = useState('')
  const [severity, setSeverity] = useState<DisciplineSeverity>('moderate')
  const [issuedDate, setIssuedDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [reviewDate, setReviewDate] = useState('')
  const [description, setDescription] = useState('')
  const [expectedImprovement, setExpectedImprovement] = useState('')
  const [overrideEnabled, setOverrideEnabled] = useState(false)
  const [overrideLevel, setOverrideLevel] = useState<DisciplineLevel | ''>('')
  const [overrideReason, setOverrideReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  useEffect(() => {
    if (!open) return
    api.get<EmployeeOption[]>('/employees')
      .then((rows) => setEmployees(Array.isArray(rows) ? rows : []))
      .catch(() => setEmployees([]))
  }, [open])

  useEffect(() => {
    if (!open) {
      setEmployeeId(prefilledEmployeeId || '')
      setInfractionType('')
      setSeverity('moderate')
      setIssuedDate(new Date().toISOString().slice(0, 10))
      setReviewDate('')
      setDescription('')
      setExpectedImprovement('')
      setOverrideEnabled(false)
      setOverrideLevel('')
      setOverrideReason('')
      setFormError('')
      reset()
    }
  }, [open, prefilledEmployeeId, reset])

  const policyOptions = useMemo(
    () => policies.map((p) => ({ value: p.infraction_type, label: p.label })),
    [policies],
  )

  const employeeOptions = useMemo(
    () => employees.map((e) => {
      const name = fullName(e)
      return {
        value: e.id,
        label: e.department ? `${name} — ${e.department}` : name,
      }
    }),
    [employees],
  )

  const canPreview =
    employeeId && infractionType && severity && !recLoading

  async function handlePreview() {
    setFormError('')
    if (!canPreview) return
    await recommend({
      employee_id: employeeId,
      infraction_type: infractionType,
      severity,
    })
  }

  async function handleIssue() {
    if (!recommendation) return
    if (overrideEnabled && overrideReason.trim().length < 20) {
      setFormError('Override reason must be at least 20 characters.')
      return
    }
    setSubmitting(true)
    setFormError('')
    try {
      const record = await issue({
        employee_id: employeeId,
        infraction_type: infractionType,
        severity,
        discipline_type:
          (overrideEnabled && overrideLevel ? overrideLevel : recommendation.recommended_level),
        issued_date: issuedDate,
        review_date: reviewDate || undefined,
        description: description || undefined,
        expected_improvement: expectedImprovement || undefined,
        override_level: overrideEnabled,
        override_reason: overrideEnabled ? overrideReason : undefined,
      })
      onIssued?.(record)
      onClose()
      navigate(`/app/discipline/${record.id}`)
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to issue discipline record')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Issue Discipline" width="lg">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Employee"
            placeholder="Select employee"
            options={employeeOptions}
            value={employeeId}
            onChange={(e) => { setEmployeeId(e.target.value); reset() }}
          />
          <Select
            label="Infraction type"
            placeholder="Select type"
            options={policyOptions}
            value={infractionType}
            onChange={(e) => { setInfractionType(e.target.value); reset() }}
          />
          <Select
            label="Severity"
            options={SEVERITIES}
            value={severity}
            onChange={(e) => { setSeverity(e.target.value as DisciplineSeverity); reset() }}
          />
          <Input
            label="Issued date"
            type="date"
            value={issuedDate}
            onChange={(e) => setIssuedDate(e.target.value)}
          />
        </div>

        <Textarea
          label="Description of conduct"
          placeholder="Concise summary of what happened, when, and witnesses (if any)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
        />
        <Textarea
          label="Expected improvement"
          placeholder="What the employee needs to demonstrate going forward"
          value={expectedImprovement}
          onChange={(e) => setExpectedImprovement(e.target.value)}
          rows={2}
        />
        <Input
          label="Review date (optional)"
          type="date"
          value={reviewDate}
          onChange={(e) => setReviewDate(e.target.value)}
        />

        <div className="flex items-center justify-between border-t border-zinc-800 pt-4">
          <Button
            variant="secondary"
            onClick={handlePreview}
            disabled={!canPreview}
          >
            {recLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            <span className="ml-2">Preview recommendation</span>
          </Button>
          {recError && <span className="text-sm text-red-400">{recError}</span>}
        </div>

        {recommendation && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 space-y-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Recommended level</div>
              <div className="text-lg font-semibold text-zinc-100">
                {LEVEL_LABEL[recommendation.recommended_level]}
                {recommendation.auto_to_written_triggered && (
                  <span className="ml-2 text-xs font-normal text-amber-400">
                    auto-to-written triggered
                  </span>
                )}
                {recommendation.termination_review && (
                  <span className="ml-2 text-xs font-normal text-red-400">
                    termination review
                  </span>
                )}
              </div>
              <div className="text-xs text-zinc-500 mt-1">
                Lookback {recommendation.lookback_months} months · Supersedes{' '}
                {recommendation.supersedes.length} prior record(s)
              </div>
            </div>
            <ul className="text-sm text-zinc-400 space-y-1 list-disc list-inside">
              {recommendation.reasoning.map((r, i) => (
                <li key={i}>{r.text}</li>
              ))}
            </ul>

            <div className="border-t border-zinc-800 pt-3">
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  checked={overrideEnabled}
                  onChange={(e) => setOverrideEnabled(e.target.checked)}
                />
                Override recommended level
              </label>
              {overrideEnabled && (
                <div className="mt-2 space-y-2">
                  <Select
                    label="Override level"
                    placeholder="Pick level"
                    options={Object.entries(LEVEL_LABEL).map(([value, label]) => ({ value, label }))}
                    value={overrideLevel}
                    onChange={(e) => setOverrideLevel(e.target.value as DisciplineLevel)}
                  />
                  <Textarea
                    label="Override reason (min 20 chars)"
                    value={overrideReason}
                    onChange={(e) => setOverrideReason(e.target.value)}
                    rows={2}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {formError && <div className="text-sm text-red-400">{formError}</div>}

        <div className="flex justify-end gap-2 pt-2 border-t border-zinc-800">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleIssue} disabled={!recommendation || submitting}>
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Issue record'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
