// Flyer designer for one promo campaign.
//
// Composition root for the designer: owns the document + history, the fonts
// gate, autosave, and the keyboard map. The canvas, panels and export menu are
// all controlled — they never hold document state of their own.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import type Konva from 'konva'
import { tellusApi } from '../../api/tellusClient'
import { promoApi } from '../../api/promo'
import type { ArtboardPreset, Brand, DesignLayer, FlyerDesign, PromoCampaign, StickerManifestEntry } from '../../api/types'
import { Button, ErrorText, Spinner } from '../../components/ui'
import { AssetPanel } from '../../components/designer/AssetPanel'
import { DesignerCanvas } from '../../components/designer/DesignerCanvas'
import { ExportMenu } from '../../components/designer/ExportMenu'
import { InspectorPanel } from '../../components/designer/InspectorPanel'
import { Toolbar } from '../../components/designer/Toolbar'
import { useDesignHistory } from '../../hooks/useDesignHistory'
import { useDesignerFonts } from '../../hooks/useDesignerFonts'
import { useTextEditOverlay } from '../../hooks/useTextEditOverlay'
import {
  ARTBOARD_PRESETS, ASSET_BASE, blankDesign, instantiateTemplate, makeImageLayer, makeQrLayer,
  makeShapeLayer, makeStickerLayer, makeTextLayer, newLayerId,
} from '../../utils/designer'

const AUTOSAVE_MS = 2000

function stickerSrc(assetId: string) {
  return `${ASSET_BASE}/stickers/${assetId}`
}

