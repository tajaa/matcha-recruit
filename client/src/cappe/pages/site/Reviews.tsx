import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Star, Check, EyeOff, Trash2 } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import type { CappeReview, CappeReviewSubmissions } from '../../types'

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

const WHO: { value: CappeReviewSubmissions; label: string }[] = [
  { value: 'anyone', label: 'Anyone' },
  { value: 'buyers', label: 'Only customers, from their order page' },
  { value: 'off', label: 'Nobody (reviews closed)' },
]

export default function Reviews() {
  const { siteId } = useParams<{ siteId: string }>()
  const [reviews, setReviews] = useState<CappeReview[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<CappeReview['status']>('pending')
  const [busy, setBusy] = useState<string | null>(null)
  const [who, setWho] = useState<CappeReviewSubmissions | null>(null)
  const [replying, setReplying] = useState<{ id: string; text: string } | null>(null)

  useEffect(() => {
    // A failed load used to leave the error AND an endless spinner on screen.
    cappeApi.get<CappeReview[]>(`/sites/${siteId}/reviews`)
      .then((r) => { setReviews(r); setLoadError(null) })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Failed to load reviews'))
    cappeApi.get<{ submissions: CappeReviewSubmissions }>(`/sites/${siteId}/review-settings`)
      .then((r) => setWho(r.submissions)).catch(() => setWho(null))
  }, [siteId, attempt])

  async function changeWho(value: CappeReviewSubmissions) {
    const before = who
    setWho(value); setError(null)
    try {
      await cappeApi.put(`/sites/${siteId}/review-settings`, { submissions: value })
    } catch (e) {
      setWho(before)
      setError(e instanceof Error ? e.message : 'Could not change who can post reviews')
    }
  }

  async function saveReply(r: CappeReview, text: string) {
    setBusy(r.id); setError(null)
    try {
      const updated = await cappeApi.put<CappeReview>(`/sites/${siteId}/reviews/${r.id}/reply`, { reply: text.trim() || null })
      setReviews((list) => (list || []).map((x) => (x.id === r.id ? updated : x)))
      setReplying(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the reply')
    } finally {
      setBusy(null)
    }
  }

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
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
      {who && (
        <label className="mb-4 flex flex-wrap items-center gap-2 text-sm text-zinc-300">
          Who can post reviews
          <select value={who} onChange={(e) => changeWho(e.target.value as CappeReviewSubmissions)}
            className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100">
            {WHO.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
          <span className="text-xs text-zinc-500">Reviews from an order page are marked “Verified purchase”.</span>
        </label>
      )}

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

      {loadError ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
          Couldn’t load your reviews. {loadError}
          <button onClick={() => { setLoadError(null); setAttempt((n) => n + 1) }} className="rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium hover:bg-red-500/10">Try again</button>
        </div>
      ) : reviews === null ? (
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
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-zinc-100">{r.author_name}</span>
                    <Stars n={r.rating} />
                    {r.verified && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-400">Verified purchase</span>}
                  </div>
                  {r.product_name && <div className="mt-1 text-xs text-zinc-400">About {r.product_name}</div>}
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm text-zinc-300">{r.body}</p>
                  <div className="mt-2 text-xs text-zinc-500">{new Date(r.created_at).toLocaleDateString()}</div>
                  {replying?.id === r.id ? (
                    <div className="mt-3 space-y-2">
                      <textarea value={replying.text} onChange={(e) => setReplying({ id: r.id, text: e.target.value })}
                        rows={2} maxLength={2000} aria-label="Your reply" placeholder="Thanks for the kind words!"
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-lime-500" />
                      <div className="flex gap-2">
                        <button onClick={() => saveReply(r, replying.text)} disabled={busy === r.id}
                          className="rounded-lg bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-900 disabled:opacity-60">Save reply</button>
                        <button onClick={() => setReplying(null)} className="text-xs text-zinc-400 hover:text-zinc-200">Cancel</button>
                      </div>
                    </div>
                  ) : r.owner_reply ? (
                    <div className="mt-3 border-l-2 border-zinc-700 pl-3 text-sm text-zinc-400">
                      <span className="font-medium text-zinc-300">Your reply:</span> {r.owner_reply}{' '}
                      <button onClick={() => setReplying({ id: r.id, text: r.owner_reply || '' })} className="text-xs text-lime-400 hover:underline">Edit</button>
                    </div>
                  ) : (
                    <button onClick={() => setReplying({ id: r.id, text: '' })} className="mt-2 text-xs text-lime-400 hover:underline">Reply publicly</button>
                  )}
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
