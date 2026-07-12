import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { cappeApi } from '../../../../api/cappeClient'
import type { CappeBlock, CappePage, CappeSite } from '../../../../types/cappe'
import { BLOCK_SCHEMAS } from './blockSchemas'
import { CanvasModeView } from './CanvasModeView'
import { SiteCtx } from './context'
import { usePremium } from './DesignPrimitives'
import { EditorToolbar } from './EditorToolbar'
import { FormModeView } from './FormModeView'
import { ThemeDrawer } from './ThemeMenu'
import { themeObj } from './themeHelpers'
import { useCanvasBridge } from './useCanvasBridge'
import { useEditorHistory } from './useEditorHistory'
import { usePagePreview } from './usePagePreview'
import { useThemeBridge, type ThemeRegion } from './useThemeBridge'
import { useThemeEditor } from './useThemeEditor'

// Stable per-block key so form-mode drag-reorder reconciles correctly (index
// keys would strand each card's local open/collapse state on reorder). Stripped
// before persisting so it never lands in stored `content.blocks`.
const STYLE_CLIP_KEY = 'cappe:styleClipboard'
const genKey = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `k${Math.random().toString(36).slice(2)}`)
const withKey = (b: CappeBlock): CappeBlock => (b._k ? b : { ...b, _k: genKey() })
const withKeys = (bs: CappeBlock[]) => bs.map(withKey)
const stripKeys = (bs: CappeBlock[]) => bs.map((b) => { const r = { ...b }; delete r._k; return r })

