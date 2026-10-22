import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, BookOpen, Eye, Loader2, Monitor, Plus, Redo2, Smartphone, Trash2, Undo2, Wand2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type {
  CappeAsset, CappeMagazine, CappePost, CappeStockSource, CappeStoryOptions, StoryBlock, StoryLayout,
} from '../../types'
import LibraryPanel from '../library/LibraryPanel'
import AssistPanel from './AssistPanel'
import BlockEditor from './BlockEditor'
import StorySettings from './StorySettings'
import { confirmLeave } from '../../utils/unsavedGuard'
import { useUnsavedGuard } from '../../pages/site/PageEditor/useUnsavedGuard'
import { BLOCK_LABELS, duplicateBlock, insertBlock, moveBlock, newBlock, withCaption, withText } from './blocks'
import { useHistory } from './history'
import BookFrame from '../reader/BookFrame'
import BlockPanel, { PanelHead } from '../canvas/BlockPanel'
import EditFrame, { type Device } from '../canvas/EditFrame'
import type { FrameMessage, FrameTarget, Place } from '../canvas/bridge'
import {
  storyDocOf, storyFromMessage, storyPreviewBody, storySaveBody, withPicture, type StoryDoc, type StoryFields,
} from '../canvas/storyDoc'

const ADDABLE: StoryBlock['type'][] = ['text', 'photo', 'photos', 'quote', 'sidebar', 'qa', 'divider']

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const MOD = isMac ? '⌘' : 'Ctrl+'

/** The story's id on its page to edit (routes/blog.py `preview_story`). */
const ON_PAGE = 'preview'
const PAGE_STORIES: ReadonlySet<string> = new Set([ON_PAGE])

type View = 'page' | 'outline'

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

/** Two or three buttons, one of them on. */
function Toggle<T extends string>({ value, options, onChange, label }: {
  value: T; options: { key: T; label: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <div className="flex rounded-lg border border-zinc-800 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)} title={o.label}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${value === o.key ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}>
          {o.icon}{o.icon ? <span className="sr-only">{o.label}</span> : o.label}
        </button>
      ))}
    </div>
  )
}

/** `sites/:siteId/stories/:postId` — one story. On the Page, it is edited
 *  as readers will see it: words typed straight onto its pages, a block's
 *  pictures and look in the panel beside them. The Outline is the same story
 *  as a column of forms, with a preview. Both share one undo history. */
