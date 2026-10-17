import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, Clock, ExternalLink, Link2, Loader2, Phone, ShoppingCart, CalendarPlus, Mail, X, OctagonX } from 'lucide-react'
import { cancelAgentTaskAction, confirmAgentTaskAction, proposeAgentTaskAction } from '../../api/matchaWork/agentTasks'
import type { AgentTaskAction, AgentTaskActionLine, AgentTaskActionRun } from '../../types'
import IntakeFieldInput from '../../components/tasks/IntakeFieldInput'
import {
  RUNNING_READS, RUNNING_READ_MS, actionParams, actionStage, errorText, initialText, webUrl,
} from '../../components/tasks/tasksLogic'

export function ActionIcon({ icon, size = 12 }: { icon: string | null | undefined; size?: number }) {
  switch (icon) {
    case 'cart': return <ShoppingCart size={size} />
    case 'calendar': return <CalendarPlus size={size} />
    case 'envelope': return <Mail size={size} />
    case 'phone': return <Phone size={size} />
    default: return <Link2 size={size} />
  }
}

/**
 * One action on a finding (buy it, apply), start to end, as on the Mac
 * (`TaskActionSheet`): its own fields, then exactly what it will do, then the
 * person's yes, then what came of it. The server proposes and carries out;
 * this only shows and asks. Espresso never pays, orders or applies: what comes
 * of a yes is a link (a store's checkout with it in the cart, an application),
 * which the person opens and finishes themselves.
 *
 * A yes can come back `running` (a confirm retried while the first one was
 * still carrying it out). That isn't an outcome: the sheet reads it again, by
 * the same confirm (which only reports a yes already given), until it's done or
 * failed, and says it's still going rather than that nothing was done.
 */
