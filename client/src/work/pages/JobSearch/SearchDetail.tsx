import RecapLink from '../../components/recaps/RecapLink'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, ArrowLeft, FileCheck2, ListFilter, Loader2, SlidersHorizontal, Trash2, X } from 'lucide-react'
import type { JobLeadSummary, JobSearchDetail, JobWeights } from '../../api/matchaWork/jobSearch'
import {
  DEFAULT_WEIGHTS, FILTERS, GMAIL_DRAFTS_URL, PHASES, anyWeightAboveZero, compBadge, displayTitle, filterLeads, fitText,
  isDrafting, isLive, leadStatusText, phaseIndex, progressLine, searchProgress, showsRemoteBadge, statusLabel,
  emailWaiting, widerCount, type JobFilter,
} from './jobSearchLogic'
import WeightSliders from './WeightSliders'

const STEPS_COLLAPSED_KEY = 'espresso-jobs-next-steps-collapsed'

function readCollapsed(): boolean {
  try { return localStorage.getItem(STEPS_COLLAPSED_KEY) === '1' } catch { return false }
}

/**
 * One job search: what it's doing, what to do next, and its ranked jobs. The
 * open job shows beside it (`LeadPane`). Mirrors the macOS app's job search view.
 */
export default function SearchDetail({
  detail, busy, error, onDismissError, selectedLeadId, onSelectLead, onRerank, onWiden, onCancel, onDelete, onBack,
}: {
  detail: JobSearchDetail
  busy: boolean
  error: string | null
  onDismissError: () => void
  selectedLeadId: string | null
  onSelectLead: (id: string) => void
  onRerank: (weights: JobWeights) => void
  onWiden: () => void
  onCancel: () => void
  onDelete: () => void
  /** Small screens: back to the list of searches. */
  onBack: () => void
}) {
  const [filter, setFilter] = useState<JobFilter>('All')
  const [showWeaker, setShowWeaker] = useState(false)
  const [stepsCollapsed, setStepsCollapsed] = useState(readCollapsed)
  const [weightsOpen, setWeightsOpen] = useState(false)
  const live = isLive(detail.status)
  const visible = filterLeads(detail.leads, filter, showWeaker)
  const wider = widerCount(detail)
  const note = detail.progress?.note

  function toggleSteps() {
    const next = !stepsCollapsed
    setStepsCollapsed(next)
    try { localStorage.setItem(STEPS_COLLAPSED_KEY, next ? '1' : '0') } catch { /* best effort */ }
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className="space-y-2 border-b border-w-line px-5 py-4">
        <RecapLink sourceId={detail.id} />
        <div className="flex items-start gap-2">
          <button type="button" onClick={onBack} aria-label="All searches" className="-ml-1 rounded-md p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text md:hidden">
            <ArrowLeft size={16} />
          </button>
          <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-w-text">{displayTitle(detail)}</h1>
          <div className="relative">
            <button
              type="button"
              onClick={() => setWeightsOpen((v) => !v)}
              disabled={live || busy}
              aria-expanded={weightsOpen}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-w-dim hover:bg-w-surface2 hover:text-w-text disabled:opacity-40"
            >
              <SlidersHorizontal size={13} /> What matters
            </button>
            {weightsOpen && (
              <WeightsPopover
                initial={detail.weights ?? DEFAULT_WEIGHTS}
                onClose={() => setWeightsOpen(false)}
                onApply={(w) => { setWeightsOpen(false); onRerank(w) }}
              />
            )}
          </div>
          {live ? (
            <button type="button" onClick={onCancel} disabled={busy} className="rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40">
              Cancel
            </button>
          ) : (
            <button type="button" onClick={onDelete} disabled={busy} aria-label="Delete this search" title="Delete this search" className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-red-400 disabled:opacity-40">
              <Trash2 size={14} />
            </button>
          )}
        </div>
        {detail.ask && detail.ask !== displayTitle(detail) && (
          <p className="line-clamp-2 text-[11px] text-w-dim">{detail.ask}</p>
        )}
        <PhaseStepper status={detail.status} />
        {note && (
          <p className={`flex items-center gap-1.5 text-[11px] ${detail.status === 'failed' ? 'text-amber-500' : 'text-w-dim'}`}>
            {live && <Loader2 size={11} className="animate-spin" />}
            {note}
          </p>
        )}
      </header>

      {error && (
        <div role="alert" className="flex items-center gap-2 bg-amber-500/10 px-5 py-1.5 text-[11px] text-amber-500">
          <AlertTriangle size={12} className="shrink-0" />
          <span className="line-clamp-2 flex-1">{error}</span>
          <button type="button" onClick={onDismissError} aria-label="Dismiss" className="rounded p-0.5 hover:bg-amber-500/10"><X size={11} /></button>
        </div>
      )}

      {!live && detail.leads.length > 0 && (
        <NextSteps
          detail={detail}
          collapsed={stepsCollapsed}
          onToggle={toggleSteps}
          showDrafted={filter !== 'Drafted' ? () => setFilter('Drafted') : null}
        />
      )}

      {wider > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-w-line px-5 py-2">
          <ListFilter size={14} className="shrink-0 text-w-dim" />
          <p className="min-w-0 flex-1 text-xs text-w-text">
            Showing your strongest matches (4/5 or better). {wider === 1 ? '1 more job scored 3/5.' : `${wider} more jobs scored 3/5.`}
          </p>
          <button type="button" onClick={onWiden} disabled={busy} className="rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40">
            Show {wider} more at 3/5
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-2">
        <div role="tablist" aria-label="Filter jobs" className="flex flex-wrap rounded-md border border-w-line p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={`rounded px-2 py-0.5 text-[11px] ${filter === f ? 'bg-w-surface2 font-semibold text-w-text' : 'text-w-dim hover:text-w-text'}`}
            >
              {f}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-w-text">
          <input type="checkbox" checked={showWeaker} onChange={(e) => setShowWeaker(e.target.checked)} />
          Show weaker matches
        </label>
        <span className="ml-auto text-[10px] text-w-dim">{visible.length} of {detail.leads.length}</span>
      </div>

      <LeadsTable leads={visible} selectedLeadId={selectedLeadId} onSelect={onSelectLead} compact={!!selectedLeadId} live={live} />
    </div>
  )
}

/** What to do with a finished search, in order, and how far along it is. */
function NextSteps({ detail, collapsed, onToggle, showDrafted }: {
  detail: JobSearchDetail
  collapsed: boolean
  onToggle: () => void
  showDrafted: (() => void) | null
}) {
  const progress = searchProgress(detail.leads)
  const line = progressLine(progress)
  return (
    <div className="space-y-2 border-b border-w-line bg-w-accent/5 px-5 py-2.5">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-w-dim">Next steps</p>
        {line && <p className="text-[11px] text-w-accent">{line}</p>}
        <button type="button" onClick={onToggle} className="ml-auto text-[11px] text-w-dim hover:text-w-text">
          {collapsed ? 'Show' : 'Hide'}
        </button>
      </div>
      {!collapsed && (
        <ol className="space-y-1.5">
          <Step n={1} action={progress.drafted > 0 && showDrafted ? { label: 'Show them', run: showDrafted } : null}>
            {progress.drafted > 0
              ? `Read your best matches. ${progress.drafted} have a drafted approach: how to get in, a first message, answers and a cover letter.`
              : 'Read your best matches, and draft an approach for any you like from its page.'}
          </Step>
          <Step n={2} action={progress.emailsWaiting > 0 ? { label: 'Open drafts', href: GMAIL_DRAFTS_URL } : null}>
            Open one you want and click Draft email. It goes to your Gmail drafts, to edit and send from Gmail.
          </Step>
          <Step n={3} action={null}>Apply through the posting, then mark the job Applied so you can keep track.</Step>
        </ol>
      )}
    </div>
  )
}

function Step({ n, action, children }: {
  n: number
  action: { label: string; run?: () => void; href?: string } | null
  children: ReactNode
}) {
  const actionClass = 'shrink-0 rounded-md border border-w-line px-2 py-0.5 text-[11px] text-w-text hover:bg-w-surface2'
  return (
    <li className="flex items-start gap-2">
      <span className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-w-accent text-[10px] font-bold text-white">{n}</span>
      <span className="min-w-0 flex-1 text-xs leading-5 text-w-text">{children}</span>
      {action?.href && <a href={action.href} target="_blank" rel="noopener noreferrer" className={actionClass}>{action.label}</a>}
      {action?.run && <button type="button" onClick={action.run} className={actionClass}>{action.label}</button>}
    </li>
  )
}

/** Plan → Search → Screen → Read pay → Draft approaches → Done. */
function PhaseStepper({ status }: { status: string }) {
  const current = phaseIndex(status)
  const live = isLive(status)
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label={`Status: ${statusLabel(status)}`}>
      {PHASES.map((label, i) => {
        const reached = (current ?? -1) >= i
        const active = current === i && live
        return (
          <span key={label} className="flex items-center gap-1.5">
            <span className="flex items-center gap-1">
              <span className={`h-1.5 w-1.5 rounded-full ${reached ? 'bg-w-accent' : 'bg-w-line'}`} />
              <span className={`text-[10px] ${active ? 'font-semibold' : ''} ${reached ? 'text-w-text' : 'text-w-dim'} ${current === i ? '' : 'hidden sm:inline'}`}>
                {label}
              </span>
            </span>
            {i < PHASES.length - 1 && <span className="h-px w-2 bg-w-line sm:w-3" />}
          </span>
        )
      })}
      {current === null && <span className="text-[10px] font-semibold text-amber-500">{statusLabel(status)}</span>}
    </div>
  )
}

