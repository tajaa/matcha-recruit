// Left rail: templates, stickers, and brand/artboard settings.
//
// Template thumbnails are LIVE miniatures — the same renderer as the canvas at
// a small scale — so a template edit can never leave a stale baked thumb
// behind. Manifest entries may still carry a `thumb` path; when they do it is
// used instead (cheaper for a large pack).
import { useEffect, useState } from 'react'
import { Layer, Stage } from 'react-konva'
import { Image as ImageIcon, LayoutTemplate, Palette, Sticker as StickerIcon } from 'lucide-react'
import type { ArtboardPreset, FlyerDesign, StickerManifestEntry, TemplateManifestEntry } from '../../api/types'
import { ARTBOARD_PRESETS, ASSET_BASE } from '../../utils/designer'
import { Button, ErrorText, Select } from '../ui'
import { BackgroundNode, LayerNode } from './LayerRenderer'

const PREVIEW_W = 132

type Tab = 'templates' | 'stickers' | 'brand'

function TemplatePreview({ design, stickerSrc }: { design: FlyerDesign; stickerSrc: (id: string) => string }) {
  const scale = PREVIEW_W / design.artboard.w
  return (
    <Stage
      width={PREVIEW_W}
      height={Math.round(design.artboard.h * scale)}
      scaleX={scale}
      scaleY={scale}
      listening={false}
    >
      <Layer listening={false}>
        <BackgroundNode design={design} />
        {design.layers.map((l) => (
          <LayerNode
            key={l.id}
            layer={l}
            stickerSrc={stickerSrc}
            qrCanvas={() => undefined}
            draggable={false}
            listening={false}
          />
        ))}
      </Layer>
    </Stage>
  )
}

export interface AssetPanelProps {
  design: FlyerDesign
  brandLogoUrl: string | null
  onApplyTemplate: (template: FlyerDesign) => void
  onAddSticker: (entry: StickerManifestEntry) => void
  onAddLogo: () => void
  onSetBackgroundColor: (color: string) => void
  onSetPreset: (preset: ArtboardPreset) => void
  stickerSrc: (assetId: string) => string
}

export function AssetPanel({
  design, brandLogoUrl, onApplyTemplate, onAddSticker, onAddLogo, onSetBackgroundColor, onSetPreset, stickerSrc,
}: AssetPanelProps) {
  const [tab, setTab] = useState<Tab>('templates')
  const [templates, setTemplates] = useState<{ entry: TemplateManifestEntry; design: FlyerDesign }[]>([])
  const [stickers, setStickers] = useState<StickerManifestEntry[]>([])
  const [assetErr, setAssetErr] = useState('')

  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        const [tRes, sRes] = await Promise.all([
          fetch(`${ASSET_BASE}/templates/index.json`),
          fetch(`${ASSET_BASE}/stickers/index.json`),
        ])
        if (tRes.ok) {
          const list = (await tRes.json()) as TemplateManifestEntry[]
          const loaded = await Promise.all(list.map(async (entry) => {
            const r = await fetch(`${ASSET_BASE}/templates/${entry.file}`)
            return r.ok ? { entry, design: (await r.json()) as FlyerDesign } : null
          }))
          if (alive) setTemplates(loaded.filter((x): x is { entry: TemplateManifestEntry; design: FlyerDesign } => !!x))
        }
        if (sRes.ok && alive) setStickers((await sRes.json()) as StickerManifestEntry[])
      } catch {
        if (alive) setAssetErr('Could not load the design asset pack.')
      }
    })()
    return () => { alive = false }
  }, [])

  const tabs: { id: Tab; label: string; icon: typeof LayoutTemplate }[] = [
    { id: 'templates', label: 'Templates', icon: LayoutTemplate },
    { id: 'stickers', label: 'Stickers', icon: StickerIcon },
    { id: 'brand', label: 'Brand', icon: Palette },
  ]

  return (
    <div className="flex h-full w-60 shrink-0 flex-col border-r border-tu-border bg-tu-panel">
      <div className="flex border-b border-tu-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex flex-1 items-center justify-center gap-1 py-2 text-xs font-medium transition ${
              tab === t.id ? 'border-b-2 border-tu-accent text-tu-text' : 'text-tu-faint hover:text-tu-dim'
            }`}
          >
            <t.icon className="h-3.5 w-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        <ErrorText>{assetErr}</ErrorText>

        {tab === 'templates' && (
          templates.length === 0 ? <p className="text-xs text-tu-faint">No templates in the asset pack.</p> : (
            <div className="space-y-3">
              {templates.map(({ entry, design: t }) => (
                <button
                  key={entry.id}
                  onClick={() => onApplyTemplate(t)}
                  className="block w-full overflow-hidden rounded-lg border border-tu-border transition hover:border-tu-accent"
                  title={`Replace the canvas with "${entry.name}"`}
                >
                  {entry.thumb
                    ? <img src={`${ASSET_BASE}/templates/${entry.thumb}`} alt="" className="w-full" />
                    : <TemplatePreview design={t} stickerSrc={stickerSrc} />}
                  <span className="block px-2 py-1.5 text-left text-xs text-tu-dim">{entry.name}</span>
                </button>
              ))}
            </div>
          )
        )}

        {tab === 'stickers' && (
          stickers.length === 0 ? <p className="text-xs text-tu-faint">No stickers in the asset pack.</p> : (
            <div className="grid grid-cols-3 gap-2">
              {stickers.map((s) => (
                <button
                  key={s.id}
                  onClick={() => onAddSticker(s)}
                  className="aspect-square rounded-lg border border-tu-border bg-tu-panel2 p-1.5 transition hover:border-tu-accent"
                >
                  <img src={`${ASSET_BASE}/stickers/${s.thumb || s.file}`} alt={s.id} className="h-full w-full object-contain" />
                </button>
              ))}
            </div>
          )
        )}

        {tab === 'brand' && (
          <div className="space-y-4">
            <Button size="sm" variant="soft" className="w-full" onClick={onAddLogo} disabled={!brandLogoUrl}>
              <ImageIcon className="h-3.5 w-3.5" /> {brandLogoUrl ? 'Add brand logo' : 'No logo on file'}
            </Button>
            {!brandLogoUrl && <p className="text-xs text-tu-faint">Upload a logo under Settings to place it on the flyer.</p>}

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-tu-dim">Background</span>
              <input
                type="color"
                value={design.background.kind === 'color' ? design.background.color : '#ffffff'}
                onChange={(e) => onSetBackgroundColor(e.target.value)}
                className="h-9 w-full cursor-pointer rounded-lg border border-tu-border bg-tu-panel2"
              />
            </label>

            <Select
              label="Artboard"
              value={design.artboard.preset}
              onChange={(e) => onSetPreset(e.target.value as ArtboardPreset)}
              options={Object.entries(ARTBOARD_PRESETS).map(([value, v]) => ({ value, label: v.label }))}
            />
            <p className="text-xs text-tu-faint">
              Changing the artboard resizes the page. Layers keep their position, so check the layout after switching.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
