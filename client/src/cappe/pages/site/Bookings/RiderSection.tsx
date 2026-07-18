import type { Dispatch, SetStateAction } from 'react'
import { Loader2, Trash2, Save, Lock } from 'lucide-react'
import type { CappeRiderItem } from '../../../types'
import { inputCls } from './constants'

interface RiderSectionProps {
  riderUnlocked: boolean | undefined
  rider: CappeRiderItem[]
  setRider: Dispatch<SetStateAction<CappeRiderItem[]>>
  setRiderItem: (i: number, patch: Partial<CappeRiderItem>) => void
  addRiderItem: () => void
  saveRider: () => void
  savingRider: boolean
}

export function RiderSection({
  riderUnlocked, rider, setRider, setRiderItem, addRiderItem, saveRider, savingRider,
}: RiderSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">Your rider</h2>
        {!riderUnlocked && <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-400"><Lock className="h-3 w-3" /> Pro</span>}
      </div>
      <p className="mb-3 mt-1 text-xs text-zinc-500">
        Requirements a client agrees to when booking you — point of contact, water/snacks, shade, travel covered, …
      </p>
      {!riderUnlocked ? (
        <p className="rounded-lg border border-dashed border-zinc-700 p-4 text-sm text-zinc-400">
          Riders are a <span className="text-zinc-200">Pro</span> creator feature. Upgrade to set the conditions you need met for every booking.
        </p>
      ) : (
        <>
          <div className="space-y-2">
            {rider.map((r, i) => (
              <div key={r.id} className="flex flex-wrap items-center gap-2">
                <input value={r.label} onChange={(e) => setRiderItem(i, { label: e.target.value })} placeholder="Requirement (e.g. Point of contact on site all day)" className={`flex-1 ${inputCls}`} />
                <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                  <input type="checkbox" checked={r.is_required} onChange={(e) => setRiderItem(i, { is_required: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                  Required
                </label>
                <button type="button" onClick={() => setRider((rl) => rl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={addRiderItem} className="text-xs font-medium text-emerald-400 hover:underline">+ Add requirement</button>
            <button onClick={saveRider} disabled={savingRider} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
              {savingRider ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save rider
            </button>
          </div>
        </>
      )}
    </section>
  )
}
