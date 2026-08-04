import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Heart, MessageCircle, Star } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, Empty, ErrorText, Spinner, Textarea } from '../../components/ui'
import { DmThreadPanel } from '../../components/DmThreadPanel'
import type { MyReview } from '../../api/types'

function hoursLeft(publishAt: string): number {
  return Math.max(0, Math.ceil((Date.parse(publishAt) - Date.now()) / 3_600_000))
}

function StateChip({ review }: { review: MyReview }) {
  if (review.review_state === 'held') return <Chip>publishes in {hoursLeft(review.publish_at)}h</Chip>
  if (review.review_state === 'published') return <Chip tone="positive">public review</Chip>
  return <Chip>withdrawn</Chip>
}

function ReviewCard({ review, onChange }: { review: MyReview; onChange: () => void }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(review.title ?? '')
  const [description, setDescription] = useState(review.description ?? '')
  const [rating, setRating] = useState(review.rating ?? 0)
  const [showDm, setShowDm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function save() {
    setBusy(true); setErr('')
    try {
      await tellusApi.patch(`/me/reviews/${review.id}`, { title: title || null, description, rating: rating || null })
      setEditing(false)
      onChange()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  async function withdraw() {
    if (!confirm('Withdraw this review? It will come down from the public page.')) return
    setBusy(true)
    try { await tellusApi.post(`/me/reviews/${review.id}/withdraw`); onChange() } finally { setBusy(false) }
  }

  const withdrawn = review.review_state === 'withdrawn'

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StateChip review={review} />
            {review.hearted && (
              <span className="inline-flex items-center gap-0.5 text-xs text-tu-accent">
                <Heart className="h-3 w-3 fill-tu-accent" /> hearted
              </span>
            )}
            {review.points_awarded > 0 && <Chip tone="positive">+{review.points_awarded} pts</Chip>}
          </div>
          <h3 className="mt-1 text-sm font-semibold">{review.brand_name}{review.store_name ? ` — ${review.store_name}` : ''}</h3>
          {review.rating != null && (
            <div className="mt-0.5 flex gap-0.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <Star key={n} className={`h-3.5 w-3.5 ${n <= review.rating! ? 'fill-tu-accent text-tu-accent' : 'text-tu-border'}`} />
              ))}
            </div>
          )}
        </div>
        {review.review_state === 'published' && (
          <a href={`/tellus/b/${review.brand_slug}`} target="_blank" rel="noreferrer"
            className="flex shrink-0 items-center gap-1 text-xs text-tu-accent hover:underline">
            View <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {!editing ? (
        <>
          {review.title && <p className="mt-2 text-sm font-medium">{review.title}</p>}
          <p className="mt-1 whitespace-pre-wrap text-sm text-tu-dim">{review.description}</p>
        </>
      ) : (
        <div className="mt-2 space-y-2">
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" onClick={() => setRating(n)}>
                <Star className={`h-6 w-6 ${n <= rating ? 'fill-tu-accent text-tu-accent' : 'text-tu-border'}`} />
              </button>
            ))}
          </div>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)"
            className="w-full rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2 text-sm text-tu-text placeholder:text-tu-faint focus:border-tu-accent focus:outline-none" />
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} />
          <ErrorText>{err}</ErrorText>
          <div className="flex gap-2">
            <Button size="sm" loading={busy} onClick={save}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {review.brand_public_reply && (
        <div className="mt-2.5 rounded-md border border-tu-border bg-tu-panel2 px-2.5 py-1.5">
          <span className="text-xs font-medium text-tu-dim">Reply from {review.brand_name}</span>
          <p className="mt-1 whitespace-pre-wrap text-sm text-tu-text">{review.brand_public_reply}</p>
        </div>
      )}

      {showDm && <div className="mt-2.5"><DmThreadPanel reportId={review.id} isBrand={false} /></div>}

      {!editing && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {!withdrawn && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Edit</Button>}
          {review.dm_thread_id && (
            <Button size="sm" variant="ghost" onClick={() => setShowDm((s) => !s)}>
              <MessageCircle className="h-3.5 w-3.5" /> Messages
            </Button>
          )}
          {!withdrawn && (
            <Button size="sm" variant="ghost" loading={busy} onClick={withdraw} className="ml-auto text-tu-bad">Withdraw</Button>
          )}
        </div>
      )}
    </Card>
  )
}

export default function MyReviews() {
  const [reviews, setReviews] = useState<MyReview[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    const r = await tellusApi.get<MyReview[]>('/me/reviews')
    setReviews(r)
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  if (loading) return <Spinner />

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">My reviews</h1>
        <p className="mt-0.5 text-sm text-tu-dim">Reviews you've posted publicly — edit or withdraw any time.</p>
      </div>

      {reviews.length === 0 ? (
        <Empty>You haven't posted a public review yet — toggle "Post as a public review" next time you give feedback.</Empty>
      ) : (
        <div className="space-y-3">
          {reviews.map((r) => <ReviewCard key={r.id} review={r} onChange={load} />)}
        </div>
      )}
    </div>
  )
}
