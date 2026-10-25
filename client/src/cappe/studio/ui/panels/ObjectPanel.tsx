import { ArrowDownToLine, ArrowUpToLine, ChevronDown, ChevronUp, Columns2, Eye, EyeOff, Image as ImageIcon, Link2, Link2Off, Lock, PersonStanding, Scissors, SeparatorVertical,
  SlidersHorizontal, Unlock } from 'lucide-react'
import { ColorField, IconBtn, NumberField, Row, Section, Seg, Slider } from '../../../magazine/workspace/controls'
import { groupOf, linkProblem } from '../../model/crops'
import { round } from '../../model/limits'
import { resolveItem } from '../../model/identity'
import { arrange, patchItems, unlinkAfter, type Arrange } from '../../model/ops'
import { cutoutFor, isCutout, subjectProblem } from '../../model/subject'
import type { Fit, GraphicFit, GraphicItem, Item, Shape, Stroke, VAlign, Wrap } from '../../model/types'
import { placeSubject, subjectShape } from '../subject'
import { useStudio } from '../../store/store'
import { command } from '../commands'
import { useCtx } from '../context'
import { LengthField, Labeled } from '../fields'

const FITS: { key: Fit; label: string }[] = [{ key: 'fill', label: 'Fill' }, { key: 'fit', label: 'Fit' }, { key: 'stretch', label: 'Stretch' }]
const GRAPHIC_FITS: { key: GraphicFit; label: string }[] = [
  { key: 'contain', label: 'Its shape' }, { key: 'stretch', label: 'Stretch' }, { key: 'tile', label: 'Repeat' },
]
const VALIGNS: { key: VAlign; label: string }[] = [
  { key: 'top', label: 'Top' }, { key: 'center', label: 'Centre' }, { key: 'bottom', label: 'Bottom' }, { key: 'justify', label: 'Justify' },
]

/** What the selection is and how it sits: place, size, turn, and its own
 *  options (a text frame's columns, a picture's fit, fills and strokes). */
