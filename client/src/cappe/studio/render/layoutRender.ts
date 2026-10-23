// A paged story's pages as HTML: the server's bytes (services/magazine/
// studio/render.py), so what the Studio shows is what a reader gets.
// server/tests/cappe/fixtures/studio_render_cases.json holds the two equal,
// and layout.css is the same file on both sides.
//
// Every length is `calc(N * var(--u))`, --u being one point on screen. A
// paragraph is a <p> of its lines; each line is a box of the width it was
// aligned in, placed by its bottom edge on its baseline and aligned by the
// browser; the spaces a line broke at follow it in a sizeless .lyt-sp.

import { escHtml } from '../../magazine/canvas/rt'
import { fontStack } from '../../magazine/design/fontStack'
import { CHAR_DEFAULTS, PARA_DEFAULTS } from '../model/limits'
import { spreads } from '../model/doc'
import { graphicUrl } from '../model/graphics'
import type { Asset, CharAttrs, Doc, GraphicItem, ImageItem, Item, Para, Run, TextItem, Thread } from '../model/types'
import { faceUrl, familyName, type FaceLookup } from '../fonts/faces'

/** The faces set by name (not built), by family, as the server's `Uses`. */
export type Used = Map<string, Set<string>>
/** Each threaded text frame's thread, its place in it, and where its words
 *  flow while it has no composition. */
export type Threads = Map<string, [Thread, number, number]>

/** A number as the server prints it: 2 decimals, half up; 12.0 → "12". */
export function n(v: number): string {
  const r = Math.floor(v * 100 + 0.5) / 100
  return String(r === 0 ? 0 : r)
}
export const u = (v: number) => `calc(${n(v)} * var(--u))`

const esc = (s: string) => escHtml(s, false)
const ALIGN_CLASS = ['', ' lyt-l--c', ' lyt-l--r', ' lyt-l--j']
const FLOW_ALIGN: Record<string, string> = { l: 'left', c: 'center', r: 'right', j: 'justify', ja: 'justify' }
const FIT: Record<string, string> = { fill: 'cover', fit: 'contain', stretch: 'fill' }

function box(item: Item, pad = 0): string {
  let style = `left:${u(item.x - pad)};top:${u(item.y - pad)};width:${u(item.w + 2 * pad)};height:${u(item.h + 2 * pad)}`
  if (item.rot) style += `;transform:rotate(${n(item.rot)}deg)`
  if (item.opacity < 100) style += `;opacity:${n(item.opacity / 100)}`
  return style
}

function stroke(item: Item, radius = ''): string {
  const s = 'stroke' in item ? item.stroke : null
  if (!s) return ''
  const r = radius ? `;border-radius:${radius}` : ''
  return `<i class="lyt-k" style="box-shadow:inset 0 0 0 ${u(s.w)} ${s.c}${r}"></i>`
}

// ── type ─────────────────────────────────────────────────────────────────────

const addUse = (used: Used, font: string, wt: number, it: boolean) => {
  if (!used.has(font)) used.set(font, new Set())
  used.get(font)!.add(`${wt}|${it ? 1 : 0}`)
}

export function runStyle(attrs: CharAttrs, used: Used, faces: FaceLookup): string {
  const a = { ...CHAR_DEFAULTS, ...attrs }
  const face = faces(a.font, a.wt, a.it)
  let family: string
  if (face) family = `'${familyName(face.sha)}'`
  else {
    addUse(used, a.font, a.wt, a.it)
    family = `${fontStack(a.font)};font-weight:${a.wt}${a.it ? ';font-style:italic' : ''}`
  }
  let style = `font-family:${family};font-size:${u(a.size)}`
  if (a.track) style += `;letter-spacing:${u((a.track / 1000) * a.size)}`
  if (a.color !== CHAR_DEFAULTS.color) style += `;color:${a.color}`
  if (a.u) style += ';text-decoration:underline'
  return style
}

function spans(runs: Run[], start: number, end: number, used: Used, faces: FaceLookup): string {
  let out = ''
  let at = 0
  for (const r of runs) {
    const a = Math.max(start, at), b = Math.min(end, at + r.t.length)
    if (b > a) out += `<span style="${runStyle(r, used, faces)}">${esc(r.t.slice(a - at, b - at))}</span>`
    at += r.t.length
  }
  return out
}

const paraText = (p: Para) => p.runs.map((r) => r.t).join('')

