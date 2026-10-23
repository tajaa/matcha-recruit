import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, BookOpen, Image as ImageIcon, Layers, Loader2, Minus, Monitor, Plus, Redo2, Shapes, Smartphone, Trash2, Type, Undo2, Wand2, X,
} from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeAsset, CappeMagazine, CappePost, CappeStockSource, CappeStoryOptions, StoryBlock, StoryLayout } from '../../types'
import LibraryPanel from '../library/LibraryPanel'
import AssistPanel from './AssistPanel'
import StorySettings from './StorySettings'
import { confirmLeave } from '../../utils/unsavedGuard'
import { useUnsavedGuard } from '../../pages/site/PageEditor/useUnsavedGuard'
import { duplicateBlock, moveBlock, newBlock, withCaption, withText } from './blocks'
import { useHistory } from './history'
import BookFrame from '../reader/BookFrame'
import BlockPanel, { PanelHead } from '../canvas/BlockPanel'
import EditFrame, { type Device } from '../canvas/EditFrame'
import type { FrameKey, FrameMessage, FrameTarget, Place } from '../canvas/bridge'
import {
  changeDesign, storyDocOf, storyFromMessage, storyPreviewBody, storySaveBody, withPicture, type StoryDoc, type StoryFields,
} from '../canvas/storyDoc'
import {
  designOf, holdsDesign, mapLayers, moveLayer, patchLayers, type ArtAt, type Heights, type LayerPatch, type TextPreset,
} from '../design/designOps'
import type { Design, PageAspect, ShapeKind } from '../design/types'
import {
  addBlock, addImage, addPage, addShape, addText, artKey, artOf, command, designMessages, layerTarget, panelKey, type Clipboard, type Did,
} from '../workspace/actions'
import { ElementsPanel, PhotosPanel, TextPanel } from '../workspace/AddPanels'
import ArtInspector from '../workspace/ArtInspector'
import LayerInspector from '../workspace/LayerInspector'
import LayersPanel from '../workspace/LayersPanel'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const MOD = isMac ? '⌘' : 'Ctrl+'

/** The story's id on its page to edit (routes/blog.py `preview_story`). */
const ON_PAGE = 'preview'
const PAGE_STORIES: ReadonlySet<string> = new Set([ON_PAGE])

/** Times the size that fits the pane. */
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]

type Tab = 'text' | 'photos' | 'elements' | 'layers'
const TABS: { key: Tab; label: string; icon: typeof Type }[] = [
  { key: 'text', label: 'Text', icon: Type },
  { key: 'photos', label: 'Photos', icon: ImageIcon },
  { key: 'elements', label: 'Elements', icon: Shapes },
  { key: 'layers', label: 'Layers', icon: Layers },
]

/** Layers copied, one clipboard a site: any picture or page of its stories
 *  can take them (another site's library hasn't their pictures). */
