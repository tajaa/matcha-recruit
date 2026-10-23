import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { CappeApiError } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { studioApi, toAsset, type StudioPost } from './api'
import { Shaper, loadHarfBuzz } from './compose/shaper'
import { FaceBook, loadManifest } from './fonts/faces'
import { FontLoader, browserWidth } from './fonts/loader'
import { DEFAULT_VIEW, Store } from './store/store'
import { TextEditor } from './text/editor'
import { Saver } from './store/saver'
import { boardOffset, layout } from './canvas/geometry'
import type { StudioCtx } from './ui/context'
import Studio from './ui/Studio'
import './ui/studio.css'
import { guideSeen } from './ui/guideContent'

type Loaded = { store: Store; fonts: FontLoader; editor: TextEditor; saver: Saver; post: StudioPost }

/** `/cappe/studio/:siteId/story/:postId`: a paged story in the Studio, full
 *  screen. Loads the story, the Studio's faces and HarfBuzz, sets the text,
 *  and saves as you go. */
export default function StudioPage() {
  const { siteId = '', postId = '' } = useParams<{ siteId: string; postId: string }>()
  const { account, loading } = useCappeMe()
  const navigate = useNavigate()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [post, setPost] = useState<StudioPost | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!account) return
    let gone = false
    let made: Loaded | null = null
    ;(async () => {
      const [opened, manifest, hb, lib] = await Promise.all([
        studioApi.open(siteId, postId), loadManifest(), loadHarfBuzz(), studioApi.assets(siteId).catch(() => ({ assets: [] })),
      ])
      const fonts = new FontLoader(new FaceBook(manifest), new Shaper(hb, browserWidth))
      await fonts.ensureDoc(opened.doc).catch(() => {})
      const assets = Object.fromEntries(lib.assets.map((a) => [a.id, toAsset(a)]))
      const store = new Store({
        doc: opened.doc, selection: [], editing: null, page: 0, tool: 'select', view: { ...DEFAULT_VIEW },
        panels: ['pages', 'props', 'character', 'paragraph'], overset: new Set(), assets, dialog: null, threading: null,
        guide: guideSeen() ? null : 'start',
        snaps: null, marquee: null,
        save: { rev: opened.post.rev, state: 'saved', message: null, draft: opened.draft, live: opened.live },
      }, fonts.measure)
      made = { store, fonts, editor: new TextEditor(store, () => document.querySelector('[data-studio-board]')),
        saver: new Saver(store, siteId, postId), post: opened.post }
      if (gone) { made.editor.destroy(); made.saver.dispose(); return }
      setLoaded(made)
      setPost(opened.post)
    })().catch((err) => {
      if (!gone) setError(err instanceof CappeApiError && err.status === 409 ? err.message
        : err instanceof Error ? err.message : 'The Studio couldn’t open this story.')
    })
    return () => { gone = true; made?.editor.destroy(); made?.saver.dispose() }
  }, [account, siteId, postId])

  const save = useCallback((opts?: { keep?: boolean; publish?: boolean }) => loaded ? loaded.saver.save(opts) : Promise.resolve(),
    [loaded])

  // Warn before leaving with changes unsaved.
  useEffect(() => {
    if (!loaded) return
    const leave = (e: BeforeUnloadEvent) => { if (loaded.saver.unsaved()) e.preventDefault() }
    window.addEventListener('beforeunload', leave)
    return () => window.removeEventListener('beforeunload', leave)
  }, [loaded])

  const fit = useCallback((page: number | null = null, spread = true) => {
    if (!loaded) return
    const sc = document.querySelector<HTMLElement>('[data-studio-scroller]')
    if (!sc) return
    const { store } = loaded
    const doc = store.get().doc
    const lay = layout(doc)
    const index = page ?? store.get().page
    const box = lay.spreads.find((s) => s.pages.includes(index)) ?? lay.spreads[0]
    const target = spread ? box : { x: lay.origin[index].x, y: lay.origin[index].y, w: doc.size.w, h: doc.size.h }
    const zoom = Math.max(0.05, Math.min((sc.clientWidth - 48) / target.w, (sc.clientHeight - 48) / target.h))
    store.set((s) => ({ view: { ...s.view, zoom }, page: index }))
    requestAnimationFrame(() => {
      const o = boardOffset(sc)
      sc.scrollLeft = o.x + (target.x + target.w / 2) * zoom - sc.clientWidth / 2
      sc.scrollTop = o.y + (target.y + target.h / 2) * zoom - sc.clientHeight / 2
    })
  }, [loaded])

  // Open fitted to the first spread.
  useEffect(() => { if (loaded) requestAnimationFrame(() => fit(0, true)) }, [loaded, fit])

  const ctx = useMemo<StudioCtx | null>(() => (loaded && post ? {
    store: loaded.store, fonts: loaded.fonts, editor: loaded.editor, siteId, postId, post, setPost, save, fit,
    board: () => document.querySelector('[data-studio-board]'),
    close: () => { void save().finally(() => navigate(`/cappe/sites/${siteId}/stories`)) },
  } : null), [loaded, post, siteId, postId, save, fit, navigate])

  if (!loading && !account) return <Navigate replace to={`/cappe/login?next=${encodeURIComponent(`/cappe/studio/${siteId}/story/${postId}`)}`} />
  if (error) {
    return (
      <div className="studio-dark fixed inset-0 flex flex-col items-center justify-center gap-3 bg-zinc-950 text-zinc-200">
        <p className="max-w-md text-center text-sm">{error}</p>
        <button type="button" onClick={() => navigate(`/cappe/sites/${siteId}/stories`)} className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs">Back to stories</button>
      </div>
    )
  }
  if (!ctx) {
    return (
      <div className="studio-dark fixed inset-0 flex items-center justify-center bg-zinc-950 text-sm text-zinc-400">
        Opening the Studio…
      </div>
    )
  }
  return <Studio ctx={ctx} />
}

