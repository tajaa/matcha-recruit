// A picture of the person's own design to go beside their reference picture
// (Ask the Studio, studio/ask.py `current`): the selected part of the page,
// else the page in view, drawn by the same renderer as the pages. The page's
// HTML goes into an SVG <foreignObject> with every font, picture and graphic
// inlined (an SVG drawn as an image loads nothing from outside), the SVG onto
// a canvas, the canvas out as a JPEG. A picture that can't be fetched is left
// a grey block; anything else going wrong means no picture (the question
// still goes, with the page described in words).

import layoutCss from '../../render/layout.css?raw'
import { bounds } from '../../canvas/geometry'
import { familyName } from '../../fonts/faces'
import { facesCss, frameThreads, pageItemsHtml, type Draw } from '../../render/layoutRender'
import type { Doc } from '../../model/types'
import { studioApi } from '../../api'
import type { State } from '../../store/store'
import type { FontLoader } from '../../fonts/loader'
import type { Asset } from '../../model/types'
import type { Picture } from './conversation'

const SIDE = 1_280 // the longest side sent, as a reference picture is
const MAX_SCALE = 3 // px per point: a small selection isn't blown up past this
const MIN_SIDE = 160 // pt: a tiny selection is shown with what's around it
const WAIT_MS = 8_000
const XHTML = 'http://www.w3.org/1999/xhtml'

export type Crop = { page: number; x: number; y: number; w: number; h: number }

/** What to draw, in the page's points: what's selected on the page of the
 *  first thing selected, with room around it (never less than MIN_SIDE each
 *  way), kept inside the page; with nothing selected, the page in view. */
export function cropFor(s: State): Crop {
  const { doc } = s
  const first = doc.items.find((i) => s.selection.includes(i.id))
  const found = first ? doc.pages.findIndex((p) => p.id === first.page) : -1
  const page = found >= 0 ? found : s.page
  const { w: pw, h: ph } = doc.size
  const chosen = first && found >= 0 ? doc.items.filter((i) => s.selection.includes(i.id) && i.page === first.page) : []
  const b = bounds(chosen, () => ({ x: 0, y: 0 }))
  if (!b) return { page, x: 0, y: 0, w: pw, h: ph }
  const pad = Math.max(18, 0.08 * Math.max(b.w, b.h))
  const span = (lo: number, size: number, max: number) => {
    let a = lo - pad, z = lo + size + pad
    const short = MIN_SIDE - (z - a)
    if (short > 0) { a -= short / 2; z += short / 2 }
    a = Math.max(0, a)
    z = Math.min(max, z)
    return [a, Math.max(z - a, 1)] as const
  }
  const [x, w] = span(b.x, b.w, pw)
  const [y, h] = span(b.y, b.h, ph)
  return { page, x, y, w, h }
}

/** Pixels per point for a crop: its longest side SIDE px, at most MAX_SCALE. */
export const scaleFor = (c: Crop) => Math.min(MAX_SCALE, SIDE / Math.max(c.w, c.h))

const asDataUrl = async (url: string, type?: string): Promise<string> => {
  const res = await fetch(url, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`${res.status}`)
  const blob = await res.blob()
  const bytes = new Uint8Array(await blob.arrayBuffer())
  let bin = ''
  for (let k = 0; k < bytes.length; k += 0x8000) bin += String.fromCharCode(...bytes.subarray(k, k + 0x8000))
  return `data:${type ?? (blob.type || 'application/octet-stream')};base64,${btoa(bin)}`
}

/** The widest of an <img>'s sources it needs (its srcset's smallest at least
 *  `want` px wide, else its biggest), else its src. */
export function sourceFor(srcset: string | null, src: string, want: number): string {
  const variants = (srcset ?? '').split(',').map((part) => part.trim().split(/\s+/))
    .map(([url, w]) => [url, Number.parseInt(w ?? '', 10)] as const).filter(([url, w]) => !!url && Number.isFinite(w))
    .sort((a, b) => a[1] - b[1])
  if (!variants.length) return src
  return (variants.find(([, w]) => w >= want) ?? variants[variants.length - 1])[0]
}

/** How the files a page loads are fetched as data URLs: a picture (by its
 *  address, at most `want` px wide) and any other file (a font, a graphic). */
export type Loader = { picture: (url: string, want: number) => Promise<string>; file: (url: string, type: string) => Promise<string> }

/** The page's HTML with everything it loads inlined, inside an XHTML body
 *  the crop's size, ready for a <foreignObject>. */
