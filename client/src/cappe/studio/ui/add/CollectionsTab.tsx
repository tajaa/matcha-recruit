import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, BookOpen, Loader2, Plus, Save, Trash2 } from 'lucide-react'
import { collectionsApi } from '../../collectionsApi'
import { composeDoc } from '../../compose/compose'
import { COLLECTION_LIMITS, portableCollection, type CollectionCard } from '../../model/collections'
import type { Doc } from '../../model/types'
import { frameThreads, pageItemsHtml } from '../../render/layoutRender'
import { setHtml } from '../../render/sink'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'
import { applyCollection } from './applyCollection'
import { blankPage } from './applyTemplate'
import { COLLECTIONS } from './collections'

const button = 'rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800 disabled:opacity-50'
const problem = (err: unknown) => err instanceof Error && err.message ? err.message : 'The collection couldn’t be opened. Try again.'

/** A real Studio page, rendered at thumbnail size with its own typography. */
export function CollectionPreview({ doc, page = 0, width = 112 }: { doc: Doc; page?: number; width?: number }) {
  const c = useCtx()
  const [prepared, setPrepared] = useState<{ source: Doc; doc: Doc } | null>(null)
  useEffect(() => {
    let alive = true
    c.fonts.ensureDoc(doc).then(() => {
      if (alive) setPrepared({ source: doc, doc: composeDoc(doc, c.store.measure, true).doc })
    }).catch(() => {})
    return () => { alive = false }
  }, [doc, c.fonts, c.store])
  const shown = prepared?.source === doc ? prepared.doc : doc
  const html = useMemo(() => pageItemsHtml(shown, page, {
    assets: {}, faces: c.fonts.book.face, used: new Map(), threads: frameThreads(shown),
  }), [shown, page, c.fonts.book])
  const box = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => { if (box.current) setHtml(box.current, html) }, [html])
  return <div ref={box} aria-hidden className="relative shrink-0 overflow-hidden shadow-md" style={{
    width, height: width * doc.size.h / doc.size.w, background: doc.paper, ['--u' as string]: `${width / doc.size.w}px`,
  }} />
}

type Opened = { id: string; name: string; description: string; fonts?: string; doc: Doc; saved?: boolean }

