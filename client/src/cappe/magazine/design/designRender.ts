import { escHtml, rtToHtml } from '../canvas/rt'
import { fontStack } from './fontStack'
import type { Design, Layer, Paint, PaintedLayer, Shadow } from './types'

/** A design → HTML, exactly as the server draws it
 *  (services/magazine/design_render.py), for the editor to show a change on
 *  the page at once while the server sets the page again. The shared fixture
 *  server/tests/cappe/fixtures/magazine_design_cases.json holds the two to
 *  the same bytes, so the server's page swaps in without a flicker.
 *
 *  A design is a `.mzd` box over its artboard; each layer carries its place
 *  as numbers (`--x`, `--y`, `--w`, `--h`) that design.css turns into a
 *  position through the artboard's units (`--bw`, `--bh`). */

/** A library picture, as much as drawing it needs. */
export type DesignAsset = {
  id: string; url: string; alt?: string | null; width?: number | null; height?: number | null
  variants?: { webp?: { w: number; url: string }[] } | null
}

/** 12 → "12", 0.5 → "0.5" (as Python's design_render.n prints them). */
export const n = (v: number) => String(v + 0)

export const cssColour = (c: string) => (c === 'accent' ? 'var(--mz-accent)' : c)

/** A size in the artboard's width units. */
export const u = (v: number) => `calc(${n(v)} * var(--bw))`

export function paintCss(p: Paint | undefined): string {
  if (!p) return ''
  if (p.kind === 'solid') return cssColour(p.color)
  if (p.kind === 'linear' || p.kind === 'radial') {
    const stops = p.stops.map((s) => `${cssColour(s.color)} ${n(s.at)}%`).join(',')
    return p.kind === 'linear' ? `linear-gradient(${n(p.angle ?? 180)}deg,${stops})` : `radial-gradient(circle,${stops})`
  }
  return ''
}

function shadow(s: Shadow, spread = true): string {
  const parts = [u(s.x), u(s.y), u(s.blur)]
  if (spread) parts.push(u(s.spread))
  return (s.inner && spread ? 'inset ' : '') + parts.join(' ') + ` ${cssColour(s.color)}`
}

/** Where a layer sits and how it is painted: its element's style. */
export function layerStyle(l: Layer): string {
  const auto = l.kind === 'text' && l.autosize === 'height'
  const parts = [`--x:${n(l.x)}`, `--y:${n(l.y)}`, `--w:${n(l.w)}`]
  if (!auto) parts.push(`--h:${n(l.h)}`)
  const transform: string[] = []
  if (l.rot) transform.push(`rotate(${n(l.rot)}deg)`)
  if (l.flip_x || l.flip_y) transform.push(`scale(${l.flip_x ? -1 : 1},${l.flip_y ? -1 : 1})`)
  if (transform.length) parts.push(`transform:${transform.join(' ')}`)
  if ((l.opacity ?? 100) !== 100) parts.push(`opacity:${n(l.opacity / 100)}`)
  if ((l.blend ?? 'normal') !== 'normal') parts.push(`mix-blend-mode:${l.blend}`)
  if (l.kind === 'group') return parts.join(';')
  const line = l.kind === 'shape' && l.shape === 'line'
  const fill = l.kind !== 'image' ? paintCss(l.fill) : ''
  if (fill) parts.push(`background:${fill}`)
  if (l.stroke?.width && !line) parts.push(`border:${u(l.stroke.width)} ${l.stroke.style} ${cssColour(l.stroke.color)}`)
  if (l.kind === 'shape' && l.shape === 'ellipse') parts.push('border-radius:50%')
  else if ((l.radius || []).some(Boolean)) parts.push(`border-radius:${l.radius.map(u).join(' ')}`)
  const filters: string[] = []
  const shadows = l.shadows || []
  if (shadows.length) {
    if (l.kind === 'image') filters.push(...shadows.filter((s) => !s.inner).map((s) => `drop-shadow(${shadow(s, false)})`))
    else if (l.kind === 'shape' || fill) parts.push(`box-shadow:${shadows.map((s) => shadow(s)).join(',')}`)
  }
  if (l.blur) filters.push(`blur(${u(l.blur)})`)
  if (filters.length) parts.push(`filter:${filters.join(' ')}`)
  if (l.kind === 'text' && l.pad) parts.push(`padding:${u(l.pad)}`)
  return parts.join(';')
}

