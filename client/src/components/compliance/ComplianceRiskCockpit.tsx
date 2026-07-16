import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, CheckCircle2, ChevronRight,
  Loader2, ShieldCheck, UserPlus,
} from 'lucide-react'
import { LABEL } from '../ui/typography'
import { fetchAssignableUsers } from '../../api/compliance'
import type {
  AssignableUser, ComplianceActionPlanUpdate, ComplianceRiskSummary,
  PinnedRequirement, RiskIssue,
} from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'

const PANEL = 'rounded-lg border border-white/[0.06] bg-zinc-950'

// Severity semantics — the spine of the whole surface.
const SEV = {
  critical: { rail: 'border-l-red-500', dot: 'bg-red-500', text: 'text-red-400', chip: 'text-red-300' },
  high: { rail: 'border-l-amber-500', dot: 'bg-amber-500', text: 'text-amber-400', chip: 'text-amber-300' },
  moderate: { rail: 'border-l-zinc-500', dot: 'bg-zinc-500', text: 'text-zinc-400', chip: 'text-zinc-300' },
} as const

const SOURCE_LABEL: Record<RiskIssue['source'], string> = {
  wage: 'Wage & Hour',
  credential: 'Credentialing',
  incident: 'Safety / OSHA',
  alert: 'Regulatory',
}

const FIX_VERB: Record<RiskIssue['source'], string> = {
  wage: 'Fix pay', credential: 'Renew', incident: 'Open incident', alert: 'Assign owner',
}

function money(v: number) {
  return `$${Math.round(v).toLocaleString()}`
}

type Props = {
  riskSummary: ComplianceRiskSummary | null
  loading: boolean
  pinnedReqs: PinnedRequirement[]
  onOpenAlerts: () => void
  onUpdateActionPlan: (alertId: string, plan: ComplianceActionPlanUpdate) => Promise<void>
  onActioned: () => void
}

