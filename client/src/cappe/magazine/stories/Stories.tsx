import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { EyeOff, Loader2, Newspaper, Plus, Settings2 } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import { statusBadge, ui } from '../../components/ui'
import type { CappeMagazine, CappePost, CappeStoryOptions } from '../../types'

type Status = 'all' | 'draft' | 'published' | 'archived'

/** `sites/:siteId/stories` — the magazine's stories as a wall of covers,
 *  with the magazine's own switch and a link to its settings. */
export default function Stories() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [posts, setPosts] = useState<CappePost[] | null>(null)
  const [magazine, setMagazine] = useState<CappeMagazine | null>(null)
  const [topics, setTopics] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('all')
  const [topic, setTopic] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<CappePost[]>(`/sites/${siteId}/posts`),
      cappeApi.get<CappeMagazine>(`/sites/${siteId}/magazine`),
      cappeApi.get<CappeStoryOptions>(`/sites/${siteId}/stories/options`),
    ]).then(([p, m, o]) => {
      if (cancelled) return
      setPosts(p)
      setMagazine(m)
      setTopics(Object.fromEntries(o.topics.map((t) => [t.key, t.label])))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load stories') })
    return () => { cancelled = true }
  }, [siteId])

  const shown = (posts || []).filter((p) => (status === 'all' || p.status === status) && (!topic || p.topic === topic))
  const usedTopics = Array.from(new Set((posts || []).map((p) => p.topic).filter((t): t is string => !!t)))

  const startStory = async () => {
    setCreating(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappePost>(`/sites/${siteId}/posts`, {
        title: 'Untitled story', format: 'blocks', layout: 'standard',
      })
      navigate(`/sites/${siteId}/stories/${created.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start a story')
      setCreating(false)
    }
  }

  return (
    <SurfaceShell
      title={magazine?.name || 'Magazine'}
      subtitle={magazine?.live ? 'Live on your site.' : magazine?.enabled ? 'Turned on, but your plan doesn’t include a magazine yet.' : 'Stories told through pictures. Turn the magazine on in its settings to publish them.'}
      actions={
        <div className="flex gap-2">
          <Link to={`/sites/${siteId}/magazine`} className={ui.btnGhost}><Settings2 className="h-4 w-4" /> Magazine settings</Link>
          <button type="button" onClick={startStory} disabled={creating} className={ui.btnPrimary}>
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} New story
          </button>
        </div>
      }
    >
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex gap-1" role="tablist" aria-label="Status">
          {(['all', 'draft', 'published', 'archived'] as const).map((s) => (
            <button key={s} type="button" role="tab" aria-selected={status === s} onClick={() => setStatus(s)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize ${status === s ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}>
              {s}
            </button>
          ))}
        </div>
        {usedTopics.length > 0 && (
          <select value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Topic"
            className="ml-auto rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100">
            <option value="">All topics</option>
            {usedTopics.map((t) => <option key={t} value={t}>{topics[t] || t}</option>)}
          </select>
        )}
      </div>

      {posts === null && !error && (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      )}
      {posts && shown.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Newspaper className="mx-auto mb-2 h-7 w-7 text-zinc-300" />
          {posts.length === 0 ? 'No stories yet. Start one and pick its pictures.' : 'Nothing matches.'}
        </div>
      )}
      {shown.length > 0 && (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {shown.map((p) => (
            <li key={p.id}>
              <Link to={`/sites/${siteId}/stories/${p.id}`} className={`${ui.cardHover} block overflow-hidden`}>
                <div className="relative aspect-[4/5] bg-zinc-950">
                  {p.cover_image_url
                    ? <img src={p.cover_image_url} alt="" loading="lazy" className="h-full w-full object-cover" />
                    : <div className="flex h-full items-center justify-center text-zinc-700"><Newspaper className="h-8 w-8" /></div>}
                  <span className={`${ui.badge} absolute left-2 top-2 ${statusBadge[p.status] || ''}`}>{p.status}</span>
                  {p.hidden && (
                    <span className={`${ui.badge} absolute right-2 top-2 inline-flex items-center gap-1 bg-red-500/15 text-red-400`}>
                      <EyeOff className="h-3 w-3" /> hidden
                    </span>
                  )}
                </div>
                <div className="p-3">
                  {(p.kicker || (p.topic && topics[p.topic])) && (
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-emerald-400">{p.kicker || topics[p.topic!]}</p>
                  )}
                  <h2 className="mt-0.5 line-clamp-2 font-medium text-zinc-100">{p.title}</h2>
                  <p className="mt-1 text-xs text-zinc-500">
                    {p.format === 'markdown' ? 'Plain post' : `${p.reading_minutes || 0} min read`}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SurfaceShell>
  )
}