export function ObjectPanel() {
  const c = useCtx()
  const { store } = c
  const doc = useStudio(store, (s) => s.doc)
  const selection = useStudio(store, (s) => s.selection)
  const overset = useStudio(store, (s) => s.overset)
  const assets = useStudio(store, (s) => s.assets)
  const items = doc.items.filter((i) => selection.includes(i.id)).map((i) => resolveItem(i, doc.identity))
  if (!items.length) {
    return (
      <Section title="Object">
        <p className="text-xs leading-relaxed text-zinc-500">Nothing selected. Draw a frame with a tool, or click something on a page.</p>
      </Section>
    )
  }
  const one = items[0]
  const ids = items.map((i) => i.id)
  const set = (patch: Record<string, unknown>, key?: string) => store.edit((d) => patchItems(d, ids, patch), { key: key ?? null })
  const same = <K extends keyof Item>(k: K) => items.every((i) => i[k] === one[k])
  const units = doc.units
  const kinds = new Set(items.map((i) => i.kind))
  const only = kinds.size === 1 ? one.kind : null
  const inked = items.filter((i): i is GraphicItem => i.kind === 'graphic' && i.color !== null)
  return (
    <>
      <Section title={items.length > 1 ? `${items.length} selected` : KIND_LABEL[one.kind]} right={
        <div className="flex">
          <IconBtn title={items.every((i) => i.locked) ? 'Unlock' : 'Lock'} onClick={() => set({ locked: !items.every((i) => i.locked) })}>
            {items.every((i) => i.locked) ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
          </IconBtn>
          <IconBtn title="Hide" onClick={() => store.edit((d) => patchItems(d, ids, { hidden: true }), { extra: { selection: [] } })}>
            {one.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </IconBtn>
        </div>
      }>
        <Row>
          <LengthField label="X" units={units} value={one.x} mixed={!same('x')} onChange={(x) => set({ x: round(x) })} />
          <LengthField label="Y" units={units} value={one.y} mixed={!same('y')} onChange={(y) => set({ y: round(y) })} />
        </Row>
        <Row>
          <LengthField label="Width" short="W" units={units} value={one.w} min={0} mixed={!same('w')} onChange={(w) => set({ w })} />
          <LengthField label="Height" short="H" units={units} value={one.h} min={0} mixed={!same('h')} onChange={(h) => set({ h })} />
        </Row>
        <Row>
          <NumberField label="Turn" short="↻" value={one.rot} min={-180} max={180} places={2} unit="°" mixed={!same('rot')}
            onChange={(rot) => set({ rot })} />
          <NumberField label="Opacity" short="α" value={one.opacity} min={0} max={100} places={0} unit="%" mixed={!same('opacity')}
            onChange={(opacity) => set({ opacity })} />
        </Row>
        <div className="flex gap-1" role="group" aria-label="Arrange">
          {(['front', 'forward', 'backward', 'back'] as Arrange[]).map((a) => (
            <IconBtn key={a} title={ARRANGE[a]} onClick={() => store.edit((d) => arrange(d, ids, a))}>
              {a === 'front' ? <ArrowUpToLine className="h-3.5 w-3.5" /> : a === 'forward' ? <ChevronUp className="h-3.5 w-3.5" />
                : a === 'backward' ? <ChevronDown className="h-3.5 w-3.5" /> : <ArrowDownToLine className="h-3.5 w-3.5" />}
            </IconBtn>
          ))}
        </div>
      </Section>

      {only === 'text' && one.kind === 'text' && (
        <Section title="Text frame">
          <Row>
            <NumberField label="Columns" short="▥" value={one.cols} min={1} max={12} places={0} onChange={(cols) => set({ cols })} />
            <LengthField label="Gutter" short="↔" units={units} value={one.gutter} min={0} max={288} onChange={(gutter) => set({ gutter })} />
          </Row>
          <Row>
            <LengthField label="Inset" short="⊡" units={units} value={one.inset} min={0} max={288} onChange={(inset) => set({ inset })} />
            <span />
          </Row>
          <Seg label="Vertical alignment" value={one.valign} options={VALIGNS} onChange={(valign) => set({ valign })} />
          <ThreadInfo frame={one.id} overset={overset} />
        </Section>
      )}

      {only === 'image' && one.kind === 'image' && (
        <Section title="Picture">
          <button type="button" onClick={() => store.set({ dialog: 'library' })}
            className="flex w-full items-center justify-center gap-2 rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-200 hover:border-emerald-500">
            <ImageIcon className="h-3.5 w-3.5" />{one.asset_id ? 'Replace picture…' : 'Choose a picture…'}
          </button>
          {one.asset_id && (
            <Row>
              <button type="button" onClick={() => store.set({ dialog: 'picture' })}
                className="flex items-center justify-center gap-1.5 rounded-md bg-emerald-600 py-1.5 text-xs font-medium text-white hover:bg-emerald-500">
                <SlidersHorizontal className="h-3.5 w-3.5" />Edit picture…
              </button>
              <button type="button" onClick={() => store.set({ dialog: 'cutout' })}
                className="flex items-center justify-center gap-1.5 rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-200 hover:border-emerald-500">
                <Scissors className="h-3.5 w-3.5" />Cut out…
              </button>
            </Row>
          )}
          {one.asset_id && assets[one.asset_id] && (
            <p className="truncate text-[11px] text-zinc-500" title={assets[one.asset_id].credit_line ?? ''}>
              {assets[one.asset_id].ai_generated ? 'AI illustration' : assets[one.asset_id].credit_line || 'No credit'}
            </p>
          )}
          <Seg label="Fit" value={one.fit} options={FITS} onChange={(fit) => set({ fit })} />
          <Slider label="Focus left" value={one.fx} min={0} max={100} unit="%" onChange={(fx) => set({ fx }, `fx:${one.id}`)} />
          <Slider label="Focus top" value={one.fy} min={0} max={100} unit="%" onChange={(fy) => set({ fy }, `fy:${one.id}`)} />
          <Slider label="Zoom" value={one.zoom} min={100} max={400} unit="%" onChange={(zoom) => set({ zoom }, `zoom:${one.id}`)} />
          <Labeled label="Caption (for the Text view)">
            <textarea value={one.caption} maxLength={500} rows={2} onChange={(e) => set({ caption: e.target.value }, `cap:${one.id}`)}
              className="w-full resize-none rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500" />
          </Labeled>
        </Section>
      )}

      {only === 'image' && one.kind === 'image' && one.asset_id && !one.cutout && items.length === 1 && (
        <Section title="Subject in front">
          <p className="text-[11px] leading-relaxed text-zinc-500">The person in the photo stands in front of the lettering over it: the photo
            stays behind the text, and its cut-out goes on top. Resize the new frame to choose which letters they cover.</p>
          <button type="button" disabled={!!subjectProblem(doc, one.id)} title={subjectProblem(doc, one.id) ?? undefined}
            onClick={() => {
              const cut = cutoutFor(assets, one.asset_id)
              if (cut) void placeSubject(c, one.id, cut)
              else store.set({ dialog: 'subject' })
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-200 hover:border-emerald-500 disabled:opacity-40">
            <PersonStanding className="h-3.5 w-3.5" />{cutoutFor(assets, one.asset_id) ? 'Put the subject in front' : 'Cut out the subject and put it in front…'}
          </button>
        </Section>
      )}

      {only === 'image' && <SpreadSection ids={ids} />}

      {only && only !== 'text' && only !== 'line' && <WrapSection items={items} set={set} units={units}
        subject={only === 'image' && items.every((i) => i.kind === 'image' && (!!i.shape || (items.length === 1 && isCutout(i.asset_id ? assets[i.asset_id] : undefined))))}
        shapeIt={async () => {
          // A frame showing a cut-out, with no silhouette yet: read it from the picture.
          if (one.kind !== 'image' || one.shape || !one.asset_id) return undefined
          try { return await subjectShape(c.siteId, one.asset_id) } catch { store.set({ notice: 'The cut-out couldn’t be read.' }); return null }
        }} />}

      {only === 'graphic' && one.kind === 'graphic' && (
        <Section title="Look">
          {/* Only the one-colour graphics take a colour: the server drops one on a colourful graphic,
              so giving it one here would show a silhouette the reader never sees. */}
          {inked.length > 0 && (
            <ColorField label="Colour" value={inked[0].color ?? ''}
              onChange={(color) => color && store.edit((d) => patchItems(d, inked.map((i) => i.id), { color }))} />
          )}
          {inked.length < items.length && (
            <p className="text-[11px] text-zinc-500">
              {inked.length ? 'The colourful graphics keep their own colours.' : 'A colourful graphic keeps its own colours.'}
            </p>
          )}
          <Seg label="In its box" value={one.fit} options={GRAPHIC_FITS} onChange={(fit) => set({ fit })} />
          {one.fit === 'tile' && (
            <LengthField label="Pattern size" short="▦" units={units} value={one.tile} min={2} max={720} onChange={(tile) => set({ tile })} />
          )}
        </Section>
      )}

      {(only === 'image' || only === 'rect') && 'radius' in one && (
        <Section title="Corners">
          <LengthField label="Corner radius" short="◜" units={units} value={one.radius} min={0} max={1000} onChange={(radius) => set({ radius })} />
        </Section>
      )}

      {only && only !== 'line' && 'fill' in one && (
        <Section title="Fill">
          <ColorField label="Fill" value={one.fill ?? ''} auto="None" onChange={(fill) => set({ fill: fill || null })} />
        </Section>
      )}

      {only && 'stroke' in one && (
        <StrokeSection stroke={one.stroke} line={only === 'line'} units={units}
          onChange={(stroke, colour) => set({ stroke, ...(colour ? { stroke_swatch: undefined } : {}) })} flip={one.kind === 'line' ? one.flip : undefined}
          onFlip={() => set({ flip: one.kind === 'line' && !one.flip })} />
      )}
    </>
  )
}

const WRAPS: { key: 'none' | Wrap['m']; label: string }[] = [
  { key: 'none', label: 'None' }, { key: 'box', label: 'Around the box' }, { key: 'subject', label: 'Around the subject' },
]

/** Text wrap: text on the page keeps away from the box, or from the cut-out
 *  subject of a picture (one with a shape, from Subject in front or a cut-out). */
function WrapSection({ items, set, subject, units, shapeIt }: { items: Item[]; set: (patch: Record<string, unknown>) => void; subject: boolean
  units: import('../../model/types').Units; shapeIt: () => Promise<Shape | null | undefined> }) {
  const wrap = 'wrap' in items[0] ? items[0].wrap : undefined
  const mode = wrap?.m ?? 'none'
  const choose = async (m: 'none' | Wrap['m']) => {
    if (m === 'none') { set({ wrap: undefined }); return }
    const next = { m, o: wrap?.o ?? 6 }
    if (m !== 'subject') { set({ wrap: next }); return }
    const shape = await shapeIt()
    if (shape === null) return
    set(shape ? { wrap: next, shape } : { wrap: next })
  }
  return (
    <Section title="Text wrap">
      <Seg label="Text wrap" value={mode} options={WRAPS.filter((w) => w.key !== 'subject' || subject)}
        onChange={(m) => void choose(m)} />
      {wrap && <LengthField label="Distance" short="↔" units={units} value={wrap.o} min={0} max={144}
        onChange={(o) => set({ wrap: { ...wrap, o } })} />}
      {!subject && items[0].kind === 'image' && <p className="text-[11px] text-zinc-500">To wrap the person in a photo, put the subject in front, or cut it out first.</p>}
    </Section>
  )
}

/** Pictures and the spread: one picture across both pages (or either side of
 *  the spine), and frames linked to show one picture between them. */
function SpreadSection({ ids }: { ids: string[] }) {
  const c = useCtx()
  // Only the document: the selection comes in as `ids` (a panel that took the
  // whole store would draw again on every zoom and hover).
  const doc = useStudio(c.store, (s) => s.doc)
  const group = ids.length === 1 ? groupOf(doc, ids[0]) : null
  const anyLinked = ids.some((id) => !!groupOf(doc, id))
  const can = (id: string) => { const cmd = command(id); return !cmd.enabled || cmd.enabled(c.store.get()) }
  const btn = 'flex items-center justify-center gap-1.5 rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-200 hover:border-emerald-500 disabled:border-zinc-800 disabled:text-zinc-600'
  const problem = ids.length > 1 ? linkProblem(doc, ids) : null
  if (ids.length === 1 && !group && !can('across-spread')) return null
  return (
    <Section title="Across the spread">
      {group ? (
        <p className="text-[11px] leading-relaxed text-zinc-400">
          <Link2 className="mr-1 inline h-3 w-3 text-emerald-400" />
          Shows one picture with {group.members.length - 1 === 1 ? 'another frame' : `${group.members.length - 1} other frames`}. Move or resize this
          frame to show a different part; change its focus or zoom to move the picture in all of them.
        </p>
      ) : ids.length === 1 ? (
        <Row>
          <button type="button" className={btn} onClick={() => command('across-spread').run(c)} title="Two frames, one on each page, out to the edges, showing one picture">
            <Columns2 className="h-3.5 w-3.5" />Across
          </button>
          <button type="button" className={btn} onClick={() => command('spine-clear').run(c)} title="One picture in two frames, the fold left white">
            <SeparatorVertical className="h-3.5 w-3.5" />Clear of spine
          </button>
        </Row>
      ) : (
        <button type="button" className={`${btn} w-full`} disabled={!!problem} title={problem ?? 'Show one picture through these frames'}
          onClick={() => command('link-crops').run(c)}>
          <Link2 className="h-3.5 w-3.5" />Link crops
        </button>
      )}
      {problem && ids.length > 1 && !anyLinked && <p className="text-[11px] text-zinc-500">{problem}</p>}
      {anyLinked && (
        <button type="button" className={`${btn} w-full`} onClick={() => command('unlink-crops').run(c)}>
          <Link2Off className="h-3.5 w-3.5" />Unlink crops
        </button>
      )}
    </Section>
  )
}

function StrokeSection({ stroke, line, onChange, units, flip, onFlip }: {
  stroke: Stroke | null; line: boolean; onChange: (s: Stroke | null, colour?: boolean) => void; units: import('../../model/types').Units
  flip?: boolean; onFlip: () => void
}) {
  const s = stroke ?? { c: '#1a1a1a', w: 0 }
  return (
    <Section title="Stroke">
      <ColorField label="Stroke colour" value={s.c} onChange={(c) => c && onChange({ c, w: s.w || 1 }, true)} />
      <Row>
        <LengthField label="Stroke weight" short="≡" units={units} value={s.w} min={line ? 0.25 : 0} max={144}
          onChange={(w) => onChange(w > 0 ? { c: s.c, w } : line ? { c: s.c, w: 0.25 } : null)} />
        {flip !== undefined ? (
          <button type="button" onClick={onFlip} aria-pressed={flip}
            className="rounded-md border border-zinc-800 text-[11px] text-zinc-300 hover:border-zinc-600">Flip ⤢</button>
        ) : <span />}
      </Row>
    </Section>
  )
}

function ThreadInfo({ frame, overset }: { frame: string; overset: Set<string> }) {
  const { store } = useCtx()
  const doc = useStudio(store, (s) => s.doc)
  const t = doc.threads.find((x) => x.frames.includes(frame))
  if (!t) return <p className="text-[11px] text-zinc-500">Empty. Double-click it to type, or click its out port ▸ to thread text into it from another frame.</p>
  const at = t.frames.indexOf(frame)
  const last = at === t.frames.length - 1
  return (
    <div className="space-y-1.5 text-[11px] text-zinc-400">
      <p>Frame {at + 1} of {t.frames.length} in this text.</p>
      {last && overset.has(t.id) && (
        <p className="rounded-md bg-red-500/10 px-2 py-1 text-red-300">
          Some text doesn't fit (overset). Make the frame bigger, or click its red ⊞ port and then another frame to flow it on.
        </p>
      )}
      {!last && (
        <button type="button" onClick={() => store.edit((d) => unlinkAfter(d, frame))}
          className="flex items-center gap-1.5 text-zinc-300 hover:text-white"><Link2Off className="h-3.5 w-3.5" />Stop the text flowing on from here</button>
      )}
    </div>
  )
}

const KIND_LABEL: Record<Item['kind'], string> = { text: 'Text frame', image: 'Picture frame', rect: 'Rectangle', ellipse: 'Ellipse', line: 'Line', graphic: 'Graphic' }
const ARRANGE: Record<Arrange, string> = { front: 'Bring to front', forward: 'Bring forward', backward: 'Send backward', back: 'Send to back' }