export function ComplianceRiskCockpit({
  riskSummary, loading, pinnedReqs, onOpenAlerts, onUpdateActionPlan, onActioned,
}: Props) {
  const navigate = useNavigate()

  if (loading && !riskSummary) {
    return (
      <div className="flex items-center gap-2 px-4 py-16 justify-center text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Measuring compliance risk…
      </div>
    )
  }
  if (!riskSummary) {
    return <p className="text-sm text-zinc-600 px-4 py-8">Risk summary unavailable. Try again shortly.</p>
  }

  const { posture: p, issues, get_ahead } = riskSummary
  const totalOpen = p.open_critical + p.open_high + p.open_moderate
  const clear = totalOpen === 0

  return (
    <div className="space-y-4">
      <VerdictBanner critical={p.open_critical} totalOpen={totalOpen} clear={clear} />

      {/* Posture strip — one panel, four cells, hairline dividers. */}
      <div className={`${PANEL} grid grid-cols-2 divide-x divide-y divide-white/[0.06] md:grid-cols-4 md:divide-y-0`}>
        <PostureCell label="Open issues">
          <div className="flex flex-col gap-1 mt-0.5">
            <SevLine dot={SEV.critical.dot} n={p.open_critical} word="critical" active={p.open_critical > 0} />
            <SevLine dot={SEV.high.dot} n={p.open_high} word="high" active={p.open_high > 0} />
            <SevLine dot={SEV.moderate.dot} n={p.open_moderate} word="moderate" active={p.open_moderate > 0} />
          </div>
        </PostureCell>

        {/* Signature cell: the measured dollar figure + the authority behind it. */}
        <PostureCell label="Est. penalty exposure">
          <ExposureFigure posture={p} issues={issues} />
        </PostureCell>

        <PostureCell label="Employees affected">
          <EmployeesAffected posture={p} issues={issues} />
        </PostureCell>

        <PostureCell label="Next deadline">
          {p.next_deadline_days != null ? (
            <>
              <p className="font-mono text-2xl font-semibold tabular-nums text-zinc-100">
                {p.next_deadline_days}<span className="text-sm text-zinc-500 ml-1">days</span>
              </p>
              <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{p.next_deadline_label}</p>
            </>
          ) : (
            <p className="text-sm text-zinc-600 mt-1">Nothing scheduled</p>
          )}
        </PostureCell>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Action queue */}
        <div className="lg:col-span-2 space-y-2">
          <div className="flex items-center justify-between">
            <h2 className={LABEL}>Action queue</h2>
            <span className="text-[11px] text-zinc-600">Ranked by severity, then deadline</span>
          </div>
          {issues.length === 0 ? (
            <div className={`${PANEL} flex items-center gap-2 px-4 py-8 text-sm text-emerald-300/80`}>
              <ShieldCheck className="h-4 w-4" /> No open compliance issues. You're clear.
            </div>
          ) : (
            <div className="space-y-2">
              {issues.map((iss) => (
                <IssueRow
                  key={iss.id}
                  issue={iss}
                  onFix={() => iss.link && navigate(iss.link)}
                  onOpenAlerts={onOpenAlerts}
                  onUpdateActionPlan={onUpdateActionPlan}
                  onActioned={onActioned}
                />
              ))}
            </div>
          )}
        </div>

        {/* Get-ahead lane */}
        <div className="space-y-2">
          <h2 className={LABEL}>Get ahead</h2>
          {get_ahead.length === 0 ? (
            <div className={`${PANEL} px-4 py-6 text-sm text-zinc-600`}>Nothing on the horizon.</div>
          ) : (
            <div className={`${PANEL} divide-y divide-white/[0.06]`}>
              {get_ahead.map((g, i) => (
                <GetAheadRow key={i} title={g.title} days={g.days_until ?? null}
                  kind={g.kind} loc={g.location_label} />
              ))}
            </div>
          )}

          {pinnedReqs.length > 0 && (
            <div className="pt-1">
              <h3 className={`${LABEL} mb-1.5`}>Pinned</h3>
              <div className={`${PANEL} divide-y divide-white/[0.06]`}>
                {pinnedReqs.slice(0, 5).map((req) => (
                  <div key={req.id} className="px-3 py-2">
                    <p className="text-xs text-zinc-300 line-clamp-1">{req.title}</p>
                    <span className="text-[10px] text-zinc-600">
                      {CATEGORY_LABELS[req.category] || req.category}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Verdict banner (the glance-value annunciator) ──
function VerdictBanner({ critical, totalOpen, clear }: { critical: number; totalOpen: number; clear: boolean }) {
  if (clear) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
        <p className="text-sm text-emerald-200">In compliance — no open issues across your roster and jurisdictions.</p>
      </div>
    )
  }
  const urgent = critical > 0
  return (
    <div className={`flex items-center gap-2.5 rounded-lg border px-4 py-3 ${
      urgent ? 'border-red-500/40 bg-red-500/[0.07]' : 'border-amber-500/30 bg-amber-500/[0.06]'
    }`}>
      <AlertTriangle className={`h-4 w-4 shrink-0 ${urgent ? 'text-red-400' : 'text-amber-400'}`} />
      <p className="text-sm text-zinc-100">
        {urgent ? (
          <><b className="font-semibold text-red-300">{critical} critical</b> {critical === 1 ? 'issue needs' : 'issues need'} action now.</>
        ) : (
          <><b className="font-semibold text-amber-300">{totalOpen}</b> open {totalOpen === 1 ? 'issue' : 'issues'} to work through.</>
        )}
        <span className="text-zinc-500"> {totalOpen} total open.</span>
      </p>
    </div>
  )
}

function PostureCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <p className={LABEL}>{label}</p>
      {children}
    </div>
  )
}

function SevLine({ dot, n, word, active }: { dot: string; n: number; word: string; active: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs ${active ? 'text-zinc-200' : 'text-zinc-600'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${active ? dot : 'bg-zinc-700'}`} />
      <span className="font-mono tabular-nums font-semibold">{n}</span>
      <span>{word}</span>
    </div>
  )
}

function ExposureFigure({ posture: p, issues }: { posture: ComplianceRiskSummary['posture']; issues: RiskIssue[] }) {
  const has = p.exposure_max_usd > 0
  // The single most-cited enforcing authority behind the exposure — the
  // signature detail that reads as a legal instrument, not a to-do list.
  const authority = useMemo(() => {
    const withPenalty = issues.find((i) => i.penalty && (i.penalty.civil_min || i.penalty.civil_max))
    return withPenalty?.penalty?.enforcing_agency || withPenalty?.statute_citation || null
  }, [issues])

  if (!has) {
    return (
      <>
        <p className="font-mono text-lg font-medium text-zinc-400 mt-0.5">No quantified exposure</p>
        {p.exposure_unquantified_count > 0 && (
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {p.exposure_unquantified_count} issue{p.exposure_unquantified_count === 1 ? '' : 's'} carry penalties the statute doesn't quantify
          </p>
        )}
      </>
    )
  }
  return (
    <>
      <p className="font-mono text-2xl font-semibold tabular-nums text-zinc-100 mt-0.5 leading-none">
        {money(p.exposure_min_usd)}<span className="text-zinc-600"> – </span>{money(p.exposure_max_usd)}
      </p>
      {p.exposure_unquantified_count > 0 && (
        <p className="text-[11px] text-zinc-500 mt-1">+ {p.exposure_unquantified_count} unquantified</p>
      )}
      {authority && <p className="text-[11px] font-mono text-zinc-500 mt-0.5 line-clamp-2">{authority}</p>}
    </>
  )
}

function EmployeesAffected({ posture: p, issues }: { posture: ComplianceRiskSummary['posture']; issues: RiskIssue[] }) {
  const names = useMemo(() => {
    const s = new Set<string>()
    issues.forEach((i) => i.employee_names.forEach((n) => s.add(n)))
    return [...s]
  }, [issues])
  return (
    <>
      <p className="font-mono text-2xl font-semibold tabular-nums text-zinc-100 mt-0.5" title={names.join(', ')}>
        {p.employees_affected}
      </p>
      {names.length > 0 && (
        <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{names.slice(0, 3).join(', ')}{names.length > 3 ? ` +${names.length - 3}` : ''}</p>
      )}
    </>
  )
}

// ── Issue row ──
function IssueRow({
  issue, onFix, onOpenAlerts, onUpdateActionPlan, onActioned,
}: {
  issue: RiskIssue
  onFix: () => void
  onOpenAlerts: () => void
  onUpdateActionPlan: (alertId: string, plan: ComplianceActionPlanUpdate) => Promise<void>
  onActioned: () => void
}) {
  const sev = SEV[issue.severity]
  const [assignOpen, setAssignOpen] = useState(false)
  const isAlert = issue.source === 'alert'
  const pen = issue.penalty

  const penaltyLine = pen && (pen.civil_min || pen.civil_max)
    ? `${pen.civil_min ? money(pen.civil_min) : '?'}–${pen.civil_max ? money(pen.civil_max) : '?'}${pen.per_violation ? '/violation' : ''}${pen.enforcing_agency ? ` · ${pen.enforcing_agency}` : ''}`
    : null

  return (
    <div className={`${PANEL} border-l-2 ${sev.rail} px-3.5 py-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-mono uppercase tracking-wide ${sev.chip}`}>{SOURCE_LABEL[issue.source]}</span>
            <span className={`text-[10px] uppercase tracking-wide ${sev.text}`}>{issue.severity}</span>
          </div>
          <p className="text-sm text-zinc-100 mt-1">{issue.title}</p>
          {issue.detail && <p className="text-xs text-zinc-400 mt-0.5">{issue.detail}</p>}
          {penaltyLine && (
            <p className="text-[11px] font-mono text-zinc-500 mt-1">{penaltyLine}</p>
          )}
          {issue.recommendation && (
            <p className="text-xs text-emerald-300/80 mt-1.5">→ {issue.recommendation}</p>
          )}
        </div>
        <div className="shrink-0">
          {isAlert ? (
            <button type="button" onClick={() => setAssignOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-2 py-1 text-xs text-zinc-300 hover:border-white/20 transition-colors">
              <UserPlus className="h-3 w-3" /> {FIX_VERB.alert}
            </button>
          ) : (
            <button type="button" onClick={onFix}
              className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/20 transition-colors">
              {FIX_VERB[issue.source]} <ArrowRight className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {isAlert && assignOpen && issue.alert_id && (
        <AssignPanel
          alertId={issue.alert_id}
          onViewAlert={onOpenAlerts}
          onSubmit={async (plan) => {
            await onUpdateActionPlan(issue.alert_id!, plan)
            setAssignOpen(false)
            onActioned()
          }}
        />
      )}
    </div>
  )
}

function AssignPanel({
  alertId, onSubmit, onViewAlert,
}: {
  alertId: string
  onSubmit: (plan: ComplianceActionPlanUpdate) => Promise<void>
  onViewAlert: () => void
}) {
  const [users, setUsers] = useState<AssignableUser[]>([])
  const [owner, setOwner] = useState('')
  const [next, setNext] = useState('')
  const [due, setDue] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { fetchAssignableUsers().then(setUsers).catch(() => setUsers([])) }, [alertId])

  async function submit(markActioned: boolean) {
    setSaving(true)
    try {
      await onSubmit({
        action_owner_id: owner || undefined,
        next_action: next || undefined,
        action_due_date: due || undefined,
        mark_actioned: markActioned,
      })
    } finally { setSaving(false) }
  }

  return (
    <div className="mt-3 rounded-md border border-white/[0.06] bg-zinc-900/50 p-3 space-y-2">
      <div className="grid gap-2 sm:grid-cols-2">
        <select value={owner} onChange={(e) => setOwner(e.target.value)}
          className="rounded-md border border-white/[0.08] bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200">
          <option value="">Assign owner…</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name || u.email}</option>)}
        </select>
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)}
          className="rounded-md border border-white/[0.08] bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200" />
      </div>
      <input type="text" value={next} onChange={(e) => setNext(e.target.value)}
        placeholder="Next action (e.g. update posting, notify affected staff)"
        className="w-full rounded-md border border-white/[0.08] bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200" />
      <div className="flex items-center justify-between">
        <button type="button" onClick={onViewAlert}
          className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
          View full alert <ChevronRight className="h-3 w-3" />
        </button>
        <div className="flex gap-1.5">
          <button type="button" disabled={saving} onClick={() => submit(false)}
            className="rounded-md border border-white/[0.08] px-2 py-1 text-xs text-zinc-300 hover:border-white/20 transition-colors disabled:opacity-50">
            Save plan
          </button>
          <button type="button" disabled={saving} onClick={() => submit(true)}
            className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-50">
            <CheckCircle2 className="h-3 w-3" /> Mark actioned
          </button>
        </div>
      </div>
    </div>
  )
}

function GetAheadRow({ title, days, kind, loc }: { title: string; days: number | null; kind: string; loc?: string | null }) {
  const urgent = days != null && days <= 30
  const lead = days == null ? 0 : Math.max(0, Math.min(100, 100 - (days / 180) * 100))
  return (
    <div className="px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-zinc-200 line-clamp-2">{title}</p>
          <span className="text-[10px] text-zinc-600 uppercase tracking-wide">
            {kind === 'legislation' ? 'New law' : 'Deadline'}{loc ? ` · ${loc}` : ''}
          </span>
        </div>
        <span className={`shrink-0 font-mono text-sm font-semibold tabular-nums ${urgent ? 'text-amber-400' : 'text-zinc-400'}`}>
          {days != null ? `${days}d` : '—'}
        </span>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-white/[0.05] overflow-hidden">
        <div className={`h-full ${urgent ? 'bg-amber-500/70' : 'bg-zinc-600'}`} style={{ width: `${lead}%` }} />
      </div>
    </div>
  )
}
