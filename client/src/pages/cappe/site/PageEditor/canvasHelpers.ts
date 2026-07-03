import type { CappeBlock, CappeCanvasElement, CappeCanvasElementStyle, CappeCanvasPos } from '../../../../types/cappe'

export function genId(): string {
  try { return crypto.randomUUID().replace(/-/g, '').slice(0, 8) } catch { return Math.random().toString(36).slice(2, 10) }
}
export function cvEls(b: unknown): CappeCanvasElement[] {
  const els = (b as { elements?: unknown } | null)?.elements
  return Array.isArray(els) ? (els as CappeCanvasElement[]) : []
}
export function cvNextY(els: CappeCanvasElement[]): number {
  return els.reduce((m, e) => Math.max(m, (e.d?.y || 0) + (e.d?.h || 1)), 0)
}
export function cvNewElement(kind: CappeCanvasElement['kind'], y: number): CappeCanvasElement {
  if (kind === 'image') return { id: genId(), kind, src: '', d: { x: 2, y, w: 8, h: 6 }, style: { fit: 'cover' } }
  if (kind === 'button') return { id: genId(), kind, text: 'Button', href: '', d: { x: 2, y, w: 6, h: 2 }, style: { variant: 'solid' } }
  return { id: genId(), kind, text: kind === 'heading' ? 'Heading' : 'Text', d: { x: 2, y, w: 12, h: kind === 'heading' ? 3 : 2 }, style: {} }
}
export function isCanvasBlock(b: unknown): boolean {
  return !!b && (b as { type?: string }).type === 'canvas'
}
export const CV_MAX_ELEMENTS = 200
export const CV_ELEMENT_KINDS: CappeCanvasElement['kind'][] = ['heading', 'text', 'image', 'button']

// Sections whose single-instance content maps cleanly to freeform elements.
export const CONVERTIBLE_TO_CANVAS = new Set(['hero', 'cta', 'split', 'text'])

/** "Customize freely": map a template section's content into a freeform canvas
 *  block — keeps the content, unlocks per-element editing. One-way. */
export function convertSectionToCanvas(block: CappeBlock): CappeBlock {
  const s = (k: string) => (typeof block[k] === 'string' ? (block[k] as string) : '')
  const els: CappeCanvasElement[] = []
  const txt = (kind: 'heading' | 'text', text: string, d: CappeCanvasPos, style: CappeCanvasElementStyle = {}) => {
    if (text) els.push({ id: genId(), kind, text, d, style })
  }
  const btn = (label: string, href: string, variant: 'solid' | 'outline', d: CappeCanvasPos) => {
    if (label) els.push({ id: genId(), kind: 'button', text: label, href: href || '', d, style: { variant } })
  }
  const img = (src: string, d: CappeCanvasPos) => {
    if (src) els.push({ id: genId(), kind: 'image', src, d, style: { fit: 'cover' } })
  }
  const design: Record<string, unknown> = {
    ...(block._design && typeof block._design === 'object' && !Array.isArray(block._design) ? (block._design as Record<string, unknown>) : {}),
  }

  if (block.type === 'hero') {
    const style = s('style'); const image = s('image'); const video = s('video')
    const fullBleed = !!video || style === 'image' || ((style === 'centered' || !style) && !!image)
    if (fullBleed && (image || video)) {
      design.bg = video
        ? { type: 'video', video, overlay: s('overlay') || 'medium' }
        : { type: 'image', image, overlay: s('overlay') || 'medium' }
    }
    txt('text', s('eyebrow'), { x: 6, y: 3, w: 12, h: 1 }, { size: 13, weight: 600 })
    txt('heading', s('heading'), { x: 6, y: 5, w: 12, h: 3 })
    txt('text', s('subheading'), { x: 6, y: 9, w: 12, h: 2 })
    btn(s('cta'), s('ctaHref'), 'solid', { x: 6, y: 12, w: 5, h: 2 })
    btn(s('cta2'), s('cta2Href'), 'outline', { x: 11, y: 12, w: 5, h: 2 })
    if (style === 'split') img(image, { x: 13, y: 3, w: 10, h: 10 })
  } else if (block.type === 'cta') {
    txt('heading', s('heading'), { x: 4, y: 2, w: 16, h: 3 })
    txt('text', s('subheading'), { x: 4, y: 6, w: 16, h: 2 })
    btn(s('cta') || 'Get started', s('ctaHref'), 'solid', { x: 4, y: 10, w: 6, h: 2 })
  } else if (block.type === 'split') {
    const reverse = block.reverse === true
    const tx = reverse ? 13 : 1
    const ix = reverse ? 1 : 13
    txt('text', s('eyebrow'), { x: tx, y: 2, w: 10, h: 1 }, { size: 13, weight: 600 })
    txt('heading', s('heading'), { x: tx, y: 4, w: 10, h: 2 })
    txt('text', s('body'), { x: tx, y: 7, w: 10, h: 4 })
    const bullets = Array.isArray(block.bullets) ? (block.bullets as unknown[]).filter((x): x is string => typeof x === 'string' && !!x) : []
    if (bullets.length) txt('text', bullets.map((x) => `• ${x}`).join('\n'), { x: tx, y: 11, w: 10, h: bullets.length + 1 })
    btn(s('cta'), s('ctaHref'), 'solid', { x: tx, y: 16, w: 6, h: 2 })
    img(s('image'), { x: ix, y: 2, w: 10, h: 14 })
  } else if (block.type === 'text') {
    txt('heading', s('heading'), { x: 4, y: 2, w: 16, h: 2 })
    const body = block.body
    const bodyText = Array.isArray(body)
      ? (body as unknown[]).filter((x): x is string => typeof x === 'string').join('\n\n')
      : (typeof body === 'string' ? body : '')
    txt('text', bodyText, { x: 4, y: 5, w: 16, h: 6 })
  }

  return {
    type: 'canvas',
    grid: { cols: 24, rowH: 24, rows: 30 },
    mobile: { cols: 8, rowH: 24, rows: 60 },
    elements: els,
    ...(Object.keys(design).length ? { _design: design } : {}),
  }
}
