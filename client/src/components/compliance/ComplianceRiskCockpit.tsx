import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowRight, CheckCircle2, ChevronRight, Clock,
  History, Info, Loader2, RotateCcw, ShieldCheck, UserPlus, X,
} from 'lucide-react'
import { LABEL } from '../ui/typography'
import { HelpHint } from '../ui/HelpHint'
import {
  dismissRemediation, fetchAssignableUsers, reopenRemediation,
} from '../../api/compliance'
import type {
  AssignableUser, ComplianceActionPlanUpdate, ComplianceRiskSummary,
  PinnedRequirement, RemediationRecord, RiskIssue,
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
  requirement: 'Requirement',
}

const FIX_VERB: Record<RiskIssue['source'], string> = {
  wage: 'Fix pay', credential: 'Renew', incident: 'Open incident', alert: 'Assign owner',
  requirement: 'Review',
}

// Plain-language help for the manager, matched to what each element controls.
const HELP = {
  openIssues: 'Everything currently out of compliance, split by urgency. Critical is a live legal violation (e.g. paid below minimum wage); high/moderate are things to get ahead of, like a license expiring soon.',
  exposure: 'A rough dollar range of the statutory penalties tied to your open violations, summed from the enforcing agencies’ published fines. It’s an estimate to size the risk, not a bill — some laws don’t name a figure (shown as "unquantified").',
  affected: 'How many of your employees are named in an open issue right now (underpaid, expired license, etc.). Hover the number to see who.',
  nextDeadline: 'The soonest thing with a due date — a license expiry, an alert deadline, or a new law taking effect. Fix these before they become violations.',
  actionQueue: 'Your to-do list, worst first. Click Fix to jump straight to the exact record (the underpaid employee, the incident) and correct it. When you do, the issue clears itself and is logged in Remediation history.',
  fix: 'Opens the exact record where you fix this — the employee’s pay, their license, or the incident. Once the data is corrected the issue leaves this list automatically.',
  dismiss: 'Use only if this isn’t a real violation (e.g. the employee is correctly classified as exempt). You must give a reason; it’s recorded. It comes back on its own if the underlying numbers change.',
  getAhead: 'Things coming up — new laws and deadlines — so you can act before they turn into violations.',
  history: 'The documented record of every issue you’ve resolved or dismissed: what it was, when, how, and who. This is your paper trail if a claim or audit ever asks "what did you do about it?"',
} as const

function money(v: number) {
  return `$${Math.round(v).toLocaleString()}`
}

function ageLabel(iso?: string | null): string | null {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days <= 0) return 'flagged today'
  return `open ${days} day${days === 1 ? '' : 's'}`
}

function humanize(s?: string | null): string {
  if (!s) return ''
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
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

  const { posture: p, issues, get_ahead, recently_resolved, dismissed_count } = riskSummary
  const totalOpen = p.open_critical + p.open_high + p.open_moderate
  const clear = totalOpen === 0

  return (
    <div className="space-y-4">
      <GuideBanner />
      <VerdictBanner critical={p.open_critical} totalOpen={totalOpen} clear={clear} />

      {/* Posture strip — one panel, four cells, hairline dividers. */}
      <div className={`${PANEL} grid grid-cols-2 divide-x divide-y divide-white/[0.06] md:grid-cols-4 md:divide-y-0`}>
        <PostureCell label="Open issues" hint={HELP.openIssues}>
          <div className="flex flex-col gap-1 mt-0.5">
            <SevLine dot={SEV.critical.dot} n={p.open_critical} word="critical" active={p.open_critical > 0} />
            <SevLine dot={SEV.high.dot} n={p.open_high} word="high" active={p.open_high > 0} />
            <SevLine dot={SEV.moderate.dot} n={p.open_moderate} word="moderate" active={p.open_moderate > 0} />
          </div>
        </PostureCell>

        {/* Signature cell: the measured dollar figure + the authority behind it. */}
        <PostureCell label="Est. penalty exposure" hint={HELP.exposure}>
          <ExposureFigure posture={p} issues={issues} />
        </PostureCell>

        <PostureCell label="Employees affected" hint={HELP.affected}>
          <EmployeesAffected posture={p} issues={issues} />
        </PostureCell>

        <PostureCell label="Next deadline" hint={HELP.nextDeadline}>
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
            <h2 className={`${LABEL} flex items-center gap-1`}>Action queue<HelpHint text={HELP.actionQueue} /></h2>
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
          <h2 className={`${LABEL} flex items-center gap-1`}>Get ahead<HelpHint text={HELP.getAhead} /></h2>
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

      <RemediationTrail
        records={recently_resolved}
        dismissedCount={dismissed_count}
        onChanged={onActioned}
      />
    </div>
  )
}

