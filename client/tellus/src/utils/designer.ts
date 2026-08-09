// Flyer-designer document helpers — artboard geometry, layer factories, and
// template instantiation. Pure functions only; nothing here touches Konva or
// the DOM so the designer page and the export path can share them.
import type { ArtboardPreset, DesignLayer, FlyerDesign } from '../api/types'

// Vite's base is '/tellus/', so files under client/tellus/public/designer/ are
// served here. Moving the pack to S3/CloudFront later is a one-line change.
export const ASSET_BASE = '/tellus/designer'

// Artboards are stored in PRINT pixels, not screen pixels: 1275x1650 is US
// Letter at 150dpi. That makes a 150dpi export a straight 1:1 stage capture
// and a 300dpi export pixelRatio 2 — no unit conversion anywhere else.
export const ARTBOARD_PRESETS: Record<ArtboardPreset, { w: number; h: number; label: string }> = {
  flyer_letter: { w: 1275, h: 1650, label: 'Flyer — US Letter' },
  reward_card: { w: 1050, h: 600, label: 'Reward card' },
  social_square: { w: 1080, h: 1080, label: 'Social square' },
  story: { w: 1080, h: 1920, label: 'Story' },
}

export function newLayerId(): string {
  return crypto.randomUUID()
}

export function blankDesign(preset: ArtboardPreset = 'flyer_letter'): FlyerDesign {
  const { w, h } = ARTBOARD_PRESETS[preset]
  return {
    version: 1,
    artboard: { preset, w, h },
    background: { kind: 'color', color: '#f3ede0' },
    layers: [],
  }
}

const LAYER_BASE = { rotation: 0, opacity: 1 }

// Factories place a new layer roughly centred on the artboard — the canvas has
// no cursor position to drop against (layers are added from the toolbar).
export function makeTextLayer(design: FlyerDesign, text: string, over?: Partial<Extract<DesignLayer, { type: 'text' }>>): DesignLayer {
  const width = Math.round(design.artboard.w * 0.7)
  return {
    ...LAYER_BASE,
    id: newLayerId(),
    type: 'text',
    x: Math.round((design.artboard.w - width) / 2),
    y: Math.round(design.artboard.h * 0.4),
    text,
    fontFamily: 'Helvetica Neue',
    fontSize: Math.round(design.artboard.h * 0.05),
    fontStyle: 'bold',
    fill: '#17140f',
    align: 'center',
    width,
    lineHeight: 1.2,
    letterSpacing: 0,
    ...over,
  }
}

export function makeShapeLayer(design: FlyerDesign, shape: 'rect' | 'circle' | 'line'): DesignLayer {
  const size = Math.round(Math.min(design.artboard.w, design.artboard.h) * 0.25)
  return {
    ...LAYER_BASE,
    id: newLayerId(),
    type: 'shape',
    shape,
    x: Math.round((design.artboard.w - size) / 2),
    y: Math.round((design.artboard.h - size) / 2),
    width: size,
    height: shape === 'line' ? 8 : size,
    fill: '#f97316',
    cornerRadius: shape === 'rect' ? 16 : 0,
  }
}

export function makeStickerLayer(design: FlyerDesign, assetId: string, w: number, h: number): DesignLayer {
  const scale = Math.min(1, (design.artboard.w * 0.3) / w)
  return {
    ...LAYER_BASE,
    id: newLayerId(),
    type: 'sticker',
    assetId,
    x: Math.round((design.artboard.w - w * scale) / 2),
    y: Math.round((design.artboard.h - h * scale) / 2),
    width: Math.round(w * scale),
    height: Math.round(h * scale),
  }
}

export function makeImageLayer(design: FlyerDesign, src: string, w: number, h: number, slot?: 'logo'): DesignLayer {
  const target = design.artboard.w * (slot === 'logo' ? 0.25 : 0.5)
  const scale = target / w
  return {
    ...LAYER_BASE,
    id: newLayerId(),
    type: 'image',
    src,
    x: Math.round((design.artboard.w - w * scale) / 2),
    y: slot === 'logo' ? Math.round(design.artboard.h * 0.06) : Math.round((design.artboard.h - h * scale) / 2),
    width: Math.round(w * scale),
    height: Math.round(h * scale),
    slot,
  }
}

export function makeQrLayer(design: FlyerDesign): DesignLayer {
  const size = Math.round(design.artboard.w * 0.32)
  return {
    ...LAYER_BASE,
    id: newLayerId(),
    type: 'qr',
    x: Math.round((design.artboard.w - size) / 2),
    y: Math.round(design.artboard.h - size - design.artboard.h * 0.08),
    size,
    fg: '#17140f',
    bg: '#ffffff',
  }
}

// A template is a plain FlyerDesign fetched from the asset pack. Ids are
// regenerated so two instantiations of the same template can't collide, and
// the brand's own logo is swapped into any slot:'logo' image layer. A template
// with a logo slot but no brand logo drops the layer rather than rendering the
// placeholder art.
export function instantiateTemplate(template: FlyerDesign, logoUrl: string | null): FlyerDesign {
  const layers: DesignLayer[] = []
  for (const raw of template.layers) {
    const layer = { ...raw, id: newLayerId() } as DesignLayer
    if (layer.type === 'image' && layer.slot === 'logo') {
      if (!logoUrl) continue
      layers.push({ ...layer, src: logoUrl })
      continue
    }
    layers.push(layer)
  }
  return {
    version: 1,
    artboard: { ...template.artboard },
    background: { ...template.background },
    layers,
  }
}

export function layerLabel(layer: DesignLayer): string {
  switch (layer.type) {
    case 'text':
      return layer.text.slice(0, 24) || 'Text'
    case 'image':
      return layer.slot === 'logo' ? 'Logo' : 'Image'
    case 'sticker':
      return 'Sticker'
    case 'shape':
      return layer.shape === 'rect' ? 'Rectangle' : layer.shape === 'circle' ? 'Circle' : 'Line'
    case 'qr':
      return 'Claim QR'
  }
}

// Konva reports resize as a scale on the node; the document model stores real
// width/height instead so font metrics and export math stay in artboard units.
export function applyScaleToSize(layer: DesignLayer, scaleX: number, scaleY: number): Partial<DesignLayer> {
  if (layer.type === 'qr') return { size: Math.max(48, Math.round(layer.size * Math.max(scaleX, scaleY))) } as Partial<DesignLayer>
  if (layer.type === 'text') {
    return {
      width: Math.max(24, Math.round(layer.width * scaleX)),
      fontSize: Math.max(8, Math.round(layer.fontSize * scaleY)),
    } as Partial<DesignLayer>
  }
  return {
    width: Math.max(8, Math.round(layer.width * scaleX)),
    height: Math.max(8, Math.round(layer.height * scaleY)),
  } as Partial<DesignLayer>
}
