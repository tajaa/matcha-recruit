import RecapLink from '../../components/recaps/RecapLink'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, BadgeCheck, Bookmark, Building2, CornerDownRight, FileText, HelpCircle, Loader2,
  MessageSquareText, SearchCheck, SlidersHorizontal, Trash2, X,
} from 'lucide-react'
import type { AgentTaskColumn, AgentTaskDetail, AgentTaskItem } from '../../types'
import {
  FILTERS, canFollowUp, columnLabel, displayTitle, filterItems, hiddenReason, homesLine, isHidden, isLive, isVerified, isWaiting,
  latestSummary, planChips, rowFacts, statusLabel, unconfirmed, webUrl, type FindingFilter,
} from '../../components/tasks/tasksLogic'

/**
 * One task: what it's looking for, how far it has got, what it says it found,
 * and its findings. The open finding shows beside it (`ItemPane`). Mirrors the
 * macOS app's Tasks view; a job search never shows here (it opens in Job search).
 */
export default function TaskDetail({
  detail, busy, error, onDismissError, journalPath, onDismissJournal, selectedItemId, onSelectItem,
  onCancel, onRefine, onMore, onDocument, onAskEspresso, onDelete, onBack,
}: {
  detail: AgentTaskDetail
  busy: boolean
  error: string | null
  onDismissError: () => void
  /** The document a "Make document" just wrote, to open. */
  journalPath: string | null
  onDismissJournal: () => void
  selectedItemId: string | null
  onSelectItem: (id: string) => void
  onCancel: () => void
  onRefine: (change: string) => void
  onMore: () => void
  onDocument: () => void
  onAskEspresso: () => void
  onDelete: () => void
  /** Small screens: back to the list of tasks. */
  onBack: () => void
}) {
  const [filter, setFilter] = useState<FindingFilter>('Fits')
  const [refineOpen, setRefineOpen] = useState(false)
  const items = detail.items ?? []
  const columns = detail.plan?.columns ?? []
  const visible = filterItems(items, filter)
  const hiddenCount = items.filter(isHidden).length
  const live = isLive(detail)
  const summary = live ? null : latestSummary(detail)
  const chips = planChips(detail)
  const followUp = canFollowUp(detail)

  return (
    // On a phone the whole column scrolls, so a long summary never squeezes the
    // findings out; wider, the header stays put and only the findings scroll.
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto md:overflow-y-hidden">
      <header className="space-y-2 border-b border-w-line px-5 py-4">
        <RecapLink sourceId={detail.id} />
        <div className="flex items-start gap-2">
          <button type="button" onClick={onBack} aria-label="All tasks" className="-ml-1 rounded-md p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text md:hidden">
            <ArrowLeft size={16} />
          </button>
          <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-w-text">{displayTitle(detail)}</h1>
          <button
            type="button"
            onClick={onAskEspresso}
            aria-label="Ask Espresso about this task"
            title="Ask Espresso about this task"
            className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text"
          >
            <MessageSquareText size={14} />
          </button>
          {!live && (
            <button type="button" onClick={onDelete} disabled={busy} aria-label="Delete this task" title="Delete this task" className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-red-400 disabled:opacity-40">
              <Trash2 size={14} />
            </button>
          )}
        </div>
        {detail.directive && detail.directive !== displayTitle(detail) && (
          <p className="line-clamp-2 text-[11px] text-w-dim">{detail.directive}</p>
        )}
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span key={chip} className="rounded-full bg-w-accent/10 px-2 py-0.5 text-[10px] font-medium text-w-text">{chip}</span>
            ))}
          </div>
        )}
        <p className={`flex flex-wrap items-center gap-1.5 text-[11px] font-medium ${detail.status === 'failed' ? 'text-amber-500' : 'text-w-dim'}`}>
          {live && <Loader2 size={11} className="animate-spin" />}
          {live ? detail.progress?.note || statusLabel(detail) : statusLabel(detail)}
          {detail.status === 'failed' && detail.error && <span className="font-normal">{detail.error}</span>}
        </p>
        {summary && (
          <div className="space-y-1 rounded-lg bg-w-surface2/50 p-2.5">
            {summary.headline && <p className="line-clamp-3 text-[13px] font-semibold text-w-text">{summary.headline}</p>}
            {summary.summary && <p className="line-clamp-6 select-text text-xs leading-5 text-w-dim">{summary.summary}</p>}
          </div>
        )}
        {detail.status === 'done' && items.length > 0 && (
          <p className="flex items-start gap-1.5 text-[11px] leading-4 text-w-dim">
            <CornerDownRight size={12} className="mt-0.5 shrink-0" />
            Next: open a finding to see where each fact came from, Save the ones you like, Refine to narrow it down,
            or Make document to keep a write-up.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {(live || isWaiting(detail)) && (
            <button type="button" onClick={onCancel} disabled={busy} className="rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40">
              Cancel
            </button>
          )}
          {followUp && (
            <>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setRefineOpen((v) => !v)}
                  disabled={busy}
                  aria-expanded={refineOpen}
                  title="Change what it's looking for. Free."
                  className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40"
                >
                  <SlidersHorizontal size={12} /> Refine
                </button>
                {refineOpen && (
                  <RefinePopover
                    onClose={() => setRefineOpen(false)}
                    onRefine={(change) => { setRefineOpen(false); onRefine(change) }}
                  />
                )}
              </div>
              <button
                type="button"
                onClick={onMore}
                disabled={busy}
                title="Look for more like these. Uses 1 unit."
                className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40"
              >
                <SearchCheck size={12} /> Search more
              </button>
            </>
          )}
          {!live && items.length > 0 && (
            <button
              type="button"
              onClick={onDocument}
              disabled={busy}
              title="Write what it found into a note. Free."
              className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-40"
            >
              <FileText size={12} /> Make document
            </button>
          )}
          {busy && <Loader2 size={13} className="animate-spin text-w-dim" />}
        </div>
      </header>

      {error && (
        <div role="alert" className="flex items-center gap-2 bg-amber-500/10 px-5 py-1.5 text-[11px] text-amber-500">
          <AlertTriangle size={12} className="shrink-0" />
          <span className="line-clamp-2 flex-1">{error}</span>
          <button type="button" onClick={onDismissError} aria-label="Dismiss" className="rounded p-0.5 hover:bg-amber-500/10"><X size={11} /></button>
        </div>
      )}

      {journalPath && (
        <div className="flex items-center gap-2 bg-w-accent/10 px-5 py-1.5 text-[11px] text-w-accent">
          <FileText size={12} className="shrink-0" />
          <span>The document is in your Journals.</span>
          <Link to={journalPath} className="font-semibold hover:underline">Open</Link>
          <span className="flex-1" />
          <button type="button" onClick={onDismissJournal} aria-label="Dismiss" className="rounded p-0.5 hover:bg-w-accent/10"><X size={11} /></button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-2">
        <div role="tablist" aria-label="Filter findings" className="flex rounded-md border border-w-line p-0.5">
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
        <span className="ml-auto text-[10px] text-w-dim">{items.length - hiddenCount} fit · {hiddenCount} hidden</span>
      </div>

      <div className="flex-1 space-y-1 px-3.5 pb-4 md:min-h-0 md:overflow-y-auto">
        {visible.map((item) => (
          <FindingRow key={item.id} item={item} columns={columns} selected={item.id === selectedItemId} onSelect={onSelectItem} />
        ))}
        {visible.length === 0 && (
          <p className="pt-8 text-center text-xs text-w-dim">{live ? "Nothing yet. It's still looking." : 'Nothing here.'}</p>
        )}
      </div>
    </div>
  )
}

/** Change what it's looking for. Free. */
function RefinePopover({ onRefine, onClose }: { onRefine: (change: string) => void; onClose: () => void }) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const change = text.trim()

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
    <div ref={ref} role="dialog" aria-label="What should change?" className="absolute left-0 top-full z-30 mt-1 w-80 space-y-2.5 rounded-xl border border-w-line bg-w-surface p-4 shadow-2xl">
      <label htmlFor="task-refine" className="block text-sm font-semibold text-w-text">What should change?</label>
      <textarea
        id="task-refine"
        autoFocus
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Only the Mission, and a dishwasher"
        className="w-full resize-none rounded-md border border-w-line bg-w-surface2/40 px-2 py-1.5 text-xs text-w-text placeholder:text-w-faint focus:border-w-accent focus:outline-none"
      />
      <p className="text-[10px] leading-4 text-w-dim">
        Espresso re-checks what it found against the change, reads pages again only for new facts, and searches again
        if too little is left. Free.
      </p>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onRefine(change)}
          disabled={change.length < 3}
          className="rounded-md bg-w-accent px-3 py-1 text-[11px] font-semibold text-white hover:bg-w-accent-hi disabled:opacity-40"
        >
          Refine
        </button>
      </div>
    </div>
  )
}

