// Linked crops: one picture seen through several frames on a spread, as if
// it lay behind the page and the frames were windows (across the spine, or
// split either side of it). Frames share a `link` (ImageItem.link); nothing
// else is stored, and the renderers draw each frame as usual: what keeps the
// windows lined up is each frame's own crop (fx, fy, zoom), worked out here
// from the picture's place on the spread.
//
// How a frame shows its picture (render/layoutRender.ts imageHtml): the
// picture covers the frame (object-fit: cover, scale c = max(w/iw, h/ih)),
// sits at object-position fx% fy%, and is scaled by zoom% about that same
// point. Its left edge then lands at fx/100 · (w − iw·c·zoom/100) inside the
// frame, so a frame shows the picture at spread scale S = c·zoom/100 with
// its top-left at x + fx/100 · (w − iw·S). zoom is a whole percent (the
// renderer prints the scale to 2 places), so frames whose cover scales
// differ can't all match S exactly: each is exact at the point of the frame
// nearest the middle of the group (the spine, for two halves), and a fresh
// fit picks the scale that keeps the leftover under a hair.

import { allIds, newId, spreads } from './doc'
import { LIMITS, clamp, round } from './limits'
import type { Asset, Doc, ImageItem, Item } from './types'

export type Rect = { x: number; y: number; w: number; h: number }
/** The picture's top-left on its spread (pt) and its scale (pt per pixel). */
export type Placement = { x: number; y: number; s: number }
type Crop = { fx: number; fy: number; zoom: number }
type Size = { iw: number; ih: number }

/** Where each page sits on its spread: the spread (its first page's id) and
 *  how far across it the page starts. */
export function spreadPlaces(doc: Doc): Map<string, { spread: string; dx: number }> {
  const out = new Map<string, { spread: string; dx: number }>()
  for (const pages of spreads(doc)) {
    pages.forEach((p, k) => out.set(doc.pages[p].id, { spread: doc.pages[pages[0]].id, dx: k * doc.size.w }))
  }
  return out
}

/** A frame's box on its spread. */
export function spreadRect(item: Item, places: ReturnType<typeof spreadPlaces>): Rect | null {
  const at = places.get(item.page)
  return at ? { x: item.x + at.dx, y: item.y, w: item.w, h: item.h } : null
}

const cover = (r: Rect, z: Size) => Math.max(r.w / z.iw, r.h / z.ih)

/** The picture as a frame at `r` shows it. */
export function shown(r: Rect, c: Crop, z: Size): Placement {
  const s = cover(r, z) * (c.zoom / 100)
  return { x: r.x + (c.fx / 100) * (r.w - z.iw * s), y: r.y + (c.fy / 100) * (r.h - z.ih * s), s }
}

function axis(left: number, room: number): number | null {
  if (Math.abs(room) < 1e-6) return 50
  const f = left / room
  if (f < -1e-3 || f > 1 + 1e-3) return null
  return round(Math.min(1, Math.max(0, f)) * 100)
}

/** The crop that shows `p` through a frame at `r`, exact at `at`. null when
 *  the frame would show past the picture's edge or need more zoom than a
 *  frame can have. */
export function cropFor(r: Rect, p: Placement, z: Size, at: { x: number; y: number }): Crop | null {
  const c = cover(r, z)
  const want = (p.s / c) * 100
  if (want < LIMITS.ZOOM_MIN - 0.5 || want > LIMITS.ZOOM_MAX + 0.5) return null
  const zoom = Math.min(LIMITS.ZOOM_MAX, Math.max(LIMITS.ZOOM_MIN, Math.round(want)))
  const s = (c * zoom) / 100
  // The picture's point under `at`, kept there at this frame's scale.
  const x = at.x - ((at.x - p.x) / p.s) * s
  const y = at.y - ((at.y - p.y) / p.s) * s
  const fx = axis(x - r.x, r.w - z.iw * s)
  const fy = axis(y - r.y, r.h - z.ih * s)
  return fx === null || fy === null ? null : { fx, fy, zoom }
}

function union(rects: Rect[]): Rect {
  const x = Math.min(...rects.map((r) => r.x)), y = Math.min(...rects.map((r) => r.y))
  const x2 = Math.max(...rects.map((r) => r.x + r.w)), y2 = Math.max(...rects.map((r) => r.y + r.h))
  return { x, y, w: x2 - x, h: y2 - y }
}


