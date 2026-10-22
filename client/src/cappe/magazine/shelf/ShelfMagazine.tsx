import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Check, ExternalLink, Loader2, Plus } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeReaderMagazine, CappeReaderStoryCard } from '../../types'
import { priceLabel } from '../settings/price'
import { setFollowing } from './follow'
import { readerPaths } from './readerPaths'
import StoryCard from './StoryCard'
import { changeSubscription, compState, startCheckout, subscriptionState } from './subscription'

// After Stripe sends the reader back, the subscription lands by webhook a
// moment later: look again this many times, this far apart.
const SETTLE_TRIES = 5
const SETTLE_MS = 2000

/** `/cappe/reader/m/:slug` — one magazine: the reader's subscription (or a
 *  way to start one), a Follow button, and its stories, newest first.
 *  `?follow=1` (the magazine's own "Follow it there" link) follows on arrival. */
export default function ShelfMagazine() {
  const { slug = '' } = useParams<{ slug: string }>()
  const [params, setParams] = useSearchParams()
  const justSubscribed = params.get('subscribed') === '1'
  const followOnArrival = params.get('follow') === '1'
  const arrivalFollowed = useRef<string | null>(null)
  // Bumped to load the magazine again (after a change, or while a new
  // subscription settles); each answer remembers which load it is for.
  const [version, setVersion] = useState(0)
  const key = `${slug}|${version}`
  const [result, setResult] = useState<{ key: string; mag?: CappeReaderMagazine; error?: string } | null>(null)
  const [more, setMore] = useState<{ slug: string; stories: CappeReaderStoryCard[]; page: number; hasMore: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeReaderMagazine>(`/reader/magazines/${encodeURIComponent(slug)}`)
      .then((m) => { if (live) setResult({ key, mag: m }) })
      .catch((e) => { if (live) setResult({ key, error: e instanceof Error ? e.message : 'Could not open this magazine' }) })
    return () => { live = false }
  }, [slug, key])

  // Shown until the next answer arrives, so a reload doesn't blank the page.
  const [shown, setShown] = useState<{ slug: string; mag: CappeReaderMagazine } | null>(null)
  if (result?.mag && result.key === key && shown?.mag !== result.mag) setShown({ slug, mag: result.mag })
  const mag = shown?.slug === slug ? shown.mag : null
  const error = result?.key === key ? result.error ?? null : null

  useEffect(() => {
    if (!justSubscribed || !mag || mag.has_access || version >= SETTLE_TRIES) return
    const t = window.setTimeout(() => setVersion((v) => v + 1), SETTLE_MS)
    return () => window.clearTimeout(t)
  }, [justSubscribed, mag, version])

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setActionError(null)
    try {
      await fn()
      setVersion((v) => v + 1)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'That didn’t work. Try again.')
    } finally {
      setBusy(false)
    }
  }

  // Once per magazine, and the request leaves the address so a reload or a
  // later unfollow doesn't follow again.
  useEffect(() => {
    if (!followOnArrival || !mag || arrivalFollowed.current === slug) return
    arrivalFollowed.current = slug
    setParams((p) => { p.delete('follow'); return p }, { replace: true })
    if (mag.following) return
    setFollowing(slug, true)
      .then(() => setVersion((v) => v + 1))
      .catch((e) => setActionError(e instanceof Error ? e.message : 'Could not follow. Try again.'))
  })

  async function loadMore() {
    if (!mag) return
    const page = (more?.slug === slug ? more.page : mag.page) + 1
    setBusy(true)
    try {
      const next = await cappeApi.get<CappeReaderMagazine>(`/reader/magazines/${encodeURIComponent(slug)}?page=${page}`)
      setMore((m) => ({ slug, stories: [...(m?.slug === slug ? m.stories : []), ...next.stories], page, hasMore: next.has_more }))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not load more stories')
    } finally {
      setBusy(false)
    }
  }

  const extra = more?.slug === slug ? more : null
  const stories = mag ? [...mag.stories, ...(extra?.stories ?? [])] : []
  const hasMore = extra ? extra.hasMore : !!mag?.has_more

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      <Link to={readerPaths.home} className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> My magazines
      </Link>
      {error && !mag && <p role="alert" className="mt-6 text-sm text-red-400">{error}</p>}
      {!mag && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>}
      {mag && (
        <>
          <header className="mt-4 border-b border-zinc-800 pb-5" style={mag.accent ? { borderBottomColor: mag.accent } : undefined}>
            <div className="flex flex-wrap items-start gap-3">
              <h1 className="font-serif text-3xl text-zinc-50">{mag.name}</h1>
              <button type="button" disabled={busy} aria-pressed={mag.following}
                className={`${mag.following ? ui.btnGhost : ui.btnPrimary} ml-auto`}
                onClick={() => act(() => setFollowing(slug, !mag.following))}>
                {mag.following ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                {mag.following ? 'Following' : 'Follow'}
              </button>
            </div>
            {mag.tagline && <p className="mt-1 text-zinc-400">{mag.tagline}</p>}
            {mag.origin && (
              <a href={mag.origin} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
                {mag.origin.replace(/^https?:\/\//, '')} <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </header>

          <section className={`${ui.card} mt-6 p-5`} aria-label="Your subscription">
            {justSubscribed && !mag.has_access && (
              <p role="status" className="mb-3 text-sm text-zinc-300">
                {version < SETTLE_TRIES ? 'Finishing your subscription…' : 'Your payment went through. Your subscription can take a minute to show: refresh the page shortly.'}
              </p>
            )}
            {mag.subscription ? (
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="font-medium text-zinc-100">Subscribed · {priceLabel(mag.subscription.total_cents)} a month</p>
                  <p className="text-sm text-zinc-400">{subscriptionState(mag.subscription)}</p>
                </div>
                <div className="ml-auto">
                  {mag.subscription.cancel_at_period_end ? (
                    mag.taking_subscribers && (
                      <button type="button" disabled={busy} className={ui.btnGhost}
                        onClick={() => act(() => changeSubscription(mag.subscription!.id, false))}>Keep it</button>
                    )
                  ) : (
                    <button type="button" disabled={busy} className={ui.btnGhost}
                      onClick={() => { if (window.confirm('Cancel? You keep reading until the month you paid for ends.')) void act(() => changeSubscription(mag.subscription!.id, true)) }}>
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            ) : mag.comp ? (
              <p className="text-sm text-zinc-300">{compState(mag.comp)}. Every story is open to you.</p>
            ) : mag.taking_subscribers && mag.price_cents ? (
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="font-medium text-zinc-100">Subscribe for {priceLabel(mag.price_cents)} a month</p>
                  <p className="text-sm text-zinc-400">{mag.paid_pitch || 'Read every story. Cancel any time.'}</p>
                </div>
                <button type="button" disabled={busy} className={`${ui.btnPrimary} ml-auto`} onClick={() => act(() => startCheckout(slug))}>
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />} Subscribe
                </button>
              </div>
            ) : (
              <p className="text-sm text-zinc-400">This magazine isn’t taking subscriptions. Its free stories are below.</p>
            )}
            {actionError && <p role="alert" className="mt-3 text-sm text-red-400">{actionError}</p>}
          </section>

          {stories.length === 0 ? (
            <p className="mt-8 text-sm text-zinc-500">No stories yet.</p>
          ) : (
            <ul className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {stories.map((s) => (
                <li key={s.slug}><StoryCard slug={slug} story={s} locked={s.access === 'paid' && !mag.has_access} /></li>
              ))}
            </ul>
          )}
          {hasMore && (
            <div className="mt-6 text-center">
              <button type="button" disabled={busy} className={ui.btnGhost} onClick={loadMore}>More stories</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
