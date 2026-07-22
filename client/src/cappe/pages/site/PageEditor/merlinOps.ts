// Merlin op types + a pure applier. Mirrors the op set the server validates
// in server/app/cappe/services/merlin.py — keep both in sync when adding an op.
//
// Ops address blocks by `id`, which the caller must set to each block's `_k`
// (the same stable React key PageEditor already assigns — see index.tsx's
// withKey/withKeys). Applying is pure: given the current blocks/theme and a
// validated op list, it returns the next blocks/theme plus a per-op result so
// the panel can render "applied" / "skipped" chips. Nothing here touches
// React state directly — the caller commits the result in one batch so
// useEditorHistory records a single undo step per Merlin turn.
import { CAPPE_THEMES, contrastText } from '../../../data/cappeThemes'
import type { CappeBlock, CappeCanvasElement } from '../../../types'
import { BLOCK_SCHEMAS } from './blockSchemas'
import { CV_MAX_ELEMENTS, cloneBlock, cvEls, cvNextY, genId, genKey } from './canvasHelpers'

export type MerlinCanvasElementInput = {
  kind: CappeCanvasElement['kind']
  text?: string
  src?: string
  alt?: string
  href?: string
  d?: CappeCanvasElement['d']
  style?: CappeCanvasElement['style']
}

export type MerlinDesignGroup = 'motion' | 'bg' | 'layout' | 'colors' | 'border' | 'anchor' | 'type' | 'image' | 'divider'

export type MerlinOp =
  | { op: 'set_field'; block: string; path: string; value: unknown }
  | { op: 'set_design'; block: string; group: MerlinDesignGroup; key: string; value: unknown }
  // Server-resolved: "all" is expanded to a concrete id list at validation
  // time, so the client here just targets the ids it's given (any missing
  // mid-flight are silently skipped, same as every other id-addressed op).
  | { op: 'set_design_bulk'; blocks: string[]; design: Partial<Record<MerlinDesignGroup, Record<string, unknown>>> }
  // `design` is a server-validated per-section design bag applied as `_design`
  // (lets one op create a fully styled section). `preset` is provenance from a
  // server-expanded apply_section_preset — the client treats it as a plain
  // add_block either way.
  // `id` is a model-assigned temp id (e.g. "new-1") — NOT the block's real
  // `_k` — so a LATER op in this same turn can target a block before it
  // exists. Server registers it the same way for validation; see tempIdMap.
  | { op: 'add_block'; type: string; at: number; content?: Record<string, unknown>; design?: Record<string, Record<string, unknown>>; preset?: string; id?: string }
  // `id` is a model-assigned temp id for the CLONE, same convention as
  // add_block's — lets a later op in this same turn address the duplicate
  // (e.g. "duplicate this, then restyle the copy") rather than only the
  // original `block`.
  | { op: 'duplicate_block'; block: string; at?: number; id?: string }
  | { op: 'remove_block'; block: string }
  | { op: 'move_block'; block: string; to: number }
  | { op: 'set_theme'; key: string; value: unknown }
  | { op: 'canvas_add'; block: string; element: MerlinCanvasElementInput }
  | { op: 'canvas_update'; block: string; el: string; patch: Partial<CappeCanvasElement> }
  | { op: 'canvas_remove'; block: string; el: string }
  // Server-validated, CLIENT-executed asynchronously: useMerlin generates the
  // image via the endpoint, then applies the URL as a follow-up set_field.
  // applyMerlinOps (a synchronous fold) never mutates state for it.
  | { op: 'generate_image'; block: string; field: string; prompt: string; aspect?: string }

export type MerlinOpResult = { ok: boolean; summary: string }
export type MerlinApplyResult = {
  blocks: CappeBlock[]
  theme: Record<string, unknown>
  results: MerlinOpResult[]
  /** Model-assigned add_block `id` → the block's real `_k`, for this turn
   *  only. useMerlin uses it to remap a same-turn generate_image's `block`
   *  before calling the (async, out-of-band) image endpoint. */
  tempIdMap: Record<string, string>
}

/** The subset of GET /merlin/schema this module reads — just enough to catch
 *  a `set_design` group/key the server doesn't actually offer (e.g. version
 *  skew between an old client bundle and a newer server registry). Optional:
 *  callers that don't fetch the schema fall back to today's behavior of
 *  applying whatever the server sent (it already validated group/key/value
 *  server-side — this is a belt-and-braces client check, not the source of
 *  truth). `blocks`/`sectionPresets`/`themePresets` are additionally read by
 *  the panel's `/` command menu, and `blocks[type].fields` by its "Apply
 *  image to…" menu (a field with kind "image" is a valid drop target) — see
 *  `build_merlin_schema` in `merlin_ops.py` for the full server-side shape
 *  this mirrors (a subset). */
