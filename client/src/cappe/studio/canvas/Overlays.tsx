import { facingPage, groupOf } from '../model/crops'
import { pageSide } from '../model/doc'
import { GUTTER_SAFE } from '../model/gutter'
import type { Doc, Item, TextItem } from '../model/types'
import { useStudio } from '../store/store'
import { useCtx } from '../ui/context'
import { bounds, centre, itemBox, type Layout } from './geometry'
import { HANDLES } from './transform'

const MARGIN = '#d946ef' // magenta, as print layout tools draw margins
const COLUMN = '#8b5cf6' // violet column guides
const GUIDE = '#22d3ee' // ruler guides
const SELECT = '#10b981'
const GUTTER = 'rgba(245,158,11,.16)' // the strip the binding hides

/** The page's margins and columns, its guides, the grids, the gutter; the
 *  selection's handles, threads and linked frames; smart guides while
 *  dragging; the marquee. */
export function Overlays({ lay }: { lay: Layout }) {
  const { store } = useCtx()
  const doc = useStudio(store, (s) => s.doc)
  const view = useStudio(store, (s) => s.view)
  const selection = useStudio(store, (s) => s.selection)
  const editing = useStudio(store, (s) => s.editing)
  const snaps = useStudio(store, (s) => s.snaps)
  const marquee = useStudio(store, (s) => s.marquee)
  const overset = useStudio(store, (s) => s.overset)
  const z = view.zoom
  const pageOf = new Map(doc.pages.map((p, i) => [p.id, i]))
  const originOf = (i: Item) => lay.origin[pageOf.get(i.page) ?? 0]
  const chosen = doc.items.filter((i) => selection.includes(i.id))
  // The frames showing one picture with a selected one (model/crops.ts).
  const partners = editing ? [] : [...new Map(chosen.flatMap((i) => groupOf(doc, i.id)?.members ?? [])
    .filter((m) => !selection.includes(m.id)).map((m) => [m.id, m])).values()]
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      {doc.pages.map((p, i) => <PageGuides key={p.id} doc={doc} index={i} lay={lay} />)}
      {partners.map((m) => {
        const b = itemBox(m, originOf(m))
        return <div key={m.id} className="absolute" style={{ left: b.x * z, top: b.y * z, width: b.w * z, height: b.h * z,
          outline: `1px dashed ${SELECT}`, outlineOffset: -1 }} />
      })}
      {!editing && chosen.length === 1 && <Handles item={chosen[0]} originOf={originOf} />}
      {!editing && chosen.length > 1 && <GroupBox items={chosen} originOf={originOf} z={z} />}
      {chosen.filter((i): i is TextItem => i.kind === 'text').map((i) => (
        <Ports key={i.id} item={i} doc={doc} originOf={originOf} overset={overset} />
      ))}
      {snaps?.x.map((x, k) => <div key={`x${k}`} className="absolute top-0 h-full" style={{ left: x * z, width: 1, background: '#f43f5e' }} />)}
      {snaps?.y.map((y, k) => <div key={`y${k}`} className="absolute left-0 w-full" style={{ top: y * z, height: 1, background: '#f43f5e' }} />)}
      {marquee && (
        <div className="absolute border border-emerald-400 bg-emerald-400/10"
          style={{ left: marquee.x * z, top: marquee.y * z, width: marquee.w * z, height: marquee.h * z }} />
      )}
    </div>
  )
}

function PageGuides({ doc, index, lay }: { doc: Doc; index: number; lay: Layout }) {
  const { store } = useCtx()
  const view = useStudio(store, (s) => s.view)
  const z = view.zoom
  const o = lay.origin[index]
  const { w, h } = doc.size
  const m = doc.margins
  const left = pageSide(doc, index) === 'left'
  const ml = left ? m.o : m.i, mr = left ? m.i : m.o
  const inner = w - ml - mr
  const cw = (inner - doc.cols.g * (doc.cols.n - 1)) / doc.cols.n
  const pid = doc.pages[index].id
  const box = { left: o.x * z, top: o.y * z, width: w * z, height: h * z }
  const baseStep = doc.baseline.step * z
  return (
    <div className="absolute" style={box}>
      {view.grid && (
        <div className="absolute inset-0" style={{
          backgroundImage: `linear-gradient(to right, rgba(148,163,184,.25) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,.25) 1px, transparent 1px)`,
          backgroundSize: `${doc.grid.step * z}px ${doc.grid.step * z}px`,
        }} />
      )}
      {view.baseline && baseStep >= 3 && (
        <div className="absolute inset-x-0 bottom-0" style={{
          top: doc.baseline.start * z - baseStep,
          backgroundImage: `linear-gradient(to bottom, transparent ${baseStep - 1}px, rgba(56,189,248,.45) ${baseStep - 1}px)`,
          backgroundSize: `100% ${baseStep}px`,
        }} />
      )}
      {view.margins && (
        <>
          <div className="absolute" style={{ left: ml * z, top: m.t * z, width: inner * z, height: (h - m.t - m.b) * z,
            outline: `1px solid ${MARGIN}` }} />
          {Array.from({ length: doc.cols.n - 1 }, (_, c) => {
            const x1 = ml + (c + 1) * cw + c * doc.cols.g
            return (
              <div key={c} className="absolute" style={{ left: x1 * z, top: m.t * z, width: doc.cols.g * z,
                height: (h - m.t - m.b) * z, borderLeft: `1px solid ${COLUMN}`, borderRight: `1px solid ${COLUMN}` }} />
            )
          })}
        </>
      )}
      {view.gutter && facingPage(doc, index) !== null && (
        <div className="absolute top-0 h-full" style={{ [left ? 'right' : 'left']: 0, width: GUTTER_SAFE * z,
          background: `repeating-linear-gradient(135deg, ${GUTTER} 0 4px, transparent 4px 8px)` }} />
      )}
      {view.guides && doc.guides.filter((g) => g.page === pid).map((g) => (
        <div key={g.id} className="absolute" style={g.axis === 'v'
          ? { left: g.at * z, top: 0, height: h * z, width: 1, background: GUIDE }
          : { top: g.at * z, left: 0, width: w * z, height: 1, background: GUIDE }} />
      ))}
    </div>
  )
}