/** How far from a whole percent the frames' zooms would be at scale `s`
 *  (the most, as a share of the zoom: what can't be matched exactly). */
function leftover(rects: Rect[], z: Size, s: number): number {
  return Math.max(...rects.map((r) => { const want = (s / cover(r, z)) * 100; return Math.abs(Math.round(want) - want) / want }))
}

/** A placement that fills every frame (it covers them all together), as
 *  close to `want` as it can be: at least the scale that covers them, and
 *  moved only as far as it must. `fresh`: no wish, so it is centred, and the
 *  scale nudged up (under 3%) to where every frame's zoom is nearly whole. */
export function fitPlacement(rects: Rect[], z: Size, want: Placement | null): Placement | null {
  if (!rects.length) return null
  const u = union(rects)
  const least = cover(u, z)
  let s = Math.max(want?.s ?? least, least)
  if (!want) {
    let best = s, worst = leftover(rects, z, s)
    for (const r of rects) {
      const c = cover(r, z)
      for (let zoom = Math.ceil((s / c) * 100); zoom <= ((s * 1.03) / c) * 100; zoom++) {
        const cand = (c * zoom) / 100
        const off = leftover(rects, z, cand)
        if (off < worst - 1e-12) { best = cand; worst = off }
      }
    }
    s = best
  }
  if (rects.some((r) => (s / cover(r, z)) * 100 > LIMITS.ZOOM_MAX + 0.5)) return null
  const cx = u.x + u.w / 2, cy = u.y + u.h / 2
  let x = want ? cx - ((cx - want.x) / want.s) * s : u.x + (u.w - z.iw * s) / 2
  let y = want ? cy - ((cy - want.y) / want.s) * s : u.y + (u.h - z.ih * s) / 2
  x = clamp(x, u.x + u.w - z.iw * s, u.x)
  y = clamp(y, u.y + u.h - z.ih * s, u.y)
  return { x, y, s }
}

/** The frames' crops for placement `p` (null when one can't show it). */
export function cropsFor(rects: Rect[], p: Placement, z: Size): Crop[] | null {
  const u = union(rects)
  const cx = u.x + u.w / 2, cy = u.y + u.h / 2
  const out: Crop[] = []
  for (const r of rects) {
    const c = cropFor(r, p, z, { x: clamp(cx, r.x, r.x + r.w), y: clamp(cy, r.y, r.y + r.h) })
    if (!c) return null
    out.push(c)
  }
  return out
}

export type LinkGroup = { link: string; spread: string; members: ImageItem[]; rects: Rect[] }

const groupsOf = new WeakMap<Doc, LinkGroup[]>()

/** The frames sharing a link on one spread (one link on two spreads is two
 *  groups: a copied spread keeps working). Worked out once per document:
 *  documents never change, and the board, the overlays and the panels ask
 *  for every frame. */
export function linkGroups(doc: Doc): LinkGroup[] {
  const hit = groupsOf.get(doc)
  if (hit) return hit
  const out = doc.items.some((i) => i.kind === 'image' && i.link) ? findGroups(doc) : []
  groupsOf.set(doc, out)
  return out
}

function findGroups(doc: Doc): LinkGroup[] {
  const places = spreadPlaces(doc)
  const groups = new Map<string, LinkGroup>()
  for (const item of doc.items) {
    if (item.kind !== 'image' || !item.link) continue
    const at = places.get(item.page)
    const r = spreadRect(item, places)
    if (!at || !r) continue
    const key = `${item.link}|${at.spread}`
    const g = groups.get(key) ?? { link: item.link, spread: at.spread, members: [], rects: [] }
    g.members.push(item)
    g.rects.push(r)
    groups.set(key, g)
  }
  return [...groups.values()]
}

/** The group a frame is in, with the others (two frames at least). */
export function groupOf(doc: Doc, id: string): LinkGroup | null {
  const g = linkGroups(doc).find((x) => x.members.some((m) => m.id === id))
  return g && g.members.length > 1 ? g : null
}

const sizeOf = (assets: Record<string, Asset>, id: string | null): Size | null => {
  const a = id ? assets[id] : undefined
  return a?.width && a.height ? { iw: a.width, ih: a.height } : null
}

