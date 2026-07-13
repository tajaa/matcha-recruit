import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Modal, Select, Textarea } from '../../components/ui'
import { api, ApiError } from '../../api/client'
import {
  useDisciplinePolicies,
  useDisciplineRecommendation,
} from '../../hooks/discipline/useDiscipline'
import { disciplineApi } from '../../api/discipline'
import type {
  ComplianceVerdict,
  DisciplineLevel,
  DisciplineSeverity,
  DisciplineRecord,
} from '../../api/discipline'
import CompliancePanel from './CompliancePanel'
import { Loader2, Plus, Sparkles, X } from 'lucide-react'

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

/** Pull the verdict out of a 422/409 the server raised from the compliance gate. */
function verdictFromError(e: unknown): ComplianceVerdict | null {
  if (!(e instanceof ApiError)) return null
  if (e.status !== 422 && e.status !== 409) return null
  const detail = (e.body as { detail?: { verdict?: ComplianceVerdict } } | undefined)?.detail
  return detail?.verdict ?? null
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
  const [occurrenceDates, setOccurrenceDates] = useState<string[]>([])
  const [reviewDate, setReviewDate] = useState('')
  const [situation, setSituation] = useState('')
  const [description, setDescription] = useState('')
  const [expectedImprovement, setExpectedImprovement] = useState('')
  const [overrideEnabled, setOverrideEnabled] = useState(false)
  const [overrideLevel, setOverrideLevel] = useState<DisciplineLevel | ''>('')
  const [overrideReason, setOverrideReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  const [drafting, setDrafting] = useState(false)
  const [draftConcerns, setDraftConcerns] = useState<string[]>([])
  const [verdict, setVerdict] = useState<ComplianceVerdict | null>(null)
  const [verdictLoading, setVerdictLoading] = useState(false)
  const [ackReason, setAckReason] = useState('')

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
      setOccurrenceDates([])
      setReviewDate('')
      setSituation('')
      setDescription('')
      setExpectedImprovement('')
      setOverrideEnabled(false)
      setOverrideLevel('')
      setOverrideReason('')
      setFormError('')
      setDraftConcerns([])
      setVerdict(null)
      setAckReason('')
      reset()
    }
  }, [open, prefilledEmployeeId, reset])

  // Live preview of the compliance verdict as the form fills in, so a hard block
  // surfaces before HR has written a letter they can't issue. This is only a
  // preview — POST /records re-runs the same check and is what actually decides.
  useEffect(() => {
    if (!open || !employeeId || !infractionType || occurrenceDates.length === 0) {
      setVerdict(null)
      return
    }
    let cancelled = false
    setVerdictLoading(true)
    const t = setTimeout(() => {
      disciplineApi
        .complianceCheck(employeeId, infractionType, occurrenceDates)
        .then((v) => { if (!cancelled) setVerdict(v) })
        .catch(() => { if (!cancelled) setVerdict(null) })
        .finally(() => { if (!cancelled) setVerdictLoading(false) })
    }, 350)
    return () => { cancelled = true; clearTimeout(t) }
  }, [open, employeeId, infractionType, occurrenceDates])

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

  const addOccurrenceDate = useCallback((value: string) => {
    if (!value) return
    setOccurrenceDates((prev) => (prev.includes(value) ? prev : [...prev, value].sort()))
  }, [])

  const blocked = (verdict?.blocks.length ?? 0) > 0
  const needsAck = !blocked && (verdict?.advisories.length ?? 0) > 0

  const canPreview = employeeId && infractionType && severity && !recLoading
  const canDraft = employeeId && situation.trim().length >= 20 && !drafting

  async function handleDraft() {
    if (!canDraft) return
    setDrafting(true)
    setFormError('')
    try {
      const draft = await disciplineApi.draft({
        employee_id: employeeId,
        situation,
        infraction_type: infractionType || undefined,
        severity,
      })
      setDescription(draft.description)
      setExpectedImprovement(draft.expected_improvement)
      setDraftConcerns(draft.concerns)
      // Only adopt the AI's classification if HR hasn't chosen one — never
      // overwrite a human's explicit call.
      if (!infractionType && draft.suggested_infraction_type) {
        setInfractionType(draft.suggested_infraction_type)
      }
      reset()
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Could not draft the letter')
    } finally {
      setDrafting(false)
    }
  }

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
        occurrence_dates: occurrenceDates,
        situation: situation || undefined,
        review_date: reviewDate || undefined,
        description: description || undefined,
        expected_improvement: expectedImprovement || undefined,
        override_level: overrideEnabled,
        override_reason: overrideEnabled ? overrideReason : undefined,
        advisory_ack_reason: ackReason.trim() || undefined,
      })
      onIssued?.(record)
      onClose()
      navigate(`/app/discipline/${record.id}`)
    } catch (e) {
      // The server's verdict supersedes whatever the live preview showed — it
      // ran the AI text review the preview doesn't, and it is the only authority.
      const serverVerdict = verdictFromError(e)
      if (serverVerdict) {
        setVerdict(serverVerdict)
        setFormError(
          serverVerdict.blocks.length > 0
            ? 'This action is barred by state law — see below.'
            : 'Review the flagged risks below and record why you are proceeding.',
        )
      } else {
        setFormError(e instanceof Error ? e.message : 'Failed to issue performance action record')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Issue Performance Action" width="lg">
      <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
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

        <div>
          <div className="mb-1 flex items-center gap-2">
            <label className="text-sm font-medium text-zinc-300">Date(s) of conduct</label>
            <span className="text-xs text-zinc-500">
              when it happened — checked against protected leave
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value=""
              onChange={(e) => addOccurrenceDate(e.target.value)}
            />
            <Plus className="h-4 w-4 shrink-0 text-zinc-600" />
          </div>
          {occurrenceDates.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {occurrenceDates.map((d) => (
                <span
                  key={d}
                  className="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-1 text-xs text-zinc-200"
                >
                  {d}
                  <button
                    type="button"
                    onClick={() => setOccurrenceDates((prev) => prev.filter((x) => x !== d))}
                    className="text-zinc-500 hover:text-zinc-200"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
          <Textarea
            label="What happened?"
            placeholder="Describe the situation in your own words — the AI will draft the letter from this."
            value={situation}
            onChange={(e) => setSituation(e.target.value)}
            rows={3}
          />
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-zinc-500">
              You review and edit every word before anything is issued.
            </span>
            <Button variant="secondary" onClick={handleDraft} disabled={!canDraft}>
              {drafting
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Sparkles className="h-4 w-4" />}
              <span className="ml-2">Draft letter</span>
            </Button>
          </div>
          {draftConcerns.length > 0 && (
            <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-amber-300/90">
              {draftConcerns.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          )}
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

        <CompliancePanel
          verdict={verdict}
          loading={verdictLoading}
          ackReason={ackReason}
          onAckReasonChange={setAckReason}
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
          <Button
            onClick={handleIssue}
            disabled={
              !recommendation ||
              submitting ||
              blocked ||
              (needsAck && ackReason.trim().length === 0)
            }
          >
            {submitting
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : blocked ? 'Barred by state law' : 'Issue record'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
