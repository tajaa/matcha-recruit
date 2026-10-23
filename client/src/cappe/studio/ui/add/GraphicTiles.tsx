import { useState } from 'react'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { graphicUrl, type GraphicCard, type GraphicGroup } from '../../model/graphics'
import { useCtx } from '../context'
import { endDrag, startDrag } from './drag'
import { GROUP_TITLE, useGraphicSearch } from './graphicSearch'
import { addGraphic } from './place'

const STICKER_SETS = ['Faces', 'People', 'Animals and nature', 'Food and drink', 'Travel and places', 'Activities', 'Objects', 'Symbols', 'Flags']
const COLS: Record<GraphicGroup, string> = {
  shapes: 'grid-cols-4', lines: 'grid-cols-2', badges: 'grid-cols-4', icons: 'grid-cols-5', stickers: 'grid-cols-4', patterns: 'grid-cols-4',
}

/** A graphic as a tile: a one-colour one drawn in a light grey (patterns as
 *  their repeat), a colourful one as it is. */
function Art({ g }: { g: GraphicCard }) {
  const url = `url(${graphicUrl(g.sha)})`
  if (!g.mono) return <img src={graphicUrl(g.sha)} alt="" loading="lazy" draggable={false} className="h-full w-full object-contain" />
  const tile = g.fit === 'tile'
  const mask = `${url} ${tile ? '0 0/14px auto repeat' : 'center/contain no-repeat'}`
  return <span aria-hidden className="block h-full w-full" style={{ background: '#d4d4d8', WebkitMask: mask, mask }} />
}

export function GraphicTile({ g }: { g: GraphicCard }) {
  const c = useCtx()
  return (
    <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'graphic', g })} onDragEnd={endDrag}
      onClick={() => addGraphic(c, g)} aria-label={`Add ${g.name}`} title={g.name}
      className={`flex items-center justify-center rounded-md border border-zinc-800 bg-zinc-950/60 hover:border-emerald-500 ${g.group === 'lines' ? 'h-10 px-2' : 'aspect-square p-2'}`}>
      <Art g={g} />
    </button>
  )
}

export function GraphicGrid({ items, group }: { items: GraphicCard[]; group?: GraphicGroup }) {
  return (
    <div className={`grid gap-1.5 ${COLS[group ?? 'icons']}`}>
      {items.map((g) => <GraphicTile key={g.sha} g={g} />)}
    </div>
  )
}

function More({ shown, total, busy, onMore }: { shown: number; total: number | null; busy: boolean; onMore: () => void }) {
  if (busy && !shown) return <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Loading…</p>
  if (total === null || shown >= total) return null
  return (
    <button type="button" onClick={onMore} disabled={busy}
      className="w-full rounded-md border border-zinc-700 py-1.5 text-xs text-zinc-300 hover:border-zinc-500">
      {busy ? 'Loading…' : `More (${total - shown} left)`}
    </button>
  )
}

/** Every graphic in one group, with the sticker sets to narrow it. */
export function GroupView({ group, q, onBack }: { group: GraphicGroup; q: string; onBack: () => void }) {
  const [set, setSet] = useState<string | undefined>(undefined)
  const found = useGraphicSearch(q, group, set)
  return (
    <div className="space-y-3">
      <button type="button" onClick={onBack} className="flex items-center gap-1 text-xs text-zinc-300 hover:text-white">
        <ArrowLeft className="h-3.5 w-3.5" />{GROUP_TITLE[group]}{found.total !== null && <span className="text-zinc-500"> · {found.total}</span>}
      </button>
      {group === 'stickers' && (
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Sticker sets">
          {[undefined, ...STICKER_SETS].map((s) => (
            <button key={s ?? 'all'} type="button" role="tab" aria-selected={set === s} onClick={() => setSet(s)}
              className={`rounded-full px-2.5 py-1 text-[11px] ${set === s ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-100'}`}>
              {s ?? 'All'}
            </button>
          ))}
        </div>
      )}
      {found.error && <p role="alert" className="text-xs text-red-300">{found.error}</p>}
      <GraphicGrid items={found.items} group={group} />
      {found.total === 0 && <p className="text-xs text-zinc-500">Nothing matches.</p>}
      <More shown={found.items.length} total={found.total} busy={found.busy} onMore={found.more} />
    </div>
  )
}

/** Search results across the whole bank. */
export function SearchResults({ q }: { q: string }) {
  const found = useGraphicSearch(q)
  return (
    <div className="space-y-2">
      {found.error && <p role="alert" className="text-xs text-red-300">{found.error}</p>}
      {found.items.length > 0 && <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Graphics · {found.total}</h3>}
      <GraphicGrid items={found.items} />
      <More shown={found.items.length} total={found.total} busy={found.busy} onMore={found.more} />
    </div>
  )
}