function linesHtml(thread: Thread, frameIndex: number, frameH: number, used: Used, faces: FaceLookup,
  mark?: (k: number) => string): string {
  const lines = thread.comp!.lines
  let out = ''
  let open = -1
  lines.forEach(([f, p, s, e, x, b, w, a], k) => {
    if (f !== frameIndex) return
    if (p !== open) {
      if (open !== -1) out += '</p>'
      out += '<p class="lyt-p">'
      open = p
    }
    const runs = thread.paras[p].runs
    out += `<span class="lyt-l${ALIGN_CLASS[a]}"${mark ? mark(k) : ''} style="left:${u(x)};bottom:${u(frameH - b)};`
      + `width:${u(w)}">${spans(runs, s, e, used, faces)}</span>`
    const next = lines[k + 1]
    if (next && next[1] === p) {
      const gap = paraText(thread.paras[p]).slice(e, next[2])
      if (gap) out += `<span class="lyt-sp">${esc(gap)}</span>`
    }
  })
  if (open !== -1) out += '</p>'
  return out
}

function paraCss(p: Para): string {
  const a = { ...PARA_DEFAULTS, ...p }
  let style = `text-align:${FLOW_ALIGN[a.align]}`
  for (const [key, prop] of [['li', 'padding-left'], ['ri', 'padding-right'], ['fi', 'text-indent'],
    ['sb', 'margin-top'], ['sa', 'margin-bottom']] as const) {
    if (a[key]) style += `;${prop}:${u(a[key])}`
  }
  if (a.lead) style += `;line-height:${u(a.lead)}`
  return style
}

function flowedHtml(thread: Thread, item: TextItem, used: Used, faces: FaceLookup): string {
  const paras = thread.paras.map((p) => `<p style="${paraCss(p)}">`
    + p.runs.map((r) => `<span style="${runStyle(r, used, faces)}">${esc(r.t)}</span>`).join('') + '</p>').join('')
  let style = `padding:${u(item.inset)}`
  if (item.cols > 1) style += `;column-count:${item.cols};column-gap:${u(item.gutter)}`
  return `<div class="lyt-flow" style="${style}">${paras}</div>`
}

// ── items ────────────────────────────────────────────────────────────────────

export type Draw = { assets: Record<string, Asset>; faces: FaceLookup; used: Used; threads: Threads;
  /** The Studio's marks on a composed line (its index in the thread's lines). */
  mark?: (thread: Thread, k: number) => string }

function textHtml(item: TextItem, d: Draw): string {
  let style = box(item)
  if (item.fill) style += `;background:${item.fill}`
  let inner = ''
  const found = d.threads.get(item.id)
  if (found) {
    const [thread, index, flow] = found
    if (thread.comp) inner = linesHtml(thread, index, item.h, d.used, d.faces, d.mark && ((k) => d.mark!(thread, k)))
    else if (index === flow) inner = flowedHtml(thread, item, d.used, d.faces)
  }
  return `<div class="lyt-item lyt-text" style="${style}">${inner}${stroke(item)}</div>`
}