const HANDLE = 8

function Handles({ item, originOf }: { item: Item; originOf: (i: Item) => { x: number; y: number } }) {
  const { store } = useCtx()
  const z = useStudio(store, (s) => s.view.zoom)
  const b = itemBox(item, originOf(item))
  const c = centre(b)
  const w = b.w * z, h = b.h * z
  const pos: Record<string, [number, number]> = {}
  for (const [k, [hx, hy]] of Object.entries(HANDLES)) pos[k] = [((hx + 1) / 2) * w, ((hy + 1) / 2) * h]
  const line = item.kind === 'line'
  return (
    <div className="absolute" style={{ left: b.x * z, top: b.y * z, width: w, height: h,
      transform: item.rot ? `rotate(${item.rot}deg)` : undefined, transformOrigin: `${(c.x - b.x) * z}px ${(c.y - b.y) * z}px`,
      outline: line ? undefined : `1px solid ${item.locked ? '#a1a1aa' : SELECT}` }}>
      {!item.locked && Object.entries(pos)
        .filter(([k]) => !line || k === 'w' || k === 'e' || k === 'nw' || k === 'se')
        .map(([k, [x, y]]) => (
          <div key={k} data-handle={k} className="pointer-events-auto absolute border bg-white"
            style={{ left: x - HANDLE / 2, top: y - HANDLE / 2, width: HANDLE, height: HANDLE, borderColor: SELECT,
              cursor: `${k}-resize` }} />
        ))}
      {!item.locked && (
        <div data-handle="rot" title="Turn" className="pointer-events-auto absolute rounded-full border bg-white"
          style={{ left: w / 2 - 5, top: -26, width: 10, height: 10, borderColor: SELECT, cursor: 'grab' }} />
      )}
    </div>
  )
}

function GroupBox({ items, originOf, z }: { items: Item[]; originOf: (i: Item) => { x: number; y: number }; z: number }) {
  const b = bounds(items, originOf)
  if (!b) return null
  return <div className="absolute" style={{ left: b.x * z, top: b.y * z, width: b.w * z, height: b.h * z,
    outline: `1px dashed ${SELECT}` }} />
}

/** A text frame's in and out ports: click the out port, then a frame, to
 *  thread text on into it. A red "+" says text is left over. */
function Ports({ item, doc, originOf, overset }: {
  item: TextItem; doc: Doc; originOf: (i: Item) => { x: number; y: number }; overset: Set<string>
}) {
  const { store } = useCtx()
  const z = useStudio(store, (s) => s.view.zoom)
  const thread = doc.threads.find((t) => t.frames.includes(item.id))
  const at = thread ? thread.frames.indexOf(item.id) : -1
  const b = itemBox(item, originOf(item))
  const last = thread && at === thread.frames.length - 1
  const over = !!(thread && last && overset.has(thread.id))
  const linkedIn = thread && at > 0
  const linkedOut = thread && !last
  const port = (x: number, y: number, kind: 'in' | 'out', inner: string, red = false) => (
    <div data-port={kind} data-frame={item.id} title={kind === 'out' ? 'Thread text into another frame' : 'Text flows in here'}
      className="pointer-events-auto absolute flex items-center justify-center border bg-white text-[9px] font-bold leading-none"
      style={{ left: x - 6, top: y - 6, width: 12, height: 12, borderColor: red ? '#ef4444' : SELECT,
        color: red ? '#ef4444' : SELECT, cursor: 'pointer' }}>{inner}</div>
  )
  return (
    <>
      {port(b.x * z + 14, b.y * z, 'in', linkedIn ? '▸' : '')}
      {port((b.x + b.w) * z - 14, (b.y + b.h) * z, 'out', over ? '+' : linkedOut ? '▸' : '', over)}
    </>
  )
}