export type MerlinDesignSchema = {
  design?: Record<string, Record<string, unknown>>
  blocks?: Record<string, { label: string; fields?: Record<string, { kind: string }> }>
  sectionPresets?: { name: string; label: string; blurb: string; blockType: string }[]
  themePresets?: { id: string; name: string; blurb: string; premium: boolean; mode: string }[]
}

const blockLabel = (type: unknown): string => BLOCK_SCHEMAS[type as string]?.label ?? String(type ?? 'block')

/** Immutable deep-set supporting object keys and numeric array indices
 *  (e.g. `deepSet(items, ['2','title'], 'New')`). Mirrors the server's
 *  dot-path convention for `set_field.path`.
 *
 *  Refuses rather than coerces on a container mismatch (`{ok: false}`). The
 *  server validates paths too, but this is the last line before content is
 *  overwritten: coercing here turned `path: "items.title"` on a list into
 *  `items: {title: …}`, silently deleting every card in the section while the
 *  chat reported success. Likewise an index past the end is refused instead
 *  of padding the array with `undefined` holes. */
function deepSet(target: unknown, parts: string[], value: unknown): { ok: boolean; value: unknown } {
  if (parts.length === 0) return { ok: true, value }
  const [key, ...rest] = parts
  const idx = /^\d+$/.test(key) ? Number(key) : null

  if (idx !== null) {
    if (!Array.isArray(target)) return { ok: false, value: target }
    if (idx > target.length) return { ok: false, value: target }  // == length is an append
    const inner = deepSet(target[idx], rest, value)
    if (!inner.ok) return { ok: false, value: target }
    const arr = [...target]
    arr[idx] = inner.value
    return { ok: true, value: arr }
  }

  // A named key into an array is the clobber case — refuse it.
  if (Array.isArray(target)) return { ok: false, value: target }
  const base = target && typeof target === 'object' ? { ...(target as Record<string, unknown>) } : {}
  const inner = deepSet(base[key], rest, value)
  if (!inner.ok) return { ok: false, value: target }
  base[key] = inner.value
  return { ok: true, value: base }
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
}

/** Apply one `set_theme` op. `key` is a dot path: `colors.brand`,
 *  `fonts.heading`, `type.<k>`, `style.<k>`, or a bare top-level key
 *  (`radius`, `mode`, `preset`, `premium`). `value === null` deletes the key,
 *  mirroring useThemeEditor's setTypeKey/setStyleKey convention. `colors.brand`
 *  additionally derives `accent`/`brandText`, matching useThemeEditor.setBrand —
 *  a chat "change the brand color" request should look the same as using the
 *  color picker. */
function applyThemeOp(theme: Record<string, unknown>, key: string, value: unknown): Record<string, unknown> | null {
  // `preset` must load the preset's whole config, exactly as
  // useThemeEditor.applyPreset does. Writing only `theme.preset` left the old
  // palette rendering while the theme menu highlighted the new preset as
  // active — a divergence that then got persisted on Save.
  if (key === 'preset') {
    const preset = CAPPE_THEMES.find((p) => p.id === value)
    if (!preset) return null
    return { ...preset.config, preset: preset.id }
  }
  if (key === 'colors.brand' && typeof value === 'string') {
    return { ...theme, colors: { ...asRecord(theme.colors), brand: value, accent: value, brandText: contrastText(value) } }
  }
  if (key === 'mode' && (value === 'light' || value === 'dark') && theme.mode !== value) {
    // render.py's `_tokens` picks the LIGHT/DARK base palette from `mode`,
    // then lets explicit `theme.colors` override it — so on a theme whose
    // preset stored its own surface colors (every dark preset does), writing
    // `mode` alone changes the flag and nothing else paints. Clear the
    // SURFACE keys (not brand/accent/brandText — that's identity, not mode)
    // so the new mode's base actually shows through.
    const colors = { ...asRecord(theme.colors) }
    for (const k of ['bg', 'surface', 'text', 'muted', 'border']) delete colors[k]
    return { ...theme, mode: value, colors }
  }
  const [head, ...rest] = key.split('.')
  if (rest.length) {
    const sub = rest.join('.')
    const bag = { ...asRecord(theme[head]) }
    if (value == null) delete bag[sub]; else bag[sub] = value
    return { ...theme, [head]: bag }
  }
  const next = { ...theme }
  if (value == null) delete next[head]; else next[head] = value
  return next
}

