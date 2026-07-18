import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Star, Check, EyeOff, Trash2 } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import type { CappeReview } from '../../types'

const TABS: { key: CappeReview['status']; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'hidden', label: 'Hidden' },
]

function Stars({ n }: { n: number | null }) {
  return (
    <span className="text-amber-400" aria-label={`${n || 0} stars`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star key={i} className={`inline h-3.5 w-3.5 ${i < (n || 0) ? 'fill-amber-400' : 'fill-none text-zinc-600'}`} />
      ))}
    </span>
  )
}

export default function Reviews() {
  const { siteId } = useParams<{ siteId: string }>()
  const [reviews, setReviews] = useState<CappeReview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<CappeReview['status']>('pending')
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    cappeApi.get<CappeReview[]>(`/sites/${siteId}/reviews`)
      .then(setReviews)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load reviews'))
  }, [siteId])

  async function moderate(r: CappeReview, status: CappeReview['status']) {
    setBusy(r.id)
    setError(null)
    try {
      const updated = await cappeApi.patch<CappeReview>(`/sites/${siteId}/reviews/${r.id}`, { status })
      setReviews((list) => (list || []).map((x) => (x.id === r.id ? updated : x)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update review')
    } finally {
      setBusy(null)
    }
  }

  async function remove(r: CappeReview) {
    if (!confirm('Delete this review permanently?')) return
    setBusy(r.id)
    try {
      await cappeApi.delete(`/sites/${siteId}/reviews/${r.id}`)
      setReviews((list) => (list || []).filter((x) => x.id !== r.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete review')
    } finally {
      setBusy(null)
    }
  }

  const counts = (s: CappeReview['status']) => (reviews || []).filter((r) => r.status === s).length
  const shown = (reviews || []).filter((r) => r.status === tab)

  return (
    <SurfaceShell title="Reviews" subtitle="Approve customer reviews to show them on your site.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <div className="mb-4 flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${
              tab === t.key ? 'bg-lime-400 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t.label} <span className="opacity-70">{counts(t.key)}</span>
          </button>
        ))}
      </div>

      {reviews === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : shown.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Star className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No {tab} reviews.
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((r) => (
            <div key={r.id} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-zinc-100">{r.author_name}</span>
                    <Stars n={r.rating} />
                  </div>
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm text-zinc-300">{r.body}</p>
                  <div className="mt-2 text-xs text-zinc-500">{new Date(r.created_at).toLocaleDateString()}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {r.status !== 'approved' && (
                    <button
                      onClick={() => moderate(r, 'approved')}
                      disabled={busy === r.id}
                      title="Approve"
                      className="rounded-lg border border-zinc-700 p-2 text-lime-400 hover:bg-zinc-800 disabled:opacity-50"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                  )}
                  {r.status !== 'hidden' && (
                    <button
                      onClick={() => moderate(r, 'hidden')}
                      disabled={busy === r.id}
                      title="Hide"
                      className="rounded-lg border border-zinc-700 p-2 text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
                    >
                      <EyeOff className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    onClick={() => remove(r)}
                    disabled={busy === r.id}
                    title="Delete"
                    className="rounded-lg border border-zinc-700 p-2 text-zinc-500 hover:bg-zinc-800 hover:text-red-400 disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