export default function CollectionsTab() {
  const c = useCtx()
  const empty = useStudio(c.store, (s) => !s.doc.guides.length && s.doc.pages.every((_, k) => blankPage(s.doc, k)))
  const [saved, setSaved] = useState<CollectionCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [opened, setOpened] = useState<Opened | null>(null)
  const [pending, setPending] = useState(false)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const load = () => {
    setLoading(true); setError(null)
    return collectionsApi.list().then(setSaved, (e) => setError(problem(e))).finally(() => setLoading(false))
  }
  useEffect(() => {
    let alive = true
    collectionsApi.list().then((rows) => { if (alive) setSaved(rows) }, (e) => { if (alive) setError(problem(e)) })
      .finally(() => { if (alive) setLoading(false) })
    for (const collection of COLLECTIONS) void c.fonts.ensureDoc(collection.doc).catch(() => {})
    return () => { alive = false }
  }, [c.fonts])
  const openSaved = async (id: string) => {
    setPending(true); setError(null)
    try {
      const row = await collectionsApi.open(id)
      await c.fonts.ensureDoc(row.doc)
      setOpened({ ...row, saved: true, description: 'Your saved page designs. Fill the picture frames and edit the words for this story.' })
    } catch (e) { setError(problem(e)) } finally { setPending(false) }
  }
  const use = async () => {
    if (!opened) return
    setPending(true); setError(null); setMessage(null)
    try {
      const at = await applyCollection(c, opened.doc)
      if (at !== null) setMessage(`Added ${opened.doc.pages.length} pages. You can undo this with ⌘Z.`)
    } catch (e) { setError(problem(e)) } finally { setPending(false) }
  }
  const save = async () => {
    if (!name.trim() || pending) return
    setPending(true); setError(null); setMessage(null)
    try {
      c.editor.close()
      const doc = portableCollection(c.store.get().doc)
      if (doc.pages.length > COLLECTION_LIMITS.pages) throw new Error(`Save up to ${COLLECTION_LIMITS.pages} pages in one collection.`)
      // Match Python's ASCII JSON size, including surrogate pairs for emoji.
      const bytes = JSON.stringify(doc).replace(/[\u007f-\uffff]/g, (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`).length
      if (bytes > COLLECTION_LIMITS.bytes) throw new Error('A collection is too big to save. Use fewer pages or less text.')
      const row = await collectionsApi.save(name.trim(), doc)
      setSaved((rows) => [row, ...rows]); setSaving(false); setName('')
      setMessage(`“${row.name}” saved to your collections.`)
    } catch (e) { setError(problem(e)) } finally { setPending(false) }
  }
  const remove = async () => {
    if (!opened?.saved) return
    setPending(true); setError(null)
    try {
      await collectionsApi.remove(opened.id)
      setSaved((rows) => rows.filter((row) => row.id !== opened.id)); setOpened(null)
      setMessage('Collection removed from your library. Pages already added to stories stay there.')
    } catch (e) { setError(problem(e)) } finally { setPending(false) }
  }
  return <div className="space-y-4">
    {error && <div role="alert" className="space-y-2 text-xs text-red-300"><p>{error}</p>
      {!opened && <button type="button" className={button} onClick={() => void load()} disabled={loading}>Reload saved collections</button>}
    </div>}
    {message && <p role="status" className="text-xs leading-relaxed text-emerald-300">{message}</p>}
    {opened ? <>
      <button type="button" className="flex items-center gap-1 text-xs text-zinc-400 hover:text-white" disabled={pending}
        onClick={() => { setOpened(null); setError(null); setMessage(null) }}><ArrowLeft className="h-3.5 w-3.5" />All collections</button>
      <div>
        <h3 className="text-lg font-medium text-zinc-100">{opened.name}</h3>
        <p className="mt-1 text-xs leading-relaxed text-zinc-400">{opened.description}</p>
        {opened.fonts && <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">{opened.fonts}</p>}
      </div>
      <div className="space-y-2 rounded-md border border-zinc-700 bg-zinc-950/50 p-3">
        <p className="text-[11px] leading-relaxed text-zinc-400">{empty ? 'Start this blank story with the complete collection.' : 'Add the complete collection after the spread in view. A blank page is added when needed to keep its facing spreads together.'} Your page size is used. Everything stays editable.</p>
        <button type="button" onClick={() => void use()} disabled={pending} aria-busy={pending}
          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-emerald-500 px-3 py-2 text-xs font-medium text-zinc-950 hover:bg-emerald-400 disabled:opacity-50">
          {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}Use all {opened.doc.pages.length} pages
        </button>
      </div>
      <div className="grid grid-cols-2 justify-items-center gap-x-2 gap-y-4" aria-label="Pages in this collection">
        {opened.doc.pages.map((p, k) => <div key={p.id} className="space-y-1.5">
          <CollectionPreview doc={opened.doc} page={k} />
          <p className="max-w-28 text-[10px] text-zinc-500">{String(k + 1).padStart(2, '0')} · {opened.saved ? 'Your design' : ['Cover', 'Contents', 'Editorial note', 'Opening · left', 'Opening · right', 'Photo essay · left', 'Photo essay · right', 'Interview · portrait', 'Interview · questions', 'Credits'][k]}</p>
        </div>)}
      </div>
      {opened.saved && <button type="button" className={`${button} flex items-center gap-1.5`} onClick={() => void remove()} disabled={pending}>
        <Trash2 className="h-3.5 w-3.5" />Remove saved collection</button>}
    </> : <>
      <div>
        <h3 className="text-sm font-medium text-zinc-100">Designed as a whole</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">Covers, contents, opening spreads, photo essays, interviews and credits. One considered design from first page to last.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {COLLECTIONS.map((collection) => <button key={collection.id} type="button" disabled={pending}
          onClick={() => { setOpened(collection); setMessage(null); setError(null) }} aria-label={`Explore ${collection.name}`}
          className="flex flex-col items-center gap-2 rounded-md border border-zinc-800 p-1.5 text-left hover:border-zinc-500 disabled:opacity-50">
          <CollectionPreview doc={collection.doc} />
          <span className="w-full text-xs text-zinc-200">{collection.name}</span>
          <span className="w-full text-[10px] leading-snug text-zinc-500">{collection.direction}<span className="mt-1 block">10 editable pages</span></span>
        </button>)}
      </div>
      <section className="space-y-3 border-t border-zinc-800 pt-4" aria-label="Your collections">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-medium text-zinc-200">Your collections</h3>
          <button type="button" onClick={() => { setSaving((v) => !v); setError(null) }} disabled={pending || loading || saved.length >= COLLECTION_LIMITS.count}
            className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-white disabled:opacity-50"><Save className="h-3 w-3" />Save these pages</button>
        </div>
        {saving && <form className="space-y-2 rounded-md border border-zinc-700 p-3" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <label className="block text-[11px] text-zinc-400">Collection name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoFocus required disabled={pending}
            className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-white" placeholder="My editorial collection" /></label>
          <p className="text-[10px] leading-relaxed text-zinc-500">Saves all current pages, up to 32, with their type, spacing and words. Photos become empty frames. Available across your magazines.</p>
          <div className="flex gap-2"><button type="submit" disabled={pending || !name.trim()} className={button}>{pending ? 'Saving…' : 'Save collection'}</button>
            <button type="button" className={button} disabled={pending} onClick={() => setSaving(false)}>Cancel</button></div>
        </form>}
        {loading ? <p role="status" className="text-[11px] text-zinc-500">Loading your collections…</p> : saved.length ? <div className="space-y-1">
          {saved.map((row) => <button type="button" key={row.id} disabled={pending} onClick={() => void openSaved(row.id)}
            className="flex w-full items-center gap-2 rounded-md p-2 text-left hover:bg-zinc-800 disabled:opacity-50">
            <BookOpen className="h-4 w-4 shrink-0 text-zinc-500" /><span className="min-w-0 flex-1 truncate text-xs text-zinc-300">{row.name}</span>
            <span className="shrink-0 text-[10px] text-zinc-500">{row.page_count} pages</span>
          </button>)}
        </div> : <p className="text-[11px] leading-relaxed text-zinc-500">Make a design your own, then save these pages here to start your next issue.</p>}
      </section>
    </>}
  </div>
}