function setCrops(doc: Doc, members: ImageItem[], crops: Crop[]): Doc {
  const want = new Map(members.map((m, k) => [m.id, crops[k]]))
  let changed = false
  const items = doc.items.map((i) => {
    const c = want.get(i.id)
    // A locked frame is never changed: the others follow it (keepLinks).
    if (!c || i.kind !== 'image' || i.locked || (i.fx === c.fx && i.fy === c.fy && i.zoom === c.zoom)) return i
    changed = true
    return { ...i, ...c }
  })
  return changed ? { ...doc, items } : doc
}

function patch(doc: Doc, ids: Set<string>, fn: (i: ImageItem) => ImageItem): Doc {
  let changed = false
  const items = doc.items.map((i) => {
    if (i.kind !== 'image' || !ids.has(i.id)) return i
    const next = fn(i)
    if (next !== i) changed = true
    return next
  })
  return changed ? { ...doc, items } : doc
}

const withoutLink = (i: ImageItem): ImageItem => {
  if (!('link' in i)) return i
  const rest = { ...i }
  delete rest.link
  return rest
}

/** Why frames can't be linked, or null: picture frames, unturned, on one spread. */
export function linkProblem(doc: Doc, ids: string[]): string | null {
  const items = doc.items.filter((i) => ids.includes(i.id))
  if (items.length < 2 || items.some((i) => i.kind !== 'image')) return 'Select two picture frames or more.'
  if (items.some((i) => i.locked)) return 'Unlock the frames first.'
  if (items.some((i) => i.rot !== 0)) return 'Turned frames can’t share a picture.'
  const places = spreadPlaces(doc)
  if (new Set(items.map((i) => places.get(i.page)?.spread)).size !== 1) return 'Linked frames have to be on one spread.'
  // A cut-out partner (model/subject.ts) shows its picture's cut-out: its own asset.
  const pics = new Set(items.filter((i) => !(i as ImageItem).cutout).map((i) => (i as ImageItem).asset_id).filter(Boolean))
  if (pics.size > 1) return 'Those frames hold different pictures. Empty all but one first.'
  return null
}

/** Show one picture through these frames (the picture already in one of
 *  them, given to them all, fitted to cover them together). Their link is
 *  new, so frames from other groups leave theirs. */
export function linkFrames(doc: Doc, ids: string[], assets: Record<string, Asset>): Doc {
  if (linkProblem(doc, ids)) return doc
  const taken = doc.items.flatMap((i) => (i.kind === 'image' && i.link ? [i.link] : []))
  const link = newId('lk', taken)
  const pic = doc.items.find((i): i is ImageItem => ids.includes(i.id) && i.kind === 'image' && !!i.asset_id)?.asset_id ?? null
  const next = patch(doc, new Set(ids), (i) => ({ ...i, link, asset_id: pic, fit: 'fill' }))
  return refit(next, link, ids[0], assets, null)
}

/** Each frame keeps the crop it shows and goes its own way. A frame left
 *  alone in its group loses its link too. */
export function unlinkFrames(doc: Doc, ids: string[]): Doc {
  const gone = new Set(ids)
  for (const g of linkGroups(doc)) {
    const left = g.members.filter((m) => !gone.has(m.id))
    if (left.length === 1 && left.length < g.members.length) gone.add(left[0].id)
  }
  return patch(doc, gone, withoutLink)
}

/** Fit the group of `id` (linked `link`) to `want` (null: afresh). */
function refit(doc: Doc, link: string, id: string, assets: Record<string, Asset>, want: Placement | null): Doc {
  const g = linkGroups(doc).find((x) => x.link === link && x.members.some((m) => m.id === id))
  if (!g || g.members.length < 2) return doc
  const size = sizeOf(assets, g.members[0].asset_id)
  if (!size) return doc
  const p = fitPlacement(g.rects, size, want)
  const crops = p && cropsFor(g.rects, p, size)
  return crops ? setCrops(doc, g.members, crops) : doc
}

/** Whether a page faces another on its spread, and which. */
export function facingPage(doc: Doc, index: number): number | null {
  const pages = spreads(doc).find((s) => s.includes(index))
  return pages && pages.length === 2 ? pages[0] === index ? pages[1] : pages[0] : null
}