const CASE = { upper: 'uppercase', lower: 'lowercase', title: 'capitalize' } as const

export function textStyle(l: Extract<Layer, { kind: 'text' }>): string {
  const parts = [`font-family:${fontStack(l.font)}`, `font-size:${u(l.size)}`, `font-weight:${l.weight}`]
  if (l.italic) parts.push('font-style:italic')
  parts.push(`color:${cssColour(l.color)}`, `text-align:${l.align}`, `line-height:${n(l.leading)}`)
  if (l.tracking) parts.push(`letter-spacing:${n(l.tracking)}em`)
  if (l.case !== 'none' && l.case in CASE) parts.push(`text-transform:${CASE[l.case as keyof typeof CASE]}`)
  if (!paintCss(l.fill)) {
    const drops = (l.shadows || []).filter((s) => !s.inner)
    if (drops.length) parts.push(`text-shadow:${drops.map((s) => shadow(s, false)).join(',')}`)
  }
  return parts.join(';')
}

export function imageStyle(l: Extract<Layer, { kind: 'image' }>): string {
  const parts = [`object-fit:${l.fit}`, `object-position:${l.focal?.x ?? 50}% ${l.focal?.y ?? 50}%`]
  if ((l.zoom ?? 100) > 100) parts.push(`transform:scale(${n(l.zoom / 100)})`)
  if (l.filter === 'bw') parts.push('filter:grayscale(1)')
  else if (l.filter === 'sepia') parts.push('filter:sepia(.85)')
  return parts.join(';')
}

// ── a library picture (as figures.img_html) ──────────────────────────────────

const SIZES: Record<string, string> = { wide: '(min-width: 1140px) 1080px, 100vw' }

