import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, BookOpen, Eye, Loader2, Plus, Redo2, Trash2, Undo2, Wand2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type {
  CappeAsset, CappeMagazine, CappePost, CappeStockSource, CappeStoryOptions, StoryBlock, StoryContent, StoryLayout,
} from '../../types'
import LibraryPanel from '../library/LibraryPanel'
import AssistPanel from './AssistPanel'
import BlockEditor from './BlockEditor'
import { confirmLeave } from '../../utils/unsavedGuard'
import { useUnsavedGuard } from '../../pages/site/PageEditor/useUnsavedGuard'
import { BLOCK_LABELS, duplicateBlock, insertBlock, moveBlock, newBlock, withCaption, withText } from './blocks'
import { useHistory } from './history'
import { wireBook, type BookControl } from '../reader/book'

type Fields = { title: string; kicker: string; excerpt: string; byline: string; topic: string; layout: StoryLayout; status: CappePost['status']; access: CappePost['access'] }

const fieldsOf = (p: CappePost): Fields => ({
  title: p.title, kicker: p.kicker || '', excerpt: p.excerpt || '', byline: p.byline || '', topic: p.topic || '',
  layout: p.layout, status: p.status, access: p.access || 'free',
})

type Doc = { fields: Fields; blocks: StoryBlock[] }

const ADDABLE: StoryBlock['type'][] = ['text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider']

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const MOD = isMac ? '⌘' : 'Ctrl+'

/** A thin "+" between blocks that opens the kinds of block to put there. */
function InsertMenu({ open, onToggle, onPick, withCover, withPaywall, last }: {
  open: boolean
  onToggle: () => void
  onPick: (type: StoryBlock['type']) => void
  withCover: boolean
  /** A paid story without its paywall yet: the line can go here. */
  withPaywall: boolean
  last?: boolean
}) {
  return (
    <div className={last ? '' : 'group -my-2 flex flex-col items-center'}>
      {last
        ? <button type="button" className={ui.btnGhost} onClick={onToggle} aria-expanded={open}><Plus className="h-4 w-4" /> Add a block</button>
        : (
          <button type="button" onClick={onToggle} aria-expanded={open} aria-label="Insert a block here"
            className={`flex h-5 w-full items-center gap-2 text-zinc-600 hover:text-emerald-400 focus-visible:text-emerald-400 ${open ? 'text-emerald-400' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'}`}>
            <span className="h-px flex-1 bg-current opacity-40" /><Plus className="h-3.5 w-3.5" /><span className="h-px flex-1 bg-current opacity-40" />
          </button>
        )}
      {open && (
        <div className={`flex flex-wrap gap-2 ${last ? 'mt-2' : 'my-2 justify-center'}`} role="menu">
          {withCover && <button type="button" role="menuitem" className={ui.btnGhost} onClick={() => onPick('cover')}>Cover</button>}
          {[...ADDABLE, ...(withPaywall ? ['paywall' as const] : [])].map((t) => (
            <button key={t} type="button" role="menuitem" className={ui.btnGhost} onClick={() => onPick(t)}>{BLOCK_LABELS[t]}</button>
          ))}
        </div>
      )}
    </div>
  )
}

/** `sites/:siteId/stories/:postId` — one story: its words, its blocks, and a
 *  live preview of the page the site will render. */
