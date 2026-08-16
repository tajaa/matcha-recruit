// Flyer-designer document helpers — artboard geometry, layer factories, and
// template instantiation. Pure functions only; nothing here touches Konva or
// the DOM so the designer page and the export path can share them.
import type { ArtboardPreset, DesignLayer, FlyerDesign, FlyerPalette, FlyerPaletteToken } from '../api/types'

// Vite's base is '/tellus/', so files under client/tellus/public/designer/ are
// served here. Moving the pack to S3/CloudFront later is a one-line change.
export const ASSET_BASE = '/tellus/designer'

// The palette a document falls back to when it carries none of its own, and
// the vocabulary every colour field may name instead of a hex literal.
export const DEFAULT_PALETTE: FlyerPalette = {
  ink: '#17140f',
  paper: '#f3ede0',
  brand: '#f97316',
  brandSoft: '#fb923c',
  accent: '#34d399',
  muted: '#8a8371',
}

export const PALETTE_TOKENS = Object.keys(DEFAULT_PALETTE) as FlyerPaletteToken[]

// Resolve a stored colour to something a renderer can paint.
//
// Anything starting '#' is a literal and passes through untouched — that is
// what keeps hand-picked colours working alongside tokens. A token missing from
// the document's own palette falls back to the default one rather than to
// nothing: a palette written by an older build (or a partial one) should lose
// the custom shade, not paint the layer black.
export function resolveColor(palette: FlyerPalette | undefined, value: string): string {
  if (!value) return DEFAULT_PALETTE.ink
  if (value.charCodeAt(0) === 35 /* '#' */) return value
  const token = value as FlyerPaletteToken
  return palette?.[token] ?? DEFAULT_PALETTE[token] ?? DEFAULT_PALETTE.ink
}

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
    background: { kind: 'color', color: 'paper' },
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
    fill: 'ink',
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
    fill: 'brand',
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
    // Literals, not tokens, and deliberately so. Everywhere else on the flyer a
    // palette swap is a taste change; on the QR it is a scanning requirement.
    // `ink` on `paper` looks like a safe pair until a dark palette inverts them
    // — midnight's ink is near-white, which on a white pad is a code no scanner
    // will read, on a flyer that still looks finished. The AI catalog may set
    // these, but only through a contrast check.
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
    ...(template.palette ? { palette: { ...template.palette } } : {}),
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

// The layer's occupied box in artboard units. One definition for snapping,
// clamping and bounds tests — a text layer's height is derived (fontSize *
// lineHeight) rather than stored, which is the only case worth a branch.
export function layerBox(layer: DesignLayer): { w: number; h: number } {
  if (layer.type === 'qr') return { w: layer.size, h: layer.size }
  if (layer.type === 'text') return { w: layer.width, h: layer.fontSize * layer.lineHeight }
  return { w: layer.width, h: layer.height }
}

function clampIntoArtboard(layer: DesignLayer, w: number, h: number): DesignLayer {
  const box = layerBox(layer)
  return {
    ...layer,
    x: Math.round(Math.min(Math.max(layer.x, 0), Math.max(0, w - box.w))),
    y: Math.round(Math.min(Math.max(layer.y, 0), Math.max(0, h - box.h))),
  } as DesignLayer
}

// Switching artboard preset has to carry the layers with it. Rewriting w/h
// alone leaves every layer at its old coordinates, and the Stage clips to the
// artboard — so going flyer_letter (1275x1650) -> reward_card (1050x600) put
// the claim QR at y~1110, entirely off-canvas, while the document still
// contained a QR layer. The result was a finished-looking flyer with nothing
// scannable on it. Positions scale per axis, sizes by the smaller factor (a QR
// stays square, nothing outgrows the new artboard), then everything is clamped
// back inside.
export function retargetArtboard(design: FlyerDesign, preset: ArtboardPreset): FlyerDesign {
  const { w, h } = ARTBOARD_PRESETS[preset]
  const { w: ow, h: oh } = design.artboard
  if (ow === w && oh === h) return { ...design, artboard: { preset, w, h } }

  const sx = w / ow
  const sy = h / oh
  const s = Math.min(sx, sy)
  const layers = design.layers.map((layer) => {
    const moved = { ...layer, x: Math.round(layer.x * sx), y: Math.round(layer.y * sy) } as DesignLayer
    const resized = { ...moved, ...applyScaleToSize(moved, s, s) } as DesignLayer
    return clampIntoArtboard(resized, w, h)
  })
  return { ...design, artboard: { preset, w, h }, layers }
}

// "Does this document have a USABLE claim QR" — a layer parked outside the
// artboard is clipped away at render and export, so counting it would leave
// the toolbar refusing to add the replacement the flyer actually needs.
export function hasQrInBounds(design: FlyerDesign): boolean {
  return design.layers.some((layer) => {
    if (layer.type !== 'qr') return false
    const { w, h } = layerBox(layer)
    return layer.x + w > 0 && layer.y + h > 0
      && layer.x < design.artboard.w && layer.y < design.artboard.h
  })
}
