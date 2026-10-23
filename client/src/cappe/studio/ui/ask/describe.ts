// The document and the page in view, in words, for Ask the Studio
// (server/app/cappe/services/magazine/studio/ask.py): the page size, margins
// and columns, then every frame on the page, back to front, with its place,
// size, type and colours, in the document's units. It goes with every
// question, so it stays short: long text is cut to its start.

import { spreads } from '../../model/doc'
import { CHAR_DEFAULTS, PARA_DEFAULTS } from '../../model/limits'
import type { Asset, Doc, Item, Para, Run, Stroke, Thread, Units } from '../../model/types'
import { show } from '../../model/units'
import { LOOKS } from '../../picture/looks'
import type { State } from '../../store/store'

export const MAX_DESCRIPTION = 15_000
const MAX_PARAS = 4
const EXCERPT = 140

const UNIT_NAME: Record<Units, string> = { pt: 'points', pc: 'picas', in: 'inches', mm: 'millimetres', cm: 'centimetres', px: 'pixels' }
const SUFFIX: Record<Units, string> = { pt: ' pt', pc: '', in: ' in', mm: ' mm', cm: ' cm', px: ' px' }
const KIND: Record<Item['kind'], string> = { text: 'Text frame', image: 'Picture frame', rect: 'Rectangle', ellipse: 'Ellipse', line: 'Line' }
const ROLE = { p: 'Body text', h1: 'Headline', h2: 'Heading', h3: 'Subheading', quote: 'Pull quote', caption: 'Caption' } as const
const ALIGN = { l: 'left', c: 'centred', r: 'right', j: 'justified', ja: 'justified, last line too' } as const
const FIT = { fill: 'Fill', fit: 'Fit', stretch: 'Stretch' } as const

const n = (v: number) => String(Math.round(v * 100) / 100)

function describeDoc(doc: Doc): string {
  const len = (pt: number) => `${show(pt, doc.units)}${SUFFIX[doc.units]}`
  const m = doc.margins
  const lines = [
    `Document: ${doc.pages.length} page${doc.pages.length === 1 ? '' : 's'}, each ${len(doc.size.w)} wide × ${len(doc.size.h)} high; `
      + `${doc.facing ? 'facing pages (they pair up as spreads)' : 'single pages'}; units: ${UNIT_NAME[doc.units]}.`,
    `Margins: top ${len(m.t)}, bottom ${len(m.b)}, inside ${len(m.i)}, outside ${len(m.o)}. `
      + `${doc.cols.n} column${doc.cols.n === 1 ? '' : 's'}, gutter ${len(doc.cols.g)}. `
      + `Baseline grid every ${n(doc.baseline.step)} pt. Bleed ${len(doc.bleed)}. Paper colour ${doc.paper}.`,
  ]
  if (doc.paywall_page) lines.push(`Pages from page ${doc.paywall_page} on are for subscribers only.`)
  return lines.join('\n')
}

const strokeText = (s: Stroke | null) => (s ? `stroke ${n(s.w)} pt ${s.c}` : 'no stroke')
const fillText = (f: string | null) => (f ? `fill ${f}` : 'no fill')

function runStyle(r: Run, p: Para): string {
  const font = r.font ?? CHAR_DEFAULTS.font
  const wt = r.wt ?? CHAR_DEFAULTS.wt
  const lead = p.lead ?? PARA_DEFAULTS.lead
  const bits = [
    `${font} ${wt}${r.it ? ' italic' : ''}`, `${n(r.size ?? CHAR_DEFAULTS.size)} pt`,
    `leading ${lead ? `${n(lead)} pt` : 'auto'}`, `tracking ${r.track ?? CHAR_DEFAULTS.track}`,
    r.color ?? CHAR_DEFAULTS.color, ALIGN[p.align ?? PARA_DEFAULTS.align],
  ]
  if (r.u) bits.push('underlined')
  for (const [key, label] of [['li', 'left indent'], ['ri', 'right indent'], ['fi', 'first-line indent'],
    ['sb', 'space before'], ['sa', 'space after']] as const) {
    if (p[key]) bits.push(`${label} ${n(p[key]!)} pt`)
  }
  return bits.join(', ')
}

/** `s` cut to at most `n` UTF-16 units, never between the two halves of one
 *  character (an emoji): a half left alone is text the server refuses. */