export default function StoryEditor() {
  const { siteId, postId } = useParams<{ siteId: string; postId: string }>()
  const navigate = useNavigate()
  const [post, setPost] = useState<CappePost | null>(null)
  // The headline fields and the blocks are one document with undo and redo.
  const doc = useHistory<Doc | null>(null)
  const fields = doc.value?.fields ?? null
  const blocks = useMemo(() => doc.value?.blocks ?? [], [doc.value])
  const [options, setOptions] = useState<CappeStoryOptions | null>(null)
  const [assets, setAssets] = useState<Map<string, CappeAsset>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [picking, setPicking] = useState<((a: CappeAsset) => void) | null>(null)
  const [insertAt, setInsertAt] = useState<number | null>(null)
  const [dropAt, setDropAt] = useState<number | null>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const [assisting, setAssisting] = useState(false)
  const [finding, setFinding] = useState<{ source: CappeStockSource; query: string } | null>(null)
  const [preview, setPreview] = useState<string>('')
  const [previewOpen, setPreviewOpen] = useState(true)
  // Whether the magazine takes paid subscribers: a story can only become paid then.
  const [paidOn, setPaidOn] = useState(false)
  const previewGen = useRef(0)
  // The preview's page turner; a fresh preview opens on the spread being read.
  const previewBook = useRef<BookControl | null>(null)
  const previewSpread = useRef(0)
  const onPreviewLoad = (e: { currentTarget: HTMLIFrameElement }) => {
    previewBook.current?.dispose()
    previewBook.current = wireBook(e.currentTarget.contentDocument, previewSpread.current, (i) => { previewSpread.current = i })
  }
  const { set: setDoc, reset: resetDoc, replace: replaceDoc } = doc

  /** Change the blocks. `step` keeps it its own undo step (adding, moving or
   *  deleting a block), never folded into the typing around it. */
  const setBlocks = useCallback((next: StoryBlock[] | ((bs: StoryBlock[]) => StoryBlock[]), step = false) =>
    setDoc((d) => (d ? { ...d, blocks: typeof next === 'function' ? next(d.blocks) : next } : d), { step }), [setDoc])
  const setFields = useCallback((next: (f: Fields) => Fields) =>
    setDoc((d) => (d ? { ...d, fields: next(d.fields) } : d)), [setDoc])
  const docOf = (p: CappePost): Doc => ({ fields: fieldsOf(p), blocks: p.content?.blocks || [] })

  useEffect(() => {
    let cancelled = false
    cappeApi.get<CappeMagazine>(`/sites/${siteId}/magazine`)
      .then((m) => { if (!cancelled) setPaidOn(!!m.paid_enabled) })
      .catch(() => { /* treated as off; the server decides anyway */ })
    return () => { cancelled = true }
  }, [siteId])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<CappePost>(`/sites/${siteId}/posts/${postId}`),
      cappeApi.get<CappeStoryOptions>(`/sites/${siteId}/stories/options`),
      cappeApi.get<{ assets: CappeAsset[] }>(`/sites/${siteId}/assets`),
    ]).then(([p, o, a]) => {
      if (cancelled) return
      setPost(p)
      resetDoc(docOf(p))
      setOptions(o)
      setAssets(new Map(a.assets.map((x) => [x.id, x])))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load the story') })
    return () => { cancelled = true }
  }, [siteId, postId, resetDoc])

  const isStory = post?.format === 'blocks'
  const dirty = useMemo(() => {
    if (!post || !fields) return false
    return JSON.stringify(fields) !== JSON.stringify(fieldsOf(post))
      || JSON.stringify(blocks) !== JSON.stringify(post.content?.blocks || [])
  }, [post, fields, blocks])

  // The preview follows the editor, a moment after typing settles.
  useEffect(() => {
    if (!fields || !isStory || !previewOpen) return
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      const body = { title: fields.title, excerpt: fields.excerpt || null, kicker: fields.kicker || null, topic: fields.topic || null,
        layout: fields.layout, byline: fields.byline || null, access: fields.access, content: { blocks } satisfies StoryContent }
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`, body)
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, fields, blocks, isStory, previewOpen])

  const setField = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((f) => ({ ...f, [key]: value }))

  const pickAsset = useCallback((done: (a: CappeAsset) => void) => {
    setPicking(() => (a: CappeAsset) => {
      setAssets((m) => new Map(m).set(a.id, a))
      done(a)
      setPicking(null)
    })
  }, [])

  // From "Find pictures": the chosen picture joins the story as a photo block.
  const addPhoto = (a: CappeAsset) => {
    setAssets((m) => new Map(m).set(a.id, a))
    setBlocks((bs) => [...bs, { ...newBlock('photo'), asset_id: a.id } as StoryBlock], true)
    setFinding(null)
  }

  const save = async (status?: CappePost['status']) => {
    if (!fields || !post) return
    setSaving(true)
    setError(null)
    const next = status ? { ...fields, status } : fields
    try {
      const body: Record<string, unknown> = {
        title: next.title.trim() || 'Untitled story', kicker: next.kicker.trim() || null, excerpt: next.excerpt.trim() || null,
        byline: next.byline.trim() || null, topic: next.topic || null, layout: next.layout, status: next.status,
      }
      if (next.access !== post.access) body.access = next.access
      if (isStory) {
        body.content = { blocks }
        const cover = blocks[0]?.type === 'cover' ? blocks[0].asset_id : null
        body.cover_asset_id = cover
      }
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, body)
      setPost(updated)
      replaceDoc(docOf(updated))
      setSavedAt(Date.now())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  const becomeStory = async () => {
    setSaving(true)
    try {
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, { format: 'blocks' })
      setPost(updated)
      resetDoc(docOf(updated))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not convert this post')
    } finally {
      setSaving(false)
    }
  }

  const startFromLayout = (layout: StoryLayout) => {
    const starter = options?.layouts.find((l) => l.key === layout)
    const empty = blocks.every((b) => b.type === 'cover' ? !b.asset_id : b.type === 'text' ? !b.md : true)
    setDoc((d) => (d ? { fields: { ...d.fields, layout }, blocks: starter && empty ? starter.content.blocks : d.blocks } : d), { step: true })
  }

  useUnsavedGuard(() => dirty)

  // ⌘S saves, ⌘Z undoes, ⇧⌘Z (or ⌘Y) redoes — anywhere in the editor, but
  // not while the picture picker is open over it.
  const keys = useRef({ save: () => {}, undo: doc.undo, redo: doc.redo, blocked: false })
  useEffect(() => {
    keys.current = { save: () => { if (dirty && !saving) save() }, undo: doc.undo, redo: doc.redo, blocked: !!(picking || finding) }
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || keys.current.blocked) return
      const k = e.key.toLowerCase()
      if (k === 's') { e.preventDefault(); keys.current.save() }
      else if (k === 'z' && !e.shiftKey) { e.preventDefault(); keys.current.undo() }
      else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); keys.current.redo() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const offerPaywall = fields?.access === 'paid' && !blocks.some((b) => b.type === 'paywall')
  const insert = (type: StoryBlock['type'], at: number) => {
    setBlocks((bs) => insertBlock(bs, at, newBlock(type)), true)
    setInsertAt(null)
  }

  // Drag a block by its grip and drop it on another block to put it there.
  const dragStart = (i: number) => (e: DragEvent) => {
    setDragging(i)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(i))
    const card = (e.currentTarget as HTMLElement).closest('[data-block]')
    if (card) e.dataTransfer.setDragImage(card, 24, 24)
  }
  const dragOver = (j: number) => (e: DragEvent) => {
    if (dragging === null || blocks[j]?.type === 'cover') return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dropAt !== j) setDropAt(j)
  }
  const drop = (j: number) => (e: DragEvent) => {
    e.preventDefault()
    const from = dragging
    setDragging(null)
    setDropAt(null)
    if (from !== null) setBlocks((bs) => moveBlock(bs, from, j), true)
  }
  const dragEnd = () => { setDragging(null); setDropAt(null) }

  const remove = async () => {
    if (!window.confirm('Delete this story? This can’t be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}/posts/${postId}`)
      navigate(`/cappe/sites/${siteId}/stories`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete')
    }
  }

  if (error && !post) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!post || !fields || !options) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <Link to={`/cappe/sites/${siteId}/stories`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
          className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Stories</Link>
        <span className={`${ui.badge} ${post.status === 'published' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{post.status}</span>
        {post.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{isStory ? `${post.reading_minutes || 0} min read · ${post.word_count} words` : 'Plain post'}</span>
        <div className="ml-auto flex items-center gap-2">
          {isStory && (
            <Link to={`/cappe/sites/${siteId}/magazine/view?story=${postId}`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
              className={ui.btnGhost} title="The saved story, as a reader will see it">
              <BookOpen className="h-4 w-4" /> View as a reader
            </Link>
          )}
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canUndo} onClick={doc.undo} aria-label="Undo" title={`Undo (${MOD}Z)`}><Undo2 className="h-4 w-4" /></button>
          <button type="button" className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30"
            disabled={!doc.canRedo} onClick={doc.redo} aria-label="Redo" title={`Redo (${isMac ? '⇧⌘Z' : 'Ctrl+Y'})`}><Redo2 className="h-4 w-4" /></button>
          {savedAt && !dirty && <span className="text-xs text-emerald-400">Saved</span>}
          {dirty && <span className="text-xs text-zinc-500">Unsaved</span>}
          {isStory && <button type="button" className={ui.btnGhost} onClick={() => setAssisting((v) => !v)} aria-pressed={assisting}><Wand2 className="h-4 w-4" /> Assist</button>}
          {isStory && <button type="button" className={ui.btnGhost} onClick={() => setPreviewOpen((v) => !v)} aria-pressed={previewOpen}><Eye className="h-4 w-4" /> Preview</button>}
          <button type="button" className={ui.btnGhost} disabled={saving || !dirty} onClick={() => save()} title={`Save (${MOD}S)`}>Save</button>
          {post.status !== 'published'
            ? <button type="button" className={ui.btnPrimary} disabled={saving} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Publish</button>
            : <button type="button" className={ui.btnPrimary} disabled={saving || !dirty} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Update</button>}
        </div>
      </header>
      {error && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-300">{error}</p>}

      <div className={`grid flex-1 ${previewOpen && isStory ? 'lg:grid-cols-2' : ''}`}>
        <div className="space-y-4 overflow-y-auto p-5">
          {assisting && isStory && (
            <AssistPanel siteId={siteId!} postId={postId!} title={fields.title} excerpt={fields.excerpt} blocks={blocks}
              assets={assets} onClose={() => setAssisting(false)}
              onHeadline={(h) => setDoc((d) => (d ? { ...d, fields: { ...d.fields, title: h.title, excerpt: h.dek || d.fields.excerpt, kicker: h.kicker || d.fields.kicker } } : d), { step: true })}
              onCaption={(id, caption) => setBlocks((bs) => withCaption(bs, id, caption), true)}
              onAlt={(a) => setAssets((m) => new Map(m).set(a.id, a))}
              onTighten={(i, md) => setBlocks((bs) => withText(bs, i, md), true)}
              onDraft={(dr) => setDoc((d) => (d ? {
                fields: { ...d.fields, title: dr.title || d.fields.title, excerpt: dr.excerpt || d.fields.excerpt, kicker: dr.kicker || d.fields.kicker },
                blocks: dr.content.blocks,
              } : d), { step: true })}
              onFind={setFinding} />
          )}
          <section className={`${ui.card} space-y-3 p-4`}>
            <input value={fields.title} onChange={(e) => setField('title', e.target.value)} maxLength={255} placeholder="Headline"
              className="w-full bg-transparent text-2xl font-semibold text-zinc-50 outline-none placeholder:text-zinc-600" aria-label="Headline" />
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={fields.kicker} onChange={(e) => setField('kicker', e.target.value)} maxLength={60} placeholder="Kicker (the small line over the headline)" className={ui.input} aria-label="Kicker" />
              <input value={fields.byline} onChange={(e) => setField('byline', e.target.value)} maxLength={160} placeholder="Byline" className={ui.input} aria-label="Byline" />
            </div>
            <textarea value={fields.excerpt} onChange={(e) => setField('excerpt', e.target.value)} rows={2} maxLength={600}
              placeholder="Dek: one or two sentences that sell the story" className={ui.input} aria-label="Dek" />
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-sm text-zinc-300">Topic
                <select value={fields.topic} onChange={(e) => setField('topic', e.target.value)} className={`${ui.input} mt-1`}>
                  <option value="">None</option>
                  {options.topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </label>
              <label className="text-sm text-zinc-300">Layout
                <select value={fields.layout} onChange={(e) => startFromLayout(e.target.value as StoryLayout)} className={`${ui.input} mt-1`} disabled={!isStory}>
                  {options.layouts.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              </label>
              <label className="text-sm text-zinc-300">Status
                <select value={fields.status} onChange={(e) => setField('status', e.target.value as CappePost['status'])} className={`${ui.input} mt-1`}>
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
            </div>
            {isStory && (
              <label className="block text-sm text-zinc-300">Who can read it
                <select value={fields.access} onChange={(e) => setField('access', e.target.value as CappePost['access'])}
                  className={`${ui.input} mt-1 sm:max-w-xs`} aria-label="Who can read it">
                  <option value="free">Everyone</option>
                  <option value="paid" disabled={!paidOn && fields.access !== 'paid'}>Subscribers (after the paywall)</option>
                </select>
                <span className="mt-1 block text-xs text-zinc-500">
                  {paidOn
                    ? 'Readers see everything above the paywall block (or the first few blocks), then are asked to subscribe.'
                    : <>To charge readers, turn on paid subscriptions in <Link to={`/cappe/sites/${siteId}/magazine`} className="underline">Magazine settings</Link>.</>}
                </span>
              </label>
            )}
          </section>

          {!isStory ? (
            <section className={`${ui.card} space-y-3 p-4`}>
              <p className="text-sm text-zinc-300">This is a plain post written as Markdown. Turn it into a story to lay it out with pictures.</p>
              <textarea value={post.body || ''} readOnly rows={8} className={`${ui.input} font-mono text-[13px] opacity-80`} aria-label="Post body" />
              <button type="button" className={ui.btnPrimary} disabled={saving} onClick={becomeStory}>Turn into a story</button>
            </section>
          ) : (
            <>
              {blocks.map((b, i) => (
                <div key={i} className="space-y-4">
                  {b.type !== 'cover' && (
                    <InsertMenu open={insertAt === i} onToggle={() => setInsertAt((v) => (v === i ? null : i))}
                      onPick={(t) => insert(t, i)} withCover={i === 0} withPaywall={offerPaywall} />
                  )}
                  <div data-block={i} onDragOver={dragOver(i)} onDrop={drop(i)} onDragEnd={dragEnd}
                    onDragLeave={() => setDropAt((v) => (v === i ? null : v))}
                    className={`rounded-xl ${dropAt === i && dragging !== i ? 'ring-2 ring-emerald-500' : ''}`}>
                    <BlockEditor block={b} index={i} count={blocks.length} assets={assets}
                      onChange={(nb) => setBlocks((bs) => bs.map((x, j) => (j === i ? nb : x)))}
                      onMove={(d) => setBlocks((bs) => moveBlock(bs, i, i + d), true)}
                      onRemove={() => setBlocks((bs) => bs.filter((_, j) => j !== i), true)}
                      onDuplicate={() => setBlocks((bs) => duplicateBlock(bs, i), true)}
                      onDragStart={dragStart(i)}
                      onPickAsset={pickAsset} />
                  </div>
                </div>
              ))}
              <div>
                <InsertMenu last open={insertAt === blocks.length} onToggle={() => setInsertAt((v) => (v === blocks.length ? null : blocks.length))}
                  onPick={(t) => insert(t, blocks.length)} withCover={blocks[0]?.type !== 'cover'} withPaywall={offerPaywall} />
              </div>
            </>
          )}

          <div className="pt-4">
            <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}><Trash2 className="h-4 w-4" /> Delete story</button>
          </div>
        </div>

        {previewOpen && isStory && (
          <div className="hidden border-l border-zinc-800 bg-zinc-950 lg:block">
            <iframe title="Story preview" srcDoc={preview} sandbox="allow-same-origin" onLoad={onPreviewLoad} className="h-full min-h-[80vh] w-full bg-white" />
          </div>
        )}
      </div>

      {(picking || finding) && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center" role="dialog"
          aria-label={picking ? 'Choose a picture' : 'Find pictures'}>
          <div className={`${ui.card} max-h-[90vh] w-full max-w-5xl overflow-y-auto p-5`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-zinc-100">{picking ? 'Choose a picture' : 'Find pictures for this story'}</h2>
              <button type="button" onClick={() => { setPicking(null); setFinding(null) }} className="text-zinc-500 hover:text-zinc-300" aria-label="Close picker"><X className="h-4 w-4" /></button>
            </div>
            {finding && <p className="mb-3 text-xs text-zinc-500">Import pictures, then click one and “Use this picture” to add it to the story as a photo.</p>}
            <LibraryPanel siteId={siteId!} onPick={picking || (finding ? addPhoto : undefined)} postId={postId}
              stockQuery={picking ? undefined : finding || undefined} />
          </div>
        </div>
      )}
    </div>
  )
}