export default function CampaignDesigner() {
  const { id = '' } = useParams()
  const stageRef = useRef<Konva.Stage>(null)

  const [campaign, setCampaign] = useState<PromoCampaign | null>(null)
  const [brand, setBrand] = useState<Brand | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')
  const [saveErr, setSaveErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const history = useDesignHistory(blankDesign())
  const { design, set, reset, undo, redo, canUndo, canRedo, dirty, markSaved } = history
  const { fonts, ready: fontsReady, ensureLoaded } = useDesignerFonts()
  const editor = useTextEditOverlay()

  const claimUrl = campaign ? `${window.location.origin}${campaign.claim_url}` : ''
  const hasQr = design.layers.some((l) => l.type === 'qr')

  // Fonts must be resolved BEFORE the stage first draws, or Konva bakes
  // fallback metrics into the text layout and the export wraps differently
  // than the preview did.
  const families = useMemo(
    () => design.layers.filter((l) => l.type === 'text').map((l) => l.fontFamily),
    [design.layers],
  )
  useEffect(() => { if (fontsReady) void ensureLoaded(families) }, [fontsReady, families, ensureLoaded])

  useEffect(() => {
    let alive = true
    void (async () => {
      setLoading(true); setLoadErr('')
      try {
        const [c, b, d] = await Promise.all([
          promoApi.getCampaign(id),
          tellusApi.get<Brand>('/brand').catch(() => null),
          promoApi.getDesign(id),
        ])
        if (!alive) return
        setCampaign(c)
        setBrand(b)
        // A campaign with no saved design opens on a starter document seeded
        // from its own copy — an empty artboard is a worse first screen than
        // something the brand can immediately edit.
        reset(d.design_json ?? starterDesign(c, b?.logo_url ?? null))
      } catch (e) {
        if (alive) setLoadErr(e instanceof Error ? e.message : 'Could not load this campaign')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [id, reset])

  const save = useCallback(async () => {
    setSaving(true); setSaveErr('')
    try {
      await promoApi.saveDesign(id, design)
      markSaved()
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : 'Could not save the design')
    } finally {
      setSaving(false)
    }
  }, [id, design, markSaved])

  // Debounced autosave. Keyed on `design` so a burst of edits collapses into
  // one PUT; the manual Save button shares the same path.
  useEffect(() => {
    if (!dirty || loading) return
    const t = setTimeout(() => { void save() }, AUTOSAVE_MS)
    return () => clearTimeout(t)
  }, [dirty, loading, save])

  useEffect(() => {
    if (!dirty) return
    function warn(e: BeforeUnloadEvent) { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // ---- document mutations (every one commits: discrete user actions) ----

  const patchLayer = useCallback((layerId: string, patch: Partial<DesignLayer>, commit: boolean) => {
    set({
      ...design,
      layers: design.layers.map((l) => (l.id === layerId ? ({ ...l, ...patch } as DesignLayer) : l)),
    }, { commit })
  }, [design, set])

  function addLayer(layer: DesignLayer) {
    set({ ...design, layers: [...design.layers, layer] }, { commit: true })
    setSelectedId(layer.id)
  }

  function deleteLayer(layerId: string) {
    set({ ...design, layers: design.layers.filter((l) => l.id !== layerId) }, { commit: true })
    setSelectedId((s) => (s === layerId ? null : s))
  }

  function duplicateLayer(layerId: string) {
    const src = design.layers.find((l) => l.id === layerId)
    if (!src) return
    const copy = { ...src, id: newLayerId(), x: src.x + 24, y: src.y + 24 } as DesignLayer
    addLayer(copy)
  }

  function reorderLayer(layerId: string, direction: 'up' | 'down') {
    const i = design.layers.findIndex((l) => l.id === layerId)
    const j = direction === 'up' ? i + 1 : i - 1
    if (i < 0 || j < 0 || j >= design.layers.length) return
    const layers = [...design.layers]
    ;[layers[i], layers[j]] = [layers[j], layers[i]]
    set({ ...design, layers }, { commit: true })
  }

  function applyPreset(preset: ArtboardPreset) {
    const { w, h } = ARTBOARD_PRESETS[preset]
    set({ ...design, artboard: { preset, w, h } }, { commit: true })
  }

  function commitTextEdit() {
    const pending = editor.commit()
    if (!pending) return
    const layer = design.layers.find((l) => l.id === pending.layerId)
    if (!layer || layer.type !== 'text' || layer.text === pending.text) return
    patchLayer(pending.layerId, { text: pending.text } as Partial<DesignLayer>, true)
  }

  // ---- keyboard ----
  // Suppressed entirely while the text overlay is open (Escape/Enter are
  // handled by the textarea) and whenever focus is in a panel input, or typing
  // a font size would delete the selected layer.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (editor.editing) return
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) redo(); else undo()
        return
      }
      if (mod && e.key.toLowerCase() === 'd') {
        e.preventDefault()
        if (selectedId) duplicateLayer(selectedId)
        return
      }
      if (!selectedId) return
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteLayer(selectedId); return }
      const step = e.shiftKey ? 10 : 1
      const nudge: Record<string, [number, number]> = {
        ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
      }
      const delta = nudge[e.key]
      if (!delta) return
      e.preventDefault()
      const layer = design.layers.find((l) => l.id === selectedId)
      if (!layer) return
      patchLayer(selectedId, { x: layer.x + delta[0], y: layer.y + delta[1] } as Partial<DesignLayer>, true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (loading || !fontsReady) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  if (loadErr || !campaign) {
    return (
      <div className="mx-auto max-w-md space-y-4 p-8 text-center">
        <ErrorText>{loadErr || 'Campaign not found.'}</ErrorText>
        <Link to="/brand/campaigns"><Button variant="soft">Back to campaigns</Button></Link>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-tu-bg text-tu-text">
      <div className="flex items-center gap-3 border-b border-tu-border bg-tu-panel px-3 py-2">
        <Link to="/brand/campaigns" className="text-tu-faint hover:text-tu-text"><ArrowLeft className="h-4 w-4" /></Link>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{campaign.title}</p>
          <p className="truncate text-xs text-tu-faint">{campaign.reward_text}</p>
        </div>
        <div className="ml-auto">
          <ExportMenu
            stageRef={stageRef}
            campaignId={id}
            design={design}
            ensureFonts={() => ensureLoaded(families)}
            onFlyerSaved={(url) => setCampaign((c) => (c ? { ...c, flyer_image_url: url } : c))}
          />
        </div>
      </div>

      <Toolbar
        onAddText={() => addLayer(makeTextLayer(design, 'Your headline'))}
        onAddShape={(shape) => addLayer(makeShapeLayer(design, shape))}
        onAddQr={() => addLayer(makeQrLayer(design))}
        onUndo={undo}
        onRedo={redo}
        canUndo={canUndo}
        canRedo={canRedo}
        dirty={dirty}
        saving={saving}
        onSave={() => void save()}
        hasQr={hasQr}
      />
      {saveErr && <div className="border-b border-tu-border bg-tu-panel px-3 py-1.5"><ErrorText>{saveErr}</ErrorText></div>}

      <div className="flex min-h-0 flex-1">
        <AssetPanel
          design={design}
          brandLogoUrl={brand?.logo_url ?? null}
          stickerSrc={stickerSrc}
          onApplyTemplate={(t) => {
            set(instantiateTemplate(t, brand?.logo_url ?? null), { commit: true })
            setSelectedId(null)
          }}
          onAddSticker={(s: StickerManifestEntry) => addLayer(makeStickerLayer(design, s.file, s.w, s.h))}
          onAddLogo={() => { if (brand?.logo_url) addLayer(makeImageLayer(design, brand.logo_url, 512, 512, 'logo')) }}
          onSetBackgroundColor={(color) => set({ ...design, background: { kind: 'color', color } }, { commit: true })}
          onSetPreset={applyPreset}
        />

        <DesignerCanvas
          design={design}
          selectedId={selectedId}
          onSelect={(sid) => { commitTextEdit(); setSelectedId(sid) }}
          onLayerChange={patchLayer}
          onBeginTextEdit={(layer, node) => { setSelectedId(layer.id); editor.begin(layer, node) }}
          claimUrl={claimUrl}
          stickerSrc={stickerSrc}
          stageRef={stageRef}
          editingLayerId={editor.editing?.layerId ?? null}
          overlay={editor.editing && (
            <textarea
              autoFocus
              value={editor.editing.value}
              style={editor.editing.style}
              onChange={(e) => editor.onChange(e.target.value)}
              onBlur={commitTextEdit}
              onKeyDown={(e) => {
                if (e.key === 'Escape') { e.preventDefault(); editor.cancel() }
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commitTextEdit() }
              }}
            />
          )}
        />

        <InspectorPanel
          design={design}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onLayerChange={(layerId, p) => patchLayer(layerId, p, true)}
          onDelete={deleteLayer}
          onDuplicate={duplicateLayer}
          onReorder={reorderLayer}
          fonts={fonts}
        />
      </div>
    </div>
  )
}

// Starter document for a campaign that has never been designed: the campaign's
// own title/reward plus the claim QR, so the first screen is already a
// printable flyer rather than a blank page.
function starterDesign(campaign: PromoCampaign, logoUrl: string | null): FlyerDesign {
  const base = blankDesign('flyer_letter')
  const layers: DesignLayer[] = []
  if (logoUrl) layers.push(makeImageLayer(base, logoUrl, 512, 512, 'logo'))
  layers.push(makeTextLayer(base, campaign.title, { y: Math.round(base.artboard.h * 0.28), fontSize: 96 }))
  layers.push(makeTextLayer(base, campaign.reward_text, {
    y: Math.round(base.artboard.h * 0.44), fontSize: 52, fontStyle: 'normal', fill: '#4b4436',
  }))
  layers.push(makeTextLayer(base, 'Scan to claim', {
    y: Math.round(base.artboard.h * 0.58), fontSize: 34, fontStyle: 'normal', fill: '#8a8371',
  }))
  layers.push(makeQrLayer(base))
  return { ...base, layers }
}
