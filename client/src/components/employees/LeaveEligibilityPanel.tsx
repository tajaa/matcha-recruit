import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Card } from '../ui'

interface FmlaSection {
  eligible: boolean
  reasons: string[]
  months_employed: number | null
  hours_worked_12mo: number
  hours_worked_12mo_source: string
  hours_worked_assumed_weekly: number | null
  hours_worked_note: string
  company_employee_count: number
}

interface StateProgram {
  program: string
  label: string
  eligible: boolean
  paid: boolean
  max_weeks: number | null
  wage_replacement_pct: number | null
  job_protection: boolean
  reasons: string[]
  notes: string | null
  source_url: string | null
}

interface ProtectionSummary {
  fmla_protected_weeks: number
  state_protected_weeks: number
  total_protected_weeks: number
  weeks_used: number
  weeks_remaining: number
  qualifying_state_programs: string[]
}

interface LeaveEligibility {
  fmla: FmlaSection
  state_programs: { state: string | null; programs: StateProgram[]; message?: string }
  checked_at: string
  protection: ProtectionSummary
}

export function LeaveEligibilityPanel({ employeeId }: { employeeId: string }) {
  const [data, setData] = useState<LeaveEligibility | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.get<LeaveEligibility>(`/employees/${employeeId}/leave/eligibility`)
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [employeeId])

  if (loading) return <p className="text-sm text-zinc-500">Computing eligibility...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!data) return null

  // Map program keys → human labels so the "Stacks" line in the protection
  // card shows e.g. "CA Paid Family Leave" instead of "ca_pfl".
  const programLabelByKey = new Map(
    data.state_programs.programs.map((p) => [p.program, p.label]),
  )
  const stackedStateLabels = data.protection.qualifying_state_programs.map(
    (k) => programLabelByKey.get(k) ?? k,
  )

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="text-sm font-medium mb-3 text-zinc-300">Job-Protected Leave Remaining</h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{data.protection.weeks_remaining.toFixed(1)}</div>
            <div className="text-xs text-zinc-500">weeks remaining</div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{data.protection.total_protected_weeks}</div>
            <div className="text-xs text-zinc-500">total protected</div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-100">{data.protection.weeks_used.toFixed(1)}</div>
            <div className="text-xs text-zinc-500">weeks used</div>
          </div>
        </div>
        {stackedStateLabels.length > 0 && (
          <p className="text-[11px] text-zinc-500 mt-3">
            Stacks: FMLA ({data.protection.fmla_protected_weeks} wks) +{' '}
            {stackedStateLabels.join(', ')} ({data.protection.state_protected_weeks} wks).
          </p>
        )}
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-zinc-300">FMLA (Federal)</h3>
          <Badge variant={data.fmla.eligible ? 'success' : 'neutral'}>
            {data.fmla.eligible ? 'Eligible' : 'Not eligible'}
          </Badge>
        </div>
        <dl className="text-xs grid grid-cols-3 gap-3 mb-2">
          <div>
            <dt className="text-zinc-500">Tenure</dt>
            <dd className="text-zinc-300">{data.fmla.months_employed != null ? `${data.fmla.months_employed.toFixed(1)} months` : '—'}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Hours (12 mo)</dt>
            <dd className="text-zinc-300">{data.fmla.hours_worked_12mo.toFixed(0)}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Company size</dt>
            <dd className="text-zinc-300">{data.fmla.company_employee_count}</dd>
          </div>
        </dl>
        {data.fmla.hours_worked_note && (
          <p className="text-[11px] text-zinc-600 italic mb-2">{data.fmla.hours_worked_note}</p>
        )}
        {!data.fmla.eligible && data.fmla.reasons.length > 0 && (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Why not</p>
            <ul className="text-xs text-zinc-400 list-disc list-inside space-y-0.5">
              {data.fmla.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-medium text-zinc-300 mb-3">
          State Leave Programs {data.state_programs.state ? `(${data.state_programs.state})` : ''}
        </h3>
        {data.state_programs.programs.length === 0 ? (
          <p className="text-xs text-zinc-500">
            No state-specific leave programs apply{data.state_programs.state ? '' : ' — work state not set on employee record'}.
          </p>
        ) : (
          <div className="space-y-3">
            {data.state_programs.programs.map((p) => (
              <div
                key={p.program}
                className="border-l-2 pl-3 py-1"
                style={{ borderColor: p.eligible ? '#10b981' : '#52525b' }}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-zinc-200">{p.label}</span>
                  <Badge variant={p.eligible ? 'success' : 'neutral'}>
                    {p.eligible ? 'Eligible' : 'Not eligible'}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500 mt-1">
                  {p.paid && (p.wage_replacement_pct ?? 0) > 0 && (
                    <span>Paid · {p.wage_replacement_pct}% wage replacement</span>
                  )}
                  {!p.paid && <span>Unpaid</span>}
                  {(p.max_weeks ?? 0) > 0 && <span>Up to {p.max_weeks} weeks</span>}
                  {p.job_protection && <span>Job-protected</span>}
                  {p.source_url && (
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-400 hover:underline"
                    >
                      source
                    </a>
                  )}
                </div>
                {!p.eligible && p.reasons.length > 0 && (
                  <ul className="text-[11px] text-zinc-500 list-disc list-inside mt-1 space-y-0.5">
                    {p.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                )}
                {p.notes && <p className="text-[11px] text-zinc-500 italic mt-1">{p.notes}</p>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <p className="text-[10px] text-zinc-600 text-right">
        Computed {new Date(data.checked_at).toLocaleString()}. Informational only — not legal advice.
      </p>
    </div>
  )
}
