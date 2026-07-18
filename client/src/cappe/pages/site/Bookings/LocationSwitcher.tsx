import type { Dispatch, SetStateAction } from 'react'
import { Plus, Trash2, MapPin } from 'lucide-react'
import { CAPPE_TIMEZONES } from '../../../data/timezones'
import type { CappeLocation } from '../../../types'
import { inputCls } from './constants'
import type { LocForm } from './types'

interface LocationSwitcherProps {
  locations: CappeLocation[]
  selLoc: string
  switchLocation: (loc: string) => void
  showLocMgr: boolean
  setShowLocMgr: Dispatch<SetStateAction<boolean>>
  locForm: LocForm
  setLocForm: Dispatch<SetStateAction<LocForm>>
  addLocation: (e: React.FormEvent) => void
  setLocationDefault: (id: string) => void
  deactivateLocation: (id: string) => void
}

export function LocationSwitcher({
  locations, selLoc, switchLocation, showLocMgr, setShowLocMgr,
  locForm, setLocForm, addLocation, setLocationDefault, deactivateLocation,
}: LocationSwitcherProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-emerald-400" />
          {locations.filter((l) => l.active).length > 0 ? (
            <>
              <span className="text-xs text-zinc-500">Managing</span>
              <select value={selLoc} onChange={(e) => switchLocation(e.target.value)} className={inputCls}>
                {locations.filter((l) => l.active).map((l) => (
                  <option key={l.id} value={l.id}>{l.name}{l.is_default ? ' · default' : ''}</option>
                ))}
                <option value="">Shared · all locations</option>
              </select>
            </>
          ) : (
            <span className="text-sm text-zinc-400">One location. Add another to manage (e.g.) LA and San Diego separately.</span>
          )}
        </div>
        <button onClick={() => setShowLocMgr((o) => !o)} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800">
          {showLocMgr ? 'Done' : 'Manage locations'}
        </button>
      </div>
      {selLoc === '' && locations.filter((l) => l.active).length > 0 && (
        <p className="mt-2 text-xs text-zinc-500">Editing the <span className="text-zinc-300">shared</span> set — applies to every location. Pick a location to edit just its appointments.</p>
      )}
      {showLocMgr && (
        <div className="mt-4 space-y-2 border-t border-zinc-800 pt-4">
          {locations.filter((l) => l.active).map((l) => (
            <div key={l.id} className="flex items-center gap-2 text-sm">
              <span className="flex-1 text-zinc-200">
                {l.name}
                {l.is_default && <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">DEFAULT</span>}
                {l.timezone && <span className="ml-2 text-xs text-zinc-500">{l.timezone}</span>}
              </span>
              {!l.is_default && <button onClick={() => setLocationDefault(l.id)} className="text-xs text-zinc-400 hover:text-emerald-400">Make default</button>}
              <button onClick={() => deactivateLocation(l.id)} className="text-zinc-500 hover:text-red-400" title="Deactivate"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <form onSubmit={addLocation} className="grid grid-cols-2 gap-2 pt-1 sm:grid-cols-4">
            <input value={locForm.name} onChange={(e) => setLocForm((f) => ({ ...f, name: e.target.value }))} placeholder="Name (e.g. LA)" className={inputCls} />
            <select value={locForm.timezone} onChange={(e) => setLocForm((f) => ({ ...f, timezone: e.target.value }))} className={inputCls}>
              <option value="">Timezone…</option>
              {CAPPE_TIMEZONES.map((tz) => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
            </select>
            <input value={locForm.address} onChange={(e) => setLocForm((f) => ({ ...f, address: e.target.value }))} placeholder="Address" className={inputCls} />
            <input value={locForm.phone} onChange={(e) => setLocForm((f) => ({ ...f, phone: e.target.value }))} placeholder="Phone" className={inputCls} />
            <button type="submit" className="col-span-2 inline-flex items-center justify-center gap-1 rounded-lg border border-dashed border-zinc-700 py-2 text-sm font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400 sm:col-span-4">
              <Plus className="h-4 w-4" /> Add location
            </button>
          </form>
        </div>
      )}
    </section>
  )
}
