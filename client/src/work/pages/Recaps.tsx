import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMe } from '../../hooks/useMe'
import { listRecaps } from '../api/matchaWork/recaps'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import type { RecapSummary } from '../types'

export default function Recaps() {
  const { me, isPersonal, loading } = useMe()
  const base = useWorkBase()
  const [query] = useSearchParams()
  const source = query.get('source_id')
  const owner = me?.user.id
  return <RecapLibrary key={`${owner ?? ''}:${source ?? ''}:${isPersonal}`} owner={owner} isPersonal={isPersonal} loading={loading} base={base} source={source} />
}

function RecapLibrary({ owner, isPersonal, loading, base, source }: {
  owner: string | undefined; isPersonal: boolean; loading: boolean; base: string; source: string | null
}) {
  const [page, setPage] = useState<{ owner: string; source: string | null; recaps: RecapSummary[]; cursor: string | null } | null>(null)
  const [error, setError] = useState('')
  const [paging, setPaging] = useState<{ owner: string; source: string | null; cursor: string } | null>(null)
  const cursor = paging?.owner === owner && paging?.source === source ? paging.cursor : null
  useEffect(() => {
    let active = true
    if (owner && isPersonal) void listRecaps(cursor, source).then((result) => {
      if (active) { setPage((old) => ({ owner, source, recaps: cursor && old?.owner === owner && old.source === source ? [...old.recaps, ...result.recaps] : result.recaps, cursor: result.next_cursor })); setError('') }
    }).catch(() => { if (active) setError('Could not load recaps. Try reopening this page.') })
    return () => { active = false }
  }, [owner, isPersonal, source, cursor])
  const shown = page && page.owner === owner && page.source === source && isPersonal ? page : null
  if (!loading && !isPersonal) return <p className="p-8 text-w-dim">Task recaps are available in personal Espresso accounts.</p>
  return <main className="mx-auto w-full max-w-4xl space-y-5 p-6 text-w-text">
    <div className="flex items-center justify-between"><h1 className="text-2xl font-semibold">Task recaps</h1><Link to={`${base}/settings`} className="text-sm text-w-dim">Recap settings</Link></div>
    <p className="text-sm text-w-dim">Short private videos of the key steps and results. New tasks are recorded when you enable recaps in Settings.</p>
    {error && <p role="alert">{error}</p>}
    {!shown && !error && <p role="status">Loading recaps…</p>}
    {shown?.recaps.length === 0 && <p>No recaps yet.</p>}
    <ul className="space-y-3">{shown?.recaps.map((recap) => <li key={recap.id}><Link className="block rounded-xl border border-w-line p-4 hover:bg-w-surface2" to={`${base}/recaps/${recap.id}`}><h2 className="font-medium">{recap.title}</h2><p className="mt-1 text-xs text-w-dim">{recap.state} · {new Date(recap.created_at).toLocaleString()}{recap.duration_ms ? ` · ${Math.round(recap.duration_ms / 1000)} seconds` : ''}</p></Link></li>)}</ul>
    {shown?.cursor && <button onClick={() => { if (owner && shown.cursor) setPaging({ owner, source, cursor: shown.cursor }) }} className="rounded border border-w-line px-3 py-2 text-sm">Load older recaps</button>}
  </main>
}
