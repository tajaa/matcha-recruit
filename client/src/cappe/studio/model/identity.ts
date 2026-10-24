// References stay in the editable document. Only composition and rendering
// receive resolved attributes, so saving/typing cannot freeze an inherited style.
import { allIds, charOf, newId, paraOf, sparsePara } from './doc'
import type { CharAttrs, Doc, Item, MagazineIdentity, Para, ParentLayout, Thread } from './types'
import { identityName, LIMITS, round } from './limits'
import { applyPara } from './ops'

export const IDENTITY_LIMITS = { styles: 32, swatches: 24, parents: 8, parentItems: 80, bytes: 500_000 } as const

export function starterIdentity(): MagazineIdentity {
  return { v: 1, name: 'Magazine identity',
    paragraphs: [
      { id: 'ps1', name: 'Body', char: charOf({}), para: paraOf({ sa: 6 }) },
      { id: 'ps2', name: 'Heading', char: charOf({ font: 'Inter', wt: 600, size: 28 }), para: paraOf({ role: 'h2', sa: 12 }) },
      { id: 'ps3', name: 'Caption', char: { ...charOf({ font: 'Inter', size: 8 }), swatch: 'sw2' }, para: paraOf({ role: 'caption', sa: 4 }) },
    ],
    characters: [{ id: 'cs1', name: 'Emphasis', char: { it: true } }],
    swatches: [{ id: 'sw1', name: 'Ink', color: '#1a1a1a' }, { id: 'sw2', name: 'Muted', color: '#72726b' }, { id: 'sw3', name: 'Accent', color: '#b44d35' }],
    parents: [], furniture: { numbers: false, header: '', start: 1, skip_first: true, inset: 24, char: charOf({ font: 'Inter', size: 8 }) },
  }
}

export function resolveChar(raw: CharAttrs, base: CharAttrs = {}, identity?: MagazineIdentity): ReturnType<typeof charOf> {
  const named = identity?.characters.find((s) => s.id === raw.style)?.char
  const merged = { ...base }
  for (const layer of [named, raw]) if (layer) {
    if (layer.color !== undefined && layer.swatch === undefined) delete merged.swatch
    Object.assign(merged, layer)
  }
  const color = identity?.swatches.find((s) => s.id === merged.swatch)?.color
  return charOf({ ...merged, ...(color ? { color } : {}) })
}

const resolved = new WeakMap<MagazineIdentity, WeakMap<Para[], Para[]>>()
export function resolveParas(paras: Para[], identity?: MagazineIdentity): Para[] {
  if (!identity) return paras
  let cache = resolved.get(identity)
  if (!cache) { cache = new WeakMap(); resolved.set(identity, cache) }
  const hit = cache.get(paras)
  if (hit) return hit
  const out = paras.map((p) => {
    const named = identity.paragraphs.find((s) => s.id === p.style)
    return { ...paraOf({ ...named?.para, ...p }), runs: p.runs.map((r) => ({ t: r.t, ...resolveChar(r, named?.char, identity) })) }
  })
  cache.set(paras, out)
  return out
}

export function resolvedThreads(doc: Doc): Thread[] {
  return doc.identity ? doc.threads.map((t) => ({ ...t, paras: resolveParas(t.paras, doc.identity) })) : doc.threads
}

export function resolveItem(item: Item, identity?: MagazineIdentity): Item {
  if (!identity) return item
  const fill = identity.swatches.find((s) => s.id === item.fill_swatch)?.color
  const stroke = identity.swatches.find((s) => s.id === item.stroke_swatch)?.color
  return { ...item, ...(fill && (item.kind !== 'graphic' || item.color !== null) ? { [item.kind === 'graphic' ? 'color' : 'fill']: fill } : {}),
    ...('stroke' in item && item.stroke && stroke ? { stroke: { ...item.stroke, c: stroke } } : {}) } as Item
}

const parentDocuments = new WeakMap<MagazineIdentity, WeakMap<ParentLayout, Doc>>()
export function parentDoc(doc: Doc, parent: ParentLayout): Doc {
  let cache = doc.identity ? parentDocuments.get(doc.identity) : undefined
  if (doc.identity && !cache) { cache = new WeakMap(); parentDocuments.set(doc.identity, cache) }
  const hit = cache?.get(parent)
  if (hit) return hit
  const made: Doc = { ...doc, size: parent.size, pages: [{ id: 'p1' }], items: parent.items, threads: parent.threads, guides: [],
    identity: doc.identity ? { ...doc.identity, parents: [], furniture: { ...doc.identity.furniture, numbers: false, header: '' } } : undefined }
  cache?.set(parent, made)
  return made
}

/** Capture only complete local threads; a shared layout cannot own a fragment
 * of the story's linked text or any site-owned photograph. */