export function safeImage(url: unknown): string | null {
  const s = typeof url === 'string' ? url.trim() : ''
  if (!s || /['"();<>\\\n\r]/.test(s)) return null
  return /^(https?:\/\/|\/)/i.test(s) ? s : null
}

function safeHref(href: unknown): string {
  const s = typeof href === 'string' ? href.trim() : ''
  if (!s || [...s].some((c) => c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f)) return '#'
  if (s.startsWith('/')) return s.replace(/\\/g, '/').startsWith('//') ? '#' : s
  if (s.startsWith('#')) return s
  return /^(https?:|mailto:|tel:)/i.test(s) ? s : '#'
}

/** The credit printed with a picture (figures.credit_html): its library
 *  row's, "AI illustration" for an AI picture. */
export function creditHtml(a: Asset): string {
  const text = a.ai_generated ? 'AI illustration' : (a.credit_line || '').trim()
  if (!text) return ''
  const source = a.source_url ? safeHref(a.source_url) : '#'
  let inner = escHtml(text)
  if (source !== '#' && !a.ai_generated) inner = `<a href="${escHtml(source)}" rel="nofollow noopener" target="_blank">${inner}</a>`
  return `<span class="${a.ai_generated ? 'mz-credit mz-credit--ai' : 'mz-credit'}">${inner}</span>`
}

const imageSizes = (item: Item, pageW: number) =>
  `(min-width: 700px) ${Math.max(1, Math.ceil((item.w / (2 * pageW)) * 100))}vw, `
  + `${Math.max(1, Math.ceil((item.w / pageW) * 100))}vw`

function img(a: Asset, sizes: string, eager: boolean, style: string): string {
  const src = safeImage(a.url)
  if (!src) return ''
  const attrs = [`src="${escHtml(src)}"`, `alt="${escHtml(a.alt || '')}"`]
  const variants = (a.variants?.webp || [])
    .map((v) => [v && Number.isInteger(v.w) ? v.w : null, safeImage(v?.url)] as const)
    .filter((v): v is readonly [number, string] => v[0] !== null && !!v[1])
    .sort((x, y) => x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0))
  if (variants.length) {
    attrs.push(`srcset="${variants.map(([w, url]) => `${escHtml(url)} ${w}w`).join(', ')}"`)
    attrs.push(`sizes="${sizes}"`)
  }
  attrs.push(eager ? 'fetchpriority="high"' : 'loading="lazy" decoding="async"')
  attrs.push(`class="lyt-pic" style="${style}"`)
  return `<img ${attrs.join(' ')} />`
}

function imageHtml(item: ImageItem, d: Draw, pageW: number, eager: boolean): string {
  const radius = item.radius ? u(item.radius) : ''
  let style = box(item)
  if (item.fill) style += `;background:${item.fill}`
  if (radius) style += `;border-radius:${radius}`
  const asset = item.asset_id ? d.assets[item.asset_id] : undefined
  let inner = ''
  if (asset) {
    let pic = `object-fit:${FIT[item.fit]};object-position:${n(item.fx)}% ${n(item.fy)}%`
    if (item.zoom !== 100) pic += `;transform:scale(${n(item.zoom / 100)});transform-origin:${n(item.fx)}% ${n(item.fy)}%`
    const tag = img(asset, imageSizes(item, pageW), eager, pic)
    const credit = creditHtml(asset)
    if (tag) inner = tag + (credit ? `<figcaption class="lyt-credit">${credit}</figcaption>` : '')
  }
  return `<figure class="lyt-item lyt-img" style="${style}">${inner}${stroke(item, radius)}</figure>`
}

function shapeHtml(item: Item & { fill: string | null }): string {
  const radius = item.kind === 'ellipse' ? '50%' : item.kind === 'rect' && item.radius ? u(item.radius) : ''
  let style = box(item)
  if (item.fill) style += `;background:${item.fill}`
  if (radius) style += `;border-radius:${radius}`
  return `<div class="lyt-item lyt-shape" style="${style}">${stroke(item, radius)}</div>`
}

function lineHtml(item: Extract<Item, { kind: 'line' }>): string {
  const s = item.stroke
  const pad = s.w / 2
  const [y1, y2] = item.flip ? [item.h, 0] : [0, item.h]
  const view = `${n(-pad)} ${n(-pad)} ${n(item.w + 2 * pad)} ${n(item.h + 2 * pad)}`
  return `<svg class="lyt-item lyt-line" style="${box(item, pad)}" viewBox="${view}" aria-hidden="true">`
    + `<line x1="0" y1="${n(y1)}" x2="${n(item.w)}" y2="${n(y2)}" stroke="${s.c}" stroke-width="${n(s.w)}"/></svg>`
}

/** A bank graphic filling its box (render._graphic_html): its own shape,
 *  stretched, or tiled; a one-colour one is a mask over its colour. */
function graphicHtml(item: GraphicItem): string {
  const src = `url(${graphicUrl(item.src)})`
  const size = item.fit === 'contain' ? 'contain' : item.fit === 'stretch' ? '100% 100%' : `${u(item.tile)} auto`
  const place = `${item.fit === 'tile' ? '0 0' : 'center'}/${size} ${item.fit === 'tile' ? 'repeat' : 'no-repeat'}`
  let style = box(item)
  if (item.color) style += `;background:${item.color};-webkit-mask:${src} ${place};mask:${src} ${place}`
  else style += `;background:${src} ${place}`
  return `<div class="lyt-item lyt-g" style="${style}"></div>`
}

export function itemHtml(item: Item, doc: Doc, d: Draw, eager = false): string {
  switch (item.kind) {
    case 'text': return textHtml(item, d)
    case 'image': return imageHtml(item, d, doc.size.w, eager)
    case 'line': return lineHtml(item)
    case 'graphic': return graphicHtml(item)
    default: return shapeHtml(item)
  }
}

/** Which of a thread's frames holds its words while it has no composition
 *  (schema.flow_frame): the first, or the first on a locked page. */
export function flowFrame(doc: Doc, thread: Thread, lockedFrom: number | null = null): number {
  if (lockedFrom) {
    const pageIndex = new Map(doc.pages.map((p, i) => [p.id, i]))
    const pages = new Map(doc.items.map((i) => [i.id, i.page]))
    const k = thread.frames.findIndex((f) => (pageIndex.get(pages.get(f) ?? '') ?? -1) + 1 >= lockedFrom)
    if (k !== -1) return k
  }
  return 0
}

export function frameThreads(doc: Doc, lockedFrom: number | null = null): Threads {
  const out: Threads = new Map()
  for (const t of doc.threads) {
    const flow = flowFrame(doc, t, lockedFrom)
    t.frames.forEach((f, i) => out.set(f, [t, i, flow]))
  }
  return out
}

/** What sits on one page, bottom to top (hidden items left out). */
export function pageItemsHtml(doc: Doc, index: number, d: Draw): string {
  const pageId = doc.pages[index].id
  return doc.items.filter((i) => i.page === pageId && !i.hidden).map((i) => itemHtml(i, doc, d, index === 0)).join('')
}

export function spreadHtml(doc: Doc, pages: number[], d: Draw, lockedFrom: number | null = null): string {
  const { w: pw, h: ph } = doc.size
  const paper = pages.map((index, k) => `<div class="lyt-paper" data-lyt-n="${index + 1}" style="left:${u(k * pw)};width:${u(pw)}"></div>`).join('')
  const layers = pages.map((index, k) => {
    const number = index + 1
    const style = `left:${u(k * pw)};width:${u(pw)}`
    if (lockedFrom !== null && number >= lockedFrom) {
      return `<div class="lyt-page lyt-page--locked" data-lyt-lock="${number}" style="${style}">`
        + '<p class="lyt-lock">For subscribers</p>'
        + '<a class="lyt-lock-go" href="#mz-paywall">Subscribe or sign in to read on</a></div>'
    }
    return `<div class="lyt-page" data-lyt-page="${number}" style="${style}">${pageItemsHtml(doc, index, d)}</div>`
  }).join('')
  return `<div class="lyt-spread" style="width:${u(pages.length * pw)};height:${u(ph)}">${paper}${layers}</div>`
}

const escAttr = (s: string) => escHtml(s)

/** The whole story as a strip of spreads (render.pages_html). */
export function pagesHtml(doc: Doc, assets: Record<string, Asset>, faces: FaceLookup,
  { lockedFrom = null, label = "The story's pages" }: { lockedFrom?: number | null; label?: string } = {}):
  { html: string; used: Used } {
  const d: Draw = { assets, faces, used: new Map(), threads: frameThreads(doc, lockedFrom) }
  const { w: pw, h: ph } = doc.size
  const slots = spreads(doc).map((pages, k) =>
    `<div class="lyt-slot" data-lyt-spread="${k}">${spreadHtml(doc, pages, d, lockedFrom)}</div>`).join('')
  const sw = doc.facing ? 2 * pw : pw
  const style = `--pw:${n(pw)};--ph:${n(ph)};--sw:${n(sw)};--paper:${doc.paper}`
  const html = `<div class="lyt" data-lyt style="${style}"><div class="lyt-strip" data-lyt-strip tabindex="0" role="region" `
    + `aria-label="${escAttr(label)}">${slots}</div></div>`
  return { html, used: d.used }
}

/** An @font-face for each of the Studio's faces the story sets (render.faces_css). */
export function facesCss(doc: Doc, faces: FaceLookup): string {
  const shas = new Set<string>()
  for (const t of doc.threads) for (const p of t.paras) for (const r of p.runs) {
    const a = { ...CHAR_DEFAULTS, ...r }
    const f = faces(a.font, a.wt, a.it)
    if (f) shas.add(f.sha)
  }
  return [...shas].sort().map((sha) => `@font-face{font-family:'${familyName(sha)}';src:url(${faceUrl(sha)}) `
    + "format('truetype');font-display:block}").join('')
}