// ── Remediation trail — the documentation record (resolved + dismissed) ──
function RemediationTrail({
  records, dismissedCount, onChanged,
}: { records: RemediationRecord[]; dismissedCount: number; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  if (records.length === 0 && dismissedCount === 0) return null

  const resolved = records.filter((r) => r.status === 'resolved')
  const dismissed = records.filter((r) => r.status === 'dismissed')

  return (
    <div className="pt-1">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
        <History className="h-3.5 w-3.5" />
        <span className={`${LABEL} flex items-center gap-1`}>Remediation history<HelpHint text={HELP.history} /></span>
        <span className="text-[11px] text-zinc-600">
          {resolved.length} resolved{dismissedCount > 0 ? ` · ${dismissedCount} dismissed` : ''}
        </span>
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className={`${PANEL} mt-2 divide-y divide-white/[0.06]`}>
          {records.length === 0 && (
            <p className="px-4 py-3 text-xs text-zinc-600">No resolutions recorded yet.</p>
          )}
          {[...resolved, ...dismissed].map((r) => (
            <div key={r.issue_key} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {r.status === 'resolved'
                    ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    : <X className="h-3.5 w-3.5 text-zinc-500 shrink-0" />}
                  <p className="text-sm text-zinc-200 truncate">{r.title}</p>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {humanize(r.source)} · {r.status === 'resolved' ? 'Resolved' : 'Dismissed'}
                  {r.resolution_method ? ` via ${humanize(r.resolution_method)}` : ''}
                  {r.resolved_at ? ` · ${new Date(r.resolved_at).toLocaleDateString()}` : ''}
                  {r.resolved_by_name ? ` · ${r.resolved_by_name}` : ''}
                </p>
                {r.resolution_note && (
                  <p className="text-[11px] text-zinc-400 mt-0.5">{r.resolution_note}</p>
                )}
              </div>
              {r.status === 'dismissed' && (
                <button type="button"
                  onClick={async () => { await reopenRemediation(r.issue_key); onChanged() }}
                  className="shrink-0 inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                  <RotateCcw className="h-3 w-3" /> Reopen
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── One-time "how this works" guide (collapses to a reopenable link) ──
const GUIDE_KEY = 'compliance_cockpit_guide_dismissed'

function GuideBanner() {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(GUIDE_KEY) !== '1' } catch { return true }
  })
  function close() {
    setOpen(false)
    try { localStorage.setItem(GUIDE_KEY, '1') } catch { /* ignore */ }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
        <Info className="h-3.5 w-3.5" /> How this page works
      </button>
    )
  }
  return (
    <div className="rounded-lg border border-white/[0.08] bg-zinc-900/40 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <Info className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs text-zinc-300 space-y-1.5">
            <p className="text-zinc-100 font-medium">Your compliance risk at a glance — and how to clear it.</p>
            <ul className="space-y-1 text-zinc-400">
              <li>• The <b className="text-zinc-200">strip</b> up top measures where you stand: open issues by urgency, the estimated penalty exposure, who's affected, and your next deadline. Hover any <span className="text-zinc-300">(?)</span> for detail.</li>
              <li>• The <b className="text-zinc-200">Action queue</b> is your to-do list, worst first. Hit <span className="text-emerald-300">Fix</span> to jump to the exact record and correct it — the issue then clears itself.</li>
              <li>• Every fix is written to <b className="text-zinc-200">Remediation history</b> automatically (who, when, how) — your paper trail for audits and claims.</li>
              <li>• Not a real violation? <span className="text-zinc-300">Dismiss</span> it with a reason. It comes back on its own if the numbers change.</li>
            </ul>
          </div>
        </div>
        <button type="button" onClick={close} aria-label="Dismiss guide"
          className="shrink-0 text-zinc-500 hover:text-zinc-200 transition-colors">
          <X className="h-4 w-4" />
        </button>
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

function PostureCell({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="px-4 py-3">
      <p className={`${LABEL} flex items-center gap-1`}>
        {label}{hint && <HelpHint text={hint} />}
      </p>
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
  // The authority behind the most DOLLARS — the signature detail that reads as a
  // legal instrument, not a to-do list.
  //
  // This used to take the first issue carrying any penalty, which is not the
  // same thing and read as a lie the moment the figures were grounded: a $500
  // wage issue sorted ahead of a $16,550 OSHA one, so the tile totalled $17,050
  // and captioned it "City of Los Angeles Office of Wage Standards" — naming the
  // authority behind 3% of it. Sum by authority and take the largest.
  const authority = useMemo(() => {
    const byAuthority = new Map<string, number>()
    for (const i of issues) {
      const name = i.penalty?.enforcing_agency || i.statute_citation
      const usd = i.penalty?.civil_max ?? i.penalty?.civil_min
      if (!name || usd == null) continue
      const n = i.penalty?.per_violation && i.violation_count ? Math.max(1, i.violation_count) : 1
      byAuthority.set(name, (byAuthority.get(name) ?? 0) + usd * n)
    }
    let top: string | null = null
    let best = -1
    // Ties break on name so the caption doesn't flicker between equal authorities.
    for (const [name, usd] of [...byAuthority].sort((a, b) => a[0].localeCompare(b[0]))) {
      if (usd > best) { best = usd; top = name }
    }
    return top
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
  const [dismissOpen, setDismissOpen] = useState(false)
  const isAlert = issue.source === 'alert'
  const pen = issue.penalty

  const penaltyLine = pen && (pen.civil_min != null || pen.civil_max != null)
    ? `${pen.civil_min != null ? money(pen.civil_min) : '?'}–${pen.civil_max != null ? money(pen.civil_max) : '?'}${pen.per_violation ? '/violation' : ''}${pen.enforcing_agency ? ` · ${pen.enforcing_agency}` : ''}`
    : null

  return (
    <div className={`${PANEL} border-l-2 ${sev.rail} px-3.5 py-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-mono uppercase tracking-wide ${sev.chip}`}>{SOURCE_LABEL[issue.source]}</span>
            <span className={`text-[10px] uppercase tracking-wide ${sev.text}`}>{issue.severity}</span>
            {ageLabel(issue.first_seen_at) && (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-zinc-600">
                <Clock className="h-2.5 w-2.5" /> {ageLabel(issue.first_seen_at)}
              </span>
            )}
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
        <div className="shrink-0 flex items-center gap-1.5">
          {isAlert ? (
            <button type="button" onClick={() => setAssignOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-2 py-1 text-xs text-zinc-300 hover:border-white/20 transition-colors">
              <UserPlus className="h-3 w-3" /> {FIX_VERB.alert}
            </button>
          ) : (
            <>
              <button type="button" onClick={onFix} title={HELP.fix}
                className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/20 transition-colors">
                {FIX_VERB[issue.source]} <ArrowRight className="h-3 w-3" />
              </button>
              <button type="button" title="Not a violation — dismiss with a reason"
                onClick={() => setDismissOpen((v) => !v)}
                className="inline-flex items-center rounded-md border border-white/[0.08] px-1.5 py-1 text-xs text-zinc-500 hover:text-zinc-300 hover:border-white/20 transition-colors">
                <X className="h-3 w-3" />
              </button>
            </>
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

      {!isAlert && dismissOpen && (
        <DismissPanel
          onCancel={() => setDismissOpen(false)}
          onSubmit={async (reason) => {
            await dismissRemediation(issue.id, reason)
            setDismissOpen(false)
            onActioned()
          }}
        />
      )}
    </div>
  )
}

function DismissPanel({ onSubmit, onCancel }: { onSubmit: (reason: string) => Promise<void>; onCancel: () => void }) {
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  return (
    <div className="mt-3 rounded-md border border-white/[0.06] bg-zinc-900/50 p-3 space-y-2">
      <p className="text-[11px] text-zinc-500">
        Dismiss only if this isn't a real violation (e.g. properly classified exempt). It re-surfaces if the underlying data changes. Recorded for the trail.
      </p>
      <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus
        placeholder="Reason (e.g. passes the duties test — exempt)"
        className="w-full rounded-md border border-white/[0.08] bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200" />
      <div className="flex justify-end gap-1.5">
        <button type="button" onClick={onCancel}
          className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Cancel</button>
        <button type="button" disabled={saving || !reason.trim()}
          onClick={async () => { setSaving(true); try { await onSubmit(reason.trim()) } finally { setSaving(false) } }}
          className="rounded-md border border-white/[0.08] px-2 py-1 text-xs text-zinc-300 hover:border-white/20 transition-colors disabled:opacity-40">
          Dismiss issue
        </button>
      </div>
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