/** A picture's address the page may load (as sanitize._safe_image). */
export function safeImage(url: unknown): string | null {
  const s = typeof url === 'string' ? url.trim() : ''
  if (!s || /['"();<>\\\n\r]/.test(s)) return null
  return /^(https?:\/\/|\/)/i.test(s) ? s : null
}

export function imgHtml(a: DesignAsset, { size = 'wide', cls = '', style = '' } = {}): string {
  const src = safeImage(a.url)
  if (!src) return ''
  const variants = (a.variants?.webp || [])
    .map((v) => [v && Number.isInteger(v.w) ? v.w : null, safeImage(v?.url)] as const)
    .filter((v): v is readonly [number, string] => v[0] !== null && !!v[1])
    .sort((x, y) => x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0))
  const attrs = [`src="${escHtml(src)}"`, `alt="${escHtml(a.alt || '')}"`]
  if (variants.length) {
    attrs.push(`srcset="${variants.map(([w, url]) => `${escHtml(url)} ${w}w`).join(', ')}"`)
    attrs.push(`sizes="${SIZES[size] ?? SIZES.wide}"`)
  }
  if (a.width && a.height) attrs.push(`width="${Math.trunc(a.width)}" height="${Math.trunc(a.height)}"`)
  attrs.push('loading="lazy" decoding="async"')
  if (cls) attrs.push(`class="${cls}"`)
  if (style) attrs.push(`style="${escHtml(style)}"`)
  return `<img ${attrs.join(' ')} />`
}

// ── layers ───────────────────────────────────────────────────────────────────

function classes(l: PaintedLayer): string {
  let cls = `mzd__l mzd__l--${l.kind}`
  if (l.kind === 'text') cls += l.autosize === 'height' ? ' mzd__l--auto' : l.valign === 'middle' ? ' mzd__l--vm' : l.valign === 'bottom' ? ' mzd__l--vb' : ''
  else if (l.kind === 'shape' && l.shape === 'line') cls += ' mzd__l--line'
  return cls
}

export type DrawOptions = { edit?: boolean; path?: string }

export function layerHtml(l: Layer, assets: Record<string, DesignAsset>, { edit = false, path = 'design' }: DrawOptions = {}): string {
  if (l.hidden) return ''
  const attrs = edit ? ` data-mzd-l="${escHtml(l.id)}"${l.locked ? ' data-mzd-lock' : ''}` : ''
  if (l.kind === 'group') {
    const inner = l.children.map((c) => layerHtml(c, assets, { edit, path })).join('')
    return `<div class="mzd__g" style="${escHtml(layerStyle(l))}"${attrs}>${inner}</div>`
  }
  let inner = ''
  if (l.kind === 'text') {
    const field = edit ? ` data-mz-f="${escHtml(path)}.${escHtml(l.id)}" data-mz-k="rich" data-mz-lazy data-mz-ph="Type something"` : ''
    inner = `<div class="mzd__t" style="${escHtml(textStyle(l))}"${field}>${rtToHtml(l.rt)}</div>`
  } else if (l.kind === 'image') {
    const a = assets[l.asset_id]
    inner = a ? imgHtml(a, { cls: 'mzd__img', style: imageStyle(l) }) : ''
    if (!inner && !edit) return ''
  } else if (l.shape === 'line') {
    const width = l.stroke?.width || 0.3
    inner = `<i class="mzd__line" style="border-top:${u(width)} ${l.stroke?.style || 'solid'} ${cssColour(l.stroke?.color || '#000000')}"></i>`
  }
  const style = escHtml(layerStyle(l))
  if (l.link && !edit) return `<a class="${classes(l)}" style="${style}" href="${escHtml(l.link)}" rel="nofollow ugc noopener">${inner}</a>`
  return `<div class="${classes(l)}" style="${style}"${attrs}>${inner}</div>`
}

/** What a cover's picture is cut to: its width over height and the focal
 *  point (0–1) its page keeps in view. */
export type PictureCut = { ratio: number; fx: number; fy: number }

const round4 = (v: number) => Math.floor(Math.max(0.2, Math.min(5, v)) * 1e4 + 0.5) / 1e4

/** The design's box with its layers. In the editor every picture gets its
 *  box, designed or not, to add layers to. */
export function designHtml(design: Design | null | undefined, assets: Record<string, DesignAsset>,
  { edit = false, path = 'design', picture = null }: DrawOptions & { picture?: PictureCut | null } = {}): string {
  const layers = design?.layers || []
  if (!layers.length && !edit) return ''
  const vars = picture ? ` style="--ar:${n(round4(picture.ratio))};--fx:${n(picture.fx)};--fy:${n(picture.fy)}"` : ''
  const marks = edit ? ` data-mzd="${escHtml(path)}"` : ''
  const probe = edit ? '<i class="mzd__box" aria-hidden="true"></i>' : ''
  return `<div class="mzd"${vars}${marks}>${probe}${layers.map((l) => layerHtml(l, assets, { edit, path })).join('')}</div>`
}

/** Just the layers (the box's inside after its probe): what the editor puts
 *  back into a design's box on the page when the design changes. */
export const layersHtml = (design: Design | null | undefined, assets: Record<string, DesignAsset>, opts: DrawOptions = {}) =>
  (design?.layers || []).map((l) => layerHtml(l, assets, opts)).join('')

/** A designed page's artboard: its shape and its background. */
export function pageStyle(design: Design | null | undefined, aspect: number): string {
  const parts = [`--ar:${n(aspect)}`]
  const bg = paintCss(design?.background)
  if (bg) parts.push(`background:${bg}`)
  return parts.join(';')
}