/** Re-rank with new weights. Free: no search is spent. */
function WeightsPopover({ initial, onApply, onClose }: {
  initial: JobWeights
  onApply: (weights: JobWeights) => void
  onClose: () => void
}) {
  const [weights, setWeights] = useState(initial)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return (
    <div ref={ref} role="dialog" aria-label="What matters most" className="absolute right-0 top-full z-30 mt-1 w-80 space-y-2.5 rounded-xl border border-w-line bg-w-surface p-4 shadow-2xl">
      <p className="text-sm font-semibold text-w-text">What matters most</p>
      <WeightSliders weights={weights} onChange={setWeights} />
      <p className="text-[10px] leading-4 text-w-dim">
        Jobs that don't post pay are ranked after those that do; unposted pay is never counted as zero.
      </p>
      <div className="flex items-center">
        <button type="button" onClick={() => setWeights(DEFAULT_WEIGHTS)} className="text-[11px] text-w-dim hover:text-w-text">Reset</button>
        <button
          type="button"
          onClick={() => onApply(weights)}
          disabled={!anyWeightAboveZero(weights)}
          className="ml-auto rounded-md bg-w-accent px-3 py-1 text-[11px] font-semibold text-white hover:bg-w-accent-hi disabled:opacity-40"
        >
          Re-rank
        </button>
      </div>
    </div>
  )
}

