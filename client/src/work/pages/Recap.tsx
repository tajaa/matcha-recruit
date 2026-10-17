import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'
import { deleteRecap, retryRecap } from '../api/matchaWork/recaps'
import RecapPlayer from '../components/recaps/RecapPlayer'
import { useRecap } from '../hooks/useRecap'
import { useWorkBase } from '../routes/WorkSurfaceContext'

export default function Recap() {
  const { recapId = '' } = useParams()
  const { isPersonal, loading } = useMe()
  const base = useWorkBase()
  const navigate = useNavigate()
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [retryId] = useState(() => crypto.randomUUID())
  const { recap, error } = useRecap(recapId, revision)
  async function act(action: 'retry' | 'delete') {
    setBusy(true); setActionError('')
    try {
      if (action === 'delete') { await deleteRecap(recapId); navigate(`${base}/recaps`) }
      else { await retryRecap(recapId, retryId); setRevision((v) => v + 1) }
    } catch { setActionError('That action could not be completed. Refresh to check its status.') }
    finally { setBusy(false) }
  }
  if (!loading && !isPersonal) return <p className="p-8 text-w-dim">Task recaps are available in personal Espresso accounts.</p>
  return <main className="mx-auto w-full max-w-5xl space-y-5 p-5 text-w-text">
    <Link to={`${base}/recaps`} className="text-sm text-w-dim">← All recaps</Link>
    <h1 className="text-2xl font-semibold">{recap?.title ?? 'Task recap'}</h1>
    {(error || actionError) && <p role="alert">{actionError || error}</p>}
    {!recap && !error && <p role="status">Loading recap…</p>}
    {recap && <>
      {recap.state === 'ready' ? <RecapPlayer key={`${recap.id}:${recap.ready_at}`} recap={recap} /> : <p role="status" className="rounded-xl border border-w-line p-5">{recap.state === 'waiting' ? 'Waiting for your answer or confirmation.' : ['collecting', 'queued', 'rendering'].includes(recap.state) ? 'Your recap is being prepared. You can close this page.' : recap.state === 'expired' ? 'This recap has expired.' : recap.state === 'skipped' ? 'No video was saved for this request.' : 'The task result is available, but its recap could not be prepared.'}</p>}
      <div className="flex flex-wrap gap-3">
        {recap.can_retry && <button disabled={busy} onClick={() => void act('retry')} className="rounded border border-w-line px-3 py-2 text-sm">Retry video</button>}
        <button disabled={busy} onClick={() => void act('delete')} className="rounded border border-w-line px-3 py-2 text-sm">Delete recap</button>
        {recap.sources.map((source) => <Link key={`${source.kind}:${source.id}`} className="rounded border border-w-line px-3 py-2 text-sm" to={source.kind === 'jobs' ? `${base}/jobs/${source.id}` : source.kind === 'research' ? `${base}/tasks/${source.id}` : `${base}/assistant`}>Open {source.kind === 'run' ? 'assistant' : source.kind === 'jobs' ? 'job search' : 'task'}</Link>)}
      </div>
      {recap.expires_at && <p className="text-xs text-w-dim">Available until {new Date(recap.expires_at).toLocaleString()}. Deletion stops new playback links; links already issued can remain valid for five minutes.</p>}
      <section><h2 className="mb-3 text-lg font-semibold">Steps and outcomes</h2><ol className="space-y-3">{recap.transcript.map((event, index) => <li key={index} className="rounded-lg border border-w-line p-4"><h3 className="font-medium">{event.title}</h3><p className="text-xs text-w-dim">{event.outcome.replaceAll('_', ' ')}</p><dl className="mt-2 text-sm">{event.facts.map((fact, n) => <div key={n} className="flex gap-2"><dt className="text-w-dim">{fact.label}:</dt><dd>{fact.value}</dd></div>)}</dl></li>)}</ol></section>
    </>}
  </main>
}
