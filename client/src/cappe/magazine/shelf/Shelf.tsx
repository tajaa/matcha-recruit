import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BookOpen, Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeShelfMagazine } from '../../types'
import { magazineSlugFrom, readerMagazinePath } from './readerPaths'
import StoryCard from './StoryCard'
import { changeSubscription, compState, subscriptionState } from './subscription'

/** `/cappe/reader` — every magazine the reader subscribes to or was given,
 *  with its latest story, and a way to open another by its address. */
export default function Shelf() {
  const [mags, setMags] = useState<CappeShelfMagazine[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // A magazine that is down has no page to open (it 404s), so its
  // subscription is stopped from here.
  const cancel = async (m: CappeShelfMagazine) => {
    if (!m.subscription || !window.confirm('Cancel? You keep reading until the month you paid for ends.')) return
    setBusy(true)
    try {
      const res = await changeSubscription(m.subscription.id, true)
      setMags((ms) => ms && ms.map((x) => (x.site_id === m.site_id && x.subscription
        ? { ...x, subscription: { ...x.subscription, cancel_at_period_end: res.cancel_at_period_end } } : x)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not cancel. Try again.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    let live = true
    cappeApi.get<{ magazines: CappeShelfMagazine[] }>('/reader/magazines')
      .then((d) => { if (live) setMags(d.magazines) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your magazines') })
    return () => { live = false }
  }, [])

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className={ui.heading}>My magazines</h1>
      <p className={`mt-1 ${ui.subtitle}`}>Everything you subscribe to, in one place.</p>
      {error && <p role="alert" className="mt-6 text-sm text-red-400">{error}</p>}
      {mags === null && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>}
      {mags && mags.length === 0 && (
        <div className={`${ui.card} mt-6 p-6 text-sm text-zinc-400`}>
          <BookOpen className="mb-2 h-5 w-5 text-zinc-500" />
          No magazines yet. Open one by its address below, or use “Open it on your dashboard” under any
          magazine’s subscriber-only story.
        </div>
      )}
      {mags && mags.length > 0 && (
        <ul className="mt-6 space-y-6">
          {mags.map((m) => (
            <li key={m.site_id} className={`${ui.card} overflow-hidden`}>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-zinc-800 px-5 py-4"
                style={m.accent ? { borderTop: `3px solid ${m.accent}` } : undefined}>
                <Link to={readerMagazinePath(m.slug)} className="font-serif text-xl text-zinc-50 hover:underline">{m.name}</Link>
                {m.tagline && <span className="text-sm text-zinc-500">{m.tagline}</span>}
                <span className="ml-auto text-xs text-zinc-400">
                  {m.subscription ? subscriptionState(m.subscription) : m.comp ? compState(m.comp) : ''}
                </span>
              </div>
              <div className="p-5">
                {!m.live && (
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="text-sm text-zinc-500">This magazine isn’t up right now.</p>
                    {m.subscription && !m.subscription.cancel_at_period_end && (
                      <button type="button" disabled={busy} className={`${ui.btnGhost} ml-auto`} onClick={() => void cancel(m)}>
                        Cancel subscription
                      </button>
                    )}
                  </div>
                )}
                {m.live && m.latest && (
                  <div className="max-w-sm">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Latest</p>
                    <StoryCard slug={m.slug} story={m.latest} />
                  </div>
                )}
                {m.live && !m.latest && <p className="text-sm text-zinc-500">No stories yet.</p>}
                {m.live && (
                  <Link to={readerMagazinePath(m.slug)} className={`mt-4 inline-block text-sm ${ui.accentText}`}>All stories and your subscription →</Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <OpenMagazine />
    </div>
  )
}

function OpenMagazine() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  function open(e: React.FormEvent) {
    e.preventDefault()
    const slug = magazineSlugFrom(text)
    if (!slug) {
      setError('Type the magazine’s address, like salt.gummfit.com.')
      return
    }
    navigate(readerMagazinePath(slug))
  }

  return (
    <form onSubmit={open} className={`${ui.card} mt-8 p-5`}>
      <label htmlFor="reader-open" className={ui.label}>Open a magazine</label>
      <div className="flex gap-2">
        <input id="reader-open" className={ui.input} placeholder="salt.gummfit.com" value={text}
          onChange={(e) => { setText(e.target.value); setError(null) }} />
        <button type="submit" className={ui.btnGhost}>Open</button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
    </form>
  )
}