export function clip(s: string, n: number): string {
  if (s.length <= n) return s
  const code = s.charCodeAt(n - 1)
  return s.slice(0, code >= 0xd800 && code <= 0xdbff ? n - 1 : n)
}

function paraLine(p: Para): string {
  const text = p.runs.map((r) => r.t).join('').replace(/\s+/g, ' ').trim()
  const excerpt = text.length > EXCERPT ? `${clip(text, EXCERPT)}…` : text
  const first = p.runs.find((r) => r.t.trim()) ?? p.runs[0] ?? { t: '' }
  const mixed = p.runs.some((r) => r.t.trim() && (r.font !== first.font || r.size !== first.size || r.color !== first.color
    || r.wt !== first.wt || !!r.it !== !!first.it))
  return `    · ${ROLE[p.role ?? PARA_DEFAULTS.role]}: "${excerpt || '(empty)'}" in ${runStyle(first, p)}${mixed ? ' (some words styled differently)' : ''}`
}

/** The part of a paragraph from `start` to `end` (UTF-16), its runs cut to fit. */
function slicePara(p: Para, start: number, end: number): Para {
  const runs: Para['runs'] = []
  let at = 0
  for (const r of p.runs) {
    const a = Math.max(start, at), b = Math.min(end, at + r.t.length)
    if (b > a) runs.push({ ...r, t: r.t.slice(a - at, b - at) })
    at += r.t.length
  }
  return { ...p, runs }
}

/** What a text frame shows: from the composition, the part of each
 *  paragraph set in it (a paragraph running on from the page before shows
 *  its own words and type here, not its beginning); else (an empty or new
 *  thread) the first paragraphs when it is the thread's first frame. */
function frameParas(item: Item, threads: Thread[]): { paras: Para[]; more: number; thread: Thread | null } {
  const thread = threads.find((t) => t.frames.includes(item.id)) ?? null
  if (!thread) return { paras: [], more: 0, thread }
  const at = thread.frames.indexOf(item.id)
  const ranges = new Map<number, [number, number]>()
  for (const l of thread.comp?.lines ?? []) {
    if (l[0] !== at) continue
    const r = ranges.get(l[1])
    ranges.set(l[1], r ? [Math.min(r[0], l[2]), Math.max(r[1], l[3])] : [l[2], l[3]])
  }
  let shown = [...ranges.keys()]
  if (!shown.length && at === 0 && !thread.comp?.lines.length) shown = thread.paras.map((_, i) => i)
  const paras = shown.slice(0, MAX_PARAS).flatMap((i) => {
    const p = thread.paras[i]
    const r = ranges.get(i)
    return !p ? [] : r ? [slicePara(p, r[0], r[1])] : [p]
  })
  return { paras, more: Math.max(0, shown.length - MAX_PARAS), thread }
}

function pictureText(asset: Asset | undefined): string {
  if (!asset) return 'a picture'
  const bits = [asset.alt ? `"${asset.alt}"` : 'a picture']
  if (asset.width && asset.height) {
    bits.push(asset.width > asset.height ? 'landscape' : asset.height > asset.width ? 'portrait' : 'square')
  }
  if (asset.ai_generated) bits.push('an AI illustration')
  const look = asset.recipe?.look && LOOKS.find((l) => l.key === asset.recipe!.look)
  if (look) bits.push(`edited with the ${look.label} look`)
  else if (asset.recipe) bits.push('edited in the Picture Editor')
  if (asset.recipe?.cutout) bits.push('cut out of its background')
  return bits.join(', ')
}