/** The ranked jobs. Beside an open job, Location folds under the company. */
function LeadsTable({ leads, selectedLeadId, onSelect, compact, live }: {
  leads: JobLeadSummary[]
  selectedLeadId: string | null
  onSelect: (id: string) => void
  compact: boolean
  live: boolean
}) {
  if (leads.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-10 text-center text-xs text-w-dim">
        {live ? 'Jobs show up here as the search finds them.' : 'No jobs in this view.'}
      </div>
    )
  }
  const head = 'px-2 py-1.5 text-left text-[11px] font-semibold text-w-dim'
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full table-fixed border-collapse">
        <thead className="sticky top-0 z-10 bg-w-bg">
          <tr className="border-b border-w-line">
            <th className={`${head} w-9 pl-5 text-right`}>#</th>
            <th className={head}>Role</th>
            {!compact && <th className={`${head} hidden w-32 lg:table-cell`}>Location</th>}
            <th className={`${head} w-36`}>Pay</th>
            <th className={`${head} w-10`}>Fit</th>
            <th className={`${head} hidden w-20 pr-5 sm:table-cell`}>Status</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <LeadRow key={lead.id} lead={lead} selected={lead.id === selectedLeadId} onSelect={onSelect} compact={compact} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LeadRow({ lead, selected, onSelect, compact }: {
  lead: JobLeadSummary
  selected: boolean
  onSelect: (id: string) => void
  compact: boolean
}) {
  const remoteBadge = showsRemoteBadge(lead)
  const where = [lead.location, remoteBadge ? 'Remote' : ''].filter(Boolean).join(' · ')
  const cell = 'px-2 py-2 align-top'
  return (
    <tr
      onClick={() => onSelect(lead.id)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(lead.id) } }}
      tabIndex={0}
      aria-selected={selected}
      className={`cursor-pointer border-b border-w-line/50 outline-none focus-visible:bg-w-surface2/60 ${selected ? 'bg-w-accent/10' : 'hover:bg-w-surface2/50'}`}
    >
      <td className={`${cell} pl-5 text-right font-mono text-[11px] text-w-dim`}>{lead.rank ?? ''}</td>
      <td className={cell}>
        <div className="flex items-start gap-1.5">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-w-text">{lead.title}</p>
            <p className="truncate text-[11px] text-w-dim">
              {compact ? [lead.company, where].filter(Boolean).join(' · ') : lead.company}
              {!compact && where && <span className="lg:hidden"> · {where}</span>}
            </p>
          </div>
          {isDrafting(lead) ? (
            <Loader2 size={11} className="mt-0.5 shrink-0 animate-spin text-w-dim" aria-label="Drafting the approach" />
          ) : lead.approach_status === 'done' ? (
            <span title="Approach drafted" className="mt-0.5 shrink-0"><FileCheck2 size={11} className="text-w-accent" aria-label="Approach drafted" /></span>
          ) : null}
        </div>
      </td>
      {!compact && (
        <td className={`${cell} hidden text-[11px] text-w-text lg:table-cell`}>
          <span className="flex items-center gap-1">
            <span className="truncate">{lead.location}</span>
            {remoteBadge && <span className="shrink-0 rounded-full bg-w-surface2 px-1.5 text-[9px] font-semibold">Remote</span>}
          </span>
        </td>
      )}
      <td className={cell} title={lead.flags.includes('below_floor') ? 'Below your minimum base' : undefined}>
        <p className="truncate text-[11px] font-medium text-w-text">{lead.comp_line}</p>
        <p className={`text-[9px] font-semibold ${lead.comp_status === 'posted' ? 'text-emerald-500' : 'text-w-dim'}`}>{compBadge(lead.comp_status)}</p>
      </td>
      <td className={`${cell} font-mono text-[11px] text-w-text`}>{fitText(lead.fit_score)}</td>
      <td className={`${cell} hidden truncate pr-5 text-[11px] sm:table-cell ${emailWaiting(lead) ? 'text-w-accent' : 'text-w-dim'}`}>
        {leadStatusText(lead)}
      </td>
    </tr>
  )
}
