import type { PropertyBuilding } from '../../../types/property'
import { PERIL_TONE } from '../../../types/property'

const PERILS = ['flood', 'quake', 'wildfire', 'wind'] as const
const PERIL_LABEL: Record<string, string> = { flood: 'Flood', quake: 'Earthquake', wildfire: 'Wildfire', wind: 'Wind' }

export function PerilDetail({ b }: { b: PropertyBuilding }) {
  if (!b.geocoded_at) {
    return <p className="text-[11px] text-zinc-500">Catastrophe exposure pending — add a full street address; geocoding runs in the background.</p>
  }
  const byPeril = Object.fromEntries(b.perils.map((p) => [p.peril, p]))
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      {PERILS.map((k) => {
        const p = byPeril[k]
        return (
          <div key={k} className="rounded-lg bg-zinc-950/60 border border-zinc-800/60 px-3 py-2">
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{PERIL_LABEL[k]}</div>
            {p && p.tier ? (
              <>
                <div className={`text-sm font-semibold uppercase ${PERIL_TONE[p.tier] ?? 'text-zinc-300'}`}>{p.tier}</div>
                <div className="text-[10px] text-zinc-600">{p.zone ?? '—'}{p.source ? ` · ${p.source}` : ''}</div>
              </>
            ) : p && p.error ? (
              <div className="text-[10px] text-zinc-600">lookup failed</div>
            ) : (
              <div className="text-[10px] text-zinc-600">—</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