export async function inlinePage(doc: Doc, crop: Crop, scale: number, html: string, css: string,
  load: Loader = { picture: (url) => asDataUrl(url), file: asDataUrl }): Promise<string> {
  const parsed = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html')
  const root = parsed.body.firstElementChild as HTMLElement
  const work: Promise<void>[] = []
  for (const img of [...root.querySelectorAll('img')]) {
    // Never wider than the page drawn: enough for any picture on it.
    const want = Math.ceil(doc.size.w * scale)
    const url = sourceFor(img.getAttribute('srcset'), img.getAttribute('src') ?? '', want)
    for (const a of ['srcset', 'sizes', 'loading', 'decoding', 'fetchpriority']) img.removeAttribute(a)
    work.push(load.picture(url, want).then((data) => img.setAttribute('src', data), () => {
      // Out of reach (no CORS, offline): a grey block where it goes.
      img.removeAttribute('src')
      img.setAttribute('style', `${img.getAttribute('style') ?? ''};background:#c8c8c8`)
    }))
  }
  // Graphics are masks or backgrounds: their files go in as data too.
  for (const el of [...root.querySelectorAll<HTMLElement>('[style*="url("]')]) {
    const style = el.getAttribute('style') ?? ''
    const urls = [...new Set([...style.matchAll(/url\(([^)'"]+)\)/g)].map((m) => m[1]))]
    work.push(Promise.all(urls.map((u) => load.file(u, 'image/svg+xml').then((d) => [u, d] as const, () => [u, ''] as const)))
      .then((pairs) => {
        let next = style
        for (const [u, d] of pairs) next = next.split(`url(${u})`).join(d ? `url("${d}")` : 'none')
        el.setAttribute('style', next)
      }))
  }
  // Only the faces this page sets.
  let fonts = css
  for (const m of [...css.matchAll(/url\((\/api\/cappe\/public\/fonts\/([0-9a-f]+)\.ttf)\)/g)]) {
    const [, url, sha] = m
    if (!html.includes(familyName(sha))) { fonts = fonts.split(`url(${url})`).join('url(data:,)'); continue }
    work.push(load.file(url, 'font/ttf').then((d) => { fonts = fonts.split(`url(${url})`).join(`url("${d}")`) }, () => {}))
  }
  await Promise.all(work)
  const body = document.createElementNS(XHTML, 'div')
  body.setAttribute('style', `position:relative;overflow:hidden;width:${crop.w * scale}px;height:${crop.h * scale}px;`
    + `background:${doc.paper};--u:${scale}px`)
  const style = document.createElementNS(XHTML, 'style')
  style.textContent = layoutCss + fonts
  const page = document.createElementNS(XHTML, 'div')
  page.setAttribute('style', `position:absolute;left:${-crop.x * scale}px;top:${-crop.y * scale}px;`
    + `width:${doc.size.w * scale}px;height:${doc.size.h * scale}px`)
  for (const child of [...root.childNodes]) page.appendChild(document.importNode(child, true))
  body.append(style, page)
  return new XMLSerializer().serializeToString(body)
}

/** A library picture through our own origin (its CDN copy may not allow
 *  reading), made no wider than needed; a picture not in the library
 *  (a sample, an address of our own), fetched as it is. */
function pictureLoader(siteId: string, assets: Record<string, Asset>): Loader['picture'] {
  const byUrl = new Map<string, string>()
  for (const a of Object.values(assets)) {
    if (a.url) byUrl.set(a.url, a.id)
    for (const v of a.variants?.webp ?? []) if (v?.url) byUrl.set(v.url, a.id)
  }
  return async (url, want) => {
    const id = byUrl.get(url)
    if (!id) return asDataUrl(url)
    const blob = await studioApi.pixels(siteId, id)
    const bitmap = await createImageBitmap(blob)
    const k = Math.min(1, want / bitmap.width)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * k))
    canvas.height = Math.max(1, Math.round(bitmap.height * k))
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    // A cut-out keeps its see-through parts.
    return blob.type === 'image/jpeg' ? canvas.toDataURL('image/jpeg', 0.9) : canvas.toDataURL('image/png')
  }
}

/** The selected part of the page (else the page in view) as a JPEG, or null
 *  when the browser can't draw it. */
export async function snapshot(s: State, fonts: FontLoader, siteId: string): Promise<Picture | null> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), WAIT_MS) })
  try {
    return await Promise.race([draw(s, fonts, siteId).catch(() => null), timeout])
  } finally {
    clearTimeout(timer)
  }
}

async function draw(s: State, fonts: FontLoader, siteId: string): Promise<Picture | null> {
  const { doc } = s
  if (!doc.pages[s.page]) return null
  const crop = cropFor(s)
  const scale = scaleFor(crop)
  const d: Draw = { assets: s.assets, faces: fonts.book.face, used: new Map(), threads: frameThreads(doc) }
  const html = pageItemsHtml(doc, crop.page, d)
  const xhtml = await inlinePage(doc, crop, scale, html, facesCss(doc, fonts.book.face),
    { picture: pictureLoader(siteId, s.assets), file: asDataUrl })
  const w = Math.max(1, Math.round(crop.w * scale)), h = Math.max(1, Math.round(crop.h * scale))
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><foreignObject x="0" y="0" width="${w}" height="${h}">${xhtml}</foreignObject></svg>`
  // A data: address, not a blob: one: Chromium won't let a canvas give back
  // pixels drawn from a blob: SVG with HTML in it (checked 2026-10-27).
  const img = new Image()
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  await img.decode()
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const g = canvas.getContext('2d')
  if (!g) return null
  g.fillStyle = '#fff'
  g.fillRect(0, 0, w, h)
  g.drawImage(img, 0, 0, w, h)
  const preview = canvas.toDataURL('image/jpeg', 0.85)
  return { media_type: 'image/jpeg', data: preview.slice(preview.indexOf(',') + 1), preview }
}

