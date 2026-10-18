import { useEffect, useState } from 'react'
import { Film, Loader2 } from 'lucide-react'
import { listRecaps } from '../../api/matchaWork/recaps'
import type { RecapState, RecapSummary } from '../../types'

const STATE_LABEL: Record<RecapState, string> = {
  collecting: 'Recording',
  waiting: 'Waiting for you',
  queued: 'Being prepared',
  rendering: 'Being prepared',
  ready: 'Ready',
  failed: 'Couldn’t be made',
  skipped: 'No video',
  expired: 'Expired',
  deleted: 'Deleted',
}

function recapStateLabel(state: RecapState) {
  return STATE_LABEL[state] ?? state
}

/**
 * The person's recaps, newest first, a page at a time. `source` narrows it to
 * one task's recaps. Keyed by owner and source, so switching either starts a
 * fresh first page and never shows another account's (or filter's) rows.
 */
export default function RecapList(props: {
  owner: string | undefined
  source: string | null
  selectedId: string | null
  onOpen: (recap: RecapSummary) => void
}) {
  return <Library key={`${props.owner ?? ''}:${props.source ?? ''}`} {...props} />
}

function Library({ owner, source, selectedId, onOpen }: {
  owner: string | undefined
  source: string | null
  selectedId: string | null
  onOpen: (recap: RecapSummary) => void
}) {
  const [recaps, setRecaps] = useState<RecapSummary[] | null>(null)
  const [next, setNext] = useState<string | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!owner) return
    let active = true
    void listRecaps(cursor, source).then((result) => {
      if (!active) return
      setRecaps((old) => (cursor && old ? [...old, ...result.recaps] : result.recaps))
      setNext(result.next_cursor)
      setError('')
    }).catch(() => { if (active) setError('Could not load recaps. Try reopening this page.') })
    return () => { active = false }
  }, [owner, source, cursor])

  return (
    <div className="space-y-0.5">
      {error && <p role="alert" className="p-3 text-xs text-amber-500">{error}</p>}
      {!recaps && !error && <div role="status" aria-label="Loading recaps" className="flex justify-center p-6"><Loader2 size={16} className="animate-spin text-w-dim" /></div>}
      {recaps?.length === 0 && (
        <p className="p-3 text-center text-xs leading-5 text-w-dim">
          {source ? 'No recaps for this task.' : 'No recaps yet. New tasks are recorded once recaps are on in Settings.'}
        </p>
      )}
      <ul className="space-y-0.5">
        {recaps?.map((recap) => {
          const selected = recap.id === selectedId
          return (
            <li key={recap.id}>
              <button type="button" onClick={() => onOpen(recap)} aria-current={selected ? 'page' : undefined}
                className={`flex w-full items-start gap-2 rounded-md px-2 py-2 text-left ${selected ? 'bg-w-accent/10' : 'hover:bg-w-surface2/60'}`}>
                <Film size={13} className={`mt-0.5 shrink-0 ${recap.state === 'ready' ? 'text-w-accent' : 'text-w-faint'}`} />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 text-xs font-semibold text-w-text">{recap.title}</span>
                  <span className="mt-0.5 block truncate text-[10px] text-w-dim">
                    {[recapStateLabel(recap.state), new Date(recap.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
                      recap.duration_ms ? `${Math.round(recap.duration_ms / 1000)}s` : null].filter(Boolean).join(' · ')}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {next && <button type="button" onClick={() => setCursor(next)}
        className="my-3 w-full rounded-md border border-w-line px-3 py-2 text-xs text-w-text">Load older recaps</button>}
    </div>
  )
}