/** A picture frame made into one picture across its spread: two linked
 *  frames, one on each page, out to the bleed. `spine`: each stops this far
 *  short of the spine, so the fold stays clear. Returns the frames' ids. */
export function acrossSpread(doc: Doc, id: string, assets: Record<string, Asset>, spine = 0): { doc: Doc; ids: string[] } | null {
  const item = doc.items.find((i): i is ImageItem => i.id === id && i.kind === 'image')
  const index = item ? doc.pages.findIndex((p) => p.id === item.page) : -1
  const other = index === -1 ? null : facingPage(doc, index)
  if (!item || other === null || item.rot !== 0 || item.locked) return null
  const { w, h } = doc.size, b = doc.bleed
  const leftIndex = Math.min(index, other), rightIndex = Math.max(index, other)
  const half = (left: boolean) => ({ x: round(left ? -b : spine), y: round(-b), w: round(w + b - spine), h: round(h + 2 * b) })
  const taken = doc.items.flatMap((i) => (i.kind === 'image' && i.link ? [i.link] : []))
  const link = newId('lk', taken)
  const partnerId = newId('i', allIds(doc))
  const mine = index === leftIndex
  const partner: ImageItem = { ...withoutLink(item), id: partnerId, page: doc.pages[mine ? rightIndex : leftIndex].id,
    ...half(!mine), rot: 0, locked: false, hidden: false, link, fit: 'fill' }
  let next: Doc = { ...doc, items: [...doc.items, partner] }
  next = patch(next, new Set([id]), (i) => ({ ...i, ...half(mine), link, fit: 'fill' }))
  return { doc: refit(next, link, id, assets, null), ids: mine ? [id, partnerId] : [partnerId, id] }
}

const cropKey = (i: ImageItem) => `${i.fx}|${i.fy}|${i.zoom}`

/** Linked frames kept showing one picture after any edit (the store runs it
 *  on every change):
 *  - a picture placed in one frame goes into all of them, fitted afresh;
 *  - a frame's crop changed (its focus or zoom) moves the picture for all;
 *  - frames moved or resized together move the picture with them; one
 *    moved or resized alone is a window moved over the picture, which stays;
 *  - a frame turned, set to Fit or Stretch, or copied into a group that was
 *    already there leaves it.
 *  A group the picture can't cover any more (zoom past its most) keeps the
 *  crops it had. */
