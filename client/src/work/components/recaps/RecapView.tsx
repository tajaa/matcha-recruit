import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { deleteRecap, retryRecap } from '../../api/matchaWork/recaps'
import { useRecap } from '../../hooks/useRecap'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type { RecapDetail } from '../../types'
import RecapPlayer from './RecapPlayer'

function sourcePath(base: string, source: RecapDetail['sources'][number]) {
  if (source.kind === 'jobs') return `${base}/jobs/${encodeURIComponent(source.id)}`
  if (source.kind === 'research') return `${base}/tasks/${encodeURIComponent(source.id)}`
  return `${base}/assistant`
}

const SOURCE_LABEL = { run: 'Open the conversation', jobs: 'Open the job search', research: 'Open the task' }

function statusText(state: RecapDetail['state']) {
  if (state === 'waiting') return 'Waiting for your answer or confirmation.'
  if (['collecting', 'queued', 'rendering'].includes(state)) return 'Your recap is being prepared. You can leave this page.'
  if (state === 'expired') return 'This recap has expired.'
  if (state === 'skipped') return 'No video was saved for this request.'
  return 'The task result is available, but its recap could not be prepared.'
}

/** One recap: the video with its chapters once it is ready (its status until
 *  then), what it came from, and every step it recorded. Polls while it is
 *  being made (`useRecap`). */
export default function RecapView({ recapId, onDeleted, onBack }: {
  recapId: string
  onDeleted: () => void
  /** Set on a narrow screen, where the list is a page back. */
  onBack?: () => void
}) {
  const base = useWorkBase()
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [retryId] = useState(() => crypto.randomUUID())
  const { recap, error } = useRecap(recapId, revision)

  async function act(action: 'retry' | 'delete') {
    if (action === 'delete' && !window.confirm('Delete this recap? The video and its steps are removed.')) return
    setBusy(true); setActionError('')
    try {
      if (action === 'delete') { await deleteRecap(recapId); onDeleted() }
      else { await retryRecap(recapId, retryId); setRevision((v) => v + 1) }
    } catch { setActionError('That action could not be completed. Refresh to check its status.') }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 p-5 text-w-text">
      {onBack && (
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs text-w-dim hover:text-w-text md:hidden">
          <ArrowLeft size={13} /> All recaps
        </button>
      )}
      <h2 className="text-lg font-semibold">{recap?.title ?? 'Task recap'}</h2>
      {(error || actionError) && <p role="alert" className="text-sm text-amber-500">{actionError || error}</p>}
      {!recap && !error && <div role="status" aria-label="Loading recap" className="flex justify-center py-10"><Loader2 className="animate-spin text-w-dim" /></div>}
      {recap && <>
        {recap.state === 'ready'
          ? <RecapPlayer key={`${recap.id}:${recap.ready_at}`} recap={recap} />
          : <p role="status" className="rounded-xl border border-w-line p-5 text-sm">{statusText(recap.state)}</p>}
        <div className="flex flex-wrap gap-2">
          {recap.sources.map((source) => (
            <Link key={`${source.kind}:${source.id}`} to={sourcePath(base, source)}
              className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-text hover:bg-w-surface2">
              {SOURCE_LABEL[source.kind]}
            </Link>
          ))}
          {recap.can_retry && <button type="button" disabled={busy} onClick={() => void act('retry')}
            className="rounded-md border border-w-line px-3 py-1.5 text-xs hover:bg-w-surface2 disabled:opacity-50">Retry video</button>}
          <button type="button" disabled={busy} onClick={() => void act('delete')}
            className="rounded-md border border-w-line px-3 py-1.5 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text disabled:opacity-50">Delete recap</button>
        </div>
        {recap.expires_at && <p className="text-[11px] text-w-dim">Available until {new Date(recap.expires_at).toLocaleString()}. Deletion stops new playback links; links already issued can remain valid for five minutes.</p>}
        <section>
          <h3 className="mb-2 text-sm font-semibold">Steps and outcomes</h3>
          <ol className="space-y-2">
            {recap.transcript.map((event, index) => (
              <li key={index} className="rounded-lg border border-w-line p-3">
                <p className="text-sm font-medium">{event.title}</p>
                <p className="text-[11px] text-w-dim">{event.outcome.replaceAll('_', ' ')}</p>
                {event.facts.length > 0 && (
                  <dl className="mt-1.5 text-xs">
                    {event.facts.map((fact, n) => <div key={n} className="flex gap-2"><dt className="text-w-dim">{fact.label}:</dt><dd>{fact.value}</dd></div>)}
                  </dl>
                )}
              </li>
            ))}
          </ol>
        </section>
      </>}
    </div>
  )
}
