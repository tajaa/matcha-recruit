import { useState } from 'react'
import {
  BookCheck, CheckCircle2, FileSearch, GitCompareArrows, ListChecks, Loader2, PenLine, RefreshCw, Sparkles,
} from 'lucide-react'
import { api } from '../../../api/client'
import { Button } from '../../../components/ui'
import { LABEL } from '../../../components/ui/typography'
import type { GotoParams, StudioView, UncodifiedItem, Worklist, WorklistAction } from './types'

const ACTION_META: Record<WorklistAction['kind'], { icon: typeof ListChecks; verb: string; why: string }> = {
  review_staged: {
    icon: FileSearch, verb: 'Review staged research',
    why: 'Research is done and waiting — review, then approve to publish it and try to codify it.',
  },
  codify_uncodified: {
    icon: PenLine, verb: 'Codify live requirements',
    // Pre-gate this read "live and serving tenants". Since the codified gate,
    // the opposite is true: these rows are in tenants' projections and WITHHELD
    // from their tabs until cited. Saying "serving" hid that a paying customer
    // is waiting on this queue.
    why: 'These are live in tenant projections but withheld from their tabs until cited — a tenant is waiting on every blocked row. Codifying is what releases them.',
  },
  research_coverage: {
    icon: Sparkles, verb: 'Research tenant gaps',
    why: 'A company onboarded and triggered a coverage gap — research it to keep them covered.',
  },
  confirm_authority: {
    icon: BookCheck, verb: 'Confirm classifications',
    why: 'Gemini proposed how these authority sections apply — confirm them so they can codify future requirements automatically.',
  },
  ack_drift: {
    icon: GitCompareArrows, verb: 'Review authority drift',
    why: 'A source law changed since the last ingest — review what changed and acknowledge it.',
  },
  research_baseline: {
    icon: ListChecks, verb: 'Research baseline jurisdictions',
    why: "These jurisdictions have onboarded locations but no requirements researched yet — that's the exhaustiveness backlog.",
  },
}

function summarizeAction(a: WorklistAction): string {
  switch (a.kind) {
    case 'review_staged':
      return `${a.count} requirement${a.count === 1 ? '' : 's'} across ${a.groups.length} jurisdiction${a.groups.length === 1 ? '' : 's'}`
    case 'codify_uncodified': {
      // Lead with the tenant-blocking count when there is one: "88 need a
      // citation" is a chore, "614 blocking live tenants" is a customer waiting.
      const parts: string[] = []
      if (a.tenant_blocked > 0) parts.push(`${a.tenant_blocked} blocking live tenants`)
      parts.push(`${a.count} need a citation by hand`)
      if (a.auto_reconcilable > 0) {
        parts.push(
          a.tenant_blocked_auto > 0
            ? `${a.auto_reconcilable} fixable with one reconcile (${a.tenant_blocked_auto} blocking)`
            : `${a.auto_reconcilable} fixable with one reconcile`,
        )
      }
      return parts.join(' · ')
    }
    case 'research_coverage':
      return `${a.count} categor${a.count === 1 ? 'y' : 'ies'} requested by onboarded tenants`
    case 'confirm_authority':
      return `${a.by_index.length} authority ${a.by_index.length === 1 ? 'index' : 'indexes'} with unconfirmed sections`
    case 'ack_drift':
      return `${a.count} citation${a.count === 1 ? '' : 's'} changed at the source`
    case 'research_baseline':
      return `${a.count} jurisdiction${a.count === 1 ? '' : 's'} with onboarded locations, no data yet`
  }
}

// The home screen — "what needs me now," merging both funnels into one
// prioritized list instead of making the admin hunt across tabs. Each card
// routes straight into the focused step for that action.
export default function CommandCenter({
  worklist, loading, onRefresh, goto, gotoUncodified,
}: {
  worklist: Worklist | null
  loading: boolean
  onRefresh: () => void
  goto: (view: StudioView, params?: GotoParams & { section?: string }) => void
  gotoUncodified: (items: UncodifiedItem[]) => void
}) {
  const [reconciling, setReconciling] = useState(false)

  async function runReconcile() {
    setReconciling(true)
    try {
      await api.post('/admin/scope-registry/reconcile', {})
      onRefresh()
    } finally {
      setReconciling(false)
    }
  }

  function openAction(a: WorklistAction) {
    switch (a.kind) {
      case 'review_staged':
        goto('pipeline', { section: 'review' }); break
      case 'codify_uncodified':
        if (a.items.length > 0) gotoUncodified(a.items)
        else goto('pipeline', { section: 'review' })
        break
      case 'research_coverage':
        goto('pipeline', { section: 'queue' }); break
      case 'confirm_authority':
        goto('authority'); break
      case 'ack_drift':
        goto('authority'); break
      case 'research_baseline':
        goto('library'); break
    }
  }

  const actions = worklist?.actions ?? []

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className={LABEL}>What needs you now</div>
          <p className="mt-0.5 text-sm text-zinc-500">
            Merged across both funnels, most-authoritative-first.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {loading && !worklist ? (
        <div className="flex items-center gap-2 py-12 justify-center text-sm text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading the worklist…
        </div>
      ) : actions.length === 0 ? (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] px-6 py-12 text-center">
          <CheckCircle2 className="mx-auto h-6 w-6 text-emerald-400" />
          <p className="mt-3 text-sm text-emerald-200">
            Library is as complete and authoritative as current signals show — nothing needs you.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {[...actions].sort((a, b) => a.priority - b.priority).map((a) => {
            const meta = ACTION_META[a.kind]
            const Icon = meta.icon
            return (
              <div key={a.kind}
                className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3.5 hover:border-white/[0.12] transition-colors">
                <div className="mt-0.5 rounded-lg border border-white/[0.08] bg-white/[0.03] p-2">
                  <Icon className="h-4 w-4 text-emerald-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-zinc-100">{meta.verb}</h3>
                    <span className="rounded-full bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                      {a.count}
                    </span>
                    {a.kind === 'codify_uncodified' && a.tenant_blocked > 0 && (
                      // The one number that means a paying customer is waiting.
                      // Amber, next to the verb, so it lands without opening the card.
                      <span
                        className="rounded-full border border-amber-800/40 bg-amber-900/20 px-1.5 py-0.5 font-mono text-[10px] text-amber-400"
                        title="Uncodified rows a live tenant already has projected — withheld from their tab until cited">
                        {a.tenant_blocked} tenant-blocking
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500">{summarizeAction(a)}</p>
                  <p className="mt-1 text-[11px] text-zinc-600">{meta.why}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  {a.kind === 'codify_uncodified' && a.auto_reconcilable > 0 && (
                    <button type="button" onClick={runReconcile} disabled={reconciling}
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 disabled:opacity-50">
                      {reconciling ? 'Reconciling…' : `Run reconcile (${a.auto_reconcilable})`}
                    </button>
                  )}
                  <Button variant="secondary" size="sm" onClick={() => openAction(a)}>Open</Button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
