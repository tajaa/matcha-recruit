import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import type { CappeReaderStory } from '../../types'
import BookFrame from '../reader/BookFrame'
import { readerMagazinePath, readerStoryPath } from './readerPaths'

const STORY = /^\/stories\/([^/?#]+)\/?$/
// A story made in the Studio links to its Text view (its words, read down).
const TEXT = /^\/stories\/([^/?#]+)\/text\/?$/
const HOME = (path: string) => path === '/' || path === '/magazine'

/** `/cappe/reader/m/:slug/:story` — a story as its magazine prints it, pages
 *  turning left and right. The server puts the whole story in for a reader
 *  with paid access. Scripts don't run in the frame, so its pages are turned
 *  and its links followed from out here (`BookFrame`): another story opens
 *  here, the magazine's own pages on its site in a new tab, and the paywall
 *  gets a button that opens the magazine's page here, where they subscribe. */
export default function ShelfStory() {
  const { slug = '', story = '' } = useParams<{ slug: string; story: string }>()
  const navigate = useNavigate()
  const asText = useSearchParams()[0].get('view') === 'text'
  const key = `${slug}|${story}|${asText}`
  const [result, setResult] = useState<{ key: string; data?: CappeReaderStory; error?: string } | null>(null)

  useEffect(() => {
    let live = true
    cappeApi.get<CappeReaderStory>(`/reader/magazines/${encodeURIComponent(slug)}/stories/${encodeURIComponent(story)}${asText ? '?view=text' : ''}`)
      .then((d) => { if (live) setResult({ key, data: d }) })
      .catch((e) => { if (live) setResult({ key, error: e instanceof Error ? e.message : 'Could not open this story' }) })
    return () => { live = false }
  }, [slug, story, key, asText])

  const current = result?.key === key ? result : null
  const data = current?.data ?? null
  const error = current?.error ?? null

  const prepare = (doc: Document) => {
    // No scripts run in this frame: the email follow box couldn't send, and
    // the dashboard has its own Follow button and reader links.
    doc.querySelectorAll('[data-mz-alt], #mz-follow').forEach((el) => el.remove())
    const actions = doc.querySelector('[data-mz-actions]')
    if (actions) {
      actions.textContent = ''
      const button = doc.createElement('a')
      button.setAttribute('href', '/magazine')
      button.className = 'mz-paywall__btn mz-paywall__btn--solid'
      button.textContent = 'Subscribe to read on'
      actions.appendChild(button)
    }
    // The magazine's other pages (a topic, About) open on its own site.
    const origin = doc.querySelector('link[rel="canonical"]')?.getAttribute('href')?.match(/^https:\/\/[^/]+/)?.[0]
    doc.querySelectorAll('a[href^="/"]').forEach((a) => {
      const href = a.getAttribute('href') || ''
      if (STORY.test(href) || TEXT.test(href) || HOME(href)) return
      if (origin) a.setAttribute('href', `${origin}${href}`)
      else a.removeAttribute('href')
    })
  }

  const follow = (path: string) => {
    const toStory = path.match(STORY), toText = path.match(TEXT)
    if (toStory) navigate(readerStoryPath(slug, decodeURIComponent(toStory[1])))
    else if (toText) navigate(`${readerStoryPath(slug, decodeURIComponent(toText[1]))}?view=text`)
    else if (HOME(path)) navigate(readerMagazinePath(slug))
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-2 text-sm">
        <Link to={readerMagazinePath(slug)} className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-100">
          <ArrowLeft className="h-4 w-4" /> All stories
        </Link>
        {data && <span className="truncate text-zinc-500">{data.title}</span>}
      </div>
      {error && <p role="alert" className="p-6 text-sm text-red-400">{error}</p>}
      {!data && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>}
      {data && (
        <BookFrame html={data.html} title={data.title || 'Story'} prepare={prepare} onLink={follow} openExternal keys
          className="flex-1" style={{ minHeight: '80vh' }} />
      )}
    </div>
  )
}