export default function ActionModal({ taskId, itemId, itemTitle, action, onClose }: {
  taskId: string
  itemId: string
  itemTitle: string
  action: AgentTaskAction
  /** Closed: `changed` when something was carried out, so the finding reloads. */
  onClose: (changed: boolean) => void
}) {
  const params = useMemo(() => action.params ?? [], [action.params])
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(
    params.flatMap((f) => (initialText(f.value) ? [[f.key, initialText(f.value)]] : [])),
  ))
  const [run, setRun] = useState<AgentTaskActionRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** Still running after the sheet stopped reading it again. */
  const [stillGoing, setStillGoing] = useState(false)
  const stage = actionStage(run)
  const dialogRef = useRef<HTMLDivElement>(null)
  // What a close has to withdraw: a proposal left in review.
  const pending = useRef<AgentTaskActionRun | null>(null)
  useEffect(() => { pending.current = run && run.status === 'proposed' ? run : null }, [run])
  const reviewing = useRef(false)
  // Closed: answers that land afterwards change nothing on screen, and a
  // proposal that lands afterwards is withdrawn. Set in the effect's body too,
  // so a development double mount starts open again.
  const closed = useRef(false)
  useEffect(() => {
    closed.current = false
    return () => {
      closed.current = true
      if (pending.current) void cancelAgentTaskAction(pending.current.id).catch(() => {})
    }
  }, [])

  /** Ask the server what it would do. Nothing happens yet. */
  const review = useCallback(async () => {
    if (reviewing.current) return
    reviewing.current = true
    setBusy(true)
    setError(null)
    try {
      const proposed = await proposeAgentTaskAction(taskId, itemId, action.key, actionParams(values, params))
      if (closed.current) {
        if (proposed.status === 'proposed') void cancelAgentTaskAction(proposed.id).catch(() => {})
        return
      }
      setRun(proposed)
    } catch (e) {
      if (!closed.current) setError(errorText(e, 'Something went wrong. Please try again.'))
    } finally {
      reviewing.current = false
      if (!closed.current) setBusy(false)
    }
  }, [taskId, itemId, action.key, values, params])

  // Nothing to fill in: straight to what it would do.
  const autoReviewed = useRef(false)
  useEffect(() => {
    if (params.length === 0 && !autoReviewed.current) {
      autoReviewed.current = true
      void review()
    }
  }, [params.length, review])

  // Something may have been carried out once the person said yes.
  const close = useCallback(() => onClose(stage === 'working' || stage === 'finished'), [onClose, stage])

  useEffect(() => {
    dialogRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [close])

  /** The yes: carried out once. Asking again after an error is safe: the
   *  server reports a yes it already has instead of carrying it out twice. */
  async function confirm() {
    if (!run || run.status !== 'proposed' || busy) return
    await follow(run.id)
  }

  /** Confirm, then read it again while it's running, up to about a minute. */
  async function follow(id: string) {
    setBusy(true)
    setError(null)
    setStillGoing(false)
    let running = stage === 'working'
    try {
      for (let reads = 0; ; reads += 1) {
        const next = await confirmAgentTaskAction(id)
        if (closed.current) return
        setRun(next)
        running = next.status === 'running'
        if (!running) return
        if (reads >= RUNNING_READS) {
          setStillGoing(true)
          return
        }
        await new Promise((resolve) => { window.setTimeout(resolve, RUNNING_READ_MS) })
        if (closed.current) return
      }
    } catch (e) {
      if (closed.current) return
      // A yes already given stays given: say it's still going, not that it failed.
      if (running) setStillGoing(true)
      setError(errorText(e, running ? "Couldn't check on it just now." : 'Something went wrong. Please try again.'))
    } finally {
      if (!closed.current) setBusy(false)
    }
  }

  /** Back to the fields, to change them. */
  async function edit() {
    if (run) await cancelAgentTaskAction(run.id).catch(() => null)
    setRun(null)
  }

  const title = run?.preview?.title || `${action.label} ${itemTitle}`
  const resultUrl = webUrl(run?.result?.url)

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/70 sm:items-center sm:px-4" onMouseDown={(e) => { if (e.target === e.currentTarget) close() }}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex max-h-[92vh] w-full max-w-md flex-col gap-4 overflow-y-auto rounded-t-2xl border border-w-line bg-w-surface p-5 shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-start gap-2">
          <span className="mt-0.5 text-w-accent"><ActionIcon icon={action.icon} size={15} /></span>
          <h2 className="line-clamp-2 flex-1 text-sm font-semibold text-w-text">{title}</h2>
          <button type="button" onClick={close} aria-label="Close" className="rounded-md p-1 text-w-faint hover:bg-w-surface2 hover:text-w-text"><X size={15} /></button>
        </div>

        {stage === 'details' && (
          <div className="space-y-3">
            {action.description && <p className="text-xs leading-5 text-w-dim">{action.description}</p>}
            {params.map((field) => (
              <div key={field.key} className="space-y-1">
                <label htmlFor={`action-${field.key}`} className="block text-[11px] font-semibold text-w-text">{field.label}</label>
                <IntakeFieldInput
                  id={`action-${field.key}`}
                  field={field}
                  value={values[field.key] ?? ''}
                  onChange={(value) => setValues((prev) => ({ ...prev, [field.key]: value }))}
                />
                {field.help && <p className="text-[10px] text-w-dim">{field.help}</p>}
              </div>
            ))}
            {params.length === 0 && busy && <div className="flex justify-center py-4"><Loader2 className="animate-spin text-w-dim" /></div>}
            {params.length === 0 && !busy && error && (
              <div className="flex items-center gap-2 pt-1">
                <button type="button" onClick={close} className="text-xs text-w-dim hover:text-w-text">Cancel</button>
                <span className="flex-1" />
                <button type="button" onClick={() => void review()} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
                  Try again
                </button>
              </div>
            )}
            {params.length > 0 && (
              <div className="flex items-center gap-2 pt-1">
                <button type="button" onClick={close} className="text-xs text-w-dim hover:text-w-text">Cancel</button>
                <span className="flex-1" />
                {busy && <Loader2 size={14} className="animate-spin text-w-dim" />}
                <button type="button" onClick={() => void review()} disabled={busy} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi disabled:opacity-50">
                  Review
                </button>
              </div>
            )}
          </div>
        )}

        {stage === 'review' && run && (
          <div className="space-y-3">
            <Lines lines={run.preview?.lines ?? []} />
            {run.preview?.note && <p className="text-[11px] leading-5 text-w-dim">{run.preview.note}</p>}
            <div className="flex items-center gap-3 pt-1">
              <button type="button" onClick={() => onClose(false)} className="text-xs text-w-dim hover:text-w-text">Cancel</button>
              {params.length > 0 && <button type="button" onClick={() => void edit()} className="text-xs text-w-dim hover:text-w-text">Change</button>}
              <span className="flex-1" />
              {busy && <Loader2 size={14} className="animate-spin text-w-dim" />}
              <button type="button" onClick={() => void confirm()} disabled={busy} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi disabled:opacity-50">
                {run.confirm_label || action.confirm_label || 'Go ahead'}
              </button>
            </div>
          </div>
        )}

        {stage === 'working' && run && (
          <div className="space-y-3">
            {stillGoing ? (
              <p className="flex items-start gap-1.5 text-xs text-w-text">
                <Clock size={14} className="mt-0.5 shrink-0 text-w-dim" />
                It's still going. Nothing more is needed from you; what came of it shows under Done on this finding.
              </p>
            ) : (
              <p className="flex items-center gap-1.5 text-xs text-w-text">
                <Loader2 size={14} className="animate-spin text-w-dim" /> Working on it…
              </p>
            )}
            <div className="flex items-center gap-2 pt-1">
              {stillGoing && !busy && (
                <button type="button" onClick={() => void follow(run.id)} className="text-xs text-w-dim hover:text-w-text">Check again</button>
              )}
              <span className="flex-1" />
              <button type="button" onClick={close} className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-text hover:bg-w-surface2">Done</button>
            </div>
          </div>
        )}

        {stage === 'finished' && run && (
          <div className="space-y-3">
            {run.status === 'done' && run.result ? (
              <>
                <p className="flex items-center gap-1.5 text-xs font-medium text-emerald-500"><CheckCircle2 size={14} /> {run.result.headline}</p>
                <Lines lines={run.result.lines ?? []} />
              </>
            ) : (
              <p className="flex items-start gap-1.5 text-xs text-amber-500">
                <OctagonX size={14} className="mt-0.5 shrink-0" /> {run.error || "It didn't go through. Nothing was done."}
              </p>
            )}
            <div className="flex items-center gap-2 pt-1">
              {resultUrl && (
                <a href={resultUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
                  <ExternalLink size={12} /> Open
                </a>
              )}
              <span className="flex-1" />
              <button type="button" onClick={close} className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-text hover:bg-w-surface2">Done</button>
            </div>
          </div>
        )}

        {error && <p role="alert" className="text-[11px] text-amber-500">{error}</p>}
      </div>
    </div>
  )
}

function Lines({ lines }: { lines: AgentTaskActionLine[] }) {
  if (!lines.length) return null
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
      {lines.map((line, i) => (
        <div key={`${line.label}-${i}`} className="contents">
          <dt className="text-w-dim">{line.label}</dt>
          <dd className="select-text break-words text-w-text">{line.value}</dd>
        </div>
      ))}
    </dl>
  )
}
