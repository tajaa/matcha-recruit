import { useEffect, useState } from 'react'
import {
  ArrowRight, CheckCircle2, ChevronRight, Clock, ExternalLink, UserPlus, X,
} from 'lucide-react'
import {
  dismissRemediation, fetchAssignableUsers,
} from '../../../api/compliance/compliance'
import type {
  AssignableUser, ComplianceActionPlanUpdate, RiskIssue,
} from '../../../types/compliance'
import { PANEL, SEV, SOURCE_LABEL, FIX_VERB, HELP } from './constants'
import { money, ageLabel } from './helpers'

// ── Issue row ──
export function IssueRow({
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

  // A single figure is shown once, not as "$16,550–$16,550": most statutes set a
  // ceiling ("shall not exceed $X") with no floor, so min borrows max upstream.
  const hasFigure = pen && (pen.civil_min != null || pen.civil_max != null)
  const figure = hasFigure
    ? `${pen.civil_min != null && pen.civil_max != null && pen.civil_min !== pen.civil_max
        ? `${money(pen.civil_min)}–${money(pen.civil_max)}`
        : money((pen.civil_max ?? pen.civil_min) as number)}${pen.per_violation ? '/violation' : ''}`
    : null
  // The FIGURE is the claim, so the figure is what you click to check it — not a
  // citation parked next to it. A grounded number was parsed out of the statute
  // at `source_url`, so following it lands on the sentence it came from.
  const proofHref = pen?.grounded && pen.source_url ? pen.source_url : null

  return (
    <div className={`${PANEL} border-l-2 ${sev.rail} px-3.5 py-3`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {/* Three chips rode every row — CREDENTIALING · CRITICAL · flagged
              today — on a row whose left rail is already coloured by severity
              and inside a queue that is sorted by it. The severity word was
              saying a third time what the rail says once, so the rail keeps
              the job and the chips are down to what actually varies. */}
          <div className="flex items-center gap-2">
            <span className={`font-mono text-[10px] uppercase tracking-wide ${sev.chip}`}>{SOURCE_LABEL[issue.source]}</span>
            {ageLabel(issue.first_seen_at) && (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-zinc-600">
                <Clock className="h-2.5 w-2.5" /> {ageLabel(issue.first_seen_at)}
              </span>
            )}
          </div>
          <p className="text-sm text-zinc-100 mt-1">{issue.title}</p>
          {issue.detail && <p className="text-xs text-zinc-400 mt-0.5">{issue.detail}</p>}
          {figure && (
            <p className="text-[11px] font-mono text-zinc-500 mt-1">
              {proofHref ? (
                <a
                  href={proofHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-zinc-300 underline decoration-dotted decoration-zinc-600 underline-offset-2 hover:text-zinc-100 hover:decoration-zinc-400"
                  title={
                    `${pen?.citation ?? 'Statute'}` +
                    `${pen?.effective_date ? ` — effective ${pen.effective_date}` : ''}` +
                    ' · opens the eCFR section this figure was read from'
                  }
                >
                  {figure}
                  <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                </a>
              ) : (
                figure
              )}
              {pen?.enforcing_agency && <span className="text-zinc-600"> · {pen.enforcing_agency}</span>}
              {/* The citation rides along as the human-readable proof, but the
                  figure is the thing you click — it is the claim being made.
                  Shown only when grounded: an ungrounded number is model recall
                  and must not borrow the authority of a citation it doesn't
                  have. */}
              {pen?.grounded && pen.citation && (
                <span className="text-zinc-600">
                  {' · '}{pen.citation}
                  {pen.effective_date && ` eff. ${pen.effective_date}`}
                </span>
              )}
            </p>
          )}
          {/* The recommendation is gone from the row. On a credentialing issue
              it read "Renew Maria Reyes's Medical License immediately — it
              lapsed and must be restored before their next shift", under a
              title reading "Maria Reyes — Medical License expired", beside a
              button reading "Renew" — the fourth telling of one fact, and the
              only one costing two wrapped lines on every row in the queue. It
              still reaches the user: it's the Renew button's tooltip, which is
              where an instruction belongs once the control itself names the
              action. */}
        </div>
        <div className="shrink-0 flex items-center gap-1.5">
          {isAlert ? (
            <button type="button" onClick={() => setAssignOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-2 py-1 text-xs text-zinc-300 hover:border-white/20 transition-colors">
              <UserPlus className="h-3 w-3" /> {FIX_VERB.alert}
            </button>
          ) : (
            <>
              <button type="button" onClick={onFix} title={issue.recommendation || HELP.fix}
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
