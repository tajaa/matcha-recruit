import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'

/** `sites/:siteId/magazine/view` (`?story=<id>`) — the magazine as a reader
 *  will see it, rendered by the server's own page code, for the writer: a
 *  draft, an unpublished site or a magazine not yet on the plan included.
 *  Scripts don't run in the frame, so a paid story shows what a reader
 *  without a subscription sees. A story link clicked inside opens that story
 *  here; other links do nothing. */
export default function ReaderView() {
  const { siteId } = useParams<{ siteId: string }>()
  const [params, setParams] = useSearchParams()
  const story = params.get('story')
  const slug = params.get('slug')
  // Each answer remembers which page it is for, so a new page shows loading.
  const key = `${siteId}|${story || ''}|${slug || ''}`
  const [result, setResult] = useState<{ key: string; html?: string; error?: string } | null>(null)
  const frame = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    let live = true
    cappeApi.postHtml(`/sites/${siteId}/magazine/view`, story ? { story_id: story } : slug ? { slug } : {})
      .then((h) => { if (live) setResult({ key, html: h }) })
      .catch((e) => { if (live) setResult({ key, error: e instanceof Error ? e.message : 'Could not show the magazine' }) })
    return () => { live = false }
  }, [siteId, story, slug, key])
  const current = result?.key === key ? result : null
  const html = current?.html ?? null
  const error = current?.error ?? null

  // The frame shares our origin (allow-same-origin, no scripts), so its
  // clicks can be read here.
  const wireLinks = () => {
    const doc = frame.current?.contentDocument
    doc?.addEventListener('click', (e) => {
      const a = (e.target as Element | null)?.closest?.('a')
      if (!a) return
      e.preventDefault()
      const path = a.getAttribute('href') || ''
      const m = path.match(/^\/stories\/([^/?#]+)/)
      if (m) setParams({ slug: decodeURIComponent(m[1]) })
      else if (path === '/' || path === '/magazine') setParams({})
    })
  }

  const back = story ? `/cappe/sites/${siteId}/stories/${story}` : `/cappe/sites/${siteId}/stories`

  return (
    <div className="flex h-full min-h-screen flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-4 py-2 text-sm">
        <Link to={back} className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-100">
          <ArrowLeft className="h-4 w-4" /> {story ? 'Back to the editor' : 'Stories'}
        </Link>
        {(story || slug) && (
          <button type="button" className={ui.btnGhost} onClick={() => setParams({})}>Front page</button>
        )}
        <span className="ml-auto text-xs text-zinc-500">What a reader sees. Only you can see this until you publish.</span>
      </div>
      {error && <p role="alert" className="p-6 text-sm text-red-400">{error}</p>}
      {html === null && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>}
      {html !== null && (
        <iframe ref={frame} title="Reader view" srcDoc={html} sandbox="allow-same-origin" onLoad={wireLinks}
          className="w-full flex-1 bg-white" style={{ minHeight: '85vh' }} />
      )}
    </div>
  )
}