export default function StoryEditor() {
  const { siteId, postId } = useParams<{ siteId: string; postId: string }>()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [post, setPost] = useState<CappePost | null>(null)
  // The headline fields and the blocks are one document with undo and redo.
  const doc = useHistory<StoryDoc | null>(null)
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
  // The page to edit on.
  const [view, setView] = useState<View>(params.get('view') === 'outline' ? 'outline' : 'page')
  const [device, setDevice] = useState<Device>('spread')
  const [asReader, setAsReader] = useState(false)
  const [page, setPage] = useState('')
  const [place, setPlace] = useState<Place>({ target: null, spread: 0 })
  const [typing, setTyping] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const pageGen = useRef(0)
  const { set: setDoc, reset: resetDoc, replace: replaceDoc } = doc

  /** Change the blocks. `step` keeps it its own undo step (adding, moving or
   *  deleting a block), never folded into the typing around it. */
  const setBlocks = useCallback((next: StoryBlock[] | ((bs: StoryBlock[]) => StoryBlock[]), step = false) =>
    setDoc((d) => (d ? { ...d, blocks: typeof next === 'function' ? next(d.blocks) : next } : d), { step }), [setDoc])
  const setFields = useCallback((next: (f: StoryFields) => StoryFields) =>
    setDoc((d) => (d ? { ...d, fields: next(d.fields) } : d)), [setDoc])

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
      resetDoc(storyDocOf(p))
      setOptions(o)
      setAssets(new Map(a.assets.map((x) => [x.id, x])))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load the story') })
    return () => { cancelled = true }
  }, [siteId, postId, resetDoc])

  const isStory = post?.format === 'blocks'
  const onPage = isStory && view === 'page'
  const dirty = useMemo(() => !!post && !!doc.value && JSON.stringify(doc.value) !== JSON.stringify(storyDocOf(post)),
    [post, doc.value])

  // The preview (the outline's, and the page as a reader sees it) follows the
  // editor, a moment after typing settles.
  const wantPreview = isStory && (view === 'outline' ? previewOpen : asReader)
  useEffect(() => {
    if (!doc.value || !wantPreview) return
    const d = doc.value
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`, { ...storyPreviewBody(d), topic: d.fields.topic || null, access: d.fields.access })
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, doc.value, wantPreview])

  // The page to edit on: rendered again after each change, but never while
  // words are being typed on it (they are already there).
  useEffect(() => {
    if (!doc.value || !onPage || asReader || typing) return
    const d = doc.value
    const gen = ++pageGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`,
        { ...storyPreviewBody(d), topic: d.fields.topic || null, access: d.fields.access, edit: true })
        .then((html) => { if (gen === pageGen.current) { setPage(html); setPageError(null) } })
        .catch((e) => { if (gen === pageGen.current) setPageError(e instanceof Error ? e.message : 'Could not show the page') })
    }, 250)
    return () => clearTimeout(t)
  }, [siteId, doc.value, onPage, asReader, typing])

  const setField = <K extends keyof StoryFields>(key: K, value: StoryFields[K]) => setFields((f) => ({ ...f, [key]: value }))

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
    if (!doc.value || !post) return
    setSaving(true)
    setError(null)
    const d = status ? { ...doc.value, fields: { ...doc.value.fields, status } } : doc.value
    try {
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, storySaveBody(d, post))
      setPost(updated)
      replaceDoc(storyDocOf(updated))
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
      resetDoc(storyDocOf(updated))
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

  const select = (target: FrameTarget | null) => setPlace((p) => ({ ...p, target }))
  const selected = place.target?.kind === 'block' && blocks[place.target.block] ? place.target.block : null
  const removeBlock = (i: number) => {
    setBlocks((bs) => bs.filter((_, j) => j !== i), true)
    select(null)
  }
  const moveSelected = (i: number, d: -1 | 1) => {
    const next = moveBlock(blocks, i, i + d)
    if (next === blocks) return
    setBlocks(next, true)
    select({ kind: 'block', story: ON_PAGE, block: i + d })
  }

  // ⌘S saves, ⌘Z undoes, ⇧⌘Z (or ⌘Y) redoes — anywhere in the editor, but
  // not while the picture picker is open over it. On the page they come from
  // the page itself (`mz-key`).
  const keys = useRef({ save: () => {}, undo: doc.undo, redo: doc.redo, blocked: false })
  useEffect(() => {
    keys.current = { save: () => { if (dirty && !saving) save() }, undo: doc.undo, redo: doc.redo, blocked: !!(picking || finding) }
  })
  // ⌘S on the page arrives right after the words typed there: the save runs
  // once a render has those words in the document, not from this render's.
  const [saveAsked, setSaveAsked] = useState(0)
  useEffect(() => { if (saveAsked) keys.current.save() }, [saveAsked])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || keys.current.blocked) return
      const k = e.key.toLowerCase()
      // A field outside the story (Assist's notes) undoes its own typing.
      const own = e.target instanceof Element && e.target.closest('[data-native-undo]')
      if (k === 's') { e.preventDefault(); keys.current.save() }
      else if (own) return
      else if (k === 'z' && !e.shiftKey) { e.preventDefault(); keys.current.undo() }
      else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); keys.current.redo() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /** What the page says: a selection, words typed, a block added, a picture
   *  to choose, something dragged, a key. */
  const onFrame = (msg: FrameMessage) => {
    switch (msg.type) {
      case 'mz-select': select(msg.target.kind === 'none' ? null : msg.target); return
      case 'mz-place': setPlace((p) => (p.spread === msg.spread ? p : { ...p, spread: msg.spread })); return
      case 'mz-editing': setTyping(msg.on); return
      case 'mz-key':
        if (keys.current.blocked) return
        if (msg.key === 'save') setSaveAsked((n) => n + 1)
        else if (msg.key === 'undo') doc.undo()
        else if (msg.key === 'redo') doc.redo()
        // Not the cover: it is the story's header, and a stray Backspace after
        // leaving the headline would take it and its picture.
        else if (selected !== null && blocks[selected]?.type !== 'cover') removeBlock(selected)
        return
      case 'mz-pick': {
        const { block, item } = msg
        if (!blocks[block]) return
        select({ kind: 'block', story: ON_PAGE, block })
        pickAsset((a) => setBlocks((bs) => bs.map((b, i) => (i === block ? withPicture(b, a.id, item) : b)), true))
        return
      }
      default: {
        if (!doc.value) return
        const r = storyFromMessage(doc.value, msg)
        if (!r) return
        setDoc((d) => (d ? storyFromMessage(d, msg)?.doc ?? d : d), { step: r.step })
        if (r.select !== undefined) select({ kind: 'block', story: ON_PAGE, block: r.select })
      }
    }
  }

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

  const settings = (narrow: boolean) => (
    <StorySettings fields={fields} options={options} isStory={isStory} paidOn={paidOn} siteId={siteId!} narrow={narrow}
      onField={setField} onLayout={startFromLayout} />
  )

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <Link to={`/cappe/sites/${siteId}/stories`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
          className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Stories</Link>
        <span className={`${ui.badge} ${post.status === 'published' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{post.status}</span>
        {post.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{isStory ? `${post.reading_minutes || 0} min read · ${post.word_count} words` : 'Plain post'}</span>
        {isStory && (
          <Toggle label="Edit on" value={view} onChange={setView}
            options={[{ key: 'page', label: 'Page' }, { key: 'outline', label: 'Outline' }]} />
        )}
        {onPage && (
          <>
            <Toggle label="Size" value={device} onChange={setDevice} options={[
              { key: 'spread', label: 'Two pages, as on a computer', icon: <Monitor className="h-4 w-4" /> },
              { key: 'phone', label: 'A phone', icon: <Smartphone className="h-4 w-4" /> },
            ]} />
            <label className="flex items-center gap-1.5 text-xs text-zinc-400" title="The page as a reader sees it, paywall and all">
              <input type="checkbox" checked={asReader} onChange={(e) => setAsReader(e.target.checked)} /> As a reader
            </label>
          </>
        )}
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
          {isStory && view === 'outline' && <button type="button" className={ui.btnGhost} onClick={() => setPreviewOpen((v) => !v)} aria-pressed={previewOpen}><Eye className="h-4 w-4" /> Preview</button>}
          <button type="button" className={ui.btnGhost} disabled={saving || !dirty} onClick={() => save()} title={`Save (${MOD}S)`}>Save</button>
          {post.status !== 'published'
            ? <button type="button" className={ui.btnPrimary} disabled={saving} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Publish</button>
            : <button type="button" className={ui.btnPrimary} disabled={saving || !dirty} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Update</button>}
        </div>
      </header>
      {error && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-300">{error}</p>}

      {assisting && isStory && (
        <div className="border-b border-zinc-800 p-5">
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
        </div>
      )}

      {onPage ? (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="relative h-[calc(100dvh-3.9rem)] min-h-[32rem] bg-zinc-950">
            {pageError && !asReader && (
              <p role="alert" className="absolute inset-x-0 top-0 z-10 bg-red-500/90 px-4 py-2 text-sm text-white">
                The page couldn’t be set with the last change: {pageError}
              </p>
            )}
            {asReader
              ? <BookFrame html={preview} title="The story as a reader sees it" keepPlace className="h-full" />
              : <EditFrame html={page} place={place} stories={PAGE_STORIES} device={device} title="The story's pages, to edit"
                  onMessage={onFrame} />}
          </div>
          <aside className="overflow-y-auto border-l border-zinc-800 bg-zinc-950/60 lg:h-[calc(100dvh-3.9rem)]" aria-label="Selected">
            {selected !== null ? (
              <BlockPanel block={blocks[selected]} index={selected} count={blocks.length} assets={assets}
                onChange={(nb) => setBlocks((bs) => bs.map((x, j) => (j === selected ? nb : x)))}
                onMove={(d) => moveSelected(selected, d)}
                onDuplicate={() => setBlocks((bs) => duplicateBlock(bs, selected), true)}
                onRemove={() => removeBlock(selected)}
                onPickAsset={pickAsset} onClose={() => select(null)} />
            ) : (
              <div>
                <PanelHead title="The story" />
                <div className="space-y-4 p-4">
                  <p className="text-xs leading-relaxed text-zinc-500">
                    Click anything on the page to change it: type straight into the headline and the text; select words for bold,
                    italic, links, headings and lists. Hover between blocks for a <span className="text-emerald-400">+</span> to add one.
                    Drag words on a photo, or the dot on a cover picture, to move them.
                  </p>
                  {settings(true)}
                  <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}><Trash2 className="h-4 w-4" /> Delete story</button>
                </div>
              </div>
            )}
          </aside>
        </div>
      ) : (
        <div className={`grid flex-1 ${previewOpen && isStory ? 'lg:grid-cols-2' : ''}`}>
          <div className="space-y-4 overflow-y-auto p-5">
            <section className={`${ui.card} space-y-3 p-4`}>
              <input value={fields.title} onChange={(e) => setField('title', e.target.value)} maxLength={255} placeholder="Headline"
                className="w-full bg-transparent text-2xl font-semibold text-zinc-50 outline-none placeholder:text-zinc-600" aria-label="Headline" />
              <div className="grid gap-3 sm:grid-cols-2">
                <input value={fields.kicker} onChange={(e) => setField('kicker', e.target.value)} maxLength={60} placeholder="Kicker (the small line over the headline)" className={ui.input} aria-label="Kicker" />
                <input value={fields.byline} onChange={(e) => setField('byline', e.target.value)} maxLength={160} placeholder="Byline" className={ui.input} aria-label="Byline" />
              </div>
              <textarea value={fields.excerpt} onChange={(e) => setField('excerpt', e.target.value)} rows={2} maxLength={600}
                placeholder="Dek: one or two sentences that sell the story" className={ui.input} aria-label="Dek" />
              {settings(false)}
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
              {/* Pinned to the screen while the blocks scroll, so a page is a
                  screen's height. A fresh preview opens on the spread being read. */}
              <BookFrame html={preview} title="Story preview" keepPlace className="sticky top-0 h-[calc(100dvh-3.9rem)]" />
            </div>
          )}
        </div>
      )}

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