export default function PageEditor() {
  const { siteId, pageId } = useParams<{ siteId: string; pageId: string }>()
  const navigate = useNavigate()
  const designerUnlocked = usePremium()

  const [page, setPage] = useState<CappePage | null>(null)
  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<'draft' | 'published'>('draft')
  const [blocks, setBlocks] = useState<CappeBlock[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  // Shared preview iframe ref — both the canvas bridge and the theme bridge
  // postMessage into the same frame, whichever mode is showing it.
  const previewIframeRef = useRef<HTMLIFrameElement>(null)

  // Live theme switching — edited locally, previewed instantly, saved on demand.
  const themeEditor = useThemeEditor()

  // ── Canvas mode (Pro & Business): click-on-page editing via the preview iframe.
  const canvasUnlocked = usePremium()
  const [editMode, setEditMode] = useState<'form' | 'canvas'>('form')
  useEffect(() => { if (canvasUnlocked) setEditMode('canvas') }, [canvasUnlocked])
  // The theme drawer is a real 18rem flex sibling, but the canvas inspector is
  // viewport-`fixed` — tell the bridge to clamp it clear of the drawer.
  const canvas = useCanvasBridge(blocks, setBlocks, previewIframeRef, themeEditor.themeOpen ? 288 : 0)

  // Reverse sync: clicking a page element while the drawer is open probes which
  // theme region governs it; the drawer scrolls to + flashes that control. Only
  // in Form mode — in Canvas mode a page click means "select this section", and
  // hijacking it would silently break canvas editing whenever the drawer is open.
  const [themeProbe, setThemeProbe] = useState<{ region: ThemeRegion; n: number } | null>(null)
  const themeProbeEnabled = themeEditor.themeOpen && editMode === 'form'
  const themeBridge = useThemeBridge(previewIframeRef, themeProbeEnabled, (region) => {
    setThemeProbe((p) => ({ region, n: (p?.n ?? 0) + 1 }))
  })

  // Site-wide promos (announcement bar + pop-up) live on the site's meta_config,
  // edited here with live preview, persisted to the site on Save.
  const [meta, setMeta] = useState<Record<string, unknown>>({})
  const [promosDirty, setPromosDirty] = useState(false)

  // Copy/paste a section's design (`_design`). Persisted to localStorage so it
  // survives page/tab switches. `anchor.id` is dropped on paste (ids stay unique).
  const [styleClip, setStyleClip] = useState<Record<string, unknown> | null>(() => {
    try { const raw = localStorage.getItem(STYLE_CLIP_KEY); return raw ? JSON.parse(raw) : null } catch { return null }
  })

  useEffect(() => {
    if (!siteId || !pageId) return
    Promise.all([
      cappeApi.get<CappePage[]>(`/sites/${siteId}/pages`),
      cappeApi.get<CappeSite>(`/sites/${siteId}`).catch(() => null),
    ])
      .then(([pages, site]) => {
        const p = pages.find((x) => x.id === pageId)
        if (!p) { setError('Page not found'); return }
        setPage(p)
        setTitle(p.title)
        setStatus(p.status === 'published' ? 'published' : 'draft')
        const bs = (p.content?.blocks as CappeBlock[]) || []
        setBlocks(withKeys(Array.isArray(bs) ? bs : []))
        themeEditor.loadTheme(themeObj(site?.theme_config))
        setMeta(themeObj(site?.meta_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load page'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, pageId])

  const preview = usePagePreview(siteId, page, title, blocks, themeEditor.theme, meta, editMode, canvas.refreshTick, canvas.suspendPreview, themeEditor.themeOpen)

  const updateBlock = (i: number, b: CappeBlock) => setBlocks((bs) => bs.map((x, j) => (j === i ? b : x)))
  const removeBlock = (i: number) => { setBlocks((bs) => bs.filter((_, j) => j !== i)); canvas.setSelBlock(null) }
  const moveBlock = (i: number, dir: -1 | 1) =>
    setBlocks((bs) => {
      const j = i + dir
      if (j < 0 || j >= bs.length) return bs
      const next = [...bs]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  // Drag-reorder (form mode): move block from → to.
  const reorderBlock = (from: number, to: number) =>
    setBlocks((bs) => {
      if (from === to || from < 0 || to < 0 || from >= bs.length || to >= bs.length) return bs
      const next = [...bs]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  const addBlock = (type: string) => {
    setBlocks((bs) => [...bs, withKey(BLOCK_SCHEMAS[type].make())])
    setAdding(false)
  }
  // Insert a new block right after index `i` (canvas "add below").
  const addBlockAt = (type: string, i: number) => {
    setBlocks((bs) => { const next = [...bs]; next.splice(i + 1, 0, withKey(BLOCK_SCHEMAS[type].make())); return next })
    canvas.setSelBlock(i + 1)
  }
  // Deep-copy a block (incl. _design + list items) and insert after it. Fresh key.
  const duplicateBlock = (i: number) => {
    setBlocks((bs) => {
      const clone = JSON.parse(JSON.stringify(bs[i])) as CappeBlock
      clone._k = genKey()
      const next = [...bs]; next.splice(i + 1, 0, clone); return next
    })
    canvas.setSelBlock(i + 1)
  }
  // Copy/paste a section's `_design` across blocks.
  const copyStyle = (i: number) => {
    const dz = (blocks[i]?._design as Record<string, unknown>) || {}
    const clip = JSON.parse(JSON.stringify(dz)) as Record<string, unknown>
    setStyleClip(clip)
    try { localStorage.setItem(STYLE_CLIP_KEY, JSON.stringify(clip)) } catch { /* ignore quota */ }
  }
  const pasteStyle = (i: number) => {
    if (!styleClip) return
    const dz = JSON.parse(JSON.stringify(styleClip)) as Record<string, unknown>
    delete dz.anchor // ids must stay unique per page
    setBlocks((bs) => bs.map((x, j) => (j === i ? { ...x, _design: dz } : x)))
  }

  // ── Undo / redo (blocks + title + meta + theme) ────────────────────────────
  const history = useEditorHistory(
    { blocks, title, meta, theme: themeEditor.theme },
    (s) => { setBlocks(s.blocks); setTitle(s.title); setMeta(s.meta); themeEditor.loadTheme(s.theme); themeEditor.markDirty() },
  )
  const historyRef = useRef(history)
  historyRef.current = history
  // Reset history baseline once the page has loaded so the first undo doesn't
  // rewind into the empty pre-load state.
  useEffect(() => {
    if (page) historyRef.current.reset({ blocks, title, meta, theme: themeEditor.theme })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page?.id])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return
      // Don't hijack undo while typing into the on-page canvas contenteditable.
      const el = document.activeElement
      if (el && (el as HTMLElement).isContentEditable) return
      e.preventDefault()
      if (e.shiftKey) historyRef.current.redo(); else historyRef.current.undo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  async function save() {
    if (!siteId || !pageId) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await cappeApi.put<CappePage>(`/sites/${siteId}/pages/${pageId}`, {
        title,
        status,
        content: { blocks: stripKeys(blocks) },
      })
      setPage(updated)
      // Persist the theme + promos (meta_config) to the site too, if changed here.
      if (themeEditor.themeDirty || promosDirty) {
        const patch: Record<string, unknown> = {}
        if (themeEditor.themeDirty) patch.theme_config = themeEditor.theme
        if (promosDirty) patch.meta_config = meta
        await cappeApi.put<CappeSite>(`/sites/${siteId}`, patch)
        themeEditor.markClean()
        setPromosDirty(false)
      }
      setNotice('Saved.')
      setTimeout(() => setNotice(null), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
  }
  if (!page) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <p className="text-sm text-red-400">{error || 'Page not found.'}</p>
        <Link to={`/cappe/sites/${siteId}`} className="mt-4 inline-flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
          <ArrowLeft className="h-4 w-4" /> Back to site
        </Link>
      </div>
    )
  }

  return (
    <SiteCtx.Provider value={siteId || ''}>
      <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
        <EditorToolbar
          title={title}
          setTitle={setTitle}
          slug={page.slug}
          notice={notice}
          error={error}
          meta={meta}
          setMeta={setMeta}
          promosDirty={promosDirty}
          setPromosDirty={setPromosDirty}
          designerUnlocked={designerUnlocked}
          themeEditor={themeEditor}
          canvasUnlocked={canvasUnlocked}
          editMode={editMode}
          setEditMode={setEditMode}
          status={status}
          setStatus={setStatus}
          saving={saving}
          onSave={save}
          onBack={() => navigate(`/cappe/sites/${siteId}`)}
          onUndo={history.undo}
          onRedo={history.redo}
          canUndo={history.canUndo}
          canRedo={history.canRedo}
        />

        {/* Theme drawer is a flex sibling of the preview/canvas (not a fixed
            overlay), so its width composes into the row instead of stacking
            on top of whatever else is already docked there. */}
        <div className="flex min-h-0 flex-1">
        {editMode === 'canvas' ? (
          /* canvas: click a section on the page → a floating editor pops up at it (Pro & Business) */
          <CanvasModeView
            preview={preview}
            blocks={blocks}
            canvas={canvas}
            updateBlock={updateBlock}
            moveBlock={moveBlock}
            removeBlock={removeBlock}
            duplicateBlock={duplicateBlock}
            addBlockAt={addBlockAt}
            addBlock={addBlock}
          />
        ) : (
          /* split: form editor | live preview */
          <FormModeView
            blocks={blocks}
            preview={preview}
            adding={adding}
            setAdding={setAdding}
            canvasUnlocked={canvasUnlocked}
            iframeRef={previewIframeRef}
            updateBlock={updateBlock}
            removeBlock={removeBlock}
            moveBlock={moveBlock}
            reorderBlock={reorderBlock}
            duplicateBlock={duplicateBlock}
            addBlock={addBlock}
            copyStyle={copyStyle}
            pasteStyle={pasteStyle}
            canPasteStyle={!!styleClip}
          />
        )}
        <ThemeDrawer themeEditor={themeEditor} designerUnlocked={designerUnlocked} bridge={themeBridge} probe={themeProbe} />
        </div>
      </div>
    </SiteCtx.Provider>
  )
}
