import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Heart, ImageIcon, Star, Video } from 'lucide-react'
import { tellusApi, tellusPublicGet } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, Empty, ErrorText, Spinner } from '../components/ui'
import type { ClaimResponse, MyClaim, PublicBrandPage, PublicReview } from '../api/types'

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

      {review.answers.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {review.answers.map((a) => (
            <div key={a.id}>
              <p className="text-xs font-medium text-tu-dim">{a.prompt_text}</p>
              <p className="whitespace-pre-wrap text-sm">{a.answer}</p>
            </div>
          ))}
        </div>
      )}

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
  const { account } = useAccount()
  const [page, setPage] = useState<PublicBrandPage | null>(null)
  const [reviews, setReviews] = useState<PublicReview[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [err, setErr] = useState('')
  const [confirmingClaim, setConfirmingClaim] = useState(false)
  const [claiming, setClaiming] = useState(false)
  const [claimErr, setClaimErr] = useState('')
  const [myClaim, setMyClaim] = useState<MyClaim | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [olderReviews, setOlderReviews] = useState<PublicReview[] | null>(null)   // null = collapsed
  const [olderTotal, setOlderTotal] = useState(0)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [feedErr, setFeedErr] = useState('')

  useEffect(() => {
    if (!account) { setMyClaim(null); return }
    tellusApi.get<MyClaim | null>('/me/claim').then(setMyClaim).catch(() => {})
  }, [account, slug])

  async function claimBrand() {
    setClaiming(true); setClaimErr('')
    try {
      const res = await tellusApi.post<ClaimResponse>(`/b/${slug}/claim`)
      // Files a PENDING claim only — account_type and ownership are untouched
      // until an admin approves it, so there's no refreshAccount/redirect here.
      setMyClaim({
        id: res.claim_id, brand_id: '', brand_slug: slug, brand_name: page?.brand_name ?? '',
        status: 'pending', created_at: new Date().toISOString(), decision_note: null,
      })
      setConfirmingClaim(false)
    } catch (e) {
      setClaimErr(e instanceof Error ? e.message : 'Could not claim this business')
    } finally {
      setClaiming(false)
    }
  }

  async function cancelClaim() {
    setCancelling(true)
    try {
      await tellusApi.post('/me/claim/cancel')
      setMyClaim(null)
    } catch (e) {
      setClaimErr(e instanceof Error ? e.message : 'Could not cancel this claim')
    } finally {
      setCancelling(false)
    }
  }

  useEffect(() => {
    tellusPublicGet<PublicBrandPage>(`/b/${slug}?limit=${PAGE_SIZE}&offset=0`)
      .then((p) => { setPage(p); setReviews(p.reviews) })
      .catch((e) => setErr(e instanceof Error ? e.message : 'This page is unavailable.'))
      .finally(() => setLoading(false))
  }, [slug])

  async function loadMore() {
    if (!page) return
    setLoadingMore(true); setFeedErr('')
    try {
      const next = await tellusPublicGet<PublicBrandPage>(`/b/${slug}?limit=${PAGE_SIZE}&offset=${reviews.length}`)
      // The underlying `publish_at <= NOW()` window grows between fetches, so
      // a review crossing the 48h boundary can shift the offset and reappear
      // in the next page — dedupe by id rather than trusting offset alone.
      setReviews((r) => {
        const seen = new Set(r.map((x) => x.id))
        return [...r, ...next.reviews.filter((x) => !seen.has(x.id))]
      })
    } catch (e) {
      setFeedErr(e instanceof Error ? e.message : 'Could not load more reviews.')
    } finally {
      setLoadingMore(false)
    }
  }

  async function loadOlder() {
    setLoadingOlder(true); setFeedErr('')
    try {
      const offset = olderReviews?.length ?? 0
      const res = await tellusPublicGet<PublicBrandPage>(`/b/${slug}?scope=older&limit=${PAGE_SIZE}&offset=${offset}`)
      setOlderTotal(res.older_count)
      setOlderReviews((prev) => {
        // Same dedupe rationale as loadMore — publish_at windows can shift results between fetches.
        const seen = new Set((prev ?? []).map((x) => x.id))
        return [...(prev ?? []), ...res.reviews.filter((x) => !seen.has(x.id))]
      })
    } catch (e) {
      setFeedErr(e instanceof Error ? e.message : 'Could not load more reviews.')
    } finally {
      setLoadingOlder(false)
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

  const pendingHere = myClaim?.status === 'pending' && myClaim.brand_slug === slug

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-6 text-center">
        {page.logo_url && <img src={page.logo_url} alt="" className="mx-auto mb-3 h-14 w-14 rounded-xl object-cover" />}
        <h1 className="text-2xl font-bold">{page.brand_name}</h1>
        {(page.address || page.city) && (
          <p className="mt-1 text-xs text-tu-faint">
            {[page.address, [page.city, page.state].filter(Boolean).join(', ')].filter(Boolean).join(' · ')}
          </p>
        )}
        {!page.claimed && (
          <span className="mt-1.5 inline-block rounded-full border border-tu-border px-2.5 py-0.5 text-xs text-tu-dim">Unclaimed</span>
        )}
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

        {/* "Write a review" is the intake flow — still gated on an active
            community link. Claim eligibility below is NOT gated on that link;
            an owner must always be able to claim even if the link was revoked. */}
        {!page.claimed && page.intake_token && (
          <div className="mt-3">
            <Link to={`/i/${page.intake_token}`} className="inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-4 py-2 text-sm font-semibold text-black transition hover:bg-tu-accent-soft">
              Write a review
            </Link>
          </div>
        )}

        {!page.claimed && (
          <div className="mt-3">
            {!account && (
              <p className="text-xs text-tu-faint">
                Are you the owner?{' '}
                <Link to={'/login?returnTo=' + encodeURIComponent('/b/' + slug)} className="font-semibold text-tu-accent hover:underline">
                  Claim this business →
                </Link>
              </p>
            )}

            {pendingHere && (
              <div className="mx-auto max-w-xs rounded-lg border border-tu-border bg-tu-panel p-3 text-left">
                <p className="text-xs font-semibold text-tu-dim">Claim pending review</p>
                <p className="mt-1 text-xs text-tu-faint">Our team reviews claims before ownership changes hands. We'll notify you once it's decided.</p>
                <ErrorText>{claimErr}</ErrorText>
                <Button size="sm" variant="ghost" className="mt-2" loading={cancelling} onClick={cancelClaim}>
                  Cancel claim
                </Button>
              </div>
            )}

            {account?.account_type === 'consumer' && !pendingHere && (
              <div>
                {confirmingClaim ? (
                  <div className="mx-auto max-w-xs rounded-lg border border-tu-border bg-tu-panel p-3 text-left">
                    <p className="text-xs text-tu-dim">
                      Claims are reviewed by our team. If approved, your account converts to a brand account — you'll lose access
                      to consumer features (points, rewards, your reviews) until support reverses it. You can cancel while the
                      claim is pending, or before paying.
                    </p>
                    <ErrorText>{claimErr}</ErrorText>
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" loading={claiming} onClick={claimBrand}>Confirm claim</Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmingClaim(false)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-tu-faint">
                    Are you the owner?{' '}
                    <button onClick={() => setConfirmingClaim(true)} className="font-semibold text-tu-accent hover:underline">
                      Claim this business →
                    </button>
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {reviews.length === 0 ? (
        <Empty>{page.older_count > 0 ? 'No reviews in the last 12 months.' : 'No public reviews yet.'}</Empty>
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

      {feedErr && <p className="mt-2 text-center text-xs text-tu-bad">{feedErr}</p>}

      {page.older_count > 0 && (
        <div className="mt-6">
          {olderReviews === null ? (
            <div className="text-center">
              <Button variant="ghost" loading={loadingOlder} onClick={loadOlder}>
                Show {page.older_count} older review{page.older_count === 1 ? '' : 's'}
              </Button>
            </div>
          ) : (
            <>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-tu-faint">
                Older reviews — not included in the rating
              </p>
              <div className="space-y-3">
                {olderReviews.map((r) => <ReviewCard key={r.id} review={r} />)}
              </div>
              {olderReviews.length < olderTotal && (
                <div className="mt-3 text-center">
                  <Button variant="soft" loading={loadingOlder} onClick={loadOlder}>Load more</Button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      <div className="mt-10 border-t border-tu-border pt-6 text-center">
        <p className="text-sm text-tu-dim">Powered by Tell-Us — get rewarded for feedback.</p>
        <Link to="/tellus-app" className="mt-1 inline-block text-sm font-semibold text-tu-accent hover:underline">Learn more →</Link>
      </div>
    </div>
  )
}