const clipboards = new Map<string, Clipboard>()
function clipboardOf(site: string): Clipboard {
  let c = clipboards.get(site)
  if (!c) clipboards.set(site, (c = { layers: [], from: '' }))
  return c
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

/** Smaller, the size that fits, larger. */
function Zoom({ value, onChange }: { value: number; onChange: (z: number) => void }) {
  const i = ZOOMS.indexOf(value)
  const btn = 'rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-30'
  return (
    <div className="flex items-center rounded-lg border border-zinc-800 p-0.5" role="group" aria-label="Zoom">
      <button type="button" className={btn} aria-label="Zoom out" title="Zoom out" disabled={i <= 0} onClick={() => onChange(ZOOMS[i - 1])}><Minus className="h-3.5 w-3.5" /></button>
      <button type="button" onClick={() => onChange(1)} title="Fit the pages to the window" aria-label="Fit"
        className="w-12 text-center text-xs tabular-nums text-zinc-300 hover:text-zinc-50">{value === 1 ? 'Fit' : `${Math.round(value * 100)}%`}</button>
      <button type="button" className={btn} aria-label="Zoom in" title="Zoom in" disabled={i >= ZOOMS.length - 1} onClick={() => onChange(ZOOMS[i + 1])}><Plus className="h-3.5 w-3.5" /></button>
    </div>
  )
}

/** `sites/:siteId/stories/:postId` — one story, in one design workspace:
 *  what to add on the left (text, photos, elements, the story's layers), the
 *  story's own pages in the middle, laid out as readers see them, where words
 *  are typed and layers are placed, and on the right everything about what
 *  is selected. One undo history covers it all. */
export default function StoryEditor() {
  const { siteId, postId } = useParams<{ siteId: string; postId: string }>()
  const navigate = useNavigate()
  const [post, setPost] = useState<CappePost | null>(null)
  // The headline fields and the blocks are one document with undo and redo.
  const doc = useHistory<StoryDoc | null>(null)
  const fields = doc.value?.fields ?? null
  const blocks = useMemo(() => doc.value?.blocks ?? [], [doc.value])
  const [options, setOptions] = useState<CappeStoryOptions | null>(null)
  const [assets, setAssets] = useState<Map<string, CappeAsset>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [picking, setPicking] = useState<((a: CappeAsset) => void) | null>(null)
  const [assisting, setAssisting] = useState(false)
  const [finding, setFinding] = useState<{ source: CappeStockSource; query: string } | null>(null)
  const [preview, setPreview] = useState<string>('')
  // Whether the magazine takes paid subscribers: a story can only become paid then.
  const [paidOn, setPaidOn] = useState(false)
  const [accent, setAccent] = useState('#10b981')
  const previewGen = useRef(0)
  const [tab, setTab] = useState<Tab | null>('layers')
  const [zoom, setZoom] = useState(1)
  const [device, setDevice] = useState<Device>('spread')
  const [asReader, setAsReader] = useState(false)
  const [page, setPage] = useState('')
  const [place, setPlace] = useState<Place>({ target: null, spread: 0 })
  const [typing, setTyping] = useState(false)
  // The heights the page measured for words that grow, by picture (artKey).
  const [heights, setHeights] = useState<Record<string, Heights>>({})
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
      .then((m) => { if (!cancelled) { setPaidOn(!!m.paid_enabled); if (m.accent) setAccent(m.accent) } })
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
      // A story made of pages is designed in the Studio.
      if (p.format === 'pages') { navigate(`/cappe/studio/${siteId}/story/${p.id}`, { replace: true }); return }
      setPost(p)
      resetDoc(storyDocOf(p))
      setOptions(o)
      setAssets(new Map(a.assets.map((x) => [x.id, x])))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load the story') })
    return () => { cancelled = true }
  }, [siteId, postId, resetDoc, navigate])

  const isStory = post?.format === 'blocks'
  const dirty = useMemo(() => !!post && !!doc.value && JSON.stringify(doc.value) !== JSON.stringify(storyDocOf(post)),
    [post, doc.value])

  // The page as a reader sees it follows the editor, a moment after typing settles.
  useEffect(() => {
    if (!doc.value || !isStory || !asReader) return
    const d = doc.value
    const gen = ++previewGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`, { ...storyPreviewBody(d), topic: d.fields.topic || null, access: d.fields.access })
        .then((html) => { if (gen === previewGen.current) setPreview(html) })
        .catch(() => { /* the last good preview stays up */ })
    }, 600)
    return () => clearTimeout(t)
  }, [siteId, doc.value, isStory, asReader])

  // The page to edit on: rendered again after each change, but never while
  // words are being typed on it (they are already there).
  useEffect(() => {
    if (!doc.value || !isStory || asReader || typing) return
    const d = doc.value
    const gen = ++pageGen.current
    const t = setTimeout(() => {
      cappeApi.postHtml(`/sites/${siteId}/stories/preview`,
        { ...storyPreviewBody(d), topic: d.fields.topic || null, access: d.fields.access, edit: true })
        .then((html) => { if (gen === pageGen.current) { setPage(html); setPageError(null) } })
        .catch((e) => { if (gen === pageGen.current) setPageError(e instanceof Error ? e.message : 'Could not show the page') })
    }, 250)
    return () => clearTimeout(t)
  }, [siteId, doc.value, isStory, asReader, typing])

  // A design changed here (the panels, undo) is drawn on the page at once;
  // the server's page follows. `drawn` is the story the page already shows
  // (a change made on the page itself is there before it reaches us).
  const [drawn, setDrawn] = useState<StoryDoc | null>(null)
  const [outbox, setOutbox] = useState<{ seq: number; messages: Record<string, unknown>[] }>({ seq: 0, messages: [] })
  if (doc.value && doc.value !== drawn) {
    const messages = designMessages(drawn, doc.value, ON_PAGE, assets)
    setDrawn(doc.value)
    if (messages.length) setOutbox((o) => ({ seq: o.seq + 1, messages }))
  }

  const setField = <K extends keyof StoryFields>(key: K, value: StoryFields[K]) => setFields((f) => ({ ...f, [key]: value }))

  const pickAsset = useCallback((done: (a: CappeAsset) => void) => {
    setPicking(() => (a: CappeAsset) => {
      setAssets((m) => new Map(m).set(a.id, a))
      done(a)
      setPicking(null)
    })
  }, [])

  const save = async (status?: CappePost['status']) => {
    if (!doc.value || !post) return
    setSaving(true)
    setError(null)
    const d = status ? { ...doc.value, fields: { ...doc.value.fields, status } } : doc.value
    try {
      const updated = await cappeApi.put<CappePost>(`/sites/${siteId}/posts/${postId}`, storySaveBody(d, post))
      setPost(updated)
      replaceDoc(storyDocOf(updated))
      setSaved(true)
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
  const target = place.target
  const removeBlock = (i: number) => {
    setBlocks((bs) => bs.filter((_, j) => j !== i), true)
    select(null)
  }
  const moveTo = (from: number, to: number) => {
    const next = moveBlock(blocks, from, to)
    if (next === blocks) return
    setBlocks(next, true)
    select({ kind: 'block', story: ON_PAGE, block: next.indexOf(blocks[from]) })
  }

  /** A change worked out from the story as it is now: one undo step, then
   *  what it selects. */
  const latest = useRef<StoryDoc | null>(null)
  useEffect(() => { latest.current = doc.value })
  const apply = (fn: (d: StoryDoc) => Did | null) => {
    const d = latest.current
    const r = d ? fn(d) : null
    if (!r) return
    setDoc(() => r.doc, { step: true })
    select(r.select)
  }
  /** A design changed by the panels (merged into one undo step while a
   *  number is dragged or a colour picked). */
  const changeArt = (art: ArtAt, fn: (d: Design) => Design, step = false) =>
    setDoc((d) => (d ? changeDesign(d, art.block, art.item, fn) ?? d : d), { step })

  // What is added goes ON the picture or page in hand, or into the story.
  const art = doc.value ? artOf(doc.value, target) : null
  const add = {
    text: (p: TextPreset) => { if (art) apply((d) => addText(d, ON_PAGE, art, p)) },
    shape: (s: ShapeKind, square?: boolean) => { if (art) apply((d) => addShape(d, ON_PAGE, art, assets, s, square)) },
    image: (a: CappeAsset) => {
      const all = new Map(assets).set(a.id, a)
      apply((d) => (art ? addImage(d, ON_PAGE, art, all, a) : addBlock(d, ON_PAGE, target, { ...newBlock('photo'), asset_id: a.id } as StoryBlock)))
    },
    block: (type: StoryBlock['type']) => apply((d) => addBlock(d, ON_PAGE, target, newBlock(type))),
    page: (aspect: PageAspect) => apply((d) => addPage(d, ON_PAGE, target, aspect)),
  }

  /** A command from the page, a key in the panels or a button. */
  const runCommand = (key: FrameKey) => {
    if (target?.kind === 'block' && key === 'delete') {
      // Not the cover: it is the story's header, and a stray Backspace after
      // leaving the headline would take it and its picture.
      if (target.item === undefined && blocks[target.block] && blocks[target.block].type !== 'cover') removeBlock(target.block)
      return
    }
    const at = target?.kind === 'layer' ? heights[artKey({ block: target.block, item: target.item })] : undefined
    apply((d) => command(d, ON_PAGE, target, key, clipboardOf(siteId!), at))
  }

  // ⌘S saves, ⌘Z undoes, ⇧⌘Z (or ⌘Y) redoes — anywhere in the editor, but
  // not while the picture picker is open over it. On the page they come from
  // the page itself (`mz-key`). Layer keys (copy, paste, group, Delete…) work
  // in the panels too, outside the boxes typed in.
  const keys = useRef({ save: () => {}, undo: doc.undo, redo: doc.redo, command: (() => {}) as (k: FrameKey) => void, blocked: false })
  useEffect(() => {
    keys.current = { save: () => { if (dirty && !saving) save() }, undo: doc.undo, redo: doc.redo, command: runCommand, blocked: !!(picking || finding) }
  })
  // ⌘S on the page arrives right after the words typed there: the save runs
  // once a render has those words in the document, not from this render's.
  const [saveAsked, setSaveAsked] = useState(0)
  useEffect(() => { if (saveAsked) keys.current.save() }, [saveAsked])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (keys.current.blocked) return
      const el = e.target instanceof Element ? e.target : null
      const typingHere = !!el?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')
      const mod = e.metaKey || e.ctrlKey
      if (mod && !e.altKey) {
        const k = e.key.toLowerCase()
        // A field outside the story (Assist's notes) undoes its own typing.
        const own = el?.closest('[data-native-undo]')
        if (k === 's') { e.preventDefault(); keys.current.save(); return }
        if (!own && k === 'z' && !e.shiftKey) { e.preventDefault(); keys.current.undo(); return }
        if (!own && ((k === 'z' && e.shiftKey) || k === 'y')) { e.preventDefault(); keys.current.redo(); return }
      }
      if (typingHere) return
      const cmd = panelKey(e)
      if (cmd) { e.preventDefault(); keys.current.command(cmd) }
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
      case 'mz-heights': {
        const key = artKey({ block: msg.block, item: msg.item })
        setHeights((h) => ({ ...h, [key]: msg.heights }))
        return
      }
      case 'mz-key':
        if (keys.current.blocked) return
        if (msg.key === 'save') setSaveAsked((n) => n + 1)
        else if (msg.key === 'undo') doc.undo()
        else if (msg.key === 'redo') doc.redo()
        else runCommand(msg.key)
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
        // The page already shows it.
        setDrawn(r.doc)
        setDoc((d) => (d ? storyFromMessage(d, msg)?.doc ?? d : d), { step: r.step })
        if (r.select !== undefined) select({ kind: 'block', story: ON_PAGE, block: r.select })
      }
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this story? This can’t be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}/posts/${postId}`)
      navigate(`/cappe/sites/${siteId}/stories`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete')
    }
  }

  const libraryAssets = useMemo(() => [...assets.values()].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')), [assets])

  if (error && !post) return <p role="alert" className="p-8 text-sm text-red-400">{error}</p>
  if (!post || !fields || !options) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>

  const offerPaywall = fields.access === 'paid' && !blocks.some((b) => b.type === 'paywall')

  /** The right-hand panel: everything about what is selected. */
  const inspector = () => {
    const t = target
    if (t?.kind === 'layer') {
      const d = designOf(blocks[t.block], t.item)
      const at = { block: t.block, item: t.item }
      if (d) {
        return (
          <LayerInspector design={d} ids={t.ids} heights={heights[artKey(at)]} accent={accent} onChange={(fn) => changeArt(at, fn)} onCommand={runCommand}
            onReplacePicture={(id) => pickAsset((a) => changeArt(at, (x) => patchLayers(x, [id], { asset_id: a.id } as LayerPatch), true))} />
        )
      }
    }
    if (t?.kind === 'block' && blocks[t.block]) {
      const b = blocks[t.block]
      const item = t.item ?? null
      if (holdsDesign(b, item)) {
        const at = { block: t.block, item }
        return (
          <ArtInspector blocks={blocks} art={at} assets={assets} accent={accent}
            handlers={{
              onText: add.text, onShape: add.shape,
              onImage: () => pickAsset((a) => add.image(a)),
              onSelectLayers: (ids) => select(layerTarget(ON_PAGE, at, ids)),
              onToggle: (id, key) => changeArt(at, (x) => mapLayers(x, [id], (l) => ({ ...l, [key]: !l[key] })), true),
              onRename: (id, name) => changeArt(at, (x) => patchLayers(x, [id], { name } as LayerPatch), true),
              onMoveLayer: (id, to, where) => changeArt(at, (x) => moveLayer(x, id, to, where), true),
            }}
            onBlock={(nb) => setBlocks((bs) => bs.map((x, j) => (j === t.block ? nb : x)))}
            onMove={(dl) => moveTo(t.block, t.block + dl)}
            onDuplicate={() => setBlocks((bs) => duplicateBlock(bs, t.block), true)}
            onRemove={() => removeBlock(t.block)}
            onPickAsset={pickAsset} onClose={() => select(null)}
            onWhole={() => select({ kind: 'block', story: ON_PAGE, block: t.block })} />
        )
      }
      return (
        <BlockPanel block={b} index={t.block} count={blocks.length} minIndex={blocks[0]?.type === 'cover' ? 1 : 0} assets={assets} accent={accent}
          onChange={(nb) => setBlocks((bs) => bs.map((x, j) => (j === t.block ? nb : x)))}
          onMove={(dl) => moveTo(t.block, t.block + dl)}
          onDuplicate={() => setBlocks((bs) => duplicateBlock(bs, t.block), true)}
          onRemove={() => removeBlock(t.block)}
          onPickAsset={pickAsset} onClose={() => select(null)} />
      )
    }
    return (
      <div>
        <PanelHead title="The story" />
        <div className="space-y-4 p-4">
          <p className="text-xs leading-relaxed text-zinc-500">
            Click anything on the pages to change it. Type straight into the headline and the text. Click a picture to lay words, shapes
            and pictures on it, then drag them, resize them from a corner and turn them from the knob. Add things from the left.
          </p>
          <StorySettings fields={fields} options={options} isStory={isStory} paidOn={paidOn} siteId={siteId!} narrow
            onField={setField} onLayout={startFromLayout} />
          <button type="button" onClick={remove} className={`inline-flex items-center gap-2 text-sm ${ui.danger}`}><Trash2 className="h-4 w-4" /> Delete story</button>
        </div>
      </div>
    )
  }

  const panel = () => {
    switch (tab) {
      case 'text': return <TextPanel canArt={!!art} onText={add.text} onBlock={add.block} />
      case 'photos': return <PhotosPanel assets={libraryAssets} canArt={!!art} onUse={add.image} onMore={() => pickAsset((a) => add.image(a))} />
      case 'elements': return <ElementsPanel canArt={!!art} onShape={add.shape} onPage={add.page} onBlock={add.block}
        withCover={blocks[0]?.type !== 'cover'} withPaywall={offerPaywall} />
      case 'layers': return (
        <LayersPanel blocks={blocks} target={target} story={ON_PAGE} assets={assets} onSelect={select}
          onToggle={(at, id, key) => changeArt(at, (x) => mapLayers(x, [id], (l) => ({ ...l, [key]: !l[key] })), true)}
          onRename={(at, id, name) => changeArt(at, (x) => patchLayers(x, [id], { name } as LayerPatch), true)}
          onMoveLayer={(at, id, to, where) => changeArt(at, (x) => moveLayer(x, id, to, where), true)}
          onMoveBlock={moveTo} />
      )
      default: return null
    }
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-4 py-2.5">
        <Link to={`/cappe/sites/${siteId}/stories`} onClick={(e) => { if (!confirmLeave()) e.preventDefault() }}
          className="inline-flex items-center gap-1 text-sm text-zinc-400 hover:text-zinc-100"><ArrowLeft className="h-4 w-4" /> Stories</Link>
        <h1 className="max-w-[16rem] truncate text-sm font-medium text-zinc-100">{fields.title || 'Untitled story'}</h1>
        <span className={`${ui.badge} ${post.status === 'published' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-800 text-zinc-400'}`}>{post.status}</span>
        {post.hidden && <span className={`${ui.badge} bg-red-500/15 text-red-400`}>hidden by Gummfit</span>}
        <span className="text-xs text-zinc-500">{isStory ? `${post.reading_minutes || 0} min read · ${post.word_count} words` : 'Plain post'}</span>
        {isStory && (
          <>
            <Toggle label="Size" value={device} onChange={setDevice} options={[
              { key: 'spread', label: 'Two pages, as on a computer', icon: <Monitor className="h-4 w-4" /> },
              { key: 'phone', label: 'A phone', icon: <Smartphone className="h-4 w-4" /> },
            ]} />
            {!asReader && <Zoom value={zoom} onChange={setZoom} />}
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
          {saved && !dirty && <span className="text-xs text-emerald-400">Saved</span>}
          {dirty && <span className="text-xs text-zinc-500">Unsaved</span>}
          {isStory && <button type="button" className={ui.btnGhost} onClick={() => setAssisting((v) => !v)} aria-pressed={assisting}><Wand2 className="h-4 w-4" /> Assist</button>}
          <button type="button" className={ui.btnGhost} disabled={saving || !dirty} onClick={() => save()} title={`Save (${MOD}S)`}>Save</button>
          {post.status !== 'published'
            ? <button type="button" className={ui.btnPrimary} disabled={saving} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Publish</button>
            : <button type="button" className={ui.btnPrimary} disabled={saving || !dirty} onClick={() => save('published')}>{saving && <Loader2 className="h-4 w-4 animate-spin" />} Update</button>}
        </div>
      </header>
      {error && <p role="alert" className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-300">{error}</p>}

      {assisting && isStory && (
        <div className="max-h-[45vh] overflow-y-auto border-b border-zinc-800 p-5">
          <AssistPanel siteId={siteId!} postId={postId!} title={fields.title} excerpt={fields.excerpt} blocks={blocks}
            assets={assets} onClose={() => setAssisting(false)}
            onHeadline={(h) => setDoc((d) => (d ? { ...d, fields: { ...d.fields, title: h.title, excerpt: h.dek || d.fields.excerpt, kicker: h.kicker || d.fields.kicker } } : d), { step: true })}
            onCaption={(id, caption) => setBlocks((bs) => withCaption(bs, id, caption), true)}
            onAlt={(a) => setAssets((m) => new Map(m).set(a.id, a))}
            onTighten={(i, md, rt) => setBlocks((bs) => withText(bs, i, md, rt), true)}
            onDraft={(dr) => setDoc((d) => (d ? {
              fields: { ...d.fields, title: dr.title || d.fields.title, excerpt: dr.excerpt || d.fields.excerpt, kicker: dr.kicker || d.fields.kicker },
              blocks: dr.content.blocks,
            } : d), { step: true })}
            onFind={setFinding} />
        </div>
      )}

      {!isStory ? (
        <div className="overflow-y-auto p-5">
          <section className={`${ui.card} max-w-3xl space-y-3 p-4`}>
            <p className="text-sm text-zinc-300">This is a plain post written as Markdown. Turn it into a story to lay it out with pictures.</p>
            <textarea value={post.body || ''} readOnly rows={8} className={`${ui.input} font-mono text-[13px] opacity-80`} aria-label="Post body" />
            <button type="button" className={ui.btnPrimary} disabled={saving} onClick={becomeStory}>Turn into a story</button>
          </section>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <nav className="flex w-16 shrink-0 flex-col items-center gap-1 border-r border-zinc-800 bg-zinc-950 py-2" aria-label="Add and arrange">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button key={key} type="button" aria-pressed={tab === key} onClick={() => setTab((v) => (v === key ? null : key))}
                className={`flex w-14 flex-col items-center gap-0.5 rounded-md py-2 text-[10px] ${tab === key ? 'bg-zinc-800 text-zinc-50' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100'}`}>
                <Icon className="h-5 w-5" />{label}
              </button>
            ))}
          </nav>
          {tab && (
            <aside className="w-64 shrink-0 overflow-y-auto border-r border-zinc-800 bg-zinc-950/80" aria-label={TABS.find((x) => x.key === tab)?.label}>
              <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">{TABS.find((x) => x.key === tab)?.label}</h2>
                <button type="button" onClick={() => setTab(null)} aria-label="Close the panel" className="text-zinc-500 hover:text-zinc-200"><X className="h-4 w-4" /></button>
              </div>
              {panel()}
            </aside>
          )}
          <main className="relative min-w-0 flex-1 bg-zinc-950">
            {pageError && !asReader && (
              <p role="alert" className="absolute inset-x-0 top-0 z-10 bg-red-500/90 px-4 py-2 text-sm text-white">
                The page couldn’t be set with the last change: {pageError}
              </p>
            )}
            {asReader
              ? <BookFrame html={preview} title="The story as a reader sees it" keepPlace className="h-full" />
              : <EditFrame html={page} place={place} stories={PAGE_STORIES} device={device} title="The story's pages, to edit"
                  onMessage={onFrame} zoom={zoom} outbox={outbox} />}
          </main>
          <aside className="w-72 shrink-0 overflow-y-auto border-l border-zinc-800 bg-zinc-950/60" aria-label="Selected">
            {inspector()}
          </aside>
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
            <LibraryPanel siteId={siteId!} postId={postId}
              onPick={picking || (finding ? (a: CappeAsset) => { setAssets((m) => new Map(m).set(a.id, a)); add.image(a); setFinding(null) } : undefined)}
              stockQuery={picking ? undefined : finding || undefined} />
          </div>
        </div>
      )}
    </div>
  )
}
