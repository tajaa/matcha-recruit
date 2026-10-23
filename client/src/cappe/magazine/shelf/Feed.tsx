import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Newspaper } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeFeedStory, CappeReaderFeed } from '../../types'
import { readerMagazinePath, readerPaths } from './readerPaths'
import StoryCard from './StoryCard'

/** `/cappe/reader/feed` — new stories from the magazines this account
 *  follows, newest first. */
export default function Feed() {
  const [stories, setStories] = useState<CappeFeedStory[] | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeReaderFeed>('/reader/feed')
      .then((d) => { if (live) { setStories(d.stories); setHasMore(d.has_more) } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load your feed') })
    return () => { live = false }
  }, [])

  async function loadMore() {
    setBusy(true)
    try {
      const next = await cappeApi.get<CappeReaderFeed>(`/reader/feed?page=${page + 1}`)
      // A story published meanwhile shifts the pages by one: never list it twice.
      setStories((s) => {
        const seen = new Set((s ?? []).map((x) => `${x.magazine.slug}/${x.slug}`))
        return [...(s ?? []), ...next.stories.filter((x) => !seen.has(`${x.magazine.slug}/${x.slug}`))]
      })
      setPage(next.page)
      setHasMore(next.has_more)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load more stories')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      <h1 className={ui.heading}>Feed</h1>
      <p className={`mt-1 ${ui.subtitle}`}>New stories from the magazines you follow.</p>
      {error && <p role="alert" className="mt-6 text-sm text-red-400">{error}</p>}
      {stories === null && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>}
      {stories && stories.length === 0 && (
        <div className={`${ui.card} mt-6 p-6 text-sm text-zinc-400`}>
          <Newspaper className="mb-2 h-5 w-5 text-zinc-500" />
          Nothing here yet. Open a magazine from <Link to={readerPaths.home} className={ui.accentText}>My magazines</Link> and
          press Follow, and its new stories will show up here.
        </div>
      )}
      {stories && stories.length > 0 && (
        <ul className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {stories.map((s) => (
            <li key={`${s.magazine.slug}/${s.slug}`}>
              <Link to={readerMagazinePath(s.magazine.slug)}
                className="mb-2 inline-flex items-center gap-2 text-xs font-medium text-zinc-400 hover:text-zinc-100">
                <span className="h-2 w-2 rounded-full bg-zinc-600" style={s.magazine.accent ? { background: s.magazine.accent } : undefined} />
                {s.magazine.name}
              </Link>
              <StoryCard slug={s.magazine.slug} story={s} />
            </li>
          ))}
        </ul>
      )}
      {hasMore && (
        <div className="mt-6 text-center">
          <button type="button" disabled={busy} className={ui.btnGhost} onClick={loadMore}>More stories</button>
        </div>
      )}
    </div>
  )
}
