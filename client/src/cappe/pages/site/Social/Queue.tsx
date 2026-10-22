import { useEffect, useRef, useState } from 'react'
import { CalendarClock, ExternalLink, Film, Loader2, RefreshCw, Send, Trash2, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import type { CappeSocialPost, CappeSocialPostStatus } from '../../../types'
import { localInputToIso, toLocalInput } from '../../../utils/socialSchedule'

const FILTERS: { key: string; label: string; statuses: CappeSocialPostStatus[] | null }[] = [
  { key: 'upcoming', label: 'Upcoming', statuses: ['scheduled', 'rendering', 'publishing'] },
  { key: 'drafts', label: 'Drafts', statuses: ['draft'] },
  { key: 'posted', label: 'Posted', statuses: ['published', 'partial'] },
  { key: 'problems', label: 'Problems', statuses: ['failed'] },
  { key: 'all', label: 'All', statuses: null },
]

const BADGE: Record<string, string> = {
  draft: 'bg-zinc-800 text-zinc-400',
  scheduled: 'bg-sky-500/15 text-sky-400',
  rendering: 'bg-violet-500/15 text-violet-300',
  publishing: 'bg-amber-500/15 text-amber-400',
  pending: 'bg-amber-500/15 text-amber-400',
  published: 'bg-emerald-500/15 text-emerald-400',
  partial: 'bg-orange-500/15 text-orange-400',
  failed: 'bg-red-500/15 text-red-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
}

const EDITABLE: CappeSocialPostStatus[] = ['draft', 'scheduled', 'rendering', 'failed']
const STATUS_LABEL: Partial<Record<CappeSocialPostStatus, string>> = { rendering: 'preparing video' }
const PHASE_LABEL: Record<string, string> = {
  instagram_processing: 'Instagram is processing the video',
  facebook_processing: 'Facebook is processing the video',
}
// A partial post (one network took it) can re-try the rest; nothing goes out twice.
const RETRYABLE: CappeSocialPostStatus[] = [...EDITABLE, 'partial']
const POLL_MS = 5000

export default function Queue({ siteId, refreshKey }: { siteId: string; refreshKey: number }) {
  const [posts, setPosts] = useState<CappeSocialPost[] | null>(null)
  const [filter, setFilter] = useState('upcoming')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [rescheduling, setRescheduling] = useState<{ id: string; value: string } | null>(null)
  const [tick, setTick] = useState(0)
  const generation = useRef(0)

  useEffect(() => {
    const gen = ++generation.current
    cappeApi.get<CappeSocialPost[]>(`/sites/${siteId}/social/posts?limit=200`)
      .then((list) => { if (gen === generation.current) { setPosts(list); setError(null) } })
      .catch((e) => { if (gen === generation.current) setError(e instanceof Error ? e.message : 'Couldn’t load posts') })
  }, [siteId, refreshKey, tick])

  // While anything is going out (or its video is being cut), check back until it reports.
  const publishing = !!posts?.some((p) => p.status === 'publishing' || p.status === 'rendering')
  useEffect(() => {
    if (!publishing) return
    const timer = setInterval(() => setTick((n) => n + 1), POLL_MS)
    return () => clearInterval(timer)
  }, [publishing])

  const statuses = FILTERS.find((f) => f.key === filter)?.statuses
  const shown = (posts ?? []).filter((p) => !statuses || statuses.includes(p.status))

  async function act(p: CappeSocialPost, run: () => Promise<CappeSocialPost | null>) {
    setBusy(p.id)
    setError(null)
    try {
      const updated = await run()
      setPosts((list) => (list ?? []).flatMap((x) => (x.id !== p.id ? [x] : updated ? [updated] : [])))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That didn’t work')
    } finally {
      setBusy(null)
    }
  }

  const base = `/sites/${siteId}/social/posts`
  const postNow = (p: CappeSocialPost) => act(p, () => cappeApi.post<CappeSocialPost>(`${base}/${p.id}/publish`))
  const cancel = (p: CappeSocialPost) => act(p, () => cappeApi.post<CappeSocialPost>(`${base}/${p.id}/cancel`))
  const remove = (p: CappeSocialPost) => {
    if (!confirm('Delete this post? It hasn’t gone out, so nothing changes on Instagram or Facebook.')) return
    void act(p, async () => { await cappeApi.delete(`${base}/${p.id}`); return null })
  }
  const reschedule = (p: CappeSocialPost, value: string) => {
    const iso = localInputToIso(value)
    if (!iso) { setError('Pick a time'); return }
    setRescheduling(null)
    void act(p, () => cappeApi.patch<CappeSocialPost>(`${base}/${p.id}`, { scheduled_at: iso }))
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <div className="flex flex-1 flex-wrap gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
          {FILTERS.map((f) => {
            const n = (posts ?? []).filter((p) => !f.statuses || f.statuses.includes(p.status)).length
            return (
              <button key={f.key} type="button" onClick={() => setFilter(f.key)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${filter === f.key
                  ? 'bg-lime-400 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>
                {f.label} {posts && <span className="opacity-70">{n}</span>}
              </button>
            )
          })}
        </div>
        <button type="button" onClick={() => setTick((n) => n + 1)} aria-label="Refresh"
          className="rounded-lg border border-zinc-700 p-2 text-zinc-400 hover:bg-zinc-800"><RefreshCw className="h-4 w-4" /></button>
      </div>
      {error && <p role="alert" className="mb-3 text-sm text-red-400">{error}</p>}
      {posts === null && !error ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : shown.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <CalendarClock className="mx-auto mb-2 h-7 w-7 text-zinc-500" /> Nothing here yet.
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((p) => (
            <div key={p.id} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="flex gap-4">
                {p.media[0] ? (
                  <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg border border-zinc-700">
                    {(p.media[0].url ?? p.media[0].poster)
                      ? <img src={(p.media[0].url ?? p.media[0].poster) as string} alt={p.media[0].alt ?? ''} className="h-full w-full object-cover" />
                      : <div className="flex h-full w-full items-center justify-center bg-zinc-950"><Loader2 className="h-4 w-4 animate-spin text-zinc-500" /></div>}
                    {p.media[0].kind === 'video' && <Film className="absolute left-1 top-1 h-3.5 w-3.5 text-white drop-shadow" aria-label="Video" />}
                    {p.media.length > 1 && <span className="absolute right-1 top-1 rounded bg-zinc-950/80 px-1 text-[10px] text-zinc-200">+{p.media.length - 1}</span>}
                  </div>
                ) : <div className="h-20 w-20 shrink-0 rounded-lg border border-dashed border-zinc-700" />}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${BADGE[p.status] ?? BADGE.draft}`}>{STATUS_LABEL[p.status] ?? p.status}</span>
                    <span className="text-xs text-zinc-400">
                      {p.published_at ? `Posted ${new Date(p.published_at).toLocaleString()}`
                        : p.scheduled_at ? `Goes out ${new Date(p.scheduled_at).toLocaleString()}` : 'Not scheduled'}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap break-words text-sm text-zinc-200">{p.caption || <span className="text-zinc-500">No caption</span>}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {p.targets.map((t) => (
                      <span key={t.id} title={t.error ?? undefined}
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs ${BADGE[t.status] ?? BADGE.draft}`}>
                        <span className="capitalize">{t.platform}</span>
                        {t.handle && <span className="opacity-70">@{t.handle}</span>}
                        {t.permalink && (
                          <a href={t.permalink} target="_blank" rel="noopener noreferrer" aria-label={`Open on ${t.platform}`}>
                            <ExternalLink className="h-3 w-3" /></a>
                        )}
                        {t.metrics.likes != null && <span className="opacity-70">· {t.metrics.likes} likes</span>}
                      </span>
                    ))}
                  </div>
                  {p.targets.filter((t) => t.phase && PHASE_LABEL[t.phase]).map((t) => (
                    <p key={`phase-${t.id}`} className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-300">
                      <Loader2 className="h-3 w-3 animate-spin" /> {PHASE_LABEL[t.phase as string]}…
                    </p>
                  ))}
                  {p.targets.some((t) => t.error && t.status === 'failed') && (
                    <p className="mt-1.5 text-xs text-red-400">{p.targets.find((t) => t.error && t.status === 'failed')?.error}</p>
                  )}
                  {rescheduling?.id === p.id && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <input type="datetime-local" value={rescheduling.value} aria-label="New time"
                        onChange={(e) => setRescheduling({ id: p.id, value: e.target.value })}
                        className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100" />
                      <button type="button" onClick={() => reschedule(p, rescheduling.value)}
                        className="rounded-lg bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-900">Save</button>
                      <button type="button" onClick={() => setRescheduling(null)} className="text-xs text-zinc-400 hover:text-zinc-200">Cancel</button>
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  {busy === p.id && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
                  {RETRYABLE.includes(p.status) && busy !== p.id && (
                    <button type="button" onClick={() => postNow(p)} disabled={!p.targets.length}
                      title={p.status === 'partial' ? 'Retry where it failed' : p.status === 'failed' ? 'Try again' : 'Post now'}
                      className="rounded-lg border border-zinc-700 p-2 text-lime-400 hover:bg-zinc-800 disabled:opacity-40"><Send className="h-4 w-4" /></button>
                  )}
                  {EDITABLE.includes(p.status) && busy !== p.id && (
                    <>
                      <button type="button" title="Reschedule"
                        onClick={() => setRescheduling({ id: p.id, value: toLocalInput(p.scheduled_at ? new Date(p.scheduled_at) : new Date(Date.now() + 3_600_000)) })}
                        className="rounded-lg border border-zinc-700 p-2 text-zinc-300 hover:bg-zinc-800"><CalendarClock className="h-4 w-4" /></button>
                      {p.status !== 'draft' && (
                        <button type="button" onClick={() => cancel(p)} title="Cancel"
                          className="rounded-lg border border-zinc-700 p-2 text-zinc-400 hover:bg-zinc-800"><X className="h-4 w-4" /></button>
                      )}
                    </>
                  )}
                  {[...EDITABLE, 'cancelled'].includes(p.status) && busy !== p.id && (
                    <button type="button" onClick={() => remove(p)} title="Delete"
                      className="rounded-lg border border-zinc-700 p-2 text-zinc-500 hover:bg-zinc-800 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
