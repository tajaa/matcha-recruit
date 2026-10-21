import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { BookOpen, EyeOff, Loader2, Plus } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import { ui } from '../../components/ui'
import type { CappeMagazineIssue, CappeMagazineIssueSummary } from '../../types'

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) : null

/** `sites/:siteId/issues` — the magazine's issues in print, newest first, as
 *  a wall of covers. A new issue takes the next number and opens in the
 *  issue editor. */
export default function IssuesPage() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [issues, setIssues] = useState<CappeMagazineIssueSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    cappeApi.get<CappeMagazineIssueSummary[]>(`/sites/${siteId}/magazine/issues`)
      .then((list) => { if (!cancelled) setIssues(list) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load your issues') })
    return () => { cancelled = true }
  }, [siteId])

  const start = async () => {
    setCreating(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeMagazineIssue>(`/sites/${siteId}/magazine/issues`, {})
      navigate(`/cappe/sites/${siteId}/issues/${created.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start an issue')
      setCreating(false)
    }
  }

  return (
    <SurfaceShell
      title="Issues"
      subtitle="Gather stories into a numbered issue with its own cover and contents. Readers turn it like a magazine."
      actions={
        <button type="button" onClick={start} disabled={creating} className={ui.btnPrimary}>
          {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} New issue
        </button>
      }
    >
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
      {issues === null && !error && (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      )}
      {issues && issues.length === 0 && (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <BookOpen className="mx-auto mb-2 h-7 w-7 text-zinc-300" />
          No issues yet. Start one, put your stories in it, and design its cover.
        </div>
      )}
      {issues && issues.length > 0 && (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {issues.map((i) => (
            <li key={i.id}>
              <Link to={`/cappe/sites/${siteId}/issues/${i.id}`} className={`${ui.cardHover} block overflow-hidden`}>
                <div className="relative aspect-[4/5] bg-zinc-950">
                  {i.cover_picture
                    ? <img src={i.cover_picture.url} alt={i.cover_picture.alt} loading="lazy" className="h-full w-full object-cover" />
                    : <div className="flex h-full items-center justify-center text-zinc-700"><BookOpen className="h-8 w-8" /></div>}
                  <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8 font-serif text-3xl font-black text-white">
                    No. {i.number}
                  </span>
                  <span className={`${ui.badge} absolute left-2 top-2 ${i.status === 'released' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>
                    {i.status === 'released' ? 'out' : 'draft'}
                  </span>
                  {i.hidden && (
                    <span className={`${ui.badge} absolute right-2 top-2 inline-flex items-center gap-1 bg-red-500/15 text-red-400`}>
                      <EyeOff className="h-3 w-3" /> hidden
                    </span>
                  )}
                </div>
                <div className="p-3">
                  <h2 className="line-clamp-2 font-medium text-zinc-100">{i.title || `No. ${i.number}`}</h2>
                  <p className="mt-1 text-xs text-zinc-500">
                    {i.story_count} {i.story_count === 1 ? 'story' : 'stories'}
                    {i.status === 'released' && i.released_at ? ` · ${when(i.released_at)}` : ''}
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