/** Rank, photo, name, and the facts the plan asked for, each marked when it
 *  couldn't be confirmed on the finding's own page. */
function FindingRow({ item, columns, selected, onSelect }: {
  item: AgentTaskItem
  columns: AgentTaskColumn[]
  selected: boolean
  onSelect: (id: string) => void
}) {
  const image = webUrl(item.images?.[0]?.url)
  const reason = hiddenReason(item)
  const missing = unconfirmed(item)
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      aria-current={selected ? 'true' : undefined}
      className={`flex w-full items-start gap-2.5 rounded-lg p-2 text-left ${selected ? 'bg-w-accent/10' : 'bg-w-surface2/30 hover:bg-w-surface2/60'}`}
    >
      <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] text-w-dim">{item.rank ?? ''}</span>
      {image && <img src={image} alt="" loading="lazy" className="h-[46px] w-[46px] shrink-0 rounded-md bg-w-surface2 object-cover" />}
      <span className="min-w-0 flex-1 space-y-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-xs font-semibold text-w-text">{item.title}</span>
          {item.user_state === 'chosen' && <BadgeCheck size={11} className="shrink-0 text-w-accent" aria-label="Chosen" />}
          {item.user_state === 'saved' && <Bookmark size={11} className="shrink-0 fill-current text-w-accent" aria-label="Saved" />}
        </span>
        {item.subtitle && <span className="block truncate text-[11px] text-w-dim">{item.subtitle}</span>}
        <FactChips item={item} columns={columns} />
        {item.homes && (
          <span className={`flex items-center gap-1 text-[10px] font-medium ${item.homes.fit === 0 ? 'text-w-dim' : 'text-w-text'}`}>
            <Building2 size={10} /> {homesLine(item.homes)}
          </span>
        )}
        {reason ? (
          <span className="block text-[10px] text-amber-500">{reason}</span>
        ) : missing.length > 0 ? (
          <span className="block text-[10px] text-w-dim">Unconfirmed: {missing.map((k) => columnLabel(k, columns)).join(', ')}</span>
        ) : null}
      </span>
    </button>
  )
}

/** "Price $3,200/mo", marked when only stated on another page. */
function FactChips({ item, columns }: { item: AgentTaskItem; columns: AgentTaskColumn[] }) {
  const facts = rowFacts(item, columns)
  if (!facts.length) return null
  return (
    <span className="flex flex-wrap gap-1.5">
      {facts.map(({ key, label, field }) => {
        const verified = isVerified(field)
        return (
          <span
            key={key}
            title={verified ? 'Read on its own page' : 'Unconfirmed: only stated on another page'}
            className="inline-flex max-w-full items-center gap-1 truncate rounded-full bg-w-surface2/70 px-1.5 py-px text-[10px]"
          >
            <span className="text-w-dim">{label}</span>
            <span className="font-medium text-w-text">{field.display}</span>
            {!verified && <HelpCircle size={10} className="shrink-0 text-amber-500" />}
          </span>
        )
      })}
    </span>
  )
}