export function captureParent(doc: Doc, page: number, id: string, name: string): Doc {
  const identity = doc.identity ?? starterIdentity()
  const pageId = doc.pages[page].id
  if (doc.pages[page].parent) throw new Error('Detach this page’s parent before saving or updating its local design.')
  const items = doc.items.filter((i) => i.page === pageId)
  if (!items.length) throw new Error('Put the recurring frames on this page first, or detach its parent to edit a copy.')
  if (items.length > IDENTITY_LIMITS.parentItems) throw new Error('A parent holds up to 80 frames.')
  const ids = new Set(items.map((i) => i.id))
  const threads = doc.threads.filter((t) => t.frames.some((f) => ids.has(f)))
  if (threads.some((t) => !t.frames.every((f) => ids.has(f)))) throw new Error('Unlink text that flows to another page before saving this parent.')
  if (!identity.parents.some((p) => p.id === id) && identity.parents.length >= IDENTITY_LIMITS.parents) throw new Error('Save up to eight parent layouts.')
  const parent: ParentLayout = { id, name, size: doc.size,
    items: items.map((i) => ({ ...i, page: 'p1', ...(i.kind === 'image' ? { asset_id: null, caption: '' } : {}) })),
    threads: threads.map(({ id, frames, paras }) => ({ id, frames, paras })),
  }
  return { ...doc, identity: { ...identity, parents: [...identity.parents.filter((p) => p.id !== id), parent] },
    pages: doc.pages.map((p, k) => k === page ? { ...p, parent: id } : p), items: doc.items.filter((i) => !ids.has(i.id)),
    threads: doc.threads.filter((t) => !threads.includes(t)) }
}

/** Make a page's parent ordinary local frames; all other pages stay linked. */
export function detachParent(doc: Doc, page: number): Doc {
  const parent = doc.identity?.parents.find((p) => p.id === doc.pages[page].parent)
  if (!parent) return doc
  const taken = allIds(doc), fresh = (prefix: string) => { const id = newId(prefix, taken); taken.push(id); return id }
  const ids = new Map(parent.items.map((i) => [i.id, fresh(i.kind[0])]))
  const scale = Math.min(doc.size.w / parent.size.w, doc.size.h / parent.size.h)
  const fit = (n: number) => round(n * scale)
  const pages = doc.pages.map((p, k) => { if (k !== page) return p; const out = { ...p }; delete out.parent; return out })
  const items = parent.items.map((i): Item => ({ ...i, id: ids.get(i.id)!, page: doc.pages[page].id,
    x: fit(i.x), y: fit(i.y), w: fit(i.w), h: fit(i.h),
    ...('stroke' in i && i.stroke ? { stroke: { ...i.stroke, w: fit(i.stroke.w) } } : {}),
    ...('radius' in i ? { radius: fit(i.radius) } : {}),
    ...(i.kind === 'text' ? { inset: fit(i.inset), gutter: fit(i.gutter) } : {}),
    ...(i.kind === 'graphic' ? { tile: fit(i.tile) } : {}),
  }))
  const threads = parent.threads.map((t) => ({ id: fresh('s'), frames: t.frames.map((f) => ids.get(f)!),
    paras: scale === 1 ? t.paras : resolveParas(t.paras, doc.identity).map((p) => ({ ...p,
      ...Object.fromEntries(['li', 'ri', 'fi', 'sb', 'sa', 'lead'].map((k) => [k, fit(p[k as keyof Para] as number)])),
      runs: p.runs.map((r) => ({ ...r, size: fit(r.size!) })),
    })),
  }))
  if (items.some((i) => Math.abs(i.x) > LIMITS.COORD || Math.abs(i.y) > LIMITS.COORD || i.w > LIMITS.COORD || i.h > LIMITS.COORD
    || ('stroke' in i && i.stroke && (i.stroke.w <= 0 || i.stroke.w > LIMITS.STROKE_MAX))
    || ('radius' in i && i.radius > LIMITS.RADIUS_MAX) || (i.kind === 'text' && (i.gutter > LIMITS.GUTTER_MAX || i.inset > LIMITS.GUTTER_MAX))
    || (i.kind === 'graphic' && (i.tile < LIMITS.TILE_MIN || i.tile > LIMITS.TILE_MAX)))
    || threads.some((t) => t.paras.some((p) => (p.lead ?? 0) > LIMITS.LEAD_MAX || (['li', 'ri', 'fi', 'sb', 'sa'] as const).some((k) => (p[k] ?? 0) > LIMITS.INDENT_MAX)
      || p.runs.some((r) => r.size !== undefined && (r.size < 1 || r.size > LIMITS.SIZE_MAX))))) throw new Error('This parent is too different in size to detach safely. Use a page size closer to its original.')
  return { ...doc, pages, items: [...items, ...doc.items], threads: [...doc.threads, ...threads] }
}

