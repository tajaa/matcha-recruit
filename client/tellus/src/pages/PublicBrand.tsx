import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Heart, ImageIcon, Star, Video } from 'lucide-react'
import { tellusPublicGet } from '../api/tellusClient'
import { Button, Card, Empty, Spinner } from '../components/ui'
import type { PublicBrandPage, PublicReview } from '../api/types'

const PAGE_SIZE = 20

function ReviewCard({ review }: { review: PublicReview }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex gap-0.5">
            {[1, 2, 3, 4, 5].map((n) => (
              <Star key={n} className={`h-3.5 w-3.5 ${n <= review.rating ? 'fill-tu-accent text-tu-accent' : 'text-tu-border'}`} />
            ))}
          </div>
          <p className="mt-1 text-sm font-semibold">{review.reviewer_name}{review.store_name ? ` · ${review.store_name}` : ''}</p>
        </div>
        <div className="flex items-center gap-2">
          {review.hearted && <Heart className="h-4 w-4 fill-tu-accent text-tu-accent" />}
          <span className="whitespace-nowrap text-xs text-tu-faint">{new Date(review.publish_at).toLocaleDateString()}</span>
        </div>
      </div>

      {review.title && <h3 className="mt-2 text-sm font-semibold">{review.title}</h3>}
      {review.description && <p className="mt-1 whitespace-pre-wrap text-sm text-tu-dim">{review.description}</p>}

      {review.media.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {review.media.map((m) => (
            <a key={m.id} href={m.url ?? '#'} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 rounded-md border border-tu-border px-2 py-1 text-xs text-tu-dim hover:border-tu-accent">
              {m.media_type === 'video' ? <Video className="h-3.5 w-3.5" /> : <ImageIcon className="h-3.5 w-3.5" />}
              {m.media_type}
            </a>
          ))}
        </div>
      )}

      {review.brand_reply && (
        <div className="mt-2.5 rounded-md border border-tu-border bg-tu-panel2 px-2.5 py-1.5">
          <span className="text-xs font-medium text-tu-dim">Response from the business</span>
          <p className="mt-1 whitespace-pre-wrap text-sm text-tu-text">{review.brand_reply}</p>
        </div>
      )}
    </Card>
  )
}

export default function PublicBrand() {
  const { slug = '' } = useParams()
  const [page, setPage] = useState<PublicBrandPage | null>(null)
  const [reviews, setReviews] = useState<PublicReview[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    tellusPublicGet<PublicBrandPage>(`/b/${slug}?limit=${PAGE_SIZE}&offset=0`)
      .then((p) => { setPage(p); setReviews(p.reviews) })
      .catch((e) => setErr(e instanceof Error ? e.message : 'This page is unavailable.'))
      .finally(() => setLoading(false))
  }, [slug])

  async function loadMore() {
    if (!page) return
    setLoadingMore(true)
    try {
      const next = await tellusPublicGet<PublicBrandPage>(`/b/${slug}?limit=${PAGE_SIZE}&offset=${reviews.length}`)
      // The underlying `publish_at <= NOW()` window grows between fetches, so
      // a review crossing the 48h boundary can shift the offset and reappear
      // in the next page — dedupe by id rather than trusting offset alone.
      setReviews((r) => {
        const seen = new Set(r.map((x) => x.id))
        return [...r, ...next.reviews.filter((x) => !seen.has(x.id))]
      })
    } finally {
      setLoadingMore(false)
    }
  }

  if (loading) return <div className="min-h-screen"><Spinner /></div>
  if (err || !page) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-lg font-bold">Page unavailable</h1>
        <p className="mt-2 text-sm text-tu-dim">{err}</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-6 text-center">
        {page.logo_url && <img src={page.logo_url} alt="" className="mx-auto mb-3 h-14 w-14 rounded-xl object-cover" />}
        <h1 className="text-2xl font-bold">{page.brand_name}</h1>
        {page.avg_rating != null && (
          <div className="mt-2 flex items-center justify-center gap-1.5">
            <div className="flex gap-0.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <Star key={n} className={`h-4 w-4 ${n <= Math.round(page.avg_rating!) ? 'fill-tu-accent text-tu-accent' : 'text-tu-border'}`} />
              ))}
            </div>
            <span className="text-sm text-tu-dim">{page.avg_rating.toFixed(1)} · {page.review_count} review{page.review_count === 1 ? '' : 's'}</span>
          </div>
        )}
      </div>

      {reviews.length === 0 ? (
        <Empty>No public reviews yet.</Empty>
      ) : (
        <div className="space-y-3">
          {reviews.map((r) => <ReviewCard key={r.id} review={r} />)}
        </div>
      )}

      {reviews.length < page.total && (
        <div className="mt-4 text-center">
          <Button variant="soft" loading={loadingMore} onClick={loadMore}>Load more</Button>
        </div>
      )}

      <div className="mt-10 border-t border-tu-border pt-6 text-center">
        <p className="text-sm text-tu-dim">Powered by Tell-Us — get rewarded for feedback.</p>
        <Link to="/tellus-app" className="mt-1 inline-block text-sm font-semibold text-tu-accent hover:underline">Learn more →</Link>
      </div>
    </div>
  )
}