export function keepLinks(before: Doc, after: Doc, assets: Record<string, Asset>): Doc {
  if (after.items === before.items && after.pages === before.pages && after.size === before.size
    && after.facing === before.facing && after.bleed === before.bleed) return after
  if (!after.items.some((i) => i.kind === 'image' && i.link)) return after
  const old = new Map(before.items.map((i) => [i.id, i]))
  const oldGroups = new Map(linkGroups(before).map((g) => [`${g.link}|${g.spread}`, g]))
  let doc = after
  // Frames that can't be in a group (turned, not filling their frame), and
  // copies landing in a group that was already there, leave it.
  const leave = new Set<string>()
  for (const g of linkGroups(doc)) {
    const was = oldGroups.get(`${g.link}|${g.spread}`)
    for (const m of g.members) {
      if (m.rot !== 0 || m.fit !== 'fill' || (was && !old.has(m.id) && !m.cutout)) leave.add(m.id)
    }
  }
  if (leave.size) doc = patch(doc, leave, withoutLink)
  for (const g of linkGroups(doc)) {
    if (g.members.length < 2) continue
    const was = oldGroups.get(`${g.link}|${g.spread}`)
    const prev = g.members.map((m) => old.get(m.id) as ImageItem | undefined)
    // A picture placed or changed in one frame goes into all of them; a
    // locked frame keeps its own, and holds the group's picture where it is.
    // A cut-out partner keeps its own picture (the cut-out of the group's).
    const locked = g.members.findIndex((m) => m.locked && !m.cutout)
    const pics = g.members.map((m) => (m.cutout ? null : m.asset_id))
    const changedPic = g.members.find((m, k) => !m.cutout && m.asset_id && m.asset_id !== prev[k]?.asset_id)?.asset_id
    const pic = (locked !== -1 ? g.members[locked].asset_id : null) ?? changedPic ?? pics.find(Boolean) ?? null
    if (g.members.some((m) => !m.cutout && m.asset_id !== pic)) {
      const ids = new Set(g.members.filter((m) => !m.locked && !m.cutout).map((m) => m.id))
      doc = patch(doc, ids, (i) => (i.asset_id === pic ? i : { ...i, asset_id: pic }))
    }
    // A partner whose picture isn't the cut-out of the group's any more goes its own way.
    const stale = g.members.filter((m) => m.cutout && (!pic || !m.asset_id || (assets[m.asset_id] && assets[m.asset_id].parent !== pic)))
    if (stale.length) {
      doc = patch(doc, new Set(stale.map((m) => m.id)), withoutLink)
      if (g.members.length - stale.length < 2) continue
    }
    const size = sizeOf(assets, pic)
    if (!size) continue
    const same = was && was.members.length === g.members.length && prev.every((m) => !!m && was.members.includes(m))
    // Frames that were in the group before this edit, as they were.
    const stayed = g.members.findIndex((_, k) => !!was && !!prev[k] && was.members.includes(prev[k]!))
    let want: Placement | null = null
    // A group just made around a frame that was there (a cut-out partner set
    // over it): the picture stays where that frame showed it.
    const kept = was ? -1 : g.members.findIndex((m) => !m.cutout && old.has(m.id) && old.get(m.id)!.kind === 'image'
      && !(old.get(m.id) as ImageItem).link && cropKey(m) === cropKey(old.get(m.id) as ImageItem))
    if (locked !== -1 && g.members[locked].asset_id === pic) {
      want = shown(g.rects[locked], g.members[locked], size)
    } else if (kept !== -1 && g.members.some((m) => m.cutout)) {
      want = shown(g.rects[kept], g.members[kept], size)
    } else if (!same && !changedPic && was && stayed !== -1) {
      // Frames left or joined (unlinked, deleted, turned): the picture stays
      // where the frames still in the group showed it. Frames that all were
      // there, unmoved and uncropped, already show it: leave them be.
      const untouched = g.members.every((m, k) => {
        const p0 = prev[k]
        const at = p0 ? was.members.indexOf(p0) : -1
        return at !== -1 && cropKey(m) === cropKey(p0!) && m.page === p0!.page
          && ['x', 'y', 'w', 'h'].every((key) => g.rects[k][key as keyof Rect] === was.rects[at][key as keyof Rect])
      })
      if (untouched) continue
      want = shown(was.rects[was.members.indexOf(prev[stayed]!)], prev[stayed]!, size)
    } else if (same && !changedPic) {
      const oldRects = prev.map((m) => was.rects[was.members.indexOf(m!)])
      const moved = g.rects.map((r, k) => r.x !== oldRects[k].x || r.y !== oldRects[k].y || r.w !== oldRects[k].w
        || r.h !== oldRects[k].h || g.members[k].page !== prev[k]!.page)
      const cropped = g.members.findIndex((m, k) => !moved[k] && cropKey(m) !== cropKey(prev[k]!))
      if (cropped !== -1) want = shown(g.rects[cropped], g.members[cropped], size)
      else if (moved.some(Boolean)) {
        const still = moved.indexOf(false)
        const anchor = still === -1 ? 0 : still
        const was0 = shown(oldRects[anchor], prev[anchor]!, size)
        // All moved by one step, keeping their sizes: the picture goes with them.
        const dx = g.rects[0].x - oldRects[0].x, dy = g.rects[0].y - oldRects[0].y
        const together = still === -1 && g.rects.every((r, k) => Math.abs(r.x - oldRects[k].x - dx) < 1e-6
          && Math.abs(r.y - oldRects[k].y - dy) < 1e-6 && r.w === oldRects[k].w && r.h === oldRects[k].h)
        want = together ? { x: was0.x + dx, y: was0.y + dy, s: was0.s } : was0
      } else continue
    }
    const p = fitPlacement(g.rects, size, want) ?? (want ? fitPlacement(g.rects, size, null) : null)
    const crops = p && cropsFor(g.rects, p, size)
    if (crops) doc = setCrops(doc, g.members, crops)
  }
  return doc
}