/** Removing a definition leaves its text's appearance intact. */
export function removeStyle(doc: Doc, kind: 'paragraphs' | 'characters', id: string): Doc {
  if (!doc.identity) return doc
  const materialize = (base: CharAttrs, raw: Para['runs'][number]) => {
    const out = { ...base, ...raw }
    if (raw.color !== undefined && raw.swatch === undefined) delete out.swatch
    return out
  }
  const clean = (threads: Thread[]) => threads.map((t) => ({ ...t, paras: t.paras.map((p) => {
    const shown = resolveParas([p], doc.identity)[0]
    if (kind === 'paragraphs' && p.style === id) {
      const base = doc.identity!.paragraphs.find((s) => s.id === id)?.char ?? {}
      return { ...sparsePara(shown), runs: p.runs.map((r) => {
        const inherited = { ...base }, character = doc.identity!.characters.find((s) => s.id === r.style)?.char
        // Materialize only the deleted paragraph's contribution. Existing
        // character styles and local overrides retain their precedence.
        if (character) {
          for (const key of Object.keys(character) as (keyof CharAttrs)[]) delete inherited[key]
          if (character.color !== undefined || character.swatch !== undefined) { delete inherited.color; delete inherited.swatch }
        }
        return materialize(inherited, r)
      }) }
    }
    return { ...p, runs: p.runs.map((r) => {
      if (kind !== 'characters' || r.style !== id) return r
      const local = { ...r }; delete local.style
      return materialize(doc.identity!.characters.find((s) => s.id === id)?.char ?? {}, local)
    }) }
  }) }))
  return { ...doc, threads: clean(doc.threads), identity: { ...doc.identity,
    [kind]: doc.identity[kind].filter((s) => s.id !== id), parents: doc.identity.parents.map((p) => ({ ...p, threads: clean(p.threads) })) } }
}

/** Merge by name, remapping source IDs before any references are copied. */
export function importIdentity(doc: Doc, source: MagazineIdentity): Doc {
  if (!doc.identity) return { ...doc, identity: structuredClone(source) }
  const target = doc.identity
  const maps = { paragraphs: new Map<string, string>(), characters: new Map<string, string>(), swatches: new Map<string, string>(), parents: new Map<string, string>() }
  for (const kind of ['paragraphs', 'characters', 'swatches', 'parents'] as const) {
    const used = target[kind].map((s) => s.id)
    for (const row of source[kind]) {
      const match = target[kind].find((s) => identityName(s.name).toLowerCase() === identityName(row.name).toLowerCase())
      const id = match?.id ?? newId(kind === 'paragraphs' ? 'ps' : kind === 'characters' ? 'cs' : kind === 'swatches' ? 'sw' : 'pl', used)
      used.push(id); maps[kind].set(row.id, id)
    }
  }
  const character = (c: CharAttrs) => ({ ...c, ...(c.style ? { style: maps.characters.get(c.style)! } : {}), ...(c.swatch ? { swatch: maps.swatches.get(c.swatch)! } : {}) })
  const identity: MagazineIdentity = { ...target, name: source.name, furniture: { ...source.furniture, char: character(source.furniture.char) } }
  for (const kind of ['paragraphs', 'characters', 'swatches', 'parents'] as const) {
    const incoming = source[kind].map((r) => {
      const row = { ...r, id: maps[kind].get(r.id)! }
      if ('char' in row) row.char = character(row.char)
      if ('items' in row) {
        row.items = row.items.map((i) => ({ ...i, ...(i.fill_swatch ? { fill_swatch: maps.swatches.get(i.fill_swatch)! } : {}), ...(i.stroke_swatch ? { stroke_swatch: maps.swatches.get(i.stroke_swatch)! } : {}) }))
        row.threads = row.threads.map((t) => ({ ...t, comp: undefined, paras: t.paras.map((p) => ({ ...p, ...(p.style ? { style: maps.paragraphs.get(p.style)! } : {}), runs: p.runs.map((r) => ({ ...character(r), t: r.t })) })) }))
      }
      return row
    })
    const ids = new Set(incoming.map((r) => r.id))
    // The discriminant is retained by each individual mapping above.
    Object.assign(identity, { [kind]: [...target[kind].filter((r) => !ids.has(r.id)), ...incoming] })
  }
  return { ...doc, identity }
}

export function removeSwatch(doc: Doc, id: string): Doc {
  const color = doc.identity?.swatches.find((s) => s.id === id)?.color
  if (!color) return doc
  const out = structuredClone(doc)
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object') return
    if (Array.isArray(value)) { value.forEach(visit); return }
    const row = value as Record<string, unknown>
    if (row.swatch === id) { delete row.swatch; row.color = color }
    if (row.fill_swatch === id) { delete row.fill_swatch; row[row.kind === 'graphic' ? 'color' : 'fill'] = color }
    if (row.stroke_swatch === id) { delete row.stroke_swatch; if (row.stroke) row.stroke = { ...(row.stroke as object), c: color } }
    Object.values(row).forEach(visit)
  }
  visit(out)
  out.identity!.swatches = out.identity!.swatches.filter((s) => s.id !== id)
  return out
}

export function linkRole(doc: Doc, id: string): Doc {
  const identity = doc.identity, style = identity?.paragraphs.find((p) => p.id === id)
  if (!identity || !style) return doc
  const link = (threads: Thread[]) => threads.map((t) => {
    const shown = resolveParas(t.paras, identity)
    return { ...t, paras: t.paras.map((p, k) => shown[k].role === (style.para.role ?? 'p') ? applyPara([p], 0, 0, { style: id })[0] : p) }
  })
  return { ...doc, threads: link(doc.threads), identity: { ...identity, parents: identity.parents.map((p) => ({ ...p, threads: link(p.threads) })) } }
}
