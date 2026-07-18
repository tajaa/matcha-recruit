import { useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'
import { LABEL } from '../ui/typography'
import { HelpHint } from '../ui/HelpHint'
import type {
  ComplianceActionPlanUpdate, ComplianceRiskSummary, PinnedRequirement,
} from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'
import { PANEL, SEV, HELP } from './ComplianceRiskCockpit/constants'
import { GuideBanner } from './ComplianceRiskCockpit/GuideBanner'
import { VerdictBanner } from './ComplianceRiskCockpit/VerdictBanner'
import {
  PostureCell, SevLine, ExposureFigure, EmployeesAffected,
} from './ComplianceRiskCockpit/PostureStrip'
import { IssueRow } from './ComplianceRiskCockpit/IssueRow'
import { GetAheadRow } from './ComplianceRiskCockpit/GetAheadRow'
import { RemediationTrail } from './ComplianceRiskCockpit/RemediationTrail'

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
      {/* Collapsed, this is a single "How this page works" link; the manual is
          behind it rather than in front of the queue. */}
      <GuideBanner />

      {/* The alarm banner only earns its place when there's nothing to alarm
          about. With issues open it restated the strip directly beneath it —
          "6 critical … 17 total open" above a cell reading 6 critical / 6 high
          / 5 moderate — and the queue below already ranks them worst-first. An
          empty strip, on the other hand, can't tell "clear" from "not loaded",
          so the clear verdict is the one that says something. */}
      {clear && <VerdictBanner critical={p.open_critical} totalOpen={totalOpen} clear />}

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