export function applyMerlinOps(
  blocks: CappeBlock[],
  theme: Record<string, unknown>,
  ops: MerlinOp[],
  schema?: MerlinDesignSchema,
): MerlinApplyResult {
  let nextBlocks = blocks
  let nextTheme = theme
  const results: MerlinOpResult[] = []
  // add_block(id="new-1") records here; every later op's `.block` resolves
  // through this first, so an id an earlier op in THIS turn assigned targets
  // the block it actually became — the temp id is never used as the real
  // `_k` (two turns could both say "new-1").
  const tempIdMap: Record<string, string> = {}
  const resolveBlock = (id: string) => tempIdMap[id] ?? id

  const findCanvas = (id: string): { idx: number; block: CappeBlock } | null => {
    const idx = nextBlocks.findIndex((b) => b._k === id)
    if (idx === -1 || nextBlocks[idx].type !== 'canvas') return null
    return { idx, block: nextBlocks[idx] }
  }

  for (const op of ops) {
    switch (op.op) {
      case 'set_field': {
        const idx = nextBlocks.findIndex((b) => b._k === resolveBlock(op.block))
        if (idx === -1) { results.push({ ok: false, summary: 'Skipped — section no longer exists' }); break }
        const block = nextBlocks[idx]
        const [head, ...rest] = op.path.split('.')
        let newVal: unknown = op.value
        if (rest.length) {
          const r = deepSet(block[head], rest, op.value)
          if (!r.ok) { results.push({ ok: false, summary: `Skipped — "${op.path}" doesn't match this section's shape` }); break }
          newVal = r.value
        }
        const updated = { ...block, [head]: newVal }
        nextBlocks = nextBlocks.map((b, i) => (i === idx ? updated : b))
        results.push({ ok: true, summary: `Edited ${blockLabel(block.type)} — ${head}` })
        break
      }
      case 'set_design': {
        const idx = nextBlocks.findIndex((b) => b._k === resolveBlock(op.block))
        if (idx === -1) { results.push({ ok: false, summary: 'Skipped — section no longer exists' }); break }
        if (schema?.design && !(op.key in (schema.design[op.group] || {}))) {
          results.push({ ok: false, summary: `Skipped — unknown design setting "${op.group}.${op.key}"` })
          break
        }
        const block = nextBlocks[idx]
        const design = asRecord(block._design)
        const group = { ...asRecord(design[op.group]) }
        // '' / null clears the key — same convention as DesignInspector's patch().
        if (op.value === '' || op.value == null) delete group[op.key]
        else group[op.key] = op.value
        nextBlocks = nextBlocks.map((b, i) =>
          (i === idx ? { ...b, _design: { ...design, [op.group]: group } } : b))
        results.push({ ok: true, summary: `${blockLabel(block.type)} — ${op.group} ${op.key}` })
        break
      }
      case 'set_design_bulk': {
        const targets = new Set(op.blocks.map(resolveBlock))
        const groupsTouched = new Set<string>()
        let changed = 0
        // Referential stability: a run that matches nothing must return the
        // identical `nextBlocks` ref, same contract as every other op here —
        // index.tsx keys "did anything change?" off reference equality, and a
        // fresh array from .map() would push a spurious undo entry.
        if (nextBlocks.some((b) => targets.has(b._k as string))) {
          nextBlocks = nextBlocks.map((b) => {
            if (!targets.has(b._k as string)) return b
            const design = asRecord(b._design)
            const merged: Record<string, unknown> = { ...design }
            for (const [group, keys] of Object.entries(op.design)) {
              merged[group] = { ...asRecord(design[group]), ...keys }
              groupsTouched.add(group)
            }
            changed += 1
            return { ...b, _design: merged }
          })
        }
        results.push(changed === 0
          ? { ok: false, summary: 'Skipped — none of the targeted sections exist' }
          : { ok: true, summary: `Styled ${changed} section${changed === 1 ? '' : 's'} — ${[...groupsTouched].join(', ')}` })
        break
      }
      case 'add_block': {
        const schema = BLOCK_SCHEMAS[op.type]
        if (!schema) { results.push({ ok: false, summary: `Skipped — unknown block type "${op.type}"` }); break }
        const nb: CappeBlock = { ...schema.make(), ...(op.content || {}), _k: genKey() }
        if (op.design && Object.keys(op.design).length > 0) nb._design = op.design
        if (op.id) tempIdMap[op.id] = nb._k as string
        const at = Math.max(0, Math.min(op.at, nextBlocks.length))
        nextBlocks = [...nextBlocks.slice(0, at), nb, ...nextBlocks.slice(at)]
        results.push({ ok: true, summary: op.preset ? `Added ${schema.label} (${op.preset} preset)` : `Added ${schema.label}` })
        break
      }
      case 'duplicate_block': {
        const idx = nextBlocks.findIndex((b) => b._k === resolveBlock(op.block))
        if (idx === -1) { results.push({ ok: false, summary: 'Skipped — section no longer exists' }); break }
        const src = nextBlocks[idx]
        const clone = cloneBlock(src)
        if (op.id) tempIdMap[op.id] = clone._k as string
        const at = op.at !== undefined ? Math.max(0, Math.min(op.at, nextBlocks.length)) : idx + 1
        nextBlocks = [...nextBlocks.slice(0, at), clone, ...nextBlocks.slice(at)]
        results.push({ ok: true, summary: `Duplicated ${blockLabel(src.type)}` })
        break
      }
      case 'remove_block': {
        const idx = nextBlocks.findIndex((b) => b._k === resolveBlock(op.block))
        if (idx === -1) { results.push({ ok: false, summary: 'Skipped — section already removed' }); break }
        const label = blockLabel(nextBlocks[idx].type)
        nextBlocks = nextBlocks.filter((_, i) => i !== idx)
        results.push({ ok: true, summary: `Removed ${label}` })
        break
      }
      case 'move_block': {
        const from = nextBlocks.findIndex((b) => b._k === resolveBlock(op.block))
        if (from === -1) { results.push({ ok: false, summary: 'Skipped — section no longer exists' }); break }
        const to = Math.max(0, Math.min(op.to, nextBlocks.length - 1))
        const label = blockLabel(nextBlocks[from].type)
        if (to === from) { results.push({ ok: true, summary: `${label} already in place` }); break }
        const next = [...nextBlocks]
        const [moved] = next.splice(from, 1)
        next.splice(to, 0, moved)
        nextBlocks = next
        results.push({ ok: true, summary: `Moved ${label}` })
        break
      }
      case 'set_theme': {
        const applied = applyThemeOp(nextTheme, op.key, op.value)
        if (applied === null) { results.push({ ok: false, summary: `Skipped — no theme called "${String(op.value)}"` }); break }
        nextTheme = applied
        results.push({ ok: true, summary: op.key === 'preset' ? `Switched theme to ${String(op.value)}` : `Updated ${op.key}` })
        break
      }
      case 'canvas_add': {
        const found = findCanvas(resolveBlock(op.block))
        if (!found) { results.push({ ok: false, summary: 'Skipped — canvas section not found' }); break }
        const els = cvEls(found.block)
        if (els.length >= CV_MAX_ELEMENTS) { results.push({ ok: false, summary: 'Skipped — canvas is full' }); break }
        const newEl: CappeCanvasElement = {
          id: genId(),
          kind: op.element.kind,
          ...(op.element.text !== undefined ? { text: op.element.text } : {}),
          ...(op.element.src !== undefined ? { src: op.element.src } : {}),
          ...(op.element.alt !== undefined ? { alt: op.element.alt } : {}),
          ...(op.element.href !== undefined ? { href: op.element.href } : {}),
          d: op.element.d ?? { x: 1, y: cvNextY(els), w: 8, h: 2 },
          ...(op.element.style ? { style: op.element.style } : {}),
        }
        nextBlocks = nextBlocks.map((b, i) => (i === found.idx ? { ...b, elements: [...els, newEl] } : b))
        results.push({ ok: true, summary: 'Added element to canvas' })
        break
      }
      case 'canvas_update': {
        const found = findCanvas(resolveBlock(op.block))
        if (!found) { results.push({ ok: false, summary: 'Skipped — canvas section not found' }); break }
        const els = cvEls(found.block)
        const elIdx = els.findIndex((e) => e.id === op.el)
        if (elIdx === -1) { results.push({ ok: false, summary: 'Skipped — element no longer exists' }); break }
        const nextEls = els.map((e, i) => (i === elIdx ? { ...e, ...op.patch } : e))
        nextBlocks = nextBlocks.map((b, i) => (i === found.idx ? { ...b, elements: nextEls } : b))
        results.push({ ok: true, summary: 'Updated canvas element' })
        break
      }
      case 'canvas_remove': {
        const found = findCanvas(resolveBlock(op.block))
        if (!found) { results.push({ ok: false, summary: 'Skipped — canvas section not found' }); break }
        const els = cvEls(found.block)
        if (!els.some((e) => e.id === op.el)) { results.push({ ok: false, summary: 'Skipped — element no longer exists' }); break }
        nextBlocks = nextBlocks.map((b, i) => (i === found.idx ? { ...b, elements: els.filter((e) => e.id !== op.el) } : b))
        results.push({ ok: true, summary: 'Removed canvas element' })
        break
      }
      case 'generate_image':
        // Handled out-of-band by useMerlin (async endpoint call → follow-up
        // set_field). Defensive no-op here so it isn't mislabeled "unrecognized"
        // if one ever reaches the synchronous fold.
        break
      default:
        results.push({ ok: false, summary: 'Skipped — unrecognized op' })
    }
  }

  return { blocks: nextBlocks, theme: nextTheme, results, tempIdMap }
}
