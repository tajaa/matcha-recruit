import { useEffect, useState } from 'react'
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
import { themeObj } from './themeHelpers'
import { useCanvasBridge } from './useCanvasBridge'
import { usePagePreview } from './usePagePreview'
import { useThemeEditor } from './useThemeEditor'

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

  // ── Canvas mode (Pro & Business): click-on-page editing via the preview iframe.
  const canvasUnlocked = usePremium()
  const [editMode, setEditMode] = useState<'form' | 'canvas'>('form')
  useEffect(() => { if (canvasUnlocked) setEditMode('canvas') }, [canvasUnlocked])
  const canvas = useCanvasBridge(blocks, setBlocks)

  // Live theme switching — edited locally, previewed instantly, saved on demand.
  const themeEditor = useThemeEditor()

  // Site-wide promos (announcement bar + pop-up) live on the site's meta_config,
  // edited here with live preview, persisted to the site on Save.
  const [meta, setMeta] = useState<Record<string, unknown>>({})
  const [promosDirty, setPromosDirty] = useState(false)

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
        setBlocks(Array.isArray(bs) ? bs : [])
        themeEditor.loadTheme(themeObj(site?.theme_config))
        setMeta(themeObj(site?.meta_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load page'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, pageId])

  const preview = usePagePreview(siteId, page, title, blocks, themeEditor.theme, meta, editMode, canvas.refreshTick, canvas.suspendPreview)

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
  const addBlock = (type: string) => {
    setBlocks((bs) => [...bs, BLOCK_SCHEMAS[type].make()])
    setAdding(false)
  }
  // Insert a new block right after index `i` (canvas "add below").
  const addBlockAt = (type: string, i: number) => {
    setBlocks((bs) => { const next = [...bs]; next.splice(i + 1, 0, BLOCK_SCHEMAS[type].make()); return next })
    canvas.setSelBlock(i + 1)
  }
  // Deep-copy a block (incl. _design + list items) and insert after it.
  const duplicateBlock = (i: number) => {
    setBlocks((bs) => {
      const clone = JSON.parse(JSON.stringify(bs[i])) as CappeBlock
      const next = [...bs]; next.splice(i + 1, 0, clone); return next
    })
    canvas.setSelBlock(i + 1)
  }

  async function save() {
    if (!siteId || !pageId) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await cappeApi.put<CappePage>(`/sites/${siteId}/pages/${pageId}`, {
        title,
        status,
        content: { blocks },
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
        />

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
            updateBlock={updateBlock}
            removeBlock={removeBlock}
            moveBlock={moveBlock}
            addBlock={addBlock}
          />
        )}
      </div>
    </SiteCtx.Provider>
  )
}