function itemLines(item: Item, s: State, len: (pt: number) => string): string[] {
  const head = [
    `- ${s.selection.includes(item.id) ? '[selected] ' : ''}${KIND[item.kind]} "${item.name || item.id}"`
      + `${item.hidden ? ' (hidden)' : ''}${item.locked ? ' (locked)' : ''}:`,
    `at ${len(item.x)} from the left, ${len(item.y)} from the top; ${len(item.w)} × ${len(item.h)}`,
  ]
  if (item.rot) head.push(`turned ${n(item.rot)}°`)
  if (item.opacity < 100) head.push(`opacity ${item.opacity}%`) // stored as a percentage
  const extra: string[] = []
  switch (item.kind) {
    case 'text': {
      if (item.cols > 1) extra.push(`${item.cols} columns, gutter ${len(item.gutter)}`)
      if (item.inset) extra.push(`inset ${len(item.inset)}`)
      if (item.valign !== 'top') extra.push(`text ${item.valign === 'center' ? 'centred' : item.valign === 'bottom' ? 'at the bottom' : 'justified'} vertically`)
      if (item.fill) extra.push(fillText(item.fill))
      if (item.stroke) extra.push(strokeText(item.stroke))
      const { paras, more, thread } = frameParas(item, s.doc.threads)
      if (thread && thread.frames.length > 1) {
        extra.push(`frame ${thread.frames.indexOf(item.id) + 1} of ${thread.frames.length} its text flows through`)
      }
      if (thread && s.overset.has(thread.id) && thread.frames[thread.frames.length - 1] === item.id) {
        extra.push("some of its text doesn't fit")
      }
      const lines = [[...head, ...extra].join('; ')]
      lines.push(...(paras.length ? paras.map(paraLine) : ['    · (no text)']))
      if (more) lines.push(`    · …and ${more} more paragraph${more === 1 ? '' : 's'}`)
      return lines
    }
    case 'image':
      extra.push(item.asset_id ? `shows ${pictureText(s.assets[item.asset_id])}` : 'empty (no picture yet)')
      if (item.asset_id) extra.push(`fit ${FIT[item.fit]}, zoom ${n(item.zoom)}%, focus ${n(item.fx)}% across, ${n(item.fy)}% down`)
      if (item.radius) extra.push(`corners ${len(item.radius)}`)
      if (item.fill) extra.push(fillText(item.fill))
      if (item.stroke) extra.push(strokeText(item.stroke))
      if (item.caption) extra.push(`caption "${clip(item.caption, EXCERPT)}"`)
      break
    case 'rect':
      extra.push(fillText(item.fill), strokeText(item.stroke))
      if (item.radius) extra.push(`corners ${len(item.radius)}`)
      break
    case 'ellipse':
      extra.push(fillText(item.fill), strokeText(item.stroke))
      break
    case 'line':
      extra.push(strokeText(item.stroke))
      break
  }
  return [[...head, ...extra].join('; ')]
}

/** The words Ask the Studio sends about the document and the page in view. */
export function describeStudio(s: State): string {
  const { doc } = s
  const len = (pt: number) => `${show(pt, doc.units)}${SUFFIX[doc.units]}`
  const page = doc.pages[s.page]
  const spread = spreads(doc).find((sp) => sp.includes(s.page)) ?? [s.page]
  const out = [describeDoc(doc)]
  out.push(`In view: page ${s.page + 1} of ${doc.pages.length}`
    + `${spread.length > 1 ? ` (a spread with page ${spread.find((p) => p !== s.page)! + 1})` : ''}.`)
  out.push(s.selection.length ? `Selected: ${s.selection.length} thing${s.selection.length === 1 ? '' : 's'}, marked [selected] below.` : 'Nothing is selected.')
  if (s.editing) out.push('The person is typing in a text frame.')

  const onPage = page ? doc.items.filter((i) => i.page === page.id) : []
  const elsewhere = doc.items.filter((i) => s.selection.includes(i.id) && i.page !== page?.id)
  const body = [
    `On page ${s.page + 1}, back to front (the last is on top):`,
    ...(onPage.length ? onPage.flatMap((i) => itemLines(i, s, len)) : ['(nothing on this page yet)']),
  ]
  if (elsewhere.length) body.push('Selected on other pages:', ...elsewhere.flatMap((i) => itemLines(i, s, len)))
  const tail = `The Picture Editor's looks: ${LOOKS.map((l) => l.label).join(', ')}.`

  let text = [...out, ...body, tail].join('\n')
  if (text.length > MAX_DESCRIPTION) {
    // Too much to send: the document, then what's selected (the "this" a
    // question means), then as many of the page's other things as fit.
    const head = out.join('\n')
    const isSel = (i: Item) => s.selection.includes(i.id)
    const kept: string[] = []
    let size = head.length + tail.length + 160, left = 0
    for (const i of [...onPage.filter(isSel), ...elsewhere, ...onPage.filter((x) => !isSel(x))]) {
      const lines = itemLines(i, s, len)
      const n = lines.reduce((a, l) => a + l.length + 1, 0)
      if (size + n > MAX_DESCRIPTION) { left++; continue }
      kept.push(...lines)
      size += n
    }
    text = [head, `On page ${s.page + 1}, what's selected first, then the rest:`, ...kept,
      `…and ${left} more thing${left === 1 ? '' : 's'} left out here.`, tail].join('\n')
  }
  return text
}
